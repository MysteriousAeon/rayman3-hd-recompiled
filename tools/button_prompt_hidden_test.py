"""Bounded D-199 hidden verification through existing M34/M9/M6 wrappers only.

Four pairs of private captures (two per process), plus an uncaptured unknown-ID
fallback. Tutorial captures use an explicitly synthetic text specimen in a copied
intro_10 save; they are not played progression or natural tutorial-trigger proof.
Run the asset audit first and supply its private plan and a private text-only
specimen plan. No physical controller is opened, no desktop input is sent.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("tag")
    ap.add_argument("--plan", type=Path, required=True)
    ap.add_argument("--specimen-plan", type=Path, required=True)
    ap.add_argument("--case", action="append", choices=("menu_auto_ps", "menu_manual_xbox",
        "tutorial_auto_xbox", "tutorial_manual_ps", "unknown"), help="run only named steps; use a fresh tag")
    a = ap.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_-]+", a.tag):
        ap.error("invalid tag")
    for p in (a.plan, a.specimen_plan):
        if not p.is_file():
            ap.error(f"missing private plan: {p}")
    work = ROOT / "private/work/button_prompts" / a.tag
    work.mkdir(parents=True, exist_ok=False)
    cases = (("menu_auto_ps", "auto", "playstation", "playstation", "title"),
             ("menu_manual_xbox", "xbox", "playstation", "xbox", "title"),
             ("tutorial_auto_xbox", "auto", "xbox", "xbox", "entry"),
             ("tutorial_manual_ps", "playstation", "xbox", "playstation", "entry"),
             ("unknown", "auto", "unknown", "xbox", "unknown"))
    results = []
    for case, preference, identity, expected, mode in cases:
        if a.case and case not in a.case:
            continue
        name = f"bp_{a.tag}_{case}"
        env = dict(os.environ, R3HD_BUTTON_PROMPTS=preference, R3HD_BUTTON_PROMPTS_TEST=identity,
                   R3HD_BUTTON_PROMPTS_PLAN=str(a.plan.resolve()))
        env.pop("R3HD_BUTTON_PROMPTS_EFFECTIVE", None)
        env.pop("R3HD_MODS_PLAN", None)
        print(f"BUTTON_PROMPT_HIDDEN starting={name}", flush=True)
        if mode == "unknown":
            steps = work / "unknown.txt"
            steps.write_text("log R3HD prompts style=xbox policy=launch-time 60\nwait 1\n")
            cmd = [sys.executable, str(ROOT / "tools/m9_license_run.py"), name, str(steps),
                   "--license-mask", "1", "--seconds", "70", "--user-root", name]
        else:
            cmd = [sys.executable, str(ROOT / "tools/m34_loc_game.py"), mode]
            if mode == "entry":
                cmd += ["intro_10_fresh", name, "config/m34/intro10_tutorial.txt", "--plan",
                        str(a.specimen_plan.resolve())]
            else:
                cmd += [name, "config/m34/menu_quit.txt"]
        with (work / f"{case}.log").open("w") as log:
            result = subprocess.run(cmd, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
        runtime = ROOT / "private/work/m6_runs" / name / "runtime.log"
        text = runtime.read_text(errors="replace") if runtime.is_file() else ""
        ok = (result.returncode == 0 and f"R3HD prompts launch_selection={expected} published=true" in text
              and f"R3HD prompts style={expected} policy=launch-time" in text
              and "M23 haptics policy=suppressed physical_pad_drivers=none" in text)
        results.append({"run": name, "exit": result.returncode, "expected": expected, "pass": ok})
        (work / "results.json").write_text(json.dumps(results, indent=2))
        print(f"BUTTON_PROMPT_HIDDEN run={name} {'PASS' if ok else 'FAIL'}", flush=True)
        if not ok:
            return 1  # stop; never start another process after a failed step
    runs = [r["run"] for r in results]
    for judge in ("m21_regression.py", "m22_regression.py", "m23_haptics_regression.py"):
        with (work / f"{judge}.log").open("w") as log:
            result = subprocess.run([sys.executable, str(ROOT / "tools" / judge), "--run", *runs],
                                    cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
        if result.returncode:
            return result.returncode
    print(f"BUTTON_PROMPT_HIDDEN PASS runs={len(results)}; human visual acceptance pending")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
