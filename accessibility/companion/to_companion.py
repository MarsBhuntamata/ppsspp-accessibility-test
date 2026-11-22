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
# The previous 0x08800000..0x08A00000 area remained completely static.
# Scan representative windows throughout 32 MiB of mapped game RAM instead.
REGIONS = (
    (0x08C00000, 0x00200000),
    (0x09000000, 0x00200000),
    (0x09800000, 0x00200000),
    (0x09C00000, 0x00200000),
)
BASE = REGIONS[0][0]  # Legacy default for changed_words unit tests.
REGION_SIZE = REGIONS[0][1]
CHUNK = 0x20000  # 128 KiB debugger reads, 64 KiB comparison blocks.
COMPARE_BLOCK = 0x10000
MAX_CAPTURES = None  # No fixed action cutoff; user stops the recording.
MAX_CHANGES_PER_BLOCK = 8
TRACE_NAME = "tactics-ogre-companion-trace.txt"


def signal(kind: str):
    """Short Windows earcon; console remains readable with NVDA review."""
    if os.name != "nt":
        return
    try:
        import winsound
        notes = {"ready": [(660, 130), (880, 150)],
                 "complete": [(880, 140), (1100, 190)],
                 "error": [(330, 240), (220, 310)]}.get(kind, [])
        for hz, ms in notes:
            winsound.Beep(hz, ms)
    except Exception:
        pass



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
    for block in range(0, len(before), COMPARE_BLOCK):
        emitted = 0
        for off in range(block, min(block + COMPARE_BLOCK, len(before)), 4):
            a = before[off:off + 4]
            b = after[off:off + 4]
            if a == b:
                continue
            total += 1
            if emitted < MAX_CHANGES_PER_BLOCK:
                changes.append((address + off, int.from_bytes(a, "little"), int.from_bytes(b, "little")))
                emitted += 1
    return total, changes


def stable_changed_words(prev_first, prev_second, current_first, current_second,
                         start, limit=24):
    """Selection candidates must be stationary within both observations.

    Two reads of a stationary cursor should agree. Moving graphics, counters
    and animations are discarded even if they changed during navigation.
    """
    if not (len(prev_first) == len(prev_second) ==
            len(current_first) == len(current_second)):
        raise ValueError("Snapshot sizes differ")
    result = []
    stable_total = 0
    for off in range(0, len(prev_first), 4):
        old = prev_second[off:off + 4]
        new = current_second[off:off + 4]
        if (old == new or old != prev_first[off:off + 4] or
                new != current_first[off:off + 4]):
            continue
        stable_total += 1
        before = int.from_bytes(old, "little")
        after = int.from_bytes(new, "little")
        if len(result) < limit * 4:
            result.append((start + off, before, after))
    # Small index-like values first, then keep a sample of other stable words.
    result.sort(key=lambda x: (not (x[1] < 128 and x[2] < 128),
                               not (abs(x[1] - x[2]) <= 4), x[0]))
    return stable_total, result[:limit]


def stop_requested():
    """Q in this console or Ctrl+C. Does not intercept PPSSPP game keys."""
    if os.name != "nt":
        return False
    try:
        import msvcrt
        while msvcrt.kbhit():
            key = msvcrt.getwch()
            if key.lower() == "q":
                return True
    except (OSError, ImportError):
        pass
    return False


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
        regions = []
        for start, size in REGIONS:
            chunks = []
            for off in range(0, size, CHUNK):
                length = min(CHUNK, size - off)
                response = self.request("memory.read", address=start + off, size=length)
                data = base64.b64decode(response["base64"], validate=True)
                if len(data) != length:
                    raise RuntimeError("PPSSPP returned a shortened memory block")
                chunks.append(data)
            regions.append(b"".join(chunks))
        return regions

    def close(self):
        self.websocket.close()


def run(port: int, log, max_captures=MAX_CAPTURES):
    import websocket
    print("Tactics Ogre companion: read-only memory navigation test.", flush=True)
    print("Use your regular PPSSPP. No game controls will be sent.", flush=True)
    log.write("TACTICS OGRE EXTERNAL COMPANION TRACE v3\n")
    log.write(f"START {datetime.now().isoformat(timespec='seconds')}\n")
    log.flush()
    try:
        conn = Connection(port)
    except Exception as exc:
        log.write(f"CONNECTION_ERROR {type(exc).__name__}: {exc}\n")
        log.flush()
        print("Could not connect to your existing PPSSPP debugger on port", port, flush=True)
        print("Open PPSSPP and enable its existing remote debugger first.", flush=True)
        signal("error")
        return 2
    try:
        status = conn.request("game.status")
        game = status.get("game") or {}
        game_id = game.get("id", "")
        log.write(f"GAME {game_id} {game.get('title', '')}\n")
        if game_id not in GAME_IDS:
            print("Tactics Ogre must already be running. Detected:", game_id or "no game", flush=True)
            log.write("ERROR Tactics Ogre not loaded at startup\n")
            signal("error")
            return 3
        for start, size in REGIONS:
            log.write(f"REGION 0x{start:08X} {size}\n")
        log.flush()
        print("Connected to Tactics Ogre. Scanning four separate game-memory regions.", flush=True)
        print("Use alternating Up/Down in one menu, if possible.", flush=True)
        print("Capturing automatically. No extra hotkeys or terminal focus needed.", flush=True)
        print("No action limit. To finish, return to this window and press Q.", flush=True)
        print("Or press Ctrl+C in this window. The current trace is saved after each action.", flush=True)
        signal("ready")
        # A baseline is necessary: compare the state before and after movement.
        baseline_first = conn.snapshot()
        time.sleep(0.30)
        baseline = conn.snapshot()
        log.write("BASELINE stationary pair captured\n")
        log.flush()
        captures = 0
        last_report = time.monotonic()
        while max_captures is None or captures < max_captures:
            if stop_requested():
                log.write("FINISHED user requested stop\n")
                log.flush()
                signal("complete")
                print("Finished. Saved trace.", flush=True)
                break
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
            time.sleep(0.25)
            snapshot_first = conn.snapshot()
            time.sleep(0.30)
            snapshot = conn.snapshot()
            captures += 1
            log.write(f"ACTION {captures} {direction}\n")
            total = 0
            logged = 0
            for (start, size), previous_bytes, current_bytes in zip(REGIONS, baseline, snapshot):
                count, changes = changed_words(previous_bytes, current_bytes, start)
                total += count
                logged += len(changes)
                log.write(f"REGION_CHANGE 0x{start:08X} changed={count}\n")
                for address, before, after in changes:
                    log.write(f"{address:08X} {before:08X} {after:08X}\n")
            stable_total = 0
            stable_logged = 0
            for (start, _), old_first, old_second, new_first, new_second in zip(
                    REGIONS, baseline_first, baseline, snapshot_first, snapshot):
                count, candidates = stable_changed_words(
                    old_first, old_second, new_first, new_second, start)
                stable_total += count
                stable_logged += len(candidates)
                log.write(f"STABLE_REGION 0x{start:08X} changed={count}\n")
                for address, before, after in candidates:
                    log.write(f"CANDIDATE {address:08X} {before:08X} {after:08X}\n")
            baseline_first = snapshot_first
            baseline = snapshot
            log.write(f"END_ACTION changed={total} logged={logged} stable={stable_total} candidates={stable_logged}\n")
            log.flush()
            print(f"Captured {captures}: {direction}; {stable_total} stable changes.", flush=True)
            last_report = time.monotonic()
        if max_captures is not None and captures >= max_captures:
            log.write("FINISHED action limit reached\n")
            log.flush()
            print("Capture complete. You can close the companion.", flush=True)
            signal("complete")
        return 0
    except Exception as exc:
        log.write(f"ERROR {type(exc).__name__}: {exc}\n")
        log.flush()
        print("Capture error:", str(exc), flush=True)
        signal("error")
        return 1
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=56244)
    parser.add_argument("--captures", type=int, default=MAX_CAPTURES,
                        help="Optional automatic stop after N moves; default is no limit")
    args = parser.parse_args()
    if args.captures is not None and args.captures < 2:
        parser.error("--captures must be at least 2")
    path = output_dir() / TRACE_NAME
    print("Trace file:", path, flush=True)
    try:
        with path.open("w", encoding="utf-8", buffering=1) as log:
            try:
                result = run(args.port, log, args.captures)
            except KeyboardInterrupt:
                log.write("FINISHED keyboard interrupt\n")
                log.flush()
                print("Stopped and saved trace.", flush=True)
                result = 0
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
