#!/usr/bin/env bash
# Research only: extracted Noble packages, never a system install or SDK build.
# Usage: bash research_expected.sh EXTRACTED_ROOT NEW_OUTPUT REPOSITORY
set -euo pipefail
ROOT=$(realpath "$1")
OUT=$(realpath -m "$2")
REPO=$(realpath "$3")
test ! -e "$OUT"
test ! -L "$OUT"
mkdir "$OUT"
# Driver dependencies only; never inject an older libc into the host loader.
mkdir "$OUT/driver-libs"
for pattern in 'libLLVM*.so*' 'libclang-cpp*.so*' 'libxml2.so*' 'libicu*.so*'; do
  find "$ROOT/usr/lib/x86_64-linux-gnu" -maxdepth 1 -name "$pattern" \
    -exec ln -s -t "$OUT/driver-libs" {} +
done
export LD_LIBRARY_PATH="$OUT/driver-libs"
for clang in 18 19; do
  for gcc in 13 14; do
    name="clang${clang}-gcc${gcc}"
    cxx="$ROOT/usr/bin/clang++-$clang"
    flags=(--sysroot="$ROOT" --gcc-install-dir="$ROOT/usr/lib/gcc/x86_64-linux-gnu/$gcc"
      -std=c++23 -O2 -pthread -march=x86-64-v2
      -nostdinc++ -isystem "$ROOT/usr/include/c++/$gcc"
      -isystem "$ROOT/usr/include/x86_64-linux-gnu/c++/$gcc"
      -isystem "$ROOT/usr/include/c++/$gcc/backward")
    "$cxx" --version > "$OUT/$name.version.txt"
    printf '#include <version>\n' | "$cxx" "${flags[@]}" -dM -E -x c++ - > "$OUT/$name.macros.txt"
    # Deliberate negative cases must fail, positive cases must compile/link/run.
    if "$cxx" "${flags[@]}" -v -Wl,-t -I"$REPO/external/rexglue-sdk/include" \
        "$REPO/tools/linux/baseline/feature.cpp" -o "$OUT/$name" > "$OUT/$name.build.txt" 2>&1; then
      test "$clang" = 19
      env -u LD_LIBRARY_PATH timeout 20 "$ROOT/usr/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2" \
        --library-path "$ROOT/usr/lib/x86_64-linux-gnu" "$OUT/$name" > "$OUT/$name.run.txt"
      grep -Fx 'R3HD_BASELINE_FEATURE PASS 42:42' "$OUT/$name.run.txt" > /dev/null
      readelf -h -d -V "$OUT/$name" > "$OUT/$name.readelf.txt"
      objdump -T "$OUT/$name" > "$OUT/$name.symbols.txt"
      printf '%s COMPILE_LINK_RUN_PASS\n' "$name"
    else
      test "$clang" = 18
      grep -F "no template named 'expected' in namespace 'std'" "$OUT/$name.build.txt" > /dev/null
      printf '%s EXPECTED_COMPILE_FAILURE\n' "$name"
    fi
  done
done
# Runtime provider exports are not the executable's imported requirements.
readelf -V "$ROOT/usr/lib/x86_64-linux-gnu/libstdc++.so.6" > "$OUT/provider.readelf.txt"
python3 - "$OUT" <<'PY'
import json, re, sys
from pathlib import Path
p = Path(sys.argv[1]); result = {}
for f in sorted(p.glob('clang*.readelf.txt')):
    text = f.read_text(); row = {}
    for prefix, ceiling in [('GLIBC', (2,39)), ('GLIBCXX', (3,4,33))]:
        values = {tuple(map(int, x.split('.'))) for x in re.findall(r'\b'+prefix+r'_(\d+(?:\.\d+)+)', text)}
        assert values and max(values) <= ceiling, (f, prefix, values)
        row[prefix] = '.'.join(map(str, max(values)))
    result[f.name] = row
(p/'abi.json').write_text(json.dumps(result, indent=2)+'\n')
print(json.dumps(result))
PY
