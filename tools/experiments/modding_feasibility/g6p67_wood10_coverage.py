#!/usr/bin/env python3
"""E-553 (D-316) G6-P67: placement coverage of the remaining editable wood_10 actors (hidden, read-only probes).

    g6p67_wood10_coverage.py inventory      the seven-instance inventory (no game; private/work/e553/inventory.json)
    g6p67_wood10_coverage.py prepare        export the P mod with the editor core (no game)
    g6p67_wood10_coverage.py run K|P TAG    one hidden run (K = control without a mod, P = placement)
    g6p67_wood10_coverage.py judge K|P TAG  (judge P needs a valid K)
    g6p67_wood10_coverage.py negatives TAG  offline negative controls of the judge on mutated recorded data
                                            (added after the runs; judge thresholds unchanged, predicates refactored)

PROSPECTIVE PROTOCOL (committed before any run; thresholds are not changed after results)
Purpose: development-only placement classification of the five wood_10 instances the G6-P66 run did not test, and a
read-only observation of their idle behaviour state. It does not verify interaction or gameplay and does not promote
wood_10 out of development (D-315). Method, probes, build rule and safety are E-552's (g6p66_wood10_runtime.py), with
E-523 amendment 1 readback; the harness adds a control run and behaviour-state sampling only.
Build: the live development build (config/release/production_identity.json `development`, D-313; 08e4eec2...);
R3HD_DEV_STRUCTURAL_TX, R3HD_EXE and R3HD_DEV_EDITOR_LEVELS absent from the game environment; no other r3hd.exe.
Instances (editor model order; placements so / matrix / snapshot are wood_10.lvl file offsets):
  Powerz #0     (50.2314, -29.5631, 2.8911)  so 0x426528 matrix 0x4265EC snapshot 0x4EFCFC  E-552 VERIFIED PLACEMENT
  Powerz #1     (-5.0586, -15.2313, 4.5311)  so 0x43C6EC matrix 0x43C7B0 snapshot 0x4EDD28  P: +3 x
  Powerz #2     (3.0078, -174.2474, -35.1511) so 0x4477F0 matrix 0x4478B4 snapshot 0x4ED3A4 P: +3 x
  Powerz #3     (304.0033, -65.7410, -19.3223) so 0x48F148 matrix 0x48F20C snapshot 0x4ED4A0 P: +3 x
  Powerz #4     (76.9702, -166.9085, -26.6934) so 0x49AB78 matrix 0x49AC3C snapshot 0x4F0140 P: +3 x
  Chameleon #0  (65.4595, 31.8054, -3.4026)  so 0x43D608 matrix 0x43D6CC snapshot 0x4ED794  E-552 VERIFIED PLACEMENT
  Chameleon #1  (68.2627, -140.7956, -9.3934) so 0x49DE6C matrix 0x49DF30 snapshot 0x4F03E0 P: +3 x
  +3 x chosen offline (static collision, `inventory`): every moved point keeps its original relation to the collision
  mesh within 0.4 unit of clearance (Powerz #3 sits 1.1-1.5 above the nearest surface instead of 0.4), stays >= 96
  units from the isolated player spawn (a can's Wait script takes it within 3 units) and >= 32 units from every
  other of the seven (nearest pair: Powerz #4 / Chameleon #1, 32.5). The #0 instances are NOT edited in P: they are in-run controls for unrelated actors.
Mod P: the editor export of a wood_10 project (R3HD_DEV_EDITOR_LEVELS=wood_10 for `prepare` only), id
  g6p67.wood10-coverage, 10 same-size 12-byte ranges (5 matrices +0x34, 5 snapshots +0x34), imported into a private
  mods root with the mod manager (cmd_import --enable) and planned by resolve_all. K: no mod, no plan variable.
Runs: m9_license_run.py -> run_milestone6.ps1 (hidden window, muted, no physical pad, private --user-root,
  --test-level wood_10, --play, no input steps, no captures), 260 s process, 200 s of samples every 0.1 s after the
  level file opens. Live observation: block8_probe.areas level area base AB (guest of file offset o = AB + o - 4);
  m5_live.Actor on all seven SuperObjects: position and alive every sample; normal and reflex behaviour names
  (comport) recorded whenever they change; guest readback of the P ranges and of the two #0 matrix / snapshot
  ranges at the first and the last read. Order: K first, then P; one run each; a rerun only after a committed
  amendment for an INVALID run or a demonstrated harness defect. "At P" means within 0.01 units.
Invalid (either run): the level does not open; any of the seven actors cannot be read at the first sample; sampling
  ends before 150 s. P is judged only against a valid K.
  K1 nothing served: no "M33 mods served" line; every instance at its original position at the first sample.
  K2 safety as W4: haptics line; M21 / M22 / M23 judges 0; runner exit 0; no game process left.
  P1 served: exactly the 10 compiled ranges of wood_10.lvl, from the one active mod; gameplay line present.
  P2 readback (E-523 amendment 1): P matrix ranges equal the compiled bytes at the first read; P snapshot ranges
     equal the compiled bytes word-swapped at the first and the last read.
  P3 unrelated actors: Powerz #0 / Chameleon #0 matrix ranges equal the original file bytes at the first read and
     their snapshot ranges the original bytes word-swapped at the first and the last read; both at their original
     position at the first and the last sample.
  P4 safety as K2.
  Classification, never a pass criterion: per edited instance VERIFIED PLACEMENT / APPEARED AT AUTHORED, THEN MOVED /
     SCRIPT-OVERRIDDEN OR NOT SERVED / ELSEWHERE / NOT OBSERVED (g6p34 classify, first and last sample); and the K
     result of the same instance at its original position (an instance that moves by itself in K cannot be judged
     "kept" in P: its class is then reported with that caveat).
  Behaviour state, classification only: per instance the ordered set of distinct (normal, reflex) behaviour names in
     P versus K: SAME IDLE STATE / DIFFERENT IDLE STATE (listed) / NOT OBSERVED. SAME IDLE STATE says only that, in an
     isolated no-input entry, the move did not change which behaviour the actor runs; it is not interaction evidence.
Verdict: RUN VALID iff K1, K2 (K) and P1-P4 (P) pass and neither run is invalid. Classes are recorded as
development-only evidence for these exact instances (not their models, not other levels, not played progression).
Outputs: private/work/e553 (numbers and behaviour names only).
"""
import hashlib
import json
import math
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
WORK = ROOT / "private" / "work" / "e553"
PREFIX = "e553"
LEVEL = "wood_10"
MID = "g6p67.wood10-coverage"
ALL = (("powerz0", "YAM_mPowerz", 0), ("powerz1", "YAM_mPowerz", 1), ("powerz2", "YAM_mPowerz", 2),
       ("powerz3", "YAM_mPowerz", 3), ("powerz4", "YAM_mPowerz", 4), ("chameleon0", "NIK_mChameleon", 0),
       ("chameleon1", "NIK_mChameleon", 1))
EDITED = ("powerz1", "powerz2", "powerz3", "powerz4", "chameleon1")
CONTROLS = ("powerz0", "chameleon0")
DX = (3.0, 0.0, 0.0)
SPAWN = (-22.97, 78.74, 18.16)          # isolated-entry player position (M14 scan of wood_10)
N_RANGES = 2 * len(EDITED)


def model():
    os.environ[core.DEV_LEVELS_ENV] = LEVEL
    try:
        return core.RemixModel(GAME, LEVEL)
    finally:
        os.environ.pop(core.DEV_LEVELS_ENV, None)


def keyed(m):
    """label -> (key, instance) for the seven instances, by model name and instance number."""
    out = {}
    for label, name, inst in ALL:
        out[label] = next(k for (k, i), a in m.actors.items() if a["name"] == name and i == inst)
    return out


def authored(m, keys):
    return {lb: g34.plus(m.actors[(keys[lb], int(lb[-1]))]["position"], DX) for lb in EDITED}


def project(m):
    keys = keyed(m)
    want = authored(m, keys)
    os.environ[core.DEV_LEVELS_ENV] = LEVEL
    try:
        p = core.new_remix(LEVEL)
        p["meta"]["id"] = MID
        p["actors"] = [{"model": keys[lb], "instance": int(lb[-1]), "position": want[lb],
                        "matrix_sha256": m.actors[(keys[lb], int(lb[-1]))]["matrix_sha256"]} for lb in EDITED]
        return keys, want, core.check_remix(p)
    finally:
        os.environ.pop(core.DEV_LEVELS_ENV, None)


def control_ranges(m, keys):
    """The two #0 instances' matrix / snapshot 12-byte ranges with the ORIGINAL file bytes."""
    out = []
    for lb in CONTROLS:
        pl = m.ix["placements"][keys[lb]][0]
        for what in ("matrix", "snapshot"):
            o = pl[what] + 0x34
            out.append((lb, o, m.lvl[o:o + 12].hex(), f"{lb} {what}"))
    return out


def _segments(tris):
    return [tuple(tuple(map(float, p)) for p in t[:3]) for t in tris]


def _sub(a, b): return tuple(x - y for x, y in zip(a, b))
def _dot(a, b): return sum(x * y for x, y in zip(a, b))
def _add(a, b): return tuple(x + y for x, y in zip(a, b))
def _mul(a, k): return tuple(x * k for x in a)


def _pt_tri(p, a, b, c):
    """Distance from p to triangle abc (Ericson, closest point); degenerate triangles fall back to vertices."""
    try:
        ab, ac, ap = _sub(b, a), _sub(c, a), _sub(p, a)
        d1, d2 = _dot(ab, ap), _dot(ac, ap)
        if d1 <= 0 and d2 <= 0:
            return math.dist(p, a)
        bp = _sub(p, b)
        d3, d4 = _dot(ab, bp), _dot(ac, bp)
        if d3 >= 0 and d4 <= d3:
            return math.dist(p, b)
        vc = d1 * d4 - d3 * d2
        if vc <= 0 and d1 >= 0 and d3 <= 0:
            return math.dist(p, _add(a, _mul(ab, d1 / (d1 - d3))))
        cp = _sub(p, c)
        d5, d6 = _dot(ab, cp), _dot(ac, cp)
        if d6 >= 0 and d5 <= d6:
            return math.dist(p, c)
        vb = d5 * d2 - d1 * d6
        if vb <= 0 and d2 >= 0 and d6 <= 0:
            return math.dist(p, _add(a, _mul(ac, d2 / (d2 - d6))))
        va = d3 * d6 - d5 * d4
        if va <= 0 and (d4 - d3) >= 0 and (d5 - d6) >= 0:
            return math.dist(p, _add(b, _mul(_sub(c, b), (d4 - d3) / ((d4 - d3) + (d5 - d6)))))
        den = 1 / (va + vb + vc)
        return math.dist(p, _add(a, _add(_mul(ab, vb * den), _mul(ac, vc * den))))
    except ZeroDivisionError:
        return min(math.dist(p, q) for q in (a, b, c))


def clearance(tris, p):
    return min(_pt_tri(p, *t) for t in tris)


def inventory():
    m = model()
    keys = keyed(m)
    want = authored(m, keys)
    tris = _segments(m.tris)
    rows = []
    for label, name, inst in ALL:
        a = m.actors[(keys[label], inst)]
        pl = m.ix["placements"][keys[label]][inst]
        new = want.get(label)
        others = [want.get(o) or m.actors[(keys[o], int(o[-1]))]["position"] for o, _, _ in ALL if o != label]
        rows.append({
            "label": label, "model": name, "instance": inst, "status": a["status"],
            "so": hex(pl["so"]), "matrix": hex(pl["matrix"]), "snapshot": hex(pl["snapshot"]),
            "matrix_sha256": a["matrix_sha256"], "original": [round(c, 4) for c in a["position"]],
            "proposed": [round(c, 4) for c in new] if new else None,
            "edited_ranges": ([f"wood_10.lvl {pl['matrix'] + 0x34:#x}+12", f"wood_10.lvl {pl['snapshot'] + 0x34:#x}+12"]
                              if new else []),
            "clearance_original": round(clearance(tris, a["position"]), 3),
            "clearance_proposed": round(clearance(tris, new), 3) if new else None,
            "spawn_distance": round(math.dist(new or a["position"], SPAWN), 2),
            "nearest_other_edited_or_control": round(min(math.dist(new or a["position"], o) for o in others), 2),
            "prior_placement_evidence": "E-552 e552_r1_W VERIFIED PLACEMENT (+3 x)" if label in CONTROLS else None})
    ident = {"lvl": m.hashes["lvl"], "ptr": m.hashes["ptr"], "transit": m.hashes["transit"],
             "pinned": all(m.hashes[k] == core.DEV_LEVELS[LEVEL][k] for k in ("lvl", "ptr", "transit"))}
    out = {"identity": ident, "instances": rows}
    WORK.mkdir(parents=True, exist_ok=True)
    (WORK / "inventory.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out, indent=1))
    return 0


def prepare():
    os.environ.pop(rm.STRUCT_ENV, None)
    m = model()
    _, _, p = project(m)
    d = WORK / "mods" / "P"
    if d.exists():
        shutil.rmtree(d)
    os.environ[core.DEV_LEVELS_ENV] = LEVEL
    try:
        r = core.validate_remix(p, GAME, d, model=m)
    finally:
        os.environ.pop(core.DEV_LEVELS_ENV, None)
    if not r["ok"] or r["ranges"] != N_RANGES:
        raise SystemExit(f"P: {r}")
    (WORK / "mods" / "P_project.json").write_text(json.dumps(p, indent=1) + "\n")
    (WORK / "mods" / "P_ranges.json").write_text(json.dumps(r["range_list"], indent=1) + "\n")
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


def run(case, tag):
    import block8_probe as bp
    from m5_live import Actor, Process
    if case not in ("K", "P"):
        raise SystemExit("case must be K or P")
    if os.environ.get(rm.STRUCT_ENV):
        raise SystemExit(f"{rm.STRUCT_ENV} is set")
    m = model()
    keys = keyed(m)
    run_ = f"{PREFIX}_{tag}_{case}"
    work = WORK / "runs" / f"{tag}_{case}"
    if work.exists() or (RUNS / run_).exists():
        raise SystemExit(f"exists: {work} or {RUNS / run_}")
    if "r3hd.exe" in subprocess.run(["tasklist", "/FI", "IMAGENAME eq r3hd.exe", "/NH"], capture_output=True,
                                    text=True).stdout:
        raise SystemExit("another r3hd.exe is running")
    bins = binaries()
    if not bins["equals_development_identity"]:
        raise SystemExit(f"live build is not the development identity: {bins}")
    work.mkdir(parents=True)
    row = {"run": run_, "case": case, "binaries": bins}
    env = dict(os.environ)
    for k in ("R3HD_MODS_PLAN", "R3HD_EXE", rm.STRUCT_ENV, core.DEV_LEVELS_ENV):   # default build only
        env.pop(k, None)
    rngs = [(o, bytes.fromhex(d)) for _, o, d, _ in control_ranges(m, keys)]
    if case == "P":
        paths = {"home": None, "game": GAME, "mods": work / "mods", "cache": work / "cache"}
        rm.cmd_import(paths, WORK / "mods" / "P", enable=True)
        res = rm.resolve_all(paths, write_plan=paths["cache"])
        row.update(plan_active=res["active"], plan_ranges=res["ranges"], gameplay_active=res["gameplay_active"],
                   structural_active=res["structural_active"])
        env["R3HD_MODS_PLAN"] = row["plan"] = str(paths["cache"] / rm.PLAN_NAME)
        rngs += [(o, bytes.fromhex(d)) for _, o, d, _ in json.loads((WORK / "mods" / "P_ranges.json").read_text())]
    sos = {label: m.ix["placements"][keys[label]][inst]["so"] for label, _, inst in ALL}
    seconds, watch = 260, 200
    (work / "steps.txt").write_text(f"wait {seconds - 8}\n", encoding="ascii")
    samples, states, reads, pid = [], [], {}, None
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
            last_state = {}
            t_end = time.monotonic() + watch
            while time.monotonic() < t_end and pr.running():
                t = round(time.monotonic() - opened, 3)
                smp = {"t": t, "a": {}}
                for label, a in list(acts.items()):
                    try:
                        smp["a"][label] = [list(a.position()), a.alive()]
                        st = [a.comport(), a.comport(True)] if a.mind else [None, None]
                    except Exception:
                        smp["a"][label] = None
                        st = None
                    if st is not None and st != last_state.get(label):
                        states.append({"t": t, "label": label, "normal": st[0], "reflex": st[1]})
                        last_state[label] = st
                samples.append(smp)
                time.sleep(0.1)
            reads["last"] = read_back() if pr.running() else {}
            row["last_t"] = samples[-1]["t"] if samples else None
        game.wait(timeout=seconds + 240)
        row["runner_exit"] = game.returncode
        r_ = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True) if pid else None
        row["process_left"] = bool(pid and str(pid) in r_.stdout)
    for name, obj in (("samples", samples), ("states", states), ("reads", reads), ("row", row)):
        (work / f"{name}.json").write_text(json.dumps(obj, indent=1, default=str) + "\n")
    print(json.dumps(row, default=str)[:1500])
    return 0


def _swap(hexs):
    b = bytes.fromhex(hexs)
    return b"".join(b[i:i + 4][::-1] for i in range(0, len(b), 4)).hex()


def _load(case, tag):
    work = WORK / "runs" / f"{tag}_{case}"
    return work, {n: json.loads((work / f"{n}.json").read_text()) for n in ("row", "samples", "states", "reads")}


def _first_last(S):
    labels = [lb for lb, _, _ in ALL]
    first = {lb: (S[0]["a"].get(lb) or [None])[0] for lb in labels} if S else {}
    last = {lb: next((x["a"][lb][0] for x in reversed(S) if x["a"].get(lb)), None) for lb in labels}
    alive = {lb: next((x["a"][lb][1] for x in reversed(S) if x["a"].get(lb)), None) for lb in labels}
    return first, last, alive


def _invalid(row, S, first):
    if row.get("error") or not S or (S[-1]["t"] - S[0]["t"]) < 150 or not all(first.values()):
        return ["level / actors / sampling window"]
    return []


def _served(run_):
    return sorted({(f.lower(), int(o), int(n)) for mid, f, o, n in
                   re.findall(r"M33 mods served mod=(\S+) file=(\S+) offset=(\d+) length=(\d+)", g34.log_of(run_))})


def _state_sets(states):
    out = {}
    for s in states:
        seq = out.setdefault(s["label"], [])
        st = [s["normal"], s["reflex"]]
        if st not in seq:
            seq.append(st)
    return out


def _at(p, q):
    return p is not None and q is not None and math.dist(p, q) < 0.01


def _readback(rl, reads):
    """E-523 amendment 1: matrix ranges exact at the first read; snapshot ranges word-swapped at first and last."""
    ok = True
    for _, o, d, w in rl:
        g = {k: (reads.get(k) or {}).get(str(o)) for k in ("first", "last")}
        ok &= (g["first"] == d) if w.endswith(" matrix") else (g["first"] == _swap(d) and g["last"] == _swap(d))
    return bool(ok)


def _bstate(p_, k_):
    return ("NOT OBSERVED" if not p_ or not k_ else "SAME IDLE STATE" if p_ == k_
            else f"DIFFERENT IDLE STATE (P {p_} / K {k_})")


def negatives(tag):
    """Offline negative controls: the judge's own predicates on mutated copies of the recorded K / P data."""
    m = model()
    keys = keyed(m)
    orig = {lb: list(m.actors[(keys[lb], inst)]["position"]) for lb, _, inst in ALL}
    _, want, _ = project(m)
    _, P = _load("P", tag)
    _, K = _load("K", tag)
    rl = json.loads((WORK / "mods" / "P_ranges.json").read_text())
    pf, pl, _ = _first_last(P["samples"])
    kf, kl, _ = _first_last(K["samples"])
    exp = sorted((f"{LEVEL}.lvl", o, len(d) // 2) for _, o, d, _ in rl)
    snap = next(o for _, o, _, w in rl if w.endswith(" snapshot"))
    mat = next(o for _, o, _, w in rl if w.endswith(" matrix"))
    cmat = next(o for _, o, _, w in control_ranges(m, keys) if w.endswith(" matrix"))

    def mutated(reads, which, o, f):
        r = json.loads(json.dumps(reads))
        r[which][str(o)] = f(r[which][str(o)])
        return r
    raw = lambda h: _swap(h)                                    # noqa: E731  (undo the loader's word swap)
    flip = lambda h: ("0" if h[0] != "0" else "1") + h[1:]      # noqa: E731
    rows = {
        "N0 recorded P data passes P2 / P3 bytes (sanity)": (
            _readback(rl, P["reads"]) and _readback(control_ranges(m, keys), P["reads"])),
        "N1 snapshot range left in file order -> P2 FAIL": not _readback(rl, mutated(P["reads"], "first", snap, raw)),
        "N2 matrix range one nibble changed -> P2 FAIL": not _readback(rl, mutated(P["reads"], "first", mat, flip)),
        "N3 last snapshot read missing -> P2 FAIL": not _readback(rl, mutated(P["reads"], "last", snap, lambda h: "")),
        "N4 control #0 matrix changed -> P3 FAIL": not _readback(control_ranges(m, keys),
                                                                 mutated(P["reads"], "first", cmat, flip)),
        "N5 K reads against P ranges (mod not served) -> P2 FAIL": not _readback(rl, K["reads"]),
        "N6 K positions classified as P -> SCRIPT-OVERRIDDEN OR NOT SERVED for all five": all(
            g34.classify(kf[lb], kl[lb], want[lb], orig[lb]).startswith("SCRIPT-OVERRIDDEN") for lb in EDITED),
        "N7 last sample 0.02 off -> APPEARED AT AUTHORED, THEN MOVED": all(
            g34.classify(pf[lb], [pl[lb][0] + 0.02] + pl[lb][1:], want[lb], orig[lb]).startswith("APPEARED")
            for lb in EDITED),
        "N8 no first sample -> NOT OBSERVED": g34.classify(None, None, want["powerz1"], orig["powerz1"]) == "NOT OBSERVED",
        "N9 changed behaviour name -> DIFFERENT IDLE STATE": _bstate(
            [["YAM_cPowerz_4WaitSnipe", None]], [["YAM_cPowerz_00Init", None]]).startswith("DIFFERENT"),
        "N10 recorded P served list equals the plan; with one range dropped it does not -> P1 FAIL": (
            _served(P["row"]["run"]) == exp and _served(P["row"]["run"])[:-1] != exp),
        "N11 K served list is empty, not the P list -> P1 FAIL on K": _served(K["row"]["run"]) != exp,
    }
    for k, v in rows.items():
        print(("PASS " if v else "FAIL ") + k)
    (WORK / "runs" / f"{tag}_negatives.json").write_text(json.dumps(rows, indent=1) + "\n")
    print(f"{sum(rows.values())}/{len(rows)}")
    return 0 if all(rows.values()) else 1


def judge(case, tag):
    m = model()
    keys = keyed(m)
    orig = {lb: list(m.actors[(keys[lb], inst)]["position"]) for lb, _, inst in ALL}
    work, R = _load(case, tag)
    row, S = R["row"], R["samples"]
    first, last, alive = _first_last(S)
    invalid = _invalid(row, S, first)
    C, D = {}, {"first_t": row.get("first_t"), "last_t": row.get("last_t"), "binaries": row.get("binaries"),
                "alive_last": alive, "states": _state_sets(R["states"])}
    ok_s, judges = g34.safety(row["run"], row)
    D["judges"] = judges
    if case == "K":
        served = _served(row["run"])
        C["K1 nothing served; all seven at their original positions at the first sample"] = (
            not served and all(_at(first[lb], orig[lb]) for lb in orig))
        C["K2 safety: haptics, M21 / M22 / M23 0, runner exit 0, no process left"] = ok_s
        D["k_kept_original"] = {lb: _at(first[lb], orig[lb]) and _at(last[lb], orig[lb]) for lb in orig}
        D["k_last"] = {lb: [round(c, 4) for c in last[lb]] if last[lb] else None for lb in orig}
    else:
        kw, K = _load("K", tag)
        kj = json.loads((kw / "judge.json").read_text()) if (kw / "judge.json").is_file() else {}
        if not kj.get("valid"):
            invalid.append("no valid K for this tag")
        _, want, _ = project(m)
        rl = json.loads((WORK / "mods" / "P_ranges.json").read_text())
        reads = R["reads"]
        exp = sorted((f"{LEVEL}.lvl", o, len(d) // 2) for _, o, d, _ in rl)
        C[f"P1 served exactly the {N_RANGES} compiled ranges ({len(_served(row['run']))})"] = (
            [x for x in _served(row["run"])] == exp and bool(
                re.search(r"M33 mods gameplay mod=\S+ achievements=not_awarded", g34.log_of(row["run"]))) and
            all(mid == MID for mid in re.findall(r"M33 mods served mod=(\S+)", g34.log_of(row["run"]))))
        C["P2 guest readback (E-523 amendment 1)"] = _readback(rl, reads)
        C["P3 unrelated #0 actors: original bytes and positions"] = (
            _readback(control_ranges(m, keys), reads)
            and all(_at(first[lb], orig[lb]) and _at(last[lb], orig[lb]) for lb in CONTROLS))
        C["P4 safety: haptics, M21 / M22 / M23 0, runner exit 0, no process left"] = ok_s
        kd = kj.get("details", {})
        D["classes"] = {}
        for lb in EDITED:
            cls = g34.classify(first[lb], last[lb], want[lb], orig[lb])
            if not kd.get("k_kept_original", {}).get(lb):
                cls += " [caveat: moved by itself in K]"
            D["classes"][lb] = cls
        ks = kd.get("states", {})
        D["behaviour_state"] = {}
        for lb, _, _ in ALL:
            D["behaviour_state"][lb] = _bstate(D["states"].get(lb), ks.get(lb))
        D["authored"] = {lb: [round(c, 4) for c in want[lb]] for lb in EDITED}
        D["p_last"] = {lb: [round(c, 4) for c in last[lb]] if last[lb] else None for lb in orig}
    res = {"case": case, "invalid": invalid, "checks": C, "details": D,
           "valid": not invalid and all(C.values()),
           "tier": "development-only placement / idle-state classification (E-553); gameplay not verified"}
    (work / "judge.json").write_text(json.dumps(res, indent=1, default=str) + "\n")
    print(json.dumps(res, indent=1, default=str))
    return 0 if res["valid"] else 1


def main():
    a = sys.argv[1:]
    if a[:1] == ["inventory"]:
        return inventory()
    if a[:1] == ["prepare"]:
        return prepare()
    if a[:1] == ["run"] and len(a) == 3:
        return run(a[1], a[2])
    if a[:1] == ["judge"] and len(a) == 3:
        return judge(a[1], a[2])
    if a[:1] == ["negatives"] and len(a) == 2:
        return negatives(a[1])
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
