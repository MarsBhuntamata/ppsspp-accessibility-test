#!/usr/bin/env python3
"""Tactics Ogre gameplay/character-generation cursor discovery, stock PPSSPP.

Keeps known title/options speech, but for unfamiliar screens observes several
small memory windows on EVERY navigation release to discover new cursor state.
Only announces an unknown cursor after repeatable opposite-direction returns.
No OCR, PSP memory modification, game input injection, or false text labels.
"""
from __future__ import annotations

import argparse
import base64
from collections import defaultdict, deque
from datetime import datetime
import os
from pathlib import Path
import sys
import time

from to_target_watch import Connection, PORT, GAME_IDS, ADDRESS
from to_speaking_title import Speaker, read_labels, LABEL_FILE, DEFAULT_LABELS
from to_menu_explorer import classify_action, release_events, stop_requested

LOG_NAME = "tactics-ogre-gameplay-cursors.txt"
# Selected from v9/v9.1 logs: dynamic UI structures, not the enormous RAM scan.
WATCH_PAGES = (
    0x0908A000, 0x0914C000, 0x09642000, 0x09645000,
    0x09648000, 0x09660000, 0x09664000,
)
PAGE_BYTES = 4096
KNOWN = {ADDRESS: "title", 0x0964251C: "secondary"}
MAX_CANDIDATE = 31
MAX_DIFFS_PER_PAGE = 10


def folder():
    return Path(sys.executable if getattr(sys, "frozen", False) else __file__).resolve().parent


def read_pages(conn):
    pages = {}
    for addr in WATCH_PAGES:
        message = conn.request("memory.read", address=addr, size=PAGE_BYTES)
        data = base64.b64decode(message["base64"], validate=True)
        if len(data) != PAGE_BYTES:
            raise ValueError(f"Unexpected memory block size at 0x{addr:08X}")
        pages[addr] = data
    return pages


def value_at(snapshot, address):
    base = address & ~(PAGE_BYTES - 1)
    data = snapshot.get(base)
    return data[address - base] if data is not None else None


def find_changes(before, after):
    """Return all plausible small integer changes for scoring; trim only logs."""
    changes = {}
    by_page = defaultdict(list)
    for base in WATCH_PAGES:
        old, new = before[base], after[base]
        for i, (a, b) in enumerate(zip(old, new)):
            if a != b and a <= MAX_CANDIDATE and b <= MAX_CANDIDATE:
                address = base + i
                changes[address] = (a, b)
                if len(by_page[base]) < MAX_DIFFS_PER_PAGE:
                    by_page[base].append((address, a, b))
    return changes, by_page


def inverse_pair(first, second):
    return (first, second) in {
        ("up", "down"), ("down", "up"),
        ("left", "right"), ("right", "left"),
    }


def inverse_returns(earlier, middle, current, first_direction, second_direction):
    """Find A->B->A bytes on an opposite-direction navigation pair."""
    if not inverse_pair(first_direction, second_direction):
        return ()
    changed_ab, _ = find_changes(earlier, middle)
    result = []
    for address, (a, b) in changed_ab.items():
        c = value_at(current, address)
        if c == a:
            result.append((address, a, b))
    return tuple(result)


def confident_candidates(scores, min_returns=2, max_results=8):
    """Avoid claiming an arbitrary single-frame animation byte is a cursor."""
    viable = [(score, addr) for addr, score in scores.items()
              if score >= min_returns]
    viable.sort(key=lambda item: (-item[0], item[1]))
    return viable[:max_results]


def report_candidates(log, scores, phase, limit=12):
    log.write(f"CANDIDATES phase={phase} eligible={len(confident_candidates(scores))}\n")
    for score, address in confident_candidates(scores, max_results=limit):
        log.write(f"CURSOR? 0x{address:08X} returns={score}\n")


def run(port, log, speaker, labels):
    import websocket
    conn = None
    log.write("TACTICS OGRE GAMEPLAY CURSOR DISCOVERY v10\n")
    log.write(f"START {datetime.now().isoformat(timespec='seconds')}\n")
    log.write("PAGES " + " ".join(f"0x{a:08X}" for a in WATCH_PAGES) + "\n")
    log.write("UNVERIFIED other-menu addresses and labels; cursor rankings are hypotheses.\n")
    try:
        conn = Connection(port)
        game = (conn.request("game.status").get("game") or {})
        if game.get("id") not in GAME_IDS:
            raise RuntimeError("Start Tactics Ogre in your regular PPSSPP.")
        log.write(f"GAME {game.get('id')} {game.get('title', '')}\n")
        state = read_pages(conn)
        history = deque(maxlen=3)
        history.append((state, None))
        scores = defaultdict(int)
        phase = 0
        count = 0
        announced = None
        last_record = time.monotonic()
        speaker.say("Ogre gameplay cursor discovery connected.")
        print("Navigate through character creation, then gameplay menus.", flush=True)
        print("Revisit options with Down and Up, or Right and Left.", flush=True)
        print("Press Q in this window when finished; upload the gameplay cursor log.", flush=True)
        while True:
            if stop_requested():
                log.write("FINISHED user requested stop\n")
                break
            if conn.pending:
                message = conn.pending.popleft()
            else:
                try:
                    message = conn.recv()
                except websocket.WebSocketTimeoutException:
                    if time.monotonic() - last_record > 20:
                        log.write(f"HEARTBEAT phase={phase}\n")
                        last_record = time.monotonic()
                    continue
            if message.get("event") == "game.quit":
                log.write("GAME_QUIT\n")
                break
            released = release_events(message)
            if not released:
                continue
            button = released[0]
            action = classify_action(button)
            start = time.monotonic()
            next_state = read_pages(conn)
            read_ms = (time.monotonic() - start) * 1000
            count += 1
            changes, examples = find_changes(state, next_state)
            log.write(f"EVENT {count} {button} action={action} phase={phase} "
                      f"read_ms={read_ms:.1f} plausible_changes={len(changes)}\n")
            for base in WATCH_PAGES:
                for addr, a, b in examples[base]:
                    log.write(f"DIFF 0x{addr:08X} {a}->{b}\n")
            if action == "transition":
                report_candidates(log, scores, phase)
                phase += 1
                scores.clear()
                history.clear()
                history.append((next_state, None))
                announced = None
                log.write(f"PHASE_SWITCH {phase} by={button} (not a verified screen ID)\n")
            elif action == "navigate":
                history.append((next_state, button))
                if len(history) == 3:
                    (a, _), (b, first), (c, second) = history
                    returns = inverse_returns(a, b, c, first, second)
                    for addr, _, _ in returns:
                        scores[addr] += 1
                    log.write(f"INVERSE_RETURNS {len(returns)} "
                              f"best={[(hex(addr), scores[addr]) for addr, _, _ in returns[:8]]}\n")
                if count % 6 == 0:
                    report_candidates(log, scores, phase)
                # Preserve the known opening-menu readout. For new screens,
                # only numeric speech after a candidate passes two returns.
                candidates = confident_candidates(scores)
                preferred = None
                for addr in (ADDRESS, 0x0964251C):
                    if addr in changes and value_at(next_state, addr) <= 3:
                        preferred = addr
                        break
                if preferred is None and candidates:
                    preferred = candidates[0][1]
                if preferred is not None and preferred in changes:
                    value = value_at(next_state, preferred)
                    if value <= MAX_CANDIDATE:
                        words = f"Option {value + 1}"
                        signature = (phase, preferred, value)
                        if signature != announced:
                            speaker.say(words)
                            announced = signature
                            log.write(f"SPOKEN {words} candidate=0x{preferred:08X}\n")
                elif changes:
                    log.write("DISCOVERING unknown menu selection\n")
            state = next_state
            last_record = time.monotonic()
            log.flush()
        report_candidates(log, scores, phase)
        log.write(f"EVENTS {count} PHASES {phase + 1}\n")
        speaker.say("Gameplay cursor discovery saved.")
        return 0
    except KeyboardInterrupt:
        log.write("FINISHED keyboard interrupt\n")
        return 0
    except Exception as exc:
        log.write(f"ERROR {type(exc).__name__}: {exc}\n")
        print("Explorer error:", exc, flush=True)
        speaker.say("Gameplay cursor explorer stopped.")
        return 1
    finally:
        log.flush()
        if conn is not None:
            conn.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=PORT)
    args = parser.parse_args()
    path = folder() / LOG_NAME
    speaker = Speaker()
    print("Tactics Ogre gameplay cursor discovery v10.", flush=True)
    print("Log:", path, flush=True)
    try:
        with path.open("w", encoding="utf-8", buffering=1) as log:
            code = run(args.port, log, speaker,
                       read_labels(folder() / LABEL_FILE) or DEFAULT_LABELS)
    except OSError as exc:
        print("Cannot write explorer log:", exc, flush=True)
        code = 2
    if os.name == "nt" and sys.stdin and sys.stdin.isatty():
        try:
            input("Press Enter to close...")
        except EOFError:
            pass
    return code


if __name__ == "__main__":
    raise SystemExit(main())
