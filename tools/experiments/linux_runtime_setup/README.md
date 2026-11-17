# Linux Runtime Setup Ownership (LRSO)

**Status: implementation prepared; native result UNKNOWN** until returned CachyOS evidence is
independently audited. Report:
[LINUX_RUNTIME_SETUP_OWNERSHIP_2026-11.md](../../../reports/LINUX_RUNTIME_SETUP_OWNERSHIP_2026-11.md).

An opt-in, isolated Linux x86-64 experiment. It calls the **real** pinned
`rex::Runtime::Setup` in tool mode and records every signal disposition before and after each
ownership transition. It then checks whether the audited LRB signal owner and the LWR
write-watch restart compose with **runtime-owned** memory.

- No game data, no title, no generated code and no private input.
- No input, audio or graphics factory, no `kernel_init`, empty VFS roots.
- Not part of the Windows build or release. It changes no production, SDK or generated code.

## Variants (one subprocess per mode, never mixed in one process)

| Mode | What it establishes |
|---|---|
| `default` | Unchanged SDK initialization: which actions `Setup` installs (SEH on SIGBUS/SIGFPE, MMIO thunk on SIGSEGV/SIGILL), and what `Shutdown` leaves behind. Nothing faults; no owner is installed |
| `default-originals` | Removes only the MMIO thunk to reveal its saved "originals" (the SEH handler, not SIG_DFL). The LRB owner's own precondition then refuses with `EBUSY` |
| `latch` | **Experimental** D1(a). The SDK's own `rex::platform::g_seh_initialized` (found by `dlsym`; the executable defines no copy) is set before `Setup`. Then: unchanged LRB handoff, one LWR restart on a watched page of runtime-owned memory, owner removal, `Shutdown` and residue checks |
| `latch-cycles` | Three Setup/handoff/restart/Shutdown cycles in one process (the latch is set once) |
| `latch-traced-positive` | `latch` under ptrace: exactly one kernel `SEGV_ACCERR` stop |
| `latch-unregistered`, `latch-unauthorized`, `latch-consumed`, `latch-foreign-session` | Traced fatal negatives on the runtime-owned watched page. Each must die through the LRB owner |

The restart uses the audited LWR admission path unchanged. The store is the synthetic leaf
`lwr_leaf_store32` (`89 77 04`, a `mov` store), authorized as an explicitly synthetic code range,
exactly as the audited LWR probe does. Generated-code restart remains LWR's evidence, not LRSO's.

## Files

| File | Role |
|---|---|
| `lrso_tests.cpp` | The fixture: snapshots, the latch, `Runtime::Setup`, handoff, restart, teardown and records |
| `CMakeLists.txt` | Linux-only build against an existing installed SDK. It reuses `lrb_owner.c`, `lrb_access.S`, `lrb_bootstrap.cpp`, `lwr_restart.c` and `lwr_test_leaf.S` unchanged |
| `lrso_gate.py` | Pinned-source contract, source ZIP, native gate, evidence and audit |
| `test_lrso_gate.py` | Validator tests (Windows-runnable) |

## Windows (development host)

```text
python tools/experiments/linux_runtime_setup/test_lrso_gate.py
python tools/experiments/linux_runtime_setup/lrso_gate.py source-contract
python tools/experiments/linux_runtime_setup/lrso_gate.py source --zip private/work/linux_runtime_setup/lrso-cachyos-source.zip
```

There is no Windows build of the fixture: `Runtime::Setup` on Windows would not exercise POSIX
signal ownership. Windows tests cover the pinned-source contract and the validators only.

## CachyOS procedure

See the report's **CachyOS execution** section. The run uses the existing SDK checkout and
install prefix. Nothing is fetched, patched or installed.

## Not established

Generated-code restart under `rex::Runtime`, guest threads and `XThread`, `KernelState` module
launch, a title image, VFS roots, input/audio/graphics, a production SEH replacement, guest
`__try` semantics on POSIX once the latch is set, multi-thread restart, non-`mov` store forms,
POSIX async-signal-safety of raw `mprotect`, full XSTATE, non-glibc or non-x86-64 hosts, and a game.
