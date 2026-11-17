"""E-460 (D-227): behavioural A/B of one designer-variable initial value (`designer-default`), hidden, read-only.

PROTOCOL (written before any run; thresholds fixed here and not changed after results)
Target: intro_10, AI model NIN_m_GenFlyIntro_10 (key = its NIN_C_FlyInit behaviour name), instance 0 (the only
DsgMem of the model in intro_10.lvl), designer variable 5: type 2 (byte), buffer offset 328, file value 0, written in
the instance's initial and current buffers. Role (RE_NOTES "M5 completion", VERIFIED by execution there): red lums
collected; the arrival macro (macro 3) at a waypoint with two outgoing arcs (variable 27 == 2, the junction) runs
`if variable 5 < 6: v24 = 45 (loop arc), next = arc 0; else: v3 = 5, next = arc 1 (exit arc)`; six lums leave the
loop toward about (780, -435, -38) and end the flight. The model's only writer of variable 5 is macro 4 (`++`, a lum
pickup); nothing resets it. The harness re-checks this role in the person's own file before every case.
Cases (one hidden run each; m9_license_run.py: hidden window, muted, no physical pad, isolated test profile,
`--test-level intro_10`, no input, no captures; 260 s run, generator sampled every 0.1 s for up to 200 s):
  base     no mod plan
  mod      value 6  (prediction: exit arc at the first junction)
  control  value 5  (prediction: loop arc at the first junction, as base, when base holds 0 lums there)
Observed per sample: position, behaviour, variables 3, 5, 8, 23, 24, 27; at the first sample also the live DsgMem's
+0 / +4 / +8 words and the whole live initial buffer. Times count from the level-open line (polled every 0.5 s);
samples every 0.1 s; therefore places, not times, are compared. Junction = first sample with variable 27 == 2.
Criteria (functional PASS needs all of C1-C7):
  C1 served: base logs `M33 mods=off`; mod and control each serve exactly the two ranges the compiler reports
     (intro_10.lvl, initial and current buffer + 328, 1 byte each) and nothing else.
  C2 loaded: first live sample of variable 5 = 0 / 6 / 5 (base / mod / control); the live initial buffer's byte
     328 the same; the live initial buffer equals the file's (with the mod's byte) in every byte outside relocated
     words; DsgMem +0 = the model record + 8 (the chain).
  C3 unchanged before the junction (mod and control vs base): first target 30; path speed while it holds within
     3 %; junction place within 4.5 units of base's.
  C4 base: variable 5 < 6 at the junction and the target changes to 45 there (loop arc).
  C5 mod: variable 3 becomes 5 at the junction, target 45 never appears, variable 5 >= 6 throughout, and within
     40 s after the junction the generator reaches a point >= 100 units from every base sample position.
  C6 control: if base's variable 5 at the junction is 0, the target changes to 45 at the junction (within 4.5 units
     of base's place) and variable 3 is not set to 5 there; if base holds lums there, C6 is NOT INFORMATIVE (not a
     failure) and is reported as such.
  C7 safety: all three: haptics policy line, M21 / M22 / M23 judges 0, runner exit recorded, no game process left
     after the case; the gameplay record line in mod and control, none in base.
  REVISION after run p1 (recorded in E-460; validated only by a fresh run, never applied to p1): C2's buffer
  comparison also skips variable 2 (type 33, sound-event array, bytes 8..67): the file holds 0047xxxx ids there and
  the loader rewrites them into addresses (p1: all 52 differing bytes of all three cases inside it, every scalar
  variable equal). C2's value checks (first variable 5, live initial byte 328, the chain) are unchanged.
Secondary, recorded but not deciding (fixed in advance): whether intro_15.lvl opens in mod (expected, as in the
lum-collecting run, unless a score panel waits for input) and not in base; any achievement gate line.
Invalid (rerun, not judged): the level does not open, the generator is not found, the first sample comes after
base's junction, sampling ends before the junction, or the role check fails.

usage: dsgvar_ab.py TAG [--cases base,mod,control]
       dsgvar_ab.py judge TAG
Outputs stay under private/work/e460/.
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
INSTANCE, VAR, OFFSET = 0, 5, 328
VALUES = {"base": None, "mod": 6, "control": 5}
PREFIX = "e460"
SECONDS, WATCH = 260, 200


def role():
    """(override template, file index, model key, entry, instance) after checking the role in the person's file."""
    ix = rm.read_script_index(GAME, LEVEL)
    key = next(n for n in ix["behaviours"] if n.endswith(BEHAVIOUR_SUFFIX) and f"\\{MODEL}\\" in n)
    entry = ix["defaults"].get(key)
    insts = entry["instances"] if entry else []
    if len(insts) != 1 or insts[0]["safe"] or entry["vars"][VAR] != (OFFSET, 2):
        raise SystemExit("role check: the generator is not one editable instance with byte variable 5 at 328")
    inst = insts[0]
    if ix["data"][inst["initial"] + OFFSET] != 0:
        raise SystemExit("role check: variable 5 does not start at 0 in this file")
    nodes = ix["models"][key][3]["nodes"]
    # (parameter, indent, type): if (27) boolcall#6 (28) v5 (29) real 6 (30) then (31) v24 = 45 (32-34) else (47)
    # v3 = 5 (48-50)
    want = {27: (0x00, 3, 0x00), 28: (6, 4, 0x01), 29: (VAR, 5, 0x0B), 31: (0x10, 3, 0x00), 32: (0x0C, 4, 0x02),
            33: (24, 5, 0x0B), 34: (45, 5, 0x0C), 47: (0x11, 3, 0x00), 48: (0x0C, 4, 0x02), 49: (3, 5, 0x0B),
            50: (5, 5, 0x0C)}
    real6 = struct.unpack(">I", struct.pack(">f", 6.0))[0]
    if any(nodes[k] != v for k, v in want.items()) or nodes[30] != (real6, 5, 0x0D):
        raise SystemExit("role check: macro 3 is not `if v5 < 6: v24 = 45 ... else: v3 = 5 ...` in this file")
    tpl = {"type": "designer-default", "level": LEVEL, "model": key, "instance": INSTANCE, "variable": VAR,
           "initial_sha256": rm.designer_hash(ix, inst, entry["length"]), "kind": "byte"}
    return tpl, ix, key, entry, inst


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
    from m5_live import Actor, Process, f32, i32, u8
    tpl, ix, key, entry, inst = role()
    value = VALUES[case]
    work = ROOT / "private" / "work" / PREFIX / tag / case
    run = f"{PREFIX}_{tag}_{case}"
    if work.exists() or (RUNS / run).exists():
        raise SystemExit(f"exists: {work} or {RUNS / run}")
    work.mkdir(parents=True)
    env = dict(os.environ)
    env.pop("R3HD_MODS_PLAN", None)
    row = {"case": case, "run": run, "value": value}
    if value is not None:
        src = work / "mod_src"
        src.mkdir()
        (src / "mod.json").write_text(json.dumps({
            "format": 1, "id": f"{PREFIX}.lums-{value}", "name": f"{PREFIX} test", "version": "1.0.0",
            "target": {"title_id": rm.TITLE_ID, "releases": rm.release_ids({"home": None}),
                       "min_port_version": "0.0.1"},
            "overrides": [{**tpl, "value": value}]}), encoding="utf-8")
        mods(work, "import", str(src), "--enable")
        env["R3HD_MODS_PLAN"] = row["plan"] = mods(work, "plan")["plan"]
        row["expected_ranges"] = sorted([inst["initial"] + OFFSET, inst["current"] + OFFSET])
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
                    mem = process.words(gen.mind[3], 3)
                    model = process.words(gen.mind[0], 1)
                    row["dsgmem"] = [f"{w:08X}" for w in mem]
                    row["chain_ok"] = bool(mem and model is not None and mem[0] == gen.mind[0] + 8)
                    ini = process.read(mem[1], entry["length"]) if mem else None
                    row["live_initial_hex"] = ini.hex() if ini else None
                    t_end = time.monotonic() + WATCH
                    while time.monotonic() < t_end and process.running():
                        try:
                            v = gen.dsg()
                            samples.append({"t": round(time.monotonic() - opened, 3), "pos": gen.position(),
                                            "beh": gen.comport(), "v3": i32(v[3]), "v5": u8(v[5]),
                                            "v8": struct.unpack_from(">I", *v[8])[0], "v23": f32(v[23]),
                                            "v24": f32(v[24]), "v27": i32(v[27])})
                        except Exception as x:   # level change or exit: stop reading
                            row["sampling_stopped"] = type(x).__name__
                            break
                        time.sleep(0.1)
        game.wait(timeout=SECONDS + 240)
        row["runner_exit"] = game.returncode
        row["process_left"] = bool(pid and alive(pid))
    (work / "samples.json").write_text(json.dumps(samples) + "\n")
    (work / "row.json").write_text(json.dumps(row, indent=1) + "\n")
    return row


def summarize(samples):
    if not samples:
        return {"samples": 0}
    j = next((i for i, s in enumerate(samples) if s["v27"] == 2), None)
    pre = [s for s in samples[:j if j is not None else len(samples)] if s["beh"] == "NIN_C_FlyMvt"
           and s["v24"] == samples[0]["v24"]]
    span = pre[-1]["t"] - pre[0]["t"] if len(pre) > 1 else 0
    dist = sum(math.dist(a["pos"], b["pos"]) for a, b in zip(pre, pre[1:]))
    after = samples[j:] if j is not None else []
    return {"samples": len(samples), "first_t": samples[0]["t"], "last_t": samples[-1]["t"],
            "first_v5": samples[0]["v5"], "first_target": samples[0]["v24"],
            "pre_path_speed": round(dist / span, 3) if span else None, "pre_samples": len(pre),
            "junction_t": samples[j]["t"] if j is not None else None,
            "junction_pos": samples[j]["pos"] if j is not None else None,
            "junction_v5": samples[j]["v5"] if j is not None else None,
            "junction_v3": samples[j]["v3"] if j is not None else None,
            "junction_target": samples[j]["v24"] if j is not None else None,
            "v3_before_junction": sorted({s["v3"] for s in samples[:j]}) if j is not None else None,
            "targets_seen": sorted({round(s["v24"], 3) for s in samples}),
            "v5_seen": sorted({s["v5"] for s in samples}),
            "after": after}


def judge(tag):
    tpl, ix, key, entry, inst = role()
    out = {}
    for case in VALUES:
        work = ROOT / "private" / "work" / PREFIX / tag / case
        run = f"{PREFIX}_{tag}_{case}"
        row = json.loads((work / "row.json").read_text())
        log = "\n".join(p.read_text(errors="replace") for p in sorted((RUNS / run).glob("runtime*.log")))
        row["mods_off"] = "M33 mods=off" in log
        row["served"] = sorted(set(re.findall(r"M33 mods served mod=(\S+) file=(\S+) offset=(\d+) length=(\d+)",
                                              log)))
        row["gameplay_line"] = bool(re.search(r"M33 mods gameplay mod=\S+ achievements=not_awarded", log))
        row["achievement_gate_lines"] = re.findall(r"M33 achievement id=\S+ not_awarded reason=gameplay_mods", log)
        row["intro_15_opened"] = bool(re.search(r"[\\/]intro_15\.lvl result=00000000", log, re.IGNORECASE))
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
    reloc = {k for k in range(entry["length"]) if any(inst["initial"] + w in ix["slots"] for w in range(k - 3, k + 1))}
    if tag != "p1":   # the revision after p1 (see PROTOCOL); p1 stays judged by the original criterion
        rewritten = entry["vars"][2]
        if rewritten != (8, 33):
            raise SystemExit("role check: variable 2 is not the type-33 array at 8 in this file")
        reloc |= set(range(8, 68))
    file_ini = ix["data"][inst["initial"]:inst["initial"] + entry["length"]]

    def loaded(case):
        row, want = out[case], VALUES[case] or 0
        live = bytes.fromhex(row.get("live_initial_hex") or "")
        exp = bytearray(file_ini)
        exp[OFFSET] = want
        return (row["summary"].get("first_v5") == want and len(live) == len(exp) and live[OFFSET] == want
                and all(live[k] == exp[k] for k in range(len(exp)) if k not in reloc) and row.get("chain_ok") is True)

    def served(case):
        row = out[case]
        return ([(int(o), int(n)) for _, f, o, n in row["served"]] == [(o, 1) for o in row["expected_ranges"]]
                and all(f.lower() == f"{LEVEL}.lvl" for _, f, _, _ in row["served"]))

    def near(p, q, d):
        return bool(p and q) and math.dist(p, q) < d

    invalid = [k for k in out if "error" in out[k] or not out[k]["summary"].get("junction_t")
               or out[k]["summary"]["first_t"] >= (b.get("junction_t") or 0)]
    base_pos = [s["pos"] for s in json.loads((ROOT / "private" / "work" / PREFIX / tag / "base" /
                                              "samples.json").read_text())]
    far = [s for s in m.get("after", []) if s["t"] <= (m.get("junction_t") or 0) + 40
           and min(math.dist(s["pos"], p) for p in base_pos) >= 100]
    c6_informative = b.get("junction_v5") == 0
    c6 = (c.get("junction_target") == 45.0 or any(s["v24"] == 45.0 for s in c.get("after", [])[:3])) \
        and near(c.get("junction_pos"), b.get("junction_pos"), 4.5) and c.get("junction_v3") != 5
    checks = {
        "C1 served: base mods=off; mod and control serve exactly the two compiled 1-byte ranges of intro_10.lvl":
            out["base"]["mods_off"] and not out["base"]["served"] and served("mod") and served("control"),
        "C2 loaded: first variable 5 and the live initial buffer = 0 / 6 / 5; buffer = file outside relocated words"
        + ("" if tag == "p1" else " and variable 2 (load-rewritten)"):
            all(loaded(k) for k in out),
        "C3 before the junction unchanged: first target 30, path speed 3 %, junction place 4.5 units":
            all(x.get("first_target") == 30.0 and x.get("pre_path_speed") and b.get("pre_path_speed")
                and abs(x["pre_path_speed"] / b["pre_path_speed"] - 1) < 0.03
                and near(x.get("junction_pos"), b.get("junction_pos"), 4.5) for x in (m, c)),
        "C4 base: variable 5 < 6 at the junction, target 45 (loop arc)":
            (b.get("junction_v5") or 0) < 6 and (b.get("junction_target") == 45.0
                                                 or any(s["v24"] == 45.0 for s in b.get("after", [])[:3])),
        "C5 mod: v3 = 5 at the junction, no target 45, v5 >= 6 throughout, >= 100 units off base's path in 40 s":
            (m.get("junction_v3") == 5 or any(s["v3"] == 5 for s in m.get("after", [])[:3]))
            and 45.0 not in m.get("targets_seen", [45.0]) and min(m.get("v5_seen", [0])) >= 6 and bool(far),
        "C6 control: loop arc at the junction (if base holds 0 lums there)": c6 if c6_informative else True,
        "C7 safety: haptics, M21/M22/M23 0, no process left; gameplay line only in mod and control":
            all(out[k]["haptics_policy"] and not any(out[k]["judges"].values()) and not out[k].get("process_left")
                for k in out) and not out["base"]["gameplay_line"] and out["mod"]["gameplay_line"]
            and out["control"]["gameplay_line"],
    }
    for x in (b, m, c):
        x["after_n"] = len(x.pop("after", []))
    result = {"invalid": invalid, "checks": checks, "pass": not invalid and all(checks.values()),
              "c6_informative": c6_informative,
              "secondary": {k: {"intro_15_opened": out[k]["intro_15_opened"],
                                "achievement_gate_lines": out[k]["achievement_gate_lines"],
                                "runner_exit": out[k].get("runner_exit"),
                                "sampling_stopped": out[k].get("sampling_stopped")} for k in out},
              "far_first": far[0] if far else None, "base": b, "mod": m, "control": c}
    (ROOT / "private" / "work" / PREFIX / tag / "judge.json").write_text(json.dumps(result, indent=1) + "\n")
    print(json.dumps({k: result[k] for k in ("invalid", "checks", "pass", "c6_informative", "secondary")}, indent=1))
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
        print(json.dumps({k: v for k, v in run_case(a.tag, case).items() if k != "live_initial_hex"}), flush=True)
    sys.exit(judge(a.tag) if a.cases == "base,mod,control" else 0)
