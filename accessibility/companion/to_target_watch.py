#!/usr/bin/env python3
"""Focused, read-only Tactics Ogre title-menu candidate verification.

Uses the unmodified PPSSPP debugger. Reads only 4 KiB surrounding the
candidate from v5, so input observations are not delayed by 8 MiB scans.
Never speaks unverified menu labels or modifies the PSP game.
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

PORT = 56244
GAME_IDS = {"ULUS10565", "ULES10500", "ULJM05753"}
ADDRESS = 0x0964271C
WINDOW = 0x09642000
SIZE = 0x1000
OFFSET = ADDRESS - WINDOW
TRACE_NAME = "tactics-ogre-companion-trace.txt"


def output_dir():
    return Path(sys.executable if getattr(sys, "frozen", False) else __file__).resolve().parent


def sound(kind):
    if os.name != "nt":
        return
    try:
        import winsound
        for freq, dur in {"ready": [(700, 90), (900, 90)],
                          "sample": [(840, 60)],
                          "done": [(950, 100), (1100, 140)],
                          "error": [(350, 200), (240, 200)]}.get(kind, []):
            winsound.Beep(freq, dur)
    except Exception:
        pass


def stop_requested():
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


def directions_released(msg):
    if msg.get("event") != "input.buttons":
        return ()
    changed = msg.get("changed")
    if not isinstance(changed, dict):
        return ()
    return tuple(d for d in ("up", "down") if changed.get(d) is False)


def candidate_value(data):
    if len(data) != SIZE:
        raise ValueError("Short memory sample")
    return data[OFFSET]


def concise_changes(old, new, limit=20):
    """Only small-valued changed bytes in focused window; deterministic."""
    if len(old) != len(new):
        raise ValueError("Incompatible samples")
    rows = []
    for i, (a, b) in enumerate(zip(old, new)):
        if a != b and a <= 15 and b <= 15:
            rows.append((WINDOW + i, a, b))
    rows.sort(key=lambda row: (row[0] != ADDRESS, row[0]))
    return rows[:limit]


class Connection:
    def __init__(self, port):
        import websocket
        self.ws = websocket.create_connection(
            f"ws://127.0.0.1:{port}/debugger",
            timeout=10, subprotocols=["debugger.ppsspp.org"],
            enable_multithread=False)
        self.ws.settimeout(0.5)
        self.ticket = 0
        self.pending = deque()

    def recv(self):
        return json.loads(self.ws.recv())

    def request(self, event, **kwargs):
        import websocket
        self.ticket += 1
        ticket = self.ticket
        self.ws.send(json.dumps({"event": event, "ticket": ticket, **kwargs}))
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            try:
                msg = self.recv()
            except websocket.WebSocketTimeoutException:
                continue
            if msg.get("ticket") == ticket:
                if msg.get("event") == "error" or msg.get("error"):
                    raise RuntimeError(str(msg.get("message") or msg.get("error")))
                return msg
            if msg.get("event") in ("input.buttons", "game.quit"):
                if len(self.pending) < 128:
                    self.pending.append(msg)
        raise TimeoutError(f"Debugger timeout on {event}")

    def sample(self):
        msg = self.request("memory.read", address=WINDOW, size=SIZE)
        data = base64.b64decode(msg["base64"], validate=True)
        if len(data) != SIZE:
            raise RuntimeError("Short memory response")
        return data

    def close(self):
        self.ws.close()


def run(port, log):
    import websocket
    log.write("TACTICS OGRE FOCUSED WATCH v6\n")
    log.write(f"START {datetime.now().isoformat(timespec='seconds')}\n")
    log.write(f"WATCH 0x{ADDRESS:08X} WINDOW 0x{WINDOW:08X} SIZE {SIZE}\n")
    log.flush()
    conn = None
    try:
        conn = Connection(port)
        status = conn.request("game.status")
        game = status.get("game") or {}
        game_id = game.get("id")
        log.write(f"GAME {game_id} {game.get('title', '')}\n")
        log.flush()
        if game_id not in GAME_IDS:
            raise RuntimeError("Load Tactics Ogre in your usual PPSSPP before starting.")
        before = conn.sample()
        initial = candidate_value(before)
        log.write(f"BASELINE candidate={initial}\n")
        log.flush()
        print(f"Connected. Candidate starts at {initial}.", flush=True)
        print("Use Down Up Down Up, then Down Down Up Up on the title screen.", flush=True)
        print("One short beep after each sample. Switch here and press Q to finish.", flush=True)
        sound("ready")
        count = 0
        last_heartbeat = time.monotonic()
        while True:
            if stop_requested():
                log.write("FINISHED user requested stop\n")
                break
            if conn.pending:
                msg = conn.pending.popleft()
            else:
                try:
                    msg = conn.recv()
                except websocket.WebSocketTimeoutException:
                    if time.monotonic() - last_heartbeat > 15:
                        log.write("HEARTBEAT connected\n")
                        log.flush()
                        last_heartbeat = time.monotonic()
                    continue
            if msg.get("event") == "game.quit":
                log.write("GAME_QUIT\n")
                break
            directions = directions_released(msg)
            if not directions:
                continue
            # Capture only a tiny nearby area after release, never pause the game.
            time.sleep(0.15)
            started = time.monotonic()
            current = conn.sample()
            elapsed = time.monotonic() - started
            old_value, new_value = candidate_value(before), candidate_value(current)
            count += 1
            log.write(f"ACTION {count} {directions[0]} candidate={old_value}->{new_value} "
                      f"scan_seconds={elapsed:.3f}\n")
            for address, old, new in concise_changes(before, current):
                log.write(f"BYTE {address:08X} {old} {new}\n")
            log.flush()
            print(f"Action {count}: {directions[0]}, candidate {new_value}, read {elapsed:.2f}s.", flush=True)
            before = current
            sound("sample")
            last_heartbeat = time.monotonic()
        log.write(f"ACTIONS_TOTAL {count}\n")
        log.flush()
        sound("done")
        print("Recording saved.", flush=True)
        return 0
    except KeyboardInterrupt:
        log.write("FINISHED keyboard interrupt\n")
        log.flush()
        return 0
    except Exception as exc:
        log.write(f"ERROR {type(exc).__name__}: {exc}\n")
        log.flush()
        print("Companion error:", exc, flush=True)
        sound("error")
        return 1
    finally:
        if conn:
            conn.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=PORT)
    args = parser.parse_args()
    path = output_dir() / TRACE_NAME
    print("Tactics Ogre focused cursor watch, existing PPSSPP only.", flush=True)
    print("Trace:", path, flush=True)
    try:
        with path.open("w", encoding="utf-8", buffering=1) as log:
            rc = run(args.port, log)
    except OSError as exc:
        print("Cannot create trace beside executable:", exc, flush=True)
        rc = 2
    if os.name == "nt" and sys.stdin and sys.stdin.isatty():
        try:
            input("Press Enter to close this window...")
        except EOFError:
            pass
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
