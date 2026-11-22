#!/usr/bin/env python3
"""Rank candidate Tactics Ogre menu-selection addresses from a native PPSSPP trace.

Offline research utility: user runs only the modified emulator and uploads
its tactics-ogre-navigation-trace.txt. Nothing is injected into the game.
These are *candidates*, not verified selected entries.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path


def parse_trace(text: str):
    actions = []
    active = None
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("ACTION "):
            parts = line.split()
            if len(parts) >= 3:
                active = {"number": int(parts[1]), "direction": parts[2], "changes": {}}
                actions.append(active)
        elif line.startswith("END_ACTION"):
            active = None
        elif active:
            parts = line.split()
            if len(parts) == 3 and all(len(x) == 8 for x in parts):
                try:
                    address, before, after = [int(x, 16) for x in parts]
                except ValueError:
                    continue
                active["changes"][address] = (before, after)
    return actions


def rank_candidates(actions, min_observations=3):
    history = defaultdict(list)
    for action in actions:
        direction = action["direction"]
        if direction not in ("up", "down"):
            continue
        for addr, (before, after) in action["changes"].items():
            for shift in (0, 8, 16, 24):
                x = (before >> shift) & 255
                y = (after >> shift) & 255
                if x == y:
                    continue
                signed_delta = y - x
                history[(addr, shift // 8)].append((direction, signed_delta, x, y, action["number"]))
    ranked = []
    for (addr, byte_index), events in history.items():
        if len(events) < min_observations:
            continue
        dirs = {e[0] for e in events}
        if len(dirs) != 2:
            continue
        # A menu index often moves in opposite directions with Up and Down.
        # Accept either orientation because menus can be reversed.
        direct = sum(1 for direction, diff, *_ in events
                     if (direction == "down" and diff > 0) or
                     (direction == "up" and diff < 0))
        reverse = len(events) - direct
        consistency = max(direct, reverse) / len(events)
        small_moves = sum(1 for _, diff, *_ in events if abs(diff) <= 8)
        small_ratio = small_moves / len(events)
        rank = (consistency, small_ratio, len(events))
        ranked.append((rank, addr + byte_index, events))
    ranked.sort(reverse=True, key=lambda entry: entry[0])
    return ranked


def report(path: Path, limit=30):
    text = path.read_text(encoding="utf-8", errors="replace")
    actions = parse_trace(text)
    print(f"Actions parsed: {len(actions)}")
    print("Directional actions:", " ".join(a["direction"] for a in actions))
    ranked = rank_candidates(actions)
    if not ranked:
        print("No convincing directional candidates found in the sampled region.")
        print("That does NOT prove the menu state is absent: the sampler limits candidates per block.")
        return
    print("Potential per-byte selection candidates (NOT VERIFIED):")
    for (consistency, small_ratio, observations), addr, events in ranked[:limit]:
        transitions = " ".join(
            f"{direction[0]}:{before}>{after}" for direction, _, before, after, _ in events[:12]
        )
        print(f"  0x{addr:08X} matches={observations} "
              f"consistency={consistency:.2f} shortSteps={small_ratio:.2f} {transitions}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path)
    parser.add_argument("--limit", type=int, default=30)
    args = parser.parse_args()
    report(args.trace, args.limit)


if __name__ == "__main__":
    main()
