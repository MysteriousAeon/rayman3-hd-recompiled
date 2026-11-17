#!/usr/bin/env bash
# One isolated, networkless container; only CPU fixtures may execute.
set -euo pipefail
export PATH="/runner:$PATH"
export CC=clang CXX=clang++ CMAKE_BUILD_PARALLEL_LEVEL=4
export PYTHONDONTWRITEBYTECODE=1
export LANG=C.UTF-8 LC_ALL=C.UTF-8 TZ=UTC SOURCE_DATE_EPOCH=1794146315
unset DISPLAY WAYLAND_DISPLAY XAUTHORITY LD_PRELOAD LD_AUDIT
mkdir -p "$HOME"
cd /task/work
OUT=/task/work/private/work/linux_build/noble_2b01
TREE=/task/work/private/lma/rex_lma
LIB=/task/work/external/rexglue-sdk/out/install/linux-amd64/lib
test ! -e "$OUT"
mkdir -p "$OUT"
python3 -B /runner/stage2b.py check
clang++ --version | tee "$OUT/compiler-version.txt"
grep -F '19.1.1' "$OUT/compiler-version.txt"
clang++ -v -E -x c++ /dev/null 2> "$OUT/compiler-search.txt"
grep -E 'Selected GCC installation: .*/13$' "$OUT/compiler-search.txt"
cp /opt/r3hd-packages.tsv "$OUT/image-packages.tsv"
cmp /opt/r3hd-packages.tsv /task/evidence/verified-2a-packages.tsv
# Repeat the unchanged feature source through the exact compiler shims used by CMake.
clang++ -std=c++23 -O2 -pthread -march=x86-64-v2 \
  -Iexternal/rexglue-sdk/include tools/linux/baseline/feature.cpp -o "$OUT/feature"
timeout 20 "$OUT/feature" | tee "$OUT/feature.log"
grep -Fx 'R3HD_BASELINE_FEATURE PASS 42:42' "$OUT/feature.log"
python3 -B tools/linux/r3hd_linux_build.py doctor --compilers clang > "$OUT/doctor.json"
# This replays the existing ordered patch chain into the NEW SDK copy only.
python3 -B tools/linux/r3hd_linux_build.py run --out "$OUT" --compilers clang --jobs 4
python3 -B /runner/stage2b.py backends --task /task
python3 -B tools/r3hd_vulkan_parity_regression.py
python3 -B tools/m5_vb_residency_regression.py
python3 -B tools/linux/test_red_correction_upload.py --cxx clang++
python3 -B tools/linux/r3hd_linux_build.py game --out "$OUT" --tree "$TREE" --jobs 4
python3 -B tools/linux/r3hd_linux_build.py gamesync --out "$OUT" \
  --game-build "$OUT/build/game-lma" --jobs 4
python3 -B tools/linux/test_r3hd_host_inputs.py
python3 -B tools/linux/test_r3hd_linux_package.py --cc clang
python3 -B tools/linux/test_lgpl_so_check.py --cc clang
python3 -B tools/linux/test_r3hd_play.py
python3 -B tools/linux/test_r3hd_settings_gui.py
clang++ -std=c++20 -O2 tools/linux/mod_plan_probe.cpp -Itools -o "$OUT/mod-plan-probe"
python3 -B tools/linux/test_r3hd_mods.py --probe "$OUT/mod-plan-probe"
sh tools/linux/test_m46_ffmpeg_so.sh clang
python3 -B tools/linux/lgpl_so_check.py --lib "$LIB" --json "$OUT/lgpl-original.json"
python3 -B tools/m46_lgpl.py package --platform linux --out "$OUT/lgpl"
shopt -s nullglob
SOURCES=("$OUT"/lgpl/r3hd-lgpl-source-*-linux-x86_64.zip)
test "${#SOURCES[@]}" -eq 1
LGPL_ZIP=${SOURCES[0]}
(cd "$OUT/lgpl" && sha256sum -c "$(basename "$LGPL_ZIP").sha256")
for MODE in plain modified; do
  EXTRA=()
  if test "$MODE" = modified; then EXTRA=(--modify); fi
  python3 -B tools/m46_lgpl.py rebuild "$LGPL_ZIP" "$OUT/lgpl-$MODE" "${EXTRA[@]}"
  python3 -B tools/linux/lgpl_so_check.py --lib "$LIB" \
    --replacement "$OUT/lgpl-$MODE/r3hd-lgpl-source/build" --json "$OUT/lgpl-$MODE.json"
done
python3 -B /runner/stage2b.py abi --task /task
python3 -B /runner/stage2b.py immutable --task /task
python3 -B tools/linux/r3hd_linux_package.py build --bin "$OUT/build/game-lma" --lib "$LIB" \
  --out "$OUT/r3hd-linux-noble-2b01.tar.gz" --development-id noble-2b01 --lgpl-source "$LGPL_ZIP" \
  > "$OUT/package-build.json"
python3 -B tools/linux/r3hd_linux_package.py check "$OUT/r3hd-linux-noble-2b01.tar.gz" \
  > "$OUT/package-check.json"
python3 -B /runner/stage2b.py package --task /task
(cd "$OUT" && sha256sum r3hd-linux-noble-2b01.tar.gz "lgpl/$(basename "$LGPL_ZIP")" > DELIVERABLES.sha256)
printf 'R3HD_STAGE2B_BUILD_PACKAGE PASS; STOP: no game execution or publication\n'
