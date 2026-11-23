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
LABEL_FILE = "tactics-ogre-title-labels.txt"
DEFAULT_LABELS = {0: "New Game", 1: "Load Game", 2: "Continue"}


def folder():
    return Path(sys.executable if getattr(sys, "frozen", False) else __file__).resolve().parent


def read_labels(path):
    """Load user-editable labels. Named entries remain provisional."""
    labels = {}
    try:
        lines = Path(path).read_text(encoding="utf-8-sig").splitlines()
    except FileNotFoundError:
        return {}
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, label = line.split("=", 1)
        if key.strip() in ("0", "1", "2", "3") and label.strip():
            labels[int(key.strip())] = label.strip()[:100]
    return labels


def selection_announcement(value, labels=None):
    """Unverified entries retain their numeric label unless configured."""
    if not 0 <= value <= 3:
        return None
    names = labels or {}
    return names.get(value, f"Title menu, option {value + 1}")


def menu_transition(last_value, value, direction):
    """Detect suspicious non-boundary backwards moves without guessing a label."""
    if last_value not in (0, 1, 2) or value not in (0, 1, 2):
        return False
    return (direction == "up" and last_value == 1 and value == 2 or
            direction == "down" and last_value == 1 and value == 0)


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


def record_and_announce(last_value, value, speaker, *, labels=None, force=False):
    """Speak only known menu indices, and only upon changed selection."""
    words = selection_announcement(value, labels)
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


def run(port, speaker, log, labels=None):
    import websocket
    conn = None
    log.write("TACTICS OGRE TITLE MENU SPEAKER v8.1\n")
    log.write(f"WATCH 0x{ADDRESS:08X}\n")
    log.write(f"LABELS {labels or {}}\n")
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
        speaker.say("Tactics Ogre title speech connected. Names are provisional.")
        # Initial title display can contain 4; do not call it a menu entry.
        last_value = initial
        recent_activity = time.monotonic()
        reconnects = 0
        while True:
            if quit_pressed():
                log.write("FINISHED user requested stop\n")
                break
            if conn.pending:
                message = conn.pending.popleft()
            else:
                try:
                    message = conn.recv()
                except (websocket.WebSocketConnectionClosedException,
                        ConnectionResetError, BrokenPipeError, OSError,
                        RuntimeError) as exc:
                    log.write(f"DEBUGGER_DISCONNECTED {type(exc).__name__}: {exc}\n")
                    log.flush()
                    if reconnects >= 3:
                        log.write("ERROR PPSSPP debugger connection lost after retries\n")
                        break
                    reconnects += 1
                    try:
                        conn.close()
                    except Exception:
                        pass
                    time.sleep(0.5)
                    try:
                        conn = Connection(port)
                        reconnect_status = conn.request("game.status")
                        reconnect_id = (reconnect_status.get("game") or {}).get("id", "")
                        if reconnect_id not in GAME_IDS:
                            raise RuntimeError("Tactics Ogre no longer loaded")
                        last_value = parse_value(
                            conn.request("memory.read", address=WINDOW, size=SIZE))
                        log.write(f"RECONNECTED {reconnects} selection={last_value}\n")
                        log.flush()
                        recent_activity = time.monotonic()
                        continue
                    except Exception as reconnect_exc:
                        log.write(f"RECONNECT_FAILED {type(reconnect_exc).__name__}: {reconnect_exc}\n")
                        log.flush()
                        break
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
            try:
                value = parse_value(conn.request("memory.read", address=WINDOW, size=SIZE))
            except (websocket.WebSocketConnectionClosedException,
                    ConnectionResetError, BrokenPipeError, OSError,
                    RuntimeError) as exc:
                log.write(f"MEMORY_READ_CONNECTION_LOST {type(exc).__name__}: {exc}\n")
                log.flush()
                try:
                    conn.close()
                except Exception:
                    pass
                try:
                    conn = Connection(port)
                    reconnect_status = conn.request("game.status")
                    if (reconnect_status.get("game") or {}).get("id", "") not in GAME_IDS:
                        raise RuntimeError("Tactics Ogre no longer loaded")
                    last_value = parse_value(
                        conn.request("memory.read", address=WINDOW, size=SIZE))
                    log.write(f"RECONNECTED after memory read selection={last_value}\n")
                    log.flush()
                    continue
                except Exception as reconnect_exc:
                    log.write(f"RECONNECT_FAILED {type(reconnect_exc).__name__}: {reconnect_exc}\n")
                    log.flush()
                    break
            elapsed = time.monotonic() - started
            suspicious = menu_transition(last_value, value, directions[0])
            # Log suspicious transitions; do not assert that the resulting
            # menu label matches the actual screen in these cases.
            spoken = record_and_announce(last_value, value, speaker, labels=labels)
            if suspicious:
                log.write("NOTICE direction and selection index disagree\n")
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
    print("Tactics Ogre speaking companion v8.1", flush=True)
    print("Speech method:", speaker.mode, flush=True)
    label_path = folder() / LABEL_FILE
    labels = read_labels(label_path)
    if not label_path.exists():
        label_path.write_text("# PROVISIONAL names inferred from the PSP game manual.\n# Change these if the title-menu order differs.\n0=New Game\n1=Load Game\n2=Continue\n", encoding="utf-8")
        labels = read_labels(label_path)
    print("Title menu labels (not yet verified):", labels, flush=True)
    path = folder() / LOG_NAME
    try:
        with path.open("w", encoding="utf-8", buffering=1) as log:
            result = run(args.port, speaker, log, labels)
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
