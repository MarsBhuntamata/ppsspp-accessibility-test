# Tactics Ogre PSP 038A.BIN archive investigation (2026-11-24)

Read-only analysis of user-supplied `038A.BIN` against existing `FILETABLE.BIN` resource manifest; no user game bytes or copyrighted dialogue checked in.

- **5,013,520 bytes**, directory ID `0x038A` (decimal 906), **61** indexed resources, all within file bounds and flagged neither encrypted nor install-only.
- Raw marker occurrences (including embedded/nested data): `pakd` **280**, `EMES` **134**, `RIFF` **48**, `PGRS` **0**.
- Conservative valid-EMES parsing: **52** tables, **312** message occurrences in **30** indexed resource containers. All 312 IDs are distinct *within this archive*; range 1–626. Not every raw signature yielded a valid table.
- Content identified from partial ASCII guesses: story dialogue involving Barbas, Catiua, Vyce, Hobyrim, Ozma, and other campaign events.
- Example verified structural keys (content descriptions provisional):
  - `(038A.BIN, resource 10, message 1)`: Barbas-related exchange.
  - `(038A.BIN, resource 50, message 63)`: massacre-related dialogue.
  - `(038A.BIN, resource 270, message 313)`: mentions Versalia Oberyth.
  - `(038A.BIN, resource 350, message 424)`: Ozma-related exchange.
  - `(038A.BIN, resource 360, message 454)`: Hobyrim dialogue.
- Messages share ID numbers with earlier archives, but that does **not** establish same content. For overlapping IDs, exactly 8 provisional text guesses matched the `0388.BIN` collection, and 8 matched `0389.BIN`.
- Cumulative dataset: **2,078 indexed message occurrences** in the eight supplied numbered archives (`0000`, `0384` through `038A`).
- No confirmed name-entry, birthday, or opening tarot questionnaire content was identified in **decoded EMES text**. They could live in other resource types, other archives, or executable code.
- **Next indexed file `038B.BIN`: 398 resources**, compared with 61 for `038A.BIN`. Median per-resource length 944 bytes versus 8,848 bytes for `038A.BIN`. This structural change is worth investigating, but its contents are not yet known.
- Provisional text guesses are not authoritative transcripts or live NVDA selected-item labels.

Delivered local research outputs: `tactics_ogre_038A_message_ids.csv`, `tactics_ogre_038A_findings.txt`, and `tactics_ogre_message_id_catalog_0000_0384_0385_0386_0387_0388_0389_038A.csv`.
