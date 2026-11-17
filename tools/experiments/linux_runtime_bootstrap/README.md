# Linux Runtime Bootstrap (LRB)

**Status: CLOSED — bounded native PASS (2026-11-05).** Retry 2 (`a7e5128`) passed on CachyOS
and was independently audited. Isolated bootstrap only; see the limits below.
Milestone report:
[LINUX_RUNTIME_BOOTSTRAP_2026-11.md](../../../reports/LINUX_RUNTIME_BOOTSTRAP_2026-11.md).

An opt-in, isolated Linux x86-64 executable (`lrb_tests`) that brings up the **real**
pinned ReXGlue memory system under a project-owned signal owner. It contains no game
data and no generated game code, never launches the game and is not part of the
Windows build or release.

## What it exercises (real SDK `c94f5eb…`, not stand-ins)

| Component | Real SDK entry points |
|---|---|
| Memory lifecycle | `Memory::Memory`, `Memory::Initialize` (shm mapping, 9 views, 8 heaps, `MMIOHandler::Install`), `~Memory` (unmap, close, `shm_unlink`) |
| Translation / aliases | `TranslateVirtual`, `TranslatePhysical`, `GetPhysicalAddress`, `HostToGuestVirtual`, `LookupHeap`, heap layout |
| Signal handoff | `ExceptionHandler::Uninstall` of the exact `MMIOHandler` thunk; singleton and ranges retained |
| MMIO | `Memory::AddVirtualMappedRange`, `LookupVirtualMappedRange`, `MMIOHandler::CheckLoad/CheckStore` |
| Write watch | `PhysicalHeap::AllocFixed`, `Memory::EnablePhysicalMemoryAccessCallbacks`, `IsHostPageWriteWatched`, `RegisterPhysicalMemoryInvalidationCallback` |
| Deferred repair | `MMIOHandler::ExceptionCallback` → `Memory::AccessViolationCallback` → `PhysicalHeap::TriggerCallbacks` (ordinary code, after sigreturn) |
| Declined fault | Same path on a virtual-heap no-access page (`BaseHeap::Alloc`, `Release`) |
| Guest scratch | `Memory::SystemHeapAlloc` / `SystemHeapFree`, `BaseHeap::QueryRegionInfo` |
| Logging | `rex::InitLogging` with no console/file sink (keeps traced output exact) |

Files: `lrb_owner.{h,c}` + `lrb_access.S` (signal owner and checked 32-bit
transport, promoted unchanged in admission semantics from the audited
`linux_sdk_composition` transport), `lrb_bootstrap.{h,cpp}` (reusable bootstrap
module), `lrb_tests.cpp` (acceptance scenarios), `lrb_gate.py` (source transfer,
native gate, evidence, audit), `test_lrb_gate.py` (validator tests),
`access_census.py` / `CENSUS.md` (static generated-code census, Windows only).

## Safety contract

- **Signal ownership.** Snapshot SIGSEGV/SIGILL/SIGBUS (must be default) → real
  Initialize installs the SDK thunk → exact `Uninstall` restores the snapshot
  (verified flag/mask-exact) → the LRB owner installs only over SIG_DFL. The handler
  only flips `sig_atomic_t` flags, records words and rewrites RIP to a recovery
  label; no locks, allocation, page queries, logging or C++ EH. Everything else
  (unarmed thread, wrong address/site/direction, non-ACCERR, nested) restores SIG_DFL
  and raises: fail-closed. SDK consumers run only in ordinary code after sigreturn.
- **Checked-access recovery only.** One admitted fault per checked access, one
  deferred dispatch, at most one fresh access; a second fault is terminal. No
  instruction retry (the recovery label returns without re-executing). This is not
  general generated-code recovery.
- **Address space.** The pinned `MapViews` uses `MAP_FIXED` at 2^32 and cannot detect
  an existing mapping; LRB refuses unless `[2^32, 2^32+0x120000000)` is unmapped.
  The ~4.5 GiB reservation is virtual: the shm object is sparse (`st_blocks`), and
  RSS/allocated bytes are reported separately from `VmSize`.
- **Shared memory.** The SDK names its object `/xenia_memory_<CLOCK_MONOTONIC_RAW ns>`
  (`shm_open(O_CREAT)` without `O_EXCL`, unlinked only in `~Memory`). LRB derives the
  name from public `Memory::file_name()`, proves via `/proc/self/maps` that every view
  is a shared mapping of that exact inode at its pinned offset, and records name,
  device, inode, size and pid in an ownership file. Fatal modes unlink that proven
  name immediately after verification, so a crash leaves no residue. The runner
  removes a residue only after reaping its own child and only if name, inode,
  device and uid all match the child's record. It never lists-and-deletes, never
  touches other entries, and reports (never removes) unattributed new
  `xenia_memory_*` names. The `leak-probe` mode deliberately records the SDK's
  crash-leak behaviour once per configuration and then removes exactly that object.
- **Quiescence.** Exactly one participating thread, the main thread. The
  `/proc/self/task` set is captured before any SDK call. It must be {main} plus the
  one pre-`main` dispatcher thread of the pinned SDK's TimerQueue, and it must be
  unchanged after logging init, after `Initialize`, at the handoff and before
  `~Memory`.
  Teardown order: scratch release → detach → owner uninstall → `~Memory` → verify no
  view mapped, no `/dev/shm` name, default dispositions, no alternate stack.

## Windows checks (no native signal claim)

```text
python tools/experiments/linux_runtime_bootstrap/test_lrb_gate.py
python tools/experiments/linux_runtime_bootstrap/test_access_census.py
python tools/experiments/linux_runtime_bootstrap/access_census.py
```

The ordinary Windows build (`-DLRB_ORDINARY_ONLY=ON`, Clang O0/O2, existing Windows
SDK install) runs the real `Memory::Initialize` on Windows and the same scenarios
with synthetic (non-hardware) dispatch. Commands are in the milestone report.

## CachyOS procedure (one session)

Prerequisites already present: Python 3, CMake, Ninja, Clang, GCC, binutils, the
existing SDK checkout at `c94f5eb…` (SIMDe `71fd833…`) and its matching install
prefix. Nothing is fetched, built into the SDK, patched or installed. Close any
other ReXGlue/Rayman process first. Do not change ptrace or other security
settings; a refused trace is a recorded blocker.

```sh
# 1. Verify the transferred ZIP, then extract into a NEW empty directory.
sha256sum lrb-cachyos-source.zip          # compare with lrb-cachyos-source.zip.sha256
mkdir -p ~/Projects/RaymanLRB && cd ~/Projects/RaymanLRB
unzip -q /path/to/lrb-cachyos-source.zip
python3 - <<'PY'
import hashlib, json, pathlib
for name, expected in json.loads(pathlib.Path('SOURCE_MANIFEST.json').read_text()).items():
    assert hashlib.sha256(pathlib.Path(name).read_bytes()).hexdigest() == expected, name
print('SOURCE_MANIFEST PASS')
PY

# 2. Run the full gate (about 20-60 min; prior regressions included).
SDK=/home/<user>/Projects/RaymanTests/external/rexglue-sdk
PREFIX=/home/<user>/Projects/RaymanOwnership/sdk-install
OUT="$PWD/private/work/linux_runtime_bootstrap/native"
mkdir -p "$OUT"
python3 tools/experiments/linux_runtime_bootstrap/lrb_gate.py run \
  --sdk "$SDK" --prefix "$PREFIX" --out "$OUT" > "$OUT/console.log" 2>&1
echo "gate exit=$?"; tail -n 3 "$OUT/console.log"

# 3a. Only after "LRB_GATE PASS ..." (exit 0):
python3 tools/experiments/linux_runtime_bootstrap/lrb_gate.py evidence \
  --out "$OUT" --zip "$OUT/lrb-native-evidence.zip"
# 3b. Otherwise (any failure, refusal or timeout):
python3 tools/experiments/linux_runtime_bootstrap/lrb_gate.py evidence \
  --out "$OUT" --zip "$OUT/lrb-native-failure.zip" --failure
```

Expected success line:
`LRB_GATE PASS configurations=4 normal=80 traced=100 leak=4 prior=7; independent audit still required`.

The gate stops at the first failure: unexpected exit, fault, stop, output, residue,
ownership conflict, pin/header/source mismatch or prior-regression failure. Do not
rerun with weakened options; `--skip-prior` is diagnostic only and is not acceptance.

### What the run does

- Verifies the source manifest, SDK/SIMDe pins, pinned SDK source and installed
  header bytes, and hashes installed SDK libraries (identities, not rehashes).
- Builds Clang O0/O2 and GCC O0/O2 with `-Wall -Wextra -Werror`.
- Per configuration: 20 `normal` runs; 5 × each of the five fatal modes under `PTRACE_TRACEME`
  (nonce-bound witnesses, kernel siginfo at every stop, forwarded exact SIGSEGV,
  final real `-11`); 1 `leak-probe`; final ELF/object hashes; `objdump -drwC` of the
  ELF, owner, access and bootstrap objects; `readelf`.
- Runs prior regressions: SDK composition (20), lifecycle (20), guest integration
  (20) + sanitizers (2), fault (20) + record sanitizers (2), emitter Clang/GCC with
  sanitizers (20).

| Fatal mode | Ordinary witness phases | Kernel stops |
|---|---|---|
| `callback-failure` | `injected` (invalidator throws a private sentinel), `caught`, `terminal` | 1 SEGV_ACCERR, then same-process SI_TKILL |
| `repair-failure` | `claimed` (SDK consumed, page left read-only), `retry_fault`, `terminal` | 2 SEGV_ACCERR at one address, then SI_TKILL |
| `declined-unhandled` | `declined`, `recorded` (M4 record in owned guest scratch), `terminal` | 1 SEGV_ACCERR, then SI_TKILL |
| `unadmitted` | `begin` only (raw store; owner terminates in signal context) | 1 SEGV_ACCERR, then SI_TKILL |
| `wrong-site` | `begin` only (armed exact read, fault from a non-admitted instruction; `LRB_TEST` hook) | 1 SEGV_ACCERR, then SI_TKILL |

### Failure reporting

Every child's argv, `LRB_*` environment, return code, signal, stdout, stderr and
timeout are stored in `results.json` before validation. Each `LRB_GATE FAIL:` line
ends with those facts.

The child writes its ownership record twice, both times atomically:
- stage `initialized`, as soon as the SDK shm name and inode are known;
- stage `started`, after a complete start.

A missing, unreadable or foreign record is a FAIL. In that case the runner removes
nothing and only lists any newly appeared `xenia_memory_*` names. On the first
failing `normal` run, the runner also records one diagnostic rerun with SDK console
logging as `diagnostic` in that configuration.

### Retry after a failed run

Keep the old output. Extract the full replacement package over the existing
workspace; the whole-tree manifest proves the result. Then use a NEW output
directory. Do not delete any `/dev/shm` entry; report what is there.

```sh
cd /home/<user>/Projects/RaymanBootstrap
# Keep each earlier output (skip a line if that backup already exists).
tar -czf private/work/linux_runtime_bootstrap/native-failed-91485d7.tar.gz \
  -C private/work/linux_runtime_bootstrap native
tar -czf private/work/linux_runtime_bootstrap/native_retry1-failed-ad226a5.tar.gz \
  -C private/work/linux_runtime_bootstrap native_retry1
ls -l --time-style=full-iso /dev/shm | grep xenia_memory_ || echo "no xenia_memory objects"
unzip -o -q /path/to/lrb-cachyos-source-retry2.zip
# then the SOURCE_MANIFEST check above, and:
OUT="$PWD/private/work/linux_runtime_bootstrap/native_retry2"
```

## Return and audit

Return only the one evidence ZIP (or the failure ZIP) to Windows under
`tools/experiments/linux_runtime_bootstrap/`. It contains results, own ELF/object
bytes and text dumps, prior regression result JSON and hash manifests. It contains
no SDK libraries, game data, generated code, saves or profiles.

```text
python tools/experiments/linux_runtime_bootstrap/lrb_gate.py audit --archive tools/experiments/linux_runtime_bootstrap/lrb-native-evidence.zip --implementation FULL_40_CHARACTER_COMMIT
```

The audit is structural; root must still review the final-linked handler admission,
TLS (`%fs:` initial-exec, no `__tls_get_addr` on admitted paths), site/recovery labels,
terminal paths and witness placement outside signal context before any PASS claim.

## Not established by LRB

Native game execution, generated-code integration, arbitrary instruction retry,
unaligned/cross-page/vector/atomic checked accesses, read watches, guest-write
records, guest C++ EH or context editing, full XSTATE, whole-handler async-signal
safety, multi-thread coexistence, production signal coexistence, non-glibc/non-x86-64
POSIX, and any general POSIX compatibility claim.
