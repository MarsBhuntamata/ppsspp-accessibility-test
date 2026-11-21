#!/usr/bin/env python3
"""Read-only PSP Tactics Ogre FILETABLE.BIN manifest decoder.

Format based on Gibbed.TacticsOgre FileTableFile / DirectoryHeader /
BatchHeader / FileHeader. Uses only the Python standard library.
Does not write, patch, or redistribute game assets.
"""
import argparse
import hashlib
import json
import struct
from pathlib import Path


def decode_table(data):
    if len(data) < 68:
        raise ValueError("Truncated FILETABLE header")
    if data[:2] == b"\xf1\x1e":
        endian = "<"
    elif data[:2] == b"\x1e\xf1":
        endian = ">"
    else:
        raise ValueError("Invalid FILETABLE signature")

    def read(fmt, offset):
        return struct.unpack_from(endian + fmt, data, offset)

    name_count, dir_count, version = read("HHH", 2)
    if version != 4:
        raise ValueError("Unsupported FILETABLE version")
    table_offset, total_size = read("II", 8)
    if total_size != len(data):
        raise ValueError("This reader targets PSP tables, not extended Reborn tables")
    title_id = data[16:32].split(b"\0", 1)[0].decode("ascii")
    title_id2 = data[32:48].split(b"\0", 1)[0].decode("ascii")
    if read("H", 48)[0] != 0:
        raise ValueError("Unexpected file-table metadata")
    pos = 68
    name_hashes = {}
    for _ in range(name_count):
        name_hash, directory_id, file_id = read("IHH", pos)
        pos += 8
        name_hashes[(directory_id, file_id)] = f"{name_hash:08X}"

    directories = []
    for _ in range(dir_count):
        if pos + 24 > len(data):
            raise ValueError("Truncated directory header")
        (directory_id, encrypted, block_shift, data_base, unknown,
         install, batch_count, name_count_in_dir, name_index,
         batch_offset, install_base) = read("HBBIBBHHHII", pos)
        pos += 24
        if unknown != 0:
            raise ValueError("Unexpected directory flags")
        directories.append(dict(
            id=directory_id, encrypted=bool(encrypted),
            block_shift=block_shift, base=data_base, install=bool(install),
            batch_count=batch_count, batch_offset=batch_offset,
            name_count=name_count_in_dir, name_index=name_index,
            install_base=install_base))

    batch_start = pos
    batch_total = sum(d["batch_count"] for d in directories)
    if batch_start + batch_total * 8 != table_offset:
        raise ValueError("Invalid batch-table boundary")
    batches = []
    for _ in range(batch_total):
        first_id, count, packed = read("HHI", pos)
        pos += 8
        batches.append((first_id, count, packed >> 29, packed & 0x1FFFFFFF))

    layouts = {2: "HH", 3: "HI", 4: "IH", 5: "II"}
    entry_sizes = {k: struct.calcsize(endian + value) for k, value in layouts.items()}
    if any(flags not in layouts for _, _, flags, _ in batches):
        raise ValueError("Unsupported PSP batch encoding")
    expected_bytes = sum(count * entry_sizes[flags] for _, count, flags, _ in batches)
    if table_offset + expected_bytes != total_size:
        raise ValueError("File-entry section size mismatch")

    records = []
    for directory in directories:
        if directory["batch_offset"] % 8:
            raise ValueError("Unaligned batch-table offset")
        batch_index = directory["batch_offset"] // 8
        stop = batch_index + directory["batch_count"]
        if stop > len(batches):
            raise ValueError("Directory batches outside table")
        for first_id, count, flags, relative in batches[batch_index:stop]:
            offset = table_offset + relative
            if offset + count * entry_sizes[flags] > len(data):
                raise ValueError("Batch data outside table")
            for i in range(count):
                block, size = read(layouts[flags], offset + i * entry_sizes[flags])
                file_id = first_id + i
                byte_offset = directory["base"] + (block << directory["block_shift"]) * 0x800
                records.append(dict(
                    archive=f"{directory['id']:04X}.BIN",
                    directory_id=directory["id"], file_id=file_id,
                    offset=byte_offset, size=size,
                    name_hash=name_hashes.get((directory["id"], file_id)),
                    encrypted=directory["encrypted"], install=directory["install"]))
    return dict(title_id=title_id, secondary_title_id=title_id2,
                sha256=hashlib.sha256(data).hexdigest(),
                directories=directories, records=records)


def verify_archives(index, folder):
    archive_groups = {}
    for record in index["records"]:
        archive_groups.setdefault(record["archive"], []).append(record)
    checks = []
    for name, records in sorted(archive_groups.items()):
        source = folder / name
        if not source.exists():
            checks.append(dict(archive=name, status="not supplied", count=len(records)))
            continue
        length = source.stat().st_size
        invalid = sum(1 for record in records
                      if record["offset"] + record["size"] > length)
        checks.append(dict(archive=name,
                           status="OK" if invalid == 0 else "OUT_OF_BOUNDS",
                           count=len(records), bytes=length, invalid=invalid))
    return checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("filetable", type=Path)
    parser.add_argument("--archives", type=Path,
                        help="Optional folder with BIN files for size checks")
    parser.add_argument("--output", type=Path,
                        default=Path("to_filetable_manifest.json"))
    args = parser.parse_args()
    result = decode_table(args.filetable.read_bytes())
    if args.archives:
        result["archive_checks"] = verify_archives(result, args.archives)
    args.output.write_text(json.dumps(result, indent=2) + "\n",
                           encoding="utf-8")
    print(f"{result['title_id']}: {len(result['directories'])} directories; "
          f"{len(result['records'])} resources")
    for check in result.get("archive_checks", []):
        if check["status"] != "not supplied":
            print(check)
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
