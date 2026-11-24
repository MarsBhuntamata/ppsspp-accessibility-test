# 0386.BIN read-only archive investigation (2026-11-24)

This note reflects inspection of the user's own uploaded `0386.BIN` against the previously decoded `FILETABLE.BIN` manifest. Neither game bytes nor dialogue transcripts are committed.

- Archive size **4,030,480 bytes**, indexed directory **0x0386** (902 decimal), **39** resource records, all in bounds and marked neither encrypted nor install-only.
- Raw tags: `pakd` **247**, `EMES` **118**, `RIFF` **32**, `PGRS` **0**. Counts include tags within nested archive structures and do not imply that all are independent valid entries.
- Conservative `EMES` decoder: **48 valid message tables**, **388** message entries in **17** indexed resource containers. All 388 message IDs are distinct *within this archive*. Other signatures were not fully decoded.
- Content type: primarily narrative dialogue, including characters Catiua, Vyce, Cistina, Lanselot, and scenes discussing Balmamusa and the Liberation Front. Recovered ASCII fragments are incomplete and not authoritative transcripts.

Examples of **structurally grounded identifiers**:

| Archive | Resource ID | Message ID | Provisional topic |
| --- | ---: | ---: | --- |
| `0386.BIN` | 20 | 1 | Story dialogue |
| `0386.BIN` | 90 | 187 | Liberation Front conversation |
| `0386.BIN` | 180 | 459 | Character conversation |
| `0386.BIN` | 200 | 597 | Narrative/choice-related dialogue |
| `0386.BIN` | 260 | 743 | Character conversation |

- Previous combined corpus: **380** message occurrences from `0000`, `0384`, and `0385`.
- Updated combined corpus: **768** message occurrences from four supplied numbered archives.
- Key remains **(archive ID, resource ID, message ID)**; a live PPSSPP UI message/selection lookup has not yet been observed.
- No confirmed name-entry keyboard or character-creation tarot questionnaire IDs recovered from this archive.
- Next sequential candidate: `0387.BIN`, with **44** resources listed in `FILETABLE.BIN`. Sequence alone does not prove matching content.

Files generated for user (not committed): `tactics_ogre_0386_message_ids.csv`, `tactics_ogre_0386_findings.txt`, `tactics_ogre_message_id_catalog_0000_0384_0385_0386.csv`, and `tactics_ogre_0386_structure.json`.
