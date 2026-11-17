#!/usr/bin/env bash
set -euo pipefail
RUNNER=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
OLD="$HOME/Projects/R3HD-baseline-noble-2b-01"
TASK="$HOME/Projects/R3HD-baseline-noble-2b-egl-01"
STAGE2A="$HOME/Projects/R3HD-baseline-noble-01"
TAG='localhost/r3hd-noble-build:stage2b-egl-01'
NAME='r3hd-noble-stage2b-egl-01'
test "$(uname -s)" = Linux && test "$(id -u)" != 0
python3 -B "$RUNNER/stage2b.py" check
python3 -B "$RUNNER/retry.py" previous "$OLD"
test "$(realpath "$OLD")" = "$OLD"
test ! -e "$TASK" && test ! -L "$TASK"
if podman image exists "$TAG"; then echo 'STOP: image tag exists'; exit 2; else test "$?" -eq 1; fi
if podman container exists "$NAME"; then echo 'STOP: container name exists'; exit 2; else test "$?" -eq 1; fi
mkdir "$TASK"; mkdir "$TASK/evidence"
test "$(realpath "$TASK")" = "$TASK"
printf '%s\n' R3HD_STAGE2B_EGL_01 > "$TASK/evidence/OWNER.txt"
trap 'rc=$?; printf "%s\n" "$rc" > "$TASK/evidence/exit-status.txt"; if podman container exists "$NAME"; then podman inspect "$NAME" > "$TASK/evidence/container-final.json"; fi' EXIT
python3 -B "$RUNNER/preflight.py" | tee "$TASK/evidence/preflight.json"
podman info --format json > "$TASK/evidence/podman-info.json"
python3 -B "$RUNNER/stage2b.py" engine --task "$TASK"
python3 -B "$RUNNER/stage2b.py" evidence --old "$STAGE2A" > "$TASK/evidence/native-2a.txt"
BASE=$(tail -1 "$TASK/evidence/native-2a.txt")
[[ "$BASE" =~ ^sha256:[0-9a-f]{64}$ ]]
podman container inspect r3hd-noble-stage2b-01 > "$TASK/evidence/previous-container.json"
podman image inspect "$BASE" > "$TASK/evidence/parent-image.json"
python3 -B - "$TASK" "$BASE" <<'PY'
import json,sys
from pathlib import Path
p=Path(sys.argv[1]);x=json.loads((p/'evidence/previous-container.json').read_text())[0]
assert x['State']['Running'] is False and x['State']['ExitCode']==2
assert x['Image'].removeprefix('sha256:')==sys.argv[2].removeprefix('sha256:')
y=json.loads((p/'evidence/parent-image.json').read_text())[0]
assert y['Os']=='linux' and y['Architecture']=='amd64'
assert y['Id'].removeprefix('sha256:')==sys.argv[2].removeprefix('sha256:')
PY
cp "$OLD/evidence/verified-2a-packages.tsv" "$TASK/evidence/verified-2a-packages.tsv"
cmp "$TASK/evidence/verified-2a-packages.tsv" "$STAGE2A/evidence/expected19-01/probe/r3hd-packages.tsv"
cp "$RUNNER/BUNDLE.json" "$TASK/evidence/TOOLKIT.json"
cp "$RUNNER/EGL_LOCK.json" "$TASK/evidence/EGL_LOCK.json"
podman images --all --no-trunc --digests > "$TASK/evidence/images-before.txt"
mkdir "$TASK/image-context"
cp "$RUNNER/Containerfile" "$RUNNER/EGL_LOCK.json" "$RUNNER/image_guard.py" "$TASK/image-context/"
podman build --pull=never --no-cache --rm=false --build-arg BASE="$BASE" \
  --iidfile "$TASK/evidence/raw-image.id" --tag "$TAG" "$TASK/image-context" 2>&1 | tee "$TASK/evidence/image-build.log"
python3 -B - "$TASK" <<'PY'
import re,sys
from pathlib import Path
p=Path(sys.argv[1]);s=(p/'evidence/raw-image.id').read_text().strip()
assert re.fullmatch(r'(?:sha256:)?[0-9a-f]{64}',s)
with (p/'evidence/image.id').open('x') as f:f.write(s if s.startswith('sha256:') else 'sha256:'+s)
PY
IMAGE=$(cat "$TASK/evidence/image.id")
podman image inspect "$IMAGE" > "$TASK/evidence/image.json"
# CoW clone only; no hard links, fallback full copy, deletion, or mutation of the old task.
cp -a --reflink=always "$OLD/work" "$TASK/work"
cp "$OLD/KIT_MANIFEST.json" "$TASK/KIT_MANIFEST.json"
python3 -B "$RUNNER/preflight.py" | tee "$TASK/evidence/preflight-before-build.json"
python3 -B - "$TASK" <<'PY'
import json,shutil,sys
from pathlib import Path
t=Path(sys.argv[1]);j=json.loads((t/'evidence/podman-info.json').read_text())
for p in (t,Path(j['store']['graphRoot']),Path(j['store']['imageCopyTmpDir'])):
    free=shutil.disk_usage(p).free;print(str(p),free,'bytes free');assert free>=50_000_000_000
PY
podman run --rm=false --name "$NAME" --pull=never \
  --userns=keep-id --user "$(id -u):$(id -g)" --network=none --cap-drop=ALL \
  --security-opt=no-new-privileges --pids-limit=1024 --memory=20g --read-only \
  --tmpfs /tmp:rw,exec,size=2g --tmpfs /run:rw,size=64m \
  -e HOME=/tmp/r3hd-home -e PYTHONDONTWRITEBYTECODE=1 \
  --mount "type=bind,src=$TASK,dst=/task" --mount "type=bind,src=$RUNNER,dst=/runner,ro" \
  --workdir /task/work "$IMAGE" bash /runner/retry_inside.sh 2>&1 | tee "$TASK/evidence/build.log"
grep -Fx 'R3HD_STAGE2B_BUILD_PACKAGE PASS; STOP: no game execution or publication' "$TASK/evidence/build.log"
podman images --all --no-trunc --digests > "$TASK/evidence/images-after.txt"
printf 'R3HD_STAGE2B_EGL_RETRY PASS (build/static package only); STOP\n'
