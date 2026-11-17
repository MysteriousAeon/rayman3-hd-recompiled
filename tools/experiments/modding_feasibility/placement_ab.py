"""E-461 (D-228): behavioural A/B of one actor's initial translation (`actor-position`), hidden and read-only.

PROTOCOL (written before any run; thresholds fixed here and not changed after results)
Target: intro_10, AI model NIN_m_Lums_Int10 (a red lum), instance 0 (first lum in file order): matrix type 2
(translation only), file translation F = (22.642759, -12.012001, -34.384747); its snapshot copy holds the same
matrix word-swapped. Both are written. Role: the flight generator (`NIN_m_GenFlyIntro_10`) collects a lum near its
path (macro 4: variable 5 += 1; RE_NOTES "M5 completion"); without input its path passes the lums 3.1 to 3.7 units
away and collects none (E-460 bases: variable 5 = 0 for 200 s). In the earlier live scan every lum stood exactly at
its file translation (static actor). The lum is not progression-critical by itself (28 lums, six needed to leave
the loop; collecting one changes the count to 1 and keeps the loop).
Cases (one hidden run each; m9_license_run.py: hidden window, muted, no physical pad, isolated test profile,
`--test-level intro_10`, no input, no captures; 260 s run, sampled every 0.1 s for up to 200 s):
  base     no mod plan
  mod      P = (19.10, -13.56, -34.58): the E-460 p2 base generator position at t = 5.25 s (0.004 from that path,
           3.87 from F)  -> predicted: picked up on the first pass
  control  Q = (47.64, -12.01, -34.38): F + 25 on x, 28.6 units from every E-460 p2 base path sample
           -> predicted: moved, never picked up
Observed: at the first sample, every NIN_m_Lums_Int10 actor's live position (SuperObject +0x20 matrix +0x34, the
same field the earlier scans read); then every 0.1 s the generator's position, behaviour, variables 5, 24, 27 and
the target lum's position (while its actor stays readable). Times count from the level-open line (0.5 s polling);
places, not times, are compared.
Criteria (functional PASS needs all of C1-C6):
  C1 served: base `M33 mods=off`; mod and control each serve exactly the two compiled 12-byte ranges of
     intro_10.lvl (matrix +0x34 and snapshot +0x34) and nothing else.
  C2 placement state at the first sample: as many live lums as file lums; base has a lum at F (0.01) and none within
     0.5 of P or Q; mod has a lum at P (0.01) and none within 0.5 of F; control has a lum at Q (0.01) and none within
     0.5 of F; every other lum at its own file translation (0.01) in all three.
  C3 flight unchanged before the lum point: first target 30; the generator's closest approach to P on its first pass
     is within 1 unit of P in all three (the same path).
  C4 gameplay effect: base and control: variable 5 = 0 in every sample; mod: variable 5 = 1 by the first sample at
     which the generator is again more than 10 units from P after its first-pass closest approach, and never above 1.
  C5 unrelated state: in all three the first junction (variable 27 == 2) lies within 4.5 units of base's place and
     the target becomes 45 there (variable 5 < 6).
  C6 safety: haptics policy line, M21 / M22 / M23 judges 0, no game process left after each case; the gameplay record
     line in mod and control, none in base.
  REVISION after run q1 (recorded in E-461; validated only by a fresh run, never applied to q1): C3's closest
  approach is measured to the sampled path (segments between consecutive samples), not to the nearest sample: at
  30 units/s and 0.1 s sampling consecutive samples lie about 3 units apart, so a sample can be 1.5 units from a point
  the path crosses (q1: base 1.50, control 1.00, mod 0.004; everything else passed). Threshold unchanged (1 unit).
Secondary, recorded but not deciding (fixed in advance): what the moved lum's actor does after a pickup (position,
behaviour, readability); whether any sound / text event follows.
Invalid (rerun, not judged): the level does not open, the generator or the lums are not found, the first sample comes
after the generator's first-pass closest approach to P, sampling ends before the first junction, or the role check
fails in the person's file.
Not measured (stated in advance): collision geometry (the lum is collected by a distance query, not by collision),
rendering, sectors, and any actor other than this lum.

usage: placement_ab.py TAG [--cases base,mod,control]
       placement_ab.py judge TAG
Outputs stay under private/work/e461/.
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
LEVEL, LUM, GEN = "intro_10", "NIN_m_Lums_Int10", "NIN_m_GenFlyIntro_10"
F = (22.642759323120117, -12.012001037597656, -34.38474655151367)
f32 = lambda v: struct.unpack(">f", struct.pack(">f", v))[0]   # noqa: E731
P = tuple(f32(v) for v in (19.10, -13.56, -34.58))
Q = tuple(f32(v) for v in (47.64, -12.01, -34.38))
POSITIONS = {"base": None, "mod": P, "control": Q}
PREFIX = "e461"
SECONDS, WATCH = 260, 200


def role():
    ix = rm.read_script_index(GAME, LEVEL)
    key = next(k for k in ix["placements"] if f"\\{LUM}\\" in k)
    insts = ix["placements"][key]
    rows = rm.placement_rows(ix, insts)
    if not rows or "position" not in rows[0] or tuple(rows[0]["position"]) != F or rows[0]["matrix_type"] != 2:
        raise SystemExit("role check: lum instance 0 is not the type-2 lum at F in this file")
    files = [tuple(struct.unpack_from(">3f", ix["data"], i["matrix"] + 0x34)) for i in insts if i["matrix"]]
    tpl = {"type": "actor-position", "level": LEVEL, "model": key, "instance": 0,
           "matrix_sha256": rows[0]["matrix_sha256"]}
    return tpl, ix, insts, files


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
    from m5_live import Actor, Process, f32 as lf32, i32, u8
    tpl, ix, insts, files = role()
    pos = POSITIONS[case]
    work = ROOT / "private" / "work" / PREFIX / tag / case
    run = f"{PREFIX}_{tag}_{case}"
    if work.exists() or (RUNS / run).exists():
        raise SystemExit(f"exists: {work} or {RUNS / run}")
    work.mkdir(parents=True)
    env = dict(os.environ)
    env.pop("R3HD_MODS_PLAN", None)
    row = {"case": case, "run": run, "position": pos}
    if pos is not None:
        src = work / "mod_src"
        src.mkdir()
        (src / "mod.json").write_text(json.dumps({
            "format": 1, "id": f"{PREFIX}.lum-{case}", "name": f"{PREFIX} test", "version": "1.0.0",
            "target": {"title_id": rm.TITLE_ID, "releases": rm.release_ids({"home": None}),
                       "min_port_version": "0.0.1"},
            "overrides": [{**tpl, "position": list(pos)}]}), encoding="utf-8")
        mods(work, "import", str(src), "--enable")
        env["R3HD_MODS_PLAN"] = row["plan"] = mods(work, "plan")["plan"]
        row["expected_ranges"] = sorted([insts[0]["matrix"] + 0x34, insts[0]["snapshot"] + 0x34])
    steps = work / "steps.txt"
    steps.write_text(f"wait {SECONDS - 8}\n", encoding="ascii")
    samples = []
    with (work / "driver.log").open("w") as log:
        game = subprocess.Popen([sys.executable, str(TOOLS / "m9_license_run.py"), run, str(steps), "--license-mask",
                                 "1", "--seconds", str(SECONDS), "--play", "--test-level", LEVEL, "--user-root", run],
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
        pid = None
        if opened is None or base is None:
            row["error"] = "level did not open"
        else:
            pid = json.loads((RUNS / run / "process.json").read_text(encoding="utf-8-sig"))["pid"]
            disc = work / "discovery.json"
            p = subprocess.run([sys.executable, str(TOOLS / "m5_memory_probe.py"), str(pid), base, str(disc),
                                "--regions"], cwd=ROOT, capture_output=True, text=True, timeout=180)
            if p.returncode != 0:
                row["error"] = "discovery failed: " + p.stderr.strip()[-200:]
            else:
                process = Process(pid, int(base, 16))
                gen, lums = None, []
                for a in json.loads(disc.read_text(encoding="utf-8"))["actors"]:
                    try:
                        act = Actor(process, int(a["so"], 16))
                    except Exception:   # an entry freed since discovery
                        continue
                    if act.model == GEN and act.mind and gen is None:
                        gen = act
                    elif act.model == LUM:
                        lums.append(act)
                if gen is None or not lums:
                    row["error"] = "generator or lums not found"
                else:
                    row["lums_t"] = round(time.monotonic() - opened, 3)
                    row["lums"] = [list(a.position()) for a in lums]
                    want = pos or F
                    tgt = min(lums, key=lambda a: math.dist(a.position(), want))
                    t_end = time.monotonic() + WATCH
                    while time.monotonic() < t_end and process.running():
                        try:
                            v = gen.dsg()
                            s = {"t": round(time.monotonic() - opened, 3), "pos": gen.position(),
                                 "beh": gen.comport(), "v5": u8(v[5]), "v24": lf32(v[24]), "v27": i32(v[27])}
                        except Exception as x:   # level change or exit: stop reading
                            row["sampling_stopped"] = type(x).__name__
                            break
                        try:
                            s["lum"] = tgt.position() if tgt.alive() else None
                            s["lum_beh"] = tgt.comport() if tgt.alive() else None
                        except Exception:
                            s["lum"] = None
                        samples.append(s)
                        time.sleep(0.1)
        game.wait(timeout=SECONDS + 240)
        row["runner_exit"] = game.returncode
        row["process_left"] = bool(pid and alive(pid))
    (work / "samples.json").write_text(json.dumps(samples) + "\n")
    (work / "row.json").write_text(json.dumps(row, indent=1) + "\n")
    return row


def seg_dist(p, a, b):
    ab = [b[i] - a[i] for i in range(3)]
    n = sum(v * v for v in ab)
    t = 0.0 if not n else max(0.0, min(1.0, sum((p[i] - a[i]) * ab[i] for i in range(3)) / n))
    return math.dist(p, [a[i] + t * ab[i] for i in range(3)])


def summarize(samples, polyline=False):
    if not samples:
        return {"samples": 0}
    early = [s for s in samples if s["t"] < 12]
    k = min(range(len(early)), key=lambda i: math.dist(early[i]["pos"], P)) if early else None
    closest = early[k] if k is not None else None
    leave = next((s for s in samples[k:] if math.dist(s["pos"], P) > 10), None) if k is not None else None
    j = next((s for s in samples if s["v27"] == 2), None)
    after_j = [s for s in samples if j and j["t"] <= s["t"] <= j["t"] + 0.5]
    return {"samples": len(samples), "first_t": samples[0]["t"], "last_t": samples[-1]["t"],
            "first_target": samples[0]["v24"],
            "closest_t": closest["t"] if closest else None,
            "closest_dist": round(math.dist(closest["pos"], P), 3) if closest else None,
            "closest_path_dist": round(min(seg_dist(P, a["pos"], b["pos"]) for a, b in zip(early, early[1:])), 3)
            if len(early) > 1 else None,
            "leave_t": leave["t"] if leave else None, "v5_at_leave": leave["v5"] if leave else None,
            "v5_seen": sorted({s["v5"] for s in samples}),
            "v5_first_1_t": next((s["t"] for s in samples if s["v5"] >= 1), None),
            "junction_t": j["t"] if j else None, "junction_pos": j["pos"] if j else None,
            "junction_v5": j["v5"] if j else None,
            "junction_target_45": any(s["v24"] == 45.0 for s in after_j),
            "lum_first": samples[0].get("lum"), "lum_last_seen": next(
                (s["lum"] for s in reversed(samples) if s.get("lum")), None),
            "lum_behaviours": sorted({str(s.get("lum_beh")) for s in samples})}


def judge(tag):
    tpl, ix, insts, files = role()
    out = {}
    for case in POSITIONS:
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
        row["summary"] = summarize(json.loads((work / "samples.json").read_text()))
        out[case] = row
    b, m, c = (out[k]["summary"] for k in ("base", "mod", "control"))

    def served(case):
        row = out[case]
        return ([(int(o), int(n)) for _, f, o, n in row["served"]] == [(o, 12) for o in row["expected_ranges"]]
                and all(f.lower() == f"{LEVEL}.lvl" for _, f, _, _ in row["served"]))

    def placed(case):
        lums = [tuple(p) for p in out[case].get("lums", [])]
        want = POSITIONS[case] or F
        if len(lums) != len(files) or not any(math.dist(p, want) < 0.01 for p in lums):
            return False
        away = [F, P, Q] if case == "base" else [F]
        if any(math.dist(p, a) < 0.5 for p in lums for a in away if a != want):
            return False
        others = [f for f in files if f != F]
        rest = [p for p in lums if math.dist(p, want) >= 0.01]
        return len(rest) == len(others) and all(any(math.dist(p, f) < 0.01 for p in rest) for f in others)

    def near(p, q, d):
        return bool(p and q) and math.dist(p, q) < d

    invalid = [k for k in out if "error" in out[k] or out[k]["summary"].get("samples", 0) == 0
               or (out[k]["summary"].get("closest_t") is not None
                   and out[k]["summary"]["first_t"] >= out[k]["summary"]["closest_t"])
               or not out[k]["summary"].get("junction_t")]
    checks = {
        "C1 served: base mods=off; mod and control serve exactly the two compiled 12-byte ranges of intro_10.lvl":
            out["base"]["mods_off"] and not out["base"]["served"] and served("mod") and served("control"),
        "C2 placement at the first sample: target lum at F / P / Q (0.01), not elsewhere; other lums at file places":
            all(placed(k) for k in out),
        "C3 flight unchanged before the lum point: first target 30, closest approach to P within 1 unit"
        + ("" if tag == "q1" else " (sampled path)"):
            all(x.get("first_target") == 30.0 and x.get("closest_dist" if tag == "q1" else "closest_path_dist")
                is not None and x["closest_dist" if tag == "q1" else "closest_path_dist"] < 1.0 for x in (b, m, c)),
        "C4 gameplay: base and control v5 = 0 always; mod v5 = 1 when leaving P (first pass), never above 1":
            b.get("v5_seen") == [0] and c.get("v5_seen") == [0] and m.get("v5_at_leave") == 1
            and max(m.get("v5_seen") or [9]) == 1,
        "C5 unrelated: first junction within 4.5 units of base's place, target 45 there (all three)":
            all(near(x.get("junction_pos"), b.get("junction_pos"), 4.5) and x.get("junction_target_45")
                for x in (b, m, c)),
        "C6 safety: haptics, M21/M22/M23 0, no process left; gameplay line only in mod and control":
            all(out[k]["haptics_policy"] and not any(out[k]["judges"].values()) and not out[k].get("process_left")
                for k in out) and not out["base"]["gameplay_line"] and out["mod"]["gameplay_line"]
            and out["control"]["gameplay_line"],
    }
    result = {"invalid": invalid, "checks": checks, "pass": not invalid and all(checks.values()),
              "secondary": {k: {"lum_first": out[k]["summary"].get("lum_first"),
                                "lum_last_seen": out[k]["summary"].get("lum_last_seen"),
                                "lum_behaviours": out[k]["summary"].get("lum_behaviours"),
                                "runner_exit": out[k].get("runner_exit"),
                                "sampling_stopped": out[k].get("sampling_stopped")} for k in out},
              "base": b, "mod": m, "control": c}
    (ROOT / "private" / "work" / PREFIX / tag / "judge.json").write_text(json.dumps(result, indent=1) + "\n")
    print(json.dumps({k: result[k] for k in ("invalid", "checks", "pass", "secondary")}, indent=1))
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
