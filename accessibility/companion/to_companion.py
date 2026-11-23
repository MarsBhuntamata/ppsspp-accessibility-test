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


def analyze_triplet(a, b, c, *, base=BASE, limit_per_block=8):
    """Find low-valued bytes stable at A, B, A with return to original."""
    if len({len(x) for pair in (a, b, c) for x in pair}) != 1:
        raise ValueError("Snapshot sizes differ")
    count = 0
    rows = []
    block_counts = {}
    for offset in range(len(a[0])):
        av, bv, cv = a[1][offset], b[1][offset], c[1][offset]
        if (av == bv or av != cv or av >= 16 or bv >= 16 or
                av != a[0][offset] or bv != b[0][offset] or
                cv != c[0][offset]):
            continue
        count += 1
        block = offset // COMPARE_BLOCK
        if block_counts.get(block, 0) < limit_per_block:
            rows.append((base + offset, av, bv))
            block_counts[block] = block_counts.get(block, 0) + 1
    return count, rows


def classify_triplet(first, middle, last, directions, regions=REGIONS):
    matches = []
    total = 0
    for (start, _), a, b, c in zip(regions, first, middle, last):
        count, items = analyze_triplet(a, b, c, base=start)
        total += count
        matches.extend(items)
    reverse = (directions[0] in ("up", "down") and
               directions[1] in ("up", "down") and
               directions[0] != directions[1])
    return reverse, total, matches


def summarize_candidates(scores, veto, limit=20):
    ranked = []
    for addr, row in scores.items():
        penalty = veto.get(addr, 0)
        score = row["returns"] * 3 - penalty * 5
        if score > 0:
            ranked.append((score, row["returns"], penalty, addr, sorted(row["pairs"])))
    ranked.sort(key=lambda item: (-item[0], -item[1], item[3]))
    return ranked[:limit]


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
    log.write("TACTICS OGRE EXTERNAL COMPANION TRACE v4\n")
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
        print("Connected to Tactics Ogre. Checking return-to-position patterns.", flush=True)
        print("On title menu, try Down Up Down Up, then Down Down Up Up.", flush=True)
        print("Capturing automatically. No extra hotkeys or terminal focus needed.", flush=True)
        print("No action limit. To finish, return to this window and press Q.", flush=True)
        print("Or press Ctrl+C in this window. The current trace is saved after each action.", flush=True)
        signal("ready")
        # A baseline is necessary: compare the state before and after movement.
        baseline_first = conn.snapshot()
        time.sleep(0.30)
        baseline = conn.snapshot()
        history = [((baseline_first, baseline), None)]
        scores = {}
        veto = {}
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
            history.append(((snapshot_first, snapshot), direction))
            if len(history) > 3:
                history.pop(0)
            if len(history) == 3:
                (aa, _), (bb, d1), (cc, d2) = history
                a_reg = list(zip(aa[0], aa[1]))
                b_reg = list(zip(bb[0], bb[1]))
                c_reg = list(zip(cc[0], cc[1]))
                reverse, matched, rows = classify_triplet(
                    a_reg, b_reg, c_reg, (d1, d2))
                kind = "RETURN" if reverse else "SAME_DIRECTION"
                log.write(f"TRIPLET {kind} matched_low_bytes={matched} samples={len(rows)}\n")
                for address, av, bv in rows:
                    if reverse:
                        item = scores.setdefault(address, {"returns": 0, "pairs": set()})
                        item["returns"] += 1
                        item["pairs"].add((av, bv))
                    else:
                        veto[address] = veto.get(address, 0) + 1
            log.write(f"ACTION_END {captures} {direction}\n")
            if captures % 4 == 0:
                leaders = summarize_candidates(scores, veto, 8)
                log.write(f"RANKING after={captures} count={len(leaders)}\n")
                for rank, returns, penalty, addr, pairs in leaders:
                    log.write(f"RANK {addr:08X} score={rank} returns={returns} alternation={penalty} values={pairs}\n")
            log.flush()
            print(f"Recorded {captures}: {direction}. Return patterns: {len(scores)}.", flush=True)
            last_report = time.monotonic()
        leaders = summarize_candidates(scores, veto)
        log.write(f"FINAL_CANDIDATES {len(leaders)}\n")
        for rank, returns, penalty, addr, pairs in leaders:
            log.write(f"RANK {addr:08X} score={rank} returns={returns} alternation={penalty} values={pairs}\n")
        log.flush()
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
