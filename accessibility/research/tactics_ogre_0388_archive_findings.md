# 0388.BIN resource/message ID inventory (2026-11-24)

Read-only analysis of user-supplied 0388.BIN against existing FILETABLE.BIN manifest; no game bytes or copyrighted dialogue checked in.

- Archive size **5,472,272 bytes**, directory ID **0x0388** (904 decimal), **59** indexed resources, all in bounds.
- Raw embedded signature counts (including nested): `pakd` **347**, `EMES` **119**, `RIFF` **54**, `PGRS` **0**.
- Conservative EMES reader recovered **51 tables** and **442 message occurrences** across **28** indexed resource containers. **442 unique message IDs** within this archive (range 1..760).
- Decoded fragment themes: narrative dialogues involving Barbas, Martym, Cistina, Nybeth, Vyce, Leonar, Lanselot, and related plot branches.
- Representative **(archive, resource, message)** mappings from actual bytes:
  - `(0388.BIN, 10, 1)`: Barbas/Martym conversation.
  - `(0388.BIN, 20, 27)`: Galgastani allegiances.
  - `(0388.BIN, 50, 132)`: Cistina and family.
  - `(0388.BIN, 120, 299)`: Oelias and Dievold.
  - `(0388.BIN, 310, 605)`: Vyce and Leonar.
- Combined corpus now **1,446 message occurrences** from `0000.BIN`, `0384.BIN` through `0388.BIN` (six archives).
- Printable ASCII guesses omit control codes and portions of words; not verified full transcripts nor runtime-selected UI text.
- Next sequential indexed archive `0389.BIN`: **62** resources, contents unknown.

Research outputs delivered to user as `tactics_ogre_0388_message_ids.csv`, `tactics_ogre_0388_findings.txt`, `tactics_ogre_message_id_catalog_0000_0384_0385_0386_0387_0388.csv`.
