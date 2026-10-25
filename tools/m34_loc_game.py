#!/usr/bin/env python3
"""M34: localization and converted-texture mods in the running game, hidden. A run loads a registered save entry
(m12_save_entry.py, D-039) through the title's own menu on a working copy of its profile, or goes from the title to
the main menu, then runs a step tail that may hold `frame` steps (at most eight per process), all through
tools/m9_license_run.py (hidden window, muted, no physical controller). With --plan the run's game-file reads go
through a mod plan of tools/r3hd_mods.py (R3HD_MODS_PLAN); without it the run has none (`M33 mods=off`).

usage:
  m34_loc_game.py entry NAME RUN TAIL.txt [--plan PLAN] [--seconds N]   from a save entry
  m34_loc_game.py title RUN STEPS.txt [--plan PLAN] [--seconds N]        from the title (an isolated fresh profile)
  m34_loc_game.py suite TAG --mod DIR [--copies]   the localization suite (below) with one localization mod
  m34_loc_game.py judge TAG                         judge a suite's runs again
  m34_loc_game.py texsuite TAG --mod DIR            a converted PC texture mod in intro_10: off / on / off again
  m34_loc_game.py texjudge TAG
Frames, logs and plans are game-derived: private/ only.

The suite (mods managed by tools/r3hd_mods.py in private/work/m34/TAG, plans in a folder with non-ASCII letters):
  title_off    the mod imported but disabled: no plan (the fallback)       config/m34/menu_quit.txt
  title_tr     the mod enabled: main menu words and the quit dialog
  intro_off    intro_10_fresh, no plan: Murfy's tutorial box in English     config/m34/intro10_tutorial.txt
  intro_tr     the same with the mod: the box in Turkish
  title_bad    the mod's plan with one recorded hash of a glyph record altered: refused as a whole
  --copies adds two experiment runs, each plan keeping the glyph records of one FontRay copy only (which copy the
  title reads: RE_NOTES "M34").
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import m12_save_entry as m12  # noqa: E402

ROOT = m12.ROOT


def run(command, env, seconds, log: Path):
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("w", encoding="utf-8") as output:
        try:
            return subprocess.run(command, cwd=ROOT, env=env, stdout=output, stderr=subprocess.STDOUT,
                                  timeout=seconds + 300).returncode
        except subprocess.TimeoutExpired:
            return None


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] in ("suite", "judge", "texsuite", "texjudge"):
        return suite_main()
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=("entry", "title"))
    ap.add_argument("args", nargs="+")
    ap.add_argument("--plan", type=Path)
    ap.add_argument("--seconds", type=int, default=0)
    a = ap.parse_args()
    env = dict(os.environ)
    env.pop("R3HD_MODS_PLAN", None)
    env.pop("R3HD_M22_DRAW_TRACE", None)
    if a.plan:
        if not a.plan.is_file():
            raise SystemExit(f"no plan at {a.plan}")
        env["R3HD_MODS_PLAN"] = str(a.plan.resolve())
    if a.mode == "entry":
        if len(a.args) != 3:
            ap.error("entry NAME RUN TAIL.txt")
        name, run_name, tail_path = a.args[0], a.args[1], Path(a.args[2])
        entry = m12.load_entry(name)
    else:
        if len(a.args) != 2:
            ap.error("title RUN STEPS.txt")
        name, entry, run_name, tail_path = None, None, a.args[0], Path(a.args[1])
    tail = [line.split("#", 1)[0].strip() for line in tail_path.read_text(encoding="utf-8").splitlines()]
    tail = [line for line in tail if line]
    frames = sum(1 for line in tail if line.split()[0] == "frame")
    waits = sum(float(line.split()[1]) for line in tail if line.split()[0] == "wait")
    if not m12.NAME_RE.fullmatch(run_name) or not 0 <= frames <= 8:
        raise SystemExit("invalid RUN, or more than eight frame steps")
    seconds = a.seconds or int(waits) + 95
    if (m12.RUNS / run_name).exists() or (m12.PROFILES / run_name).exists():
        raise SystemExit(f"run or profile already exists for {run_name}")
    if entry is not None:
        if not m12.stored_profile_matches(entry):
            raise SystemExit(f"stored profile of {name} no longer matches entry.json")
        steps = m12.STEPS / f"{run_name}.txt"
        shutil.copytree(m12.SAVES / name / "profile", m12.PROFILES / run_name)
        m12.STEPS.mkdir(parents=True, exist_ok=True)
        steps.write_text("\n".join(m12.load_steps(0)[:-1] + tail) + "\n", encoding="ascii")
        command = m12.driver_command(run_name, steps, seconds, run_name)
    else:
        steps = tail_path
        command = [sys.executable, str(ROOT / "tools" / "m9_license_run.py"), run_name, str(steps), "--license-mask",
                   "1", "--seconds", str(seconds), "--user-root", run_name]
    code = run(command, env, seconds, ROOT / "private" / "work" / "m34" / f"{run_name}.driver.log")
    got = len(list((m12.RUNS / run_name).glob("m3_frame_*.bmp")))
    reasons = []
    if code is None:
        reasons.append("driver timeout")
    elif code:
        reasons.append(f"driver exit code {code}")
    if got != frames:
        reasons.append(f"frames {got} of {frames}")
    if entry is not None:
        facts = m12.evaluate_entry(entry, run_name)
        reasons += [r for r in facts["reasons"] if "frame captures" not in r]
    print(f"M34_LOC_RUN {'FAIL' if reasons else 'PASS'} run={run_name} frames={got} plan={'yes' if a.plan else 'no'}"
          + (f" reasons={';'.join(reasons)}" if reasons else ""), flush=True)
    return 1 if reasons else 0


WORK = ROOT / "private" / "work" / "m34"
MENU = ROOT / "config" / "m34" / "menu_quit.txt"
INTRO = ROOT / "config" / "m34" / "intro10_tutorial.txt"
TOOLS = ROOT / "tools"


def mods(margs, *extra):
    r = subprocess.run([sys.executable, str(TOOLS / "r3hd_mods.py"), *extra, "--json", *margs], cwd=ROOT,
                       capture_output=True, text=True)
    out = json.loads(r.stdout)
    if out.get("result") != "ok":
        raise SystemExit(f"r3hd_mods.py {' '.join(extra)} refused: {out}")
    return out


def plan_variant(plan: Path, out: Path, keep):
    """A copy of a plan keeping the range lines `keep(fields)` accepts (the end line recounted)."""
    lines = plan.read_text(encoding="utf-8").splitlines()
    body = [ln for ln in lines if not ln.startswith("range ") or keep(ln.split(" "))]
    n = sum(1 for ln in body if ln.startswith("range "))
    body = [re.sub(r"^end (\d+) \d+$", lambda m: f"end {m.group(1)} {n}", ln) for ln in body]
    out.write_text("\n".join(body) + "\n", encoding="utf-8")
    return out


def self_run(args, plan=None):
    cmd = [sys.executable, str(Path(__file__).resolve()), *args] + (["--plan", str(plan)] if plan else [])
    r = subprocess.run(cmd, cwd=ROOT)
    print(f"run {' '.join(args[:2])}: exit {r.returncode}", flush=True)


def runs_of(tag, copies):
    names = ["title_off", "title_tr", "intro_off", "intro_tr", "title_bad"] + (["title_copy1", "title_copy2"] if copies else [])
    return {n: f"m34_{tag}_{n}" for n in names}


def suite_run(tag, mod_dir: Path, copies: bool) -> int:
    home = WORK / tag
    if home.exists():
        shutil.rmtree(home)
    home.mkdir(parents=True)
    margs = ["--mods-root", str(home / "mods"), "--cache", str(home / "cache")]
    mid = json.loads((mod_dir / "mod.json").read_text(encoding="utf-8"))["id"]
    (home / "ids.json").write_text(json.dumps({"mod": mid, "copies": copies}))
    mods(margs, "import", str(mod_dir))

    def plan(case):
        out = mods(margs, "plan", "--out", str(home / f"plan_{case}_çğ"))
        return Path(out["plan"]) if out.get("plan") else None
    runs = runs_of(tag, copies)
    if plan("off"):
        raise SystemExit("a disabled mod still produced a plan")
    self_run(["title", runs["title_off"], str(MENU)])
    self_run(["entry", "intro_10_fresh", runs["intro_off"], str(INTRO)])
    mods(margs, "enable", mid)
    p = plan("tr")
    self_run(["title", runs["title_tr"], str(MENU)], p)
    self_run(["entry", "intro_10_fresh", runs["intro_tr"], str(INTRO)], p)

    def alter_first_glyph(f):
        if f[0] == "range" and not alter_first_glyph.done and int(f[3]) == 14:
            f[4] = f"{int(f[4], 16) ^ 1:016x}"   # the recorded hash of the game's own record bytes, one bit off
            alter_first_glyph.done = True
        return True
    alter_first_glyph.done = False
    lines = p.read_text(encoding="utf-8").splitlines()
    bad = []
    for ln in lines:
        f = ln.split(" ")
        alter_first_glyph(f)
        bad.append(" ".join(f))
    (p.parent / "bad_plan.txt").write_text("\n".join(bad) + "\n", encoding="utf-8")
    self_run(["title", runs["title_bad"], str(MENU)], p.parent / "bad_plan.txt")
    if copies:
        # glyph records are 14-byte ranges; FontRay copy 1 holds them at 0x2B24 + code * 14, copy 2 at 0x50F0 + ...
        t1, t2 = 0x2AF2 + 50, 0x50BE + 50
        for name, drop in (("title_copy1", t2), ("title_copy2", t1)):
            v = plan_variant(p, p.parent / f"{name}.txt",
                             lambda f, drop=drop: not (int(f[3]) == 14 and drop <= int(f[2]) < drop + 256 * 14))
            self_run(["title", runs[name], str(MENU)], v)
    return suite_judge(tag)


def frames(run):
    return sorted((m12.RUNS / run).glob("m3_frame_*.bmp"), key=lambda p: int(re.findall(r"\d+", p.stem)[-1]))


def region_diff(a, b, box):
    from PIL import Image, ImageChops, ImageStat
    ia, ib = Image.open(a).convert("RGB").crop(box), Image.open(b).convert("RGB").crop(box)
    return round(sum(ImageStat.Stat(ImageChops.difference(ia, ib)).mean) / 3, 2)


# Frame regions at 1280x720 (x0, y0, x1, y1), from the M33 / M34 baseline frames. Main menu rows are 50 px apart,
# centred at x 520; the menu cursor sits on New (its highlight pulses).
MENU_ROWS = {"new": (430, 136, 610, 170), "load": (430, 186, 610, 220), "options": (390, 238, 650, 272),
             "album": (470, 290, 580, 322), "achievements": (380, 340, 660, 372), "leaderboards": (380, 390, 660, 422),
             "exit": (390, 440, 650, 474), "validate": (1000, 498, 1120, 530), "score": (950, 140, 1120, 176)}
MENU_SAME = {"gear_bolt": (535, 642, 580, 680), "gear_eye": (695, 652, 750, 700), "round_button": (955, 448, 990, 482),
             "plate_left": (128, 336, 164, 382), "frame_left": (8, 120, 100, 600)}
QUIT_TEXT = (330, 250, 950, 400)
QUIT_SAME = {"frame_left": (8, 120, 100, 600), "gear_bolt": (535, 642, 580, 680)}
TUTORIAL_TEXT = (240, 535, 1000, 580)  # the line itself (the box around it is mostly unchanged)
INTRO_SCENE = (0, 0, 1280, 500)


def suite_judge(tag) -> int:
    ids = json.loads((WORK / tag / "ids.json").read_text())
    runs = runs_of(tag, ids["copies"])
    results = []

    def check(ok, label):
        results.append(bool(ok))
        print(f"{'PASS' if ok else 'FAIL'} {label}", flush=True)
    logs = {c: "\n".join(p.read_text(errors="replace") for p in sorted((m12.RUNS / r).glob("runtime*.log")))
            for c, r in runs.items()}
    for c in ("title_off", "intro_off"):
        check("M33 mods=off" in logs[c] and "M33 mods state=" not in logs[c], f"{c}: no plan, nothing loaded")
    for c in ("title_tr", "intro_tr") + tuple(c for c in runs if c.startswith("title_copy")):
        m = re.search(r"M33 mods state=active mods=(\d+) files=(\d+) ranges=(\d+)", logs[c])
        served = re.findall(r"M33 mods served mod=(\S+) file=(\S+) offset=(\d+)", logs[c])
        files = {s[1] for s in served}
        check(m and len(served) == int(m.group(3)) and {s[0] for s in served} == {ids["mod"]}
              and {"fix.lvl", "fix.btf"} <= files,
              f"{c}: plan active, every range served by {ids['mod']} in fix.lvl and fix.btf "
              f"({m.group(0) if m else 'no active line'}, served {len(served)})")
    check(re.search(r"M33 mods state=refused reason=game_bytes_hash", logs["title_bad"])
          and "M33 mods served" not in logs["title_bad"], "title_bad: the altered plan is refused as a whole")
    fr = {c: frames(r) for c, r in runs.items()}
    if not all(len(v) == 2 for v in fr.values()):
        check(False, f"two frames per run ({ {c: len(v) for c, v in fr.items()} })")
    else:
        table = {}
        menu = {n: {c: region_diff(fr["title_off"][0], fr[c][0], box) for c in runs if c.startswith("title")}
                for n, box in {**MENU_ROWS, **MENU_SAME}.items()}
        table["menu"] = menu
        for n in {**MENU_ROWS, **MENU_SAME}:
            print(f"  menu {n:13s} " + "  ".join(f"{c[6:]} {menu[n][c]:6.2f}" for c in menu[n]), flush=True)
        steady = [n for n in MENU_SAME]
        noise = max(menu[n]["title_bad"] for n in list(MENU_ROWS) + steady if n != "new")
        check(all(menu[n]["title_tr"] >= max(8.0, 4 * noise) for n in MENU_ROWS),
              f"title_tr: every translated menu row changes (smallest {min(menu[n]['title_tr'] for n in MENU_ROWS)}, "
              f"noise {noise})")
        check(all(menu[n]["title_tr"] <= max(3.0, 2 * noise) for n in steady),
              f"title_tr: sprites and the frame stay equal (largest {max(menu[n]['title_tr'] for n in steady)})")
        check(all(menu[n]["title_bad"] <= max(3.0, 2 * noise) for n in list(MENU_ROWS) + steady if n != "new"),
              "title_bad: equal to the baseline (the refused plan served nothing)")
        q = {c: region_diff(fr["title_off"][1], fr[c][1], QUIT_TEXT) for c in runs if c.startswith("title")}
        qs = {c: max(region_diff(fr["title_off"][1], fr[c][1], b) for b in QUIT_SAME.values()) for c in q}
        table["quit"] = {"text": q, "same": qs}
        check(q["title_tr"] >= 8 and qs["title_tr"] <= 3 and q["title_bad"] <= 3,
              f"quit dialog: the moved sentence replaces the English one ({q['title_tr']}), the rest equal "
              f"({qs['title_tr']}); refused run equal ({q['title_bad']})")
        # The first frame (6 s) always holds the box; whether it is up again at the second depends on the opening's
        # timing (E-174: shown at 32 s in one run, not in another), so the second frame is reported, not judged.
        t = [region_diff(fr["intro_off"][i], fr["intro_tr"][i], TUTORIAL_TEXT) for i in (0, 1)]
        scene = region_diff(fr["intro_off"][0], fr["intro_tr"][0], INTRO_SCENE)
        table["tutorial"] = {"text": t, "scene_first_frame": scene}
        check(t[0] >= 8 and scene <= 3, f"intro_10: the tutorial line is the Turkish one ({t[0]}), the scene above it "
              f"equal ({scene}); second frame {t[1]} (not judged)")
        if ids["copies"]:
            row = MENU_ROWS["leaderboards"]
            table["copies"] = {c: region_diff(fr["title_tr"][0], fr[c][0], row) for c in ("title_copy1", "title_copy2")}
            print(f"  copies: leaderboards row against title_tr {table['copies']} (0 = that copy is the one read)")
        (WORK / f"{tag}_judge.json").write_text(json.dumps(table, indent=2) + "\n")
    for judge_tool in ("m21_regression.py", "m22_regression.py", "m23_haptics_regression.py"):
        r = subprocess.run([sys.executable, str(TOOLS / judge_tool), "--run", *runs.values()], cwd=ROOT,
                           capture_output=True, text=True)
        check(r.returncode == 0, f"{judge_tool} --run (all {len(runs)} runs)")
    n = results.count(False)
    print(f"M34_LOC_GAME {'PASS' if not n else 'FAIL'} {len(results) - n}/{len(results)}", flush=True)
    return 1 if n else 0


def tex_runs(tag):
    return {n: f"m34_{tag}_{n}" for n in ("intro_off", "intro_pc", "intro_back")}


def tex_suite(tag, mod_dir: Path) -> int:
    """A converted PC texture mod in the game: intro_10 without it (imported, disabled), with it, and disabled again."""
    home = WORK / tag
    if home.exists():
        shutil.rmtree(home)
    home.mkdir(parents=True)
    margs = ["--mods-root", str(home / "mods"), "--cache", str(home / "cache")]
    mid = json.loads((mod_dir / "mod.json").read_text(encoding="utf-8"))["id"]
    (home / "ids.json").write_text(json.dumps({"mod": mid, "texture": True}))
    mods(margs, "import", str(mod_dir))
    runs = tex_runs(tag)

    def plan(case):
        out = mods(margs, "plan", "--out", str(home / f"plan_{case}_çğ"))
        return Path(out["plan"]) if out.get("plan") else None
    if plan("off"):
        raise SystemExit("a disabled mod still produced a plan")
    self_run(["entry", "intro_10_fresh", runs["intro_off"], str(INTRO)])
    mods(margs, "enable", mid)
    self_run(["entry", "intro_10_fresh", runs["intro_pc"], str(INTRO)], plan("pc"))
    mods(margs, "disable", mid)
    if plan("back"):
        raise SystemExit("a disabled mod still produced a plan")
    self_run(["entry", "intro_10_fresh", runs["intro_back"], str(INTRO)])
    return tex_judge(tag)


def colour_signature(path):
    """(pattern-blue pixels, magenta pixels) of a frame: the colours of r3hd_pcmod.py's test picture."""
    from PIL import Image
    im = Image.open(path).convert("RGB")
    blue = magenta = 0
    for r, g, b in im.getdata():
        if b > 150 and r < 90 and g < 130 and b - r > 100:
            blue += 1
        elif r > 110 and b > 110 and g < 70 and abs(r - b) < 80:
            magenta += 1
    return blue, magenta


def tex_judge(tag) -> int:
    ids = json.loads((WORK / tag / "ids.json").read_text())
    runs = tex_runs(tag)
    results = []

    def check(ok, label):
        results.append(bool(ok))
        print(f"{'PASS' if ok else 'FAIL'} {label}", flush=True)
    logs = {c: "\n".join(p.read_text(errors="replace") for p in sorted((m12.RUNS / r).glob("runtime*.log")))
            for c, r in runs.items()}
    for c in ("intro_off", "intro_back"):
        check("M33 mods=off" in logs[c] and "M33 mods state=" not in logs[c], f"{c}: no plan, nothing loaded")
    m = re.search(r"M33 mods state=active mods=(\d+) files=(\d+) ranges=(\d+)", logs["intro_pc"])
    served = re.findall(r"M33 mods served mod=(\S+) file=(\S+) offset=(\d+)", logs["intro_pc"])
    check(m and len(served) == int(m.group(3)) and {s[0] for s in served} == {ids["mod"]}
          and {s[1] for s in served} == {"fix.btf"},
          f"intro_pc: plan active, every range served from fix.btf by {ids['mod']} ({len(served)} served)")
    fr = {c: frames(r) for c, r in runs.items()}
    table = {}
    if not all(len(v) == 2 for v in fr.values()):
        check(False, f"two frames per run ({ {c: len(v) for c, v in fr.items()} })")
    else:
        # The opening's camera and Rayman's pose drift by a few pixels between runs (t1: two runs without the mod
        # differ by 12-14 over Rayman), so pixel differencing cannot judge a character texture. The test picture's
        # colours can: its top-right quadrant (Rayman's hoodie on this page) is a saturated blue nothing in the
        # opening has, its bottom-right (the shoes) magenta.
        sig = {c: [colour_signature(f) for f in fr[c]] for c in runs}
        line = {c: region_diff(fr["intro_off"][0], fr[c][0], TUTORIAL_TEXT) for c in ("intro_pc", "intro_back")}
        table = {"signature_blue_magenta": sig, "tutorial_line": line}
        print(f"  blue / magenta pixels per frame {sig}; tutorial line against intro_off {line}", flush=True)
        base = max(s[0] for c in ("intro_off", "intro_back") for s in sig[c])
        check(all(s[0] >= max(300, 10 * base) for s in sig["intro_pc"]),
              f"intro_pc: the converted picture is on Rayman in both frames (pattern blue {[s[0] for s in sig['intro_pc']]}"
              f" against at most {base} without the mod)")
        check(sum(s[1] for s in sig["intro_pc"]) > 3 * max(sum(s[1] for s in sig[c]) for c in ("intro_off", "intro_back")),
              "intro_pc: the bottom-right quadrant's magenta is there too (upright, not mirrored to the top)")
        check(line["intro_pc"] <= 3 and line["intro_back"] <= 3,
              f"unrelated: the HUD tutorial line is unchanged ({line})")
        check(all(s[0] <= 150 for s in sig["intro_back"]), "intro_back (disabled again): no trace of the picture")
    (WORK / f"{tag}_judge.json").write_text(json.dumps(table, indent=2) + "\n")
    for judge_tool in ("m21_regression.py", "m22_regression.py", "m23_haptics_regression.py"):
        r = subprocess.run([sys.executable, str(TOOLS / judge_tool), "--run", *runs.values()], cwd=ROOT,
                           capture_output=True, text=True)
        check(r.returncode == 0, f"{judge_tool} --run (all {len(runs)} runs)")
    n = results.count(False)
    print(f"M34_TEX_GAME {'PASS' if not n else 'FAIL'} {len(results) - n}/{len(results)}", flush=True)
    return 1 if n else 0


def suite_main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("suite", "judge", "texsuite", "texjudge"))
    ap.add_argument("tag")
    ap.add_argument("--mod", type=Path)
    ap.add_argument("--copies", action="store_true")
    a = ap.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_]+", a.tag):
        ap.error("TAG: letters, digits, underscore")
    if a.cmd == "judge":
        return suite_judge(a.tag)
    if a.cmd == "texjudge":
        return tex_judge(a.tag)
    if not a.mod:
        ap.error("--mod DIR")
    if a.cmd == "texsuite":
        return tex_suite(a.tag, a.mod)
    return suite_run(a.tag, a.mod, a.copies)


if __name__ == "__main__":
    sys.exit(main())
