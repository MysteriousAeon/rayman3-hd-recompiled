# Focused terminal-reason evidence

**PREPARED, native execution UNKNOWN.** This resolves the diagnostic design, not
the open milestone verdict. The audited `6f81aa7` positive matrix remains valid
within its original limits. No game/runtime replacement or dependency changes.

## What changes

`TERMINAL_DIAGNOSTICS=ON` selects fixture-only ordinary C++ paths. It does not
change `transport.c`, `access.S`, Windows SEH, guest code or the installed SDK.
Default builds preserve the original positive tests and original fatal modes.

| Mode | Required ordinary evidence | Required kernel SIGSEGV stops |
|---|---|---|
| callback-failure | Actual invalidator emits `injected`, only its private sentinel is caught, `caught`, then `terminal`; one callback/invalidation, unchanged bytes | One SEGV_ACCERR, then same-process SI_TKILL |
| repair-failure | SDK claims repair with page still read-only; `claimed`; exactly one fresh fault at the same site/address/op, unchanged bytes, `retry_fault`, `terminal` | Two same-address SEGV_ACCERR stops, then same-process SI_TKILL |
| unhandled | One real CheckLoad decline, one capture/SDK decline, one filter returning search, typed Unhandled catch, no active finally execution; `filter_search`, `caught`, `terminal` | One SEGV_ACCERR, then same-process SI_TKILL |

The parent generates a per-run nonce and requires the exact three-line stderr
contract, counters and address. It checks trace position at every kernel stop,
forwards each intended SIGSEGV unchanged into the real handler, and requires final
real signal death (`-11`, never ordinary `exit(139)`). Extra faults, wrong sender,
missing/extra/partial trace bytes, unexpected output, ordinary exits or timeouts
fail. This closes the post-marker false-pass window of marker-only diagnostics.

All witness formatting, SDK callbacks, filters and catches run AFTER signal return
in ordinary code. The parent uses PTRACE_TRACEME/GETSIGINFO/CONT with EXITKILL on
its own synthetic child; it never reads/writes child memory or registers. It
requires the initial exec SIGTRAP and no unexpected signal/event. A denied trace
exits explicitly with an errno message; there is no untraced fallback or security
setting change. Failed/interrupted runs kill and reap only their own child.

This is Linux/glibc x86-64 siginfo ABI code and remains unverified until native
execution. SI_TKILL identifies the sender process, not independently its thread.
Single-thread/quiescent fixture execution remains a precondition. No arbitrary
third-party runtimes, loader/stack corruption, full XSTATE, sanitizer recovery or
performance conclusions are established. Ptrace changes scheduling; these are
diagnostics, not timings. Original canary/PLT safety limitations remain.

## Windows checks

`test_terminal_gate.py` tests synthetic records only, including a synchronous
fault after the terminal marker, wrong-origin signals, missing phases, wrong
counter/address/nonce, extra output and ordinary exit 139. `terminal_trace_tests.cpp`
tests the portable C++ witness at O0/O2; its output is cross-checked by the Python
parser. The ordinary installed-SDK O0/O2 regression remains separate. None is
represented as native signal execution.

## Source transfer

After committing the intended sources, from the Windows repository root:

```text
python tools/experiments/linux_sdk_composition/terminal_gate.py source
```

Output: `private/work/linux_sdk_composition/terminal-gate-source.zip`. The packager
requires source bytes to match Git HEAD, preserves relative paths, and reopens
the ZIP to verify all content/CRC/inventory. Thirteen source/document files plus
source manifest, exact commit identity and archive hash manifest are included.
No SDK, historical result archive, game data, generated code or binary is included.
Use the full commit in `IMPLEMENTATION_ID.json` as the expected implementation.

## Exact CachyOS run: four builds, twelve native processes

Extract the source ZIP into a NEW directory and change to that root. Existing
SDK source/prefix must match SDK `c94f5ebdcb3c9d1a460ca48e04f9758448f8d518`
and SIMDe `71fd833d9666141edcd1d3c109a80e228303d8d7`, with a compatible C++ ABI.
Use existing Clang/GCC, CMake, Ninja, Python 3 and binutils; no SDK build/install.

```sh
SDK=/absolute/path/to/existing/rexglue-sdk
PREFIX=/absolute/path/to/existing/sdk-install
OUT="$PWD/private/work/linux_sdk_composition/terminal_gate"
mkdir -p "$OUT"
python3 tools/experiments/linux_sdk_composition/terminal_gate.py run \
  --sdk "$SDK" --prefix "$PREFIX" --out "$OUT" > "$OUT/console.log" 2>&1
```

The runner verifies the source manifest, pinned source/header bytes (including
every SIMDe header), installed headers and library identities. It builds Clang
O0/O2 and GCC O0/O2 with strict warnings. Each binary executes exactly the three
named fatal modes once under the parent tracer. No normal/benchmark/full-matrix
rerun, sanitizer mode or game launch is requested. Common fixture preparation
checks still execute before each named mode. Do not suppress a warning or bypass
a refusal. On failure, stop and retain results; do not change security settings.

Successful collection (only after `TERMINAL_GATE PASS ... subprocesses=12`):

```sh
python3 tools/experiments/linux_sdk_composition/terminal_gate.py evidence \
  --out "$OUT" --zip "$OUT/terminal-gate-evidence.zip"
```

If setup/tracing/probes fail, collect a clearly INCOMPLETE bundle instead:

```sh
python3 tools/experiments/linux_sdk_composition/terminal_gate.py evidence \
  --out "$OUT" --zip "$OUT/terminal-gate-failure.zip" --failure
```

## Linux-to-Windows transfer and independent audit

Physically transfer the one evidence ZIP to Windows under
`tools/experiments/linux_sdk_composition/`, preserving the older archive. Nothing
is uploaded or published by these scripts. Successful evidence has 32 entries:
results with all 12 phase/kernel traces, source/commit identities, four synthetic
fixture ELFs, their eight transport/access objects, sixteen object/final text
dumps and a hash manifest. SDK libraries and game data are excluded. The own ELF
and object bytes permit independent rehash and fresh disassembly on Windows;
installed SDK library hashes remain recorded identities, not independent rehashes.

```text
python tools/experiments/linux_sdk_composition/terminal_gate.py audit --archive tools/experiments/linux_sdk_composition/terminal-gate-evidence.zip --implementation FULL_40_CHARACTER_COMMIT
```

This read-only audit checks source against the EXPECTED local Git commit, SDK
objects against pins, every archive/ELF/object digest, exact 4x3 records and kernel
provenance. Its PASS is structural evidence validation. Root must still inspect
the included final ELF/object control flow, witness locations after sigreturn,
exact site/recovery/TLS bindings, terminal call and unchanged handler semantics.
Only then may the milestone report/state be closed and a closure commit made.
The next production-oriented handoff stays inactive until that review succeeds.
