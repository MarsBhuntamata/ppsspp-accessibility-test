// Copyright (c) 2018- PPSSPP Project.

// This program is free software: you can redistribute it and/or modify
// it under the terms of the GNU General Public License as published by
// the Free Software Foundation, version 2.0 or later versions.

// This program is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU General Public License 2.0 for more details.

// A copy of the GPL 2.0 should have been included with the program.
// If not, see http://www.gnu.org/licenses/

// Official git repository and contact information can be found at
// https://github.com/hrydgard/ppsspp and http://www.ppsspp.org/.

#include <unordered_map>
#include <cstring>
#include <vector>
#include "Core/Core.h"
#include "Core/MemMap.h"
#include "Core/ELF/ParamSFO.h"
#include "Core/System.h"
#include "Core/Debugger/WebSocket/InputBroadcaster.h"
#include "Core/Debugger/WebSocket/InputSubscriber.h"
#include "Core/Debugger/WebSocket/WebSocketUtils.h"
#include "Core/HLE/sceCtrl.h"
#include "Core/HW/Display.h"

// Button press state change (input.buttons)
//
// Sent unexpectedly with these properties:
//  - buttons: an object with button names as keys and bool press state as values.
//  - changed: same as buttons, but only including changed states.
//
// See input.buttons.send in InputSubscriber for button names.

// Analog position change (input.analog)
//
// Sent unexpectedly with these properties:
//  - stick: "left" or "right".
//  - x: number between -1.0 and 1.0, representing horizontal position in a square.
//  - y: number between -1.0 and 1.0, representing vertical position in a square.

std::string InputBroadcaster::Analog::Event(const char *stick) {
	JsonWriter j;
	j.begin();
	j.writeString("event", "input.analog");
	j.writeString("stick", stick);
	j.writeFloat("x", x);
	j.writeFloat("y", y);
	j.end();
	return j.str();
}

static std::string ButtonsEvent(uint32_t lastButtons, uint32_t newButtons) {
	uint32_t pressed = newButtons & ~lastButtons;
	uint32_t released = ~newButtons & lastButtons;

	JsonWriter j;
	j.begin();
	j.writeString("event", "input.buttons");
	j.pushDict("buttons");
	for (auto it : WebSocketInputButtonLookup()) {
		j.writeBool(it.first, (newButtons & it.second) != 0);
	}
	j.pop();
	j.pushDict("changed");
	for (auto it : WebSocketInputButtonLookup()) {
		if (pressed & it.second) {
			j.writeBool(it.first, true);
		} else if (released & it.second) {
			j.writeBool(it.first, false);
		}
	}
	j.pop();
	j.end();
	return j.str();
}

// Observe a 32 KiB candidate region only when an attached debugger sees a
// directional release.  The memory copy executes on PPSSPP's CPU thread.
// This does not identify the selected option: changes include game timers.
static std::string TacticsOgreNavigationSample(const std::string &direction,
		const std::vector<uint8_t> &previous, std::vector<uint8_t> *next,
		std::string *previousGame, uint32_t address) {
	std::string gameId;
	bool valid = false;
	constexpr uint32_t kSampleSize = 0x8000;
	Core_RunOnCPUThread([&] {
		if (PSP_GetBootState() != BootState::Complete || !Memory::IsActive())
			return;
		gameId = g_paramSFO.GetDiscID();
		if (gameId != "ULUS10565" && gameId != "ULES10500" && gameId != "ULJM05753")
			return;
		if (!Memory::IsValidRange(address, kSampleSize))
			return;
		next->resize(kSampleSize);
		memcpy(next->data(), Memory::GetPointerUnchecked(address), kSampleSize);
		valid = true;
	});
	if (!valid) {
		next->clear();
		previousGame->clear();
		return {};
	}
	bool first = *previousGame != gameId || previous.size() != next->size();
	JsonWriter json;
	json.begin();
	json.writeString("event", "accessibility.tacticsOgre.navigation");
	json.writeString("gameId", gameId);
	json.writeString("direction", direction);
	json.writeBool("firstSample", first);
	json.writeUint("region", address);
	json.writeUint("regionSize", kSampleSize);
	uint32_t changed = 0;
	if (!first) {
		for (size_t offset = 0; offset < next->size(); offset += 4)
			if (memcmp(previous.data() + offset, next->data() + offset, 4) != 0)
				++changed;
	}
	json.writeUint("changedWords", changed);
	json.writeBool("truncated", changed > 64);
	json.pushArray("changes");
	uint32_t emitted = 0;
	if (!first) {
		for (size_t offset = 0; offset < next->size() && emitted < 64; offset += 4) {
			if (memcmp(previous.data() + offset, next->data() + offset, 4) == 0)
				continue;
			uint32_t before = 0, after = 0;
			memcpy(&before, previous.data() + offset, 4);
			memcpy(&after, next->data() + offset, 4);
			json.pushDict();
			json.writeUint("address", address + (uint32_t)offset);
			json.writeUint("before", before);
			json.writeUint("after", after);
			json.pop();
			++emitted;
		}
	}
	json.pop();
	json.end();
	*previousGame = gameId;
	return json.str();
}

void InputBroadcaster::Broadcast(net::WebSocketServer *ws) {
	int counter = __DisplayGetNumVblanks();
	if (lastCounter_ == counter)
		return;
	lastCounter_ = counter;

	// Read the game after several vblanks, allowing the menu to react
	// to a release without stopping emulation or sending any input.
	if (navigationDueVblank_ >= 0 && counter >= navigationDueVblank_) {
		std::vector<uint8_t> next;
		std::string event = TacticsOgreNavigationSample(navigationDirection_,
			navigationPrevious_, &next, &navigationGame_, navigationAddress_);
		if (!event.empty()) {
			ws->Send(event);
			navigationPrevious_.swap(next);
		} else {
			navigationPrevious_.clear();
		}
		navigationDueVblank_ = -1;
	}

	uint32_t newButtons = __CtrlPeekButtons();
	if (newButtons != lastButtons_) {
		ws->Send(ButtonsEvent(lastButtons_, newButtons));
		const uint32_t released = lastButtons_ & ~newButtons;
		if (released & (CTRL_UP | CTRL_DOWN | CTRL_LEFT | CTRL_RIGHT)) {
			const uint32_t key = released & (CTRL_UP | CTRL_DOWN | CTRL_LEFT | CTRL_RIGHT);
			navigationDirection_ = (key & CTRL_UP) ? "up" :
				(key & CTRL_DOWN) ? "down" :
				(key & CTRL_LEFT) ? "left" : "right";
			navigationDueVblank_ = counter + 3;
		}
		lastButtons_ = newButtons;
	}

	Analog newAnalog;
	__CtrlPeekAnalog(CTRL_STICK_LEFT, &newAnalog.x, &newAnalog.y);
	if (!lastAnalog_[0].Equals(newAnalog)) {
		ws->Send(newAnalog.Event("left"));
		lastAnalog_[0].x = newAnalog.x;
		lastAnalog_[0].y = newAnalog.y;
	}

	__CtrlPeekAnalog(CTRL_STICK_RIGHT, &newAnalog.x, &newAnalog.y);
	if (!lastAnalog_[1].Equals(newAnalog)) {
		ws->Send(newAnalog.Event("right"));
		lastAnalog_[1].x = newAnalog.x;
		lastAnalog_[1].y = newAnalog.y;
	}
}
