#!/usr/bin/env python3
"""M33 (D-070): the data-only mod override in the running game, hidden. Six runs from the title to the main menu
(config/m33/menu_mod.txt, two frames each), all through tools/m9_license_run.py (hidden window, muted, no physical
controller, an isolated test profile under private/work/m9_profiles), with mods managed by tools/r3hd_mods.py in a
private mods folder:

  base      no plan (the runtime logs `M33 mods=off`)
  mod       the texture + text mod (MOD) enabled: every range of its plan served
  text      only the text mod (TEXT, two strings) enabled: the menu frame texture stays the game's own
  priority  both enabled, TEXT moved above MOD: TEXT's strings win where both change the same string
  disabled  both disabled: `plan` writes no plan, so the launch has none (as play.ps1)
  refused   MOD's plan with one recorded hash of the game's own bytes altered: the runtime refuses the whole plan

Judged from the logs (which mod served which range) and the frames (1280x720): regions of the replaced texture differ
from the baseline only where a plan applies it; sprites of other textures stay equal in every run; the text rows
change only in the runs whose plan holds them; disabled and refused equal the baseline. Each run must also pass the
M21 / M22 / M23-haptics judges. Mods folders, plans, frames and logs stay under private/ (game-derived); the two mods
given are private test mods.

usage:  m33_mod_game.py TAG --mod DIR --text-mod DIR [--seconds 120]
        m33_mod_game.py judge TAG          (judge existing runs again)
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
RUNS = ROOT / "private" / "work" / "m6_runs"
WORK = ROOT / "private" / "work" / "m33"
STEPS = ROOT / "config" / "m33" / "menu_mod.txt"
CASES = ("base", "mod", "text", "priority", "disabled", "refused")
# Frame regions at 1280x720 (x0, y0, x1, y1), from the M33 baseline frame (cursor on Help & Options).
TEXTURE = {  # texture menu\mnu_xb512_en (the menu frame, the stone panel, the score plate's backing)
    "frame_left": (8, 120, 100, 600),
    "frame_right": (1010, 440, 1270, 700),
    "panel": (160, 500, 640, 590),
}
ROWS = {  # menu words, centred at x 520, rows 50 px apart
    "row_load": (430, 186, 610, 220),
    "row_options": (390, 238, 650, 272),
    "row_album": (430, 288, 610, 322),
    "row_achievements": (400, 340, 640, 372),
    "row_exit": (410, 440, 630, 474),
}
SPRITES = {  # other textures: gear bolts, a round button, the two side plates
    "gear_bolt": (535, 642, 580, 680),
    "gear_eye": (695, 652, 750, 700),
    "round_button": (955, 448, 990, 482),
    "plate_left": (128, 336, 164, 382),
    "plate_right": (848, 370, 882, 418),
}
SELECTED = "row_options"  # the menu cursor's row: its highlight pulses
# The highlight is an ellipse sized to the selected word: a word of another width moves its edge into the rows above
# and below (E-170: "Album" glyphs identical, the glow behind them not). Those rows prove nothing when the selected
# word changes; they still must change when their own word does.
NEXT_TO_SELECTED = ("row_load", "row_album")
# What each run changes against the baseline (the rest must stay equal).
EXPECT = {
    "mod": set(TEXTURE) | set(ROWS),          # the texture lies behind every row as well
    "text": {"row_load", "row_options"},
    "priority": set(TEXTURE) | set(ROWS),
    "disabled": set(),
    "refused": set(),
}


def mods(margs, *extra):
    r = subprocess.run([sys.executable, str(TOOLS / "r3hd_mods.py"), *extra, "--json", *margs], cwd=ROOT,
                       capture_output=True, text=True)
    out = json.loads(r.stdout)
    if out.get("result") != "ok":
        raise SystemExit(f"r3hd_mods.py {' '.join(extra)} refused: {out}")
    return out


def run_case(tag, case, plan, seconds):
    run = f"m33_{tag}_{case}"
    env = dict(os.environ)
    env.pop("R3HD_MODS_PLAN", None)
    if plan:
        env["R3HD_MODS_PLAN"] = str(plan)
    r = subprocess.run([sys.executable, str(TOOLS / "m9_license_run.py"), run, str(STEPS), "--license-mask", "1",
                        "--seconds", str(seconds), "--user-root", f"m33_{tag}_{case}"], cwd=ROOT, env=env)
    print(f"run {run}: exit {r.returncode}", flush=True)


def frames(run):
    return sorted((RUNS / run).glob("m3_frame_*.bmp"), key=lambda p: int(re.findall(r"\d+", p.stem)[-1]))


def region_diff(a, b, box):
    from PIL import Image, ImageChops, ImageStat
    ia, ib = Image.open(a).convert("RGB").crop(box), Image.open(b).convert("RGB").crop(box)
    return round(sum(ImageStat.Stat(ImageChops.difference(ia, ib)).mean) / 3, 2)


def served(log):
    return sorted(re.findall(r"M33 mods served mod=(\S+) file=(\S+) offset=(\d+)", log))


def judge(tag, ids) -> int:
    results = []

    def check(ok, label):
        results.append(bool(ok))
        print(f"{'PASS' if ok else 'FAIL'} {label}", flush=True)

    mod_id, text_id = ids
    runs = {c: f"m33_{tag}_{c}" for c in CASES}
    logs = {c: "\n".join(p.read_text(errors="replace") for p in sorted((RUNS / r).glob("runtime*.log")))
            for c, r in runs.items()}
    for c in ("base", "disabled"):
        check("M33 mods=off" in logs[c] and "M33 mods state=" not in logs[c], f"{c}: no plan, nothing loaded")
    sv = {c: served(logs[c]) for c in ("mod", "text", "priority")}
    for c, n in (("mod", 5), ("text", 2), ("priority", 5)):
        m = re.search(r"M33 mods state=active mods=(\d+) files=(\d+) ranges=(\d+)", logs[c])
        check("M33 mods=plan" in logs[c] and m and int(m.group(3)) == n and len(sv[c]) == n,
              f"{c}: plan active with {n} ranges, every range served ({m.group(0) if m else 'no active line'})")
    check({s[0] for s in sv["mod"]} == {mod_id} and {s[0] for s in sv["text"]} == {text_id},
          "mod / text: each range served by its own mod")
    by = {s[2]: s[0] for s in sv["priority"]}
    check(by.get("143992") == text_id and by.get("144064") == text_id and by.get("144168") == mod_id
          and [s[0] for s in sv["priority"] if s[1] == "fix.btf"] == [mod_id, mod_id],
          f"priority: the higher mod serves the shared strings, the other mod the rest ({by})")
    check(re.search(r"M33 mods state=refused reason=game_bytes_hash", logs["refused"])
          and "M33 mods served" not in logs["refused"], "refused: the altered plan is refused as a whole, nothing served")
    fr = {c: frames(r) for c, r in runs.items()}
    if not all(len(v) >= 2 for v in fr.values()):
        check(False, f"two frames per run ({ {c: len(v) for c, v in fr.items()} })")
    else:
        regions = {**TEXTURE, **ROWS, **SPRITES}
        table = {n: {c: region_diff(fr["base"][1], fr[c][1], box) for c in EXPECT} for n, box in regions.items()}
        for n in regions:
            print(f"  {n:17s} " + "  ".join(f"{c} {table[n][c]:6.2f}" for c in EXPECT), flush=True)
        # The selected row (Help & Options) carries a pulsing highlight whose phase depends on timing (E-170: 0 in a
        # disabled run, 44 in a refused one with identical words); it is never used as evidence of equality.
        steady = [n for n in regions if n != SELECTED]
        noise = max(table[n][c] for n in steady for c in ("disabled", "refused"))
        for c, changed in EXPECT.items():
            same = [n for n in steady if n not in changed and not (c in ("text", "priority") and n in NEXT_TO_SELECTED)]
            check(all(table[n][c] >= max(8.0, 4 * noise) for n in changed),
                  f"{c}: changes {sorted(changed) or 'nothing'} (smallest {min([table[n][c] for n in changed], default=0)}, "
                  f"noise {noise})")
            check(all(table[n][c] <= max(3.0, 2 * noise) for n in same),
                  f"{c}: leaves {len(same)} other regions equal to the baseline (largest {max(table[n][c] for n in same)})")
        prio_vs_mod = region_diff(fr["mod"][1], fr["priority"][1], ROWS["row_options"])
        far = [n for n in regions if n not in (SELECTED,) + NEXT_TO_SELECTED]
        other_vs_mod = max(region_diff(fr["mod"][1], fr["priority"][1], {**TEXTURE, **ROWS, **SPRITES}[n]) for n in far)
        check(prio_vs_mod >= 8 and other_vs_mod <= max(3.0, 2 * noise),
              f"priority: the Help & Options word differs from the mod run, everything away from it is equal "
              f"({prio_vs_mod} vs {other_vs_mod})")
        (WORK / f"{tag}_judge.json").write_text(json.dumps(table, indent=2) + "\n")
    for judge_tool in ("m21_regression.py", "m22_regression.py", "m23_haptics_regression.py"):
        r = subprocess.run([sys.executable, str(TOOLS / judge_tool), "--run", *runs.values()], cwd=ROOT,
                           capture_output=True, text=True)
        check(r.returncode == 0, f"{judge_tool} --run (all six runs)")
    n = results.count(False)
    print(f"M33_MOD_GAME {'PASS' if not n else 'FAIL'} {len(results) - n}/{len(results)}", flush=True)
    return 1 if n else 0


def mod_id(d: Path) -> str:
    return json.loads((d / "mod.json").read_text(encoding="utf-8"))["id"]


def main() -> int:
    if len(sys.argv) == 3 and sys.argv[1] == "judge":
        ids = json.loads((WORK / sys.argv[2] / "ids.json").read_text())
        return judge(sys.argv[2], ids)
    ap = argparse.ArgumentParser()
    ap.add_argument("tag")
    ap.add_argument("--mod", type=Path, required=True)
    ap.add_argument("--text-mod", type=Path, required=True)
    ap.add_argument("--seconds", type=int, default=120)
    a = ap.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_]+", a.tag):
        ap.error("TAG: letters, digits, underscore")
    home = WORK / a.tag
    if home.exists():
        shutil.rmtree(home)
    margs = ["--mods-root", str(home / "mods"), "--cache", str(home / "cache")]
    ids = [mod_id(a.mod), mod_id(a.text_mod)]
    home.mkdir(parents=True)
    (home / "ids.json").write_text(json.dumps(ids))
    mods(margs, "import", str(a.mod), "--enable")
    mods(margs, "import", str(a.text_mod))

    def plan(case):
        # Non-ASCII folder names (a Turkish home folder): the runtime must read R3HD_MODS_PLAN and the plan's paths
        # as Unicode (M33 review).
        out = mods(margs, "plan", "--out", str(home / f"plan_{case}_çğ"))
        return Path(out["plan"]) if out.get("plan") else None

    run_case(a.tag, "base", None, a.seconds)
    mod_plan = plan("mod")
    run_case(a.tag, "mod", mod_plan, a.seconds)
    mods(margs, "disable", ids[0])
    mods(margs, "enable", ids[1])
    run_case(a.tag, "text", plan("text"), a.seconds)
    mods(margs, "enable", ids[0])
    mods(margs, "move", ids[1], "top")
    run_case(a.tag, "priority", plan("priority"), a.seconds)
    mods(margs, "disable", ids[0])
    mods(margs, "disable", ids[1])
    if plan("disabled"):
        raise SystemExit("disabled mods still produced a plan")
    run_case(a.tag, "disabled", None, a.seconds)
    lines = mod_plan.read_text(encoding="utf-8").splitlines()
    i = next(k for k, ln in enumerate(lines) if ln.startswith("range "))
    f = lines[i].split(" ")
    f[4] = f"{int(f[4], 16) ^ 1:016x}"  # the recorded hash of the game's own bytes, altered by one bit
    lines[i] = " ".join(f)
    bad = mod_plan.with_name("refused_plan.txt")
    bad.write_text("\n".join(lines) + "\n", encoding="utf-8")
    run_case(a.tag, "refused", bad, a.seconds)
    return judge(a.tag, ids)


if __name__ == "__main__":
    sys.exit(main())
