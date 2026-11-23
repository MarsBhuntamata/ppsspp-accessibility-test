#!/usr/bin/env python3
"""Tactics Ogre v14 passive transition/connection diagnostic for stock PPSSPP.

No execution breakpoints, CPU pauses, memory writes, or input injection.
Record menu navigation events, game identity and ELF signature as sessions
cross into character creation. Reconnect if PPSSPP closes the debugger socket.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import os
import sys
import time

import websocket
from to_target_watch import Connection, PORT, GAME_IDS
from to_runtime_mapper import folder, read, matches_relocated_method, METHOD_ELF, METHOD_PREFIX
from to_menu_explorer import release_events
from to_speaking_title import Speaker

LOG_NAME = "tactics-ogre-transition-v14.txt"
# Validated for the user's ULUS10565 build by both v12 and v13 diagnostics.
KNOWN_BASE = 0x08804000
SAMPLE_ADDR = KNOWN_BASE + METHOD_ELF
MAX_SECONDS = 240
MAX_RECONNECTS = 12


def read_session_status(conn, log, marker):
    game = (conn.request("game.status").get("game") or {})
    game_id = game.get("id")
    log.write(f"{marker} game_id={game_id} title={game.get('title', '')!r}\n")
    if game_id not in GAME_IDS:
        return False
    try:
        code = read(conn, SAMPLE_ADDR, len(METHOD_PREFIX))
        ok = matches_relocated_method(code)
        log.write(f"{marker}_CODE address=0x{SAMPLE_ADDR:08X} "
                  f"valid={ok} bytes={code.hex()}\n")
    except Exception as exc:
        log.write(f"{marker}_CODE_ERROR {type(exc).__name__} {exc}\n")
    return True


def run(port, log, speaker, max_seconds=MAX_SECONDS, max_reconnects=MAX_RECONNECTS):
    conn = None
    log.write("TACTICS OGRE PASSIVE TRANSITION DIAGNOSTIC v14\n")
    log.write(f"START {datetime.now().isoformat(timespec='seconds')}\n")
    log.write("NO_BREAKPOINTS NO_PAUSE NO_MEMORY_WRITES NO_INPUT_INJECTION\n")
    log.write(f"ELF_SAMPLE address=0x{SAMPLE_ADDR:08X} (validated ULUS10565 only)\n")
    log.flush()
    deadline = time.monotonic() + max_seconds
    reconnects = 0
    events = 0
    last_check = 0.0
    had_connected = False
    try:
        while time.monotonic() < deadline:
            if conn is None:
                if reconnects > max_reconnects:
                    log.write("STOP reconnect_limit\n")
                    break
                try:
                    conn = Connection(port)
                    status_ok = read_session_status(conn, log, "CONNECTED" if not had_connected else "RECONNECTED")
                    log.flush()
                    if not status_ok:
                        log.write("STOP not Tactics Ogre\n")
                        break
                    if had_connected:
                        speaker.say("Ogre debugger reconnected.")
                    else:
                        speaker.say("Ogre transition watcher ready.")
                    had_connected = True
                    last_check = time.monotonic()
                except Exception as exc:
                    log.write(f"CONNECT_ERROR attempt={reconnects} {type(exc).__name__}: {exc}\n")
                    log.flush()
                    if conn:
                        try:
                            conn.close()
                        except Exception:
                            pass
                    conn = None
                    reconnects += 1
                    time.sleep(0.8)
                    continue
            try:
                if conn.pending:
                    msg = conn.pending.popleft()
                else:
                    try:
                        msg = conn.recv()
                    except websocket.WebSocketTimeoutException:
                        msg = None
                if msg is not None:
                    event = msg.get("event", "")
                    if event == "game.quit":
                        log.write(f"GAME_QUIT event={msg}\n")
                        log.flush()
                        # The emulator may be transitioning to another game/load,
                        # so try a new connection rather than asserting a crash.
                        conn.close()
                        conn = None
                        reconnects += 1
                        continue
                    released = release_events(msg)
                    if released:
                        events += 1
                        log.write(f"INPUT_RELEASE #{events} buttons={','.join(released)}\n")
                        log.flush()
                    elif event in ("cpu.stepping", "cpu.resume", "cpu.breakpoint.hit", "game.start"):
                        log.write(f"DEBUGGER_EVENT event={event} data={str(msg)[:350]}\n")
                        log.flush()
                if time.monotonic() - last_check >= 3:
                    # Heartbeat confirms remote debugger is still responding and
                    # that the same game remains running after menu transitions.
                    read_session_status(conn, log, "HEARTBEAT")
                    log.flush()
                    last_check = time.monotonic()
            except Exception as exc:
                log.write(f"DISCONNECTED after_events={events} reconnects={reconnects} "
                          f"reason={type(exc).__name__}: {exc}\n")
                log.flush()
                try:
                    conn.close()
                except Exception:
                    pass
                conn = None
                reconnects += 1
                time.sleep(0.7)
        log.write(f"FINISHED events={events} reconnects={reconnects}\n")
        speaker.say("Ogre transition log saved.")
        return 0
    except KeyboardInterrupt:
        log.write("INTERRUPTED\n")
        return 0
    finally:
        if conn:
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
    print("Tactics Ogre v14 passive connection and character-creation watcher", flush=True)
    print("Navigate from the opening menus into name entry, birth date or tarot.", flush=True)
    print("No breakpoints or game input changes. Log saved beside executable.", flush=True)
    print("Log:", path, flush=True)
    try:
        with path.open("w", encoding="utf-8", buffering=1) as log:
            code = run(args.port, log, Speaker())
    except OSError as exc:
        print("Could not write log:", exc, flush=True)
        code = 2
    if os.name == "nt" and sys.stdin and sys.stdin.isatty():
        try:
            input("Press Enter to close...")
        except EOFError:
            pass
    return code


if __name__ == "__main__":
    raise SystemExit(main())
