# Tactics Ogre (ULUS10565) decrypted EBOOT inspection

Source: user-supplied PPSSPP dump `ULUS10565_EBOOT.BIN`, inspected 2026-11-23. This note records evidence, not verified game-menu screen IDs.

## Format
- Actual ELF32 little-endian MIPS-II, not the encrypted `~PSP` container.
- Relocatable PSP program (ELF type 0xffa0), .text at file offset 0xC0, code size 0x2A21F0.
- Entry address 0x10C. LLVM's MIPS disassembler successfully decodes the entry code.
- Relocations exist; **file offsets and unrelocated ELF addresses are not live PPSSPP PSP addresses**. Don't hard-code a value from this table into the companion.

## Internal names in executable rodata

| String | ELF relative address (file offset minus 0xC0) | Implication |
| --- | --- | --- |
| `MN_BIRTHDAY` | 0x2A743C | A named birthday-related component |
| `BirthDayInputMenu` | 0x2A7448 | Birthday input menu implementation |
| `MenuCalendarWindow` | 0x2A74B0 | Calendar display/window implementation |
| `MenuConfirmParts` | 0x2A7644 | Confirmation-related component |
| `MenuConfirm` | near 0x2A7658 | Confirmation-related component |
| `MenuAnswer` | 0x2A7664 | Answer-related component; **not yet proven to be tarot** |
| `NameInputCursor` | 0x2A77E8 | Name-input cursor |
| `NameInputParent` | 0x2A77F8 | Name-input parent |
| `NameInputWindow` | 0x2A7808 | Name-input window |
| `NameCharListWindow` | 0x2A7818 | Character list/window for name entry |
| `MenuKeyLayOutWindow` | 0x2AAB68 | Keyboard/layout-related menu name; exact role TBD |
| `FrontMenu` | 0x2AAA50 | Front-menu component |
| `FILETABLE.BIN` | 0x2AD140 | File table loader reference (approximate, search precise offsets before use) |

Data following several names resembles **tables of pointers to .text**. For example, after `BirthDayInputMenu` the unrelocated 32-bit code-address-like values include 0x000D0BB4, 0x000D0EE0, and 0x000D17CC. After `MenuCalendarWindow`, values include 0x000D1BC0 and 0x000D1D6C. This is a lead to disassemble and correlate with PSP runtime debugger traces, **not yet a verified function map**.

## Consequences for accessibility
1. Stop inferring screen state from the number of Cross presses. Name-input, confirmation, date, answer, and other menus have distinct named code components.
2. Character creation should be studied in user-confirmed order: name keyboard, name confirmation, birth date, first tarot question, second tarot question.
3. Next step: map relocated names/code references and identify the active component or update routine using PPSSPP debugger. Decode cursor positions and actual question/answer strings only after validating against live interaction.
4. The ELF has abundant internal names, but no immediately readable `TAROT` label was found by a plain ASCII string search. `MenuAnswer` alone is not proof of tarot identity. The text may live in the numbered archives.
5. Keep the working title speaker separate; never announce speculative option indices in gameplay.
