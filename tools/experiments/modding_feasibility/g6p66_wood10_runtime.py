#!/usr/bin/env python3
"""E-552 (D-315) G6-P66: one DEVELOPMENT-ONLY hidden run of a wood_10 editor export (read-only probes).

    g6p66_wood10_runtime.py prepare      export the wood_10 remix with the editor core (no game)
    g6p66_wood10_runtime.py run TAG      one hidden run
    g6p66_wood10_runtime.py judge TAG

PROSPECTIVE PROTOCOL (committed before any run; thresholds are not changed after results)
Purpose: Tier C evidence only. The result classifies placement of two actors; it does not verify gameplay and does not
promote wood_10 out of development (D-315). Method and probes are G6-P34's (E-523 case M, amendment 1 readback).
Build: the live development build named by config/release/production_identity.json `development` (D-313); its
r3hd.exe / rexruntime.dll SHA-256 are recorded in the row. R3HD_DEV_STRUCTURAL_TX absent in the parent and the game
environment (the editor variable R3HD_DEV_EDITOR_LEVELS is read by the editor only; it is set for `prepare` and removed
from the game environment).
Mod: the editor export of a wood_10 project (R3HD_DEV_EDITOR_LEVELS=wood_10), id g6p66.wood10-remix:
  YAM_mPowerz #0  original O_P -> O_P + (3, 0, 0)
  NIK_mChameleon #0 original O_C -> O_C + (3, 0, 0)
  4 same-size 12-byte ranges of wood_10.lvl (each actor's matrix +0x34 and snapshot +0x34), imported into a private
  mods root with the mod manager (cmd_import --enable) and planned by resolve_all.
Run: m9_license_run.py (run_milestone6.ps1: hidden window, muted, no physical pad, private --user-root, --test-level
wood_10, --play, no input steps, no captures), 260 s process, 200 s of samples every 0.1 s after the level file opens.
Live observation: block8_probe.areas for the level area base AB (guest address of file offset o = AB + o - 4);
m5_live.Actor on the two edited actors' SuperObjects; guest readback of the 4 ranges at the first and the last read.
At most one run; a rerun only after a committed amendment for an INVALID run or a demonstrated harness defect.
"At P" means within 0.01 units.
  W1 served: exactly the 4 compiled ranges of wood_10.lvl, from the one active mod; gameplay line present.
  W2 readback (E-523 amendment 1): matrix ranges equal the compiled bytes at the first read; snapshot ranges equal the
     compiled bytes word-swapped (authored value, native order) at the first and the last read.
  W3 classification only, never a pass criterion: per actor VERIFIED PLACEMENT (at P at the first and the last
     sample) / APPEARED AT AUTHORED, THEN MOVED / SCRIPT-OVERRIDDEN OR NOT SERVED / ELSEWHERE / NOT OBSERVED.
  W4 safety: haptics line; M21 / M22 / M23 judges 0; runner exit 0; no game process left.
  Invalid: the level does not open; an edited actor cannot be read at the first sample; sampling ends before 150 s.
Verdict: RUN VALID iff W1, W2 and W4 pass and the run is not invalid; the W3 classes are then recorded as
development-only placement evidence for these two exact instances (not their models, not other instances).
Outputs: private/work/e552 (numbers only).
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOLS = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(TOOLS))
import r3hd_mods as rm  # noqa: E402
import r3hd_level_editor_core as core  # noqa: E402
import g6p34_remix_runtime as g34  # noqa: E402

ROOT = TOOLS.parent
GAME = ROOT / "private" / "extracted" / "5841123F"
RUNS = ROOT / "private" / "work" / "m6_runs"
WORK = ROOT / "private" / "work" / "e552"
PREFIX = "e552"
LEVEL = "wood_10"
MID = "g6p66.wood10-remix"
TARGETS = (("powerz0", "YAM_mPowerz", 0), ("chameleon0", "NIK_mChameleon", 0))
DX = (3.0, 0.0, 0.0)


def model():
    os.environ[core.DEV_LEVELS_ENV] = LEVEL
    try:
        return core.RemixModel(GAME, LEVEL)
    finally:
        os.environ.pop(core.DEV_LEVELS_ENV, None)


def spec(m):
    acts = []
    for label, name, inst in TARGETS:
        k = next(k for (k, i), a in m.actors.items() if a["name"] == name and i == inst)
        acts.append((label, k, inst, g34.plus(m.actors[(k, inst)]["position"], DX)))
    return {"level": LEVEL, "actors": acts, "waypoints": []}


def project(m):
    s = spec(m)
    os.environ[core.DEV_LEVELS_ENV] = LEVEL
    try:
        p = core.new_remix(LEVEL)
        p["meta"]["id"] = MID
        p["actors"] = [{"model": k, "instance": i, "matrix_sha256": m.actors[(k, i)]["matrix_sha256"],
                        "position": pos} for _, k, i, pos in s["actors"]]
        return s, core.check_remix(p)
    finally:
        os.environ.pop(core.DEV_LEVELS_ENV, None)


def prepare():
    os.environ.pop(rm.STRUCT_ENV, None)
    m = model()
    s, p = project(m)
    d = WORK / "mods" / "W"
    if d.exists():
        shutil.rmtree(d)
    os.environ[core.DEV_LEVELS_ENV] = LEVEL
    try:
        r = core.validate_remix(p, GAME, d, model=m)
    finally:
        os.environ.pop(core.DEV_LEVELS_ENV, None)
    if not r["ok"] or r["ranges"] != 4:
        raise SystemExit(f"W: {r}")
    (WORK / "mods" / "W_project.json").write_text(json.dumps(p, indent=1) + "\n")
    (WORK / "mods" / "W_ranges.json").write_text(json.dumps(r["range_list"], indent=1) + "\n")
    out = {"id": MID, "ranges": r["ranges"], "mod_sha256": rm.sha256_bytes((d / "mod.json").read_bytes())}
    (WORK / "mods" / "prepared.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out, indent=1))
    return 0


def binaries():
    ident = json.loads((ROOT / "config" / "release" / "production_identity.json").read_text(encoding="utf-8"))
    want = (ident.get("development") or {}).get("binaries", {})
    folder = ROOT / "private" / "work" / "rex" / "out" / "build" / "win-amd64-release"
    have = {n: hashlib.sha256((folder / n).read_bytes()).hexdigest() for n in want if (folder / n).is_file()}
    return {"have": have, "equals_development_identity": bool(want) and have == want,
            "r3hd_exe_override": os.environ.get("R3HD_EXE")}


def run(tag):
    import block8_probe as bp
    from m5_live import Actor, Process
    if os.environ.get(rm.STRUCT_ENV):
        raise SystemExit(f"{rm.STRUCT_ENV} is set")
    m = model()
    s, _ = project(m)
    run_ = f"{PREFIX}_{tag}_W"
    work = WORK / "runs" / tag
    if work.exists() or (RUNS / run_).exists():
        raise SystemExit(f"exists: {work} or {RUNS / run_}")
    if "r3hd.exe" in subprocess.run(["tasklist", "/FI", "IMAGENAME eq r3hd.exe", "/NH"], capture_output=True,
                                    text=True).stdout:
        raise SystemExit("another r3hd.exe is running")
    work.mkdir(parents=True)
    paths = {"home": None, "game": GAME, "mods": work / "mods", "cache": work / "cache"}
    rm.cmd_import(paths, WORK / "mods" / "W", enable=True)
    res = rm.resolve_all(paths, write_plan=paths["cache"])
    row = {"run": run_, "plan_active": res["active"], "plan_ranges": res["ranges"],
           "gameplay_active": res["gameplay_active"], "structural_active": res["structural_active"],
           "binaries": binaries()}
    env = dict(os.environ)
    for k in ("R3HD_MODS_PLAN", "R3HD_EXE", rm.STRUCT_ENV, core.DEV_LEVELS_ENV):   # default build only
        env.pop(k, None)
    env["R3HD_MODS_PLAN"] = row["plan"] = str(paths["cache"] / rm.PLAN_NAME)
    rngs = [(o, bytes.fromhex(d)) for _, o, d, _ in json.loads((WORK / "mods" / "W_ranges.json").read_text())]
    sos = {label: m.ix["placements"][k][i]["so"] for label, k, i, _ in s["actors"]}
    seconds, watch = 260, 200
    (work / "steps.txt").write_text(f"wait {seconds - 8}\n", encoding="ascii")
    samples, reads, pid = [], {}, None
    with (work / "driver.log").open("w") as log:
        game = subprocess.Popen([sys.executable, str(TOOLS / "m9_license_run.py"), run_, str(work / "steps.txt"),
                                 "--license-mask", "1", "--seconds", str(seconds), "--play", "--test-level", LEVEL,
                                 "--user-root", run_], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
        needle = re.compile(rf"[\\/]{LEVEL}\.lvl result=00000000", re.IGNORECASE)
        opened = base = None
        end = time.monotonic() + 120
        while time.monotonic() < end and game.poll() is None and opened is None:
            time.sleep(0.5)
            lp = RUNS / run_ / "runtime.log"
            if lp.is_file():
                text = lp.read_text(errors="replace")
                opened = time.monotonic() if needle.search(text) else None
                mm = re.search(r"virtual base 0x0*([0-9A-Fa-f]+),", text)
                base = mm.group(1) if mm else base
        if opened is None or base is None:
            row["error"] = "level did not open"
        else:
            pid = json.loads((RUNS / run_ / "process.json").read_text(encoding="utf-8-sig"))["pid"]
            pr = Process(pid, int(base, 16))
            ab = None
            while time.monotonic() < opened + 20 and ab is None:
                ar = bp.areas(pr)
                ab = ar[1]["base"] if ar and ar.get(1) else None
                time.sleep(0.1)
            time.sleep(2.0)
            row["ab"] = hex(ab) if ab else None
            acts = {}
            for label, so in sos.items():
                if ab:
                    try:
                        acts[label] = Actor(pr, ab + so - 4)
                    except Exception as x:
                        row.setdefault("actor_errors", {})[label] = repr(x)
            row["actor_models"] = {k: a.model for k, a in acts.items()}

            def read_back():
                return {o: (pr.read(ab + o - 4, len(d)) or b"").hex() for o, d in rngs} if ab else {}
            reads["first"] = read_back()
            row["first_t"] = round(time.monotonic() - opened, 3)
            t_end = time.monotonic() + watch
            while time.monotonic() < t_end and pr.running():
                smp = {"t": round(time.monotonic() - opened, 3), "a": {}}
                for label, a in list(acts.items()):
                    try:
                        smp["a"][label] = [list(a.position()), a.alive()]
                    except Exception:
                        smp["a"][label] = None
                samples.append(smp)
                time.sleep(0.1)
            reads["last"] = read_back() if pr.running() else {}
            row["last_t"] = samples[-1]["t"] if samples else None
        game.wait(timeout=seconds + 240)
        row["runner_exit"] = game.returncode
        r_ = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True) if pid else None
        row["process_left"] = bool(pid and str(pid) in r_.stdout)
    for name, obj in (("samples", samples), ("reads", reads), ("row", row)):
        (work / f"{name}.json").write_text(json.dumps(obj, indent=1, default=str) + "\n")
    print(json.dumps(row, default=str)[:1200])
    return 0


def judge(tag):
    m = model()
    s, _ = project(m)
    work = WORK / "runs" / tag
    row = json.loads((work / "row.json").read_text())
    S = json.loads((work / "samples.json").read_text())
    reads = json.loads((work / "reads.json").read_text())
    run_ = row["run"]
    rl = json.loads((WORK / "mods" / "W_ranges.json").read_text())
    invalid = []
    first = {label: (S[0]["a"].get(label) or [None])[0] for label, _, _, _ in s["actors"]} if S else {}
    if row.get("error") or not S or (S[-1]["t"] - S[0]["t"]) < 150 or not all(first.values()):
        invalid.append("level / actors / sampling window")
    C, D = {}, {}
    log = g34.log_of(run_)
    want = sorted((f"{LEVEL}.lvl", o, len(d) // 2) for _, o, d, _ in rl)
    got = sorted({(f.lower(), int(o), int(n)) for mid, f, o, n in
                  re.findall(r"M33 mods served mod=(\S+) file=(\S+) offset=(\d+) length=(\d+)", log) if mid == MID})
    C[f"W1 served exactly the 4 compiled ranges ({len(got)})"] = got == want and bool(
        re.search(r"M33 mods gameplay mod=\S+ achievements=not_awarded", log))
    ok = True
    for _, o, d, w in rl:
        b = bytes.fromhex(d)
        sw = b"".join(b[i:i + 4][::-1] for i in range(0, len(b), 4)).hex()
        g = {k: (reads.get(k) or {}).get(str(o)) for k in ("first", "last")}
        ok &= (g["first"] == d) if w.endswith(" matrix") else (g["first"] == sw and g["last"] == sw)
    C["W2 guest readback (E-523 amendment 1)"] = bool(ok)
    lastv = {k: next((x["a"][k][0] for x in reversed(S) if x["a"].get(k)), None) for k in first}
    D["classes"] = {label: g34.classify(first[label], lastv[label], pos, list(m.actors[(k, i)]["position"]))
                    for label, k, i, pos in s["actors"]}
    D["alive_last"] = {k: next((x["a"][k][1] for x in reversed(S) if x["a"].get(k)), None) for k in first}
    D["first_t"], D["last_t"], D["binaries"] = row.get("first_t"), row.get("last_t"), row.get("binaries")
    ok4, judges = g34.safety(run_, row)
    C["W4 safety: haptics, M21 / M22 / M23 0, runner exit 0, no process left"] = ok4
    D["judges"] = judges
    res = {"invalid": invalid, "checks": C, "details": D, "valid": not invalid and all(C.values()),
           "tier": "development-only placement classification (E-552); gameplay not verified"}
    (work / "judge.json").write_text(json.dumps(res, indent=1, default=str) + "\n")
    print(json.dumps(res, indent=1, default=str))
    return 0 if res["valid"] else 1


def main():
    a = sys.argv[1:]
    if a[:1] == ["prepare"]:
        return prepare()
    if a[:1] == ["run"] and len(a) == 2:
        return run(a[1])
    if a[:1] == ["judge"] and len(a) == 2:
        return judge(a[1])
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
