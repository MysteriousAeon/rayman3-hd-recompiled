#!/usr/bin/env bash
# Run only on CachyOS, after the toolkit and original sealed kit are present.
set -euo pipefail
RUNNER=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
OLD="$HOME/Projects/R3HD-baseline-noble-01"
TASK="$HOME/Projects/R3HD-baseline-noble-2b-01"
ARCHIVE="$HOME/Downloads/r3hd-baseline-2a/r3hd-baseline-2a.tar.gz"
NAME='r3hd-noble-stage2b-01'
test "$(uname -s)" = Linux
test "$(id -u)" != 0
python3 -B "$RUNNER/stage2b.py" check
test ! -e "$TASK" && test ! -L "$TASK"
test -f "$ARCHIVE" && test ! -L "$ARCHIVE"
if podman container exists "$NAME"; then echo 'STOP: container name exists'; exit 2; else test "$?" -eq 1; fi
mkdir "$TASK"
test "$(realpath "$TASK")" = "$TASK"
mkdir "$TASK/evidence"
printf '%s\n' 'R3HD_STAGE2B_01' > "$TASK/evidence/OWNER.txt"
trap 'rc=$?; printf "%s\n" "$rc" > "$TASK/evidence/exit-status.txt"; if podman container exists "$NAME"; then podman container inspect "$NAME" > "$TASK/evidence/container-final.json"; fi' EXIT
python3 -B "$RUNNER/preflight.py" | tee "$TASK/evidence/preflight.json"
python3 -B "$RUNNER/stage2b.py" evidence --old "$OLD" > "$TASK/evidence/native-2a.txt"
cp "$OLD/evidence/expected19-01/probe/r3hd-packages.tsv" "$TASK/evidence/verified-2a-packages.tsv"
cp "$RUNNER/BUNDLE.json" "$TASK/evidence/TOOLKIT.json"
cp "$RUNNER/SDK_REPLAY.json" "$TASK/evidence/SDK_REPLAY.json"
IMAGE_ID=$(tail -1 "$TASK/evidence/native-2a.txt")
[[ "$IMAGE_ID" =~ ^sha256:[0-9a-f]{64}$ ]]
podman info --format json > "$TASK/evidence/podman-info.json"
python3 -B "$RUNNER/stage2b.py" engine --task "$TASK"
podman image inspect "$IMAGE_ID" > "$TASK/evidence/image.json"
python3 -B - "$TASK/evidence/image.json" "$IMAGE_ID" <<'PY'
import json, sys
x=json.load(open(sys.argv[1]))[0]
assert x['Os']=='linux' and x['Architecture']=='amd64'
assert x['Id'].removeprefix('sha256:')==sys.argv[2].removeprefix('sha256:')
PY
podman images --all --no-trunc --digests > "$TASK/evidence/images-before.txt"
podman ps --all --no-trunc > "$TASK/evidence/containers-before.txt"
python3 -B "$RUNNER/stage2b.py" extract --task "$TASK" --archive "$ARCHIVE" \
  2>&1 | tee "$TASK/evidence/extract.log"
python3 -B "$RUNNER/preflight.py" | tee "$TASK/evidence/preflight-before-build.json"
# Recheck actual storage budget after extraction; no storage relocation or cleanup.
python3 -B - "$TASK" <<'PY'
import json,shutil,sys
from pathlib import Path
t=Path(sys.argv[1]);j=json.loads((t/'evidence/podman-info.json').read_text())
for p in (t,Path(j['store']['graphRoot']),Path(j['store']['imageCopyTmpDir'])):
    free=shutil.disk_usage(p).free
    print(str(p),free,'bytes free')
    assert free>=50_000_000_000
PY
podman run --rm=false --name "$NAME" --pull=never \
  --userns=keep-id --user "$(id -u):$(id -g)" \
  --network=none --cap-drop=ALL --security-opt=no-new-privileges \
  --pids-limit=1024 --memory=20g --read-only \
  --tmpfs /tmp:rw,exec,size=2g --tmpfs /run:rw,size=64m \
  -e HOME=/tmp/r3hd-home -e PYTHONDONTWRITEBYTECODE=1 \
  --mount "type=bind,src=$TASK,dst=/task" \
  --mount "type=bind,src=$RUNNER,dst=/runner,ro" \
  --workdir /task/work "$IMAGE_ID" bash /runner/build_inside.sh \
  2>&1 | tee "$TASK/evidence/build.log"
grep -Fx 'R3HD_STAGE2B_BUILD_PACKAGE PASS; STOP: no game execution or publication' "$TASK/evidence/build.log"
podman container inspect "$NAME" > "$TASK/evidence/container.json"
podman images --all --no-trunc --digests > "$TASK/evidence/images-after.txt"
printf 'R3HD_STAGE2B_NATIVE PASS (build/static package acceptance only); STOP\n'
