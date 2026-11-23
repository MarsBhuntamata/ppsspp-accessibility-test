#!/usr/bin/env python3
"""Tactics Ogre accessible menu explorer for stock PPSSPP (experimental).

The confirmed title cursor reader remains unchanged. This separate companion
observes the Load/Continue and later menus, including confirm/cancel events,
and ranks selection candidates in small RAM windows. It does not claim to
read text or know new menu labels, and never writes PSP memory.
"""
from __future__ import annotations

import argparse
import base64
from collections import Counter, deque
from datetime import datetime
import os
from pathlib import Path
import sys
import time

from to_target_watch import Connection, PORT, GAME_IDS, ADDRESS
from to_speaking_title import Speaker, selection_announcement, read_labels, LABEL_FILE, DEFAULT_LABELS

LOG_NAME = "tactics-ogre-menu-explorer.txt"

# 64 KiB samples, distributed across title-menu and nearby game structures.
# Avoid known graphics-buffer regions around 0x09800000.
WINDOWS = (
    0x09080000, 0x09140000, 0x09240000,
    0x09440000, 0x09640000, 0x09660000,
    0x09A40000, 0x09C40000,
)
WINDOW_SIZE = 0x10000
MAX_CHANGES = 16
MAX_REPORT = 16


def folder():
    return Path(sys.executable if getattr(sys, "frozen", False) else __file__).resolve().parent


def release_events(message):
    if message.get("event") != "input.buttons":
        return ()
    changed = message.get("changed")
    if not isinstance(changed, dict):
        return ()
    return tuple(k for k in ("up", "down", "left", "right",
                             "cross", "circle", "triangle", "square")
                 if changed.get(k) is False)


def classify_action(button):
    if button in ("cross", "circle"):
        return "transition"
    if button in ("up", "down", "left", "right"):
        return "navigate"
    return "other"


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


def read_windows(conn):
    values = {}
    for address in WINDOWS:
        response = conn.request("memory.read", address=address, size=WINDOW_SIZE)
        data = base64.b64decode(response["base64"], validate=True)
        if len(data) != WINDOW_SIZE:
            raise ValueError(f"Short memory block at 0x{address:08X}")
        values[address] = data
    return values


def small_changes(before, after, cap=MAX_CHANGES):
    """Compact low-valued changes sampled fairly across 64 KiB windows."""
    chosen = []
    total = 0
    for start, old in before.items():
        new = after[start]
        if len(old) != len(new):
            raise ValueError("Mismatched samples")
        emitted = 0
        for i, (a, b) in enumerate(zip(old, new)):
            if a != b and a < 16 and b < 16:
                total += 1
                if emitted < cap:
                    chosen.append((start + i, a, b))
                    emitted += 1
    chosen.sort(key=lambda r: (r[0] != ADDRESS, r[0]))
    return total, chosen

def return_candidates(a, b, c, limit_per_window=12):
    """A-B-A low-valued states, stable across a three-position trajectory."""
    candidates = []
    totals = 0
    for start in WINDOWS:
        first, middle, last = a[start], b[start], c[start]
        emitted = 0
        for i, (va, vb, vc) in enumerate(zip(first, middle, last)):
            if va != vb and va == vc and va < 16 and vb < 16:
                totals += 1
                if emitted < limit_per_window:
                    candidates.append((start + i, va, vb))
                    emitted += 1
    return totals, candidates


def ranking(scores, veto, max_rows=MAX_REPORT):
    rows = []
    for addr, row in scores.items():
        penalty = veto[addr]
        weight = 3 * row["returns"] - 5 * penalty
        if weight > 0:
            rows.append((weight, addr, row["returns"], penalty, sorted(row["values"])))
    rows.sort(key=lambda r: (-r[0], -r[2], r[1]))
    return rows[:max_rows]


def add_triplet(scores, veto, triplet, directions):
    count, items = return_candidates(*triplet)
    inverse = (directions[0], directions[1]) in (
        ("down", "up"), ("up", "down"),
        ("left", "right"), ("right", "left"))
    for addr, old, new in items:
        if inverse:
            row = scores.setdefault(addr, {"returns": 0, "values": set()})
            row["returns"] += 1
            row["values"].add((old, new))
        else:
            veto[addr] += 1
    return count, len(items), inverse


def log_ranking(log, scores, veto, phase):
    leaders = ranking(scores, veto)
    log.write(f"RANKING phase={phase} total={len(leaders)}\n")
    for weight, addr, returns, penalty, values in leaders:
        log.write(f"RANK 0x{addr:08X} score={weight} returns={returns} "
                  f"same_direction={penalty} values={values}\n")
    log.flush()


def run(port, log, speaker, labels=None):
    import websocket
    conn = None
    log.write("TACTICS OGRE SPEAKING MENU EXPLORER v9.1\n")
    log.write(f"START {datetime.now().isoformat(timespec='seconds')}\n")
    log.write("WINDOWS " + " ".join(f"0x{x:08X}" for x in WINDOWS) + "\n")
    log.flush()
    try:
        conn = Connection(port)
        status = conn.request("game.status")
        game = status.get("game") or {}
        if game.get("id") not in GAME_IDS:
            raise RuntimeError("Start Tactics Ogre in your regular PPSSPP.")
        log.write(f"GAME {game.get('id')} {game.get('title', '')}\n")
        current = read_windows(conn)
        last_announced = None
        log.write("BASELINE captured\n")
        log.flush()
        speaker.say("Tactics Ogre speaking menu explorer connected.")
        print("Explore the Load screen or another menu using your usual controls.", flush=True)
        print("Cross and Circle are logged as possible screen transitions.", flush=True)
        print("The companion does not know those menus' labels yet.", flush=True)
        print("Press Q in this console to finish. PPSSPP remains running.", flush=True)
        phase = 0
        moves = 0
        history = deque(maxlen=3)
        history.append((current, None))
        scores = {}
        veto = Counter()
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
                    if time.monotonic() - last_heartbeat > 20:
                        log.write("HEARTBEAT connected\n")
                        log.flush()
                        last_heartbeat = time.monotonic()
                    continue
            if msg.get("event") == "game.quit":
                log.write("GAME_QUIT\n")
                break
            events = release_events(msg)
            if not events:
                continue
            button = events[0]
            action = classify_action(button)
            time.sleep(0.10 if action == "navigate" else 0.35)
            start = time.monotonic()
            next_state = read_windows(conn)
            seconds = time.monotonic() - start
            changes, examples = small_changes(current, next_state)
            offset = ADDRESS - 0x09640000
            old_index = current[0x09640000][offset]
            new_index = next_state[0x09640000][offset]
            moves += 1
            log.write(f"EVENT {moves} {button} kind={action} phase={phase} "
                      f"read_seconds={seconds:.3f} low_changes={changes}\n")
            for addr, old, new in examples[:40]:
                log.write(f"DIFF 0x{addr:08X} {old}->{new}\n")

            if action == "transition":
                log_ranking(log, scores, veto, phase)
                phase += 1
                scores, veto = {}, Counter()
                history.clear()
                history.append((next_state, None))
                log.write(f"TRANSITION candidate={button} phase={phase}\n")
                print(f"Possible menu transition: {button}, phase {phase}.", flush=True)
                # No assertion that the game actually opened a new menu.
                speaker.say("Possible menu transition. Further menu labels unverified.")
                last_announced = None
            elif action == "navigate":
                history.append((next_state, button))
                if len(history) == 3:
                    (a, _), (b, first_dir), (c, second_dir) = history
                    count, samples, inverse = add_triplet(
                        scores, veto, (a, b, c), (first_dir, second_dir))
                    log.write(f"TRIPLET inverse={int(inverse)} matches={count} "
                              f"samples={samples}\n")
                if moves % 4 == 0:
                    log_ranking(log, scores, veto, phase)
                delta = new_index - old_index
                expected = 1 if button == "down" else -1 if button == "up" else 0
                if expected and delta == expected and 0 <= new_index <= 15:
                    # Only the title phase gets the known (provisional) names.
                    words = (selection_announcement(new_index, labels) if phase == 0
                             else f"Possible menu option {new_index + 1}, unverified")
                    if words and last_announced != (phase, new_index):
                        speaker.say(words)
                        log.write(f"SPOKEN phase={phase} index={new_index} text={words}\n")
                        last_announced = (phase, new_index)
                print(f"Recorded {moves}: {button} in phase {phase}.", flush=True)
            current = next_state
            log.flush()
            last_heartbeat = time.monotonic()
        log_ranking(log, scores, veto, phase)
        log.write(f"TOTAL_EVENTS {moves} PHASES {phase + 1}\n")
        log.flush()
        speaker.say("Menu exploration saved.")
        return 0
    except KeyboardInterrupt:
        log.write("FINISHED keyboard interrupt\n")
        log.flush()
        return 0
    except Exception as exc:
        log.write(f"ERROR {type(exc).__name__}: {exc}\n")
        log.flush()
        print("Explorer error:", exc, flush=True)
        speaker.say("Menu explorer stopped due to an error.")
        return 1
    finally:
        if conn is not None:
            conn.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=PORT)
    args = parser.parse_args()
    path = folder() / LOG_NAME
    speaker = Speaker()
    print("Tactics Ogre speaking menu explorer v9.1. Speaker:", speaker.mode, flush=True)
    print("Log:", path, flush=True)
    try:
        with path.open("w", encoding="utf-8", buffering=1) as log:
            result = run(args.port, log, speaker, read_labels(folder() / LABEL_FILE) or DEFAULT_LABELS)
    except OSError as exc:
        print("Cannot create explorer log:", exc, flush=True)
        result = 2
    if os.name == "nt" and sys.stdin and sys.stdin.isatty():
        try:
            input("Press Enter to close...")
        except EOFError:
            pass
    return result


if __name__ == "__main__":
    raise SystemExit(main())
