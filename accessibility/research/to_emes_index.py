#!/usr/bin/env python3
"""Experimental read-only EMES indexer for Tactics Ogre (PSP).

Uses a player's own extracted BIN files. Does not patch ISOs or ship game data.
The printable text is a heuristic, NOT a complete decoding of TO's text format.
"""
import argparse
import hashlib
import json
import re
import struct
from pathlib import Path

SEPARATOR = b"\xff\x81\x01\x01"


def visible_text(raw):
    fragments = []
    for segment in raw.split(SEPARATOR):
        runs = re.findall(rb"[\x20-\x7e]{2,}", segment)
        if runs:
            fragments.append(runs[-1].decode("ascii", "replace"))
    return re.sub(r"\s+", " ", "".join(fragments)).strip()


def read_table(data, start):
    if data[start:start + 4] != b"EMES" or start + 8 > len(data):
        return None
    count = struct.unpack_from("<H", data, start + 4)[0]
    if not 2 <= count <= 4096:
        return None
    table_size = 8 + count * 6
    if start + table_size > len(data):
        return None
    ids = struct.unpack_from(f"<{count}H", data, start + 8)
    offsets = struct.unpack_from(f"<{count}I", data, start + 8 + 2 * count)
    if (offsets[0] < table_size or
        any(a > b for a, b in zip(offsets, offsets[1:])) or
        start + offsets[-1] >= len(data) or
        offsets[-1] - offsets[0] > 4_000_000):
        return None
    records = []
    for i, (message_id, offset) in enumerate(zip(ids, offsets)):
        begin = start + offset
        if i + 1 < count:
            end = start + offsets[i + 1]
        else:
            # Last message extent is unresolved; do not claim a precise length.
            end = min(len(data), begin + 4096)
            sentinel = data[begin:end].find(b"\x00\x00\x00\x00", 4)
            if sentinel >= 0:
                end = begin + sentinel
        raw = data[begin:end]
        records.append({
            "id": message_id, "offset": begin, "byte_length": len(raw),
            "last_extent_provisional": i + 1 == count,
            "text_guess": visible_text(raw),
        })
    return records


def index_file(path):
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    records = []
    pos = 0
    while True:
        pos = data.find(b"EMES", pos)
        if pos < 0:
            break
        entries = read_table(data, pos)
        if entries is not None:
            for entry in entries:
                records.append({
                    "archive": path.name, "sha256": digest,
                    "table_offset": pos, **entry,
                })
        pos += 4
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--output", default="to_messages.jsonl", type=Path)
    args = parser.parse_args()
    all_records = []
    for path in args.files:
        entries = index_file(path)
        all_records.extend(entries)
        print(f"{path.name}: {len(entries)} message records")
    with args.output.open("w", encoding="utf-8") as fp:
        for entry in all_records:
            fp.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(f"Wrote {len(all_records)} records to {args.output}")
    print("WARNING: text extraction is provisional; not a live selected-menu reader.")


if __name__ == "__main__":
    main()
