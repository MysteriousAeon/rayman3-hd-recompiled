# Isolated checked-access / guest-record integration

This fixture uses synthetic memory and real pinned SDK `PPCContext` headers.
It does not execute game code, patch dependencies, change Windows SEH, or build a
production runtime. See [the report](../../../reports/LINUX_GUEST_INTEGRATION_2026-11.md)
for actual results and the separate SDK consumer evidence boundary.
See [SDK_CONSUMERS.md](SDK_CONSUMERS.md) for the real SDK component fixture;
it uses the existing installed SDK prefix and remains separate from hardware recovery.

## Windows preparation

From the repository root, with the existing toolchain:

```text
cmd /c tools\devenv.bat python tools/experiments/linux_guest_integration/run.py --portable-only --cxx clang++ --repeats 2 --bench --out private/work/linux_guest_integration/windows
python tools/experiments/linux_guest_integration/package.py
```

`package.py` writes only an allowlisted source/report ZIP under `private/work/`,
re-opens it, checks CRCs, exact inventory and every LF-normalized source hash.
It includes a `SOURCE_MANIFEST.json`; no SDK, binaries, game data or Git history.
This is a local transfer package, not a release or public upload.

## CachyOS transfer and execution

Extract the ZIP into a fresh working directory, preserving `tools/experiments/`
and `reports/`. Use the **existing pinned SDK checkout** on CachyOS; do not copy
SDK sources into the ZIP or install a replacement. Set its absolute path:

```sh
SDK=/absolute/path/to/existing/rexglue-sdk
python3 - <<'PY'
import hashlib, json
from pathlib import Path
manifest = json.loads(Path('SOURCE_MANIFEST.json').read_text())
for name, expected in manifest.items():
    assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == expected, name
print('TRANSFER_SOURCE PASS', len(manifest))
PY
python3 tools/experiments/linux_guest_integration/run.py --sdk "$SDK" --cxx clang++ --cxx g++ --repeats 20 --bench --out private/work/linux_guest_integration/native
python3 tools/experiments/linux_guest_integration/run.py --sdk "$SDK" --portable-only --sanitize --cxx clang++ --cxx g++ --repeats 2 --out private/work/linux_guest_integration/sanitizers
python3 tools/experiments/linux_guest_fault/run_matrix.py --sdk "$SDK" --cxx clang++ --cxx g++ --repeats 20 --out private/work/linux_guest_integration/fault_regression
python3 tools/experiments/linux_guest_fault/run_matrix.py --sdk "$SDK" --portable-only --sanitize --cxx clang++ --cxx g++ --repeats 2 --out private/work/linux_guest_integration/record_sanitizers
python3 tools/experiments/portable_guest_eh/run_native.py --sdk "$SDK" --cxx clang++ --cxx g++ --repeats 2 --sanitize --out private/work/linux_guest_integration/emitter_regression
```

Use already available Clang, GCC, Python and binutils. No WSL access or system
security/virtualization changes are needed. The runners refuse pin/header drift;
their result JSON records actual OS/compiler versions, flags, hashes and outcomes.
The integration sanitizer matrix excludes native signal recovery; no sanitizer
claim should be made for the hardware path. The previous fault runner handles
deliberate crashes as independent subprocesses with exact expected signals.

For each compiler/O0/O2 build inspect both object **and final ELF** code:

```sh
for d in private/work/linux_guest_integration/native/*_O*; do
  objdump -dr "$d/transport.o" > "$d/transport.disassembly.txt"
  objdump -dr "$d/access.o" > "$d/access.disassembly.txt"
  objdump -d "$d/native_bridge" > "$d/final.disassembly.txt"
  readelf -Ws -r "$d/native_bridge" > "$d/final.symbols-relocations.txt"
done
```

Audit admitted signal paths for direct TLS, exact load/recovery binding, no TLS
resolver/allocation/guest dispatch/throw, and no unexpected helper call. Final
linked inspection is required for this new fixture, even though transport source
is unchanged. Return JSON records plus these text dumps for review. Do not send
SDK binaries or private game data. Benchmark JSON is synthetic ns/operation,
including the named fixture work; process wall times are not access costs.

Stop on unexpected crashes, state corruption, lost cleanup, duplicate effects,
scratch write faults, recursive dispatch, or consumed faults reaching filters.
Only aligned four-byte reads and explicit fresh-call retry after repair are in
scope. Actual SDK signal coexistence, complete memory coverage and production
Linux readiness require additional gates described in the report.
