# Native SDK consumers and exclusive POSIX signal owner

**Bounded PASS.** The positive real SDK component/lifecycle records and object/final-ELF
admission text were audited at implementation `6f81aa7`. The terminal-reason gate
(callback-failure, repair-failure and unhandled) closed at `5e914a8`, after native
traced evidence and an independent Windows audit. No game data or game executable
is used. See the [report](../../../reports/LINUX_SDK_COMPOSITION_2026-11.md) and
[lifecycle details](LIFECYCLE.md).

The [terminal-reason instructions](TERMINAL_GATE.md) are the transferred source
identity at `5e914a8`. They are kept unchanged so that the source manifest still matches.

On Windows, audit the original transferred evidence without executing its commands:

```text
python tools/experiments/linux_sdk_composition/audit_evidence.py --archive tools/experiments/linux_sdk_composition/linux-sdk-composition-evidence.zip
```

The auditor's PASS concerns record/source integrity, not full milestone acceptance.
The report identifies the missing three branch proofs and a targeted 12-subprocess
follow-up; no entire new matrix is requested. Original executables/libraries were
not transferred, so their hashes are recorded identities, not independent rehashes.

The process owns its synthetic mappings and callback storage. Registration and
handoff happen before worker threads; teardown follows detach/join. No concurrent
signal registrars, unmapping, protection writers or callback registration are
supported. SDK locks/page queries/callbacks run only in ordinary code after
signal return. Direct MMIO completes before any checked access. A write helper
exists only to test write-watch repair; guest exception admission remains read-only.

The SDK's signal callback is explicitly detached using its exact registered
thunk before the experimental owner is installed. This is a controlled ownership
handoff, not simultaneous installation of competing handlers. No `seh_initialize`.
Real MMIO and standalone PhysicalHeap components are used; the tiny heap is not
the SDK's complete Memory.Initialize/physical-alias lifecycle.

## Original CachyOS reproduction (use the 6f81aa7 source package)

Use already available Python 3, CMake, Ninja, Clang, GCC and binutils. The SDK
checkout and matching installed SDK prefix must already exist. These scripts
never fetch, patch, build or install the SDK. A missing SDK or exported symbol is
a blocker to record, not permission to modify a dependency.
The prefix and fixture must use a compatible C++ standard-library/unwind ABI;
successful linkage alone does not prove compatibility between mixed runtimes.

Required commits:

- SDK: `c94f5ebdcb3c9d1a460ca48e04f9758448f8d518`
- SIMDe: `71fd833d9666141edcd1d3c109a80e228303d8d7`

Extract the source-only ZIP into a new directory, preserving paths. From that root:

```sh
SDK=/absolute/path/to/existing/rexglue-sdk
PREFIX=/absolute/path/to/existing/rexglue-sdk-install
python3 - <<'PY'
import hashlib, json, pathlib
for name, expected in json.loads(pathlib.Path('SOURCE_MANIFEST.json').read_text()).items():
    assert hashlib.sha256(pathlib.Path(name).read_bytes()).hexdigest() == expected, name
print('SOURCE_MANIFEST PASS')
PY
python3 tools/experiments/linux_sdk_composition/run_lifecycle.py --help
python3 tools/experiments/linux_sdk_composition/run_lifecycle.py --repeats 20 --bench --out private/work/linux_sdk_composition/lifecycle
python3 tools/experiments/linux_sdk_composition/run.py --sdk "$SDK" --prefix "$PREFIX" --repeats 20 --bench --out private/work/linux_sdk_composition/native
```

Consult `run_lifecycle.py --help` / LIFECYCLE.md for its separate ordinary-only
sanitizer mode. ASan may own SIGSEGV: signal-owner conflict refusal remains required.
Sanitizer results cover fixture ordinary paths only, not the installed SDK internals
or kernel signal-frame recovery. The SDK composition itself is not run with ASan:
SDK Install would replace its handler before the controlled handoff. Use the
ordinary bridge sanitizers below instead of weakening ownership refusal.

Preserve previous regressions, separately from the new result set:

```sh
python3 tools/experiments/linux_guest_integration/run.py --sdk "$SDK" --repeats 20 --out private/work/linux_sdk_composition/prior_native
python3 tools/experiments/linux_guest_integration/run.py --sdk "$SDK" --portable-only --sanitize --repeats 2 --out private/work/linux_sdk_composition/prior_sanitizers
python3 tools/experiments/linux_guest_fault/run_matrix.py --sdk "$SDK" --repeats 20 --out private/work/linux_sdk_composition/prior_fault
python3 tools/experiments/linux_guest_fault/run_matrix.py --sdk "$SDK" --portable-only --sanitize --repeats 2 --out private/work/linux_sdk_composition/prior_record_sanitizers
python3 tools/experiments/portable_guest_eh/run_native.py --sdk "$SDK" --cxx clang++ --cxx g++ --sanitize --repeats 20 --out private/work/linux_sdk_composition/prior_emitter
```

Stop on an unexpected crash, timeout, repeated fault, lost cleanup, duplicate
callback/store, incorrect output, ownership conflict or failed protection query.
Do not disable strict warnings or bypass pin checks. Fatal tests run in separate
subprocesses; only an actual expected terminating signal passes, never an exit
code with the same numeric value. No native game launch follows these tests.

## Machine-code review and returned evidence

The runners retain commands, versions, sources/header/library/executable hashes,
statuses and dumps under their selected private outputs. Installed library hashes
identify artifacts, but do not prove how a prebuilt SDK was compiled. Return exact
missing-symbol/configuration logs if linkage fails. Do not send SDK libraries.

For every Clang/GCC O0/O2 configuration, inspect objects **and final ELF**:

```sh
find private/work/linux_sdk_composition -name '*.o' -print
# For each transport/access object and final executable:
objdump -drwC /path/to/object-or-executable > /path/to/dump.txt
readelf -Wr -Ws -Wl /path/to/final-executable > /path/to/elf.txt
sha256sum /path/to/final-executable > /path/to/executable.sha256
```

Verify exact read/store fault sites and recovery labels; normal admitted-return
branches, with an intact owned alternate stack/canary,
must reach no decoder, SDK callback, lock, allocator, logging, C++ EH, memcpy helper
or TLS resolver. Only local call-free admission helpers are permitted at O0.
Confirm direct initial-exec/local-exec TLS in the linked image, no dynamic TLS
resolver on admitted paths, and no accidental instruction between a completed
store and success reporting that could cause replay. Review terminal branches
separately (async-signal-safe signal-policy operations only). Kernel restoration
keeps its own FP/XSTATE frame; complete XSTATE preservation is not inferred.

Return result JSON and object/final-ELF text dumps associated with those hashes.
Do not include game data, SDK binaries, generated game code, saves or profiles.
Do not treat a matrix PASS as completion of the manual ELF review.

## Local package

```text
python tools/experiments/linux_sdk_composition/package.py
```

This writes and reopens `private/work/linux_sdk_composition/cachyos-source.zip`,
checks its exact inventory/content, and writes a verification JSON. It includes
only allowlisted experiment sources and reports; the SDK remains external.
