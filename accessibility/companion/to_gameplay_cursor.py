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


# The only reliable cursors are from the opening menus. Phase numbers are
# NOT screen identifiers, and later screens never get guessed speech.
OPENING_CURSORS = {1: ADDRESS, 2: 0x0964251C}
DIAGNOSTIC_ADDRESSES = (
    0x0964214C, 0x0964859E, 0x09648C88,
    0x0914CB90, 0x0914CBA4, 0x0914CBB8,
)


def opening_announcement(phase, changes):
    """Never announce unknown popup, tarot or gameplay memory as an option."""
    address = OPENING_CURSORS.get(phase)
    if address is None or address not in changes:
        return None
    previous, current = changes[address]
    if not 0 <= current <= 3:
        return None
    # A movement by several slots is valid when key repeat is fast.
    return (address, current, f"Option {current + 1}")


def animation_like(address, before, after):
    """Exclude the recurrent 21/22 pattern seen throughout the v10 trace."""
    return (before, after) in ((21, 22), (22, 21))


def cursor_hypotheses(scores, page_samples):
    """Separate repetitive mirrored graphics data from candidates in the log."""
    candidates = confident_candidates(scores, min_returns=2, max_results=48)
    reliable = []
    rejected = []
    for score, addr in candidates:
        transitions = page_samples.get(addr, set())
        if transitions and all(animation_like(addr, a, b) for a, b in transitions):
            rejected.append((score, addr, "repeated_21_22_pattern"))
        elif transitions and all(a in (0, 1) and b in (0, 1) for a, b in transitions):
            rejected.append((score, addr, "binary_toggle_not_index"))
        else:
            reliable.append((score, addr))
    return reliable, rejected


def report_stage(log, phase, scores, samples, limit=12):
    probable, rejected = cursor_hypotheses(scores, samples)
    log.write(f"STAGE phase={phase} reviewed={len(scores)} "
              f"candidates={len(probable)} filtered={len(rejected)}\n")
    for score, addr in probable[:limit]:
        log.write(f"HYPOTHESIS 0x{addr:08X} returns={score} transitions={sorted(samples.get(addr, ()))[:8]}\n")
    for score, addr, reason in rejected[:6]:
        log.write(f"FILTERED 0x{addr:08X} returns={score} reason={reason}\n")


def run(port, log, speaker, labels):
    import websocket
    conn = None
    log.write("TACTICS OGRE TAROT RESEARCH v11\n")
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
        samples = defaultdict(set)
        phase = 0
        count = 0
        announced = None
        last_record = time.monotonic()
        speaker.say("Ogre tarot research connected.")
        print("Navigate through character creation, then gameplay menus.", flush=True)
        print("Tarot and gameplay are research-only; no guessed option numbers.", flush=True)
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
            log.write("STATE " + " ".join(
                f"0x{addr:08X}={value_at(next_state, addr)}" for addr in DIAGNOSTIC_ADDRESSES) + "\n")
            if action == "navigate":
                for addr, pair in changes.items():
                    samples[addr].add(pair)
            if action == "transition":
                report_stage(log, phase, scores, samples)
                phase += 1
                scores.clear()
                samples.clear()
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
                    report_stage(log, phase, scores, samples)
                # Only the two known opening cursors speak. Tarot and gameplay
                # candidates remain silent research data until independently
                # validated. No more popup = "Option 2" false positives.
                spoken = opening_announcement(phase, changes)
                if spoken is not None:
                    addr, value, words = spoken
                    signature = (phase, addr, value)
                    if signature != announced:
                        speaker.say(words)
                        announced = signature
                        log.write(f"SPOKEN {words} verified_opening_cursor=0x{addr:08X}\n")
                else:
                    log.write("SILENT_UNKNOWN_SCREEN no cursor verified\n")
            state = next_state
            last_record = time.monotonic()
            log.flush()
        report_stage(log, phase, scores, samples)
        log.write(f"EVENTS {count} PHASES {phase + 1}\n")
        speaker.say("Tarot research log saved.")
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
    print("Tactics Ogre tarot research v11.", flush=True)
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
