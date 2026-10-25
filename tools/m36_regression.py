#!/usr/bin/env python3
"""M36 regression (no game run, D-073): a mod plan may grow VS.sub for the guest.

  * runtime: the overlay header (installed copy = tools/), ExtendRead before the M26 / M33 overlays in
    HostPathFile::ReadSync, GuestSize in HostPathEntry::Create and update(), every call gated by m33mods::Enabled();
    only VS.sub may grow, by the same limit the mod tool uses; the built runtime carries the M36 lines
  * tools: the subtitle compiler's growth limit, its port gate = the payload version, the plan writer's grow record
  * the localization stress tests (synthetic; the real-data part when the game data is present)
  * build order: patch after M33, this regression after M35
Game data is never written.

usage: m36_regression.py
"""
import json
import re
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
sys.path.insert(0, str(TOOLS))
import r3hd_mods as rm  # noqa: E402

SDK = ROOT / "external" / "rexglue-sdk"
BUILD = ROOT / "private" / "work" / "rex" / "out" / "build" / "win-amd64-release"
results = []


def check(ok, label):
    results.append(bool(ok))
    print(f"{'PASS' if ok else 'FAIL'} {label}", flush=True)


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace") if p.is_file() else ""


def run(*args):
    return subprocess.run([sys.executable, *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                          errors="replace")


h = read(TOOLS / "m33_mod_overlay.h")
check((SDK / "include" / "rex" / "m33_mod_overlay.h").read_bytes() == (TOOLS / "m33_mod_overlay.h").read_bytes()
      if (SDK / "include" / "rex" / "m33_mod_overlay.h").is_file() else False,
      "runtime: the overlay header with the M36 growth is installed as written")
names = re.search(r"kGrowNames\[\] = \{([^}]*)\}", h)
check(names and names.group(1).strip() == '"VS.sub"', f"runtime: only VS.sub may grow ({names.group(1) if names else ''})")
lim = re.search(r"kMaxGrowBytes = (\d+)ull << (\d+);", h)
check(lim and int(lim.group(1)) << int(lim.group(2)) == rm.SUB_MAX_GROW,
      "runtime and mod tool: the same growth limit (kMaxGrowBytes = SUB_MAX_GROW)")
check(all(s in h for s in ('fail("grow_not_allowed")', 'fail("grow_order")', 'fail("grow_bounds")', '"grow_uncovered"',
                           'fail("bad_grow")', 'fail("grow_file")')) and "ofstream" not in h,
      "runtime: a grow record is refused for another file, out of order, out of bounds or with an uncovered tail; "
      "nothing is written")
ext = h[h.index("inline bool ExtendRead("):h.index("// Test only: forget the loaded plan.")]
check("std::memset(buffer + inside, 0, size_t(want - inside));" in ext
      and "std::min<uint64_t>(length, t->guest_size - offset)" in ext and ext.count("memcpy") == 0,
      "runtime: ExtendRead writes only buffer[inside, want), want <= the read's length and the grown size")
hpf = read(SDK / "src" / "filesystem" / "devices" / "host_path_file.cpp")
site = hpf[hpf.index("X_STATUS HostPathFile::ReadSync"):hpf.index("X_STATUS HostPathFile::WriteSync")] if hpf else ""
order = [site.find(s) for s in ("file_handle_->Read(", "if (m33mods::Enabled()) {\n    host_read = m33mods::ExtendRead(",
                                "if (host_read) {", "m26tex::AfterRead(", "m33mods::AfterRead(",
                                "return X_STATUS_SUCCESS;", "return X_STATUS_END_OF_FILE;")]
check(all(x >= 0 for x in order) and order == sorted(order) and hpf.count("ExtendRead(") == 1,
      "runtime: ReadSync: host read, gated ExtendRead, then the M26 / M33 overlays; statuses unchanged")
check("ExtendRead" not in hpf[hpf.index("X_STATUS HostPathFile::WriteSync"):] if hpf else False,
      "runtime: nothing in the write or resize path")
hpe = read(SDK / "src" / "filesystem" / "devices" / "host_path_entry.cpp")
check(hpe.count("if (m33mods::Enabled()) entry->size_ = m33mods::GuestSize(full_path, entry->size_, &M36Log);") == 1
      and hpe.count("if (m33mods::Enabled()) size_ = m33mods::GuestSize(host_path_, size_, &M36Log);") == 1
      and hpe.count("GuestSize(") == 2 and "rex::round_up(entry->size_, device->bytes_per_sector())" in hpe,
      "runtime: the guest-visible size (Create and update) is GuestSize, gated; allocation size follows it")
dll = BUILD / "rexruntime.dll"
if dll.is_file():
    b = dll.read_bytes()
    check(b"M36 grow read file=" in b and b"M36 grow size file=" in b and b"grow_not_allowed" in b,
          "runtime: the built runtime carries the M36 growth")
else:
    print("SKIP runtime: not built")
bat = read(TOOLS / "build_milestone8.bat")
pos = [bat.find(s) for s in ("python tools\\m33_runtime_patch.py", "python tools\\m36_runtime_patch.py",
                             "m33_mod_overlay_test.exe || exit /b 1", "python tools\\m35_regression.py",
                             "python tools\\m36_regression.py", "M8_BUILD_OK")]
check(all(x > 0 for x in pos) and pos == sorted(pos), f"build: M36 patch after M33, overlay test, regression after M35 {pos}")
patch = read(TOOLS / "m36_runtime_patch.py")
check("patch_once" in patch and "generated" not in patch.split('"""')[2], "patch: additive (patch_once), host-only")

# tools
pay = json.loads((ROOT / "config" / "release" / "payload.json").read_text(encoding="utf-8"))
check(rm.version_key(pay["version"]) >= rm.version_key(rm.SUB_GROW_PORT) and pay["version"].startswith(("0.36.0", "0.49.0", "0.50.0", "1.0.0", "1.0.1")),
      f"payload: version {pay['version']} serves grown subtitles (gate {rm.SUB_GROW_PORT})")
check('#define AppVersion "' + pay["version"] + '"' in read(TOOLS / "installer" / "r3hd_setup.iss"),
      "setup: the same version as the payload")
src = read(TOOLS / "r3hd_mods.py")
check('if path.name.lower() != "vs.sub":' in src and 'lines.append(f"grow {len(files) - 1} {ends[path]}")' in src,
      "plan writer: a grow record only for VS.sub, right after its file record")
for tool, marker in (("r3hd_mods.py", "R3HD_MODS_SELFTEST PASS"), ("r3hd_locflow.py", "R3HD_LOCFLOW_SELFTEST PASS"),
                     ("r3hd_loc.py", "R3HD_LOC_SELFTEST PASS")):
    r = run(str(TOOLS / tool), "selftest")
    check(r.returncode == 0 and marker in r.stdout, f"{tool} selftest ({(r.stdout.strip().splitlines() or [''])[-1]})")
r = run(str(TOOLS / "m36_loc_stress.py"), "synthetic")
check(r.returncode == 0 and "M36_LOC_STRESS PASS" in r.stdout,
      f"localization stress, synthetic ({(r.stdout.strip().splitlines() or [''])[-1]})")
if (ROOT / "private" / "extracted" / "5841123F" / rm.SUB_FILE).is_file():
    r = run(str(TOOLS / "m36_loc_stress.py"), "real")
    check(r.returncode == 0 and "M36_LOC_REAL PASS" in r.stdout,
          f"localization stress, real data ({(r.stdout.strip().splitlines() or [''])[-1]})")
else:
    print("SKIP localization stress, real data: no game data")
game = read(TOOLS / "m36_sub_game.py")
check("m35.one_run(" in game and "r3hd.exe" not in game and "--user_language=5" in game,
      "in-game check: the M35 runner only (hidden, muted, no controller); the Spanish runs by the runtime's option")

n = results.count(False)
print(f"M36_REGRESSION {'PASS' if not n else 'FAIL'} {len(results) - n}/{len(results)}", flush=True)
sys.exit(1 if n else 0)
