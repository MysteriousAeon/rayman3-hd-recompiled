#!/usr/bin/env bash
# Reproduces the Milestone 1 measurements from the raw package. Run from repo root (Git Bash).
# Prereqs: external/ checkouts at the commits pinned in PROJECT_STATE.md, built as described in
# EXPERIMENTS.md (E-05, E-06); external/venv with capstone + pycryptodome.
set -euo pipefail
RAW=private/raw/xbox360/5841123F/000D0000/3D8189500116FB22A848B806DDF3F90B2824B54958
X=private/extracted/5841123F
W=private/work
PY=external/venv/Scripts/python
REX=$PWD/external/rexglue-sdk/out/win-amd64/Release/rexglue.exe
XR=external/XenonRecomp/out-clang
mkdir -p "$W/xenon/ppc" "$W/rex"

sha256sum "$RAW"                                                             # E-01
python tools/stfs_extract.py "$RAW" --info --list > "$W/stfs_listing.txt"    # E-02
python tools/stfs_extract.py "$RAW" --extract "$X" --manifest "$W/extracted_manifest.tsv"
$PY tools/xex_info.py "$X/Default.xex" --image-out "$W/default_image.bin" > "$W/xex_info.json"   # E-03
$PY tools/pe_analyze.py "$W/default_image.bin" "$W/xex_info.json" --out "$W/pe_analysis.json" > /dev/null  # E-04
$PY tools/import_xrefs.py "$W/default_image.bin" "$W/pe_analysis.json" > /dev/null
$PY tools/strings_scan.py "$W/default_image.bin" > "$W/strings_scan.txt"

# ReXGlue (E-06..E-08). First run only: rexglue init, then add the includes line.
if [ ! -f "$W/rex/r3hd_manifest.toml" ]; then
  (cd "$W/rex" && "$REX" init --project-name r3hd --xex-path ../../extracted/5841123F/Default.xex \
      --game-root ../../extracted/5841123F --project-root . --scan-dll)
  sed -i 's#includes = \[\]#includes = ["../../../config/rexglue/r3hd_functions.toml"]#' "$W/rex/r3hd_manifest.toml"
fi
(cd "$W/rex" && "$REX" --log-level debug codegen --ignore-stamp r3hd_manifest.toml > codegen_e08.stdout 2>&1)
$PY tools/rex_coverage.py "$W/rex/generated/default" "$W/default_image.bin" "$W/pe_analysis.json" "$W/rex_coverage.json"
$PY tools/fnptr_scan.py "$W/default_image.bin" "$W/pe_analysis.json" "$W/rex/generated/default/r3hd_init.cpp" - \
    "$W/rex/generated/default" "$W/fnptr_scan.json"
python tools/import_surface.py "$W/pe_analysis.json" "$W/import_xrefs.json" external/rexglue-sdk external/xenia \
    reports/milestone1/import_surface.csv

# XenonRecomp cross-check (E-10, E-11)
"$XR/XenonAnalyse/XenonAnalyse.exe" "$X/Default.xex" "$W/xenon/switch_tables.toml"
cp config/xenonrecomp/r3hd.toml "$W/xenon/r3hd.toml"
(cd "$W/xenon" && ../../../$XR/XenonRecomp/XenonRecomp.exe r3hd.toml ../../../external/XenonRecomp/XenonUtils/ppc_context.h > recomp.log 2>&1)
