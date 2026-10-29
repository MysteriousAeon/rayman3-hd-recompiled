#!/usr/bin/env python3
"""M35: movie subtitle (`VS.sub`) mods in the running game, hidden. A run starts at the title on a working copy of a
registered save entry's profile (m12_save_entry.py, D-039) and runs a step file that may hold `frame` steps (at most
eight per process), all through tools/m9_license_run.py (hidden window, muted, no physical controller). With --plan
the run's game-file reads go through a mod plan of tools/r3hd_mods.py (R3HD_MODS_PLAN); without it the run has none
(`M33 mods=off`).

usage:
  m35_sub_game.py run RUN STEPS.txt --entry NAME [--plan PLAN] [--seconds N]     from the title, the entry's profile
  m35_sub_game.py entry RUN TAIL.txt --entry NAME [--plan PLAN] [--seconds N]   Load the entry's save, then TAIL
  m35_sub_game.py suite TAG --mod DIR|ZIP   a subtitle mod in the Otto movie (gallery title en.213) (menu10.bik, VS.sub movie
                                            42) from the Bonus > Cinematic page of knaar_20_human: off / tr / bad
  m35_sub_game.py judge TAG                 judge a suite's runs again (M35_SUB_GAME)
  m35_sub_game.py pcjudge TAG               judge `m34_loc_game.py texsuite TAG` for a real converted PC texture
                                            (M35_PC_TEX: changed pixels around Rayman, none elsewhere or disabled)
Frames, logs and plans are game-derived: private/ only.
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
WORK = ROOT / "private" / "work" / "m35"


def one_run(run_name: str, steps: Path, entry_name: str, plan, seconds: int = 0, load: bool = False,
            audio_after: int = 0, menu_frame: bool = False) -> int:
    env = dict(os.environ)
    for k in ("R3HD_MODS_PLAN", "R3HD_M22_DRAW_TRACE"):
        env.pop(k, None)
    if plan:
        plan = Path(plan)
        if not plan.is_file():
            raise SystemExit(f"no plan at {plan}")
        env["R3HD_MODS_PLAN"] = str(plan.resolve())
    entry = m12.load_entry(entry_name)
    lines = [ln.split("#", 1)[0].strip() for ln in steps.read_text(encoding="utf-8").splitlines()]
    lines = [ln for ln in lines if ln]
    frames = sum(1 for ln in lines if ln.split()[0] == "frame")
    frames += int(menu_frame)
    waits = sum(float(ln.split()[1]) for ln in lines if ln.split()[0] == "wait")
    if not m12.NAME_RE.fullmatch(run_name) or not 0 <= frames <= 8:
        raise SystemExit("invalid RUN, or more than eight frame steps")
    seconds = seconds or int(waits) + 95
    if (m12.RUNS / run_name).exists() or (m12.PROFILES / run_name).exists():
        raise SystemExit(f"run or profile already exists for {run_name}")
    if not m12.stored_profile_matches(entry):
        raise SystemExit(f"stored profile of {entry_name} no longer matches entry.json")
    shutil.copytree(m12.SAVES / entry_name / "profile", m12.PROFILES / run_name)
    if load:   # the title's Load menu first (the save's level from its start), then the tail
        m12.STEPS.mkdir(parents=True, exist_ok=True)
        full = m12.STEPS / f"{run_name}.txt"
        prefix = m12.load_steps(0)[:-1]
        if menu_frame:
            prefix.insert(prefix.index("wait 12") + 1, "frame main_menu")
        full.write_text("\n".join(prefix + lines) + "\n", encoding="ascii")
        steps = full
        seconds += 30
    command = m12.driver_command(run_name, steps, seconds, run_name)
    command += ["--audio-after", str(audio_after)]
    log = WORK / f"{run_name}.driver.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("w", encoding="utf-8") as out:
        try:
            code = subprocess.run(command, cwd=ROOT, env=env, stdout=out, stderr=subprocess.STDOUT,
                                  timeout=seconds + 300).returncode
        except subprocess.TimeoutExpired:
            code = None
    got = len(list((m12.RUNS / run_name).glob("m3_frame_*.bmp")))
    reasons = []
    if code is None:
        reasons.append("driver timeout")
    elif code:
        reasons.append(f"driver exit code {code}")
    if got != frames:
        reasons.append(f"frames {got} of {frames}")
    print(f"M35_SUB_RUN {'FAIL' if reasons else 'PASS'} run={run_name} frames={got} plan={'yes' if plan else 'no'}"
          + (f" reasons={';'.join(reasons)}" if reasons else ""), flush=True)
    return 1 if reasons else 0


TOOLS = ROOT / "tools"
OTTO = ROOT / "config" / "m35" / "cinematic_otto.txt"
ENTRY = "knaar_20_human"
CASES = ("off", "tr", "bad")
# Frame boxes at 1280x720 from the discovery run (E-179): the subtitle banner (one or two lines) and the movie above it.
BANNER = (150, 545, 1130, 705)
SCENE = (0, 0, 1280, 560)
CUE_FRAMES = (2, 4, 5)   # frames cue0, cue1 (shows cue 2), cue3 (shows cue 4) of cinematic_otto.txt
GAP_FRAME = 3


def mods(margs, *extra):
    r = subprocess.run([sys.executable, str(TOOLS / "r3hd_mods.py"), *margs, *extra, "--json"], cwd=ROOT,
                       capture_output=True, text=True, encoding="utf-8")
    out = json.loads(r.stdout)
    if out.get("result") != "ok":
        raise SystemExit(f"r3hd_mods.py {' '.join(extra)} refused: {out}")
    return out


def suite_run(tag: str, mod: Path) -> int:
    """off (the mod imported but disabled: no plan), tr (enabled), bad (its plan with the VS.sub range's recorded game
    hash altered: refused as a whole). The same steps each time."""
    home = WORK / tag
    if home.exists():
        shutil.rmtree(home)
    home.mkdir(parents=True)
    margs = ["--mods-root", str(home / "mods"), "--cache", str(home / "cache")]
    mods(margs, "import", str(mod))
    mid = mods(margs, "list")["mods"][0]["id"]
    (home / "ids.json").write_text(json.dumps({"mod": mid}))
    runs = {c: f"m35_{tag}_{c}" for c in CASES}
    if mods(margs, "plan", "--out", str(home / "plan_off_çğ")).get("plan"):
        raise SystemExit("a disabled mod still produced a plan")
    one_run(runs["off"], OTTO, ENTRY, None, load=True)
    mods(margs, "enable", mid)
    plan = Path(mods(margs, "plan", "--out", str(home / "plan_tr_çğ"))["plan"])
    one_run(runs["tr"], OTTO, ENTRY, plan, load=True)
    lines = plan.read_text(encoding="utf-8").splitlines()
    files = [ln for ln in lines if ln.startswith("file ")]
    vs = next(i for i, ln in enumerate(files) if ln.lower().endswith("vs.sub"))
    bad = []
    for ln in lines:
        f = ln.split(" ")
        if f[0] == "range" and int(f[1]) == vs:
            f[4] = f"{int(f[4], 16) ^ 1:016x}"
        bad.append(" ".join(f))
    (plan.parent / "bad_plan.txt").write_text("\n".join(bad) + "\n", encoding="utf-8")
    one_run(runs["bad"], OTTO, ENTRY, plan.parent / "bad_plan.txt", load=True)
    return suite_judge(tag)


def frames(run):
    return sorted((m12.RUNS / run).glob("m3_frame_*.bmp"), key=lambda p: int(re.findall(r"\d+", p.stem)[-1]))


def region(a, b, box):
    from PIL import Image, ImageChops, ImageStat
    ia, ib = Image.open(a).convert("RGB").crop(box), Image.open(b).convert("RGB").crop(box)
    return round(sum(ImageStat.Stat(ImageChops.difference(ia, ib)).mean) / 3, 2)


def banner_ink(path):
    """(banner rows, text pixels): rows of the box that are mostly the subtitle banner's dark blue, and the white
    pixels inside those rows (the movie behind can be nearly white, so brightness alone says nothing)."""
    from PIL import Image
    im = Image.open(path).convert("RGB").crop(BANNER)
    w, h = im.size
    px = im.load()
    rows, ink = 0, 0
    for y in range(h):
        line = [px[x, y] for x in range(w)]
        dark = sum(1 for r, g, b in line if r < 80 and g < 80 and 40 < b < 170 and b > r + 15)
        if dark >= 0.35 * w:
            rows += 1
            ink += sum(1 for r, g, b in line if min(r, g, b) > 200)
    return rows, ink


def has_subtitle(ink) -> bool:
    return ink[0] >= 20 and ink[1] >= 300


def suite_judge(tag: str) -> int:
    ids = json.loads((WORK / tag / "ids.json").read_text())
    runs = {c: f"m35_{tag}_{c}" for c in CASES}
    results = []

    def check(ok, label):
        results.append(bool(ok))
        print(f"{'PASS' if ok else 'FAIL'} {label}", flush=True)
    logs = {c: "\n".join(p.read_text(errors="replace") for p in sorted((m12.RUNS / r).glob("runtime*.log")))
            for c, r in runs.items()}
    check("M33 mods=off" in logs["off"] and "M33 mods state=" not in logs["off"], "off: no plan, nothing loaded")
    m = re.search(r"M33 mods state=active mods=(\d+) files=(\d+) ranges=(\d+)", logs["tr"])
    served = re.findall(r"M33 mods served mod=(\S+) file=(\S+) offset=(\d+)", logs["tr"])
    check(m and {s[0] for s in served} == {ids["mod"]} and "VS.sub" in {s[1] for s in served},
          f"tr: plan active, VS.sub served by {ids['mod']} ({m.group(0) if m else 'no active line'}; "
          f"files served {sorted({s[1] for s in served})})")
    check("menu10.bik" in logs["tr"] and "menu10.bik" in logs["off"] and "menu10.bik" in logs["bad"],
          "every run played VIDEOS\\menu10.bik")
    check(re.search(r"M33 mods state=refused reason=game_bytes_hash", logs["bad"]) and "M33 mods served" not in logs["bad"],
          "bad: the altered plan is refused as a whole")
    fr = {c: frames(r) for c, r in runs.items()}
    if not all(len(v) == 6 for v in fr.values()):
        check(False, f"six frames per run ({ {c: len(v) for c, v in fr.items()} })")
    else:
        for k in CUE_FRAMES:
            b_tr, b_bad = region(fr["off"][k], fr["tr"][k], BANNER), region(fr["off"][k], fr["bad"][k], BANNER)
            s_tr = region(fr["off"][k], fr["tr"][k], SCENE)
            ink = {c: banner_ink(fr[c][k]) for c in CASES}
            print(f"  frame {k}: banner off/tr {b_tr} off/bad {b_bad}; scene off/tr {s_tr}; ink {ink}", flush=True)
            check(all(has_subtitle(v) for v in ink.values()), f"frame {k}: a subtitle banner with text in every run")
            check(b_tr >= max(4.0, 3 * b_bad),
                  f"frame {k}: the Turkish subtitle differs from the English ({b_tr} against {b_bad} between the "
                  "two English runs)")
            check(b_bad <= 4.0, f"frame {k}: the refused plan shows the English subtitle ({b_bad})")
        g = {c: banner_ink(fr[c][GAP_FRAME]) for c in CASES}
        check(not any(has_subtitle(v) for v in g.values()), f"frame {GAP_FRAME}: no subtitle between cues in any run ({g})")
    for c, r in runs.items():
        for judge in ("m21_regression.py", "m23_haptics_regression.py"):
            rr = subprocess.run([sys.executable, str(TOOLS / judge), "--run", r], cwd=ROOT, capture_output=True, text=True)
            check(rr.returncode == 0, f"{c}: {judge} ({(rr.stdout.strip().splitlines() or [''])[-1]})")
    n = results.count(False)
    print(f"M35_SUB_GAME {'PASS' if not n else 'FAIL'} {len(results) - n}/{len(results)}", flush=True)
    return 1 if n else 0


RAYMAN_BOX = (560, 280, 720, 460)   # Rayman in intro_10's second M34 frame (about 32 s), 1280x720


def pc_judge(tag: str) -> int:
    """A real converted PC texture mod run with `m34_loc_game.py texsuite TAG` (runs m34_TAG_intro_off / _pc / _back):
    the second frame (deterministic in these runs) must change only around Rayman with the mod, and not at all when
    the mod is disabled again. Judged by changed pixels, since a real picture has no test pattern."""
    from PIL import Image, ImageChops
    fr = {c: frames(f"m34_{tag}_intro_{c}") for c in ("off", "pc", "back")}
    results = []

    def check(ok, label):
        results.append(bool(ok))
        print(f"{'PASS' if ok else 'FAIL'} {label}", flush=True)
    if not all(len(v) == 2 for v in fr.values()):
        check(False, f"two frames per run ({ {c: len(v) for c, v in fr.items()} })")
    else:
        def changed(a, b):
            x = ImageChops.difference(Image.open(a).convert("RGB"), Image.open(b).convert("RGB")).convert("L")
            full = sum(1 for v in x.tobytes() if v > 40)
            return full, sum(1 for v in x.crop(RAYMAN_BOX).tobytes() if v > 40)
        pc, back = changed(fr["off"][1], fr["pc"][1]), changed(fr["off"][1], fr["back"][1])
        check(pc[1] >= 200 and pc[0] - pc[1] <= max(50, pc[1] // 10),
              f"pc: Rayman changes with the mod, the rest of the frame does not (changed {pc[0]}, around Rayman {pc[1]})")
        check(back == (0, 0) or back[0] <= 20, f"back: disabled again, the frame equals the baseline (changed {back[0]})")
    n = results.count(False)
    print(f"M35_PC_TEX {'PASS' if not n else 'FAIL'} {len(results) - n}/{len(results)}", flush=True)
    return 1 if n else 0


def main() -> int:
    if len(sys.argv) > 2 and sys.argv[1] == "pcjudge":
        return pc_judge(sys.argv[2])
    if len(sys.argv) > 1 and sys.argv[1] in ("suite", "judge"):
        ap = argparse.ArgumentParser()
        ap.add_argument("mode")
        ap.add_argument("tag")
        ap.add_argument("--mod", type=Path)
        a = ap.parse_args()
        if not m12.NAME_RE.fullmatch(a.tag):
            ap.error("invalid TAG")
        if a.mode == "suite":
            if not a.mod:
                ap.error("suite TAG --mod DIR|ZIP")
            return suite_run(a.tag, a.mod)
        return suite_judge(a.tag)
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=("run", "entry"))
    ap.add_argument("args", nargs="+")
    ap.add_argument("--entry", required=True)
    ap.add_argument("--plan", type=Path)
    ap.add_argument("--seconds", type=int, default=0)
    ap.add_argument("--audio-after", type=int, default=0, help="start the existing muted 10 s PCM capture after N seconds")
    ap.add_argument("--menu-frame", action="store_true", help="entry mode: also capture the main menu before Load")
    a = ap.parse_args()
    if len(a.args) != 2:
        ap.error(f"{a.mode} RUN STEPS.txt")
    if a.audio_after < 0:
        ap.error("--audio-after must be nonnegative")
    if a.menu_frame and a.mode != "entry":
        ap.error("--menu-frame needs entry mode")
    return one_run(a.args[0], Path(a.args[1]), a.entry, a.plan, a.seconds, load=a.mode == "entry",
                   audio_after=a.audio_after, menu_frame=a.menu_frame)


if __name__ == "__main__":
    sys.exit(main())
