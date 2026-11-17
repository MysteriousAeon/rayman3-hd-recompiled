#!/usr/bin/env bash
set -euo pipefail
# Invoked inside the pinned image only; /work is read-only, /evidence is task-specific.
test "$(uname -m)" = x86_64
test "$(id -u)" != 0
test -d /evidence
test ! -e /evidence/feature
mkdir -p "$HOME"
cp /opt/r3hd-packages.tsv /evidence/
clang++-18 --version
cmake --version
ninja --version
ld --version
clang++-18 --gcc-toolchain=/usr -v -E -x c++ /dev/null
printf '#include <version>\n' | clang++-18 --gcc-toolchain=/usr -std=c++23 -dM -E -x c++ - > /evidence/feature-macros.txt
# g++-13 is the sole GCC development toolchain in the recipe; reject accidental newer selection.
clang++-18 --gcc-toolchain=/usr -v -E -x c++ /dev/null 2> /evidence/compiler-search.txt
grep -E 'Selected GCC installation: .*/13$' /evidence/compiler-search.txt
clang++-18 --gcc-toolchain=/usr -std=c++23 -O2 -pthread -march=x86-64-v2 \
  -I/work/external/rexglue-sdk/include /work/tools/linux/baseline/feature.cpp -o /evidence/feature
timeout 20 /evidence/feature
readelf -h -d -V /evidence/feature > /evidence/feature-readelf.txt
objdump -T /evidence/feature > /evidence/feature-symbols.txt
python3 -B - <<'PY'
import re
from pathlib import Path
text = Path('/evidence/feature-readelf.txt').read_text()
for prefix, limit in [('GLIBC', (2,39)), ('GLIBCXX', (3,4,33))]:
    values = {tuple(map(int, v.split('.'))) for v in re.findall(r'\b'+prefix+r'_(\d+(?:\.\d+)+)', text)}
    assert values and max(values) <= limit, (prefix, sorted(values), limit)
    print(prefix, 'max', '.'.join(map(str,max(values))))
PY
sha256sum /evidence/feature /evidence/r3hd-packages.tsv
printf 'R3HD_BASELINE_PROBE PASS (feature only; full SDK/game not built)\n'
