#!/usr/bin/env bash
set -euo pipefail
export PATH="/runner:$PATH" CC=clang CXX=clang++ CMAKE_BUILD_PARALLEL_LEVEL=4
export PYTHONDONTWRITEBYTECODE=1 LANG=C.UTF-8 LC_ALL=C.UTF-8 TZ=UTC SOURCE_DATE_EPOCH=1794146315
unset DISPLAY WAYLAND_DISPLAY XAUTHORITY LD_PRELOAD LD_AUDIT
mkdir -p "$HOME"
cd /task/work
OUT=/task/work/private/work/linux_build/noble_2b01
TREE=/task/work/private/lma/rex_lma
LIB=/task/work/external/rexglue-sdk/out/install/linux-amd64/lib
python3 -B /runner/stage2b.py check
python3 -B /runner/retry.py sources
cmp /opt/r3hd-egl/parent-packages.tsv /task/evidence/verified-2a-packages.tsv
pkg-config --print-errors --exists 'wayland-client >= 1.18' wayland-egl wayland-cursor egl 'xkbcommon >= 0.5.0'
clang++ --version | grep -F '19.1.1'
clang++ -v -E -x c++ /dev/null 2> /task/evidence/retry-compiler-search.txt
grep -E 'Selected GCC installation: .*/13$' /task/evidence/retry-compiler-search.txt
clang++ -std=c++23 -O2 -pthread -march=x86-64-v2 -Iexternal/rexglue-sdk/include \
  tools/linux/baseline/feature.cpp -o /task/evidence/retry-feature
timeout 20 /task/evidence/retry-feature
python3 -B /runner/retry.py sdk
cp /opt/r3hd-packages.tsv "$OUT/image-packages.tsv"
# Reuse the entire unchanged acceptance/build tail, including every SDL/ABI/LGPL gate.
python3 -B /runner/retry.py tail /tmp/r3hd-after-sdk.sh
source /tmp/r3hd-after-sdk.sh
