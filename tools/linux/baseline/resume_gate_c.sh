#!/usr/bin/env bash
# Run only on native CachyOS after applying the checked recipe update. No SDK/game/probe.
set -euo pipefail
TASK="$HOME/Projects/R3HD-baseline-noble-01"
TRANSFER="$HOME/Downloads/r3hd-baseline-2a"
UPDATE_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
BASE='docker.io/library/ubuntu@sha256:78d4744ead1f5b19b04d0df558ab182a5300903900755e515b2ca4d10eb2044d'
TAG='localhost/r3hd-noble-build:stage2a-comments-01'
OUT="$TASK/evidence/gate-c-comments-01"
test "$(uname -s)" = Linux
test "$(id -u)" != 0
python3 -B "$UPDATE_DIR/apply_update.py" check --task "$TASK"
test ! -e "$OUT"
test ! -L "$OUT"
mkdir "$OUT"
trap 'rc=$?; printf "%s\n" "$rc" > "$OUT/exit-status.txt"' EXIT
python3 -B "$TRANSFER/preflight.py" | tee "$OUT/preflight-before-build.json"
# Read-only inventories; failed prior builds/layers/images are preserved, never pruned.
podman ps --all --no-trunc > "$OUT/containers-before.txt"
podman images --all --no-trunc --digests > "$OUT/images-before.txt"
if podman image exists "$TAG"; then
    printf 'STOP: new task image tag already exists; preserve it\n'; exit 2
else
    test "$?" -eq 1
fi
podman image inspect "$BASE" > "$OUT/base-image.json"
python3 -B - "$OUT/base-image.json" <<'PY'
import json, sys
j=json.load(open(sys.argv[1]))[0]
assert j['Architecture']=='amd64' and j['Os']=='linux'
PY
sha256sum "$TASK/recipe/Containerfile" "$TASK/recipe/ubuntu.sources" \
  "$TASK/recipe/validate_apt_sources.sh" > "$OUT/recipe.sha256"
# Separate new tag/ID/log; never overwrite the failed Gate C records. Keep intermediate
# build containers too. --no-cache avoids relying on partial layers; --pull=never uses
# the already verified exact base. Only image packages use networking.
podman build --pull=never --no-cache --rm=false --build-arg BASE="$BASE" \
  --iidfile "$OUT/build-image.id" --tag "$TAG" "$TASK/recipe" \
  2>&1 | tee "$OUT/image-build.log"
IMAGE_ID=$(cat "$OUT/build-image.id")
[[ "$IMAGE_ID" =~ ^sha256:[0-9a-f]{64}$ ]]
podman image inspect "$IMAGE_ID" > "$OUT/build-image.json"
python3 -B "$TRANSFER/preflight.py" | tee "$OUT/preflight-before-save.json"
podman save --format oci-archive --output "$OUT/build-image.oci.tar" "$IMAGE_ID"
sha256sum "$OUT/build-image.oci.tar" > "$OUT/build-image.oci.tar.sha256"
podman images --all --no-trunc --digests > "$OUT/images-after.txt"
printf 'R3HD_BASELINE_GATE_C_IMAGE PASS; STOP before Gate D/SDK/game\n'
