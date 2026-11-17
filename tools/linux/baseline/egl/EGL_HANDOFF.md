# EGL-only derived image and Stage 2B retry

Use these commands only after copying `r3hd-stage2b-egl.zip` and its SHA256 sidecar
to CachyOS Downloads. Compare the hash with the committed EGL report first. Use
this handoff, not the older HANDOFF.md retained inside the toolkit as evidence.

```bash
set -euo pipefail
cd "$HOME/Downloads"
sha256sum -c r3hd-stage2b-egl.zip.sha256
RUNNER="$HOME/Downloads/r3hd-stage2b-egl-01"
test ! -e "$RUNNER" && test ! -L "$RUNNER"
mkdir "$RUNNER"
python3 -B -m zipfile -e r3hd-stage2b-egl.zip "$RUNNER"
python3 -B "$RUNNER/stage2b.py" check
chmod 755 "$RUNNER/clang" "$RUNNER/clang++"
if bash "$RUNNER/run_egl.sh"; then RESULT=0; else RESULT=$?; fi
printf 'EGL retry exit=%s\n' "$RESULT"
TASK="$HOME/Projects/R3HD-baseline-noble-2b-egl-01"
if test -f "$TASK/evidence/OWNER.txt"; then
  python3 -B "$RUNNER/collect_egl.py"
fi
test "$RESULT" -eq 0
```

Required existing inputs: Stage2A expected19-01 evidence/local image, stopped
`r3hd-noble-stage2b-01` container, failed `R3HD-baseline-noble-2b-01` workspace
with exit2 and SDK configure/build/install/CPU tests PASS. Prior toolkit and kit
manifest hashes must match. No previous game-build directory may exist.

New resources: workspace `~/Projects/R3HD-baseline-noble-2b-egl-01`, image tag
`localhost/r3hd-noble-build:stage2b-egl-01`, container
`r3hd-noble-stage2b-egl-01`. Any collision stops without overwriting/removing it.

The original read-only preflight and actual Podman storage/security checks remain:
one suitable filesystem, >=50,000,000,000 free bytes (70,000,000,000 preferred),
>=16,000,000,000 available RAM bytes, rootless overlay, seccomp and namespace mappings.
Disk checks repeat after the clone. No host package installation or storage relocation.

Image build uses only the previously verified immutable Clang19 image ID; no base
pull. Its Ubuntu-signed fixed snapshot and HTTPS checks remain unchanged. Only
`libegl-dev=1.7.0-1build1` is requested with no recommendations. Its normal dependencies
include Mesa/GLVND runtime libraries and libLLVM20 (a Mesa dependency, not a compiler
upgrade). The permitted transaction is locked. Existing package versions/architectures
must all remain present and unchanged; unexpected additions stop image creation.
No driver integration, GPU test or arbitrary trust/certificate change occurs.

Plan for up to42,588,338 bytes of additional package downloads in the predicted
closure (actual native closure may reuse more packages), plus APT indexes and roughly
hundreds of MB of image storage. Keep the 50GB workspace margin for rebuilt objects,
later game/LGPL/package outputs. No full image/source archive transfer is needed.

The old work tree is cloned with `cp -a --reflink=always`, preserving timestamps and
using CoW, not hard links. Unsupported reflink stops; no automatic full-copy fallback.
Only the new clone is writable in the container. Same `/task/work` and `/runner`
paths, exact source/24 pins/patch digest, compiler shims, generator and build flags
are required before cache reuse. Any mismatch stops for review, not cache deletion.
This is an incremental retry of the prior clean SDK build; it is not an independent
second clean build or evidence of byte reproducibility.

Only cached negative PC_WAYLAND pkg-config results are invalidated. CMake configures
the existing preset, builds the complete original Release target list through Ninja
dependencies, reinstalls, and reruns CPU host checks. Prior results/logs/feature files
are backed up inside the new clone's `noble_2b01/before-egl` directory. The actual
compiled Release SDL backend gate remains unchanged and must require Wayland ON
along with Vulkan/X11/ALSA/PulseAudio/PipeWire. KMSDRM/libthai are optional and their
development packages are not requested. No feature/API/renderer/source-pin changes.

After that gate, the exact hash-locked original Stage2B build/acceptance tail runs:
Vulkan and host regressions, full sealed LM-A build, freshness stamp, LGPL source
and plain/modified rebuild checks, all-five ABI ceilings/loader checks, private
package integrity and binding to audited ELF/source hashes. No game entrypoint runs.

Success requires `R3HD_STAGE2B_EGL_RETRY PASS (build/static package only); STOP` and
exit0. Verify the deliverables and return only the small private evidence ZIP:

```bash
set -euo pipefail
TASK="$HOME/Projects/R3HD-baseline-noble-2b-egl-01"
cd "$TASK/work/private/work/linux_build/noble_2b01"
sha256sum -c DELIVERABLES.sha256
python3 -B - <<'PY'
import json
from pathlib import Path
for name in ('results.json','results-game-lma.json','results-gamesync.json','abi.json','backends.json','acceptance.json'):
    assert json.loads(Path(name).read_text())['status']=='PASS',name
p=json.loads(Path('package-check.json').read_text())
assert p['result']=='PASS' and p['publishable'] is False
print('R3HD_EGL_STATIC_ACCEPT PASS; STOP before all game/runtime testing')
PY
cd "$TASK"
sha256sum -c stage2b-private-evidence.zip.sha256
```

Failure: keep all artifacts and return the new evidence ZIP/sidecar. If collection
fails, return new evidence/exit-status.txt, image-build.log, build.log, preflights
and sdk-egl.log/results. Do not rerun into the same names, prune, reset, clean caches,
change pins, disable Wayland/ABI/LGPL gates, or modify the old workspace. No cleanup
is necessary. If interrupted, inspect and stop only this task's new container:

```bash
podman container inspect r3hd-noble-stage2b-egl-01
podman stop --time 30 r3hd-noble-stage2b-egl-01
podman wait r3hd-noble-stage2b-egl-01
```

Preserve old images, intermediates, evidence, sealed inputs and known-good homes.
Keep the new private binary and LGPL source archives together locally; publish
nothing. Native image/Wayland/build/package success remains unverified until rerun.
