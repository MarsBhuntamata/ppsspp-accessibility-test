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

## Static disassembly follow-up: confirmed code-table locations (2026-11-23)

Inspected the **user-uploaded decrypted ELF** with `readelf` and `llvm-objdump`. The file's `.text` has ELF address 0x00000000 and file offset 0xC0; the `.rodata` section has ELF address 0x002A31C0 and file offset 0x2A3280. Therefore, for these sections, `file_offset = ELF_address + 0xC0`. These are **unrelocated addresses**, not debugger addresses.

Four UI component name strings are followed, after padding, by contiguous 32-bit words within the executable's `.rodata`. Values fall within its executable section; `llvm-objdump` disassembles the respective targets. This supports the hypothesis that they are **method/function pointer tables**, but precise method roles are still unverified.

| Named component | Table file offset | ELF-relative table address | First code addresses | Count until first zero |
| --- | --- | --- | --- | --- |
| `BirthDayInputMenu` | `0x2A7520` | `0x2A7460` | `0xD0BB4, 0xD0EE0, 0xD17CC, 0xD0EE8` | 13 |
| `MenuCalendarWindow` | `0x2A7588` | `0x2A74C8` | `0xD1BC0, 0xD1D6C, 0xD1D94, 0xD1D74` | 17 |
| `MenuAnswer` | `0x2A7730` | `0x2A7670` | `0xD7454, 0xD7658, 0xD7678, 0xD78EC` | 13 |
| `NameCharListWindow` | `0x2A78F0` | `0x2A7830` | `0xDDC54, 0xDDD48, 0xDE69C, 0xDE5B0` | 9 |

### Specific code evidence
- `0xD0BB4` (first `BirthDayInputMenu` table target) contains valid MIPS code and constructs a pointer to the text string `MN_BIRTHDAY` at ELF address `0x2A743C` using `lui $5, 0x2a` and `addiu $5, $5, 0x743c` (at `0xD0BBC` and `0xD0BD4`). This is a **direct executable-to-name cross-reference** anchoring the birthday component, considerably stronger than the generic memory-change patterns.
- `0xD1BC0` (first `MenuCalendarWindow` target) is valid MIPS and performs initialization-like calls and stores relative to an object register; exact semantics TBD.
- `0xD7454` (first `MenuAnswer` target) performs a series of setup calls and stores into object-relative offsets `0x140`, `0x144`, etc.; exact semantics TBD.
- `0xDDC54` (first `NameCharListWindow` target) similarly initializes object-relative memory and stores a returned pointer at `0x19C`. The table contains distinct code targets `0xDDD48`, `0xDDD50`, `0xDE4C4`, `0xDE544`, etc.
- `0xDE708`, another nearby name-input component's code-table target, contains accesses to object fields `0x7A`, `0xA8`, `0xB0` and nested fields `0x194` / `0x1AF`. These offsets are **object-relative**, not PSP RAM addresses.

### Key caveats and planned next trace
- Being in a function-pointer-looking table does **not** establish which target handles left/right/up/down. That requires a control-flow/data-flow study and confirmation against actual gameplay.
- Do **not** mistake the zero-filled `BOOT.BIN` or encrypted `EBOOT.BIN` for this `ULUS10565_EBOOT.BIN` dump.
- Need to identify PPSSPP's runtime ELF load base, determine whether/where each table appears after relocation, and associate object instances with each user-identified screen.
- Once birthday and name-entry objects are located, examine fields and transitions while stationary vs changing selected value; then produce a **screen-aware reader** with verified labels. No auto-speech on tentative data.
