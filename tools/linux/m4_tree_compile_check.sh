#!/bin/bash
# LM-A A2 (WSL/Linux discovery, not authoritative): compile every SEH-owning file of the production generated tree
# (macro emission) against the portable M4 backend with GCC, -fsyntax-only, plus the two patched SDK kernel files
# that hold the RtlRaiseException/RtlUnwind hooks. Prints one line per file and a summary. Nothing is linked or run.
#   bash tools/linux/m4_tree_compile_check.sh [OUT_DIR]
R=$(cd "$(dirname "$0")/../.." && pwd)
G=$R/private/work/rex/generated/default
S=$R/external/rexglue-sdk
OUT=${1:-$R/private/work/m4_tree_check}
mkdir -p "$OUT/inc/rex"
cp "$R/tools/m4_seh.h" "$R/tools/m4_seh_portable.h" "$R/tools/m4_dispatch.h" "$OUT/inc/rex/"
COMMON=(-std=c++23 -fsyntax-only -msse4.1 -fexceptions -w -DREX_PLATFORM_LINUX=1 -DSPDLOG_FMT_EXTERNAL -DNDEBUG
        -include "$R/tools/linux/compat_gcc/rex_gcc_builtin_assume.h"
        -I "$OUT/inc" -I "$R/tools/linux/compat"
        -isystem "$S/out/install/win-amd64/include" -isystem "$S/thirdparty/fmt/include"
        -isystem "$S/thirdparty/spdlog/include")
pass=0; fail=0
for f in $(grep -l 'M4_FRAME(' "$G"/r3hd_recomp.*.cpp | sort -V); do
  if g++ "${COMMON[@]}" -include "$R/tools/experiments/linux_guest_entry/lge_define_rex_func.h" \
       -I "$G" -I "$R/private/work/rex" -I "$R/private/work/rex/src" "$f" > "$OUT/$(basename "$f").log" 2>&1; then
    pass=$((pass+1))
  else
    fail=$((fail+1)); echo "FAIL $(basename "$f")"; grep -m3 'error' "$OUT/$(basename "$f").log"
  fi
done
echo "M4_TREE_COMPILE seh_files_pass=$pass seh_files_fail=$fail"
for k in src/kernel/xboxkrnl/xboxkrnl_debug.cpp src/kernel/xboxkrnl/xboxkrnl_rtl.cpp src/system/function_dispatcher.cpp; do
  if g++ "${COMMON[@]}" -I "$S/include" -I "$S/src" -I "$S/thirdparty/simde" "$S/$k" > "$OUT/$(basename "$k").log" 2>&1; then
    echo "SDK_HOOK_COMPILE PASS $k"
  else
    echo "SDK_HOOK_COMPILE FAIL $k"; grep -m5 'error' "$OUT/$(basename "$k").log"
  fi
done
