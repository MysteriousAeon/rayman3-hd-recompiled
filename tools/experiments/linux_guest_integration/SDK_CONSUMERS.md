# SDK memory-consumer boundary fixture

`sdk_consumers.cpp` links an **existing installed SDK**. It uses the real
`MMIOHandler` direct load/store methods and protected-page callback with
synthetic `Exception` objects. It allocates and protects synthetic pages using
the SDK's memory APIs and verifies protection with its `QueryProtect` before
entering the callback. Its small watch callback and top-level dispatcher are
explicit stand-ins. The fixture never accesses a game, window, audio, input,
physical device or profile.

The fixture calls the SDK's public `MMIOHandler::Install`, which registers the
SDK's own process exception handler. No additional handler or `seh_initialize`
is installed. A derived type exposes a protected pointer-to-member, invoked on
the actual SDK-owned base object without a downcast. Before leaving, the object
is destroyed while the mapping and its callback context are still alive. All
registration and destruction are single-threaded and quiescent.

The tests separate pre-access direct MMIO from post-fault dispatch, cover real
`CheckLoad`/`CheckStore` and callback dispatch, one
read-only-page synthetic write watch that repairs protection with SDK `Protect`,
unconsumed no-access-page read admission,
an outside-host rejection including an MMIO-like guest EA, wrong-site and the
SDK `kUnknown` operation (the enum has no separate execute value), and a
recursive-dispatch guard. An unconsumed synthetic fault goes through the new
record bridge into a live filter, with real PPCContext, writable scratch in the
SDK mapping, guest PC/read/EA fields and negative continuation checked. There is
no actual CPU fault, instruction decoding, `XMemory`/`PhysicalHeap` watch registration or process
signal chaining in this fixture. A passing run cannot establish those behaviors,
signal safety, or runtime coexistence. An already-repaired page also consumes
without invoking the watcher twice. The protected callback invokes the real
SDK page-query and lock path; its callback is a synthetic watcher.

## Run against an existing SDK

Windows, from the repository root with the existing toolchain and installation:

```text
cmd /c tools\devenv.bat python tools/experiments/linux_guest_integration/run_consumers.py --sdk external/rexglue-sdk --prefix external/rexglue-sdk/out/install/win-amd64 --cxx clang++ --repeats 2 --out private/work/linux_guest_integration/sdk_consumers_windows
```

CachyOS, from the transferred source root, using the existing pinned SDK source
checkout and its **already installed** matching SDK prefix:

```sh
SDK=/absolute/path/to/existing/rexglue-sdk
PREFIX=/absolute/path/to/existing/rexglue-sdk-install
python3 tools/experiments/linux_guest_integration/run_consumers.py --sdk "$SDK" --prefix "$PREFIX" --cxx clang++ --cxx g++ --repeats 2 --out private/work/linux_guest_integration/sdk_consumers_native
```

The SDK checkout must match the pinned commit and the checked MMIO source must be
unchanged. The prefix must already export `rex::runtime` through CMake's `rexglue` package,
its dependencies, and `lib/rexruntime` (platform naming applies). The script
does not fetch, configure, build, install or mutate the SDK. It checks SDK and
SIMDe Git pins; checks selected SDK source files for changes; checks the selected
installed SDK headers against their pinned source; records source/header and
installed library and SIMDe header hashes, compiler versions, exact CMake and verbose build
commands, executable hashes and outcomes in `results.json`. Installed library
hashes identify the tested artifacts but do **not** prove their source provenance.
SDK or toolchain incompatibility is a reported blocker, never a reason to change
the SDK or suppress warnings. Commands build only the new fixture in the chosen
output directory. Each successful executable prints `SDK_CONSUMERS PASS checks=`;
the matrix ends with `SDK_CONSUMER_MATRIX PASS`.
