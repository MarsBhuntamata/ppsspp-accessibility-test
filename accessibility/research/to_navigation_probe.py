#!/usr/bin/env python3
"""Experimental navigation-state recorder for standalone PPSSPP.

Read-only. Listens to the emulator's own input.buttons broadcasts and records
a small PSP RAM sample after D-pad navigation. No OCR, screenshots, pauses,
input injection, game-file modifications, or timing prompts. Results are
evidence for identifying a genuine menu state value, NOT speech output.

Do not run alongside another active debugger capture on the same port.
"""
from __future__ import annotations

import argparse
import base64
from collections import Counter
import json
from pathlib import Path
import queue
import threading
import time


NAV_KEYS = frozenset(("up", "down", "left", "right"))
DIRECTIONAL_LIMIT = 256
DEFAULT_ADDRESS = 0x08800000
DEFAULT_SIZE = 0x00200000
MAX_TOTAL = 0x02000000
CHUNK = 0x10000


def changed_offsets(a: bytes, b: bytes, *, limit: int = DIRECTIONAL_LIMIT):
    """Yield bounded byte changes for diagnostics, not exhaustive indexing."""
    if len(a) != len(b):
        raise ValueError("Snapshots must cover identical memory ranges")
    count = 0
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y:
            yield i, x, y
            count += 1
            if count >= limit:
                return


def navigation_releases(message: dict):
    """Identify D-pad release events without confusing presses with releases."""
    if message.get("event") != "input.buttons":
        return ()
    changed = message.get("changed") or {}
    return tuple(key for key in ("up", "down", "left", "right")
                 if key in changed and changed[key] is False)


class Debugger:
    def __init__(self, port):
        import websocket
        self.socket = websocket.create_connection(
            f"ws://127.0.0.1:{port}/debugger",
            subprotocols=["debugger.ppsspp.org"],
            timeout=10,
        )
        self.socket.settimeout(0.1)
        self.ticket = 0
        self.broadcasts = queue.Queue()
        self.responses = {}
        self.lock = threading.Lock()
        self.closed = threading.Event()
        self.receiver = threading.Thread(target=self._recv_loop, daemon=True)
        self.receiver.start()

    def _recv_loop(self):
        import websocket
        while not self.closed.is_set():
            try:
                message = json.loads(self.socket.recv())
            except websocket.WebSocketTimeoutException:
                continue
            except Exception as exc:
                self.broadcasts.put({"event": "_disconnected", "error": repr(exc)})
                return
            ticket = message.get("ticket")
            if isinstance(ticket, int) and ticket in self.responses:
                self.responses[ticket].put(message)
            else:
                self.broadcasts.put(message)

    def request(self, event, **kwargs):
        with self.lock:
            self.ticket += 1
            ticket = self.ticket
            response = queue.Queue(maxsize=1)
            self.responses[ticket] = response
            try:
                self.socket.send(json.dumps({
                    "event": event, "ticket": ticket, **kwargs,
                }))
                result = response.get(timeout=15)
                if result.get("event") == "error":
                    raise RuntimeError(result.get("message") or "Debugger error")
                return result
            finally:
                self.responses.pop(ticket, None)

    def snapshot(self, address, size):
        parts = []
        for offset in range(0, size, CHUNK):
            length = min(CHUNK, size - offset)
            reply = self.request("memory.read", address=address + offset, size=length)
            data = base64.b64decode(reply["base64"], validate=True)
            if len(data) != length:
                raise RuntimeError("Short memory response")
            parts.append(data)
        return b"".join(parts)

    def close(self):
        self.closed.set()
        self.socket.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=56244)
    parser.add_argument("--address", type=lambda s: int(s, 0), default=DEFAULT_ADDRESS)
    parser.add_argument("--size", type=lambda s: int(s, 0), default=DEFAULT_SIZE)
    parser.add_argument("--output", type=Path, default=Path("navigation_trace.jsonl"))
    parser.add_argument("--max-captures", type=int, default=12)
    args = parser.parse_args()
    if not 1 <= args.size <= MAX_TOTAL or args.address % 4:
        parser.error("size must be 1..32 MiB and address aligned to four bytes")
    if args.max_captures < 2:
        parser.error("--max-captures must be at least 2")

    client = Debugger(args.port)
    print("PPSSPP navigation probe connected. No game input will be injected.")
    print("It observes directional button releases while you play normally.")
    print("Press Ctrl+C to stop; no timing or extra keys are required.")
    previous = None
    capture_count = 0
    try:
        identity = client.request("game.status")
        print("Game:", identity.get("title"), identity.get("id"))
        with args.output.open("w", encoding="utf-8") as output:
            while capture_count < args.max_captures:
                message = client.broadcasts.get()
                if message.get("event") == "_disconnected":
                    raise RuntimeError(message.get("error"))
                directions = navigation_releases(message)
                if not directions:
                    continue
                # Give the game several frames to process the new selection.
                # The actual memory capture is performed safely by PPSSPP.
                time.sleep(0.12)
                snapshot = client.snapshot(args.address, args.size)
                changes = []
                if previous is not None:
                    changes = [
                        {"address": hex(args.address + off), "before": old, "after": new}
                        for off, old, new in changed_offsets(previous, snapshot)
                    ]
                record = {
                    "capture": capture_count + 1,
                    "button_releases": list(directions),
                    "address": hex(args.address),
                    "size": args.size,
                    "first_changes_only": len(changes) == DIRECTIONAL_LIMIT,
                    "changes": changes,
                }
                output.write(json.dumps(record) + "\n")
                output.flush()
                print(f"Capture {capture_count + 1}: {','.join(directions)}, {len(changes)} initial byte changes")
                previous = snapshot
                capture_count += 1
    finally:
        client.close()
        print("Stopped. Keep any trace local; it contains game-state addresses.")
    print("Trace:", args.output)


if __name__ == "__main__":
    main()
