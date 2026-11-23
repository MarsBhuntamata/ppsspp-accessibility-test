#!/usr/bin/env python3
"""Experimental speaking Tactics Ogre title-menu reader for stock PPSSPP.

Reads the discovered PSP memory address 0x0964271C on navigation releases.
No OCR, game patching, memory writes, or unverified text labels. This is not
yet a reader for inventory, dialogue, or battle menus.
"""
from __future__ import annotations

import argparse
import base64
import ctypes
import json
import os
from pathlib import Path
import sys
import time

from to_target_watch import Connection, directions_released, WINDOW, SIZE, OFFSET, ADDRESS

GAME_IDS = {"ULUS10565", "ULES10500", "ULJM05753"}
LOG_NAME = "tactics-ogre-speaking-log.txt"


def folder():
    return Path(sys.executable if getattr(sys, "frozen", False) else __file__).resolve().parent


def selection_announcement(value):
    """Labels deliberately withheld until confirmed against actual title menu."""
    if 0 <= value <= 2:
        return f"Title menu, option {value + 1}"
    if value == 3:
        return "Title menu, option 4, unverified"
    return None


class Speaker:
    """NVDA Controller DLL if present; otherwise Windows SAPI speech.

    Never claim NVDA was used unless the controller actually accepted speech.
    """
    def __init__(self, base=None):
        self.base = Path(base) if base else folder()
        self.nvda = None
        self.sapi = None
        self.mode = "console"
        self._prepare_nvda()
        if self.nvda is None:
            self._prepare_sapi()

    def _prepare_nvda(self):
        if os.name != "nt":
            return
        for name in ("nvdaControllerClient.dll", "nvdaControllerClient64.dll"):
            path = self.base / name
            if not path.exists():
                continue
            try:
                lib = ctypes.WinDLL(str(path))
                lib.nvdaController_testIfRunning.restype = ctypes.c_ulong
                lib.nvdaController_speakText.argtypes = [ctypes.c_wchar_p]
                lib.nvdaController_speakText.restype = ctypes.c_ulong
                lib.nvdaController_cancelSpeech.restype = ctypes.c_ulong
                if lib.nvdaController_testIfRunning() == 0:
                    self.nvda = lib
                    self.mode = "NVDA"
                    return
            except (OSError, AttributeError):
                continue

    def _prepare_sapi(self):
        if os.name != "nt":
            return
        try:
            import pythoncom
            import win32com.client
            pythoncom.CoInitialize()
            self.sapi = win32com.client.Dispatch("SAPI.SpVoice")
            self.mode = "Windows SAPI"
        except Exception as exc:
            print("Speech unavailable:", repr(exc), flush=True)

    def say(self, words):
        print("SPEAK:", words, flush=True)
        if self.nvda is not None:
            try:
                self.nvda.nvdaController_cancelSpeech()
                if self.nvda.nvdaController_speakText(words) == 0:
                    return
            except (OSError, AttributeError):
                pass
            self.nvda = None
            self._prepare_sapi()
        if self.sapi is not None:
            try:
                # Async + purge previous utterance for responsive navigation.
                self.sapi.Speak(words, 3)
            except Exception as exc:
                print("SAPI speech error:", repr(exc), flush=True)


def parse_value(response):
    if not isinstance(response, dict):
        raise TypeError("Expected memory.read response dictionary")
    data = base64.b64decode(response["base64"], validate=True)
    if len(data) != SIZE:
        raise ValueError("Unexpected PSP memory read length")
    return data[OFFSET]


def record_and_announce(last_value, value, speaker, *, force=False):
    """Speak only known menu indices, and only upon changed selection."""
    words = selection_announcement(value)
    if words and (value != last_value or force):
        speaker.say(words)
        return True
    return False


def quit_pressed():
    if os.name != "nt":
        return False
    try:
        import msvcrt
        while msvcrt.kbhit():
            if msvcrt.getwch().lower() == "q":
                return True
    except (ImportError, OSError):
        pass
    return False


def run(port, speaker, log):
    import websocket
    conn = None
    log.write("TACTICS OGRE TITLE MENU SPEAKER v7\n")
    log.write(f"WATCH 0x{ADDRESS:08X}\n")
    try:
        conn = Connection(port)
        status = conn.request("game.status")
        game = status.get("game") or {}
        game_id = game.get("id", "")
        log.write(f"GAME {game_id} {game.get('title', '')}\n")
        if game_id not in GAME_IDS:
            raise RuntimeError("Please start Tactics Ogre in your normal PPSSPP.")
        initial = parse_value(conn.request("memory.read", address=WINDOW, size=SIZE))
        log.write(f"BASELINE {initial}\n")
        log.flush()
        print(f"Connected to Tactics Ogre. Speech: {speaker.mode}.", flush=True)
        print("Move Up/Down on the title menu. Press Q here to quit.", flush=True)
        speaker.say("Tactics Ogre title menu speech test connected")
        # Initial title display can contain 4; do not call it a menu entry.
        last_value = initial
        recent_activity = time.monotonic()
        while True:
            if quit_pressed():
                log.write("FINISHED user requested stop\n")
                break
            if conn.pending:
                message = conn.pending.popleft()
            else:
                try:
                    message = conn.recv()
                except websocket.WebSocketTimeoutException:
                    if time.monotonic() - recent_activity >= 15:
                        log.write("HEARTBEAT waiting for game navigation\n")
                        log.flush()
                        recent_activity = time.monotonic()
                    continue
            if message.get("event") == "game.quit":
                log.write("GAME_QUIT\n")
                break
            directions = directions_released(message)
            if not directions:
                continue
            time.sleep(0.10)
            started = time.monotonic()
            value = parse_value(conn.request("memory.read", address=WINDOW, size=SIZE))
            elapsed = time.monotonic() - started
            spoken = record_and_announce(last_value, value, speaker)
            log.write(f"MOVE {directions[0]} {last_value}->{value} spoken={int(spoken)} read_ms={elapsed*1000:.1f}\n")
            log.flush()
            last_value = value
            recent_activity = time.monotonic()
        speaker.say("Ogre menu speech test stopped")
        return 0
    except KeyboardInterrupt:
        log.write("FINISHED keyboard interrupt\n")
        return 0
    except Exception as exc:
        log.write(f"ERROR {type(exc).__name__}: {exc}\n")
        print("ERROR:", exc, flush=True)
        speaker.say(f"Tactics Ogre companion error. {exc}")
        return 1
    finally:
        log.flush()
        if conn is not None:
            conn.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=56244)
    args = parser.parse_args()
    speaker = Speaker()
    print("Tactics Ogre speaking companion v7", flush=True)
    print("Speech method:", speaker.mode, flush=True)
    path = folder() / LOG_NAME
    try:
        with path.open("w", encoding="utf-8", buffering=1) as log:
            result = run(args.port, speaker, log)
    except OSError as exc:
        print("Cannot write log:", exc, flush=True)
        result = 2
    print("Log:", path, flush=True)
    if os.name == "nt" and sys.stdin and sys.stdin.isatty():
        try:
            input("Press Enter to close...")
        except EOFError:
            pass
    return result


if __name__ == "__main__":
    raise SystemExit(main())
