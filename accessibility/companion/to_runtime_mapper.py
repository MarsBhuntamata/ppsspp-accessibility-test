#!/usr/bin/env python3
"""Read-only Tactics Ogre ELF load-base and live UI-pointer locator.

Run while the name-entry keyboard is OPEN. Does not speak guessed selections,
modify game memory, press buttons, inject code, or require OCR.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime
import os
from pathlib import Path
import struct
import sys
import time

from to_target_watch import Connection, PORT, GAME_IDS
from to_speaking_title import Speaker

LOG_NAME = "tactics-ogre-runtime-objects.txt"
CHUNK = 0x10000
RAM_START, RAM_END = 0x08800000, 0x0A000000
NAME = b"NameCharListWindow\x00"
BIRTHDAY = b"BirthDayInputMenu\x00"
NAME_ELF = 0x002A7818
BIRTHDAY_ELF = 0x002A7448
VTABLE_ELF = 0x002A7830
METHOD_ELF = 0x000DDC54
# The first MIPS words at NameCharListWindow's first table target.
# LUI $a0,5 ; ADDIU $a0,$a0,-0x7588 ; JAL 0x1f572c (MIPS little-endian).
METHOD_PREFIX = bytes.fromhex("0500043c788a8424cbd5070c")
# Relocation changes immediate fields. Validate only opcode/register pattern.
METHOD_MASKS = (0xFFFF0000, 0xFFFF0000, 0xFC000000)


def folder():
    return Path(sys.executable if getattr(sys, "frozen", False) else __file__).resolve().parent


def decode_block(response, size):
    data = base64.b64decode(response["base64"], validate=True)
    if len(data) != size:
        raise ValueError(f"Expected {size} memory bytes, got {len(data)}")
    return data


def read(conn, address, size):
    return decode_block(conn.request("memory.read", address=address, size=size), size)


def find_load_base(address, buffer, verify):
    """Return module base only when BOTH independent, adjacent strings match."""
    offset = 0
    while True:
        index = buffer.find(NAME, offset)
        if index < 0:
            return None
        loaded_name = address + index
        base = loaded_name - NAME_ELF
        expected_birthday = base + BIRTHDAY_ELF
        if RAM_START <= base < RAM_END and verify(expected_birthday, BIRTHDAY):
            return base
        offset = index + 1


def find_aligned_words(address, buffer, targets):
    """Return pointer slots with target values; never claim they are objects."""
    values = []
    for off in range((-address) & 3, len(buffer)-3, 4):
        value = struct.unpack_from("<I", buffer, off)[0]
        if value in targets:
            values.append((address+off, value))
    return values


def matches_relocated_method(code):
    if len(code) != len(METHOD_PREFIX):
        return False
    for off, mask in zip(range(0, len(code), 4), METHOD_MASKS):
        actual = struct.unpack_from("<I", code, off)[0]
        original = struct.unpack_from("<I", METHOD_PREFIX, off)[0]
        if (actual & mask) != (original & mask):
            return False
    return True


def scan_for_base(conn, log):
    # Game PRX usually loads in early user RAM. Continue wider if necessary.
    for start, end in ((RAM_START, 0x09000000), (0x09000000, RAM_END)):
        log.write(f"SEARCH_NAMES range=0x{start:08X}-0x{end:08X}\n")
        for address in range(start, end, CHUNK):
            try:
                data = read(conn, address, min(CHUNK, end-address))
            except Exception as exc:
                log.write(f"READ_FAIL 0x{address:08X} {type(exc).__name__}: {exc}\n")
                continue
            def verify(other, expected):
                if address <= other and other + len(expected) <= address+len(data):
                    return data[other-address:other-address+len(expected)] == expected
                if RAM_START <= other <= RAM_END-len(expected):
                    try:
                        return read(conn, other, len(expected)) == expected
                    except Exception:
                        return False
                return False
            base = find_load_base(address, data, verify)
            if base is not None:
                log.write(f"ELF_LOAD_BASE 0x{base:08X} name=0x{base+NAME_ELF:08X} "
                          f"birthday=0x{base+BIRTHDAY_ELF:08X}\n")
                return base
            if (address-start) % (CHUNK*16) == 0:
                print(f"Checking game memory near 0x{address:08X}", flush=True)
    return None


def scan_pointer_slots(conn, targets, log):
    found = []
    for address in range(RAM_START, RAM_END, CHUNK):
        try:
            data = read(conn, address, CHUNK)
        except Exception as exc:
            log.write(f"SCAN_FAIL 0x{address:08X} {type(exc).__name__}\n")
            continue
        found.extend(find_aligned_words(address, data, targets))
        if len(found) > 2000:
            log.write("LIMIT pointer matches exceed 2000; stopping\n")
            break
    return found


def run(port, log, speaker):
    conn = None
    log.write("TACTICS OGRE RUNTIME OBJECT LOCATOR v12\n")
    log.write(f"START {datetime.now().isoformat(timespec='seconds')}\n")
    log.write("READ_ONLY module signatures, vtable/method pointers; not cursor labels\n")
    try:
        conn = Connection(port)
        game = (conn.request("game.status").get("game") or {})
        if game.get("id") not in GAME_IDS:
            raise RuntimeError("Start Tactics Ogre in regular PPSSPP first.")
        log.write(f"GAME {game.get('id')} {game.get('title', '')}\n")
        speaker.say("Ogre runtime mapper connected.")
        print("Please keep the name-entry keyboard open during this scan.", flush=True)
        started = time.monotonic()
        base = scan_for_base(conn, log)
        if base is None:
            log.write("RESULT no verified ELF base; do not infer addresses\n")
            print("No verified module base. Upload the log.", flush=True)
            speaker.say("Could not verify game module address.")
            return 0
        candidate_method = base + METHOD_ELF
        code = read(conn, candidate_method, len(METHOD_PREFIX))
        if not matches_relocated_method(code):
            log.write(f"CODE_MISMATCH at=0x{candidate_method:08X} "
                      f"observed={code.hex()} expected={METHOD_PREFIX.hex()}\n")
            speaker.say("Executable layout needs further investigation.")
            return 0
        log.write(f"CODE_CONFIRMED 0x{candidate_method:08X} "
                  f"prefix={code.hex()}\n")
        vtable = base + VTABLE_ELF
        words = read(conn, vtable, 36)
        expected = struct.pack("<I", candidate_method)
        if words[:4] != expected:
            log.write(f"TABLE_MISMATCH 0x{vtable:08X} first={words[:4].hex()} "
                      f"expected={expected.hex()}\n")
            # Still record code base; do not scan for ambiguous objects.
            return 0
        log.write(f"METHOD_TABLE_CONFIRMED 0x{vtable:08X} "
                  f"first={struct.unpack_from('<I', words)[0]:08X}\n")
        # Search memory for pointers to this *verified* method table.
        slots = scan_pointer_slots(conn, {vtable}, log)
        log.write(f"POINTER_SLOTS total={len(slots)}\n")
        for addr, value in slots[:120]:
            log.write(f"POINTER_SLOT address=0x{addr:08X} value=0x{value:08X}\n")
        if not slots:
            log.write("INTERPRETATION method table may be referenced indirectly; "
                      "no object location identified\n")
        else:
            log.write("INTERPRETATION slots are UNVERIFIED references, "
                      "not proven live object or selected characters\n")
        log.write(f"SCAN_SECONDS {time.monotonic()-started:.1f}\n")
        speaker.say("Ogre runtime mapping saved.")
        return 0
    except Exception as exc:
        log.write(f"ERROR {type(exc).__name__}: {exc}\n")
        print("Runtime mapper error:", exc, flush=True)
        speaker.say("Ogre runtime mapper stopped.")
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
    print("Tactics Ogre read-only runtime object locator v12", flush=True)
    print("Log:", path, flush=True)
    try:
        with path.open("w", encoding="utf-8", buffering=1) as log:
            result = run(args.port, log, speaker)
    except OSError as exc:
        print("Cannot write log:", exc, flush=True)
        result = 2
    if os.name == "nt" and sys.stdin and sys.stdin.isatty():
        try:
            input("Press Enter to close...")
        except EOFError:
            pass
    return result


if __name__ == "__main__":
    raise SystemExit(main())
