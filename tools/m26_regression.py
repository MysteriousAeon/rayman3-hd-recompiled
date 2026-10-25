#!/usr/bin/env python3
"""M26 tooling regression (no game run): the texture orientation correction's patch shape, launcher option, table
identity against the local target data, and the audit tool's self-test.

    python tools/m26_regression.py                 -> M26_REGRESSION PASS checks=N failures=0
    python tools/m26_regression.py --run RUN...    also judges hidden run directories (private/work/m6_runs/RUN):
                                                   a run named *_corrected must have selected the correction and
                                                   served every listed page it read; any other run must not

The block mirror itself is tested by m26_texture_orient_test.exe (in the build); here an independent Python
implementation recomputes the table's hashes from `private/extracted/.../fact_55_2.btf` when that file exists
(checks that need it are counted as skipped otherwise, never as passed). The build script also runs the test
executable against that file (whole-file read through the overlay); this script starts no executable.
"""
import re
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
SDK = ROOT / "external" / "rexglue-sdk"
RUNS = ROOT / "private" / "work" / "m6_runs"
DATA = ROOT / "private" / "extracted" / "5841123F" / "GAMEDATAbin"

checks = failures = skipped = 0


def check(condition: bool, label: str) -> None:
    global checks, failures
    checks += 1
    if not condition:
        failures += 1
        print(f"FAIL {label}")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def fnv(data: bytes) -> int:
    h = 0xCBF29CE484222325
    for c in data:
        h = ((h ^ c) * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
    return h


def mirror_block(b: bytes) -> bytes:
    w = bytearray(b)
    w[0::2], w[1::2] = w[1::2], w[0::2]
    a, c = int.from_bytes(w[2:5], "little"), int.from_bytes(w[5:8], "little")
    w[2:5] = ((c >> 12) | ((c & 0xFFF) << 12)).to_bytes(3, "little")
    w[5:8] = ((a >> 12) | ((a & 0xFFF) << 12)).to_bytes(3, "little")
    w[12:16] = w[12:16][::-1]
    w[0::2], w[1::2] = w[1::2], w[0::2]
    return bytes(w)


def mirror_page(blobs, levels) -> None:
    for blob, base, pitch, x, y, n in levels:
        buf = blobs[blob]
        at = lambda j: base + ((y + j) * pitch + x) * 16
        rows = [bytes(buf[at(j):at(j) + n * 16]) for j in range(n)]
        for j in range(n):
            src = rows[n - 1 - j]
            buf[at(j):at(j) + n * 16] = b"".join(mirror_block(src[k * 16:k * 16 + 16]) for k in range(n))


def judge_run(name: str) -> None:
    run = RUNS / name
    log = "".join(read(p) for p in sorted(run.glob("runtime*.log")))
    mode = re.findall(r"M26 texture_orient=(\w+)", log)
    states = re.findall(r"M26 texture_orient file=(\S+) page=(\S+) state=(\w+)", log)
    served = re.findall(r"M26 texture_orient file=(\S+) page=(\S+) served_bytes=(\d+)", log)
    if name.endswith("_corrected"):
        check(mode and set(mode) == {"corrected"}, f"{name}: correction selected (got {sorted(set(mode))})")
        check(all(s == "corrected" for _, _, s in states), f"{name}: no page refused ({states})")
        if "fact_55_2.btf" in log.lower() or states:
            check(sorted(p for _, p, _ in states) == sorted(PAGES), f"{name}: the four pages prepared once each")
            check(sorted(p for _, p, _ in served) == sorted(PAGES) and all(int(n) == 0x60000 for _, _, n in served),
                  f"{name}: every page's line says exactly its 393,216 bytes ({served})")
            # (the counter adds replaced bytes, so a re-read counts twice: exactly one page's size at the first
            # crossing is what one complete delivery gives; the byte-exact proof is the test executable's)
    else:
        check(mode and set(mode) == {"original"}, f"{name}: the title's data (got {sorted(set(mode))})")
        check(not states and not served, f"{name}: no page line without the switch")


header = read(TOOLS / "m26_texture_orient.h")
patch = read(TOOLS / "m26_runtime_patch.py")
hpf = read(SDK / "src/filesystem/devices/host_path_file.cpp")
cp = read(SDK / "src/graphics/d3d12/command_processor.cpp")
bat = read(TOOLS / "build_milestone8.bat")
play = read(TOOLS / "play.ps1")
hidden = read(TOOLS / "run_milestone6.ps1")

rows = re.findall(r'\{"(fac_sbire0\d\.dds)", \{(0x[0-9A-F]+), (0x[0-9A-F]+)\}, \{(0x[0-9A-F]+), (0x[0-9A-F]+)\},\s*'
                  r'\{(0x[0-9A-F]+)ull, (0x[0-9A-F]+)ull\}, \{(0x[0-9A-F]+)ull, (0x[0-9A-F]+)ull\}\}', header)
PAGES = [r[0] for r in rows]
levels = [tuple(int(v, 0) for v in m) for m in re.findall(
    r"\{(\d), (0x[0-9A-F]+), (\d+), (\d+), (\d+), (\d+)\}", header[header.index("kPage512Dxt5[]"):header.index("kPage512Dxt5Levels")])]
bundle = re.search(r'\{"(fact_55_2\.btf)", (\d+), kFact55Pages,', header)

if "--run" in sys.argv:
    for run_name in sys.argv[sys.argv.index("--run") + 1:]:
        judge_run(run_name)

check(read(SDK / "include/rex/m26_texture_orient.h") == header, "m26_texture_orient.h: installed copy equals tools/")

# Off by default, one variable, one value; fail-closed identity; nothing written anywhere.
check('Selected(std::getenv("R3HD_TEXTURE_ORIENT"))' in header and header.count("getenv") == 1, "header: one variable")
check('std::strcmp(value, "corrected") == 0' in header, "header: only 'corrected' selects the correction")
check(len(rows) == 4 and bundle and len(levels) == 10, "header: one bundle, four pages, ten mip levels parsed")
check("file_size(host_path, ec) != bundle.size" in header and "!= page.stored[b]) return PageState::kRefusedStored" in header
      and "!= page.corrected[b]) return PageState::kRefusedResult" in header,
      "header: file size, stored hash and result hash must all match or the read is returned as it is")
check("if (slot.state != PageState::kCorrected) continue;" in header, "header: a refused page is never overlaid")
for word in ("ofstream", "fopen", "WriteFile", "CreateFile", "virtual_membase", "TranslateVirtual", "store_and_swap",
             "remove(", "rename("):
    check(word not in header, f"header: no '{word}' (nothing written to disk or to guest memory by address)")
check("if (!(force || Enabled()) || !length) return 0;" in header, "header: the switch is tested before anything else")

# One read site, after a successful host read; the write path and every other file are untouched.
check(hpf.count("m26tex::") == 3 and hpf.count("m26tex::AfterRead(") == 1, "host file: one gated call site")
site = hpf[hpf.index("X_STATUS HostPathFile::ReadSync"):hpf.index("X_STATUS HostPathFile::WriteSync")]
check(site.index("file_handle_->Read(") < site.index("if (m26tex::Enabled()) {") < site.index("m26tex::AfterRead(")
      < site.index("return X_STATUS_SUCCESS;"), "site: flag, then the overlay, inside the success branch only")
check("m26tex" not in hpf[hpf.index("X_STATUS HostPathFile::WriteSync"):], "site: nothing in the write or resize path")
check(site.count("return X_STATUS_SUCCESS;") == 1 and "return X_STATUS_END_OF_FILE;" in site and "X_STATUS_ACCESS_DENIED" in site,
      "site: the read's status codes are unchanged")
check("m20save::NoteWriteFailure" in hpf, "host file: the M20 write-path lines are still there")
check('REXGPU_INFO("M26 texture_orient={}", m26tex::Enabled() ? "corrected" : "original");' in cp, "mode logged at start-up")
check(cp.count("m26tex::") == 1, "command processor: the log line only")
check('REXGPU_INFO("M23 layer_coords={}", m23water::Enabled() ? "separate" : "original");\n'
      '  REXGPU_INFO("M15 draw_scale' in cp, "command processor: the M23 patch text is still contiguous")
others = [p for p in (SDK / "src").rglob("*.cpp") if "m26tex::" in read(p)]
check(len(others) == 2, f"SDK: two source files mention the option ({[p.name for p in others]})")

# Launcher: a person's switch, default original, restored afterwards; the hidden runner never selects it.
check("[ValidateSet('original', 'corrected')][string]$TextureOrient = 'original'," in play, "play.ps1: -TextureOrient, default original")
check("$savedOrient = $env:R3HD_TEXTURE_ORIENT" in play and "$env:R3HD_TEXTURE_ORIENT = $TextureOrient" in play
      and "$env:R3HD_TEXTURE_ORIENT = $savedOrient" in play, "play.ps1: sets the variable from the option and restores it")
check(play.count("texture_orient = $TextureOrient") == 2, "play.ps1: the mode is recorded with the session")
check("R3HD_TEXTURE_ORIENT" not in hidden, "hidden runner: never selects the correction by itself")
check("[Alias('WaterLayers')][ValidateSet('original', 'separate')][string]$LayerCoords = 'original'," in play,
      "play.ps1: the M23 option is unchanged")

# Build chain.
check(bat.index("m24_runtime_patch.py") < bat.index("m26_runtime_patch.py") < bat.index("cmake --build external"), "patch order")
check(bat.index("m20_runtime_patch.py") < bat.index("m26_runtime_patch.py"), "after M20 (which rebuilds host_path_file.cpp from the pin)")
check(bat.index("m23_prepare.py") < bat.index("m26_prepare.py") < bat.index("rexglue.exe"), "prepare order")
check("m26_texture_orient_test.exe || exit /b 1" in bat and "--target m26_texture_orient_test " in bat, "build runs the mirror test")
check("python tools\\m26_regression.py" in bat, "build runs this regression")
check("patch_once" in patch and "from_head" not in patch, "patch is additive (patch_once)")

# The audit tool's own self-test (no game data).
done = subprocess.run([sys.executable, str(TOOLS / "m26_uv_audit.py"), "selftest"], capture_output=True, text=True)
check(done.returncode == 0 and "M26_UV_AUDIT_SELFTEST PASS" in done.stdout, "m26_uv_audit.py selftest")

# Table identity against the local target data.
btf, bhf = DATA / "fact_55" / "fact_55_2.btf", DATA / "fact_55" / "fact_55_2.bhf"
if btf.is_file() and bhf.is_file() and rows and bundle:
    check(btf.stat().st_size == int(bundle.group(2)), "target: bundle size as listed")
    same_name = [p for p in DATA.rglob("*") if p.is_file() and p.name.lower() == "fact_55_2.btf"]
    check(same_name == [btf], "target: no other file of the title has the listed name")
    head = bhf.read_bytes()
    entries = {}
    for i in range(struct.unpack_from(">I", head, 0)[0]):
        o = 4 + i * 0x114
        s1, o1, s2, o2 = struct.unpack_from(">4I", head, o)
        entries[head[o + 16:o + 0x114].split(b"\0")[0].decode("latin1").split("\\")[-1].lower()] = (o1, o2, s1, s2)
    data = btf.read_bytes()
    for name, o1, o2, s1, s2, h1, h2, c1, c2 in rows:
        o1, o2, s1, s2, h1, h2, c1, c2 = (int(v, 16) for v in (o1, o2, s1, s2, h1, h2, c1, c2))
        check(entries.get(name) == (o1, o2, s1, s2), f"target: {name} is the bundle entry at the listed offsets and sizes")
        blobs = [bytearray(data[o1:o1 + s1]), bytearray(data[o2:o2 + s2])]
        check((fnv(blobs[0]), fnv(blobs[1])) == (h1, h2), f"target: {name} stored hashes")
        mirror_page(blobs, levels)
        check((fnv(blobs[0]), fnv(blobs[1])) == (c1, c2), f"target: {name} corrected hashes from the independent mirror")
        mirror_page(blobs, levels)
        check(bytes(blobs[0]) == data[o1:o1 + s1] and bytes(blobs[1]) == data[o2:o2 + s2], f"target: {name} mirror twice is the file")
else:
    skipped += 18

print(f"M26_REGRESSION {'PASS' if not failures else 'FAIL'} checks={checks} failures={failures} skipped={skipped}")
sys.exit(1 if failures else 0)
