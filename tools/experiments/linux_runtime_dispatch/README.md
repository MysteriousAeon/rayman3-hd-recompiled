# Linux Runtime Generated Dispatch (LRGD)

**Status: implementation prepared; Windows contract VERIFIED; native result UNKNOWN** until
returned CachyOS evidence is independently audited. Report:
[LINUX_RUNTIME_GENERATED_DISPATCH_2026-11.md](../../../reports/LINUX_RUNTIME_GENERATED_DISPATCH_2026-11.md).

An opt-in, isolated executable (`lrgd_tests`). It runs the ten audited LGE generated
Rayman 3 HD functions (private, verbatim, codegen `c7e96852…`) through the **real** pinned
ReXGlue runtime path:

```text
rex::Runtime::Setup(PPCImageInfo, tool mode)
  -> FunctionDispatcher::InitializeFunctionTable   (guest table at IMAGE_BASE + IMAGE_SIZE)
  -> FunctionDispatcher::SetFunction x 10          (the production func_mappings rows)
rex::runtime::ThreadState                          (constructed directly; no XThread, no thread)
FunctionDispatcher::Execute(thread_state, guest, args, n)
  -> ThreadState::Bind, r1 -= 176, lr = 0xBCBCBCBC, fn(ctx, membase), restore
```

- The `PPCImageInfo` carries the production layout constants from `r3hd_pch.h` and exactly the
  ten production `PPCFuncMappings` rows for the selected functions, with the same host symbols.
  No image bytes are loaded; the selected bodies never read code memory.
- Memory, the function table, the arenas and the watched pages are all **runtime-owned**.
- No game data, no title image, no kernel module, imports, threads, GPU, audio or input.
- Not part of the Windows build or release. It changes no production, SDK or generated code.

## Cases and reference equivalence

All 124 LGE cases and all 8 LWR cases are reused unchanged: same order, seeds, synthetic memory
and context fill. The dispatcher legitimately changes four observable things. Each is checked
exactly in the fixture and re-derived field by field by the gate:

| Rule | What the dispatcher does | Applied to |
|---|---|---|
| T1 entry | the callee sees the LGE input with `lr = 0xBCBCBCBC` (whole `PPCContext` byte-compared at the first prologue hook) | every case |
| T2 exit | `Execute` restores r1 (+176) and the caller's LR; the callee's final LR is not observable | every case |
| T2b r12 | `erase` does `mflr r12`, and `__restgprlr_29` reloads r12 from the save slot, so r12 exits as the sentinel | `erase` cases only |
| T3 memory | `__savegprlr_29` stores that LR at entry `r1 - 8`; exactly this 4-byte slot is normalized | `erase` cases only |

Argument registers in the thread-state context are poisoned (`~value`). Only the dispatcher's
`args[]` marshalling can produce the callee's arguments. After the rules above, the
reconstructed `LGE_CASE_V1` / `LWR_CASE_V1` lines must equal the audited Windows references
**byte for byte**. The raw `LRGD_CASE_V1` records keep the unnormalized pre/entry/post states and
memory delta for the gate's independent re-derivation.

Dispatcher proof per case: `ThreadState::Get()` is null before and after `Execute` and is the
test's thread state inside the callee; every prologue sees the thread-state context object; the
return value is r3. Registration proof: dispatcher lookup, the guest table slot read with the
generated prelude's formula, and `ResolveIndirectFunction` all return the registered host symbol;
the table window holds exactly ten entries. Negative: `Execute` on an unregistered in-range
address returns `0xDEADBABE`, enters nothing and writes no guest memory; `SetFunction` outside the
module range is refused.

## Modes (one subprocess per mode, never mixed)

| Mode | Platform | What it establishes |
|---|---|---|
| `default-dispatch` | Windows and Linux | Unchanged SDK initialization; the SDK SEH handler is live, no project owner, ordinary dispatch only (nothing faults). 2 passes of 132 cases, the second must reproduce the first |
| `latch` | Linux | **Experimental** LRSO D1(a), test only: the SDK's own `g_seh_initialized` is set before `Setup`; the unchanged LRB handoff; 2 passes of ordinary dispatch plus the 8 LWR cases dispatched again on watched runtime pages (9 claims per pass) |
| `latch-cycles` | Linux | `latch` for two Setup/Shutdown cycles in one process |
| `latch-traced-positive` | Linux | `latch` under ptrace: exactly 18 kernel `SEGV_ACCERR` stops, each matching a claim |
| `lrgd-write-guard` | Linux, traced | memset through `Execute` into the LGE guard page: terminal through the owner |
| `lrgd-unregistered-page`, `lrgd-unauthorized`, `lrgd-wrong-function` | Linux, traced | watched-page stores through `Execute` that LWR must reject: terminal through the owner |

The restart path is the audited LWR admission unchanged: decoded single-page `mov` stores from
authorized generated ranges, error code 7, one claim and one invalidation per page, no context
edit, drain through `Memory::TriggerPhysicalMemoryCallbacks`.

## Files

| File | Role |
|---|---|
| `lrgd_tests.cpp` | Fixture: runtime lifecycle, registration, thread state, dispatch, normalization, restart, records |
| `CMakeLists.txt` | Build against an existing installed SDK; reuses `lrb_bootstrap.cpp`, `lrb_owner.c`, `lrb_access.S`, `lwr_restart.c` and the LGE generated object with their audited flags |
| `lrgd_gate.py` | Pinned-source contract, private check, Windows reference, packages, native gate, evidence, audit |
| `test_lrgd_gate.py` | Validator tests (Windows-runnable) |

## Windows (development host)

```text
python tools/experiments/linux_runtime_dispatch/test_lrgd_gate.py
python tools/experiments/linux_runtime_dispatch/lrgd_gate.py source-contract
python tools/experiments/linux_runtime_dispatch/lrgd_gate.py private-check
tools\devenv.bat python tools/experiments/linux_runtime_dispatch/lrgd_gate.py windows --repeats 3
python tools/experiments/linux_runtime_dispatch/lrgd_gate.py private-zip
python tools/experiments/linux_runtime_dispatch/lrgd_gate.py source --zip private/work/linux_runtime_dispatch/lrgd-cachyos-source.zip
```

On Windows the real `Runtime::Setup(PPCImageInfo)` and `FunctionDispatcher::Execute` run in
`default-dispatch` mode against the installed SDK. That build is ordinary-only: it never
pretends to have produced a Linux signal, latch or restart.

## CachyOS procedure

See the report's **CachyOS execution** section. Inputs: the source ZIP, the unchanged LGE
private ZIP and the LRGD private reference ZIP. The run uses the existing SDK checkout and
install prefix; nothing is fetched, patched or installed.

## Not established

`XThread`/kernel threads and guest thread attachment, module launch (`SetExecutableModule`),
imports and the export resolver, indirect calls through the table from generated code, a title
image, VFS roots, devices, guest SEH on POSIX under the latch, the proposed
`RuntimeConfig::posix_seh` option, FPR/VMX/atomic/MMIO forms, multi-thread restart, non-`mov`
stores, POSIX async-signal-safety of raw `mprotect`, full XSTATE, non-glibc or non-x86-64 hosts,
and a game.
