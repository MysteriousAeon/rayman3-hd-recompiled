"""E-456: behavioural A/B of one script constant (D-223 `script-constant`), hidden and read-only.

Constant: intro_10, NIN_m_GenFlyIntro_10, behaviour NIN_C_FlyInit, script 0, node 101 = int 30 in
`dsgvar#24 = 30` (operator 0x0C, assignment; node 100 = designer variable 24). Role (RE_NOTES "M5 completion" and
"Script constants"): variable 24 is the flight's target speed; NIN_C_FlyMvt script 1 eases the speed variable 23
toward it (`v23 = callB#2D(v23, 0.94, v24)`) and script 0 moves the generator along its waypoint graph by
`v23 * callB#45` per frame. The arrival macro later assigns 45 (the loop arc), so the constant governs the first
flight segment. Rayman is carried by this generator; nothing is pressed.

Two cases, each one hidden run (tools/m9_license_run.py: hidden window, muted, no physical controller, isolated
test profile, `-level:intro_10` isolated test-only entry, no input, no captures):
  base   no mod plan (the runtime logs `M33 mods=off`)
  mod    a private mod made through `r3hd_mods.py import` / `plan` (the public compiler): node 101 -> --value
After the level opens, m5_memory_probe.py discovers actors; then this tool reads, every 0.1 s, the generator's
position, behaviour, variables 23 / 24 and the current-waypoint variable 8 (read-only, m5_live.Actor).
Judged: target / speed values per segment, path speed from positions, time of the first target change (the
junction), the served range, and the M21 / M22 / M23-haptics judges. Outputs stay under private/work/e456/.

usage: script_const_ab.py TAG [--value 15] [--settle 0] [--watch 75] [--seconds 150] [--cases base,mod]
       script_const_ab.py judge TAG
"""
import argparse
import json
import math
import os
import re
import struct
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))
import r3hd_mods as rm  # noqa: E402

GAME = ROOT / "private" / "extracted" / "5841123F"
RUNS = ROOT / "private" / "work" / "m6_runs"
LEVEL, MODEL = "intro_10", "NIN_m_GenFlyIntro_10"
BEHAVIOUR_SUFFIX, SCRIPT, NODE = ":NIN_C_FlyInit", 0, 101
TARGET_VAR, SPEED_VAR, WAYPOINT_VAR = 24, 23, 8
# E-459 (D-226), --target junction: the loop-arc speed in the generator's arrival macro (macro 3 of the model whose
# first behaviour is NIN_C_FlyInit): node 34 = int 45 in `dsgvar#24 = 45`, taken when `variable 5 < 6` at a junction.
JUNCTION_MACRO, JUNCTION_NODE, JUNCTION_ORIGINAL = 3, 34, 45
TARGET = "flyinit"
PREFIX = "e456"


def target_override(value):
    """The override, after checking the node's role in the person's own file: `dsgvar#24 = <int 30>` in FlyInit, or
    (--target junction) `dsgvar#24 = <int 45>` in the arrival macro. value None: the original value (role check)."""
    ix = rm.read_script_index(GAME, LEVEL)
    name = next(n for n in ix["behaviours"] if n.endswith(BEHAVIOUR_SUFFIX) and f"\\{MODEL}\\" in n)
    if TARGET == "junction":
        macros = ix["models"].get(name) or []
        mac = macros[JUNCTION_MACRO] if len(macros) > JUNCTION_MACRO else None
        nodes = mac["nodes"] if mac and not mac["safe"] else None
        k = JUNCTION_NODE
        role = (bool(nodes) and len(nodes) > k and nodes[k - 2][2] == 0x02 and nodes[k - 2][0] == 0x0C
                and nodes[k - 1][2] == 0x0B and nodes[k - 1][0] == TARGET_VAR and nodes[k][2] == 0x0C
                and nodes[k][0] == JUNCTION_ORIGINAL and nodes[k - 1][1] == nodes[k][1] == nodes[k - 2][1] + 1)
        if not role:
            raise SystemExit(f"macro {JUNCTION_MACRO} node {k} is not `dsgvar#{TARGET_VAR} = 45` in this file")
        return {"type": "macro-constant", "level": LEVEL, "model": name, "macro": JUNCTION_MACRO, "node": k,
                "script_sha256": rm.script_hash(ix, mac["nodes_at"], nodes), "kind": "int",
                "value": JUNCTION_ORIGINAL if value is None else value}
    na, nodes = ix["behaviours"][name][SCRIPT]
    op, var, const = nodes[NODE - 2], nodes[NODE - 1], nodes[NODE]
    role = (op[2] == 0x02 and op[0] == 0x0C and var[2] == 0x0B and var[0] == TARGET_VAR and const[2] == 0x0C
            and const[0] == 30 and var[1] == const[1] == op[1] + 1)
    if not role:
        raise SystemExit(f"node {NODE} is not `dsgvar#{TARGET_VAR} = 30` in this file: {op} {var} {const}")
    return {"type": "script-constant", "level": LEVEL, "behavior": name, "script": SCRIPT, "node": NODE,
            "script_sha256": rm.script_hash(ix, na, nodes), "kind": "int", "value": 30 if value is None else value}


def mods(work, *args):
    common = ["--mods-root", str(work / "mods"), "--cache", str(work / "cache"), "--game-dir", str(GAME), "--json"]
    r = subprocess.run([sys.executable, "-I", str(TOOLS / "r3hd_mods.py"), *args, *common], capture_output=True,
                       text=True, cwd=ROOT)
    out = json.loads(r.stdout)
    if out.get("result") != "ok":
        raise SystemExit(f"r3hd_mods {args}: {out}")
    return out


def run_case(tag, case, value, settle, watch, seconds):
    from m5_live import Actor, Process, f32
    work = ROOT / "private" / "work" / PREFIX / tag / case
    run = f"{PREFIX}_{tag}_{case}"
    if work.exists() or (RUNS / run).exists():
        raise SystemExit(f"exists: {work} or {RUNS / run}")
    work.mkdir(parents=True)
    env = dict(os.environ)
    env.pop("R3HD_MODS_PLAN", None)
    row = {"case": case, "run": run}
    if case == "mod":
        src = work / "mod_src"
        src.mkdir()
        (src / "mod.json").write_text(json.dumps({
            "format": 1, "id": f"{PREFIX}.flight-{TARGET}", "name": f"{PREFIX} test", "version": "1.0.0",
            "target": {"title_id": rm.TITLE_ID, "releases": rm.release_ids({"home": None}),
                       "min_port_version": "0.0.1"},
            "overrides": [target_override(value)]}), encoding="utf-8")
        mods(work, "import", str(src), "--enable")
        env["R3HD_MODS_PLAN"] = row["plan"] = mods(work, "plan")["plan"]
        row["value"] = value
    else:
        target_override(None)   # the same role check on the unmodified file
    steps = work / "steps.txt"
    steps.write_text(f"wait {seconds - 8}\n", encoding="ascii")
    samples = []
    with (work / "driver.log").open("w") as log:
        game = subprocess.Popen([sys.executable, str(TOOLS / "m9_license_run.py"), run, str(steps), "--license-mask",
                                 "1", "--seconds", str(seconds), "--play", "--test-level", LEVEL, "--user-root", run],
                                cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
        needle = re.compile(rf"[\\/]{LEVEL}\.lvl result=00000000", re.IGNORECASE)
        opened, base, end = None, None, time.monotonic() + 90
        while time.monotonic() < end and game.poll() is None and opened is None:
            time.sleep(0.5)
            lp = RUNS / run / "runtime.log"
            if lp.is_file():
                text = lp.read_text(errors="replace")
                opened = time.monotonic() if needle.search(text) else None
                m = re.search(r"virtual base 0x0*([0-9A-Fa-f]+),", text)
                base = m.group(1) if m else base
        if opened is None or base is None:
            row["error"] = "level did not open"
        else:
            time.sleep(settle)
            pid = json.loads((RUNS / run / "process.json").read_text(encoding="utf-8-sig"))["pid"]
            disc = work / "discovery.json"
            p = subprocess.run([sys.executable, str(TOOLS / "m5_memory_probe.py"), str(pid), base, str(disc),
                                "--regions"], cwd=ROOT, capture_output=True, text=True, timeout=180)
            if p.returncode != 0:
                row["error"] = "discovery failed: " + p.stderr.strip()[-200:]
            else:
                process = Process(pid, int(base, 16))
                gen = None
                for a in json.loads(disc.read_text(encoding="utf-8"))["actors"]:
                    try:
                        act = Actor(process, int(a["so"], 16))
                    except Exception:   # an entry freed since discovery
                        continue
                    if act.model == MODEL and act.mind:
                        gen = act
                        break
                if gen is None:
                    row["error"] = "generator not found"
                else:
                    row["discovered_after_open_s"] = round(time.monotonic() - opened, 2)
                    t_end = time.monotonic() + watch
                    while time.monotonic() < t_end and process.running():
                        try:
                            v = gen.dsg()
                            samples.append({"t": round(time.monotonic() - opened, 3), "pos": gen.position(),
                                            "beh": gen.comport(), "speed": f32(v[SPEED_VAR]),
                                            "target": f32(v[TARGET_VAR]),
                                            "wp": struct.unpack_from(">I", *v[WAYPOINT_VAR])[0]})
                        except Exception as x:   # level change or exit: stop reading
                            row["sampling_stopped"] = type(x).__name__
                            break
                        time.sleep(0.1)
        game.wait(timeout=seconds + 240)
        row["runner_exit"] = game.returncode
    (work / "samples.json").write_text(json.dumps(samples) + "\n")
    (work / "row.json").write_text(json.dumps(row, indent=1) + "\n")
    return row


def summarize(samples):
    """Per sample run: the first target, path speed (units / s) while the first target holds, the first target change."""
    if not samples:
        return {"samples": 0}
    first = samples[0]["target"]
    seg = [s for s in samples if s["beh"] == "NIN_C_FlyMvt"]
    change = next((s for s in samples if s["target"] != first), None)
    hold = [s for s in seg if change is None or s["t"] < change["t"]]
    dist = sum(math.dist(a["pos"], b["pos"]) for a, b in zip(hold, hold[1:]))
    span = hold[-1]["t"] - hold[0]["t"] if len(hold) > 1 else 0
    tail = [s for s in hold if span and s["t"] >= hold[-1]["t"] - min(3.0, span / 3)]
    tail_d = sum(math.dist(a["pos"], b["pos"]) for a, b in zip(tail, tail[1:]))
    tail_s = tail[-1]["t"] - tail[0]["t"] if len(tail) > 1 else 0
    changes = [(a["t"], b["target"]) for a, b in zip(samples, samples[1:]) if a["target"] != b["target"]]
    later = []   # segments after the first junction: (target, path speed 1.5 s after the change, duration)
    for (t0, tg), (t1, _) in zip(changes, changes[1:]):
        h = [s for s in samples if t0 + 1.5 <= s["t"] < t1]
        if len(h) > 5:
            d = sum(math.dist(a["pos"], b["pos"]) for a, b in zip(h, h[1:]))
            later.append((tg, round(d / (h[-1]["t"] - h[0]["t"]), 3), round(t1 - t0, 2)))
    return {"samples": len(samples), "first_t": samples[0]["t"], "first_target": first, "later_segments": later,
            "first_speed": samples[0]["speed"], "first_beh": samples[0]["beh"],
            "segment_samples": len(hold), "segment_s": round(span, 2),
            "segment_path_speed": round(dist / span, 3) if span else None,
            "segment_end_path_speed": round(tail_d / tail_s, 3) if tail_s else None,
            "segment_end_speed_var": round(hold[-1]["speed"], 3) if hold else None,
            "segment_waypoints": len({s["wp"] for s in hold}),
            "first_target_change_t": change["t"] if change else None,
            "first_target_change_to": change["target"] if change else None,
            "first_target_change_pos": change["pos"] if change else None,
            "targets_seen": sorted({round(s["target"], 3) for s in samples})}


def judge(tag, value):
    out = {}
    for case in ("base", "mod"):
        work = ROOT / "private" / "work" / PREFIX / tag / case
        run = f"{PREFIX}_{tag}_{case}"
        row = json.loads((work / "row.json").read_text())
        log = "\n".join(p.read_text(errors="replace") for p in sorted((RUNS / run).glob("runtime*.log")))
        row["mods_off"] = "M33 mods=off" in log
        row["served"] = sorted(set(re.findall(r"M33 mods served mod=(\S+) file=(\S+) offset=(\d+)", log)))
        row["haptics_policy"] = "M23 haptics policy=suppressed physical_pad_drivers=none" in log
        judges = {}
        for tool in ("m21_regression.py", "m22_regression.py", "m23_haptics_regression.py"):
            r = subprocess.run([sys.executable, str(TOOLS / tool), "--run", run], cwd=ROOT, capture_output=True,
                               text=True)
            judges[tool] = r.returncode
            (work / f"{tool}.log").write_text(r.stdout + r.stderr)
        row["judges"] = judges
        row["summary"] = summarize(json.loads((work / "samples.json").read_text()))
        out[case] = row
    b, m = out["base"]["summary"], out["mod"]["summary"]
    if TARGET == "junction":
        return judge_junction(tag, value, out, b, m)
    checks = {
        "base: no plan, mod: the one range served from intro_10.lvl":
            out["base"]["mods_off"] and len(out["mod"]["served"]) == 1
            and out["mod"]["served"][0][1].lower() == f"{LEVEL}.lvl",
        "both: no error, sampled while the first target held":
            not any("error" in out[c] for c in out) and b.get("segment_samples", 0) >= 20
            and m.get("segment_samples", 0) >= 20,
        "base: first target 30 (the file's constant)": b.get("first_target") == 30.0,
        f"mod: first target {value} (the mod's constant, executed by FlyInit)": m.get("first_target") == float(value),
        "speed variable approaches the target in both (eased by FlyMvt)":
            b.get("segment_end_speed_var") is not None and abs(b["segment_end_speed_var"] - 30) < 1.5
            and m.get("segment_end_speed_var") is not None and abs(m["segment_end_speed_var"] - value) < 1.5,
        "path speed at the segment end follows the target (ratio within 15 %)":
            bool(b.get("segment_end_path_speed") and m.get("segment_end_path_speed"))
            and abs((m["segment_end_path_speed"] / b["segment_end_path_speed"]) / (value / 30) - 1) < 0.15,
        "both: the junction later sets the loop target 45":
            b.get("first_target_change_to") == 45.0 and m.get("first_target_change_to") == 45.0,
        "after the first junction: same targets, path speeds (3 %) and durations (0.3 s) as the baseline":
            len(b.get("later_segments", [])) >= 4 and len(m.get("later_segments", [])) >= 4
            and all(x[0] == y[0] and abs(x[1] / y[1] - 1) < 0.03 and abs(x[2] - y[2]) < 0.3
                    for x, y in zip(b["later_segments"], m["later_segments"])),
        "both: haptics policy line, M21 / M22 / M23 judges pass":
            all(out[c]["haptics_policy"] and not any(out[c]["judges"].values()) for c in out),
    }
    result = {"value": value, "checks": checks, "pass": all(checks.values()),
              "base": out["base"]["summary"], "mod": out["mod"]["summary"]}
    (ROOT / "private" / "work" / PREFIX / tag / "judge.json").write_text(json.dumps(result, indent=1) + "\n")
    print(json.dumps(result, indent=1))
    return 0 if result["pass"] else 1


def judge_junction(tag, value, out, b, m):
    """E-459: the macro sets the loop-arc target; the first segment (FlyInit's 30) and the 30 segments set by the
    other macro must equal the baseline, the loop-arc segments must run at the mod's value and last 45 / value as
    long."""
    bl, ml = b.get("later_segments", []), m.get("later_segments", [])
    pairs = list(zip(bl, ml))
    arcs = [(x, y) for x, y in pairs if x[0] == 45.0]
    thirty = [(x, y) for x, y in pairs if x[0] == 30.0]
    checks = {
        "base: no plan, mod: the one range served from intro_10.lvl":
            out["base"]["mods_off"] and len(out["mod"]["served"]) == 1
            and out["mod"]["served"][0][1].lower() == f"{LEVEL}.lvl",
        "both: no error, sampled while the first target held":
            not any("error" in out[c] for c in out) and b.get("segment_samples", 0) >= 20
            and m.get("segment_samples", 0) >= 20,
        # The junction's place, not its time: times count from the level-open log line, polled every 0.5 s
        # (E-459: baselines 9.38-9.77 s for the same place).
        "first segment unchanged: target 30, path speed (3 %), junction reached at the same place (4.5 units)":
            b.get("first_target") == m.get("first_target") == 30.0
            and abs(m["segment_path_speed"] / b["segment_path_speed"] - 1) < 0.03
            and bool(b.get("first_target_change_pos") and m.get("first_target_change_pos"))
            and math.dist(b["first_target_change_pos"], m["first_target_change_pos"]) < 4.5,
        f"at the junction the macro sets the loop target: base 45, mod {value}":
            b.get("first_target_change_to") == 45.0 and m.get("first_target_change_to") == float(value),
        f"loop-arc segments: path speed 45 / {value} (3 %), mod duration = base x 45 / {value} (10 %)":
            len(arcs) >= 2 and all(y[0] == float(value) and abs(x[1] / 45 - 1) < 0.03 and abs(y[1] / value - 1) < 0.03
                                   and abs(y[2] / (x[2] * 45 / value) - 1) < 0.10 for x, y in arcs),
        # A 30 segment starts at the previous arc's speed and eases to 30 in about 1.6 s (FlyMvt), so its duration
        # shifts a little with the arc's speed (E-459: j1 60 -0.09..-0.19 s, j2 35 +0.10..+0.32 s). The sign is not
        # checked: segment ends are sampled every 0.1 s and the baseline itself spans 9.84-9.95 s (j3 50: -0.11 and
        # +0.02 s for a predicted -0.05 s). Checked: target, speed after the easing, a bounded shift.
        "segments at 30 (the other macro): same target and speed (3 %); duration shift under 0.5 s (carried speed)":
            len(thirty) >= 2 and all(y[0] == 30.0 and abs(y[1] / x[1] - 1) < 0.03 and abs(y[2] - x[2]) < 0.5
                                     for x, y in thirty),
        "both: haptics policy line, M21 / M22 / M23 judges pass":
            all(out[c]["haptics_policy"] and not any(out[c]["judges"].values()) for c in out),
    }
    result = {"target": TARGET, "value": value, "checks": checks, "pass": all(checks.values()),
              "base": b, "mod": m}
    (ROOT / "private" / "work" / PREFIX / tag / "judge.json").write_text(json.dumps(result, indent=1) + "\n")
    print(json.dumps(result, indent=1))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("tag")
    ap.add_argument("tag2", nargs="?")
    ap.add_argument("--value", type=int, default=15)
    ap.add_argument("--settle", type=float, default=0)
    ap.add_argument("--watch", type=float, default=75)
    ap.add_argument("--seconds", type=int, default=150)
    ap.add_argument("--cases", default="base,mod")
    ap.add_argument("--target", choices=("flyinit", "junction"), default="flyinit",
                    help="flyinit: E-456 script-constant; junction: E-459 macro-constant (runs named e459_*)")
    a = ap.parse_args()
    TARGET = a.target
    PREFIX = "e459" if TARGET == "junction" else "e456"
    if a.tag == "judge":
        sys.exit(judge(a.tag2, a.value))
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", a.tag) or not 1 <= a.value <= 1000:
        ap.error("bad tag or value")
    for case in a.cases.split(","):
        print(json.dumps(run_case(a.tag, case, a.value, a.settle, a.watch, a.seconds)), flush=True)
    sys.exit(judge(a.tag, a.value) if a.cases == "base,mod" else 0)
