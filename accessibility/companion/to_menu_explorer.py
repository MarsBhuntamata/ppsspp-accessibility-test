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

from to_target_watch import Connection, PORT, GAME_IDS, ADDRESS, WINDOW as FAST_WINDOW, SIZE as FAST_SIZE
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


FAST_CURSORS = (ADDRESS, 0x0964251C)  # second is a candidate from v9.1, not confirmed
FAST_OFFSETS = {addr: addr - FAST_WINDOW for addr in FAST_CURSORS}
IDLE_SCOUT_DELAY = 1.2


def read_fast(conn):
    """One 4 KiB request rather than eight 64 KiB requests per key."""
    response = conn.request("memory.read", address=FAST_WINDOW, size=FAST_SIZE)
    data = base64.b64decode(response["base64"], validate=True)
    if len(data) != FAST_SIZE:
        raise ValueError("Short fast memory response")
    return {addr: data[offset] for addr, offset in FAST_OFFSETS.items()}


def select_cursor(old, new, phase):
    """Prefer known title cursor, then the observed adjacent-screen candidate."""
    order = (ADDRESS, 0x0964251C) if phase <= 1 else (0x0964251C, ADDRESS)
    for addr in order:
        if old[addr] != new[addr] and 0 <= new[addr] <= 15:
            return addr, new[addr]
    return None, None


def speech_label(phase, addr, value, labels):
    """Never invent an item's name for an unverified screen."""
    # Index 0x0964271C has only been tied to the title menu, and
    # phase counters alone cannot prove which screen is currently shown.
    return f"Option {value + 1}"


def run(port, log, speaker, labels=None):
    import websocket
    conn = None
    log.write("TACTICS OGRE FAST SPEAKING EXPLORER v9.2\n")
    log.write(f"START {datetime.now().isoformat(timespec='seconds')}\n")
    log.write(f"FAST_WINDOW 0x{FAST_WINDOW:08X} size={FAST_SIZE}\n")
    log.write("CANDIDATES " + " ".join(f"0x{a:08X}" for a in FAST_CURSORS) + "\n")
    log.write("All other menu labels are unknown. Spoken numbers are hypotheses.\n")
    log.flush()
    try:
        conn = Connection(port)
        status = conn.request("game.status")
        game = status.get("game") or {}
        if game.get("id") not in GAME_IDS:
            raise RuntimeError("Start Tactics Ogre in your regular PPSSPP.")
        log.write(f"GAME {game.get('id')} {game.get('title', '')}\n")
        current = read_fast(conn)
        log.write(f"BASELINE fast={current}\n")
        speaker.say("Tactics Ogre fast menu explorer connected.")
        print("Speak short option numbers while scanning possible menus.", flush=True)
        print("Press Q in this console to finish. PPSSPP remains running.", flush=True)
        phase, moves = 0, 0
        last_spoken = None
        last_event = time.monotonic()
        last_scout = time.monotonic()
        last_heartbeat = time.monotonic()
        scout_state = None
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
                    now = time.monotonic()
                    if now - last_event > IDLE_SCOUT_DELAY and now - last_scout > 5:
                        # Only on idle time: expensive scouting never delays
                        # the normal per-key speaking path.
                        try:
                            next_scout = read_windows(conn)
                            if scout_state is not None:
                                changes, samples = small_changes(scout_state, next_scout)
                                log.write(f"IDLE_SCOUT phase={phase} low_changes={changes}\n")
                                for addr, old, new in samples[:16]:
                                    log.write(f"IDLE_DIFF 0x{addr:08X} {old}->{new}\n")
                            else:
                                log.write(f"IDLE_SCOUT baseline phase={phase}\n")
                            scout_state = next_scout
                            last_scout = time.monotonic()
                            log.flush()
                        except Exception as e:
                            log.write(f"SCOUT_ERROR {type(e).__name__} {e}\n")
                    if now - last_heartbeat > 20:
                        log.write("HEARTBEAT connected\n")
                        log.flush()
                        last_heartbeat = now
                    continue
            if msg.get("event") == "game.quit":
                log.write("GAME_QUIT\n")
                break
            buttons = release_events(msg)
            if not buttons:
                continue
            button = buttons[0]
            kind = classify_action(button)
            moves += 1
            last_event = time.monotonic()
            started = time.monotonic()
            # No artificial 100ms/350ms delay. PPSSPP already processed
            # the release event; the memory request observes its current state.
            next_state = read_fast(conn)
            elapsed = (time.monotonic() - started) * 1000
            address, value = select_cursor(current, next_state, phase)
            if kind == "transition":
                phase += 1
                last_spoken = None
                log.write(f"EVENT {moves} {button} transition phase={phase} read_ms={elapsed:.1f} fast={next_state}\n")
                # Do not interrupt the player with 'unverified' on every confirmation.
            elif kind == "navigate":
                log.write(f"EVENT {moves} {button} navigate phase={phase} read_ms={elapsed:.1f} fast={next_state}\n")
                if address is not None:
                    announcement = speech_label(phase, address, value, labels)
                    if (address, value, phase) != last_spoken:
                        speaker.say(announcement)
                        last_spoken = (address, value, phase)
                        log.write(f"SPOKEN addr=0x{address:08X} index={value} text={announcement}\n")
                else:
                    log.write("NO_CURSOR_CHANGE\n")
            current = next_state
            log.flush()
            last_heartbeat = time.monotonic()
        log.write(f"TOTAL_EVENTS {moves} PHASES {phase + 1}\n")
        speaker.say("Menu exploration saved.")
        return 0
    except KeyboardInterrupt:
        log.write("FINISHED keyboard interrupt\n")
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
    print("Tactics Ogre fast speaking menu explorer v9.2. Speaker:", speaker.mode, flush=True)
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
