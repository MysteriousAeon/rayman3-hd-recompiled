# Manifest-only EGL retry correction

This supersedes only toolkit extraction/application instructions in the EGL handoff.
No source archive, image recipe/lock, SDK source, backend or ABI acceptance change.
The original locked manifest hash authenticates the same bytes after allowing only
LF/CRLF line endings. No parsed-JSON or native-hash trust exception is used.

Copy `r3hd-egl-manifest-update.zip` and its `.sha256` sidecar to CachyOS Downloads.
First compare the ZIP SHA256 with the committed manifest-correction report. Then:

```bash
set -euo pipefail
cd "$HOME/Downloads"
sha256sum -c r3hd-egl-manifest-update.zip.sha256
UPDATE="$HOME/Downloads/r3hd-egl-manifest-update-01"
OLD_RUNNER="$HOME/Downloads/r3hd-stage2b-egl-01"
RUNNER="$HOME/Downloads/r3hd-stage2b-egl-manifest-01"
test ! -e "$UPDATE" && test ! -L "$UPDATE"
test ! -e "$RUNNER" && test ! -L "$RUNNER"
mkdir "$UPDATE"
python3 -B -m zipfile -e r3hd-egl-manifest-update.zip "$UPDATE"
(cd "$UPDATE" && sha256sum -c SHA256SUMS)
python3 -B "$UPDATE/manifest_update.py" apply --old "$OLD_RUNNER" --dest "$RUNNER"
python3 -B "$RUNNER/stage2b.py" check
chmod 755 "$RUNNER/clang" "$RUNNER/clang++"
python3 -B "$RUNNER/retry.py" previous "$HOME/Projects/R3HD-baseline-noble-2b-01"
```

Expected: every checksum OK; `R3HD_EGL_MANIFEST_UPDATE PASS`, toolkit PASS, then
`R3HD_EGL_PREVIOUS PASS`. These are static checks, not native SDK/image success.
Old toolkit must be the exact previous 45,352-byte transfer extraction; local edits,
unknown files/symlinks or mismatched manifest contents STOP before creating a clone.
Do not modify the old manifest to satisfy the checker or reformat/reseal the archive.

The reported failure occurred before any new task/image/container was created.
Retain the same intended native resource names, but explicitly check absence:

```bash
TASK="$HOME/Projects/R3HD-baseline-noble-2b-egl-01"
test ! -e "$TASK" && test ! -L "$TASK"
if podman image exists localhost/r3hd-noble-build:stage2b-egl-01; then
  echo 'STOP: image tag already exists'; false
else test "$?" -eq 1; fi
if podman container exists r3hd-noble-stage2b-egl-01; then
  echo 'STOP: container name already exists'; false
else test "$?" -eq 1; fi
if bash "$RUNNER/run_egl.sh"; then RESULT=0; else RESULT=$?; fi
printf 'EGL retry exit=%s\n' "$RESULT"
if test -f "$TASK/evidence/OWNER.txt"; then
  python3 -B "$RUNNER/collect_egl.py"
fi
test "$RESULT" -eq 0
```

Resource collision or any failure: STOP; preserve the new partial update/toolkit,
all old/new evidence, images/layers/caches and workspaces. Do not delete, rename,
overwrite, change dependency/source pins, relax gates or retry with another name.
If the failure precedes task creation, retain terminal output; otherwise return the
new private evidence ZIP and checksum produced by the collector. No Codex needed.
No host installation, game launch or publication. Do not execute `run_native.sh`.

Original `EGL_HANDOFF.md` in the new toolkit still describes the unchanged build,
>=50,000,000,000 free-byte/16,000,000,000 RAM gates, single-filesystem Podman checks,
CoW clone, cache/source validation and final acceptance. Use its final-result and
checksum checks after the command above, not its superseded extraction block.
Native image/Wayland/full game/ABI/LGPL/package success remains UNKNOWN until run.
