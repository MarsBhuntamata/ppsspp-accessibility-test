> **STATUS (2026-11-22): OCR speaking probe is suspended, not playable.**
> Live testing confirmed that v0.3 responds to requests but announces
> "No text recognized on the current screen" in both PPSSPP and the bridge.
> This proves the pipeline returns an empty recognition result, **not** whether
> the game pixels were correctly captured. Stop distributing it as a playable
> test. No further user testing of the OCR bridge requested. The first useful
> milestone is an actual selection-to-text-to-NVDA integration based on the
> currently running game version, with keyboard/menu functionality before
> advanced features. Avoid F8 and other PPSSPP-bound keys.

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


## Mapping individual resources to EMES messages

Generate a FILETABLE manifest first, then run:

```powershell
py accessibility/research/to_resource_emes.py to_filetable_manifest.json "path/to/USRDIR" --output to_resource_messages.jsonl
```

This combines the extracted file offsets with the provisional EMES decoder to
label messages with their parent archive and resource ID. On the two supplied
One Vision archives, the mapper located **128 message records in 5 resources**:

- `0000.BIN` resource ID 0
- `0384.BIN` resource IDs 10, 12, 16 and 18 (resource 18 has two tables)

These are archive identifiers, **not** menu selection IDs. The extraction is
read-only and the JSONL generated from the user's game should remain local.


## Speaking prototype: standalone PPSSPP

`accessibility/bridge/to_speaking_probe.py` is a **temporary OCR-based**
screen reader for the *game framebuffer*, not the emulator UI. It uses PPSSPP's
read-only `gpu.buffer.screenshot` WebSocket event, the **local/offline**
Windows OCR engine, and Windows SAPI speech independent of NVDA. It avoids
RetroArch completely and does not rely on inaccessible PowerShell prompts.

On Windows, enable PPSSPP's remote debugger at port 56244, launch the game,
then run `accessibility/bridge/start_windows.bat`. The launcher installs
Python dependencies and opens the bridge.

- **Ctrl+Alt+Shift+O**: recognize and speak the currently displayed game screen.
- **Ctrl+Alt+Shift+P**: repeat the last recognized screen text.
- **Ctrl+Alt+Shift+Q**: quit the bridge.

Dependencies: Python 3.11+ on Windows, `websocket-client`, `pywin32`,
and `winrt-Windows.Media.Ocr[all]`, plus a Windows OCR language pack.
Nothing is uploaded to a cloud service. The bridge uses its own local SAPI
speech voice initially, rather than the NVDA controller API.

**Not yet verified on the player's machine:** Windows OCR accuracy, readable
text in One Vision, responsive speech, or game-wide playability. Its current
OCR read is manual and may have the same fundamental recognition limitations
as other OCR tools. The existing game-data index remains research, not active
menu text. This is a practical interim access experiment; permanent
accessibility requires semantic menu, dialogue, and battlefield state decoding.

## v0.2 hotkey and speech fixes

The original F8 hotkey conflicted with PPSSPP's pause control. It has been removed in favor of Ctrl+Alt+Shift+O/P/Q. The Windows SAPI background worker now uses synchronous speech after COM initialization, avoiding an asynchronous voice call that could silently produce no audio. On launch it announces a speech self-test before attempting to connect; this makes voice problems distinguishable from debugger/OCR problems. The Windows launcher now installs the Graphics.Imaging and Storage WinRT namespace packages as well as Media.Ocr. **This remains unverified with the player's live game.**


## v0.3: fixes for the user's actual test results

Observed failures in v0.2:
- `gpu.buffer.screenshot` answered `Neither CPU or GPU is stepping`. PPSSPP requires stepping for this debugger endpoint. The new bridge **does not call it** and will never automatically pause the game for screenshots.
- The user heard no speech and got `UNSPOKEN` logs. The new speech worker logs the SAPI initialization error and tries local Windows PowerShell `System.Speech` synthesis as an independent fallback.
- Global `Ctrl+Alt+Shift+O` worked in the bridge but not in the Tactics Ogre game. The bridge console now accepts **Enter** to read, **R** to repeat, **Q** to quit, so one can Alt+Tab to the bridge and use Enter. Global shortcuts are retained as optional.
- The bridge minimizes its own console briefly during capture so it doesn't obstruct PPSSPP, then restores the console.

The new capture uses Pillow's Windows ImageGrab to read the **visible PPSSPP window** rather than the debugger GPU screenshot. PPSSPP must be visible and not minimized; a covering window or GPU overlay can interfere with pixel capture. A real Windows test is still required. The voice logs and errors are diagnostic evidence, not proof that audio worked.

The automated tests verify source syntax and test utilities, not real Windows SAPI/WinRT/OCR execution.
