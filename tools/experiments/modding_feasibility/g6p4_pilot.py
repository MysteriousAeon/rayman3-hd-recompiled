#!/usr/bin/env python3
"""E-490 (D-257) G6-P4: an actor -> actor reference. Development-only; private; hidden.

Selected relationship (bounded census of type-18 designer variables in intro_10 / 15 / 17 / 20, `census`; decode of
the manager's behaviours): intro_10's `MAN_mGenManager_Frog` (model NIK_mGenManager, the only instance, SuperObject
0x53C3F0, block 0x11E4 to the next SuperObject). Its designer variable 0 (type 18, actor) is an own-file relocated
word naming the SuperObject of `MAN_mGenSound_Frog` (NIK_mGenSound instance 2, 0x53BED0) in both buffers (initial
+0xED0, current +0x10DC). Its active behaviour NIK_C_mGenManager_GestionType_0 (designer variable 1 = 0) sets v4
(type 19) = value call 0xAD(v2 = its graph, main actor) and, if v4 is valid, v6 = v4's position and runs procedure
0xDB (219) on (v0, v6): the actor v0 names is moved onto a waypoint of the manager's graph (graph 0x53D2E0, 8 nodes,
stored inside the manager's block at +0xEF0..+0x10DC). The two other NIK_mGenSound instances (SmallRiver 0x53A09C,
Forest 0x53B9B0) are same-model alternative targets; NIK_mGenSound's scripts do not set positions themselves.

  g6p4_pilot.py census                 offline candidate census (writes private/work/e490/census.json)
  g6p4_pilot.py oracle TAG             controlled reference oracle (production build, no structural growth):
                                       A (no plan), RS / RF (the manager's two v0 words redirected to SmallRiver /
                                       Forest: a same-size .lvl edit of two existing relocated words)
  g6p4_pilot.py oracle-judge TAG       Q1-Q6
Outputs: private/work/e490/.

ORACLE PROTOCOL (committed before the oracle runs)
Runs: m9_license_run.py hidden, non-activating, muted, no physical pad, private user root, `--test-level intro_10`,
no input, no frames, 130 s; production build. 6 s after intro_10's area appears: the manager, the three GenSound
actors read at their file SuperObjects (area base + offset - 4); then every 0.1 s: the three GenSound positions, the
manager's live v0 words (initial and current buffers) and its live v4 (current buffer +8) with the position of the
waypoint it names. W = the set of the manager graph's eight waypoint positions (file values).
"At W" = within 0.01 units of a waypoint of W; "at home" = within 0.01 of the actor's file translation.
  A: no plan.  RS: plan e490.redirect-smallriver.  RF: plan e490.redirect-forest.  Target T: A Frog, RS SmallRiver,
  RF Forest; the other two GenSound actors are the non-targets.
  Q1 serving: RS / RF `M33 mods state=active`, served intro_10.lvl only, no `M36 grow`, no G5P1 / G5P3 / G6P1 line;
     A `M33 mods=off`.
  Q2 guest resolution: in every sample the manager's live v0 words (both buffers) = area base + T's SuperObject - 4.
  Q3 consumption: in the samples from 10 s after the first read, T is at W in >= 90 % of samples.
  Q4 reference-specific: both non-targets are at home in every sample (none ever at W), and in RS / RF the Frog is
     at home in every sample (it is no longer moved).
  Q5 guest witness: in >= 90 % of the samples in which v4 names a waypoint, T's position equals that waypoint's
     position within 0.01, or the previous sample's (one AI run of lag).
  Q6 safety: M21 / M22 / M23 0, haptics policy line, runner exit 0, no game process naming the run left, no access
     violation / engine error line, fault codes within {406D1388}.
  Invalid (new tag, kept): intro_10 not loaded, an actor unreadable, < 60 s of samples, A fails Q3 (the manager
     moves nothing without input: then no oracle exists and the milestone stops as research).
  All six = ORACLE VERIFIED: the actor the manager moves is the one its v0 reference names.
ORACLE RESULT o1 (oracle_o1.json): ORACLE VERIFIED, Q1-Q6 PASS in A / RS / RF. In ~970 samples each, T at W and at
  v4's waypoint in every sample; the two non-targets at home in every sample; RS / RF: the Frog at home throughout.
  One waypoint only in each window (the waypoint choice function 0xAD stays a HYPOTHESIS: nearest to the main actor).

EXIT-ROUTE PROBE (read-only, no plan, production build; informs the runtime protocol, judges nothing):
  g6p4_pilot.py route TAG   one hidden run X: intro_10 opened directly, after 45 s G5-P3's Exit Game sequence.
  x1 (route_x1.json): menumap opens after intro_10, area left 64 s after it appeared; fix-only 20,795,836 (1 / 1)
  between; menumap 13,274,536 free.

  g6p4_pilot.py check            offline O1-O8 (offline.json)
  g6p4_pilot.py negtest          transaction tests (dev + production headers) and G6-P3's chained suites
  g6p4_pilot.py run TAG          hidden runs A, B, C, D (development build)
  g6p4_pilot.py judge TAG        P1-P8

OPERATION (manifest): {"type": "insert-gensound-manager", "level": "intro_10", "model": GM10, "instance": 0,
  "lvl_sha256", "ptr_sha256", "transit_sha256", "moves_gensound_instance": 0 | 1} (0 = MAN_mGenSound_AmbGeneral_Forest
  0x53A09C, 1 = MAN_YmGenSound_SmallRiver 0x53B9B0; resolved and asserted from the exact files: a NIK_mGenSound actor
  of the world, not the Frog, named by no designer buffer). No addresses, offsets, slots, relocation values, script
  or designer bytes, other levels / models / instances, a second actor, or composition.
CONSTRUCTION: copy SuperObject 0x74E910; segments [+0, +0x338) -> +0, [+0xD6C, +0xEF0) -> +0x33C, [+0x10DC, +0x11E4)
  -> +0x4CC (copy 1,492 bytes); its own Perso / 3dData / StdGame / Brain / Mind / Intelligence (+0x33C) / DsgMem
  (+0x494) / buffers (+0x4A0, +0x4CC); AI model, DsgVar, behaviours, graph = the source's (kept); v0 = the target;
  personal type 69 `MAN_mGenManager_Frog_G6P4`; SO record; backups -> copy +0x52C / +0x52E / +0xC4; always element;
  transit actor count 61. .lvl +1,796 (7,663,632), .ptr +528 (209,596).

RUNTIME PROTOCOL (committed before the development build and before any modified run)
Build: g5p1_dev_gate.py apply (unchanged gate: intro_10 version 2 already allowed) + tools\\build_incremental.bat;
production restored afterwards. Runs: m9_license_run.py hidden, non-activating, muted, no physical pad, private user
root, `--test-level intro_10`, 150 s; guest-scoped input only for the exit (85 s after intro_10 opened, x1's Exit Game
sequence). Reads (read-only): block-8 snapshot at every area-table change; 6 s after the area appears the source
manager, the copy (B / C) and the three GenSound actors and the actor lists once; every 0.1 s the GenSound positions
and, for each manager, its live v0 words and v4 waypoint position, until the area is left; the actor / list read
again 80 s after the area appeared.
  A: no plan.  B: moves_gensound_instance 0 (mod g6p4.manager-forest, session = run, R3HD_DEV_STRUCTURAL_TX=intro_10).
  C: moves_gensound_instance 1 (g6p4.manager-smallriver, same).  D: B's plan with the development variable unset.
  T = the copy's target (B Forest 0x53A09C, C SmallRiver 0x53B9B0); N = the other of the two. W, "at W", "at home",
  X(o) = AB + o - 4 as in the oracle; t >= first read + 10 s for "moved" fractions.
  P1 transaction: B / C one `M33 mods state=active`; `G5P1 level-tx active level=intro_10 mod=<mod> id=<plan id>`;
     `G6P1 level-tx version=2 members=lvl,ptr,transit`; snapshots intro_10.lvl 7663632, intro_10.ptr 209596,
     transit.lvl 41508; grow lines 7661836 -> 7663632, 209068 -> 209596, 41508 -> 41508; served exactly the three;
     no host change. A `M33 mods=off`.
  P2 registration (first read): the copy X(0x74E910) alive (reciprocal links), model NIK_mGenManager; the world union
     = A's + exactly the copy, once, links consistent; SO records A + 1 with the copy once; backup targets A's + the
     copy's three (X(copy + 0x52C), X(copy + 0x52E), X(copy + 0xC4)) once each; personal types 70, the last
     `MAN_mGenManager_Frog_G6P4`. A / D: 69, no copy.
  P3 target resolution (B / C, first and 80-s reads): the copy's Perso / 3dData / Brain / Mind / Intelligence /
     DsgMem / initial / current = X(copy + 0x80 / 0xAC / 0x318 / 0x324 / 0x33C / 0x494 / 0x4A0 / 0x4CC); its AI model
     (Mind +0) and DsgMem model = the source's; its live v0 words = X(T) and v2 words = X(0x53D2E0) (both buffers);
     the source's v0 = X(Frog) and v2 = X(0x53D2E0) in all four.
  P4 guest consumption (B / C): the copy's live v4 names a waypoint in >= 90 % of samples (its GestionType_0 runs);
     T at W in >= 90 % of the moved samples; T's position = the copy's v4 waypoint (or the previous sample's) in
     >= 90 % of the samples where that v4 is valid; the copy's behaviour name = the source's.
  P5 target-specific consequence: N at home in every sample of B / C (never at W); in A / D Forest and SmallRiver
     at home in every sample; the Frog (the source manager's target) at W in >= 90 % of the moved samples in all four;
     changing only the selector (B -> C) moves the moved actor from Forest to SmallRiver.
  P6 integrity: both world walks' links consistent at both reads, no list read error; the copy alive and once in the
     union at the 80-s read; no access violation / engine error line; fault codes within {406D1388}.
  P7 lifetime / cleanup: route taken in all four (intro_10 -> menumap, area left); loaded B - A = C - A = {area 1
     length +1,796, free -1,796, largest -1,796}, D - A = {}; block 8 between intro_10 and menumap fix only
     (20,795,836 free, 1 / 1) in all four; menumap state equal to A's in B, C, D.
  P8 safety: D `state=refused reason=level_tx_not_enabled`, nothing served, no grow, no development line; every run
     M21 / M22 / M23 0, haptics policy line, runner exit 0, no game process naming the run left; B / C markers armed
     (session, plan SHA-256) and cleared after the controlled end; check and negtest passed first.
  Invalid (new tag, kept): process / area not found, a tracked actor unreadable at the first read, < 60 s of samples,
     A's Frog not moved (P5 Frog term fails in A), the route not taken in A.
  Stop: a guest fault, bad actor ownership, invalid reference resolution or a desktop-safety violation.
  All eight = G6-P4 VERIFIED — ACTOR-TO-ACTOR REFERENCE INSERTION; P1-P3 with P4 or P5 failing = PARTIAL — REFERENCE
  RESOLVED, CONSUMPTION UNVERIFIED.
"""
import hashlib
import json
import math
import os
import re
import shutil
import struct
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TOOLS = ROOT / "tools"
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(HERE))
import r3hd_mods as rm  # noqa: E402
import g3a_ab as g3a  # noqa: E402
import block8_probe as bp  # noqa: E402
import g6p3_pilot as g6p3  # noqa: E402  (generic readers: actor_state, lists, safety, load_log)

PREFIX = "e490"
WORK = ROOT / "private" / "work" / PREFIX
LEVEL, ENV = "intro_10", rm.STRUCT_ENV
GAME, RUNS = g3a.GAME, g3a.RUNS
LDIR = GAME / "GAMEDATAbin" / LEVEL
LVL, PTR, TRANSIT = LDIR / f"{LEVEL}.lvl", LDIR / f"{LEVEL}.ptr", LDIR / "transit.lvl"
SIZE, PSIZE, TSIZE = 7661836, 209068, 41508
LVL_SHA = "a37638bf1370357db21f33df5c4d37ae806b3c4b9f81b331503ba62d1b19e2ee"
PTR_SHA = "6c9dd70c488a1cac95efc0a55a6086255dae2d851bacd93f5abefdcc8200e940"
TRANSIT_SHA = "d300ba3a4a3c03cec6a73eb9da8a8d820fcc3a669591e976b357e804315bf275"
GM10 = "Gen_Sound\\NIK_mGenManager\\NIK_mGenManager.rul^CreateIntelligence^CreateComport:NIK_C_mGenManager_Init"
GM_SO = 0x53C3F0
V0_WORDS = (0xED0, 0x10DC)                  # the manager's initial / current v0 words (block offsets)
CUR_BUF = 0x10DC
GM_GRAPH = 0x53D2E0
# Label correction (after o1, before any other run): personal names show 0x53A09C = MAN_mGenSound_AmbGeneral_Forest
# and 0x53B9B0 = MAN_YmGenSound_SmallRiver; the protocol text first had the two names swapped. Every criterion is
# keyed by SuperObject, so o1's verdict is unchanged: its RS plan (mod e490.redirect-smallriver) served 0x53A09C
# (Forest) and its RF plan (e490.redirect-forest) 0x53B9B0 (SmallRiver). The case keys below keep o1's labels.
SOUNDS = {"frog": 0x53BED0, "forest": 0x53A09C, "smallriver": 0x53B9B0}
SECONDS = 130
sha = lambda b: hashlib.sha256(b).hexdigest()   # noqa: E731


def u32(b, o):
    return struct.unpack_from(">I", b, o)[0]


def files():
    data, ptr, tl = LVL.read_bytes(), PTR.read_bytes(), TRANSIT.read_bytes()
    if (len(data), sha(data), len(ptr), sha(ptr), len(tl), sha(tl)) != (SIZE, LVL_SHA, PSIZE, PTR_SHA, TSIZE,
                                                                         TRANSIT_SHA):
        raise SystemExit("intro_10 files are not the verified versions")
    return data, ptr, tl


def gm_waypoints(data):
    ix = rm.read_script_index(GAME, LEVEL)
    e = ix["graphs"][(GM10, 0, 2)]
    if e["graph"] != GM_GRAPH:
        raise SystemExit("the manager's graph is not the verified one")
    return [struct.unpack_from(">3f", data, w) for _, w in e["nodes"]]


def home(data, so):
    return struct.unpack_from(">3f", data, so + 0xC4 + 0x34)


# --- census (offline): every type-18 designer variable naming another actor's SuperObject ---------------------------

def census():
    out = {}
    for level in ("intro_10", "intro_15", "intro_17", "intro_20"):
        ix = rm.read_script_index(GAME, level)
        lvl, slots = ix["data"], ix["slots"]
        T = lambda o: u32(lvl, o) + 4 if slots.get(o) == 1 else None   # noqa: E731
        so_of = {i["so"]: (k.rsplit(":", 1)[-1], n) for k, v in ix["placements"].items() for n, i in enumerate(v or [])}
        rows = []
        for key, e in ix["defaults"].items():
            for n, inst in enumerate((e or {}).get("instances", ())):
                if not isinstance(inst.get("initial"), int):
                    continue
                for var, (off, t) in enumerate(e["vars"]):
                    w = inst["initial"] + off
                    if t == 18 and w in slots and T(w) in so_of:
                        rows.append({"source": [key.rsplit(":", 1)[-1], n], "variable": var,
                                     "target": list(so_of[T(w)]),
                                     "current_equal": T(inst["current"] + off) == T(w)})
        out[level] = {"size": len(lvl), "sha256": sha(lvl), "actor_references": rows}
    WORK.mkdir(parents=True, exist_ok=True)
    (WORK / "census.json").write_text(json.dumps(out, indent=1) + "\n")
    print({k: len(v["actor_references"]) for k, v in out.items()})
    return 0


# --- oracle plans ---------------------------------------------------------------------------------------------------

def oracle_plan(work: Path, target: str):
    data, _, _ = files()
    so = SOUNDS[target]
    mid = f"e490.redirect-{target}"
    lines = ["R3HD_MOD_PLAN 1", f"# E-490 oracle plan (g6p4_pilot.py): manager v0 -> {target} {so:#x}",
             f"mod {mid} 1.0.0", f"gameplay {mid}", f"file {SIZE} {LVL}"]
    for k, off in enumerate(V0_WORDS):
        o = GM_SO + off
        if u32(data, o) != SOUNDS["frog"] - 4:
            raise SystemExit("the manager's v0 word is not the expected original")
        blob = work / f"range_{k}.bin"
        new = struct.pack(">I", so - 4)
        blob.write_bytes(new)
        lines.append(f"range 0 {o} 4 {g3a.fnv(data[o:o + 4]):016x} {g3a.fnv(new):016x} {mid} {blob}")
    lines += ["end 1 2", ""]
    plan = work / "plan.txt"
    plan.write_bytes("\n".join(lines).encode("utf-8"))   # LF bytes, as write_plan_files writes them
    return plan


# --- the hidden runner (read-only) ----------------------------------------------------------------------------------

def run_case(tag, case, plan=None, env_level=None, extra=None, session_paths=None, steps=None, seconds=SECONDS,
             end_read_at=None, manager_label="gm"):
    """One hidden intro_10 run. Tracked: the manager (and `extra` added actors: {label: file SO}) and the three
    GenSound actors. Per sample: the GenSound (and extra GenSound-like) positions, and for each manager its live v0
    words and v4 waypoint position."""
    from m5_live import Actor, Process
    work = WORK / tag / case
    run = f"{PREFIX}_{tag}_{case}"
    if work.exists() or (RUNS / run).exists():
        raise SystemExit(f"exists: {work} or {RUNS / run}")
    work.mkdir(parents=True)
    env = dict(os.environ)
    for k in ("R3HD_MODS_PLAN", "R3HD_E465_TEST_GROW", "R3HD_G3A_TEST_GROW", ENV):
        env.pop(k, None)
    row = {"case": case, "run": run, "marker_before_start": ["none", None]}
    if plan is not None:
        shutil.copyfile(plan, work / "plan_copy.txt")
        row["plan_sha256"] = sha(Path(plan).read_bytes())
        env["R3HD_MODS_PLAN"] = str(plan)
        if session_paths is not None:
            row["marker_before_start"] = rm.read_structural_marker(session_paths)
    if env_level:
        env[ENV] = env_level
    managers = {manager_label: GM_SO}
    managers.update({k: v for k, v in (extra or {}).items() if k.startswith("gm")})
    tracked = dict(SOUNDS)
    tracked.update({k: v for k, v in (extra or {}).items() if not k.startswith("gm")})
    row["tracked"], row["managers"] = dict(tracked), dict(managers)   # label -> file SuperObject, judged by SO
    (work / "steps.txt").write_text("\n".join(steps or [f"wait {seconds - 8}"]) + "\n", encoding="ascii")
    states, samples, live = [], [], {}
    with (work / "driver.log").open("w") as log:
        game = subprocess.Popen([sys.executable, str(TOOLS / "m9_license_run.py"), run, str(work / "steps.txt"),
                                 "--license-mask", "1", "--seconds", str(seconds), "--play", "--test-level", LEVEL,
                                 "--user-root", run], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
        t0 = time.monotonic()
        base = pid = None
        while time.monotonic() < t0 + 60 and game.poll() is None and (base is None or pid is None):
            lp_, pj = RUNS / run / "runtime.log", RUNS / run / "process.json"
            if base is None and lp_.is_file():
                mm = re.search(r"virtual base 0x0*([0-9A-Fa-f]+),", lp_.read_text(errors="replace"))
                base = mm.group(1) if mm else None
            if pid is None and pj.is_file():
                try:
                    pid = json.loads(pj.read_text(encoding="utf-8-sig"))["pid"]
                except Exception:
                    pid = None
            time.sleep(0.02)
        if base is None or pid is None:
            row["error"] = "process not found"
        else:
            p = Process(pid, int(base, 16))
            last, t_end, area_t, ab, aend, actors, nxt = "none", t0 + seconds - 5, None, None, None, None, 0.0
            mstate = {}

            def read_end(ab_):
                end = {"t": round(time.monotonic() - t0, 3), "actors": {}}
                for label, off in list(managers.items()) + list(tracked.items()):
                    try:
                        end["actors"][label] = st = g6p3.actor_state(p, ab_ + off - 4)
                        if label in managers:
                            st["v2"] = [p.words(st["initial"] + 4, 1)[0], p.words(st["current"] + 4, 1)[0]]
                    except Exception as x:
                        end["actors"][label] = {"error": repr(x)}
                end["lists"] = g6p3.lists(p)
                return end
            while time.monotonic() < t_end and p.running():
                ar = bp.areas(p)
                key = json.dumps({k: (v["base"], v["end"]) for k, v in (ar or {}).items()})
                if ar is not None and key != last:
                    last = key
                    s = bp.snapshot(p)
                    s.update(t=round(time.monotonic() - t0, 3), state="areas_changed", area_keys=sorted(ar))
                    states.append(s)
                    if ar.get(1) and area_t is None:
                        area_t, ab, aend = time.monotonic(), ar[1]["base"], ar[1]["end"]
                    elif area_t is not None and "level_change_t" not in row and \
                            (not ar.get(1) or (ar[1]["base"], ar[1]["end"]) != (ab, aend)):
                        row["level_change_t"] = round(time.monotonic() - t0, 3)
                        actors = {}
                        mstate = {}
                if end_read_at is not None and area_t is not None and "end" not in live and \
                        "level_change_t" not in row and time.monotonic() >= area_t + end_read_at:
                    live["end"] = read_end(ab)
                if area_t is not None and actors is None and time.monotonic() >= area_t + 6:
                    actors, first = {}, {"t": round(time.monotonic() - t0, 3), "ab": ab, "actors": {}}
                    for label, off in list(managers.items()) + list(tracked.items()):
                        try:
                            first["actors"][label] = g6p3.actor_state(p, ab + off - 4)
                            if label in tracked:
                                actors[label] = Actor(p, ab + off - 4)
                            else:
                                st = first["actors"][label]
                                mstate[label] = (st["initial"], st["current"])
                                st["v2"] = [p.words(st["initial"] + 4, 1)[0], p.words(st["current"] + 4, 1)[0]]
                        except Exception as x:
                            first["actors"][label] = {"error": repr(x)}
                    first["lists"] = g6p3.lists(p)
                    live["first"] = first
                now = time.monotonic()
                if actors and now >= nxt:
                    smp = {"t": round(now - t0, 3), "p": {}, "m": {}}
                    for label, a in list(actors.items()):
                        try:
                            smp["p"][label] = list(a.position())
                        except Exception as x:
                            row.setdefault("sampling_stopped", {})[label] = type(x).__name__
                            actors.pop(label)
                    for label, (ini, cur) in mstate.items():
                        try:
                            w0 = [p.words(ini, 1)[0], p.words(cur, 1)[0]]
                            v4 = p.words(cur + 8, 1)[0]
                            wp = p.read(v4, 12) if v4 else None
                            smp["m"][label] = {"v0": w0, "v4": v4,
                                               "v4pos": list(struct.unpack(">3f", wp)) if wp else None}
                        except Exception as x:
                            smp["m"][label] = {"error": type(x).__name__}
                    samples.append(smp)
                    nxt = now + 0.1
                time.sleep(0.005)
            if p.running() and ab is not None:
                if "level_change_t" not in row and "end" not in live:
                    live["end"] = read_end(ab)
                s = bp.snapshot(p)
                s.update(t=round(time.monotonic() - t0, 3), state="final", area_keys=sorted(bp.areas(p) or {}))
                states.append(s)
        game.wait(timeout=seconds + 240)
        row["runner_exit"] = game.returncode
    left, detail = g3a.game_left(pid, run) if pid else (False, {"pid": None})
    row["game_left"], row["game_left_detail"] = left, detail
    controlled = row["runner_exit"] == 0 and not (RUNS / run / "r3hd_crash.txt").exists()
    row["controlled"] = controlled
    if session_paths is not None:
        if row["marker_before_start"][0] == "armed":
            row["session_end"] = rm.end_structural_session(session_paths, run, row["plan_sha256"], controlled)
        row["marker_after"] = rm.read_structural_marker(session_paths)[0]
    for name, obj in (("states", states), ("samples", samples), ("live", live), ("row", row)):
        (work / f"{name}.json").write_text(json.dumps(obj, indent=1, default=str) + "\n")
    return row


def at(pos, pts, tol=0.01):
    return pos is not None and any(math.dist(pos, q) <= tol for q in pts)


def movement(samples, label, manager, wps, homepos, t_from):
    """Per actor: fraction of samples at W, at home; and the v4 witness fraction."""
    s = [x for x in samples if x["t"] >= t_from and label in x["p"]]
    atw = sum(at(x["p"][label], wps) for x in s)
    ath = sum(at(x["p"][label], [homepos]) for x in s)
    wit = tot = 0
    prev = None
    for x in s:
        m = x["m"].get(manager, {})
        if m.get("v4pos"):
            tot += 1
            cand = [m["v4pos"]] + ([prev] if prev else [])
            wit += at(x["p"][label], cand)
            prev = m["v4pos"]
    return {"n": len(s), "at_w": atw, "at_home": ath, "witness": wit, "witness_n": tot,
            "distinct_waypoints": len({tuple(round(c, 2) for c in x["p"][label]) for x in s
                                       if at(x["p"][label], wps)})}


ORACLE_CASES = {"A": "frog", "RS": "forest", "RF": "smallriver"}   # o1's served SuperObjects (label correction)
# o1's samples are keyed by the labels its runner used (the swapped names): label -> SuperObject at run time
O1_LABELS = {"frog": 0x53BED0, "smallriver": 0x53A09C, "forest": 0x53B9B0}


def labels_of(row):
    """label -> SuperObject the run's runner used (recorded since the label correction; o1 by its known labels)."""
    return {k: int(v) for k, v in row["tracked"].items()} if "tracked" in row else dict(O1_LABELS)


def oracle(tag):
    st = subprocess.run([sys.executable, str(HERE / "g5p1_dev_gate.py"), "status"], capture_output=True, text=True)
    if st.stdout.strip() != "production":
        raise SystemExit("the oracle runs on the production build (gate status must be production)")
    for case, target in ORACLE_CASES.items():
        plan = None
        if case != "A":
            pd = WORK / tag / f"plan_{case}"
            pd.mkdir(parents=True, exist_ok=True)
            plan = oracle_plan(pd, target)
        print(case, json.dumps(run_case(tag, case, plan=plan), default=str)[:400], flush=True)
    return 0


def oracle_judge(tag):
    data, _, _ = files()
    wps = gm_waypoints(data)
    homes = {k: home(data, so) for k, so in SOUNDS.items()}
    out, det, Q, invalid = {}, {}, {}, []
    for case in ORACLE_CASES:
        w = WORK / tag / case
        r = json.loads((w / "row.json").read_text())
        for k in ("samples", "live"):
            r[k] = json.loads((w / f"{k}.json").read_text())
        r["log"] = g6p3.load_log(r["run"])
        r["safe"], r["safety"] = g6p3.safety(r)
        out[case] = r
        lf = r["live"].get("first")
        if r.get("error") or not lf or any("error" in a for a in lf["actors"].values()):
            invalid.append(f"{case}:read")
        if not r["samples"] or r["samples"][-1]["t"] - r["samples"][0]["t"] < 60:
            invalid.append(f"{case}:samples")
    if invalid:
        res = {"invalid": invalid, "verdict": "INVALID"}
        (WORK / f"oracle_{tag}.json").write_text(json.dumps(res, indent=1) + "\n")
        print(json.dumps(res))
        return 1
    for case, tname in ORACLE_CASES.items():
        r = out[case]
        lab = labels_of(r)                                  # sample label -> SuperObject
        by_so = {v: k for k, v in lab.items()}
        homes = {k: home(data, so) for k, so in lab.items()}
        target = by_so[SOUNDS[tname]]                       # the label under which the target was sampled
        ab = r["live"]["first"]["ab"]
        t_from = r["samples"][0]["t"] + 10
        log = r["log"]
        if case == "A":
            Q[f"{case}_Q1"] = "M33 mods=off" in log and "M33 mods served" not in log
        else:
            served = sorted(set(re.findall(r"M33 mods served mod=\S+ file=(\S+)", log)))
            Q[f"{case}_Q1"] = ("M33 mods state=active" in log and served == [f"{LEVEL}.lvl"] and "M36 grow" not in log
                               and not re.search(r"G5P1|G5P3|G6P1", log))
        want = ab + SOUNDS[tname] - 4
        Q[f"{case}_Q2"] = all(x["m"].get("gm", {}).get("v0") == [want, want] for x in r["samples"])
        mv = {k: movement(r["samples"], k, "gm", wps, homes[k], t_from) for k in lab}
        det[case] = {f"{k} {lab[k]:#x}": v for k, v in mv.items()}
        tm = mv[target]
        Q[f"{case}_Q3"] = tm["n"] > 0 and tm["at_w"] >= 0.9 * tm["n"]
        others = [k for k in lab if k != target]
        allsamp = {k: movement(r["samples"], k, "gm", wps, homes[k], 0) for k in others}
        Q[f"{case}_Q4"] = all(v["at_home"] == v["n"] and v["at_w"] == 0 for v in allsamp.values())
        Q[f"{case}_Q5"] = tm["witness_n"] > 0 and tm["witness"] >= 0.9 * tm["witness_n"]
        Q[f"{case}_Q6"] = r["safe"]
        det[f"{case}_others_all"] = allsamp
    if not Q["A_Q3"]:
        invalid.append("A:no_movement")
    verdict = "INVALID" if invalid else ("ORACLE VERIFIED" if all(Q.values()) else "NOT PASSED")
    res = {"invalid": invalid, "Q": Q, "verdict": verdict, "details": det,
           "safety": {c: r["safety"] for c, r in out.items()}}
    (WORK / f"oracle_{tag}.json").write_text(json.dumps(res, indent=1, default=str) + "\n")
    print(json.dumps({k: res[k] for k in ("invalid", "Q", "verdict")}, indent=1))
    return 0 if verdict == "ORACLE VERIFIED" else 1


# --- compiler helpers -----------------------------------------------------------------------------------------------

import g5p1_pilot as p1  # noqa: E402

TARGET_SO = {0: SOUNDS["forest"], 1: SOUNDS["smallriver"]}
MOD = {0: "g6p4.manager-forest", 1: "g6p4.manager-smallriver"}
COPY = 0x74E910                              # the copy's SuperObject (file offset) in both variants
N_LVL, N_PTR = 1796, 528
NEW_NAME = b"MAN_mGenManager_Frog_G6P4"
REGIONS = ((0x338, 0xD6C), (0xEF0, 0x10DC))
KEPT = (0x324, 0xD6C, 0xD74, 0xD78, 0xD80, 0xEC4, 0xED4, 0x10E0)


def manager(sel=0, **kw):
    o = {"type": "insert-gensound-manager", "level": LEVEL, "model": GM10, "instance": 0, "lvl_sha256": LVL_SHA,
         "ptr_sha256": PTR_SHA, "transit_sha256": TRANSIT_SHA, "moves_gensound_instance": sel}
    o.update(kw)
    return o


def compiled(sel=0, **kw):
    with p1.dev_env(LEVEL):
        return rm.compile_insert_gensound_manager(manager(sel, **kw), {"game": GAME})


def refused(fn, code, env=LEVEL):
    with p1.dev_env(env):
        return p1.refused(fn, code)


def compile_plan(name, mods, session=None, env=LEVEL):
    p1.WORK = WORK
    paths = p1.fresh(name)
    with p1.dev_env(env):
        for mid, ov in mods:
            p1.install(paths, mid, ov)
        res = rm.resolve_all(paths, write_plan=paths["cache"], session=session)
    plan = paths["cache"] / rm.PLAN_NAME
    return res, (plan.read_text(encoding="utf-8") if plan.is_file() else None), paths


# --- the independent constructor (O3; shares no code with the compiler) ---------------------------------------------

def construct(data, ptr, tl, sel):
    """The G6-P4 copy built directly from the census facts: the manager's three instance segments packed (each in its
    source 16-byte phase), shared-region pointers kept, v0 retargeted, in-segment pointers remapped; personal type,
    SO record, three backups (list order), always element; the same conventions as G4c's constructor."""
    n, m = u32(ptr, 0), u32(data, 0)
    sl = {}
    for i in range(n):
        f, loc = struct.unpack_from(">iI", ptr, 4 + 8 * i)
        sl[loc + 4] = f
    t = lambda o: u32(data, o) + 4   # noqa: E731
    S, B = GM_SO, 0x11E4
    segs, pos, a = [], 0, 0
    for x, y in REGIONS + ((B, B),):
        pos += (a % 16 - pos % 16) % 16
        segs.append((a, x, pos))
        pos += x - a
        a = y
    CS = pos

    def mp(k):
        return next(k - a_ + d for a_, b_, d in segs if a_ <= k < b_)
    size = len(data)
    C = size + (S % 16 - size % 16) % 16
    name = NEW_NAME + b"\0" * (4 - len(NEW_NAME) % 4)
    PE = C + CS + (-CS) % 4
    NM = PE + 0x14
    RC = NM + len(name)
    BK = RC + 0x48
    BC = BK + 3 * 0x18
    AE = BC + 0x54
    end = AE + 0x14
    end += (-end) % 16
    out = bytearray(data) + bytes(end - size)
    w = lambda o, v: struct.pack_into(">I", out, o, v)   # noqa: E731
    for a_, b_, d in segs:
        out[C + d:C + d + b_ - a_] = data[S + a_:S + b_]
    new = []
    for a_, b_, d in segs:
        for o in sorted(k for k in sl if S + a_ <= k < S + b_):
            co = C + mp(o - S)
            if o in (S + 0xED0, S + 0x10DC):
                w(co, TARGET_SO[sel] - 4)
            elif o - S in KEPT:
                pass
            elif sl[o] == 1 and S <= t(o) < S + B:
                w(co, C + mp(t(o) - S) - 4)
            new.append((sl[o], co))
    nxt = t(S + 0x14)
    w(C + 0x14, nxt - 4)
    w(C + 0x18, S - 4)
    std = t(t(S + 4) + 4)
    pcount = u32(data, 0x1C74 + 8)
    w(C + mp(std - S) + 8, pcount)
    el = t(0x1C74)
    for _ in range(u32(data, std + 8)):
        el = t(el)
    plast = t(0x1C74 + 4)
    out[PE:PE + 0x14] = data[el:el + 0x14]
    w(PE, 0)
    w(PE + 4, plast - 4)
    w(PE + 0xC, NM - 4)
    out[NM:NM + len(name)] = name
    new += [(1, PE + 4), (1, PE + 8), (1, PE + 0xC), (1, plast)]
    prv = t(S + 0x18)
    recs = [o - 4 for o in sl if sl[o] == 1 and t(o) == S and not S <= o < S + B and o not in (nxt + 0x18, prv + 0x14)]
    srec = [r for r in recs if u32(data, r) == 0 or sl.get(r) == 1]
    rh = 0x5A7434
    rl, r = [], t(rh)
    while r is not None and len(rl) < 70000:
        rl.append(r)
        r = t(r) if sl.get(r) == 1 else None
    srec = [x for x in srec if x in rl]
    assert len(srec) == 1, "the manager's SO record"
    rlast = t(rh + 4)
    out[RC:RC + 0x48] = data[srec[0]:srec[0] + 0x48]
    w(RC, 0)
    w(RC + 4, C - 4)
    new += [(1, RC + 4), (1, rlast)]
    links, b = [], t(0x1CEC)
    while b is not None and len(links) < 70000:
        links.append(b)
        b = t(b) if sl.get(b) == 1 else None
    mine = [(l_ - 4, t(l_ + 4)) for l_ in links if sl.get(l_ + 4) == 1 and S <= t(l_ + 4) < S + B]
    blink = prev = t(0x1CEC + 4)
    for i, (sb, tg) in enumerate(mine):
        rr = BK + 0x18 * i
        out[rr:rr + 0x18] = data[sb:sb + 0x18]
        w(rr + 4, 0)
        if i:
            w(prev, rr)
        w(rr + 8, C + mp(tg - S) - 4)
        new.append((1, rr + 8))
        if tg == S + 0xC4:
            out[BC:BC + 0x54] = data[t(sb + 0xC):t(sb + 0xC) + 0x54]
            w(rr + 0xC, BC - 4)
            new.append((1, rr + 0xC))
        new.append((1, prev))
        prev = rr + 4
    alast = t(0x1CA8 + 4)
    ael = [e for e in range(0x53A000, 0x53A090, 4) if sl.get(e + 0xC) == 1 and t(e + 0xC) == S]
    assert len(ael) == 1, "the manager's always-active element"
    w(AE, 0)
    w(AE + 4, alast - 4)
    w(AE + 8, 0x53A090 - 4)
    w(AE + 0xC, C - 4)
    out[AE + 0x10:AE + 0x14] = data[ael[0] + 0x10:ael[0] + 0x14]
    new += [(1, AE + 4), (1, AE + 8), (1, AE + 0xC), (1, alast)]
    acount = u32(data, 0x1CA8 + 8)
    for o, v in ((S + 0x14, C - 4), (nxt + 0x18, C - 4), (0x1C74 + 4, PE - 4), (0x1C74 + 8, pcount + 1),
                 (plast, PE - 4), (rh + 4, RC - 4), (rh + 8, u32(data, rh + 8) + 1), (rlast, RC - 4),
                 (0x1CEC + 4, prev - 4), (blink, BK), (alast, AE - 4), (0x1CA8 + 4, AE - 4), (0x1CA8 + 8, acount + 1),
                 (0x53A090 + 4, AE - 4), (0x53A090 + 8, acount + 1)):
        w(o, v)
    nptr = struct.pack(">I", n + len(new)) + ptr[4:4 + 8 * n] + b"".join(struct.pack(">iI", f, o - 4) for f, o in
                                                                         new) + ptr[4 + 8 * n:]
    ntl = bytearray(tl)
    struct.pack_into(">I", ntl, 0x9B4 + 0x10, u32(tl, 0x9B4 + 0x10) + 1)
    return bytes(out), nptr, bytes(ntl), {"copy": C, "personal": PE, "name": NM, "record": RC, "backup": BK,
                                          "backup_copy": BC, "always": AE, "slots": len(new), "copy_size": CS,
                                          "map": mp}


# --- the independent loader simulator (O4 / O5) ---------------------------------------------------------------------

def simulate(lvl, ptr, tl, mp, base=0x40F5509C):
    n, m = u32(ptr, 0), u32(lvl, 0)
    sl = {}
    for i in range(n):
        f, loc = struct.unpack_from(">iI", ptr, 4 + 8 * i)
        if loc + 4 in sl:
            return {"error": f"duplicate slot {loc + 4:#x}"}
        sl[loc + 4] = f
    cross = [struct.unpack_from(">IiIi", ptr, 4 + 8 * n + 16 * j) for j in range(m)]
    A = lambda off: base + off - 4   # noqa: E731
    F = lambda addr: addr - base + 4   # noqa: E731

    def rd(addr):
        o = F(addr)
        return base + u32(lvl, o) if sl.get(o) == 1 else None
    first = next(A(ob + 4) for oa, fa, ob, fb in cross if fa != 1 and fb == 1 and oa + 4 == 0x9B4 + 8)
    world, so = [], first
    while so is not None and so not in world and len(world) < 4096:
        world.append(so)
        so = rd(so + 0x14)
    c = A(COPY)
    out = {"world": len(world), "world_count": u32(tl, 0x9B4 + 0x10), "copy_in_world": world.count(c),
           "copy_after_source": c in world and world.index(c) == world.index(A(GM_SO)) + 1,
           "prev_ok": all(rd(b + 0x18) == a for a, b in zip(world, world[1:]))}
    perso = rd(c + 4)
    brain = rd(perso + 0xC)
    mind = rd(brain)
    dm = rd(mind + 0xC)
    ini, cur = rd(dm + 4), rd(dm + 8)
    rel = lambda x: F(x) - COPY   # noqa: E731
    out["chain"] = {"perso": rel(perso), "3ddata": rel(rd(perso)), "std": rel(rd(perso + 4)), "brain": rel(brain),
                    "mind": rel(mind), "intelligence": rel(rd(mind + 4)), "dsgmem": rel(dm), "initial": rel(ini),
                    "current": rel(cur)}
    out["want_chain"] = {k: mp(v) for k, v in (("perso", 0x80), ("3ddata", 0xAC), ("std", 0x2B4), ("brain", 0x318),
                                               ("mind", 0x324), ("intelligence", 0xD6C), ("dsgmem", 0xEC4),
                                               ("initial", 0xED0), ("current", 0x10DC))}
    out["ai_model"], out["dsg_model"] = F(rd(mind)), F(rd(dm))
    out["intelligence_model"] = F(rd(rd(mind + 4)))
    out["v0"] = [F(rd(ini)), F(rd(cur))]
    out["v2"] = [F(rd(ini + 4)), F(rd(cur + 4))]
    wps, node = [], rd(rd(ini + 4))
    while node is not None and len(wps) < 64:
        wps.append(struct.unpack_from(">3f", lvl, F(rd(node + 0xC))))
        node = rd(node)
    out["graph_waypoints"] = wps
    rh = F(rd(A(0x1CFC)))
    recs, r = [], rd(A(rh))
    while r is not None and len(recs) < 4096:
        own = rd(r + 4)
        recs.append(F(own) if own else None)
        r = rd(r)
    out["records"] = {"n": len(recs), "count": u32(lvl, rh + 8), "copy": recs.count(COPY), "last": recs[-1]}
    pl, e = [], rd(A(0x1C74))
    while e is not None and len(pl) < 4096:
        pl.append(lvl[F(rd(e + 0xC)):F(rd(e + 0xC)) + 64].split(b"\0")[0])
        e = rd(e)
    out["personal"] = {"n": len(pl), "count": u32(lvl, 0x1C74 + 8), "last": pl[-1].decode(),
                       "copy_index": u32(lvl, F(rd(perso + 4)) + 8)}
    bl, b = [], rd(A(0x1CEC))
    while b is not None and len(bl) < 8192:
        tg = rd(b + 4)
        bl.append(F(tg) if tg else None)
        b = rd(b)
    out["backups"] = {"n": len(bl), "copy_targets": [x - COPY for x in bl[-3:]]}
    al, e = [], rd(A(0x1CA8))
    while e is not None and len(al) < 4096:
        own = rd(e + 0xC)   # None: an element of a fix actor (not an own-file pointer)
        al.append(F(own) if own else None)
        e = rd(e)
    out["always"] = {"n": len(al), "count": u32(lvl, 0x1CA8 + 8), "copy": al.count(COPY), "last": al[-1]}
    return out


# --- offline O1-O8 --------------------------------------------------------------------------------------------------

def check():
    WORK.mkdir(parents=True, exist_ok=True)
    p1.WORK = WORK
    data, ptr, tl = files()
    ix = rm.read_script_index(GAME, LEVEL)
    O, det = {}, {}
    # O1 reference semantics (files) / O2 behavioural oracle (guest)
    d = ix["defaults"][GM10]
    inst = d["instances"][0]
    words = [inst["initial"], inst["current"]]
    O["O1_reference_semantics"] = (dict(d["vars"])[0] == 18 and all(ix["slots"].get(w_) == 1 for w_ in words)
                                   and all(u32(data, w_) + 4 == SOUNDS["frog"] for w_ in words)
                                   and [i["so"] for i in ix["placements"][rm.FROG10]] == [SOUNDS["forest"],
                                                                                          SOUNDS["smallriver"],
                                                                                          SOUNDS["frog"]])
    orc = json.loads((WORK / "oracle_o1.json").read_text())
    O["O2_behavioural_oracle"] = orc.get("verdict") == "ORACLE VERIFIED"
    det["O1_O2"] = {"oracle": orc.get("verdict"), "v0_words": [hex(x) for x in words]}
    # O3 compiler equivalence (direct and through the plan)
    eq, sims = {}, {}
    for sel in (0, 1):
        _, tx = compiled(sel)
        im = tx["images"]
        cl, cp, ct, lay = construct(data, ptr, tl, sel)
        res, text, _ = compile_plan(f"o3_{sel}", [(MOD[sel], [manager(sel)])])
        pim = p1.images(p1.parse_plan(text)) if text else {}
        lay_cmp = {k: v for k, v in lay.items() if k not in ("map", "slots", "copy_size")}
        eq[sel] = {"direct": (im["lvl"], im["ptr"], im["transit"]) == (cl, cp, ct),
                   "plan": (pim.get(f"{LEVEL}.lvl"), pim.get(f"{LEVEL}.ptr"), pim.get("transit.lvl")) == (cl, cp, ct),
                   "active": res["active"] == [MOD[sel]], "layout": lay_cmp == tx["info"]["objects"]
                   and lay["slots"] == tx["info"]["slots"] and lay["copy_size"] == tx["info"]["copy_size"],
                   "sha": {k: sha(v) for k, v in im.items()}, "growth": [len(cl) - SIZE, len(cp) - PSIZE]}
        sims[sel] = simulate(cl, cp, ct, lay["map"])
    O["O3_compiler_equivalence"] = all(v["direct"] and v["plan"] and v["active"] and v["layout"]
                                       and v["growth"] == [N_LVL, N_PTR] for v in eq.values())
    det["O3"] = eq
    t = lambda o: u32(data, o) + 4   # noqa: E731
    wps = gm_waypoints(data)
    mp0 = construct(data, ptr, tl, 0)[3]["map"]
    O["O4_ownership_identity"] = all(
        s["world"] == s["world_count"] == 61 and s["copy_in_world"] == 1 and s["copy_after_source"] and s["prev_ok"]
        and s["chain"] == s["want_chain"] and s["ai_model"] == t(GM_SO + 0x324) and s["dsg_model"] == t(GM_SO + 0xEC4)
        and s["intelligence_model"] == t(GM_SO + 0xD6C)
        and s["records"] == {"n": 123, "count": 123, "copy": 1, "last": COPY}
        and s["personal"] == {"n": 70, "count": 70, "last": NEW_NAME.decode(), "copy_index": 69}
        and s["backups"]["copy_targets"] == [mp0(0x113C), mp0(0x113E), mp0(0xC4)]
        and s["always"] == {"n": 18, "count": 18, "copy": 1, "last": COPY} for s in sims.values())
    O["O5_target_relocation"] = all(s["v0"] == [TARGET_SO[sel]] * 2 and s["v2"] == [GM_GRAPH] * 2
                                    and s["graph_waypoints"] == wps for sel, s in sims.items())
    det["O4_O5"] = {sel: {k: v for k, v in s.items() if k != "graph_waypoints"} for sel, s in sims.items()}
    # relocation detail: 66 entries, unique, inside new objects / old list ends; the copy's slots = the block's in
    # its instance segments (the model region's 1 fix word and the graph region left out)
    o5 = {}
    for sel in (0, 1):
        _, tx = compiled(sel)
        L, np_ = tx["info"]["objects"], tx["images"]["ptr"]
        n0, n1 = u32(ptr, 0), u32(np_, 0)
        added = [(f, loc + 4) for f, loc in (struct.unpack_from(">iI", np_, 4 + 8 * i) for i in range(n0, n1))]
        allsl = [struct.unpack_from(">iI", np_, 4 + 8 * i)[1] + 4 for i in range(n1)]
        blk = [k for k in ix["slots"] if GM_SO <= k < GM_SO + 0x11E4]
        inseg = [k for k in blk if not any(GM_SO + a <= k < GM_SO + b for a, b in REGIONS)]
        o5[sel] = {"added": len(added), "unique": len(set(allsl)) == len(allsl),
                   "copy_slots": sum(1 for _, o in added if L["copy"] <= o < L["copy"] + tx["info"]["copy_size"]),
                   "instance_slots": len(inseg), "fix_slots_in_copy": sum(1 for f, _ in added if f == 0)}
    O["O5_target_relocation"] = O["O5_target_relocation"] and all(
        v["added"] == 66 and v["unique"] and v["copy_slots"] == v["instance_slots"] and v["fix_slots_in_copy"] == 0
        for v in o5.values())
    det["O5_slots"] = o5
    # O6 transaction / memory
    o6 = {}
    for sel in (0, 1):
        _, tx = compiled(sel)
        res, text, _ = compile_plan(f"o6_{sel}", [(MOD[sel], [manager(sel)])])
        m = p1.parse_plan(text)
        members = []
        for f in m["files"]:
            for tline in f["tx"]:
                role, orig, guest, result = tline.split(" ")
                members.append((role, Path(f["path"]).name, f["size"], orig, int(guest), result))
        want = sorted([("lvl", f"{LEVEL}.lvl", SIZE, LVL_SHA, SIZE + N_LVL, sha(tx["images"]["lvl"])),
                       ("ptr", f"{LEVEL}.ptr", PSIZE, PTR_SHA, PSIZE + N_PTR, sha(tx["images"]["ptr"])),
                       ("transit", "transit.lvl", TSIZE, TRANSIT_SHA, TSIZE, sha(tx["images"]["transit"]))])
        txl = m["txs"][0].split(" ") if len(m["txs"]) == 1 else []
        o6[sel] = {"tx": m["txs"], "members_ok": sorted(members) == want,
                   "id_ok": txl[1:4] == ["2", LEVEL, MOD[sel]] and txl[4] == rm.tx_id(LEVEL, MOD[sel], want, 2),
                   "gameplay": m["gameplay"] == [f"gameplay {MOD[sel]}"], "memory": tx["info"]["memory"]}
    O["O6_atomicity_memory"] = all(v["members_ok"] and v["id_ok"] and v["gameplay"] and v["memory"]["headroom"] > 0
                                   for v in o6.values())
    det["O6"] = o6
    # O7 negatives
    bad = lambda **kw: (lambda: compiled(0, **kw))   # noqa: E731
    neg = {
        "gate off (parse)": refused(lambda: rm.parse_insert_gensound_manager(manager(0), "o"), "UNSUPPORTED", None),
        "gate off (compile)": refused(lambda: rm.compile_insert_gensound_manager(manager(0), {"game": GAME}),
                                      "UNSUPPORTED", None),
        "gate names intro_20": refused(lambda: rm.compile_insert_gensound_manager(manager(0), {"game": GAME}),
                                       "UNSUPPORTED", "intro_20"),
        "wrong level": refused(lambda: rm.parse_insert_gensound_manager(manager(0, level="intro_20"), "o"),
                               "UNSUPPORTED"),
        "wrong model": refused(bad(model=rm.FROG10), "UNSUPPORTED"),
        "other instance": refused(bad(instance=1), "UNSUPPORTED"),
        "unsupported target (2 = the Frog)": refused(lambda: rm.parse_insert_gensound_manager(
            manager(0, moves_gensound_instance=2), "o"), "UNSUPPORTED"),
        "broken reference (raw address)": refused(lambda: rm.parse_insert_gensound_manager(
            manager(0, moves_gensound_instance="0x53a09c"), "o"), "UNSUPPORTED"),
        "broken reference (bool)": refused(lambda: rm.parse_insert_gensound_manager(
            manager(0, moves_gensound_instance=True), "o"), "UNSUPPORTED"),
        "raw pointer key": refused(lambda: rm.parse_insert_gensound_manager(dict(manager(0), actor=0x53A09C), "o"),
                                   "BAD_MANIFEST"),
        "missing key": refused(lambda: rm.parse_insert_gensound_manager(
            {k: v for k, v in manager(0).items() if k != "transit_sha256"}, "o"), "BAD_MANIFEST"),
        "source-hash mismatch (lvl)": refused(bad(lvl_sha256="0" * 64), "TARGET_CHANGED"),
        "source-hash mismatch (ptr)": refused(bad(ptr_sha256="1" * 64), "TARGET_CHANGED"),
    }
    spec = rm.GMGR_ALLOW[LEVEL]
    peers = [i["so"] for i in ix["placements"][rm.FROG10]]
    foreign = [(e2[k], dd["length"]) for key, dd in ix["defaults"].items() if dd
               for e2 in dd["instances"] for k in ("initial", "current") if isinstance(e2.get(k), int)]

    def build(lvl_=data, ptr_=ptr, tl_=tl, sel=0, spec_=spec, foreign_=foreign):
        return rm.build_gensound_manager(lvl_, ptr_, tl_, 1, spec_, peers, sel, foreign_, "neg")
    dup = bytearray(ptr)
    struct.pack_into(">iI", dup, 4 + 8 * 1, *struct.unpack_from(">iI", ptr, 4))
    pc = bytearray(data)
    struct.pack_into(">I", pc, 0x1C74 + 8, u32(data, 0x1C74 + 8) + 1)
    managed = foreign + [(GM_SO + 0xED0 - 0x10000, 4)]   # an existing designer buffer naming the target (synthetic)
    fake = bytearray(data)
    fake_ptr = bytearray(ptr)   # make a free relocated word name Forest: the target would already be managed
    neg.update({
        "duplicate relocation slot": p1.refused(lambda: build(ptr_=bytes(dup)), "STRUCTURE_CHECK"),
        "duplicate actor index (personal count)": p1.refused(lambda: build(lvl_=bytes(pc)), "STRUCTURE_CHECK"),
        "missing resource (transit too short)": p1.refused(lambda: build(tl_=tl[:0x9B4]), "STRUCTURE_CHECK"),
        "target already managed (a designer buffer names it)": p1.refused(lambda: build(
            foreign_=foreign + [(GM_SO + 0xED0, 4)], spec_=dict(spec, targets={0: SOUNDS["frog"]})),
            "STRUCTURE_CHECK"),
        "target = the source's own target": p1.refused(lambda: build(spec_=dict(spec, targets={0: SOUNDS["frog"]})),
                                                       "STRUCTURE_CHECK"),
        "target not an actor": p1.refused(lambda: build(spec_=dict(spec, targets={0: GM_GRAPH})), "STRUCTURE_CHECK"),
        "insufficient memory budget": p1.refused(lambda: rm.structural_budget(
            LEVEL, SIZE, SIZE + 16 * 1024 * 1024, PSIZE + N_PTR, u32(data, 0), "o"), "BUDGET"),
    })
    del managed, fake, fake_ptr
    try:
        nl, np_, nt, edits, info = build()
        s = rm._gmgr_source(data, ptr, tl, 1, spec, peers, 0, foreign, "neg")
        L = info["objects"]
        sl_new = [(f, loc + 4) for f, loc in (struct.unpack_from(">iI", np_, 4 + 8 * i)
                                              for i in range(u32(ptr, 0), u32(np_, 0)))]
        bad1 = bytearray(nl)   # v0 rebased into the source (the Frog) instead of the chosen target
        struct.pack_into(">I", bad1, info["reference_words"][0], SOUNDS["frog"] - 4)
        neg["damaged output (reference names the Frog)"] = p1.refused(
            lambda: rm.verify_gensound_manager(data, ptr, tl, bytes(bad1), np_, nt, 1, spec, s, L, sl_new, edits, "o"),
            "STRUCTURE_CHECK")
        bad2 = bytearray(nl)   # a kept model pointer rebased into the copy
        mpk = construct(data, ptr, tl, 0)[3]["map"]
        struct.pack_into(">I", bad2, COPY + mpk(0x324), COPY + mpk(0x324) - 4)
        neg["damaged output (shared model pointer rebased)"] = p1.refused(
            lambda: rm.verify_gensound_manager(data, ptr, tl, bytes(bad2), np_, nt, 1, spec, s, L, sl_new, edits, "o"),
            "STRUCTURE_CHECK")
    except Exception as x:
        neg["damaged output"] = repr(x)
    with p1.dev_env(LEVEL):
        mk = lambda ov: {"mod.json": json.dumps(p1.manifest("x.gm", ov)).encode()}   # noqa: E731
        neg["two managers in one mod"] = p1.refused(lambda: rm.parse_manifest(mk([manager(0), manager(1)])),
                                                    "BAD_MANIFEST")
        neg["manager + Frog"] = p1.refused(lambda: rm.parse_manifest(mk([manager(0), dict(
            type="insert-scripted-frog", level=LEVEL, model=rm.FROG10, instance=2, lvl_sha256=LVL_SHA,
            ptr_sha256=PTR_SHA, transit_sha256=TRANSIT_SHA, placement="at_source", period_ms=500)])), "BAD_MANIFEST")
    nr, ntext = compile_plan("o7_two_mods", [("x.gm-0", [manager(0)]), ("x.gm-1", [manager(1)])])[:2]
    neg["two structural mods on intro_10"] = (sorted(nr["active"]) == [] and ntext is None) or nr["mods"]
    O["O7_negatives"] = all(v is True for v in neg.values())
    det["O7"] = neg
    # O8 compatibility
    st = subprocess.run([sys.executable, str(TOOLS / "r3hd_mods.py"), "selftest"], capture_output=True, text=True)
    comp = {"selftest": st.stdout.strip().splitlines()[-1] if st.stdout else st.stderr[-200:]}
    for name in ("g5p4a_pilot", "g6p1_pilot", "g6p2_pilot", "g6p3_pilot"):
        cw = WORK / "compat" / name
        cw.mkdir(parents=True, exist_ok=True)
        q = subprocess.run([sys.executable, "-c", (
            "import sys, pathlib, shutil; sys.path.insert(0, r'%s'); sys.path.insert(0, r'%s'); import %s as m; "
            "import g5p1_pilot as p1; src = m.WORK; m.WORK = pathlib.Path(r'%s'); p1.WORK = m.WORK; "
            "[shutil.copyfile(src / f, m.WORK / f) for f in ('oracle_o2.json',) if (src / f).is_file()]; "
            "sys.exit(m.check())") % (TOOLS, HERE, name, cw)], cwd=ROOT, capture_output=True, text=True)
        (cw / "check.log").write_text(q.stdout + q.stderr)
        comp[name] = q.returncode
    O["O8_compatibility"] = (comp["selftest"].startswith("R3HD_MODS_SELFTEST PASS")
                             and all(comp[n] == 0 for n in ("g5p4a_pilot", "g6p1_pilot", "g6p2_pilot", "g6p3_pilot")))
    det["O8"] = comp
    ok = all(O.values())
    (WORK / "offline.json").write_text(json.dumps({"pass": ok, "O": O, "details": det}, indent=1, default=str) + "\n")
    print(json.dumps(O, indent=1))
    print("OFFLINE_G6P4", "PASS" if ok else "FAIL")
    return 0 if ok else 1


# --- deterministic transaction tests (g5p1_tx_test.cpp; development and production headers; no game) ---------------

def negtest():
    WORK.mkdir(parents=True, exist_ok=True)
    nd = WORK / "negtest"
    if nd.exists():
        shutil.rmtree(nd)
    nd.mkdir(parents=True)
    p1.WORK = WORK
    data, ptr, tl = files()
    exes = {k: p1.build_test(k) for k in ("dev", "prod")}
    texts = {sel: compile_plan(f"neg_{sel}", [(MOD[sel], [manager(sel)])])[1] for sel in (0, 1)}
    base = p1.parse_plan(texts[0])
    V = {}
    for sel in (0, 1):
        cl, cp, ct, _ = construct(data, ptr, tl, sel)
        for k, b in (("lvl", cl), ("ptr", cp), ("transit", ct)):
            V[(sel, k)] = nd / f"img_{sel}_{k}.bin"
            V[(sel, k)].write_bytes(b)
    idx = {Path(f["path"]).name: i for i, f in enumerate(base["files"])}
    li, pi, ti = idx[f"{LEVEL}.lvl"], idx[f"{LEVEL}.ptr"], idx["transit.lvl"]

    def variant(name, fn=None, src=base):
        m = json.loads(json.dumps(src))
        if fn:
            fn(m)
        p = nd / f"plan_{name}.txt"
        p.write_text(p1.emit(m), encoding="utf-8")
        return p

    def tamper(m, i, ri):
        off, length, gb, nb, mid, blob = m["files"][i]["range"][ri].split(" ", 5)
        b = bytearray(Path(blob).read_bytes())
        b[len(b) // 2] ^= 0x33
        q = nd / f"tampered_{i}_{ri}.bin"
        q.write_bytes(bytes(b))
        m["files"][i]["range"][ri] = " ".join([off, length, gb, f"{g3a.fnv(bytes(b)):016x}", mid, str(q)])

    def retarget(m):
        """The actor reference swapped after compilation (v0 -> the other GenSound actor in the appended tail)."""
        _, tx = compiled(0)
        for k, r in enumerate(m["files"][li]["range"]):
            off, length, gb, nb, mid, blob = r.split(" ", 5)
            if int(off) == SIZE:
                b = bytearray(Path(blob).read_bytes())
                for w_ in tx["info"]["reference_words"]:
                    struct.pack_into(">I", b, w_ - SIZE, TARGET_SO[1] - 4)
                q = nd / "retargeted_tail.bin"
                q.write_bytes(bytes(b))
                m["files"][li]["range"][k] = " ".join([off, length, gb, f"{g3a.fnv(bytes(b)):016x}", mid, str(q)])
    plans = {
        "valid": variant("valid"),
        "valid_1": variant("valid_1", src=p1.parse_plan(texts[1])),
        "missing_transit": variant("missing_transit", lambda m: m["files"].pop(ti)),
        "missing_lvl": variant("missing_lvl", lambda m: m["files"].pop(li)),
        "tampered_ptr": variant("tampered_ptr", lambda m: tamper(m, pi, 0)),
        "retargeted": variant("retargeted", retarget),
        "partial_always": variant("partial_always", lambda m: m["files"][li].update(
            range=[r for r in m["files"][li]["range"] if int(r.split(" ")[0]) != 0x1CA8 + 8])),
        "corrupt_id": variant("corrupt_id", lambda m: m.update(
            txs=[m["txs"][0][:-1] + ("0" if m["txs"][0][-1] != "0" else "1")])),
        "version_1": variant("version_1", lambda m: m.update(txs=[m["txs"][0].replace("level-tx 2 ", "level-tx 1 ")])),
    }
    O = ("-", "-", "-")
    Va = (V[(0, "lvl")], V[(0, "ptr")], V[(0, "transit")])
    Vb = (V[(1, "lvl")], V[(1, "ptr")], V[(1, "transit")])
    cp = nd / "copies"
    cp.mkdir()
    cps = {k: cp / src.name for k, src in (("lvl", LVL), ("ptr", PTR), ("transit", TRANSIT))}
    mc = json.loads(json.dumps(base))
    for f in mc["files"]:
        f["path"] = str(cps[{f"{LEVEL}.lvl": "lvl", f"{LEVEL}.ptr": "ptr", "transit.lvl": "transit"}[Path(f["path"]).name]])
    plans["copies"] = nd / "plan_copies.txt"
    plans["copies"].write_text(p1.emit(mc), encoding="utf-8")
    paths = (str(LVL), str(PTR), str(TRANSIT))
    cpaths = (str(cps["lvl"]), str(cps["ptr"]), str(cps["transit"]))
    dev = [("manager 0 valid, lvl,ptr,transit", "valid", LEVEL, "active", "lvl,ptr,transit", Va, paths),
           ("manager 0 valid, transit,ptr,lvl", "valid", LEVEL, "active", "transit,ptr,lvl", Va, paths),
           ("manager 0 valid, repeated opens", "valid", LEVEL, "active", "ptr,transit,lvl,transit,ptr", Va, paths),
           ("manager 1 valid, transit,lvl,ptr", "valid_1", LEVEL, "active", "transit,lvl,ptr", Vb, paths),
           ("manager not enabled", "valid", "-", "level_tx_not_enabled", "lvl,ptr,transit", O, paths),
           ("manager enabled for another level", "valid", "intro_20", "tx_level", "transit,lvl,ptr", O, paths),
           ("manager missing transit member", "missing_transit", LEVEL, "tx_incomplete", "transit,lvl,ptr", O, paths),
           ("manager missing lvl member", "missing_lvl", LEVEL, "tx_incomplete", "ptr,transit,lvl", O, paths),
           ("manager tampered ptr, rehashed", "tampered_ptr", LEVEL, "tx_result_hash", "lvl,ptr,transit", O, paths),
           ("manager reference swapped after compilation", "retargeted", LEVEL, "tx_result_hash", "lvl,ptr,transit",
            O, paths),
           ("manager partial: always-count edit dropped", "partial_always", LEVEL, "tx_result_hash",
            "transit,ptr,lvl", O, paths),
           ("manager corrupted id", "corrupt_id", LEVEL, "tx_id", "transit,lvl,ptr", O, paths),
           ("manager relabelled version 1", "version_1", LEVEL, "tx_role", "lvl,ptr,transit", O, paths),
           ("manager copies: host changes after activation", "copies", LEVEL, "active",
            "lvl,flip_transit,transit,flip_lvl,lvl,flip_ptr,ptr", Va, cpaths),
           ("manager copies: lvl changed before activation", "copies", LEVEL, "tx_identity",
            "flip_lvl,transit,lvl,ptr", O, cpaths)]
    prod = [("production: manager transaction (lvl first)", "valid", LEVEL, "unknown_record", "lvl,ptr,transit", O,
             paths),
            ("production: manager transaction (transit first)", "valid", LEVEL, "unknown_record", "transit,ptr,lvl", O,
             paths)]
    out = {}
    for kind, cases in (("dev", dev), ("prod", prod)):
        res_k = []
        for i, (n, p, env, want, order, e, pa) in enumerate(cases):
            for k, src in (("lvl", LVL), ("ptr", PTR), ("transit", TRANSIT)):
                shutil.copyfile(src, cps[k])   # pristine private copies before every case (never the game files)
            cf = nd / f"case_{kind}_{i}.tsv"
            cf.write_text("\t".join([n, str(plans[p]), env, want, order, pa[0], pa[1], str(e[0]), str(e[1]), pa[2],
                                     str(e[2])]) + "\n", encoding="utf-8")
            r = subprocess.run([str(exes[kind]), str(cf)], capture_output=True, text=True, timeout=600)
            res_k.append({"case": n, "rc": r.returncode, "out": r.stdout.strip().splitlines()[:2]})
        out[kind] = {"cases": len(cases), "passed": sum(x["rc"] == 0 for x in res_k), "results": res_k}
        print(kind, out[kind]["passed"], "/", out[kind]["cases"])
    for k in cps.values():
        k.unlink()
    # G6-P3's suite (which re-runs G5-P4a's and G6-P2's, and those G6-P1's and the G5 suites), redirected
    cw = WORK / "compat" / "g6p3_pilot_negtest"
    cw.mkdir(parents=True, exist_ok=True)
    q = subprocess.run([sys.executable, "-c", (
        "import sys, pathlib; sys.path.insert(0, r'%s'); sys.path.insert(0, r'%s'); import g6p3_pilot as m; "
        "import g5p1_pilot as p1; m.WORK = pathlib.Path(r'%s'); p1.WORK = m.WORK; sys.exit(m.negtest())")
        % (TOOLS, HERE, cw)], cwd=ROOT, capture_output=True, text=True, timeout=5400)
    (cw / "negtest.log").write_text(q.stdout + q.stderr)
    out["g6p3_negtest_rc"] = q.returncode
    out["pass"] = all(out[k]["passed"] == out[k]["cases"] for k in ("dev", "prod")) and out["g6p3_negtest_rc"] == 0
    (nd / "summary.json").write_text(json.dumps(out, indent=1, default=str) + "\n")
    print("NEGTEST_G6P4", "PASS" if out["pass"] else "FAIL")
    return 0 if out["pass"] else 1


# --- the modified runs (development build) --------------------------------------------------------------------------

CASES = {"A": None, "B": 0, "C": 1, "D": 0}
RUN_SECONDS, EXIT_AFTER, END_READ = 150, 85, 80
CM = {0x80: 0x80, 0xAC: 0xAC, 0x318: 0x318, 0x324: 0x324, 0xD6C: 0x33C, 0xEC4: 0x494, 0xED0: 0x4A0, 0x10DC: 0x4CC,
      0x113C: 0x52C, 0x113E: 0x52E, 0xC4: 0xC4}


def run(tag):
    st = subprocess.run([sys.executable, str(HERE / "g5p1_dev_gate.py"), "status"], capture_output=True, text=True)
    if st.stdout.strip() != "patched":
        raise SystemExit("the development gate is not applied")
    for f in ("offline.json", "negtest/summary.json"):
        if not json.loads((WORK / f).read_text()).get("pass"):
            raise SystemExit(f"{f} did not pass")
    for case, sel in CASES.items():
        plan = paths = env = None
        if sel is not None:
            run_ = f"{PREFIX}_{tag}_{case}"
            res, text, paths = compile_plan(f"run_{tag}_{case}", [(MOD[sel], [manager(sel)])],
                                            session=run_ if case != "D" else None)
            if res["active"] != [MOD[sel]] or text is None:
                raise SystemExit(f"compiler refused the run's mod: {res['mods']}")
            plan = paths["cache"] / rm.PLAN_NAME
            env = LEVEL if case != "D" else None
        row = run_case(tag, case, plan=plan, env_level=env, extra={"gm_copy": COPY} if case in ("B", "C") else None,
                       session_paths=paths if case != "D" else None, steps=exit_steps(EXIT_AFTER),
                       seconds=RUN_SECONDS, end_read_at=END_READ)
        print(case, json.dumps(row, default=str)[:500], flush=True)
    return 0


def judge(tag):
    data, _, _ = files()
    wps = gm_waypoints(data)
    out, det, P, invalid = {}, {}, {}, []
    for case in CASES:
        w = WORK / tag / case
        r = json.loads((w / "row.json").read_text())
        for k in ("samples", "live", "states"):
            r[k] = json.loads((w / f"{k}.json").read_text())
        r["log"] = g6p3.load_log(r["run"])
        r["safe"], r["safety"] = g6p3.safety(r)
        out[case] = r
        lf = r["live"].get("first")
        if r.get("error") or not lf or any("error" in a for a in lf["actors"].values()):
            invalid.append(f"{case}:read")
        if not r["samples"] or r["samples"][-1]["t"] - r["samples"][0]["t"] < 60:
            invalid.append(f"{case}:samples")
    A, B, C, D = (out[c] for c in "ABCD")

    def mv(r, label, mgr):
        lab = labels_of(r)
        return movement(r["samples"], label, mgr, wps, home(data, lab[label]), r["samples"][0]["t"] + 10)

    def whole(r, label):
        lab = labels_of(r)
        return movement(r["samples"], label, "gm", wps, home(data, lab[label]), 0)
    frog = {c: mv(r, "frog", "gm") for c, r in out.items()}
    det["frog"] = frog
    if not invalid and frog["A"]["at_w"] < 0.9 * frog["A"]["n"]:
        invalid.append("A:frog_not_moved")
    opens = {c: [o.rsplit("\\", 1)[-1].lower() for o in re.findall(r"vfs_open path=(\S+?\.lvl) result=00000000",
                                                                   r["log"])] for c, r in out.items()}
    route_ok = {c: f"{LEVEL}.lvl" in o and "menumap.lvl" in o[o.index(f"{LEVEL}.lvl"):] and
                bool(out[c].get("level_change_t")) for c, o in opens.items()}
    det["route"] = {c: [opens[c], out[c].get("level_change_t")] for c in out}
    if not route_ok["A"]:
        invalid.append("A:route")
    if invalid:
        res = {"invalid": invalid, "verdict": "INVALID", "details": det}
        (WORK / f"judgement_{tag}.json").write_text(json.dumps(res, indent=1, default=str) + "\n")
        print(json.dumps({"invalid": invalid, "verdict": "INVALID"}))
        return 1

    def p1ok(r):
        log = r["log"]
        ptx = p1.parse_plan((WORK / tag / r["case"] / "plan_copy.txt").read_text(encoding="utf-8"))["txs"]
        want = [tuple(ptx[0].split(" ")[2:5])]
        t = [tuple(x) for x in re.findall(r"G5P1 level-tx active level=(\S+) mod=(\S+) id=(\S+)", log)]
        snaps = sorted((f, b) for f, _, b, _ in re.findall(
            r"G5P3 tx snapshot file=(\S+) host_size=(\d+) image_bytes=(\d+) disk_reads=(\d+)", log))
        grow = sorted(set(re.findall(r"M36 grow size file=(\S+) host_size=(\d+) guest_size=(\d+)", log)))
        served = sorted(set(re.findall(r"M33 mods served mod=\S+ file=(\S+)", log)))
        return (log.count("M33 mods state=active") == 1 and t == want
                and "G6P1 level-tx version=2 members=lvl,ptr,transit" in log
                and snaps == sorted([(f"{LEVEL}.lvl", str(SIZE + N_LVL)), (f"{LEVEL}.ptr", str(PSIZE + N_PTR)),
                                     ("transit.lvl", str(TSIZE))])
                and grow == sorted([(f"{LEVEL}.lvl", str(SIZE), str(SIZE + N_LVL)),
                                    (f"{LEVEL}.ptr", str(PSIZE), str(PSIZE + N_PTR)),
                                    ("transit.lvl", str(TSIZE), str(TSIZE))])
                and served == sorted([f"{LEVEL}.lvl", f"{LEVEL}.ptr", "transit.lvl"])
                and "G5P3 tx host_changed" not in log), {"tx": t, "snaps": snaps, "grow": grow, "served": served}
    (b1, db), (c1, dc) = p1ok(B), p1ok(C)
    P["P1_transaction"] = b1 and c1 and "M33 mods=off" in A["log"]
    det["P1"] = {"B": db, "C": dc}

    def union(r, which="first"):
        ls = r["live"][which]["lists"]
        return ls["dw"]["walk"] + ls["inactive"]["walk"]

    def p2(r, grown):
        ab = r["live"]["first"]["ab"]
        X = lambda o: ab + o - 4   # noqa: E731
        ls, la = r["live"]["first"]["lists"], A["live"]["first"]["lists"]
        u, ua = union(r), union(A)
        ok = "error" not in ls and ls["dw"]["prev_ok"] and ls["inactive"]["prev_ok"] and len(u) == len(set(u))
        if not grown:
            return ok and sorted(u) == sorted(ua) and ls["personal"]["count"] == 69 and X(COPY) not in u
        cp = r["live"]["first"]["actors"]["gm_copy"]
        bt = ls["bak_targets"]
        return (ok and cp.get("alive") and cp.get("model") == "NIK_mGenManager" and sorted(u) == sorted(ua + [X(COPY)])
                and ls["rec"]["count"] == la["rec"]["count"] + 1 and ls["rec"]["owners"].count(X(COPY)) == 1
                and len(bt) == len(la["bak_targets"]) + 3
                and all(bt.count(X(COPY + CM[k])) == 1 for k in (0x113C, 0x113E, 0xC4))
                and ls["personal"] == {"count": 70, "last_name": NEW_NAME.decode()})
    P["P2_registration"] = p2(B, True) and p2(C, True) and p2(A, False) and p2(D, False)
    det["P2"] = {c: {"union": len(union(r)), "rec": r["live"]["first"]["lists"].get("rec", {}).get("count"),
                     "bak": len(r["live"]["first"]["lists"].get("bak_targets", [])),
                     "personal": r["live"]["first"]["lists"].get("personal")} for c, r in out.items()}

    def p3(r, sel):
        ok, d = True, {}
        ab = r["live"]["first"]["ab"]
        X = lambda o: ab + o - 4   # noqa: E731
        for which in ("first", "end"):
            lv = r["live"].get(which)
            if not lv:
                return False, {"missing": which}
            src = lv["actors"]["gm"]
            ok = ok and src.get("var2") == [X(SOUNDS["frog"])] * 2 and src.get("v2") == [X(GM_GRAPH)] * 2
            if sel is None:
                continue
            cp = lv["actors"]["gm_copy"]
            own = {"perso": X(COPY + 0x80), "3ddata": X(COPY + 0xAC), "brain": X(COPY + 0x318),
                   "dsgmem": X(COPY + 0x494), "initial": X(COPY + 0x4A0), "current": X(COPY + 0x4CC)}
            got = {k: cp.get(k) for k in own}
            mind = cp.get("mind") or [None] * 4
            ok = ok and got == own and mind[1] == X(COPY + 0x33C) and mind[3] == X(COPY + 0x494) \
                and mind[0] == (src.get("mind") or [None])[0] and cp.get("dsg_model") == src.get("dsg_model") \
                and cp.get("var2") == [X(TARGET_SO[sel])] * 2 and cp.get("v2") == [X(GM_GRAPH)] * 2
            d[which] = {"v0": cp.get("var2"), "v2": cp.get("v2"), "own": got == own}
        return ok, d
    p3r = {c: p3(out[c], CASES[c] if c in ("B", "C") else None) for c in CASES}
    P["P3_target_resolution"] = all(v[0] for v in p3r.values())
    det["P3"] = {c: v[1] for c, v in p3r.items()}
    cc = {}
    for c in ("B", "C"):
        r = out[c]
        lab = labels_of(r)
        by_so = {v: k for k, v in lab.items()}
        tl_, nl_ = by_so[TARGET_SO[CASES[c]]], by_so[TARGET_SO[1 - CASES[c]]]
        t_m = mv(r, tl_, "gm_copy")
        v4n = sum(1 for x in r["samples"] if x["m"].get("gm_copy", {}).get("v4pos"))
        acts = r["live"]["first"]["actors"]
        cc[c] = {"target": t_m, "other_whole": whole(r, nl_), "copy_v4_valid": v4n, "samples": len(r["samples"]),
                 "behaviour": [acts["gm_copy"].get("behaviour"), acts["gm"].get("behaviour")]}
    det["P4_P5"] = cc
    P["P4_guest_consumption"] = all(
        v["copy_v4_valid"] >= 0.9 * v["samples"] and v["target"]["at_w"] >= 0.9 * v["target"]["n"]
        and v["target"]["witness"] >= 0.9 * v["target"]["witness_n"] and v["target"]["witness_n"] > 0
        and v["behaviour"][0] and v["behaviour"][0] == v["behaviour"][1] for v in cc.values())
    ad = {c: {k: whole(out[c], k) for k in ("forest", "smallriver")} for c in ("A", "D")}
    det["A_D_sounds"] = ad
    P["P5_target_specific"] = (all(v["other_whole"]["at_home"] == v["other_whole"]["n"] and v["other_whole"]["at_w"] == 0
                                   for v in cc.values())
                               and all(x["at_home"] == x["n"] and x["at_w"] == 0 for v in ad.values() for x in v.values())
                               and all(f["at_w"] >= 0.9 * f["n"] for f in frog.values()))

    def p6(r, grown):
        ok = True
        for which in ("first", "end"):
            ls = r["live"].get(which, {}).get("lists", {})
            ok = ok and "error" not in ls and ls.get("dw", {}).get("prev_ok") and ls.get("inactive", {}).get("prev_ok")
        if grown:
            ab = r["live"]["first"]["ab"]
            ok = ok and union(r, "end").count(ab + COPY - 4) == 1 and r["live"]["end"]["actors"]["gm_copy"].get("alive")
        return ok and r["safety"]["fault_line"] is False and set(r["safety"]["fault_codes"]) <= {"406D1388"}
    P["P6_integrity"] = all(p6(out[c], c in ("B", "C")) for c in out)

    def brief(x):
        return None if not x else {"free": x["free_bytes"], "largest": x["largest_free"],
                                   "alloc": x["allocated_chunks"], "free_chunks": x["free_chunks"],
                                   "areas": {k: (v["base"], v["length"]) for k, v in x["areas"].items()}}

    def phases(r):
        st = [x for x in r["states"] if "invalid" not in x and "areas" in x]
        lvl_ = next((x for x in st if set(x["areas"]) == {"0", "1", "3"}), None)
        i = st.index(lvl_) if lvl_ else None
        after = st[i + 1:] if i is not None else []
        fix = next((x for x in after if set(x["areas"]) == {"0"}), None)
        menu = next((x for x in after if set(x["areas"]) == {"0", "1", "2"}), None)
        return brief(lvl_), brief(fix), brief(menu)

    def diff(a, b):
        d = {k: a[k] - b[k] for k in ("free", "largest", "alloc", "free_chunks") if a[k] != b[k]}
        for k in sorted(set(a["areas"]) | set(b["areas"])):
            x, y = a["areas"].get(k), b["areas"].get(k)
            if x == y:
                continue
            if x and y and x[0] == y[0]:
                d[f"area{k}_length"] = x[1] - y[1]
            else:
                d[f"area{k}"] = [x, y]
        return d
    ph = {c: phases(r) for c, r in out.items()}
    det["phases"] = ph
    try:
        grown = {"area1_length": N_LVL, "free": -N_LVL, "largest": -N_LVL}
        dl = {c: diff(ph[c][0], ph["A"][0]) for c in "BCD"}
        det["P7_loaded_diff"] = dl
        fix_ok = all(ph[c][1] and ph[c][1]["free"] == 20795836 and ph[c][1]["alloc"] == 1 and
                     ph[c][1]["free_chunks"] == 1 for c in out)
        menu_ok = all(ph[c][2] and ph[c][2] == ph["A"][2] for c in "BCD")
        P["P7_lifetime_cleanup"] = (all(route_ok.values()) and dl["B"] == grown and dl["C"] == grown and dl["D"] == {}
                                    and fix_ok and menu_ok)
    except Exception as x:
        det["P7_error"] = repr(x)
        P["P7_lifetime_cleanup"] = False
    marks = all(r["marker_before_start"][0] == "armed" and r["marker_before_start"][1]["session"] == r["run"]
                and r["marker_before_start"][1]["plan_sha256"] == r["plan_sha256"] and r["controlled"] is True
                and r.get("session_end", {}).get("cleared") is True and r.get("marker_after") == "none"
                for r in (B, C))
    d_ok = ("state=refused reason=level_tx_not_enabled" in D["log"] and "M33 mods served" not in D["log"]
            and "M36 grow" not in D["log"] and not re.search(r"G5P1|G5P3|G6P1", D["log"]))
    P["P8_safety"] = all(r["safe"] for r in out.values()) and marks and d_ok
    det["P8"] = {"marks": marks, "D_refused": d_ok, "safety": {c: r["safety"] for c, r in out.items()}}
    passed = [k for k, v in P.items() if v is True]
    if len(passed) == 8:
        verdict = "G6-P4 VERIFIED — ACTOR-TO-ACTOR REFERENCE INSERTION"
    elif all(P[k] for k in ("P1_transaction", "P2_registration", "P3_target_resolution")) and not (
            P["P4_guest_consumption"] and P["P5_target_specific"]):
        verdict = "G6-P4 PARTIAL — REFERENCE RESOLVED, CONSUMPTION UNVERIFIED"
    else:
        verdict = "NOT PASSED"
    res = {"invalid": invalid, "P": P, "verdict": verdict, "details": det}
    (WORK / f"judgement_{tag}.json").write_text(json.dumps(res, indent=1, default=str) + "\n")
    print(json.dumps({k: res[k] for k in ("invalid", "P", "verdict")}, indent=1))
    return 0 if verdict.startswith("G6-P4 VERIFIED") else 1


def exit_steps(after):
    return (["log intro_10.lvl result=00000000 60", f"wait {after}", "press 40", "wait 3"]
            + sum([[*g6p3.DOWN, "wait 1.2"] for _ in range(5)], [])
            + ["press 44", "wait 4", *g6p3.LEFT, "wait 1.5", "press 44", "wait 20"])


def route(tag):
    st = subprocess.run([sys.executable, str(HERE / "g5p1_dev_gate.py"), "status"], capture_output=True, text=True)
    if st.stdout.strip() != "production":
        raise SystemExit("the route probe runs on the production build")
    row = run_case(tag, "X", steps=exit_steps(45), seconds=110)
    log = g6p3.load_log(row["run"])
    opens = [o.rsplit("\\", 1)[-1].lower() for o in re.findall(r"vfs_open path=(\S+?\.lvl) result=00000000", log)]
    ok, s = g6p3.safety(row)
    states = json.loads((WORK / tag / "X" / "states.json").read_text())
    res = {"lvl_opens": opens, "level_change_t": row.get("level_change_t"), "safe": ok, "safety": s,
           "menumap_after_intro_10": f"{LEVEL}.lvl" in opens and "menumap.lvl" in opens[opens.index(f"{LEVEL}.lvl"):],
           "states": [(x["t"], sorted(x.get("areas", {})), x.get("free_bytes"), x.get("allocated_chunks"),
                       x.get("free_chunks")) for x in states]}
    (WORK / f"route_{tag}.json").write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps(res, indent=1))
    return 0


def main():
    a = sys.argv[1:]
    if a == ["census"]:
        return census()
    if len(a) == 2 and a[0] == "route":
        return route(a[1])
    if a == ["check"]:
        return check()
    if a == ["negtest"]:
        return negtest()
    if len(a) == 2 and a[0] == "run":
        return run(a[1])
    if len(a) == 2 and a[0] == "judge":
        return judge(a[1])
    if len(a) == 2 and a[0] == "oracle":
        return oracle(a[1])
    if len(a) == 2 and a[0] == "oracle-judge":
        return oracle_judge(a[1])
    raise SystemExit(__doc__)


if __name__ == "__main__":
    sys.exit(main())
