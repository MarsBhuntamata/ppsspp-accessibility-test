# 038B.BIN archive investigation (2026-11-24)

Analyzed the user's own 26,675,024-byte `038B.BIN` read-only, using the earlier decoded `FILETABLE.BIN` resource manifest. No game assets or verbatim dialogue checked into GitHub.

## Indexed and nested resource layout

- PSP archive directory `0x038B`, **398** indexed resources. Every resource has an in-bounds offset/size and begins with `pakd`.
- Median resource length **944 bytes**, but several are hundreds of KB.
- Every outer `pakd` offset table passed basic bounds and monotonicity checks. They hold **3,397 immediate nested members**.
- Opening member signatures: **948** `pakd`, **427** `EMES`, and **2,022** other.
- Common signatures in the other member group: `0c000080` (**643**), `IDX0` (**643**), `ashg` (**354**), `SEDB` (**247**), `xlce` (**135**). These are raw signatures, not interpreted format labels.
- Raw archive signature counts including nested data: `pakd` **1,346**, `EMES` **427**, `RIFF` **242**, `PGRS` **0**.

## EMES message IDs

- Conservative existing EMES parser accepted **165** valid tables, totaling **1,104** message occurrences across **73** indexed resources.
- **812** distinct numeric message IDs within this archive; repeated IDs are possible even in one archive. Always qualify an ID with **archive and resource**, and for multiple EMES tables potentially table offset.
- The 427 EMES signatures should **not** be presented as 427 decoded tables; many were not accepted by the current decoder. Alternative EMES layouts or bounds may need investigation.
- Recovered fragments mainly contain late-story dialogue involving Catiua, Heim Castle, the Dark Knights, Lanselot, Ozma and other plot threads. Text reconstruction is incomplete and provisional.
- Earlier corpus **2,078**, combined through `038B.BIN` **3,182** message occurrences over nine supplied numbered archives.
- No confirmed character-name keyboard, birthdate, or opening tarot questionnaire resources from decoded message text. Non-EMES data is **not** ruled out.

## Next archive vs. better decoding

- Next indexed `038C.BIN` has **65** resources; `038D.BIN` has **354**.
- Instead of relying only on sequential BIN uploads, inspect **IDX0/ashg/SEDB/xlce** and nested pakd members to locate text, scripts, UI layouts, or indexes. Whether these hold chargen data is unproven.
- Local user outputs: `tactics_ogre_038B_message_ids.csv`, `tactics_ogre_038B_nested_members.csv`, `tactics_ogre_038B_resource_structure.csv`, `tactics_ogre_038B_findings.txt`, and `tactics_ogre_message_id_catalog_through_038B.csv`.
