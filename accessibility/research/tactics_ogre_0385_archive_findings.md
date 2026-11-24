# 0385.BIN archival mapping (2026-11-24)

Analysis of the user's supplied `0385.BIN` against the previously decoded `FILETABLE.BIN` manifest, using the existing conservative EMES-table parsing method. Game data is **not** checked into the repository.

- Archive size: 4,816,912 bytes.
- `0385.BIN` is directory ID `0x0385` (901 decimal), with **42** indexed resource/file IDs.
- All 42 indexed resources have in-bounds byte ranges; manifest marks them not encrypted and not install-only.
- Raw marker occurrences (including nested/repeated): **359 `pakd`**, **113 `EMES`**, **39 `RIFF`**, no `PGRS`.
- Conservative valid-`EMES` parser: **36 tables**, **252 message rows**, in **19 indexed resources**. All 252 message IDs are distinct *within this archive*. This does **not** imply every raw EMES marker was decoded.
- 252 provisional printable-ASCII guesses; sentence fragments are not authoritative transcripts.
- Recognizable content is primarily story/dialogue, including branching narrative decisions, rather than demonstrated character-creation interface text.
- Structural examples of recovered IDs:
  - `0385.BIN / resource 10 / message 1`: initial Lanselot-related conversation
  - `0385.BIN / resource 140 / message 284`: a narrative choice
  - `0385.BIN / resource 160 / message 317`: Lanselot dialogue
  - `0385.BIN / resource 260 / message 436`: another branching narrative choice
- Previous `0000.BIN` and `0384.BIN` corpus had 128 message rows. Combined corpus is now **380 rows** across three archive files.
- Proper mapping key remains `(archive ID, resource ID, message ID)`, and live runtime message selection is not yet proven.

**Next candidate:** `0386.BIN`, the immediately subsequent indexed archive containing **39** resource IDs. This is based on archive adjacency, not established contents.

The CSV catalog with provisional text guesses was delivered directly to the user; only these research notes are committed here.
