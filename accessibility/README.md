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
- Decoded the PSP `FILETABLE.BIN` index (29 archive directories and 8,651 resource entries from the supplied One Vision sample). Each entry maps to a numbered BIN archive, file ID, byte offset, and size. Bounds checks pass for all 11 entries in the two supplied archives. This is **not** yet a mapping from resource ID to currently displayed text.
- The proposed next reverse-engineering step is to trace an EMES/resource reference from a known game screen through PPSSPP's debugger, after verifying the game's text loading functions. Do not assume that PSP graphics output contains readable strings.

## Accessibility design
All eventual on-device probes must be keyboard-driven and speak instructions, with no time-limited console-reading requirement. Preserve the player's existing RetroArch setup and saves; keep `master` unchanged until a useful feature is verified.


## PSP archive resource manifest (new)

The read-only decoder follows the field layouts described in
[Gibbed's Tactics Ogre file table implementation](https://github.com/gibbed/Gibbed.LetUsClingTogether/blob/main/projects/Gibbed.TacticsOgre.FileFormats/FileTableFile.cs).

```powershell
py accessibility/research/to_filetable_manifest.py "path/to/FILETABLE.BIN" --archives "path/to/USRDIR" --output "to_filetable_manifest.json"
```

It requires only Python 3 and does not change the game, PPSSPP, or saves.
Do not commit the generated JSON, extracted text, or proprietary game resources.
On the supplied sample it identified 29 directories / 8,651 resources; supplied
`0000.BIN` (1 record) and `0384.BIN` (10 records) passed bounds validation.
All ten located records in `0384.BIN` begin with the `pakd` magic.

Run the standard-library regression suite with:

```powershell
py -m unittest discover -s accessibility/research -p "test_*.py" -v
```

The accessibility-only CI workflow checks Python syntax and these tests on the
`to-accessibility` branch, without building PPSSPP. A live NVDA reader is
**not yet implemented**: the next research problem is correlating an identified
resource/message ID with an actual active UI selection in emulator memory.
