# Native synthetic exception test package

This package uses synthetic guest state only. It does not run the game, patch the SDK,
install a signal handler, touch game data or link the production runtime. It uses the
actual `PPCContext` / FPSCR header from pinned ReXGlue and the pinned SIMDe headers.
This milestone's adapter and runner explicitly accept Windows/Linux x86-64 only.
ARM64 requires separate FPCR/FPSR tests and is rejected rather than assumed equivalent.
The normal product build patches other SDK files; the runner rejects modifications to
the specific SDK include closure it uses and rejects changed SIMDe headers.

## Prepare on CachyOS

Install the standard tools (the command may ask for your normal system password):

```sh
sudo pacman -S --needed base-devel clang python git
```

Package references: [Arch Clang](https://archlinux.org/packages/extra/x86_64/clang/)
and [Arch GCC](https://archlinux.org/packages/core/x86_64/gcc/). The runner records
the versions actually installed; these instructions do not pin CachyOS package versions.

Copy `tools/experiments/portable_guest_eh/` from the completed experimental
milestone into a working folder, preserving that path. Alternatively check out the
exact milestone commit in a clone of the repository. No files from `private/`,
`generated/` or a game installation are needed. From that working folder:

```sh
mkdir -p external
git clone --no-checkout https://github.com/rexglue/rexglue-sdk.git external/rexglue-sdk
git -C external/rexglue-sdk checkout --detach c94f5ebdcb3c9d1a460ca48e04f9758448f8d518
git -C external/rexglue-sdk submodule update --init thirdparty/simde
```

The runner checks ReXGlue HEAD and the SIMDe submodule HEAD against
`c94f5ebdcb3c9d1a460ca48e04f9758448f8d518` and
`71fd833d9666141edcd1d3c109a80e228303d8d7`, respectively. It does not download
or change these dependencies.

## Run on native x86-64 Linux

```sh
python3 tools/experiments/portable_guest_eh/run_native.py \
  --sdk external/rexglue-sdk --cxx clang++ --cxx g++ --repeats 20 --bench
python3 tools/experiments/portable_guest_eh/run_native.py \
  --sdk external/rexglue-sdk --cxx clang++ --cxx g++ --repeats 2 --sanitize \
  --out private/work/portable_guest_eh/native_sanitizers
```

Both commands use C++23, exceptions, precise floating point and pthreads. Each
compiler runs unoptimized and optimized test executables, plus an independently
built shared object for the cross-module transfer case. The sanitizer command also
runs ASan/UBSan. The fixture intentionally executes a `noexcept` barrier in a
child process; exit 86 means its terminate handler was reached as expected. Any
other exit is a failure. A second child returns 87 after reproducing an intentionally
swallowed transfer; that is a known incompatible barrier, not successful guest handling.
The library destructor counter proves actual unwinding inside the DSO at both optimization levels.
The second command uses a separate output directory so it
does not overwrite the first command's results.

Expected final lines include `NATIVE_FIXTURE_MATRIX PASS`; individual probe results
and compiler versions, source hashes and exact commands are in each output folder's
`results.json`. Share those JSON files and the console output for review. Treat the
benchmark as a synthetic microbenchmark only. A result is native Linux evidence only
when actually executed on Linux; Windows results do not supply it.

## Run on the existing Windows development machine

From the repository root, under the existing SDK and toolchain:

```text
cmd /c tools\devenv.bat python tools/experiments/portable_guest_eh/run_native.py --cxx clang++ --repeats 20 --bench
```

`--out PATH` selects a separate output directory. The default is
`private/work/portable_guest_eh/native` under the working folder. The runner needs
no administrator privileges and writes no dependency or production source files.
The actual architecture and test status must be taken from the result and report,
not inferred from the existence of these instructions.

`--sanitize` on Windows additionally attempts ASan (Linux retains combined ASan/UBSan).
The runner adds the installed Clang runtime directory to the child process PATH;
it does not install or copy runtime DLLs. On this host, the adapter passes ASan, but
the full emitter aborts in the MSVC exception unwinder with both the pre-fix and
corrected source. This remains a failing configuration, not a sanitizer PASS.
See the alignment-correction section of the investigation report. No warning or
sanitizer suppression is applied. Use a separate `--out` folder for sanitizer runs.

## Scope of the adapter

`Adapter::capture_owner` calls the actual SDK `SaveNonVolatiles` and saves
r1/r2/r13; `restore_owner` calls `RestoreNonVolatiles`. That method restores
the guest-owned FPSCR bits while retaining current host-owned CSR bits.
`capture_full` additionally captures the full host C floating-point environment
and actual CSR. Its rollback is deliberately stronger than M4's guest-bit merge:
it models an isolated funclet's complete host environment, and does not claim that
Windows M4 uses the same policy. This does not establish ARM64 FPCR/FPSR behavior,
guest memory exception-record serialization, a native fault bridge or guest C++ EH.
