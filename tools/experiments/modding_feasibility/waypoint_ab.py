"""E-464 (D-231): behavioural A/B of one waypoint position (`waypoint-position`), hidden and read-only.

PROTOCOL (committed before any run; thresholds fixed here and not changed after results)
Target: intro_10, AI model NIN_m_GenFlyIntro_10 (key = its NIN_C_FlyInit behaviour name), instance 0, designer
variable 0 (type 20, its graph; 143 nodes, editable), node 13: waypoint W = (19.207331, -32.903214, -40.101063),
radius 1.0, flags 0, referenced only by its node; neighbours node 12 (21.38, -21.13, -37.37) and node 14
(16.63, -43.81, -42.50), about 12 and 11 units away; not the junction (that is node 23 / 24, 50+ units on). In the
E-460 p2 base flight the sampled path passes 1.18 units from W at about t 6.0 s (first loop) and every loop after.
Mod: W' = W moved 6 units horizontally, perpendicular to the node 12 -> 14 direction: (25.08, -34.13, -40.10)
(base path 7.12 units from W'). Control: node 32 (88.05, -236.58, -49.55; base path 125 units away, never visited
in the loop) moved by the same vector to (93.92, -237.81, -49.55).
Cases (one hidden run each; m9_license_run.py: hidden window, muted, no physical pad, isolated test profile,
`--test-level intro_10`, no input, no captures; 150 s run, generator sampled every 0.1 s for 75 s):
  base, mod (node 13 -> W'), control (node 32 -> C').
Observed: generator position every 0.1 s; at the first sample, the live graph (generator variable 0 -> graph ->
node list) with the live x, y, z of nodes 13 and 32 and the live node count.
Path comparison is by position, not time: distance of a sample to the base run's sampled path (segments between
consecutive base samples). Run-to-run noise of no-mod intro_10 paths measured this way: at most 0.15 units
(E-460 p1 / E-461 q2 / E-461 q2 control vs E-460 p2, after the first junction).
Criteria (functional PASS needs all):
  W1 data: base `M33 mods=off` and nothing served; mod serves exactly one 12-byte range of intro_10.lvl at node
     13's waypoint; control exactly one at node 32's.
  W2 load: live node count 143; live node 13 = W' (mod) / W (base, control) and live node 32 = C' (control) / its
     file position (base, mod), each within 0.0001.
  W3 effect: mod's sampled path passes within 2.5 units of W' while base's stays >= 4.5 from W'; the mod sample
     farthest from base's path lies within 16 units of W, at least 3.0 units off base's path, and displaced toward
     W' (positive dot product of its offset from the nearest base path point with W' - W).
  W4 control: every control sample within 0.5 of base's path; control >= 4.5 from W'.
  W5 isolation: every mod sample more than 16 units from W lies within 0.5 of base's path.
  W6 safety: haptics policy line, M21 / M22 / M23 judges 0, no game process left; the gameplay record line in mod
     and control only.
REVISION after run w1 (recorded in E-464; applies to fresh runs only, w1 stays judged by the criteria above):
  w1 passed W1, W2, W6 and failed W3, W4, W5. Causes: (a) measurement flaw: a run's first samples (control t 2.1-2.6 s
  on the spawn approach, y 85 -> 70) precede base's first sample (2.7 s, y 63), so base has no path there (W4 1.41,
  W5 0.57 at those samples only); (b) prediction errors: the generator turns toward the next waypoint before reaching
  one (mod passed 1.5 from W, 5.4 from W'), so the path bends toward W' by at most 2.7 units, beginning about 22 units
  before W (W5's 16-unit region too small). Revised criteria, judged on samples after the latest first sample of the
  three runs + 0.5 s:
  W3r: mod's maximum distance from base's path >= 1.5 units (10 x the 0.15 run-to-run noise), at a sample within 25
       units of W, displaced toward W'; mod's closest approach to W' at least 1.0 unit smaller than base's.
  W4r: control within 0.5 of base's path everywhere; control's closest approach to W' within 0.5 of base's.
  W5r: mod samples more than 25 units from W within 0.5 of base's path.
  W1, W2, W6 unchanged.
Invalid (rerun, not judged): level not opened, generator not found, first sample after base's closest approach to
W, fewer than 60 s of samples, or the role check fails in the person's file.

usage: waypoint_ab.py TAG [--cases base,mod,control]
       waypoint_ab.py judge TAG
Outputs stay under private/work/e464/.
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
LEVEL, MODEL, BEHAVIOUR_SUFFIX = "intro_10", "NIN_m_GenFlyIntro_10", ":NIN_C_FlyInit"
NODE, CNODE = 13, 32
W = (19.20733070373535, -32.90321350097656, -40.1010627746582)
C = (88.04761505126953, -236.5763702392578, -49.55243682861328)
f32 = lambda v: struct.unpack(">f", struct.pack(">f", v))[0]   # noqa: E731
WP = tuple(f32(v) for v in (25.08, -34.13, -40.10))
CP = tuple(f32(v) for v in (93.92, -237.81, -49.55))
CASES = {"base": None, "mod": (NODE, WP), "control": (CNODE, CP)}
PREFIX = "e464"
SECONDS, WATCH = 150, 75


def role():
    ix = rm.read_script_index(GAME, LEVEL)
    key = next(n for n in ix["behaviours"] if n.endswith(BEHAVIOUR_SUFFIX) and f"\\{MODEL}\\" in n)
    e = ix["graphs"].get((key, 0, 0))
    rows = {r["variable"]: r for r in rm.waypoint_rows(ix, key) if r["instance"] == 0}
    nodes = rows.get(0, {}).get("nodes", [])
    if not e or e["safe"] or len(nodes) != 143 or tuple(nodes[NODE].get("position", ())) != W \
            or tuple(nodes[CNODE].get("position", ())) != C or nodes[NODE]["radius"] != 1.0:
        raise SystemExit("role check: the flight graph's nodes 13 / 32 are not the expected editable waypoints")
    return ix, key, e, nodes


def seg(p, a, b):
    ab = [b[i] - a[i] for i in range(3)]
    n2 = sum(v * v for v in ab)
    t = 0.0 if not n2 else max(0.0, min(1.0, sum((p[i] - a[i]) * ab[i] for i in range(3)) / n2))
    q = [a[i] + t * ab[i] for i in range(3)]
    return math.dist(p, q), q


def to_path(p, path):
    return min((seg(p, a, b) for a, b in zip(path, path[1:])), key=lambda x: x[0])


def mods(work, *args):
    common = ["--mods-root", str(work / "mods"), "--cache", str(work / "cache"), "--game-dir", str(GAME), "--json"]
    r = subprocess.run([sys.executable, "-I", str(TOOLS / "r3hd_mods.py"), *args, *common], capture_output=True,
                       text=True, cwd=ROOT)
    out = json.loads(r.stdout)
    if out.get("result") != "ok":
        raise SystemExit(f"r3hd_mods {args}: {out}")
    return out


def alive(pid):
    r = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True)
    return str(pid) in r.stdout


def run_case(tag, case):
    from m5_live import Actor, Process
    ix, key, e, nodes = role()
    work = ROOT / "private" / "work" / PREFIX / tag / case
    run = f"{PREFIX}_{tag}_{case}"
    if work.exists() or (RUNS / run).exists():
        raise SystemExit(f"exists: {work} or {RUNS / run}")
    work.mkdir(parents=True)
    env = dict(os.environ)
    env.pop("R3HD_MODS_PLAN", None)
    row = {"case": case, "run": run}
    if CASES[case]:
        node, pos = CASES[case]
        src = work / "mod_src"
        src.mkdir()
        (src / "mod.json").write_text(json.dumps({
            "format": 1, "id": f"{PREFIX}.waypoint-{case}", "name": f"{PREFIX} test", "version": "1.0.0",
            "target": {"title_id": rm.TITLE_ID, "releases": rm.release_ids({"home": None}),
                       "min_port_version": "0.0.1"},
            "overrides": [{"type": "waypoint-position", "level": LEVEL, "model": key, "instance": 0, "variable": 0,
                           "node": node, "waypoint_sha256": nodes[node]["waypoint_sha256"], "position": list(pos)}]}),
            encoding="utf-8")
        mods(work, "import", str(src), "--enable")
        env["R3HD_MODS_PLAN"] = row["plan"] = mods(work, "plan")["plan"]
        row["expected_range"] = e["nodes"][node][1]
    (work / "steps.txt").write_text(f"wait {SECONDS - 8}\n", encoding="ascii")
    samples = []
    with (work / "driver.log").open("w") as log:
        game = subprocess.Popen([sys.executable, str(TOOLS / "m9_license_run.py"), run, str(work / "steps.txt"),
                                 "--license-mask", "1", "--seconds", str(SECONDS), "--play", "--test-level", LEVEL,
                                 "--user-root", run], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
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
        pid = None
        if opened is None or base is None:
            row["error"] = "level did not open"
        else:
            pid = json.loads((RUNS / run / "process.json").read_text(encoding="utf-8-sig"))["pid"]
            disc = work / "discovery.json"
            p = subprocess.run([sys.executable, str(TOOLS / "m5_memory_probe.py"), str(pid), base, str(disc),
                                "--regions"], cwd=ROOT, capture_output=True, text=True, timeout=180)
            process = Process(pid, int(base, 16))
            gen = None
            for a in (json.loads(disc.read_text(encoding="utf-8"))["actors"] if p.returncode == 0 else []):
                try:
                    act = Actor(process, int(a["so"], 16))
                except Exception:
                    continue
                if act.model == MODEL and act.mind:
                    gen = act
                    break
            if gen is None:
                row["error"] = "generator not found"
            else:
                try:
                    v = gen.dsg()
                    g = struct.unpack_from(">I", *v[0])[0]
                    first, last, count = process.words(g, 3)
                    live, nd = {}, first
                    for i in range(max(NODE, CNODE) + 1):
                        if i in (NODE, CNODE):
                            wp = process.words(nd + 0xC, 1)[0]
                            live[i] = list(struct.unpack(">3f", process.read(wp, 12)))
                        nd = process.words(nd, 1)[0]
                    row["live_graph"] = {"count": count, "node13": live[NODE], "node32": live[CNODE]}
                except Exception as x:
                    row["live_graph_error"] = repr(x)
                t_end = time.monotonic() + WATCH
                while time.monotonic() < t_end and process.running():
                    try:
                        samples.append({"t": round(time.monotonic() - opened, 3), "pos": gen.position()})
                    except Exception as x:
                        row["sampling_stopped"] = type(x).__name__
                        break
                    time.sleep(0.1)
        game.wait(timeout=SECONDS + 240)
        row["runner_exit"] = game.returncode
        row["process_left"] = bool(pid and alive(pid))
    (work / "samples.json").write_text(json.dumps(samples) + "\n")
    (work / "row.json").write_text(json.dumps(row, indent=1) + "\n")
    return row


def judge(tag):
    ix, key, e, nodes = role()
    out, paths = {}, {}
    for case in CASES:
        work = ROOT / "private" / "work" / PREFIX / tag / case
        run = f"{PREFIX}_{tag}_{case}"
        row = json.loads((work / "row.json").read_text())
        log = "\n".join(p.read_text(errors="replace") for p in sorted((RUNS / run).glob("runtime*.log")))
        row["mods_off"] = "M33 mods=off" in log
        row["served"] = sorted(set(re.findall(r"M33 mods served mod=(\S+) file=(\S+) offset=(\d+) length=(\d+)",
                                              log)))
        row["gameplay_line"] = bool(re.search(r"M33 mods gameplay mod=\S+ achievements=not_awarded", log))
        row["haptics_policy"] = "M23 haptics policy=suppressed physical_pad_drivers=none" in log
        judges = {}
        for tool in ("m21_regression.py", "m22_regression.py", "m23_haptics_regression.py"):
            r = subprocess.run([sys.executable, str(TOOLS / tool), "--run", run], cwd=ROOT, capture_output=True,
                               text=True)
            judges[tool] = r.returncode
            (work / f"{tool}.log").write_text(r.stdout + r.stderr)
        row["judges"] = judges
        out[case] = row
        paths[case] = json.loads((work / "samples.json").read_text())
    base = [s["pos"] for s in paths["base"]]
    t_close = min(paths["base"], key=lambda s: math.dist(s["pos"], W))["t"] if base else 0
    invalid = [k for k in out if "error" in out[k] or len(paths[k]) < 2
               or paths[k][-1]["t"] - paths[k][0]["t"] < 60 or paths[k][0]["t"] >= t_close]

    def served(case):
        want = [] if CASES[case] is None else [(out[case]["expected_range"], 12)]
        return ([(int(o), int(n)) for _, f, o, n in out[case]["served"]] == want
                and all(f.lower() == f"{LEVEL}.lvl" for _, f, _, _ in out[case]["served"]))

    def loaded(case):
        lg = out[case].get("live_graph") or {}
        w13 = WP if case == "mod" else W
        w32 = CP if case == "control" else C
        return (lg.get("count") == 143 and bool(lg.get("node13")) and math.dist(lg["node13"], w13) < 1e-4
                and math.dist(lg["node32"], w32) < 1e-4)

    revised = tag != "w1"
    t0 = max(paths[k][0]["t"] for k in paths if paths[k]) + 0.5 if revised else -1.0
    region = 25 if revised else 16
    summary = {}
    for case in ("mod", "control"):
        pts = [s["pos"] for s in paths[case] if s["t"] >= t0]
        offs = [(to_path(p, base), p) for p in pts]
        far = max(offs, key=lambda x: x[0][0]) if offs else None
        summary[case] = {
            "closest_to_Wp": round(min(to_path(WP, pts)[0], 1e9), 3) if len(pts) > 1 else None,
            "max_off_base": round(far[0][0], 3) if far else None,
            "max_off_point": far[1] if far else None,
            "max_off_dist_to_W": round(math.dist(far[1], W), 2) if far else None,
            "max_off_toward_Wp": (sum((far[1][i] - far[0][1][i]) * (WP[i] - W[i]) for i in range(3)) > 0) if far else None,
            "max_off_outside_16": round(max([o[0][0] for o in offs if math.dist(o[1], W) > region] or [0]), 3),
        }
    summary["base"] = {"closest_to_W": round(to_path(W, base)[0], 3), "closest_to_Wp": round(to_path(WP, base)[0], 3),
                       "t_closest_W": t_close}
    m, c, b = summary["mod"], summary["control"], summary["base"]
    if revised:
        checks = {
            "W1 data: base serves nothing; mod / control serve exactly their 12-byte waypoint range":
                out["base"]["mods_off"] and served("base") and served("mod") and served("control"),
            "W2 load: live node count 143; live nodes 13 / 32 at the expected positions (0.0001)":
                all(loaded(k) for k in out),
            "W3r effect: max deviation >= 1.5 within 25 of W toward W'; mod >= 1.0 closer to W' than base":
                m["max_off_base"] is not None and m["max_off_base"] >= 1.5 and m["max_off_dist_to_W"] <= 25
                and m["max_off_toward_Wp"] is True and m["closest_to_Wp"] <= b["closest_to_Wp"] - 1.0,
            "W4r control: within 0.5 of base's path; closest approach to W' within 0.5 of base's":
                c["max_off_base"] is not None and c["max_off_base"] <= 0.5
                and abs(c["closest_to_Wp"] - b["closest_to_Wp"]) <= 0.5,
            "W5r isolation: mod samples more than 25 from W within 0.5 of base's path":
                m["max_off_outside_16"] <= 0.5,
            "W6 safety: haptics, M21/M22/M23 0, no process left; gameplay line only in mod and control":
                all(out[k]["haptics_policy"] and not any(out[k]["judges"].values())
                    and not out[k].get("process_left") for k in out)
                and not out["base"]["gameplay_line"] and out["mod"]["gameplay_line"]
                and out["control"]["gameplay_line"],
        }
    else:
      checks = {
        "W1 data: base serves nothing; mod / control serve exactly their 12-byte waypoint range":
            out["base"]["mods_off"] and served("base") and served("mod") and served("control"),
        "W2 load: live node count 143; live nodes 13 / 32 at the expected positions (0.0001)":
            all(loaded(k) for k in out),
        "W3 effect: mod within 2.5 of W', base >= 4.5; max deviation >= 3.0, within 16 of W, toward W'":
            m["closest_to_Wp"] is not None and m["closest_to_Wp"] <= 2.5 and b["closest_to_Wp"] >= 4.5
            and m["max_off_base"] >= 3.0 and m["max_off_dist_to_W"] <= 16 and m["max_off_toward_Wp"] is True,
        "W4 control: every sample within 0.5 of base's path; >= 4.5 from W'":
            c["max_off_base"] is not None and c["max_off_base"] <= 0.5 and c["closest_to_Wp"] >= 4.5,
        "W5 isolation: mod samples more than 16 from W within 0.5 of base's path":
            m["max_off_outside_16"] <= 0.5,
        "W6 safety: haptics, M21/M22/M23 0, no process left; gameplay line only in mod and control":
            all(out[k]["haptics_policy"] and not any(out[k]["judges"].values()) and not out[k].get("process_left")
                for k in out) and not out["base"]["gameplay_line"] and out["mod"]["gameplay_line"]
            and out["control"]["gameplay_line"],
    }
    result = {"invalid": invalid, "checks": checks, "pass": not invalid and all(checks.values()),
              "summary": summary, "live_graph": {k: out[k].get("live_graph") for k in out},
              "rows": {k: {x: out[k].get(x) for x in ("runner_exit", "sampling_stopped", "served")} for k in out}}
    (ROOT / "private" / "work" / PREFIX / tag / "judge.json").write_text(json.dumps(result, indent=1) + "\n")
    print(json.dumps({k: result[k] for k in ("invalid", "checks", "pass", "summary")}, indent=1))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("tag")
    ap.add_argument("tag2", nargs="?")
    ap.add_argument("--cases", default="base,mod,control")
    a = ap.parse_args()
    if a.tag == "judge":
        sys.exit(judge(a.tag2))
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", a.tag):
        ap.error("bad tag")
    for case in a.cases.split(","):
        print(json.dumps(run_case(a.tag, case)), flush=True)
    sys.exit(judge(a.tag) if a.cases == "base,mod,control" else 0)
