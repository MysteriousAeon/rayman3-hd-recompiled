# Linux Guest Entry (LGE)

**Status: CLOSED — bounded native PASS (2026-11-06).** Retry 3 (`b165b20`) passed on CachyOS
(Clang/GCC O0/O2) and was independently audited. Isolated, synthetic scope only. Report:
[LINUX_GUEST_ENTRY_2026-11.md](../../../reports/LINUX_GUEST_ENTRY_2026-11.md).

An opt-in, isolated executable (`lge_tests`) that runs **10 real generated Rayman 3 HD
functions** (8 entry points, 2 compiler GPR helpers), taken verbatim from the pinned codegen
output (digest `c7e96852…`), on synthetic inputs. They run inside the real pinned ReXGlue
memory system, brought up by the audited LRB module (`../linux_runtime_bootstrap`). It does not
use `rex::Runtime`, the XEX image, kernel/XAM imports, threads, GPU, audio, input or files.
Native results must equal the Windows reference bit for bit.

## Three separate categories

| Category | Where | Contents |
|---|---|---|
| 1. Committed infrastructure | this directory | selector, selection identities (`lge_selection.json`: names, addresses, digests, no code), harness, gate, tests, `m2_trace.h` shim |
| 2. Private generated code | `private/work/linux_guest_entry/lge-private-generated.zip` | `lge_generated.cpp` (the 10 bodies verbatim + declarations), verbatim `r3hd_pch.h`, `GENERATED_MANIFEST.json`, `windows_reference.json` |
| 3. Native evidence | returned to `private/work/linux_guest_entry/evidence/` | results, logs, ELF/object bytes and dumps. **Private**: the ELF/objects contain compiled game code |

Category 2 is authorized only for the maintainer's own Windows → CachyOS transfer. Never commit,
publish or upload it, and never put it into an evidence ZIP.

## Selected functions

| Guest | Role (SUPPORTED by static reading) | Calls |
|---|---|---|
| 0x820E7440 | memset | none |
| 0x820EB7D8 | forward copy (memcpy variant) | none |
| 0x820E78A0 | memmove | 0x820EB350 when dst < src |
| 0x820EB350 | memcpy, doubleword path; spills r3 at r1-8 | none |
| 0x820E7328 | strncpy | none |
| 0x820E6D08 | strstr | none |
| 0x820F0A28 | format-spec compatibility predicate → 0/1 | none |
| 0x820F7978 | erase(position), vector of 4-byte elements | `__savegprlr_29`, memmove, `__restgprlr_29` |
| 0x820E73CC / 0x820E741C | `__savegprlr_29` / `__restgprlr_29` | none |

Admitted forms: GPR/CR/XER/LR/CTR, plain scalar `REX_LOAD/STORE_U8/16/32/64` and direct calls
inside the set. The selector excludes FPR/VMX/FPSCR, MMIO, reservations/atomics, `dcbz`/memset,
indirect calls/`REX_LOOKUP_FUNC`, imports, traps, setjmp, M4 SEH, global locks, timebase,
`switch` and absolute image/heap address constants. Unaligned scalar accesses and accesses that
cross pages occur only inside one RW allocation, so they never fault on x86-64. Faults across a
protection boundary are tested only as fatal negatives.

**Prelude substitutions (the bodies are never changed):**
- `m2_trace.h` records entered functions, the production M2 hook.
- Under GCC only, `lge_define_rex_func.h` replaces the pinned `DEFINE_REX_FUNC`. It is the
  same declaration with its attributes after `extern "C"`, which GCC 16 requires. It is
  force-included through the template's `#ifndef` extension point.
- The gate checks on every compiler that each `X` is a weak alias of the global `__imp__X`.

**Inline helpers.** A compiler may emit header-inline helpers out of line, typically at O0.
The admitted set is exactly five names (`INLINE_HELPERS` in `lge_gate.py`):
- `rex::ppc::CRRegister::compare<int32_t>` and `compare<uint32_t>`;
- `std::rotl<uint64_t>` under both of its mangled names, and `std::__rotl<uint64_t>`. These
  come from the pinned GCC polyfill for `__builtin_rotateleft64` in `rex/platform.h`.

Each helper a body reaches must be defined in the generated object, and its own body may
reach only listed helpers, local data or stack protection. Aliased names must share one
final-ELF address. Every rotate in the bodies must be `__builtin_rotateleft64` with a literal
shift in [0, 63].

## Harness contract

- **Arena.** A real fixed `AllocFixed` at guest `0x20000000` in the 4 KiB `v00000000` heap:
  `[guard][16 RW pages][guard]`, both guards no-access. Data is in the first 48 KiB; the stack
  `r1` starts at `0x20010F00`.
- **Inputs.** Every case fills the whole arena and the whole `PPCContext` from a fixed
  SplitMix64 seed. It then sets arguments, `r1`, `lr = 0x82FFF000`, 0/1 XER/CR bits and
  `fpscr = 0`.
- **Per case it records and checks:**
  - input digest (arena + integer state);
  - all 32 GPRs, LR, CTR, XER and CR8 before and after;
  - that non-integer context bytes are unchanged;
  - every changed arena byte, each inside a declared writable range;
  - the entered-function trace (from the production M2 prologue hook);
  - an independent host model (memset/memcpy/memmove/strncpy/strstr/erase semantics; 0/1 for
    the predicate).
- **Output.** One canonical line plus SHA-256 per case (`LGE_CASE_V1|…|digest=`). The gate
  compares the case files byte for byte and the archived file field by field.
- **Native extras.** The LRB owner is exclusive before and after; zero admitted faults; guard
  pages stay no-access.
- **Fatal negatives** (`lge-write-guard`: memset into the high guard; `lge-read-guard`: strncpy
  reading it). The access comes from generated code and is unadmitted, so the owner must
  terminate in signal context. The traced contract is the LRB `unadmitted` profile: witness
  `begin`, one SEGV_ACCERR at the guard address, same-process SI_TKILL, real `-11`.
- **Link.** `lge_tests` is linked `-z now`: the executable's PLT is bound at load, so the
  owner's terminal path does not enter the lazy resolver. The stack protector remains reachable;
  whole-handler async-signal safety and full XSTATE are not claimed.

## Windows (maintainer development host)

```text
python tools/experiments/linux_guest_entry/test_lge_gate.py
python tools/experiments/linux_guest_entry/lge_gate.py extract
tools\devenv.bat python tools/experiments/linux_guest_entry/lge_gate.py windows --repeats 5
python tools/experiments/linux_guest_entry/lge_gate.py private-zip
python tools/experiments/linux_guest_entry/lge_gate.py source
```

## CachyOS procedure (one session)

Uses the existing SDK checkout and install prefix; nothing is fetched, patched or installed.

```sh
W=~/Projects/RaymanLGE; mkdir -p "$W" && cd "$W"
sha256sum /path/to/lge-cachyos-source.zip /path/to/lge-private-generated.zip   # compare with the .sha256 files
unzip -q /path/to/lge-cachyos-source.zip
mkdir -p private/work/linux_guest_entry && unzip -q /path/to/lge-private-generated.zip -d private/work/linux_guest_entry
python3 - <<'PY'
import hashlib, json, pathlib
for m, root in (("SOURCE_MANIFEST.json", "."), ("private/work/linux_guest_entry/PRIVATE_MANIFEST.json", "private/work/linux_guest_entry")):
    for name, expected in json.loads(pathlib.Path(m).read_text()).items():
        assert hashlib.sha256(pathlib.Path(root, name).read_bytes()).hexdigest() == expected, name
print('MANIFESTS PASS')
PY
SDK=/home/<user>/Projects/RaymanTests/external/rexglue-sdk
PREFIX=/home/<user>/Projects/RaymanOwnership/sdk-install
OUT="$PWD/private/work/linux_guest_entry/native"; mkdir -p "$OUT"
python3 tools/experiments/linux_guest_entry/test_lge_gate.py > "$OUT/validator.log" 2>&1; echo "validator exit=$?"
python3 tools/experiments/linux_guest_entry/lge_gate.py run --sdk "$SDK" --prefix "$PREFIX" \
  --private "$PWD/private/work/linux_guest_entry/private_generated" --out "$OUT" > "$OUT/console.log" 2>&1
echo "gate exit=$?"; tail -n 3 "$OUT/console.log"
# Only after "LGE_GATE PASS ..." (exit 0):
python3 tools/experiments/linux_guest_entry/lge_gate.py evidence --out "$OUT" --zip "$OUT/lge-native-evidence.zip"
# Otherwise:
python3 tools/experiments/linux_guest_entry/lge_gate.py evidence --out "$OUT" --zip "$OUT/lge-native-failure.zip" --failure
```

Expected: `LGE_GATE PASS configurations=4 normal=80 traced=40 cases=124 lrb_regression=PASS`.
The gate builds Clang 22 and GCC 16 at O0 and O2 with `-Wall -Wextra -Werror`. For each
configuration it runs:
- 20 normal runs, each case file byte-identical to the Windows reference;
- 5 × 2 traced fatal runs;
- binary checks:
  - BIND_NOW;
  - every selected body's relocations reach only selected functions, M2Enter, the SDK CR
    compare helper or local strings;
  - no unselected generated function in the object.

It then reruns LRB unchanged (5 normal runs, 1 × each fatal mode, leak probe, `--skip-prior`).
The gate stops at the first failure and keeps failed case files. Do not weaken options. A
refused ptrace is a blocker; do not change security settings. Expected time: about 5–15 minutes.

### Retry after a failed run

Keep the old output and package it as a failure ZIP first. Only the source package is
replaced; the private package is reused unchanged (its SHA-256 must still match). Extract the
full replacement source ZIP over the workspace, so that the whole-tree manifest proves the
result, then use a NEW output directory:

```sh
cd ~/Projects/RaymanLGE
python3 tools/experiments/linux_guest_entry/lge_gate.py evidence --out "$PWD/private/work/linux_guest_entry/native" \
  --zip "$PWD/private/work/linux_guest_entry/native/lge-native-failure-attempt1.zip" --failure
unzip -o -q /path/to/lge-cachyos-source-retryN.zip      # then the MANIFESTS check above
OUT="$PWD/private/work/linux_guest_entry/native_retryN"; mkdir -p "$OUT"   # then validator + run as above
```

Return the evidence ZIP to `private/work/linux_guest_entry/evidence/`. Then:

```text
python tools/experiments/linux_guest_entry/lge_gate.py audit --archive private/work/linux_guest_entry/evidence/lge-native-evidence.zip --implementation FULL_40_CHARACTER_COMMIT
```

The audit is structural. Root must still review the final ELF, the handler and the generated
object disassembly before any PASS claim.

## Not established

Game launch, `rex::Runtime`/`KernelState`, imports, threads, indirect dispatch,
FPR/VMX/reservation/MMIO/`dcbz` forms, guest exceptions, arbitrary retry, whole-handler async
safety, full XSTATE, production signal coexistence, and any behaviour outside the 124 synthetic
cases.
