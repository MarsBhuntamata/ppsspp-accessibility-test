# Tactics Ogre PSP accessibility research

This is an **experimental** read-only research area, not a working screen reader.

## Goal
Make *Tactics Ogre: Let Us Cling Together* (PSP) usable with NVDA through standalone PPSSPP, with one bridge for vanilla and One Vision. Resource names and statistics must come from the **loaded game version**, never a hardcoded vanilla database.

## What has been verified
- PPSSPP's remote debugger was successfully connected on the player's Windows PC.
- The debugger returned game ID `ULUS10565` and could read emulated memory.
- The supplied `0384.BIN` and `0000.BIN` contain recognizable EMES message structures.
- The initial indexer found 128 records across six plausible EMES tables, with 16 nonempty printable-text guesses. This does **not** prove the full game text has been decoded.
- Memory snapshots did not verify a stable selected-menu index; the earlier `0x08B09DB8` pointer is NOT confirmed.

## Offline use
With Python 3.9+ (standard library only):

```powershell
py accessibility/research/to_emes_index.py "path/to/0384.BIN" "path/to/0000.BIN" --output to_messages.jsonl
```

The indexer reads the player's own extracted files. It does not alter game files or PPSSPP. Do not commit extracted game data, generated message indexes, or ISOs to this repository.

## Known limitations
- `text_guess` is heuristic printable ASCII, not an accurate full decode of the game's message markup.
- `last_extent_provisional` identifies a record whose end is not known from a following offset.
- Archive records are **not** evidence of active menu selections.
- We have not yet decoded the authoritative resource mapping in `FILETABLE.BIN`.
- The proposed next reverse-engineering step is to trace an EMES/resource reference from a known game screen through PPSSPP's debugger, after verifying the game's text loading functions. Do not assume that PSP graphics output contains readable strings.

## Accessibility design
All eventual on-device probes must be keyboard-driven and speak instructions, with no time-limited console-reading requirement. Preserve the player's existing RetroArch setup and saves; keep `master` unchanged until a useful feature is verified.
