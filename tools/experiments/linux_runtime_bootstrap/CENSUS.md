# Memory access census of the generated game code

Purpose: aggregate counts of memory access forms in the private recompiled (PPC to C++) code,
to inform a future native Linux integration. Static and read-only. Tracked file: counts and
percentages only, no code lines, function bodies or game addresses.

Tool: `access_census.py` (Python 3 stdlib; test: `test_access_census.py`).

```
python tools/experiments/linux_runtime_bootstrap/access_census.py
python tools/experiments/linux_runtime_bootstrap/test_access_census.py
```

Private output (not tracked): `private/work/linux_runtime_bootstrap/census/census.json` and `census.md`.
Those may contain at most 3 register/number-normalised example lines per category.

## Method

- Streams `private/work/rex/generated/Default/*.cpp` (123 files, 45858 function definitions,
  about 4.6 M lines) with regexes. The 124 `.h` files are hashed but not counted (they hold
  declarations and a copy of the macro definitions, which would inflate counts). The aggregate
  SHA-256 over sorted name+hash of all 247 inputs is `5a4f9dc8d5ae1a16...` (full value in census.json).
- Macro definitions are read from the SDK pin `c94f5ebdcb3c9d1a460ca48e04f9758448f8d518`
  (`resources/templates/codegen/pch_h.inja`, `_indirect_call.inja`). Working copies of both files
  are byte-identical to the pin (recorded in census.json). The generated `r3hd_pch.h` is a
  rendered copy of `pch_h.inja`, not a byte copy.
- Occurrences are token counts; "functions" is the number of distinct function definitions that
  contain at least one occurrence (exact, tracked per category and per group).
- The translator writes the guest mnemonic as a comment before each translated instruction. These
  comments give a second, independent census by guest instruction (used to separate lvx from
  lvlx, lfs from lfd, etc.). The two censuses reconcile exactly (see below).

## Macro semantics (VERIFIED from the pinned definitions)

- Address: `base + (u32)addr + REX_PHYS_HOST_OFFSET(addr)`. The offset is 0 except on Windows
  (and macOS arm64), where addresses >= 0xE0000000 get +0x1000. On Linux x86-64 it is 0.
- Scalars: `REX_LOAD_Un` is `__builtin_bswapN(*(volatile uN*)addr)`; `REX_STORE_Un` the mirror;
  U8 has no swap. They are plain host loads/stores through a `volatile` pointer: no alignment
  check, no page check, no bounds check (the 32-bit guest address is relied on to stay inside
  the 4 GiB reservation), no atomicity guarantee beyond what the host gives.
- `REX_FUNC_PROLOGUE` asserts (`__builtin_assume`/`unreachable`) that `base` is 32-byte aligned.
  A Linux mapping must honour that or the assumption is undefined behavior.
- MMIO: `REX_MM_*` test `0x7F000000 <= addr < 0x80000000`; inside that range they call
  `MMIOHandler::CheckLoad/CheckStore` (U64 as two 32-bit calls), otherwise do the same plain access.
- `REX_LOOKUP_FUNC` reads a function pointer from `base + IMAGE_BASE + IMAGE_SIZE + (target -
  CODE_BASE) * 2`: a dispatch table that lives inside the guest mapping. `REX_CALL_INDIRECT_FUNC`
  range-checks, falls back to `ResolveIndirectFunction`, and calls. No guest memory is fetched as
  instructions; the table region must exist in the mapping on every platform.
- Global lock macros use a host mutex plus an `std::atomic<i32>` counter; they are not guest memory accesses.

## Result

All figures are for the 123 generated `.cpp` files.

### Access size (token occurrences; all guest-memory access macros and vector forms)

| size | occurrences | share |
|---|---:|---:|
| 1 byte | 35,779 | 6.50% |
| 2 byte | 16,989 | 3.09% |
| 4 byte | 438,024 | 79.59% |
| 8 byte | 51,816 | 9.41% |
| 16 byte (aligned vector) | 7,746 | 1.41% |
| total | 550,354 | 100% |

Multi-byte (2/4/8/16): 514,575 (93.50%). 4 byte and wider: 497,586 (90.41%).

### Categories

| category | occurrences | functions | status |
|---|---:|---:|---|
| scalar U8/U16/U32/U64 loads+stores (`REX_LOAD/STORE_U*`) | 542,544 | 37,313 | VERIFIED (macro form) |
| scalar load U8 / U16 / U32 / U64 | 22,070 / 11,393 / 270,658 / 25,972 | 6,104 / 2,573 / 32,500 / 11,835 | VERIFIED |
| scalar store U8 / U16 / U32 / U64 | 13,709 / 5,595 / 167,303 / 25,844 | 4,399 / 1,556 / 29,099 / 12,059 | VERIFIED |
| MMIO `REX_MM_*` (all widths) | 64 (loads 29: U32 28, U16 1; stores 35: U32) | 28 | VERIFIED |
| vector 128-bit guest-memory access via `REX_RAW_ADDR` | 7,746 (load 4,745, store 3,001) | 546 | VERIFIED form, SUPPORTED semantics |
| guest vector aligned lvx/lvx128 + stvx/stvx128 (comments) | 4,303 + 3,001 | 393 + 261 | SUPPORTED |
| guest vector partial lvlx/lvrx/stvlx/stvrx (comments) | 1,002 | 93 | SUPPORTED |
| guest vector element lvewx/stvewx/lvehx/stvehx (comments) | 821 | 117 | SUPPORTED |
| reservation load (`reserved = *(uintN_t*)RAW_ADDR`) | 509 | 240 | VERIFIED form (from generated text) |
| reservation store-conditional (`__sync_bool_compare_and_swap`) | 767 | 240 | VERIFIED form |
| reservation guest instructions lwarx/ldarx/stwcx./stdcx. (comments) | 335 / 174 / 425 / 342 = 1,276 | 240 (any) | SUPPORTED |
| global-lock enter / leave / check | 525 / 788 / 509 | 251 / 251 / 240 | VERIFIED |
| `std::atomic_thread_fence` (seq_cst) | 1,822 | 252 | form VERIFIED, source instruction UNKNOWN |
| bulk `memset` on `REX_RAW_ADDR` (dcbz/dcbzl; sizes 128 x36, 32 x2) | 38 | 11 | SUPPORTED |
| `memcpy` / `memmove` | 0 | 0 | VERIFIED (absent) |
| byte-reversed guest instr. (lhbrx/lwbrx/ldbrx/sthbrx/stwbrx/stdbrx, comments) | 60 | 26 | SUPPORTED |
| lswi/lswx/stswi/stswx/lmw/stmw | 0 | 0 | VERIFIED (absent) |
| `loadu`/`storeu`/`lddqu`/`stream`/`maskload` intrinsics | 0 | 0 | VERIFIED (absent) |
| `REX_RAW_ADDR` total | 9,060 | 788 | VERIFIED |
| `REX_CALL_INDIRECT_FUNC` | 7,308 | 3,375 | VERIFIED |
| `REX_LOOKUP_FUNC` (direct uses in generated code) | 105 | 103 | VERIFIED |
| other/unclassified (RAW_ADDR in unknown form, `base +` outside macros, `REX_LOAD_STRING`, unknown REX tokens, unknown memory-like mnemonics) | 0 | 0 | VERIFIED (none) |

Reconciliation checks: scalar tokens (542,544) equal the sum of the independently observed
per-macro counts; reservation load+store tokens (1,276 by width: 32-bit 760, 64-bit 516) equal
the reservation mnemonic count; 4,745 vector loads = 4,303 aligned + 438 partial + 4 element
guest instructions.

### Detail by guest instruction (comments, SUPPORTED)

- FP: loads lfs-family 34,844 (of which lfsx etc included), lfd-family 8,612; stores stfs-family
  24,733 plus stfiwx 120, stfd-family 4,143. FP accesses compile to the same U32/U64 scalar macros
  (single precision = 4 byte, double = 8 byte) and are included in the scalar rows above.
- Cache/sync: dcbt* 174, dcbf 73, dcbst 3, dcbz 2, dcbzl 36, lwsync 269, eieio 30, sync 36.
  Only dcbz/dcbzl map to a memory macro form (the 38 memsets); no other cache or sync
  instruction maps to a guest-memory access macro in the census.
- Scalar address argument form: base register + immediate 409,519; register + register 27,595;
  precomputed `ea` 30,296; other expression 75,058; bare register 69; constant 15. The address
  is computed at run time in essentially all cases.

## Classification notes and limits

- aligned-scalar candidates: alignment is NOT statically known for any scalar access (base is a
  runtime register). Misaligned U16/U32/U64 access is therefore possible. The macro tolerates
  it by construction (a plain host load/store plus a swap): x86-64 handles unaligned scalar
  `mov` in hardware (SUPPORTED, general ISA knowledge, not tested here). The volatile
  dereference of a cast pointer is formally outside the C++ object rules; it compiles to a
  single `mov` with GCC/Clang for these macros, but this was not checked on Linux.
- unaligned access: there is no explicit unaligned helper (no memcpy-based or `loadu` form). The
  explicit "unaligned-capable" guest forms present are lvlx/lvrx/stvlx/stvrx (1,002 instructions;
  the generated code masks the address with `& ~0xF` and uses a shuffle table, so the host
  access is 16-byte aligned) and byte-reversed loads/stores (60; these swap bytes, they are not
  an alignment form).
- vector: 128-bit accesses use the aligned `simde_mm_load/store_si128` on `REX_RAW_ADDR(ea)`
  where `ea` is masked with `& ~0xF` (7,308 masked assignments) in the observed forms. An
  aligned host vector access faults if the address were not 16-byte aligned; the generated
  masking (SUPPORTED, by inspecting forms, not proven for every path) prevents that. Other
  masks seen: `~0x3` 812 (element), `~0x1` 5, `~127`/`~31` (dcbz, 36/2).
- cross-page: undeterminable statically. Upper bound of cross-page candidates = all multi-byte
  accesses, 514,575, but a naturally aligned access cannot cross a page, so the real set is
  the misaligned scalar subset only (UNKNOWN size); vector forms are 16-byte aligned by masking
  and cannot cross a page.
- atomics: a reservation is a per-context copy of the loaded value (`ctx.reserved`); the
  store-conditional is a value-compare `__sync_bool_compare_and_swap` on the swapped word.
  That is a value-based emulation (ABA-prone; no reservation granule). Width is 32 or 64 bit.
  There is no use of `__atomic`, `std::atomic` or `_Interlocked` in guest memory accesses.
  The 1,822 seq_cst thread fences are not tied to a guest instruction by this census (one
  sampled instance followed an mfmsr comment); their source instruction is UNKNOWN.
- MMIO: only 64 sites, all U32 apart from one U16 load; the MMIO window check is in the macro.
- Instruction fetch: no site reads guest memory as code. Indirect calls resolve through the
  in-mapping function table and a host dispatcher.
- Distinct-function counts are exact; counts are token counts, not dynamic execution counts, so
  they say nothing about how often each form runs.
- Detection depends on the translator's current text forms; a different SDK pin or codegen
  setting can change them. The census does not execute or compile anything.
