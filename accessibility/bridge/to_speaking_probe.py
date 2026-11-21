#!/usr/bin/env python3
"""Tactics Ogre accessible interim screen-reader bridge for Windows + PPSSPP.

This is an OCR-based fallback, NOT native semantic Tactics Ogre menu support.
Captures PPSSPP's emulated PSP framebuffer through its read-only WebSocket
debugger and recognizes it using Windows' built-in, offline OCR engine.
F8: read current screen; F9: repeat; F10: quit.
No game memory, ISO, save, or emulator setting is written.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import ctypes
from ctypes import wintypes
import json
import queue
import re
import tempfile
import threading
from pathlib import Path

USER32 = ctypes.windll.user32 if hasattr(ctypes, "windll") else None
WM_HOTKEY = 0x0312
HOTKEY_IDS = {1: 0x77, 2: 0x78, 3: 0x79}  # F8, F9, F10


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


class Voice:
    """Windows SAPI speech in a single worker thread (independent of NVDA)."""
    def __init__(self):
        self.messages = queue.Queue()
        self.worker = threading.Thread(target=self._run, daemon=True)
        self.worker.start()

    def say(self, text: str):
        if text:
            self.messages.put(text)

    def _run(self):
        try:
            import win32com.client
            voice = win32com.client.Dispatch("SAPI.SpVoice")
            # Async with purge, so reading the newest selection interrupts older text.
            while True:
                item = self.messages.get()
                if item is None:
                    return
                voice.Speak(item, 3)
        except Exception as exc:
            print("Speech failed:", exc, flush=True)
            while True:
                item = self.messages.get()
                if item is None:
                    return
                print(item, flush=True)

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
            identity = str(game.get("title") or game.get("id") or "unknown game")
            self.voice.say(f"Connected to PPSSPP. {identity}. Press F8 to read the screen, F9 to repeat, F10 to quit.")
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
                        image = client.request("gpu.buffer.screenshot", type="uri")
                        picture.write_bytes(extract_screenshot(image))
                        recognized = asyncio.run(windows_ocr(picture))
                        if recognized:
                            self.latest = recognized
                            self.voice.say(recognized)
                        else:
                            self.voice.say("No text recognized on the current screen.")
                    except Exception as exc:
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
        try:
            for hotkey_id, vk in HOTKEY_IDS.items():
                if not USER32.RegisterHotKey(None, hotkey_id, 0, vk):
                    raise RuntimeError(f"Could not register F{hotkey_id + 7}; another app may use it")
                registered.append(hotkey_id)
            worker = threading.Thread(target=self.run_worker, daemon=True)
            worker.start()
            msg = wintypes.MSG()
            while USER32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == WM_HOTKEY:
                    action = {1: "read", 2: "repeat", 3: "stop"}.get(msg.wParam)
                    if action == "stop":
                        break
                    if action:
                        self.actions.put(action)
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
