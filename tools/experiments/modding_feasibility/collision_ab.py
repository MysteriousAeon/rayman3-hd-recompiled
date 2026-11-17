"""E-462 (D-229): does a moved collision-bearing actor's collision follow its `actor-position` edit? Hidden, read-only.

PROTOCOL (written before any A/B run; thresholds fixed here and not changed after results)
Known before the protocol: RE_NOTES "M7" (VERIFIED by run): `NIK_mSpoPont` bridges are absent from static
collision and Rayman stood on the intro_15 bridge at (81.0, 52.24, -5.96) at (81.9, 50.7, -5.2): its walkable top
there is about 0.76 above the bridge origin (Rayman's origin rests 0.00-0.31 above a surface, so 0.45-0.76).
Exploratory baseline `collision_recon.py r1` (no mod, not judged): in an unattended isolated intro_15 start the
opening cinematic places Rayman at (-95.896, 56.433, -9.094) at about 34 s; at about 71 s he enters YAM_C_Attente
(grounded control) and the game's ground resolution sets z -9.104 (0.010 lower); he then stays exactly still.
Target: intro_15, AI model NIK_mSpoPont, instance 6 (file order; the bridge above), matrix type 2, origin
B = (81.003929, 52.241116, -5.961654). Rayman (in fix.lvl) cannot be moved and is not edited.
Cases (one hidden run each; m9_license_run.py: hidden window, muted, no physical pad, isolated test profile,
`--test-level intro_15`, no input, no captures; 230 s run):
  base     no mod plan
  mod      bridge origin O = Rayman's settled spot (-95.896, 56.433, -9.104) - stand offset (0.9, -1.54, 0.76) +
           0.5 up = (-96.796, 57.973, -9.364): the measured walkable spot lies under Rayman's feet, its top 0.19 to
           0.50 above them (inside his body)
  control  O + 15 on x = (-81.796, 57.973, -9.364): same height, 15 units from Rayman, no contact possible
Observed every 0.2 s (m5_live, read-only): Rayman's position and behaviour; at the first sample and every sample
the target bridge's position (SuperObject +0x20 matrix +0x34) and behaviour; at the first sample all bridges.
Criteria (judged separately; the result class follows from them):
  P1 placement: base / mod / control: the target bridge live at B / O / O+15x (0.01) at the first and the last
     sample (it stays); the other six bridges at their file origins (0.01); base, mod and control each with exactly
     7 bridges. Mod and control serve exactly the two compiled 12-byte ranges of intro_15.lvl; base mods=off.
  P2 collision: Rayman's settled position in mod (median of the samples 5 to 60 s after his first YAM_C_Attente
     sample) differs from base's settled position by more than 0.10 units (base's within-run spread is 0.000 in
     the recon), or Rayman shows a behaviour other than YAM_C_Init / YAM_C_Attente in the 60 s after base's
     Attente time. The direction is reported (expected: up onto the bridge, z about -8.85 .. -8.60).
  P3 control: control's settled position within 0.02 of base's and only YAM_C_Init / YAM_C_Attente seen.
  P4 isolation: Rayman's placed position (first sample after the cinematic's jump of > 5 units) within 0.02 of
     base's in all three, YAM_C_Attente reached in all three, its time within 5 s of base's.
  P5 safety: haptics policy line, M21 / M22 / M23 judges 0, no game process left; the gameplay record line in mod
     and control only.
Result classes: P1-P5 PASS -> collision followed the placement for this actor class (static bridge, ground
resolution at spawn); P1, P3-P5 PASS and P2 FAIL -> collision did not follow OR the test could not provoke contact
(unresolved unless further evidence); P1 FAIL -> placement not loaded.
Invalid (rerun, not judged): the level does not open, Rayman or the bridges are not found, base never reaches
YAM_C_Attente, sampling ends before base's Attente + 60 s, or the role check fails in the person's file.
Not measured (stated in advance): rendering, sector membership, collision of other actor classes, contact from
motion (walking or landing), the snapshot copy's use.

usage: collision_ab.py TAG [--cases base,mod,control]
       collision_ab.py judge TAG
Outputs stay under private/work/e462/.
"""
import argparse
import json
import math
import os
import re
import statistics
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
LEVEL, BRIDGE, RAY, INSTANCE = "intro_15", "NIK_mSpoPont", "YLT_RaymanModel", 6
B = (81.0039291381836, 52.24111557006836, -5.961654186248779)
f32 = lambda v: struct.unpack(">f", struct.pack(">f", v))[0]   # noqa: E731
O = tuple(f32(v) for v in (-96.796, 57.973, -9.364))
OC = tuple(f32(v) for v in (-81.796, 57.973, -9.364))
POSITIONS = {"base": None, "mod": O, "control": OC}
PREFIX = "e462"
SECONDS = 230
CALM = {"YAM_C_Init", "YAM_C_Attente"}


def role():
    ix = rm.read_script_index(GAME, LEVEL)
    key = next(k for k in ix["placements"] if BRIDGE in k.split("\\"))
    insts = ix["placements"][key]
    rows = rm.placement_rows(ix, insts)
    if len(rows) != 7 or tuple(rows[INSTANCE].get("position", ())) != B or rows[INSTANCE]["matrix_type"] != 2:
        raise SystemExit("role check: bridge instance 6 is not the type-2 bridge at B in this file")
    files = [tuple(r["position"]) for r in rows]
    tpl = {"type": "actor-position", "level": LEVEL, "model": key, "instance": INSTANCE,
           "matrix_sha256": rows[INSTANCE]["matrix_sha256"]}
    return tpl, insts, files


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
    tpl, insts, files = role()
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
            "format": 1, "id": f"{PREFIX}.bridge-{case}", "name": f"{PREFIX} test", "version": "1.0.0",
            "target": {"title_id": rm.TITLE_ID, "releases": rm.release_ids({"home": None}),
                       "min_port_version": "0.0.1"},
            "overrides": [{**tpl, "position": list(pos)}]}), encoding="utf-8")
        mods(work, "import", str(src), "--enable")
        env["R3HD_MODS_PLAN"] = row["plan"] = mods(work, "plan")["plan"]
        row["expected_ranges"] = sorted([insts[INSTANCE]["matrix"] + 0x34, insts[INSTANCE]["snapshot"] + 0x34])
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
            ray, bridges = None, []
            for x in (json.loads(disc.read_text(encoding="utf-8"))["actors"] if p.returncode == 0 else []):
                try:
                    act = Actor(process, int(x["so"], 16))
                except Exception:
                    continue
                if act.model == RAY and ray is None:
                    ray = act
                elif act.model == BRIDGE:
                    bridges.append(act)
            if ray is None or not bridges:
                row["error"] = "rayman or bridges not found"
            else:
                row["bridges"] = [list(b.position()) for b in bridges]
                want = pos or B
                tgt = min(bridges, key=lambda b: math.dist(b.position(), want))
                t_end = time.monotonic() + SECONDS - 45
                while time.monotonic() < t_end and process.running():
                    try:
                        samples.append({"t": round(time.monotonic() - opened, 2), "pos": ray.position(),
                                        "beh": ray.comport(), "bridge": tgt.position(), "bridge_beh": tgt.comport()})
                    except Exception as x:
                        row["sampling_stopped"] = type(x).__name__
                        break
                    time.sleep(0.2)
        game.wait(timeout=SECONDS + 240)
        row["runner_exit"] = game.returncode
        row["process_left"] = bool(pid and alive(pid))
    (work / "samples.json").write_text(json.dumps(samples) + "\n")
    (work / "row.json").write_text(json.dumps(row, indent=1) + "\n")
    return row


def summarize(samples):
    if not samples:
        return {"samples": 0}
    jump = next((b for a, b in zip(samples, samples[1:]) if math.dist(a["pos"], b["pos"]) > 5), None)
    att = next((s for s in samples if s["beh"] == "YAM_C_Attente"), None)
    settled = [s["pos"] for s in samples if att and att["t"] + 5 <= s["t"] <= att["t"] + 60]
    med = [statistics.median(p[i] for p in settled) for i in range(3)] if settled else None
    return {"samples": len(samples), "first_t": samples[0]["t"], "last_t": samples[-1]["t"],
            "placed": jump["pos"] if jump else None, "placed_t": jump["t"] if jump else None,
            "attente_t": att["t"] if att else None, "settled": med, "settled_n": len(settled),
            "settled_spread": round(max(math.dist(p, med) for p in settled), 4) if settled else None,
            "behaviours": sorted({s["beh"] for s in samples}),
            "bridge_first": samples[0]["bridge"], "bridge_last": samples[-1]["bridge"],
            "bridge_behaviours": sorted({str(s["bridge_beh"]) for s in samples})}


def judge(tag):
    tpl, insts, files = role()
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
        want = POSITIONS[case] or B
        s, br = out[case]["summary"], [tuple(p) for p in out[case].get("bridges", [])]
        others = [f for f in files if f != B]
        rest = [p for p in br if math.dist(p, want) >= 0.01]
        return (len(br) == 7 and any(math.dist(p, want) < 0.01 for p in br) and len(rest) == 6
                and all(any(math.dist(p, f) < 0.01 for p in rest) for f in others)
                and bool(s.get("bridge_first")) and math.dist(s["bridge_first"], want) < 0.01
                and math.dist(s["bridge_last"], want) < 0.01)

    def within(x, ref, d):
        return bool(x and ref) and math.dist(x, ref) < d

    window = [s for s in json.loads((ROOT / "private" / "work" / PREFIX / tag / "mod" / "samples.json").read_text())
              if b.get("attente_t") and b["attente_t"] <= s["t"] <= b["attente_t"] + 60]
    invalid = [k for k in out if "error" in out[k] or not out[k]["summary"].get("samples")]
    if not b.get("attente_t") or b.get("last_t", 0) < (b.get("attente_t") or 1e9) + 60:
        invalid.append("base: no Attente or sampling too short")
    checks = {
        "P1 placement: bridge live at B / O / O+15x at first and last sample, other 6 at file origins; ranges served":
            all(placed(k) for k in out) and out["base"]["mods_off"] and not out["base"]["served"]
            and served("mod") and served("control"),
        "P2 collision: mod settled position differs from base by > 0.10, or a non-calm behaviour after base's Attente":
            (bool(m.get("settled") and b.get("settled")) and math.dist(m["settled"], b["settled"]) > 0.10)
            or any(s["beh"] not in CALM for s in window),
        "P3 control: settled within 0.02 of base, only YAM_C_Init / YAM_C_Attente":
            within(c.get("settled"), b.get("settled"), 0.02) and set(c.get("behaviours", [])) <= CALM,
        "P4 isolation: placed position within 0.02 of base, Attente reached within 5 s of base (all three)":
            all(within(x.get("placed"), b.get("placed"), 0.02) and x.get("attente_t") is not None
                and abs(x["attente_t"] - b["attente_t"]) < 5 for x in (b, m, c)),
        "P5 safety: haptics, M21/M22/M23 0, no process left; gameplay line only in mod and control":
            all(out[k]["haptics_policy"] and not any(out[k]["judges"].values()) and not out[k].get("process_left")
                for k in out) and not out["base"]["gameplay_line"] and out["mod"]["gameplay_line"]
            and out["control"]["gameplay_line"],
    }
    delta = [round(m["settled"][i] - b["settled"][i], 4) for i in range(3)] if m.get("settled") and b.get(
        "settled") else None
    result = {"invalid": invalid, "checks": checks, "pass": not invalid and all(checks.values()),
              "mod_minus_base_settled": delta,
              "mod_behaviours_after_base_attente": sorted({s["beh"] for s in window}),
              "base": b, "mod": m, "control": c,
              "secondary": {k: {"runner_exit": out[k].get("runner_exit"),
                                "sampling_stopped": out[k].get("sampling_stopped")} for k in out}}
    (ROOT / "private" / "work" / PREFIX / tag / "judge.json").write_text(json.dumps(result, indent=1) + "\n")
    print(json.dumps({k: result[k] for k in ("invalid", "checks", "pass", "mod_minus_base_settled",
                                              "mod_behaviours_after_base_attente")}, indent=1))
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
