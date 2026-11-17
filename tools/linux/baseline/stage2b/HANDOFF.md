# Stage 2B private native build, then STOP

Prerequisites: native Stage2A expected19-01 PASS from the previous handoff, its exact
local image still present, and the unchanged original sealed kit in Downloads.
No host packages, image pulls, source pins or system settings are changed here.
Only a fresh sibling workspace and one named rootless container are created.
No game process, GPU, audio device, session socket or controller is used.

Copy `r3hd-stage2b-prep.zip` and its `.sha256` sidecar privately to `~/Downloads`.
Compare the ZIP hash with the committed research report/maintainer handoff before
extracting. The original 232 MB kit is reused in place; do not download/reseal it.

```bash
set -euo pipefail
cd "$HOME/Downloads"
sha256sum -c r3hd-stage2b-prep.zip.sha256
RUNNER="$HOME/Downloads/r3hd-stage2b-prep-01"
test ! -e "$RUNNER" && test ! -L "$RUNNER"
mkdir "$RUNNER"
python3 -B -m zipfile -e r3hd-stage2b-prep.zip "$RUNNER"
python3 -B "$RUNNER/stage2b.py" check
chmod 755 "$RUNNER/clang" "$RUNNER/clang++"
if bash "$RUNNER/run_native.sh"; then RESULT=0; else RESULT=$?; fi
printf 'Stage 2B command exit=%s\n' "$RESULT"
TASK="$HOME/Projects/R3HD-baseline-noble-2b-01"
if test -f "$TASK/evidence/OWNER.txt"; then
  python3 -B "$RUNNER/collect.py"
fi
test "$RESULT" -eq 0
```

Expected gates, in order:

1. Exact toolkit inventory/hashes PASS; fresh names only. Existing task/container stops.
2. Read-only preflight PASS; Stage2A exit0, both probe hashes, feature/compiler/GCC13
   evidence and immutable image ID rechecked. Image must be local Linux/amd64.
3. Actual Podman rootless/seccomp, overlay, namespaces and storage locations match
   preflight. Workspace, graphroot and image-copy temporary directory must share the
   one filesystem. Each path must have >=50,000,000,000 free bytes, counted once;
   >=70,000,000,000 preferred. RAM must have >=16,000,000,000 available bytes.
4. Original archive SHA and all21,719 members verified; fresh extraction and24 SDK
   Git pins/pristine worktrees/fsck PASS. After extraction, disk/preflight rerun.
5. Container has no network/devices/session mounts, no added capabilities, read-only
   root, UID/GID keep-id,4 build jobs,20 GB memory cap,2 GB temporary tmpfs.
   Locale C.UTF-8, UTC and SOURCE_DATE_EPOCH=1794146315 (sealed0414e72 commit time)
   fix build metadata inputs. Byte-identical full ELFs require a later clean repeat;
   this first rebuild does not establish that result.
6. Compiler shims select Clang19.1.1/GCC13 for **all** explicit clang invocations.
   Unchanged feature source42:42, SDK build/install and CPU host tests PASS.
7. Compiled SDL X11/Wayland/ALSA/Pulse/PipeWire backends present. Missing backend stops
   for review, not an automatic feature-disable workaround.
8. Existing Vulkan parity, vertex residency, actual synthetic Red upload, host-input
   freshness, portable package, launcher/settings/model/mods tests PASS. GUI/Turkish
   asset tests are skipped headlessly; those skips are not visual acceptance.
9. Complete sealed LM-A target builds without generation; gamesync stamp current.
   LGPL source package passes its own validation; plain and marker-modified source
   rebuilds and export/import replacement checks PASS.
10. Every five-component ELF and four replacement libraries meets GLIBC<=2.39 and
    GLIBCXX<=3.4.33. Save symbols/RPATH/interpreter/dependencies and Noble loader
    `--list` closure (including version checks); never execute r3hd's entrypoint.
    Absolute/unsupported packaged RPATH, GLIBC_PRIVATE, missing/extra dependency,
    missing symbols, stale host stamp or unknown SDK/source change stops.
11. Project and complete generated/host LM-A bytes remain sealed;24 pins unchanged;
    existing full patch replay matches the prepared source digest. Private portable
    package validates with its existing allowlists and `publishable:false` intact.
12. Final `R3HD_STAGE2B_NATIVE PASS (build/static package acceptance only); STOP`,
    exit0 and small private evidence ZIP emitted. No runtime/Deck acceptance claimed.

Budget: original kit775,527,036 uncompressed file bytes plus filesystem overhead;
roughly20–40 GB planning allowance for SDK/guest objects, debug line tables, installs,
LGPL repeats and private archives. Actual peak is UNKNOWN;50 GB free is the hard
gate and70 GB preferred. Existing Stage2A images/archives occupy space separately
and are retained. No new network downloads are needed. Expect tens of minutes to
hours;4 jobs limit pressure. Disk/RAM/build failures are stops, never cleanup prompts.

On failure: preserve everything. Return `stage2b-private-evidence.zip` and its sidecar
from the new task. If collection itself fails, return `evidence/exit-status.txt`,
`evidence/build.log` if present, extraction/preflight/engine logs and the relevant
SDK/game result/log. No automatic rerun/reset. A fresh attempt needs separately
reviewed new workspace/container/output names; this procedure refuses collisions.
Do not remove source files, change compiler flags/pins, disable a check or alter
renderer behavior to force progress. A major SDK/renderer change needs review.

No cleanup is needed. If the terminal is interrupted while the named container is
still running, inspect it first; these commands target only this task's new name:

```bash
podman container inspect r3hd-noble-stage2b-01
podman stop --time 30 r3hd-noble-stage2b-01
podman wait r3hd-noble-stage2b-01
```

Do not use prune/reset, delete shared caches/layers, stop compilers by name or remove
other containers/images. Keep original RaymanLM1/native_lma, LX2F/LX2RED installations,
Stage2A and this attempt intact. No paths outside the new task are mounted writable.

After success, verify retained deliverables without starting the game:

```bash
set -euo pipefail
TASK="$HOME/Projects/R3HD-baseline-noble-2b-01"
cd "$TASK/work/private/work/linux_build/noble_2b01"
sha256sum -c DELIVERABLES.sha256
python3 -B - <<'PY'
import json
from pathlib import Path
for name in ('results.json','results-game-lma.json','results-gamesync.json','abi.json','backends.json','acceptance.json'):
    assert json.loads(Path(name).read_text())['status']=='PASS',name
p=json.loads(Path('package-check.json').read_text())
assert p['result']=='PASS' and p['publishable'] is False
print('R3HD_STAGE2B_ACCEPT PASS: build/static package only; STOP')
PY
cd "$TASK"
sha256sum -c stage2b-private-evidence.zip.sha256
```

Keep both private binary package and matching LGPL source ZIP together locally.
Do not upload them, source inputs, profiles, saves, keys, translations or game data.
Actual game loading, visual corrections, Mods/Turkish behavior, sound/input, modified
LGPL marker execution and Steam Deck hardware/Game Mode are separate future human
acceptance work. This handoff authorizes none of those runs and publishes nothing.
