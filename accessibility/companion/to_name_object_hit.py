#!/usr/bin/env python3
"""Find active name-entry object by intercepting one verified MIPS code location.

READ-ONLY game memory. Sets ONE temporary debugger breakpoint, briefly pauses
on the actual name-entry routine, captures $s0, removes the breakpoint, and
resumes PPSSPP. Start on the title screen, before the name keyboard appears.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime
import os
import struct
import sys
import time

import websocket
from to_runtime_mapper import (folder, LOG_NAME as OLD_LOG, read, scan_for_base,
                               matches_relocated_method, METHOD_ELF,
                               METHOD_PREFIX, RAM_START, RAM_END)
from to_target_watch import Connection, PORT, GAME_IDS, stop_requested
from to_speaking_title import Speaker

LOG_NAME = "tactics-ogre-name-object-hit.txt"
BREAK_TIMEOUT = 150
OBJECT_BYTES = 0x1C0
OFFSETS = (0x60, 0x7A, 0x88, 0xA8, 0xB0, 0x180, 0x194, 0x19C,
           0x1A0, 0x1A4, 0x1A5, 0x1A7, 0x1A9, 0x1AA, 0x1AB)


def is_psp_ram_pointer(value):
    return RAM_START <= value <= RAM_END - OBJECT_BYTES and value % 4 == 0


def inspect_object(conn, addr, log, label):
    if not is_psp_ram_pointer(addr):
        log.write(f"INVALID_OBJECT_CANDIDATE label={label} addr=0x{addr:08X}\n")
        return
    data = read(conn, addr, OBJECT_BYTES)
    log.write(f"OBJECT_SNAPSHOT {label} address=0x{addr:08X}\n")
    for offset in OFFSETS:
        if offset in (0x7A, 0x1A4, 0x1A5, 0x1A7, 0x1A9, 0x1AA, 0x1AB):
            value = data[offset]
            log.write(f"FIELD {label} +0x{offset:03X} u8={value}\n")
        else:
            value = struct.unpack_from("<I", data, offset)[0]
            log.write(f"FIELD {label} +0x{offset:03X} u32=0x{value:08X}\n")
    for off in (0x60, 0x19C, 0x1A0):
        child = struct.unpack_from("<I", data, off)[0]
        if is_psp_ram_pointer(child):
            log.write(f"LINKED_CANDIDATE owner={label} offset=0x{off:X} "
                      f"address=0x{child:08X}\n")
            try:
                blob = read(conn, child, 0x1B0)
                log.write(f"LINKED_BYTES owner={label} offset=0x{off:X} "
                          f"at=0x{child:08X} raw_hex={blob[:48].hex()}\n")
                for coff in (0x180, 0x194):
                    log.write(f"LINKED_FIELD owner={label} offset=0x{off:X} "
                              f"+0x{coff:X}=0x{struct.unpack_from('<I', blob, coff)[0]:08X}\n")
            except Exception as exc:
                log.write(f"LINKED_READ_FAIL {type(exc).__name__}: {exc}\n")


def run(port, log, speaker, timeout=BREAK_TIMEOUT):
    conn = None
    breakpoint_at = None
    resumed = False
    own_breakpoint = False
    log.write("TACTICS OGRE NAME OBJECT BREAKPOINT v13\n")
    log.write(f"START {datetime.now().isoformat(timespec='seconds')}\n")
    log.write("Temporarily pauses on name-entry execution; NEVER writes game memory.\n")
    try:
        conn = Connection(port)
        game = (conn.request("game.status").get("game") or {})
        if game.get("id") not in GAME_IDS:
            raise RuntimeError("Start Tactics Ogre in stock PPSSPP first.")
        log.write(f"GAME {game.get('id')}\n")
        base = scan_for_base(conn, log)
        if base is None:
            log.write("NO_ELF_BASE\n")
            return 1
        breakpoint_at = base + METHOD_ELF
        code = read(conn, breakpoint_at, len(METHOD_PREFIX))
        if not matches_relocated_method(code):
            log.write(f"INVALID_METHOD at=0x{breakpoint_at:08X} code={code.hex()}\n")
            return 1
        existing = conn.request("cpu.breakpoint.list").get("breakpoints") or []
        if any(item.get("address") == breakpoint_at for item in existing):
            log.write("EXISTING_BREAKPOINT refuse to replace user breakpoint\n")
            return 1
        # enabled=True means pause at this point. We immediately remove and resume.
        conn.request("cpu.breakpoint.add", address=breakpoint_at, enabled=True, log=True)
        own_breakpoint = True
        log.write(f"ARMED 0x{breakpoint_at:08X}\n")
        log.flush()
        speaker.say("Ogre name object trap armed. Enter the name keyboard now.")
        print("Now enter the name keyboard in PPSSPP.", flush=True)
        print("The debugger will briefly pause and resume the game on first hit.", flush=True)
        print("Press Q in this window to cancel before capture.", flush=True)
        deadline = time.monotonic() + timeout
        hit = False
        while time.monotonic() < deadline:
            if stop_requested():
                log.write("CANCELLED_BY_USER\n")
                break
            if conn.pending:
                msg = conn.pending.popleft()
            else:
                try:
                    msg = conn.recv()
                except websocket.WebSocketTimeoutException:
                    continue
            if msg.get("event") == "game.quit":
                log.write("GAME_QUIT\n")
                break
            if msg.get("event") != "cpu.breakpoint.hit":
                continue
            info = msg.get("hit") or {}
            if info.get("pc") != breakpoint_at and info.get("address") != breakpoint_at:
                continue
            hit = True
            log.write(f"BREAK_HIT {info}\n")
            # The code uses s0 (GPR 16) as its object pointer in nearby
            # instructions: sw v0,0x19c(s0) at 0xDDCA8.
            reg = conn.request("cpu.getReg", name="s0")
            s0 = reg.get("uintValue")
            if not isinstance(s0, int):
                log.write(f"REGISTER_ERROR {reg}\n")
                break
            log.write(f"OBJECT_CANDIDATE_S0 0x{s0:08X}\n")
            conn.request("cpu.breakpoint.remove", address=breakpoint_at)
            own_breakpoint = False
            # cpu.resume intentionally has no immediate response.
            conn.ws.send(__import__("json").dumps(
                {"event":"cpu.resume", "ticket":conn.ticket+1}))
            resumed = True
            log.write("RESUME_SENT\n")
            log.flush()
            # Allow constructor to finish before inspecting the live object.
            time.sleep(0.5)
            inspect_object(conn, s0, log, "name_window")
            speaker.say("Ogre name object snapshot captured.")
            break
        if not hit:
            log.write("NO_HIT time_limit_or_cancel\n")
        return 0
    except Exception as exc:
        log.write(f"ERROR {type(exc).__name__}: {exc}\n")
        speaker.say("Ogre name object diagnostic stopped.")
        return 1
    finally:
        # Breakpoint cleanup must happen even if data collection fails.
        if conn is not None:
            if own_breakpoint and breakpoint_at is not None:
                try:
                    conn.request("cpu.breakpoint.remove", address=breakpoint_at)
                    log.write("BREAKPOINT_REMOVED_IN_CLEANUP\n")
                except Exception as exc:
                    log.write(f"CLEANUP_BREAKPOINT_ERROR {exc}\n")
            if not resumed:
                try:
                    status = conn.request("cpu.status")
                    if status.get("stepping"):
                        conn.ws.send(__import__("json").dumps(
                            {"event":"cpu.resume", "ticket":conn.ticket+1}))
                        log.write("RESUME_SENT_IN_CLEANUP\n")
                except Exception as exc:
                    log.write(f"CLEANUP_RESUME_ERROR {exc}\n")
            try:
                conn.close()
            except Exception:
                pass
        log.flush()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=PORT)
    args = parser.parse_args()
    path = folder() / LOG_NAME
    print("Tactics Ogre name-entry object trap v13", flush=True)
    print("Log:", path, flush=True)
    with path.open("w", encoding="utf-8", buffering=1) as log:
        rc = run(args.port, log, Speaker())
    if os.name == "nt" and sys.stdin and sys.stdin.isatty():
        try:
            input("Press Enter to close...")
        except EOFError:
            pass
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
