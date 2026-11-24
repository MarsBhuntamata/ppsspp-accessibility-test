# Tactics Ogre PSP numbered-archive ID inventory (2026-11-24)

Inspected the actual user-uploaded `FILETABLE.BIN`, `0000.BIN`, `0384.BIN` and previously produced `to_filetable_manifest.json` and `to_resource_messages.jsonl` using the repo's existing `to_filetable_manifest.py`, `to_emes_index.py`, and `to_resource_emes.py` research context. This note contains **structure/identifiers only**, not copyrighted game prose.

## Verified index structure

- 29 indexed archive directories, **8,651** file/resource records total.
- Archive naming follows **four-digit uppercase hexadecimal directory IDs**, e.g. decimal 900 (`0x384`) = `0384.BIN`.
- Index records provide an archive name, **resource/file ID**, byte offset and length. **751** entries have name-hash values; hashes are not human-readable filenames.
- Nested **EMES** message tables add a further **message ID**. Therefore the useful identity is **(archive ID, resource ID, message ID)**, *not* an unqualified number.
- Existing heuristics extracted **128 EMES message occurrences** across five resource containers in the two supplied numbered archives. Text readings are *incomplete, printable-ASCII guesses* and should not be used as authoritative speech.

| Archive | Indexed resource ID | Indexed message IDs | Recognizable contents (provisional) |
| --- | ---: | ---: | --- |
| `0000.BIN` | 0 | 36 | General tutorial and world map guidance |
| `0384.BIN` | 10 | 36 | Same message IDs and readable text fragments as 0000/0 |
| `0384.BIN` | 12 | 10 | Includes crafting guidance at message 428 |
| `0384.BIN` | 16 | 22 | Includes combat/stronghold guidance |
| `0384.BIN` | 18 | 24 | Includes **World Tarot** explanation at message 590 |

**Important:** World Tarot is not necessarily the **character-creation tarot questions**. Message 590 does not establish either tarot questionnaire ID.

The `0000/0` and `0384/10` record sets contain the exact same **36 message IDs** and matching available text guesses. This suggests some reuse/duplication across resources; these are **message records**, not proof the entire archive chunks are identical.

## Examples of identifiers actually recovered

- `(0384.BIN, resource 12, message 428)` = crafting tutorial text
- `(0384.BIN, resource 18, message 590)` = World Tarot explanation
- `(0384.BIN, resource 10, message 476)` = world-map movement tutorial
- `(0000.BIN, resource 0, message 476)` = matching movement tutorial reference

They are **confirmed mappings from indexed archive bytes to text fragments**, *not* runtime menu selection mappings.

## Target for next archive inspection

`0385.BIN` is the adjacent indexed directory and contains **42** resources, making it a bounded follow-up after the verified EMES resources in `0384.BIN`. This is a **prioritization hypothesis**, not evidence of any particular tarot text in 0385.

Use already committed readers on that additional archive. Compare EMES table IDs and text formats, then search for title/creation terms, and only subsequently request another archive. Do not ask again for `FILETABLE.BIN`, `0000.BIN`, or `0384.BIN`.

## Accessibility interpretation

Resource IDs answer *which text exists and where*. The PPSSPP live object pointer/cursor work answers *which text is currently selected*. We need an observed cross-reference before speaking arbitrary archive IDs as a selected menu entry.
