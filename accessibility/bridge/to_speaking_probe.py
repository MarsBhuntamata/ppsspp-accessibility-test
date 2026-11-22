#!/usr/bin/env python3
"""Tactics Ogre accessible interim screen-reader bridge for Windows + PPSSPP.

This is an OCR-based fallback, NOT native semantic Tactics Ogre menu support.
Captures PPSSPP's on-screen window without pausing the emulator and
recognizes it using Windows' built-in, offline OCR engine.
Ctrl+Alt+Shift+O: read screen; Ctrl+Alt+Shift+P: repeat; Ctrl+Alt+Shift+Q: quit.
No game memory, ISO, save, or emulator setting is written.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import ctypes
from ctypes import wintypes
import json
import os
import queue
import re
import tempfile
import threading
import time
from pathlib import Path

USER32 = ctypes.windll.user32 if hasattr(ctypes, "windll") else None
WM_HOTKEY = 0x0312
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_NOREPEAT = 0x4000
HOTKEY_MODIFIERS = MOD_ALT | MOD_CONTROL | MOD_SHIFT | MOD_NOREPEAT
HOTKEY_IDS = {1: ord('O'), 2: ord('P'), 3: ord('Q')}


def extract_screenshot(response: dict) -> bytes:
    uri = response.get("uri", "")
    prefix = "data:image/png;base64,"
    if response.get("event") != "gpu.buffer.screenshot" or not uri.startswith(prefix):
        raise ValueError("PPSSPP did not return a PNG screenshot")
    result = base64.b64decode(uri[len(prefix):], validate=True)
    if not result.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("Invalid PNG data")
    return result


def clean_text(text: str) -> str:
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def new_lines(previous: str, current: str) -> str:
    """Prefer newly appearing lines for automatic reads; preserve order."""
    old = set(previous.splitlines())
    fresh = [line for line in current.splitlines() if line not in old]
    return "\n".join(fresh) or current



def find_ppsspp_window():
    """Find a visible PPSSPP top-level window, preferring one with a game title.

    This uses the normal Win32 window list, not an emulator debugger GPU hook.
    """
    if USER32 is None:
        raise RuntimeError("Windows only")
    matches = []
    cb_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    @cb_type
    def inspect(hwnd, lparam):
        if not USER32.IsWindowVisible(hwnd) or USER32.IsIconic(hwnd):
            return True
        length = USER32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buffer = ctypes.create_unicode_buffer(length + 1)
        USER32.GetWindowTextW(hwnd, buffer, len(buffer))
        title = buffer.value
        if "ppsspp" in title.lower():
            rect = wintypes.RECT()
            if USER32.GetWindowRect(hwnd, ctypes.byref(rect)):
                bbox = (rect.left, rect.top, rect.right, rect.bottom)
                if bbox[2] - bbox[0] > 150 and bbox[3] - bbox[1] > 100:
                    matches.append((hwnd, title, bbox))
        return True

    USER32.EnumWindows(inspect, 0)
    if not matches:
        raise RuntimeError("No visible PPSSPP window found. Keep PPSSPP open and not minimized.")
    # Longer titles commonly contain the game name; prefer that over incidental windows.
    return max(matches, key=lambda row: len(row[1]))


def capture_game_window(path: Path):
    """Capture displayed PPSSPP pixels using Pillow, no CPU/GPU stepping.

    If the bridge console is in front, temporarily minimize that console.
    The game remains running and no key is sent to PPSSPP.
    """
    from PIL import ImageGrab
    _, title, bbox = find_ppsspp_window()
    kernel32 = ctypes.windll.kernel32
    console = kernel32.GetConsoleWindow()
    # Do not hide the window if PPSSPP happens to be in the foreground.
    front = USER32.GetForegroundWindow()
    hidden = bool(console and front == console)
    try:
        if hidden:
            USER32.ShowWindow(console, 6)  # SW_MINIMIZE
            time.sleep(0.3)
        screenshot = ImageGrab.grab(bbox=bbox, all_screens=True)
        screenshot.save(path, "PNG")
        return title
    finally:
        if hidden:
            USER32.ShowWindow(console, 9)  # SW_RESTORE


def console_key():
    """Nonblocking fallback controls for when PPSSPP intercepts global hotkeys."""
    if os.name != "nt":
        return None
    import msvcrt
    if not msvcrt.kbhit():
        return None
    value = msvcrt.getwch()
    if value in ("\\r", "\\n", "o", "O"):
        return "read"
    if value in ("r", "R", "p", "P"):
        return "repeat"
    if value in ("q", "Q", "\\x1b"):
        return "stop"
    return None


class Voice:
    """Reliable local Windows SAPI speech, with a queue and COM initialization.

    Synchronous Speak avoids the silent async COM worker issue in v0.1.
    Speech does not require NVDA, so it works even with NVDA running.
    """
    def __init__(self):
        self.messages = queue.Queue()
        self.worker = threading.Thread(target=self._run, daemon=True)
        self.worker.start()

    def say(self, text: str):
        if text:
            print("SPEAK:", text, flush=True)
            self.messages.put(str(text))

    def _run(self):
        try:
            import pythoncom
            import win32com.client
            pythoncom.CoInitialize()
            try:
                voice = win32com.client.Dispatch("SAPI.SpVoice")
                while True:
                    item = self.messages.get()
                    if item is None:
                        break
                    # Synchronous speech in a COM-initialized thread.
                    # The older async call could return without ever speaking.
                    voice.Speak(item, 0)
            finally:
                pythoncom.CoUninitialize()
        except Exception as exc:
            print("SAPI ERROR:", repr(exc), flush=True)
            while True:
                item = self.messages.get()
                if item is None:
                    return
                print("UNSPOKEN:", item, flush=True)

    def stop(self):
        self.messages.put(None)

class Ppsspp:
    def __init__(self, port: int):
        import websocket
        self.ws = websocket.create_connection(
            f"ws://127.0.0.1:{port}/debugger",
            subprotocols=["debugger.ppsspp.org"],
            timeout=12,
            enable_multithread=True,
        )
        self.ticket = 0

    def request(self, event: str, **args) -> dict:
        self.ticket += 1
        ticket = self.ticket
        self.ws.send(json.dumps({"event": event, "ticket": ticket, **args}))
        while True:
            response = json.loads(self.ws.recv())
            if response.get("ticket") != ticket:
                continue  # ignore unrelated broadcast events
            if response.get("event") == "error":
                raise RuntimeError(response.get("message", "Debugger error"))
            return response

    def close(self):
        self.ws.close()


async def windows_ocr(path: Path) -> str:
    from winrt.windows.media.ocr import OcrEngine
    from winrt.windows.graphics.imaging import BitmapDecoder
    from winrt.windows.storage import StorageFile

    source = await StorageFile.get_file_from_path_async(str(path.resolve()))
    stream = await source.open_read_async()
    decoder = await BitmapDecoder.create_async(stream)
    bitmap = await decoder.get_software_bitmap_async()
    engine = OcrEngine.try_create_from_user_profile_languages()
    if engine is None:
        raise RuntimeError("No Windows OCR language installed for your profile")
    result = await engine.recognize_async(bitmap)
    return clean_text("\n".join(line.text for line in result.lines))


class Bridge:
    def __init__(self, port: int):
        self.port = port
        self.voice = Voice()
        self.actions = queue.Queue()
        self.latest = ""
        self.done = threading.Event()

    def run_worker(self):
        client = None
        try:
            client = Ppsspp(self.port)
            status = client.request("game.status")
            game = status.get("game") or {}
            identity = str(status.get("title") or status.get("id") or game.get("title") or game.get("id") or "unknown game")
            self.voice.say(f"Connected to PPSSPP. {identity}. In this bridge window press Enter to read, R to repeat, Q to quit. Global shortcuts may also work.")
            with tempfile.TemporaryDirectory(prefix="to_accessibility_") as temp:
                picture = Path(temp) / "capture.png"
                while not self.done.is_set():
                    try:
                        action = self.actions.get(timeout=0.2)
                    except queue.Empty:
                        continue
                    if action == "stop":
                        return
                    if action == "repeat":
                        self.voice.say(self.latest or "Nothing has been recognized yet.")
                        continue
                    if action != "read":
                        continue
                    try:
                        window_title = capture_game_window(picture)
                        print("Captured:", window_title, flush=True)
                        recognized = asyncio.run(windows_ocr(picture))
                        if recognized:
                            self.latest = recognized
                            self.voice.say(recognized)
                        else:
                            self.voice.say("No text recognized on the current screen.")
                    except Exception as exc:
                        print("CAPTURE/OCR ERROR:", repr(exc), flush=True)
                        self.voice.say(f"Read failed. {exc}")
        except Exception as exc:
            self.voice.say(f"Cannot connect to PPSSPP. {exc}")
        finally:
            if client:
                client.close()

    def run(self):
        if USER32 is None:
            raise RuntimeError("This prototype requires Windows")
        registered = []
        self.voice.say("Tactics Ogre speech test. Use Enter to read, R to repeat, Q to quit.")
        try:
            for hotkey_id, vk in HOTKEY_IDS.items():
                if USER32.RegisterHotKey(None, hotkey_id, HOTKEY_MODIFIERS, vk):
                    registered.append(hotkey_id)
                else:
                    print("Global hotkey unavailable:", chr(vk), flush=True)
            self.voice.say("Starting PPSSPP connection.")
            worker = threading.Thread(target=self.run_worker, daemon=True)
            worker.start()
            msg = wintypes.MSG()
            # Poll messages and console keys without losing the ability to read
            # while the bridge is focused. Global hotkeys are optional.
            while not self.done.is_set():
                while USER32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
                    if msg.message == WM_HOTKEY:
                        action = {1: "read", 2: "repeat", 3: "stop"}.get(msg.wParam)
                        if action == "stop":
                            return
                        if action:
                            self.actions.put(action)
                    elif msg.message == 0x0012:  # WM_QUIT
                        return
                    else:
                        USER32.TranslateMessage(ctypes.byref(msg))
                        USER32.DispatchMessageW(ctypes.byref(msg))
                action = console_key()
                if action == "stop":
                    return
                if action:
                    self.actions.put(action)
                time.sleep(0.03)
        finally:
            self.done.set()
            self.actions.put("stop")
            for ident in registered:
                USER32.UnregisterHotKey(None, ident)
            self.voice.stop()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=56244)
    args = parser.parse_args()
    Bridge(args.port).run()


if __name__ == "__main__":
    main()
