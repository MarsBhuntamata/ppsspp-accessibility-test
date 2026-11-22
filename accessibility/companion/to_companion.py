#!/usr/bin/env python3
"""External, read-only Tactics Ogre navigation recorder for stock PPSSPP.

No PPSSPP patch, OCR, game-data rewrite, hotkeys, or manual memory commands.
Requires the user's *existing* PPSSPP debugger on localhost:56244.
The trace is evidence for menu-state research, NOT spoken menu text.
"""
from __future__ import annotations

import argparse
import base64
from collections import deque
from datetime import datetime
import json
import os
from pathlib import Path
import sys
import time

GAME_IDS = {"ULUS10565", "ULES10500", "ULJM05753"}
BASE = 0x08800000
REGION_SIZE = 0x00200000  # 2 MiB, bounded and adjustable later.
CHUNK = 0x10000  # 64 KiB safe debugger reads.
MAX_CAPTURES = 14
MAX_CHANGES_PER_BLOCK = 8
TRACE_NAME = "tactics-ogre-companion-trace.txt"


def output_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def changed_words(before: bytes, after: bytes, address: int = BASE):
    """A bounded, representative subset across 64 KiB blocks of a memory region."""
    if len(before) != len(after) or len(before) % 4:
        raise ValueError("Mismatched or unaligned snapshots")
    changes = []
    total = 0
    for block in range(0, len(before), CHUNK):
        emitted = 0
        for off in range(block, min(block + CHUNK, len(before)), 4):
            a = before[off:off + 4]
            b = after[off:off + 4]
            if a == b:
                continue
            total += 1
            if emitted < MAX_CHANGES_PER_BLOCK:
                changes.append((address + off, int.from_bytes(a, "little"), int.from_bytes(b, "little")))
                emitted += 1
    return total, changes


def released_directions(message: dict):
    if message.get("event") != "input.buttons":
        return ()
    changed = message.get("changed")
    if not isinstance(changed, dict):
        return ()
    return tuple(key for key in ("up", "down", "left", "right") if changed.get(key) is False)


class Connection:
    def __init__(self, port):
        import websocket
        self.websocket = websocket.create_connection(
            f"ws://127.0.0.1:{port}/debugger",
            timeout=10,
            subprotocols=["debugger.ppsspp.org"],
            enable_multithread=False,
        )
        self.websocket.settimeout(1)
        self.ticket = 0
        self.messages = deque()

    def receive(self):
        return json.loads(self.websocket.recv())

    def request(self, event: str, **kwargs):
        self.ticket += 1
        ticket = self.ticket
        self.websocket.send(json.dumps({"event": event, "ticket": ticket, **kwargs}))
        # Record input broadcasts during reads, instead of discarding them.
        deadline = time.monotonic() + 25
        import websocket
        while time.monotonic() < deadline:
            try:
                message = self.receive()
            except (TimeoutError, websocket.WebSocketTimeoutException):
                continue
            if message.get("ticket") == ticket:
                if message.get("event") == "error" or message.get("error"):
                    raise RuntimeError(str(message.get("message") or message.get("error")))
                return message
            if message.get("event") in ("input.buttons", "game.start", "game.quit"):
                if len(self.messages) < 256:
                    self.messages.append(message)
        raise TimeoutError(f"PPSSPP did not respond to {event} within 25 seconds")

    def snapshot(self):
        chunks = []
        for off in range(0, REGION_SIZE, CHUNK):
            response = self.request("memory.read", address=BASE + off, size=CHUNK)
            data = base64.b64decode(response["base64"], validate=True)
            if len(data) != CHUNK:
                raise RuntimeError("PPSSPP returned a shortened memory block")
            chunks.append(data)
        return b"".join(chunks)

    def close(self):
        self.websocket.close()


def run(port: int, log, max_captures=MAX_CAPTURES):
    import websocket
    print("Tactics Ogre companion: read-only memory navigation test.", flush=True)
    print("Use your regular PPSSPP. No game controls will be sent.", flush=True)
    log.write("TACTICS OGRE EXTERNAL COMPANION TRACE v1\n")
    log.write(f"START {datetime.now().isoformat(timespec='seconds')}\n")
    log.flush()
    try:
        conn = Connection(port)
    except Exception as exc:
        log.write(f"CONNECTION_ERROR {type(exc).__name__}: {exc}\n")
        log.flush()
        print("Could not connect to your existing PPSSPP debugger on port", port, flush=True)
        print("Open PPSSPP and enable its existing remote debugger first.", flush=True)
        return 2
    try:
        status = conn.request("game.status")
        game = status.get("game") or {}
        game_id = game.get("id", "")
        log.write(f"GAME {game_id} {game.get('title', '')}\n")
        if game_id not in GAME_IDS:
            print("Tactics Ogre must already be running. Detected:", game_id or "no game", flush=True)
            log.write("ERROR Tactics Ogre not loaded at startup\n")
            return 3
        log.write(f"REGION 0x{BASE:08X} {REGION_SIZE}\n")
        log.flush()
        print("Connected to Tactics Ogre. Use Up/Down in one menu.", flush=True)
        print("Capturing automatically. No extra hotkeys or terminal focus needed.", flush=True)
        print("The companion stops after", max_captures, "directional releases.", flush=True)
        # A baseline is necessary: compare the state before and after movement.
        baseline = conn.snapshot()
        log.write("BASELINE captured\n")
        log.flush()
        captures = 0
        last_report = time.monotonic()
        while captures < max_captures:
            if conn.messages:
                message = conn.messages.popleft()
            else:
                try:
                    message = conn.receive()
                except (websocket.WebSocketTimeoutException, TimeoutError):
                    if time.monotonic() - last_report > 15:
                        log.write("HEARTBEAT connected, awaiting input broadcasts\n")
                        log.flush()
                        print("Connected, awaiting game navigation...", flush=True)
                        last_report = time.monotonic()
                    continue
            if message.get("event") == "game.quit":
                log.write("GAME_QUIT\n")
                break
            directions = released_directions(message)
            if not directions:
                continue
            direction = directions[0]
            # Let gameplay process input; no CPU break or pause request.
            time.sleep(0.12)
            snapshot = conn.snapshot()
            total, changes = changed_words(baseline, snapshot)
            baseline = snapshot
            captures += 1
            log.write(f"ACTION {captures} {direction}\n")
            for address, before, after in changes:
                log.write(f"{address:08X} {before:08X} {after:08X}\n")
            log.write(f"END_ACTION changed={total} logged={len(changes)}\n")
            log.flush()
            print(f"Captured {captures}/{max_captures}: {direction}, {total} changed words.", flush=True)
            last_report = time.monotonic()
        if captures >= max_captures:
            log.write("FINISHED action limit reached\n")
            log.flush()
            print("Capture complete. You can close the companion.", flush=True)
        return 0
    except Exception as exc:
        log.write(f"ERROR {type(exc).__name__}: {exc}\n")
        log.flush()
        print("Capture error:", str(exc), flush=True)
        return 1
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=56244)
    parser.add_argument("--captures", type=int, default=MAX_CAPTURES)
    args = parser.parse_args()
    if not 2 <= args.captures <= MAX_CAPTURES:
        parser.error("--captures must be between 2 and 14")
    path = output_dir() / TRACE_NAME
    print("Trace file:", path, flush=True)
    try:
        with path.open("w", encoding="utf-8", buffering=1) as log:
            result = run(args.port, log, args.captures)
    except OSError as exc:
        print("Cannot write the trace beside this program:", exc, flush=True)
        result = 4
    print("Finished. Trace:", path, flush=True)
    if os.name == "nt" and sys.stdin and sys.stdin.isatty():
        try:
            input("Press Enter to close this window (PPSSPP remains running)...")
        except EOFError:
            pass
    return result


if __name__ == "__main__":
    raise SystemExit(main())
