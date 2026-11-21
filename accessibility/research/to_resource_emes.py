#!/usr/bin/env python3
"""Read-only mapping from PSP FILETABLE resource IDs to EMES message records.

Input: JSON from to_filetable_manifest.py and the player's numbered BIN archives.
Does not bundle or modify game data. Text is only a provisional printable guess.
"""
import argparse
import json
from pathlib import Path

from to_emes_index import read_table


def map_resources(index, base):
    archives = {}
    rows = []
    counts = {}
    for record in index["records"]:
        if record["encrypted"] or record["install"]:
            continue
        name = record["archive"]
        path = base / name
        if not path.is_file():
            continue
        if name not in archives:
            archives[name] = path.read_bytes()
        source = archives[name]
        start, length = record["offset"], record["size"]
        if start < 0 or length < 0 or start + length > len(source):
            raise ValueError(f"{name}: resource {record['file_id']} outside file")
        chunk = source[start:start + length]
        pos = 0
        while True:
            pos = chunk.find(b"EMES", pos)
            if pos < 0:
                break
            entries = read_table(chunk, pos)
            if entries is not None:
                key = (name, record["file_id"])
                counts[key] = counts.get(key, 0) + 1
                for msg in entries:
                    rows.append(dict(
                        archive=name, directory_id=record["directory_id"],
                        resource_id=record["file_id"],
                        table_offset_in_resource=pos,
                        table_offset_in_archive=start + pos,
                        message_id=msg["id"],
                        message_offset_in_archive=start + msg["offset"],
                        provisional_last_extent=msg["last_extent_provisional"],
                        text_guess=msg["text_guess"],
                    ))
            pos += 4
    return rows, counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("archive_folder", type=Path)
    parser.add_argument("--output", type=Path,
                        default=Path("to_resource_messages.jsonl"))
    args = parser.parse_args()
    index = json.loads(args.manifest.read_text(encoding="utf-8"))
    rows, counts = map_resources(index, args.archive_folder)
    with args.output.open("w", encoding="utf-8") as fp:
        for row in rows:
            fp.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"Indexed {len(rows)} message records in {len(counts)} resources")
    for (archive, resource_id), count in sorted(counts.items()):
        print(f"{archive}, resource {resource_id}: {count} EMES table(s)")
    print("Text guesses are provisional; not live menu announcements.")


if __name__ == "__main__":
    main()
