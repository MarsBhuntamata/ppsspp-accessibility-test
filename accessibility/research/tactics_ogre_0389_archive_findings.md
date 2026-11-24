# 0389.BIN verified read-only ID analysis (2026-11-24)

Inspected user-supplied `0389.BIN` against existing `FILETABLE.BIN` manifest. No user game assets or copyrighted dialogue checked in.

- File length: **5,439,504 bytes**; directory **0x0389**, **62** indexed resource entries, all in bounds, unencrypted.
- Raw embedded signature counts (include nested data): `pakd` 294, `EMES` 119, `RIFF` 47, `PGRS` 0.
- Conservative EMES parsing: **38 tables**, **320 distinct message IDs**, in **24** resource containers.
- Primary visible text fragments are narrative scenes with Barbas, Martym, Catiua, Dark Knights, etc. Text is incomplete heuristic ASCII reconstruction, not a verified full transcript.
- Example archive/resource/message keys: `(0389,10,1)` Barbas scene; `(0389,30,27)` Catiua/Denam; `(0389,330,444)` standoff; `(0389,370,518)` someone led away; `(0389,410,592)` Dark Knights discussion.
- **205 message IDs overlap with 0388.BIN**, but only IDs **1 through 9** have exactly matching provisional text guesses; cross-archive collisions are common. Always use archive ID + resource ID + message ID and avoid claiming numeric IDs are globally unique.
- Cumulative read-only dataset: **1,766 message occurrences** from `0000.BIN` and `0384.BIN` through `0389.BIN`, seven archives.
- No confirmed character-creation name keyboard, birthdate, or starting tarot-questionnaire IDs yet. Their resources may use different formats from EMES or be defined in executable code.
- Next sequential indexed candidate `038A.BIN` contains **61** resource entries; this is not evidence the desired resource is located there.
