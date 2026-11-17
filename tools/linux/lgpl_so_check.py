#!/usr/bin/env python3
"""B3 (E-376): the Linux LGPL libraries judged by what matters, not by a count (native; needs binutils nm).

  python3 tools/linux/lgpl_so_check.py --lib DIR [--replacement DIR] [--windows-list FILE] [--json OUT]

Checks on DIR/librexruntime.so, libffmpeg.so and libmspack.so:
  * libffmpeg.so exports only av* names (upstream's libav*.v rule, the Windows .def rule) and nothing else;
  * every av* symbol librexruntime.so imports is exported by libffmpeg.so, and the imports equal the recorded
    Windows import list (config/release/lgpl_components.json imported_by_rexruntime);
  * librexruntime.so defines no av* / ff* symbol (FFmpeg is no longer linked into it statically);
  * libmspack.so exports exactly the recorded lzxd_* set; librexruntime.so imports only from it.
With --windows-list (the av* names of the Windows ffmpeg.def, one per line or an EXTERN list), the name-level
difference is reported. A different count is information: the export set follows each platform's FFmpeg
configuration; correctness is the import and naming checks above. Final line R3HD_LGPL_SO PASS|FAIL.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def nm(path, *flags):
    out = subprocess.run(["nm", "-D", *flags, str(path)], capture_output=True, text=True, check=True).stdout
    return {line.split()[-1].split("@")[0] for line in out.splitlines() if line.strip()}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--lib", type=Path, required=True)
    ap.add_argument("--windows-list", type=Path)
    ap.add_argument("--replacement", type=Path,
                    help="B3b: a directory holding libffmpeg.so / libmspack.so rebuilt from the source archive; "
                         "they are judged against the shipped librexruntime.so of --lib")
    ap.add_argument("--json", type=Path)
    a = ap.parse_args()
    fails, facts = [], {}
    rec = json.loads((ROOT / "config/release/lgpl_components.json").read_text(encoding="utf-8"))["components"]
    rt, ff, ms = (a.lib / n for n in ("librexruntime.so", "libffmpeg.so", "libmspack.so"))
    if a.replacement:
        ff, ms = a.replacement / "libffmpeg.so", a.replacement / "libmspack.so"
        facts["replacement"] = str(a.replacement)

    def check(name, ok, detail=""):
        print(("ok   " if ok else "FAIL ") + name + ("" if ok else f" ({detail})"))
        if not ok:
            fails.append(name)

    ff_exports = nm(ff, "--defined-only")
    ms_exports = nm(ms, "--defined-only")
    rt_defined = nm(rt, "--defined-only")
    rt_undefined = nm(rt, "--undefined-only")
    rt_av = {s for s in rt_undefined if s.startswith("av")}
    rt_lzxd = {s for s in rt_undefined if s.startswith("lzxd_")}
    facts.update(ffmpeg_exports=len(ff_exports), runtime_av_imports=sorted(rt_av))
    check(f"libffmpeg.so exports only av* names ({len(ff_exports)})", all(s.startswith("av") for s in ff_exports),
          sorted(s for s in ff_exports if not s.startswith("av"))[:10])
    check("every av* import of librexruntime.so is exported by libffmpeg.so", rt_av <= ff_exports,
          sorted(rt_av - ff_exports))
    check("librexruntime.so imports exactly the recorded Windows FFmpeg functions",
          rt_av == set(rec["ffmpeg"]["imported_by_rexruntime"]),
          f"extra {sorted(rt_av - set(rec['ffmpeg']['imported_by_rexruntime']))}, "
          f"missing {sorted(set(rec['ffmpeg']['imported_by_rexruntime']) - rt_av)}")
    check("librexruntime.so defines no av*/ff* symbol", not any(s.startswith(("av_", "avpriv_", "ff_")) for s in rt_defined),
          sorted(s for s in rt_defined if s.startswith(("av_", "avpriv_", "ff_")))[:10])
    check("libmspack.so exports exactly the recorded lzxd_* set", ms_exports == set(rec["libmspack"]["exports"]),
          sorted(ms_exports ^ set(rec["libmspack"]["exports"])))
    check("librexruntime.so imports only recorded lzxd_* functions", rt_lzxd <= ms_exports, sorted(rt_lzxd - ms_exports))
    if a.windows_list:
        win = set(re.findall(r"^\s*(av[A-Za-z0-9_]*)\s*(?:DATA)?\s*$", a.windows_list.read_text(encoding="utf-8"), re.M))
        facts.update(windows_exports=len(win), linux_only=sorted(ff_exports - win), windows_only=sorted(win - ff_exports))
        print(f"info Windows .def {len(win)} names; Linux {len(ff_exports)}; Linux-only {facts['linux_only']}; "
              f"Windows-only {facts['windows_only']}")
    verdict = "PASS" if not fails else "FAIL"
    if a.json:
        a.json.write_text(json.dumps({"verdict": verdict, "failed": fails, **facts}, indent=1) + "\n", encoding="utf-8")
    print(f"R3HD_LGPL_SO {verdict} ffmpeg_exports={len(ff_exports)} runtime_av_imports={len(rt_av)}")
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
