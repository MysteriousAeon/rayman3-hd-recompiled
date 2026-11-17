#!/usr/bin/env python3
"""LX-4 (E-375): the in-game PC Settings save path on POSIX, end to end, without the game.

1. A synthetic installed (portable-prepared) home: installer.json and a fresh HD+ settings.json, as the engine writes.
2. The shared engine on this platform: launcher-model (header, REVISION, END, RUNNING from /proc on Linux) and
   set-preferences with --expect-revision (a change is written; a stale revision is refused STALE).
3. With --cxx (POSIX only): the panel's own engine code, tools/m2_host/r3hd_pc_settings.h (RunEngine / Start with a
   result file, posix_spawn + poll), compiled into a small driver against the SDK headers and run on the same home.

  python3 tools/linux/pcset_engine_test.py [--cxx g++] [--sdk external/rexglue-sdk]
Prints R3HD_PCSET_ENGINE PASS|FAIL with the failed checks; exit 0 only on PASS. No game, window, device or network.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
ROOT = TOOLS.parent
sys.path.insert(0, str(TOOLS))
import r3hd_installer as engine  # noqa: E402

DRIVER = r'''
#include "tools/m2_host/r3hd_pc_settings.h"
#include <chrono>
#include <cstdio>
#include <thread>
using namespace r3hd_pcset;
static std::shared_ptr<Job> Wait(std::shared_ptr<Job> job) {
  for (int i = 0; i < 3000; ++i) {
    { std::lock_guard lock(job->mutex); if (job->done) return job; }
    std::this_thread::sleep_for(std::chrono::milliseconds(20));
  }
  return job;
}
int main(int argc, char** argv) {
  Engine e;
  e.home = Widen(argv[1]); e.python = Widen(argv[2]); e.tools = Widen(argv[3]);
  if (!e.usable()) return 10;
  auto model = Wait(Start(e, {L"launcher-model"}, false));
  Model m = ParseModel(model->out);
  std::printf("MODEL ran=%d code=%u ok=%d settings=%zu revision=%s\n", model->ran, unsigned(model->code), m.ok,
              m.settings.size(), m.revision.c_str());
  std::vector<std::wstring> args{L"set-preferences", L"--expect-revision", Widen(m.revision), L"--set",
                                 L"dualsense_light=off"};
  auto save = Wait(Start(e, args, true));
  std::string result = save->result;
  for (auto& c : result) if (c == '\n' || c == '\r') c = '|';
  std::printf("SAVE ran=%d code=%u result=%s\n", save->ran, unsigned(save->code), result.c_str());
  auto stale = Wait(Start(e, args, true));
  std::printf("STALE ran=%d code=%u\n", stale->ran, unsigned(stale->code));
  std::printf("UTF8 %d\n", Narrow(Widen("\xC4\x9F\xC5\x9F\xC4\xB1")) == "\xC4\x9F\xC5\x9F\xC4\xB1");
  return 0;
}
'''


def make_home(root: Path) -> Path:
    home = root / "home"
    home.mkdir()
    settings = engine.settings_from_args("hdplus", None, (), False, home, fresh=True)
    engine.write_json(home / "settings.json", settings)
    payload = {"version": "lx-test", "payload_id": "0" * 64, "files": {}}
    state = engine.new_state(payload, {"release": "lx-synthetic"}, settings, None)
    state["distribution"] = "portable"
    engine.write_json(home / engine.STATE, state)
    return home


def run_engine(home, *args):
    return subprocess.run([sys.executable, "-B", str(TOOLS / "r3hd_installer.py"), *args, "--home", str(home)],
                          capture_output=True, text=True, encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cxx", help="a C++ compiler (POSIX): also test the panel's engine code")
    ap.add_argument("--sdk", default=str(ROOT / "external" / "rexglue-sdk"))
    a = ap.parse_args()
    fails, notes = [], []

    def check(name, ok, detail=""):
        (notes if ok else fails).append(name + ("" if ok else f" ({detail})"))

    with tempfile.TemporaryDirectory() as tmp:
        home = make_home(Path(tmp))
        r = run_engine(home, "launcher-model")
        rows = [line.split("\t") for line in r.stdout.splitlines()]
        kinds = {row[0]: row for row in rows}
        check("launcher-model exit 0", r.returncode == 0, r.stderr[-300:])
        check("launcher-model header/END", rows and rows[0][0] == "R3HD_LAUNCHER_MODEL" and rows[-1][0] == "END")
        check("launcher-model INSTALL ok", kinds.get("INSTALL", ["", ""])[1] == "ok", kinds.get("INSTALL"))
        check("launcher-model RUNNING 0", kinds.get("RUNNING", ["", ""])[1] == "0", kinds.get("RUNNING"))
        revision = kinds.get("REVISION", ["", ""])[1]
        check("launcher-model REVISION", len(revision) == 64, revision)
        light = [row for row in rows if row[:2] == ["SETTING", "dualsense_light"]]
        check("fresh home: light bar on (D-108)", light and light[0][10] == "on", light)
        r = run_engine(home, "set-preferences", "--expect-revision", revision, "--set", "dualsense_light=off", "--json")
        check("set-preferences exit 0", r.returncode == 0, r.stderr[-300:] or r.stdout[-300:])
        data = json.loads((home / "settings.json").read_text(encoding="utf-8"))
        check("settings.json preference written", data.get("preferences", {}).get("dualsense_light") == "off",
              data.get("preferences"))
        r = run_engine(home, "set-preferences", "--expect-revision", revision, "--set", "dualsense_light=on")
        check("stale revision refused", r.returncode != 0 and "STALE" in (r.stdout + r.stderr), r.returncode)

        if a.cxx:
            if os.name == "nt":
                check("--cxx is POSIX only", False, "run under Linux/WSL")
            else:
                home2 = make_home(Path(tmp) / "cxx") if (Path(tmp) / "cxx").mkdir() is None else None
                src, exe = Path(tmp) / "pcset_driver.cpp", Path(tmp) / "pcset_driver"
                src.write_text(DRIVER, encoding="utf-8")
                sdk = Path(a.sdk)
                inc = [f"-I{ROOT}", f"-I{sdk / 'include'}", f"-I{sdk / 'thirdparty/imgui'}",
                       f"-I{sdk / 'thirdparty/fmt/include'}", f"-I{sdk / 'thirdparty/spdlog/include'}",
                       f"-I{sdk / 'thirdparty/tomlplusplus/include'}", f"-I{sdk / 'thirdparty/cli11/include'}"]
                c = subprocess.run([a.cxx, "-std=c++23", "-O1", "-Wall", "-DFMT_HEADER_ONLY", *inc, str(src), "-o", str(exe), "-pthread"],
                                   capture_output=True, text=True)
                check(f"driver builds with {a.cxx}", c.returncode == 0, c.stderr[-600:])
                if c.returncode == 0:
                    d = subprocess.run([str(exe), str(home2), sys.executable, str(TOOLS)], capture_output=True,
                                       text=True, timeout=300)
                    out = {line.split(" ", 1)[0]: line for line in d.stdout.splitlines()}
                    check("driver exit 0", d.returncode == 0, d.returncode)
                    check("panel RunEngine: launcher-model parsed",
                          "ran=1 code=0 ok=1" in out.get("MODEL", "") and "revision=none" not in out.get("MODEL", ""),
                          out.get("MODEL"))
                    check("panel Start: set-preferences result file read",
                          "ran=1 code=0" in out.get("SAVE", "") and "CHANGED=1" in out.get("SAVE", ""), out.get("SAVE"))
                    saved = json.loads((home2 / "settings.json").read_text(encoding="utf-8"))
                    check("panel save reached settings.json",
                          saved.get("preferences", {}).get("dualsense_light") == "off", saved.get("preferences"))
                    check("panel: stale save refused", "ran=1" in out.get("STALE", "") and "code=0" not in out.get("STALE", ""),
                          out.get("STALE"))
                    check("panel UTF-8 round trip", out.get("UTF8") == "UTF8 1", out.get("UTF8"))
                    leftovers = [p for p in Path(os.environ.get("TMPDIR") or "/tmp").glob("r3p*")
                                 if p.stat().st_mtime > Path(tmp).stat().st_mtime - 5]
                    check("result files removed", not leftovers, leftovers[:3])
    verdict = "PASS" if not fails else "FAIL"
    print(f"R3HD_PCSET_ENGINE {verdict} checks={len(notes) + len(fails)} failed={fails}")
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
