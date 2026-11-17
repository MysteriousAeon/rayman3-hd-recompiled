# Isolated Linux guest-fault source package

**Status: source preparation; native execution UNKNOWN.** No game, production
runtime, generated code or SDK binary is used. See the
[evidence report](../../../reports/LINUX_GUEST_FAULT_2026-11.md).

## Copy only source

Keep these directories at the same relative paths in a local working folder:

- `tools/experiments/linux_guest_fault/` (this experiment).
- `tools/experiments/portable_guest_eh/` (unchanged synthetic emitter and runner).

Do not copy `private/`, generated title code or game data. No archive/publication
is made by this checkpoint; the maintainer can copy these tracked sources locally.
For the real PPCContext fixture, obtain pinned SDK/SIMDe headers separately using
the existing [dependency preparation instructions](../portable_guest_eh/LINUX.md#prepare-on-cachyos).
No SDK patch/build/install is necessary. The runner checks the pins and used headers.

## Native CachyOS x86-64 commands

Use installed Python, GCC, Clang and binutils. From the working folder root:

```sh
python3 tools/experiments/linux_guest_fault/run_matrix.py \
  --cxx clang++ --cxx g++ --repeats 20 \
  --out private/work/linux_guest_fault/native
python3 tools/experiments/linux_guest_fault/run_matrix.py \
  --portable-only --sanitize --cxx clang++ --cxx g++ --repeats 2 \
  --out private/work/linux_guest_fault/record_sanitizers
python3 tools/experiments/portable_guest_eh/run_native.py \
  --cxx clang++ --cxx g++ --repeats 2 --sanitize \
  --out private/work/linux_guest_fault/emitter_sanitizers
```

The fault matrix must report `LINUX_FAULT_MATRIX PASS scope=native-fixtures`.
The record-only matrix must report `scope=record-only`; that marker proves no
hardware recovery. The unchanged emitter must report `NATIVE_FIXTURE_MATRIX PASS`.
Each runner writes compiler versions, exact commands, OS/machine, hashes and
results under its output directory. The new runner leaves `status=INCOMPLETE`
and returns nonzero on an unexpected result. A failed build or unexpected signal
is a failure, never evidence of successful rejection.

Hardware recovery is intentionally **not** claimed sanitizer-validated. The new
sanitizer matrix covers the portable serialization/range model. The prior emitter
matrix covers ordinary C++ transport. Neither covers kernel signal-frame return.
No warning, sanitizer or optimizer suppression is used to make a test pass.

## Review machine code before accepting results

Inspect each compiler/O0/O2 `transport.o` and `access.o`:

```sh
objdump -dr private/work/linux_guest_fault/native/clang++_O2/transport.o
objdump -dr private/work/linux_guest_fault/native/clang++_O2/access.o
```

The runner's directory uses the resolved compiler executable's stem; use the
actual directory if different. The admitted handler path must have direct static
TLS access, with no `__tls_get_addr`, allocation, lazy binding, guest/C++ runtime or
unexpected helper calls. Terminal rejection may use the documented async-signal-safe
POSIX functions. The assembly access leaf must have its single whitelisted load,
status returns, no stack adjustment and no nonvolatile register writes. The output
store is not an admitted guest fault site. A standalone executable/static initial-exec
TLS result does not authorize dynamically loaded module TLS.

Return the three result JSON files and disassembly output for review. Check source
hashes against the checkpoint being tested; record local modifications rather than
silently reporting a different fixture as this checkpoint.

## Interpretation and stop conditions

The native matrix separately executes each deliberate crash mode in a subprocess.
It must distinguish expected default signals from controlled capture, test-thread
rejection and ordinary guest transfer. Test input is synthetic anonymous mappings.
Successful negative disposition means a **new checked helper call after repair**,
not arbitrary native instruction retry. Source code and expected statuses are test
specifications until actually compiled and executed on Linux.
Only aligned four-byte reads are admitted; stores, unaligned/cross-page accesses
and arbitrary generated instructions are outside the experiment. The independent
context target covers callee-saved GPRs/RSP/carry/red zone, x87 control/MXCSR and
XMM0/XMM15. Its known SIGUSR1 chain is a narrow same-signal stand-in. It does not
establish full register/XSTATE preservation or SDK chaining.

The adapter refuses an already-owned SIGSEGV action. The pre-access MMIO/watch
callback is an ordering stand-in, not a linked ReXGlue callback or instruction decoder.
Do not install this adapter in the production SDK. Stop on unexpected crashes,
TLS resolver/helper calls in admitted signal paths, state corruption, unrepaired
retry, duplicate memory side effects, wrong cleanup or memory-consumer suppression.
AVX/AVX-512/AMX/full XSTATE, ARM64 and actual SDK coexistence remain outside proof.

## Windows record model only

```text
cmd /c tools\devenv.bat python tools/experiments/linux_guest_fault/run_matrix.py --portable-only --cxx clang++ --repeats 2 --out private/work/linux_guest_fault/record_matrix
```

The native mode refuses Windows. This checkpoint did not retry denied WSL access
or install/change virtualization, security settings or development tools.
