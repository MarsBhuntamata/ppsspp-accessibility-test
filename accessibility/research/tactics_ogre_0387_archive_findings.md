# 0387.BIN resource/message ID inventory (2026-11-24)

Examined user's supplied `0387.BIN` against previously decoded `FILETABLE.BIN` manifest. Game bytes and copyrighted dialogue not checked into GitHub.

- `0387.BIN` archive size **3,276,816 bytes**.
- Directory ID `0x0387` / decimal 903; **44** indexed resource records, all in bounds.
- Raw signatures (may include nested archive signatures): `pakd` **232**, `EMES` **97**, `RIFF` **22**, `PGRS` **0**.
- Conservative parser: **43** valid `EMES` tables, **236** message records distributed among **18** indexed resources. All 236 message IDs distinct within this archive.
- Subject: primarily story dialogue, including discussion of Balmamusa, the Resistance, Galgastani, Leonar, and a revolt. Text readings are provisional ASCII fragments, not full or verified transcripts.

Example structurally grounded IDs:

| Archive | Resource ID | Message ID | Topic (provisional) |
| --- | ---: | ---: | --- |
| 0387.BIN | 30 | 1 | Siblings' opening conversation |
| 0387.BIN | 90 | 52 | Discussion of Balmamusa |
| 0387.BIN | 140 | 156 | Return to the Resistance |
| 0387.BIN | 220 | 312 | News of revolt |
| 0387.BIN | 260 | 335 | Orders during castle assault |

- Prior combined corpus: **768** message occurrences.
- Now **1,004** indexed message occurrences in `0000.BIN`, `0384.BIN`, `0385.BIN`, `0386.BIN`, and `0387.BIN` (five archives).
- Character creation name-entry cursor / tarot questionnaire not identified from decoded message entries. Do **not** equate World Tarot with opening questionnaire.
- Identifiers require context of archive + resource + message; no live PPSSPP message object mapping established yet.
- Next sequential archive `0388.BIN` contains **59** indexed resources; archive adjacency only, contents not yet verified.

Files delivered directly to user: `tactics_ogre_0387_message_ids.csv`, `tactics_ogre_0387_findings.txt`, and `tactics_ogre_message_id_catalog_0000_0384_0385_0386_0387.csv`.
