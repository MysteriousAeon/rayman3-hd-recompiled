#!/usr/bin/env python3
"""E-489 (D-256) G6-P3: an added actor with a genuine cross-object reference. Development-only; private; hidden.

Selected relationship (offline census, `census` below; VERIFIED in the target data): intro_20's `NIN_m_FairyLight`
designer variable 2 (type 20, graph). Each instance's initial and current designer buffers hold one own-file
relocated word (a `.ptr` slot of file 1) naming a waypoint graph in the level file; three graphs are named by two
fairies each (instances 0 / 3 -> 0x3226a8, 1 / 7 -> 0x335660, 4 / 5 -> 0x3399d8). The source of the copy is instance
2 (SuperObject 0x3358a0, span 0xA4C to the next SuperObject); its own graph 0x336050 lies INSIDE that span at
+0x7B0..+0x9E4 (header, 6 nodes, waypoints, arc lists, arcs), and the only pointers crossing that region's boundary
are the two variable-2 words (initial +0x77C, current +0x9E4). A copy must therefore keep its reference pointing at
an EXISTING graph (target identity preserved, never rebased into the copy) and must not copy the graph region.

  g6p3_pilot.py census                 offline candidate / structure census (writes private/work/e489/census.json)
  g6p3_pilot.py oracle TAG             controlled reference oracle (production build, no structural growth): hidden
                                       runs A (no plan), RA, RB (instance 2's two variable-2 words redirected, a
                                       same-size .lvl edit of two existing relocated words, to the graph of instance
                                       0 resp. 1)
  g6p3_pilot.py oracle-judge TAG       Q1-Q6
Outputs: private/work/e489/.

ORACLE PROTOCOL (committed before the oracle runs; derived from the read-only survey E-480 s1 and G5-P4a f1 A)
Evidence before the runs: in E-480 s1 (no plan, 114 s sampled) every moving fairy passes within 0.1-0.4 units of
every waypoint of the graph its variable 2 names (instances 0 / 3 and 1 / 7 follow their shared graph; 5 and 6 do
not move); instance 2 arrives at each of its own 6 waypoints 4-5 times and comes no closer than 5.3 units to graph
A's waypoints. The oracle asks whether the REFERENCE WORD causes the path: only the two 4-byte values change (the
graph's file offset - 4), the relocation slots are the existing ones, nothing grows.
Runs: m9_license_run.py hidden, non-activating, muted, no physical pad, private user root, `--test-level intro_20`,
no input, no frames, 130 s; production build (gate status `production`); after intro_20's area appears + 6 s the
eight fairies are read at their file SuperObjects (area base + offset - 4), then every fairy's position is sampled
every 0.1 s; designer words and the actor lists are read once there and once at the end.
  A: no plan.  RA: plan `e489.redirect-a` (instance 2 -> graph 0x3226a8).  RB: plan `e489.redirect-b` (-> 0x335660).
Arrival = within 1.0 unit of a waypoint; own-exclusive waypoints of graph 0x336050 = nodes 0, 1, 5 (each >= 17 units
from both other graphs' flown paths in s1).
  Q1 serving: RA / RB `M33 mods state=active`, `M33 mods served` names intro_20.lvl only, no `M36 grow`, no G5P1 /
     G5P3 / G6P1 line; A `M33 mods=off`.
  Q2 guest resolution: at the first read instance 2's live initial and current variable-2 words = area base + the
     plan's graph - 4 (A: + 0x336050 - 4); the other seven fairies' words = area base + their file graph - 4.
  Q3 consumption: instance 2 arrives >= 3 times at every waypoint of the plan's graph (A: of its own graph), and in
     RA / RB never comes within 3.0 units of own-exclusive waypoints 0, 1, 5.
  Q4 graph-specific traversal: instance 2's arrival sequence (consecutive duplicates removed) steps along the target
     graph's cycle as its original followers fly it in A (graph A: +1 mod 5; graph B: 1 -> 4 -> 3 -> 2 -> 0 -> 1),
     allowing at most one irregular step (the first arrival after the start).
  Q5 locality: in RA / RB each of instances 0, 1, 3, 4, 7 arrives >= 3 times at every waypoint of its own graph, as
     in A.
  Q6 safety: M21 / M22 / M23 0, haptics policy line, runner exit 0, no game process naming the run left, no access
     violation / engine error line, fault codes within {406D1388}.
  Invalid (new tag, kept): intro_20 not loaded, a fairy unreadable, < 60 s of samples, A fails Q3 or Q5.
  All six = ORACLE VERIFIED: the graph a fairy flies is the one its variable-2 reference names; the reference is
  resolved by the existing relocation and consumed per instance.
ORACLE REVISION 1 (after run o1, before o2; o1 kept as judged, oracle_o1.json: NOT PASSED):
  Cause: a harness defect, not the reference. The oracle plan ended with an empty line after `end`, so the production
  overlay refused the whole plan (`M33 mods state=refused reason=data_after_end@line9`): nothing was served in RA / RB
  (Q1 / Q2 / Q3 FAIL there; instance 2 flew its own graph, as in A). A passed Q1-Q3, Q5, Q6; Q5 / Q6 passed in all
  three. Fix: the plan text ends exactly as the compiler's writer ends it (`end 1 2` + one newline). Nothing else
  changes (cases, steps, criteria, thresholds). Fresh runs: o2 (A, RA, RB).

ORACLE RESULT o2 (oracle_o2.json): ORACLE VERIFIED. RA: instance 2's words live = area base + 0x3226a8 - 4, 6
  arrivals at each of graph A's waypoints in its cycle (0 irregular steps), own exclusive waypoints >= 17.2 units;
  RB: + 0x335660 - 4, 9-10 arrivals each in graph B's cycle, >= 19.4 units; the other fairies unchanged; A as s1.
ROUTE PROBE x1 (route_x1.json): menumap.lvl opens after intro_20; intro_20's area left 64 s after it appeared; the
  fix-only block-8 state between them is 20,795,836 free, 1 / 1 chunks; menumap then at 0x40F4C290 (7,512,308
  bytes), 13,274,536 free.

  g6p3_pilot.py check            offline O1-O8 (offline.json)
  g6p3_pilot.py negtest          transaction tests: dev + production headers; G5-P4a and G6-P2 suites re-run
  g6p3_pilot.py run TAG          hidden runs A, B, C, D (development build)
  g6p3_pilot.py judge TAG        P1-P8

OPERATION (manifest): {"type": "insert-fairy-on-graph", "level": "intro_20", "model": FAIRY20, "instance": 2,
  "lvl_sha256", "ptr_sha256", "transit_sha256" (exact originals), "follow_graph_of": 0 | 1}. The selector names the
  fairy instance whose variable-2 graph the new fairy follows (0 -> graph A 0x3226a8, 1 -> graph B 0x335660), resolved
  and asserted by the compiler from the exact files (named by exactly the two fairies the allow-list names; node count
  5 > the copy's variable 0 = 4). No addresses, offsets, slots, relocation values, graph or designer bytes, other
  models / instances / levels, a second actor, or composition with any other structural operation.
CONSTRUCTION (compiler = independent constructor, O2): the copy (SuperObject 0x5D9F90) of instance 2's 0xA4C-byte
  block; its own Perso / 3dData / StdGame / Dynam / Brain / Mind / Intelligence / DsgMem / buffers (rebased); model
  data shared; the source's graph region +0x7B0..+0x9E4 left out (zero, unrelocated); both variable-2 words = the
  target graph (two new own-file slots naming EXISTING data: identity kept); personal type 143
  `LLU_NIN_m_FairyLight_rose01_G6P3`, SO record, matrix backup, sibling after the source; transit actor count 128.
  .lvl +2,892 (6,138,576), .ptr +408 (51 slots; 273,948).

RUNTIME PROTOCOL (committed before the development build and before any modified run)
Build: g5p1_dev_gate.py apply (G5-P3 snapshot, G6-P1 version 2, the G6-P3 intro_20 rows) + tools\\build_incremental.bat;
production restored afterwards. Runs: m9_license_run.py hidden, non-activating, muted, no physical pad, private user
root, `--test-level intro_20`, 150 s; guest-scoped input only for the exit: after intro_20.lvl opens, wait 85 s,
then the probe x1's Exit Game sequence, then 20 s. Reads (read-only): block-8 snapshot at every area-table change;
6 s after intro_20's area appears the eight fairies (+ the copy in B / C) at their file SuperObjects, the actor lists
and the fairy graphs once; positions every 0.1 s until the area is left; the same actor / list read 80 s after the
area appeared (before the exit).
  A: no plan.  B: follow_graph_of 0 (mod g6p3.fairy-a, session = run, R3HD_DEV_STRUCTURAL_TX=intro_20).
  C: follow_graph_of 1 (g6p3.fairy-b, same).  D: B's plan with the development variable unset (gate off).
  (No E case: every case exits the level through the title, so B / C demonstrate cleanup themselves.)
Arrival = within 1.0 unit of a waypoint. AB = the live intro_20 area base; X(o) = AB + o - 4.
  P1 transaction integrity (B, C): one `M33 mods state=active`; `G5P1 level-tx active level=intro_20 mod=<mod>
     id=<plan id>`; `G6P1 level-tx version=2 members=lvl,ptr,transit`; `G5P3 tx snapshot` intro_20.lvl image_bytes
     6138576, intro_20.ptr 273948, transit.lvl 26140; `M36 grow size` intro_20.lvl 6135684 -> 6138576, intro_20.ptr
     273540 -> 273948, transit.lvl 26140 -> 26140; served exactly intro_20.lvl, intro_20.ptr, transit.lvl; no
     `G5P3 tx host_changed`. A: `M33 mods=off`.
  P2 new actor registration (first read): the copy X(0x5D9F90) alive (reciprocal links), model NIN_m_FairyLight;
     the union of the active and inactive worlds = A's union + exactly the copy, each once, previous links
     consistent; SO records = A's count + 1 with the copy once; backup targets = A's + the copy's matrix X(0x5DA054)
     once; personal types 144, the last `LLU_NIN_m_FairyLight_rose01_G6P3`. A / D: 143 personal types, no copy.
  P3 reference resolution (guest-side; B, C; first and 80-s reads): the copy's Perso / 3dData / Brain / Mind /
     Intelligence / DsgMem / initial / current = X(copy + 0x80 / 0xAC / 0x5F8 / 0x604 / 0x618 / 0x770 / 0x77C /
     0x9E4); its AI model and DsgMem model = the source's; its two live variable-2 words = X(target graph) (B 0x3226a8,
     C 0x335660); the live walk of that graph: 5 nodes, no problems, header count 5; the source's words = X(0x336050)
     and the other fairies' = X(their file graph) in every case.
  P4 reference consumption (B, C): the copy arrives >= 3 times at every waypoint of its target graph; its live
     behaviour name equals the source's at the first read.
  P5 reference-specific behaviour: the copy's arrival sequence steps along its target's cycle as flown in E-480 s1 /
     o2 (A: 0 1 2 3 4; B: 1 4 3 2 0), at most one irregular step; it never arrives at a waypoint of the other target
     graph and never comes within 3.0 units of the source graph's exclusive waypoints 0, 1, 5; changing only the
     selector (B -> C) moves the copy from graph A to graph B while the source keeps its own graph (>= 3 arrivals at
     each of its six waypoints in B and C).
  P6 runtime structural integrity: both world walks' previous links consistent and no list read error at both reads;
     the copy in the union exactly once and alive at the 80-s read; instances 0, 1, 3, 4, 7 >= 3 arrivals at each own
     waypoint in every case (as in A); no access violation / engine error line, fault codes within {406D1388}.
  P7 lifetime and cleanup: route taken in all four (menumap.lvl opens after intro_20.lvl, intro_20's area left);
     while loaded B - A = C - A = {area 1 length +2,892, free -2,892, largest -2,892}, D - A = {}; the block-8 state
     between intro_20 and menumap = fix only (20,795,836 free, 1 / 1 chunks) in all four (the grown area, the copy
     and its allocations released); the menumap state after the exit equal to A's in B, C, D.
  P8 production / desktop safety: D `state=refused reason=level_tx_not_enabled`, nothing served, no `M36 grow`, no
     G5P1 / G5P3 / G6P1 line; every run: M21 / M22 / M23 0, haptics policy line, runner exit 0, no game process
     naming the run left; B / C markers armed before the start (session, plan SHA-256) and cleared after the
     controlled end; `check` and `negtest` passed first.
  Invalid (new tag, kept): process / area not found, a tracked actor unreadable at the first read, < 60 s of samples,
     A's movers fail P6's arrival term, the route not taken in A.
  Stop: a guest fault, bad actor ownership, invalid reference resolution or a desktop-safety violation.
  All eight = G6-P3 VERIFIED — CROSS-REFERENCED ACTOR INSERTION; P1-P3 with P4 or P5 failing = PARTIAL — REFERENCE
  RESOLVED, CONSUMPTION UNVERIFIED.

EXIT-ROUTE PROBE (read-only, no plan, production build; informs the runtime protocol, judges nothing):
  g6p3_pilot.py route TAG   one hidden run X with no plan: intro_20 opened directly, then after 45 s the title's own
  Start -> pause menu -> five downs -> A -> left -> A (G5-P3's Exit Game sequence, guest-scoped input) -> the title
  screen; recorded: whether menumap.lvl opens after intro_20 and when intro_20's block-8 area disappears.
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
import g3b_ab as g3b  # noqa: E402
import g4b_ab as g4b  # noqa: E402
import block8_probe as bp  # noqa: E402

PREFIX = "e489"
WORK = ROOT / "private" / "work" / PREFIX
LEVEL, ENV = "intro_20", rm.STRUCT_ENV
GAME, RUNS = g3a.GAME, g3a.RUNS
LDIR = GAME / "GAMEDATAbin" / LEVEL
LVL, PTR, TRANSIT = LDIR / f"{LEVEL}.lvl", LDIR / f"{LEVEL}.ptr", LDIR / "transit.lvl"
SIZE, PSIZE, TSIZE = 6135684, 273540, 26140
LVL_SHA = "a21aa7691db4cedb3892e685e5395fd23b530b0bde4d64a09035dfb5f2d0b11f"
PTR_SHA = "be90b58a3bfa78d19f3335489edcc79214442d52cbde04c6ad5a465f9fb17cb1"
TRANSIT_SHA = "51c0fbf1239acd6188316a6d64507761903d5a087df1ea717426d5cb810e6aa8"
SRC_INST, SRC_SO, VAR = 2, 0x3358A0, 2
VAR_WORDS = (0x77C, 0x9E4)                  # instance 2's initial / current variable-2 words (block offsets)
OWN_GRAPH = 0x336050
GRAPHS = {"a": (0, 0x3226A8), "b": (1, 0x335660)}   # selector -> (fairy instance whose graph it is, graph offset)
CYCLE = {"a": [0, 1, 2, 3, 4], "b": [1, 4, 3, 2, 0]}  # the cyclic waypoint order the original followers fly (s1)
OWN_EXCLUSIVE = (0, 1, 5)
MOVERS = (0, 1, 3, 4, 7)
SECONDS = 130
sha = lambda b: hashlib.sha256(b).hexdigest()   # noqa: E731


def u32(b, o):
    return struct.unpack_from(">I", b, o)[0]


def files():
    data, ptr, tl = LVL.read_bytes(), PTR.read_bytes(), TRANSIT.read_bytes()
    if (len(data), sha(data), len(ptr), sha(ptr), len(tl), sha(tl)) != (SIZE, LVL_SHA, PSIZE, PTR_SHA, TSIZE,
                                                                         TRANSIT_SHA):
        raise SystemExit("intro_20 files are not the verified versions")
    return data, ptr, tl


def index():
    ix = rm.read_script_index(GAME, LEVEL)
    insts = ix["placements"][rm.FAIRY20]
    graphs = {n: ix["graphs"][(rm.FAIRY20, n, VAR)] for n in range(len(insts))}
    return ix, insts, graphs


def waypoints(lvl, entry):
    return [struct.unpack_from(">3f", lvl, w) for _, w in entry["nodes"]]


# --- census (offline) -----------------------------------------------------------------------------------------------

def census():
    data, ptr, tl = files()
    ix, insts, graphs = index()
    slots = ix["slots"]
    dsg = ix["defaults"][rm.FAIRY20]
    allso = sorted(i["so"] for v in ix["placements"].values() for i in (v or []))
    out = {"files": {"lvl": [SIZE, LVL_SHA], "ptr": [PSIZE, PTR_SHA], "transit": [TSIZE, TRANSIT_SHA]},
           "dsg_vars": dsg["vars"], "dsg_length": dsg["length"], "instances": []}
    for n, i in enumerate(insts):
        d = dsg["instances"][n]
        end = min(s for s in allso if s > i["so"])
        words = [d[k] + dsg["vars"][VAR][0] for k in ("initial", "current")]
        out["instances"].append({
            "instance": n, "so": hex(i["so"]), "span": hex(end - i["so"]), "dsgmem": hex(d["dsgmem"] - i["so"]),
            "buffers": [hex(d["initial"] - i["so"]), hex(d["current"] - i["so"])],
            "var2_words_relocated": [slots.get(w) for w in words],
            "graph": hex(graphs[n]["graph"]), "graph_in_own_span": i["so"] <= graphs[n]["graph"] < end,
            "nodes": len(graphs[n]["nodes"]), "var0": data[d["initial"] + 49], "var1": data[d["initial"] + 48]})
    (WORK / "census.json").parent.mkdir(parents=True, exist_ok=True)
    (WORK / "census.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out, indent=1))
    return 0


# --- oracle plans (same-size .lvl edits of the two existing relocated words; production runtime) -------------------

def oracle_plan(work: Path, selector: str):
    data, _, _ = files()
    _, g = GRAPHS[selector]
    mid = f"e489.redirect-{selector}"
    lines = ["R3HD_MOD_PLAN 1", f"# E-489 oracle plan (g6p3_pilot.py): instance 2 variable 2 -> graph {g:#x}",
             f"mod {mid} 1.0.0", f"gameplay {mid}", f"file {SIZE} {LVL}"]
    for k, off in enumerate(VAR_WORDS):
        o = SRC_SO + off
        if u32(data, o) != OWN_GRAPH - 4:
            raise SystemExit("instance 2's variable-2 word is not the expected original")
        blob = work / f"range_{k}.bin"
        new = struct.pack(">I", g - 4)
        blob.write_bytes(new)
        lines.append(f"range 0 {o} 4 {g3a.fnv(data[o:o + 4]):016x} {g3a.fnv(new):016x} {mid} {blob}")
    lines += ["end 1 2", ""]   # the writer's own terminator (r3hd_mods.write_plan_files): nothing after `end`
    plan = work / "plan.txt"
    plan.write_bytes("\n".join(lines).encode("utf-8"))   # LF bytes, as write_plan_files writes them
    return plan


# --- the hidden runner (read-only probes) ---------------------------------------------------------------------------

def actor_state(p, so):
    """One read-only snapshot of an actor: links, Brain / Mind / Intelligence / DsgMem / buffers, variable 2."""
    from m5_live import Actor
    a = Actor(p, so)
    st = {"so": so, "model": a.model, "perso": a.perso, "alive": a.alive()}
    pw = p.words(a.perso, 4)
    st["3ddata"], st["brain"] = pw[0], pw[3]
    st["mind"] = list(a.mind) if a.mind else None
    if a.mind:
        mem = p.words(a.mind[3], 3)
        st["dsgmem"], st["dsg_model"], st["initial"], st["current"] = a.mind[3], mem[0], mem[1], mem[2]
        st["var2"] = [p.words(mem[1] + 0, 1)[0], p.words(mem[2] + 0, 1)[0]]
        st["behaviour"] = a.comport()
    return st


def lists(p):
    def w(a):
        x = p.words(a, 1)
        if not x:
            raise ValueError(f"read {a:#x}")
        return x[0]
    r = {}
    try:
        for key, g in (("dw", g4b.G_DW), ("inactive", g4b.G_INACT)):
            wd = w(g)
            walk, so = [], w(wd + 8)
            while so and len(walk) < 600:
                walk.append(so)
                so = w(so + 0x14)
            r[key] = {"count": w(wd + 0x10), "walk": walk,
                      "prev_ok": all(w(b + 0x18) == a for a, b in zip(walk, walk[1:]))}
        h = w(g4b.G_REC)
        recs, c = [], w(h)
        while c and len(recs) < 2000:
            recs.append(w(c + 4))
            nx = w(c)
            if nx == c:
                break
            c = nx
        r["rec"] = {"count": w(h + 8), "owners": recs}
        links, l_ = [], w(g4b.G_BAK)
        while l_ and len(links) < 4000:
            links.append(w(l_ + 4))
            l_ = w(l_)
        r["bak_targets"] = links
        pc = w(g4b.G_OBJ + 0x20)
        e, i = w(g4b.G_OBJ + 0x18), 0
        while e and i < pc - 1:
            e, i = w(e), i + 1
        nm = p.read(w(e + 0xC), 32) if e else None
        r["personal"] = {"count": pc, "last_name": nm.split(b"\0")[0].decode("ascii", "replace") if nm else None}
    except Exception as x:
        r["error"] = repr(x)
    return r


def run_case(tag, case, plan=None, env_level=None, extra=None, session_paths=None, steps=None, seconds=SECONDS,
             end_read_at=None):
    """One hidden run. `extra` = {label: file SuperObject offset} of added actors; `session_paths` = the compiler's
    paths when the plan armed a structural marker (cleared after a controlled end)."""
    from m5_live import Actor, Process
    data, _, _ = files()
    ix, insts, graphs = index()
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
    tracked = {f"f{n}": i["so"] for n, i in enumerate(insts)}
    tracked.update(extra or {})
    graph_offsets = sorted({e["graph"] for e in graphs.values()})
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
            last, t_end, area_t, ab, actors, nxt = "none", t0 + seconds - 5, None, None, None, 0.0

            def rd(a):
                x = p.words(a, 1)
                if not x:
                    raise ValueError(f"read {a:#x}")
                return x[0]

            def read_end(ab_):
                end = {"t": round(time.monotonic() - t0, 3), "actors": {}}
                for label, off in tracked.items():
                    try:
                        end["actors"][label] = actor_state(p, ab_ + off - 4)
                    except Exception as x:
                        end["actors"][label] = {"error": repr(x)}
                end["lists"] = lists(p)
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
                        row["level_change_t"] = round(time.monotonic() - t0, 3)   # intro_20's area left
                        actors = {}
                if end_read_at is not None and area_t is not None and "end" not in live and \
                        "level_change_t" not in row and time.monotonic() >= area_t + end_read_at:
                    live["end"] = read_end(ab)
                if area_t is not None and actors is None and time.monotonic() >= area_t + 6:
                    actors, first = {}, {"t": round(time.monotonic() - t0, 3), "ab": ab, "actors": {}}
                    for label, off in tracked.items():
                        try:
                            first["actors"][label] = actor_state(p, ab + off - 4)
                            actors[label] = Actor(p, ab + off - 4)
                        except Exception as x:
                            first["actors"][label] = {"error": repr(x)}
                    first["lists"] = lists(p)
                    first["graphs"] = {}
                    for g in graph_offsets:
                        try:
                            nodes, prob, hdr = g3b.walk_null(rd, ab + g - 4)
                            first["graphs"][hex(g)] = {"nodes": nodes, "problems": prob, "header": hdr}
                        except Exception as x:
                            first["graphs"][hex(g)] = {"error": repr(x)}
                    live["first"] = first
                now = time.monotonic()
                if actors and now >= nxt:
                    smp = {"t": round(now - t0, 3), "p": {}}
                    for label, a in list(actors.items()):
                        try:
                            smp["p"][label] = list(a.position())
                        except Exception as x:
                            row.setdefault("sampling_stopped", {})[label] = type(x).__name__
                            actors.pop(label)
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


def load_log(run):
    return "\n".join(q.read_text(errors="replace") for q in sorted((RUNS / run).glob("runtime*.log")))


def safety(r):
    run = r["run"]
    log = load_log(run)
    judges = {t: subprocess.run([sys.executable, str(TOOLS / t), "--run", run], cwd=ROOT, capture_output=True,
                                text=True).returncode
              for t in ("m21_regression.py", "m22_regression.py", "m23_haptics_regression.py")}
    mf = RUNS / run / "m2_faults.log"
    codes = sorted(set(re.findall(r"M2 exception code=([0-9A-Fa-f]+)", mf.read_text(errors="replace")))) \
        if mf.is_file() else []
    fault = bool(re.search(r"access violation|engine error|[Ii]nvalid.*(indirect|function)|Unresolved indirect", log))
    ok = (not any(judges.values()) and "M23 haptics policy=suppressed physical_pad_drivers=none" in log
          and r["runner_exit"] == 0 and not r["game_left"] and not fault and set(codes) <= {"406D1388"})
    return ok, {"judges": judges, "fault_codes": codes, "fault_line": fault}


def arrivals(track, wps, radius=1.0):
    seq = []
    for t, pos in track:
        hit = next((i for i, w in enumerate(wps) if math.dist(pos, w) < radius), None)
        if hit is not None and (not seq or seq[-1][1] != hit):
            seq.append((t, hit))
    return seq


def track_of(samples, label):
    return [(s["t"], s["p"][label]) for s in samples if label in s["p"]]


def cycle_ok(seq, cyc, allowed_irregular=1):
    order = [h for _, h in seq]
    nxt = {a: b for a, b in zip(cyc, cyc[1:] + cyc[:1])}
    bad = sum(1 for a, b in zip(order, order[1:]) if nxt.get(a) != b)
    return bad <= allowed_irregular, bad


# --- oracle ---------------------------------------------------------------------------------------------------------

ORACLE_CASES = {"A": None, "RA": "a", "RB": "b"}


def oracle(tag):
    st = subprocess.run([sys.executable, str(HERE / "g5p1_dev_gate.py"), "status"], capture_output=True, text=True)
    if st.stdout.strip() != "production":
        raise SystemExit("the oracle runs on the production build (gate status must be production)")
    for case, sel in ORACLE_CASES.items():
        plan = None
        if sel:
            pd = WORK / tag / f"plan_{case}"
            pd.mkdir(parents=True, exist_ok=True)
            plan = oracle_plan(pd, sel)
        print(case, json.dumps(run_case(tag, case, plan=plan), default=str)[:400], flush=True)
    return 0


def oracle_judge(tag):
    data, _, _ = files()
    ix, insts, graphs = index()
    wps = {n: waypoints(data, graphs[n]) for n in graphs}
    gwps = {sel: waypoints(data, graphs[n]) for sel, (n, _) in GRAPHS.items()}
    out = {}
    for case in ORACLE_CASES:
        w = WORK / tag / case
        r = json.loads((w / "row.json").read_text())
        for k in ("samples", "live"):
            r[k] = json.loads((w / f"{k}.json").read_text())
        r["log"] = load_log(r["run"])
        r["safe"], r["safety"] = safety(r)
        out[case] = r
    det, Q, invalid = {}, {}, []
    for c, r in out.items():
        lf = r["live"].get("first")
        if r.get("error") or not lf or any("error" in a for a in lf["actors"].values()):
            invalid.append(f"{c}:read")
        if not r["samples"] or r["samples"][-1]["t"] - r["samples"][0]["t"] < 60:
            invalid.append(f"{c}:samples")
    if invalid:
        res = {"invalid": invalid, "verdict": "INVALID"}
        (WORK / f"oracle_{tag}.json").write_text(json.dumps(res, indent=1) + "\n")
        print(json.dumps(res))
        return 1
    A = out["A"]

    def q1(r, sel):
        log = r["log"]
        if sel is None:
            return "M33 mods=off" in log and "M33 mods served" not in log
        served = sorted(set(re.findall(r"M33 mods served mod=\S+ file=(\S+)", log)))
        return ("M33 mods state=active" in log and served == [f"{LEVEL}.lvl"] and "M36 grow" not in log
                and not re.search(r"G5P1|G5P3|G6P1", log))

    def q2(r, sel):
        ab, acts = r["live"]["first"]["ab"], r["live"]["first"]["actors"]
        want2 = (GRAPHS[sel][1] if sel else OWN_GRAPH)
        ok = acts["f2"]["var2"] == [ab + want2 - 4] * 2
        for n in graphs:
            if n != SRC_INST:
                ok = ok and acts[f"f{n}"]["var2"] == [ab + graphs[n]["graph"] - 4] * 2
        return ok

    def q3(r, sel):
        tr = track_of(r["samples"], "f2")
        target = gwps[sel] if sel else wps[SRC_INST]
        seq = arrivals(tr, target)
        counts = [sum(1 for _, h in seq if h == i) for i in range(len(target))]
        excl = [min(math.dist(pp, wps[SRC_INST][i]) for _, pp in tr) for i in OWN_EXCLUSIVE]
        det[f"{r['case']}_f2_counts"], det[f"{r['case']}_f2_exclusive_min"] = counts, excl
        det[f"{r['case']}_f2_seq"] = seq[:40]
        return min(counts) >= 3 and (sel is None or min(excl) >= 3.0), seq

    def q5(r):
        ok = True
        for n in MOVERS:
            seq = arrivals(track_of(r["samples"], f"f{n}"), wps[n])
            counts = [sum(1 for _, h in seq if h == i) for i in range(len(wps[n]))]
            det[f"{r['case']}_f{n}_counts"] = counts
            ok = ok and min(counts) >= 3
        return ok
    seqs = {}
    for c, sel in ORACLE_CASES.items():
        Q[f"{c}_Q1"] = q1(out[c], sel)
        Q[f"{c}_Q2"] = q2(out[c], sel)
        Q[f"{c}_Q3"], seqs[c] = q3(out[c], sel)
        Q[f"{c}_Q5"] = q5(out[c])
        Q[f"{c}_Q6"] = out[c]["safe"]
        if sel:
            Q[f"{c}_Q4"], det[f"{c}_irregular_steps"] = cycle_ok(seqs[c], CYCLE[sel])
    if not (Q["A_Q3"] and Q["A_Q5"]):
        invalid.append("A:control")
    verdict = "INVALID" if invalid else ("ORACLE VERIFIED" if all(Q.values()) else "NOT PASSED")
    res = {"invalid": invalid, "Q": Q, "verdict": verdict, "details": det,
           "safety": {c: r["safety"] for c, r in out.items()}}
    (WORK / f"oracle_{tag}.json").write_text(json.dumps(res, indent=1, default=str) + "\n")
    print(json.dumps({k: res[k] for k in ("invalid", "Q", "verdict")}, indent=1))
    return 0 if verdict == "ORACLE VERIFIED" else 1


# --- compiler helpers -----------------------------------------------------------------------------------------------

import g5p1_pilot as p1  # noqa: E402

MOD = {"a": "g6p3.fairy-a", "b": "g6p3.fairy-b"}
SEL = {"a": 0, "b": 1}
COPY = 0x5D9F90                              # the copy's SuperObject (file offset) in both variants
N_LVL, N_PTR = 2892, 408                     # growth (bytes)
NEW_NAME = b"LLU_NIN_m_FairyLight_rose01_G6P3"


def fairy(sel="a", **kw):
    o = {"type": "insert-fairy-on-graph", "level": LEVEL, "model": rm.FAIRY20, "instance": SRC_INST,
         "lvl_sha256": LVL_SHA, "ptr_sha256": PTR_SHA, "transit_sha256": TRANSIT_SHA, "follow_graph_of": SEL[sel]}
    o.update(kw)
    return o


def compiled(sel="a", **kw):
    with p1.dev_env(LEVEL):
        return rm.compile_insert_fairy_on_graph(fairy(sel, **kw), {"game": GAME})


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


# --- the independent constructor (O2 oracle; shares no code with the compiler) --------------------------------------

def construct(data, ptr, tl, sel):
    """The G6-P3 copy built directly from the census facts: (lvl, ptr, transit, layout). Same conventions as G4b's
    constructor (copy in the source's 16-byte phase; new relocation entries in block order, then personal, record,
    backup; list ends edited)."""
    n, m = u32(ptr, 0), u32(data, 0)
    sl = {}
    for i in range(n):
        f, loc = struct.unpack_from(">iI", ptr, 4 + 8 * i)
        sl[loc + 4] = f
    t = lambda o: u32(data, o) + 4   # noqa: E731
    S, B = SRC_SO, 0xA4C
    gl, gh = S + 0x7B0, S + 0x9E4
    g = GRAPHS[sel][1]
    size = len(data)
    C = size + (S % 16 - size % 16) % 16
    name = NEW_NAME + b"\0" * (4 - len(NEW_NAME) % 4)
    PE = C + B
    NM = PE + 0x14
    RC = NM + len(name)
    BK = RC + 0x48
    BC = BK + 0x18
    end = BC + 0x54
    end += (-end) % 16
    out = bytearray(data) + bytes(end - size)
    w = lambda o, v: struct.pack_into(">I", out, o, v)   # noqa: E731
    out[C:C + B] = data[S:S + B]
    out[C + 0x7B0:C + 0x9E4] = bytes(gh - gl)
    new = []
    for o in sorted(k for k in sl if S <= k < S + B and not gl <= k < gh):
        if o in (S + 0x77C, S + 0x9E4):
            w(o - S + C, g - 4)
        elif sl[o] == 1 and S <= t(o) < S + B:
            w(o - S + C, t(o) - S + C - 4)
        new.append((sl[o], o - S + C))
    nxt = t(S + 0x14)
    w(C + 0x14, nxt - 4)
    w(C + 0x18, S - 4)
    std = t(t(S + 4) + 4)
    pcount = u32(data, 0x1C74 + 8)
    w(std - S + C + 8, pcount)
    # personal: template = the source's element (index at StdGame +8)
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
    rh = t(0x1CFC)
    prv = t(S + 0x18)
    recs = [o - 4 for o in sl if sl[o] == 1 and t(o) == S and not S <= o < S + B and o not in (nxt + 0x18, prv + 0x14)]
    assert len(recs) == 1, "the source's SO record"
    srec = recs[0]
    rlast = t(rh + 4)
    out[RC:RC + 0x48] = data[srec:srec + 0x48]
    w(RC, 0)
    w(RC + 4, C - 4)
    new += [(1, RC + 4), (1, rlast)]
    sb = next(r - 8 for r in sl if sl[r] == 1 and t(r) == S + 0xC4 and not S <= r < S + B)
    blink = t(0x1CEC + 4)
    out[BK:BK + 0x18] = data[sb:sb + 0x18]
    w(BK + 4, 0)
    w(BK + 8, C + 0xC4 - 4)
    w(BK + 0xC, BC - 4)
    out[BC:BC + 0x54] = data[t(sb + 0xC):t(sb + 0xC) + 0x54]
    new += [(1, BK + 8), (1, BK + 0xC), (1, blink)]
    for o, v in ((S + 0x14, C - 4), (nxt + 0x18, C - 4), (0x1C74 + 4, PE - 4), (0x1C74 + 8, pcount + 1),
                 (plast, PE - 4), (rh + 4, RC - 4), (rh + 8, u32(data, rh + 8) + 1), (rlast, RC - 4),
                 (0x1CEC + 4, BK), (blink, BK)):
        w(o, v)
    nptr = struct.pack(">I", n + len(new)) + ptr[4:4 + 8 * n] + b"".join(struct.pack(">iI", f, o - 4) for f, o in
                                                                         new) + ptr[4 + 8 * n:]
    ntl = bytearray(tl)
    struct.pack_into(">I", ntl, 0x9B4 + 0x10, u32(tl, 0x9B4 + 0x10) + 1)
    return bytes(out), nptr, bytes(ntl), {"copy": C, "personal": PE, "name": NM, "record": RC, "backup": BK,
                                          "backup_copy": BC, "slots": len(new)}


# --- the independent loader simulator (O3 / O4) ---------------------------------------------------------------------

def simulate(lvl, ptr, tl, base=0x40F51494):
    """The new files as the guest sees them after the loader: every own-file slot holds area base + word, the
    transit dynamic world's first child comes from the cross-file table. Walks from the world to the copy, its
    Perso -> Brain -> Mind -> DsgMem -> buffers -> variable 2 -> graph -> node waypoints, and the three lists."""
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

    def rd(addr):   # a relocated own-file pointer read at a live address -> live address (None if not relocated)
        o = F(addr)
        return base + u32(lvl, o) if sl.get(o) == 1 else None
    first = next(A(ob + 4) for oa, fa, ob, fb in cross if fa != 1 and fb == 1 and oa + 4 == 0x9B4 + 8)
    world, so = [], first
    while so is not None and so not in world and len(world) < 4096:
        world.append(so)
        so = rd(so + 0x14)
    out = {"world": len(world), "world_count": u32(tl, 0x9B4 + 0x10), "copy_in_world": world.count(A(COPY)),
           "copy_after_source": A(COPY) in world and world.index(A(COPY)) == world.index(A(SRC_SO)) + 1,
           "prev_ok": all(rd(b + 0x18) == a for a, b in zip(world, world[1:]))}
    c = A(COPY)
    perso = rd(c + 4)
    brain = rd(perso + 0xC)
    mind = rd(brain)
    dm = rd(mind + 0xC)
    ini, cur = rd(dm + 4), rd(dm + 8)
    g = [rd(ini), rd(cur)]
    out["chain"] = {"perso": F(perso) - COPY, "brain": F(brain) - COPY, "mind": F(mind) - COPY,
                    "dsgmem": F(dm) - COPY, "initial": F(ini) - COPY, "current": F(cur) - COPY,
                    "intelligence": F(rd(mind + 4)) - COPY, "3ddata": F(rd(perso)) - COPY,
                    "dynam": F(rd(perso + 8)) - COPY, "dsg_model": F(rd(dm)), "ai_model": F(rd(mind))}
    out["var2"] = [F(x) if x else None for x in g]
    wps, node = [], rd(g[0]) if g[0] else None
    while node is not None and len(wps) < 64:
        wps.append(struct.unpack_from(">3f", lvl, F(rd(node + 0xC))))
        node = rd(node)
    out["waypoints"] = wps
    out["copy_points_into_source"] = sorted(hex(F(x)) for x in (rd(A(o)) for o in range(COPY, COPY + 0xA4C, 4))
                                            if x is not None and SRC_SO <= F(x) < SRC_SO + 0xA4C)
    rh = F(rd(A(0x1CFC)))
    recs, r = [], rd(A(rh))
    while r is not None and len(recs) < 4096:
        own = rd(r + 4)   # None: a record of an actor in another file (not an own-file pointer)
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
        tgt = rd(b + 4)
        bl.append(F(tgt) if tgt else None)
        b = rd(b)
    out["backups"] = {"n": len(bl), "copy_matrix": bl.count(COPY + 0xC4), "last": bl[-1]}
    return out


# --- offline O1-O8 --------------------------------------------------------------------------------------------------

def check():
    WORK.mkdir(parents=True, exist_ok=True)
    p1.WORK = WORK
    data, ptr, tl = files()
    ix, insts, graphs = index()
    O, det = {}, {}
    # O1 reference semantics: census facts (VERIFIED in the files) + the oracle verdict (VERIFIED in the guest)
    orc = json.loads((WORK / "oracle_o2.json").read_text()) if (WORK / "oracle_o2.json").is_file() else {}
    words_ok = all(ix["slots"].get(ix["defaults"][rm.FAIRY20]["instances"][n][k]) == 1
                   for n in range(len(insts)) for k in ("initial", "current"))
    shared = {sel: sorted(n for n in graphs if graphs[n]["graph"] == g) for sel, (_, g) in GRAPHS.items()}
    O["O1_reference_semantics"] = (words_ok and orc.get("verdict") == "ORACLE VERIFIED"
                                   and shared == {"a": [0, 3], "b": [1, 7]}
                                   and graphs[SRC_INST]["graph"] == OWN_GRAPH)
    det["O1"] = {"var2_words_relocated": words_ok, "oracle": orc.get("verdict"), "shared": shared}
    # O2 oracle equivalence: the compiler's images = the independent constructor's, directly and through the plan
    eq = {}
    for sel in GRAPHS:
        _, tx = compiled(sel)
        im = tx["images"]
        cl, cp, ct, lay = construct(data, ptr, tl, sel)
        res, text, _ = compile_plan(f"o2_{sel}", [(MOD[sel], [fairy(sel)])])
        pim = p1.images(p1.parse_plan(text)) if text else {}
        eq[sel] = {"direct": (im["lvl"], im["ptr"], im["transit"]) == (cl, cp, ct),
                   "plan": (pim.get(f"{LEVEL}.lvl"), pim.get(f"{LEVEL}.ptr"), pim.get("transit.lvl")) == (cl, cp, ct),
                   "active": res["active"] == [MOD[sel]], "layout": lay == {k: v for k, v in tx["info"]["objects"].items()}
                   | {"slots": tx["info"]["slots"]},
                   "sha": {k: sha(v) for k, v in im.items()}, "growth": [len(cl) - SIZE, len(cp) - PSIZE]}
    O["O2_oracle_equivalence"] = all(v["direct"] and v["plan"] and v["active"] and v["layout"]
                                     and v["growth"] == [N_LVL, N_PTR] for v in eq.values())
    det["O2"] = eq
    # O3 / O4 identity, ownership and the reference, by the independent simulator
    sims = {}
    for sel in GRAPHS:
        cl, cp, ct, _ = construct(data, ptr, tl, sel)
        sims[sel] = simulate(cl, cp, ct)
    want_chain = {"perso": 0x80, "brain": 0x5F8, "mind": 0x604, "dsgmem": 0x770, "initial": 0x77C, "current": 0x9E4,
                  "intelligence": 0x618, "3ddata": 0xAC, "dynam": 0x318}
    t = lambda o: u32(data, o) + 4   # noqa: E731
    O["O3_actor_identity"] = all(
        s["world"] == s["world_count"] == 128 and s["copy_in_world"] == 1 and s["copy_after_source"] and s["prev_ok"]
        and {k: s["chain"][k] for k in want_chain} == want_chain
        and s["chain"]["dsg_model"] == t(SRC_SO + 0x770) and s["chain"]["ai_model"] == t(SRC_SO + 0x604)
        and s["copy_points_into_source"] == [hex(SRC_SO)]
        and s["records"] == {"n": 214, "count": 214, "copy": 1, "last": COPY}
        and s["personal"] == {"n": 144, "count": 144, "last": NEW_NAME.decode(), "copy_index": 143}
        and s["backups"]["copy_matrix"] == 1 and s["backups"]["last"] == COPY + 0xC4 for s in sims.values())
    tw = {sel: waypoints(data, graphs[n]) for sel, (n, _) in GRAPHS.items()}
    O["O4_cross_reference"] = all(s["var2"] == [GRAPHS[sel][1]] * 2 and s["waypoints"] == tw[sel]
                                  for sel, s in sims.items())
    det["O3_O4"] = {sel: {k: v for k, v in s.items() if k != "waypoints"} for sel, s in sims.items()}
    # O5 relocations / fixups: 51 entries, unique, every one inside a new object or an old list end, none inside the
    # copy's left-out region; the copy's slots = the source block's 96 minus the 54 of its graph region (42: in-block
    # rebased, the two reference words now naming the target graph, 17 shared, 1 transit), + 9 list slots
    o5 = {}
    for sel in GRAPHS:
        _, tx = compiled(sel)
        L, nl, np_ = tx["info"]["objects"], tx["images"]["lvl"], tx["images"]["ptr"]
        n0, n1 = u32(ptr, 0), u32(np_, 0)
        added = [struct.unpack_from(">iI", np_, 4 + 8 * i) for i in range(n0, n1)]
        added = [(f, loc + 4) for f, loc in added]
        allsl = [struct.unpack_from(">iI", np_, 4 + 8 * i)[1] + 4 for i in range(n1)]
        cl_, ch_ = tx["info"]["graph_region"]
        objs = [(L["copy"], 0xA4C), (L["personal"], 0x14), (L["record"], 0x48), (L["backup"], 0x18)]
        ends = set()
        for h, off in ((0x1C74, 4), (u32(data, 0x1CFC) + 4, 4), (0x1CEC, 4)):
            ends.add(u32(data, h + off) + 4)
        block_src = [k for k in ix["slots"] if SRC_SO <= k < SRC_SO + 0xA4C]
        region_src = [k for k in block_src if SRC_SO + 0x7B0 <= k < SRC_SO + 0x9E4]
        o5[sel] = {"added": len(added), "unique": len(set(allsl)) == len(allsl),
                   "inside": all(any(a <= o < a + z for a, z in objs) or o in ends for _, o in added),
                   "none_in_region": not any(cl_ <= o < ch_ for _, o in added),
                   "copy_slots": sum(1 for _, o in added if L["copy"] <= o < L["copy"] + 0xA4C),
                   "source_block_slots": len(block_src), "source_region_slots": len(region_src),
                   "ref_words_relocated": all((1, w) in added for w in tx["info"]["reference_words"]),
                   "ptr_growth": len(np_) - PSIZE}
    O["O5_relocations"] = all(v["added"] == 51 and v["unique"] and v["inside"] and v["none_in_region"]
                              and v["copy_slots"] == v["source_block_slots"] - v["source_region_slots"]
                              and v["ref_words_relocated"] and v["ptr_growth"] == 8 * 51 for v in o5.values())
    det["O5"] = o5
    # O6 transaction / budget: one version-2 level-tx with three members whose result hashes are the images; the id
    # recomputed here; memory headroom
    o6 = {}
    for sel in GRAPHS:
        _, tx = compiled(sel)
        res, text, _ = compile_plan(f"o6_{sel}", [(MOD[sel], [fairy(sel)])])
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
    O["O6_transaction_memory"] = all(v["members_ok"] and v["id_ok"] and v["gameplay"]
                                     and v["memory"]["headroom"] > 0 for v in o6.values())
    det["O6"] = o6
    # O7 negatives: every case refuses the whole mod, nothing compiled
    bad = lambda **kw: (lambda: compiled("a", **kw))   # noqa: E731
    neg = {
        "gate off (parse)": refused(lambda: rm.parse_insert_fairy_on_graph(fairy("a"), "o"), "UNSUPPORTED", None),
        "gate off (compile)": refused(lambda: rm.compile_insert_fairy_on_graph(fairy("a"), {"game": GAME}),
                                      "UNSUPPORTED", None),
        "gate names intro_10": refused(lambda: rm.compile_insert_fairy_on_graph(fairy("a"), {"game": GAME}),
                                       "UNSUPPORTED", "intro_10"),
        "wrong level": refused(lambda: rm.parse_insert_fairy_on_graph(fairy("a", level="intro_10"), "o"),
                               "UNSUPPORTED"),
        "unsupported model": refused(bad(model=rm.FLY10 if hasattr(rm, "FLY10") else "x\\y"), "UNSUPPORTED"),
        "other instance": refused(bad(instance=0), "UNSUPPORTED"),
        "invalid symbolic target (4)": refused(lambda: rm.parse_insert_fairy_on_graph(
            fairy("a", follow_graph_of=4), "o"), "UNSUPPORTED"),
        "invalid symbolic target (own graph, 2)": refused(lambda: rm.parse_insert_fairy_on_graph(
            fairy("a", follow_graph_of=2), "o"), "UNSUPPORTED"),
        "malformed reference (raw address)": refused(lambda: rm.parse_insert_fairy_on_graph(
            fairy("a", follow_graph_of="0x3226a8"), "o"), "UNSUPPORTED"),
        "malformed reference (bool)": refused(lambda: rm.parse_insert_fairy_on_graph(
            fairy("a", follow_graph_of=True), "o"), "UNSUPPORTED"),
        "raw pointer key": refused(lambda: rm.parse_insert_fairy_on_graph(dict(fairy("a"), graph=0x3226A8), "o"),
                                   "BAD_MANIFEST"),
        "missing key": refused(lambda: rm.parse_insert_fairy_on_graph(
            {k: v for k, v in fairy("a").items() if k != "transit_sha256"}, "o"), "BAD_MANIFEST"),
        "wrong source version (lvl)": refused(bad(lvl_sha256="0" * 64), "TARGET_CHANGED"),
        "wrong source version (transit)": refused(bad(transit_sha256="1" * 64), "TARGET_CHANGED"),
    }
    # damaged inputs fed straight to the builder (missing transaction member / target / conflicting index / budget)
    me = 1
    insts_named = {n: (e["initial"], e["current"]) for n, e in enumerate(ix["defaults"][rm.FAIRY20]["instances"])}
    spec = rm.FAIRY_ALLOW[LEVEL]
    peers = [i["so"] for n, i in enumerate(insts) if n != SRC_INST]

    def build(lvl_=data, ptr_=ptr, tl_=tl, sel=0, named=insts_named, spec_=spec):
        return rm.build_fairy_on_graph(lvl_, ptr_, tl_, me, spec_, peers, sel, named, "neg")
    dup = bytearray(ptr)
    struct.pack_into(">iI", dup, 4 + 8 * 1, *struct.unpack_from(">iI", ptr, 4))   # entry 1 = entry 0
    pc = bytearray(data)
    struct.pack_into(">I", pc, 0x1C74 + 8, u32(data, 0x1C74 + 8) + 1)            # conflicting personal index
    xref = bytearray(data)   # a third reference to the target graph: an unrelated word made to point at it
    named_wrong = dict(insts_named)
    named_wrong[0] = insts_named[1]
    spec_tight = dict(spec, targets={0: dict(spec["targets"][0], nodes=4)})
    neg.update({
        "duplicate relocation slot": p1.refused(lambda: build(ptr_=bytes(dup)), "STRUCTURE_CHECK"),
        "conflicting personal index": p1.refused(lambda: build(lvl_=bytes(pc)), "STRUCTURE_CHECK"),
        "missing transaction member (transit too short)": p1.refused(lambda: build(tl_=tl[:0x9B4]),
                                                                     "STRUCTURE_CHECK"),
        "target named by other data": p1.refused(lambda: build(named=named_wrong), "STRUCTURE_CHECK"),
        "target node count changed": p1.refused(lambda: build(spec_=spec_tight), "STRUCTURE_CHECK"),
        "target with fewer nodes than variable 0 (graph 0x3399d8)": p1.refused(lambda: build(
            spec_=dict(spec, targets={0: {"graph": 0x3399D8, "nodes": 3, "named_by": (4, 5)}})), "STRUCTURE_CHECK"),
        "insufficient memory budget": p1.refused(lambda: rm.structural_budget(
            LEVEL, SIZE, SIZE + 16 * 1024 * 1024, PSIZE + N_PTR, u32(data, 0), "o"), "BUDGET"),
    })
    del xref
    # damaged output: the simulator must refuse a copy whose reference word was rebased into the copy
    try:
        nl, np_, nt, edits, info = build()
        s = rm._fairy_source(data, ptr, tl, me, spec, peers, 0, insts_named, "neg")
        L = info["objects"]
        bad_l = bytearray(nl)
        struct.pack_into(">I", bad_l, info["reference_words"][1], info["graph_region"][0] - 4)
        sl_new = [(f, loc + 4) for f, loc in (struct.unpack_from(">iI", np_, 4 + 8 * i)
                                              for i in range(u32(ptr, 0), u32(np_, 0)))]
        neg["damaged output (reference rebased into the copy)"] = p1.refused(
            lambda: rm.verify_fairy_on_graph(data, ptr, tl, bytes(bad_l), np_, nt, me, spec, s, L, sl_new, edits, "o"),
            "STRUCTURE_CHECK")
        bad_l2 = bytearray(nl)
        bad_l2[info["graph_region"][0]:info["graph_region"][0] + 4] = b"\0\0\0\1"
        neg["damaged output (left-out region not empty)"] = p1.refused(
            lambda: rm.verify_fairy_on_graph(data, ptr, tl, bytes(bad_l2), np_, nt, me, spec, s, L, sl_new, edits, "o"),
            "STRUCTURE_CHECK")
    except Exception as x:
        neg["damaged output"] = repr(x)
    # composition: one structural operation per mod
    with p1.dev_env(LEVEL):
        mk = lambda ov: {"mod.json": json.dumps(p1.manifest("x.fairy", ov)).encode()}   # noqa: E731
        neg["two fairies in one mod"] = p1.refused(lambda: rm.parse_manifest(mk([fairy("a"), fairy("b")])),
                                                   "BAD_MANIFEST")
        neg["fairy + graph node"] = p1.refused(lambda: rm.parse_manifest(mk([fairy("a"), dict(
            type="insert-graph-node", level=LEVEL, model=rm.FAIRY20, instance=2, variable=2, after_node=3,
            lvl_sha256=LVL_SHA, ptr_sha256=PTR_SHA, position=[-17.0295, -51.4579, -22.0739])])), "BAD_MANIFEST")
    neg_res, o2b = compile_plan("o7_two_mods", [("x.fairy-a", [fairy("a")]), ("x.fairy-b", [fairy("b")])])[:2]
    neg["two structural mods on intro_20"] = (sorted(neg_res["active"]) == [] and o2b is None) or neg_res["mods"]
    O["O7_negatives"] = all(v is True for v in neg.values())
    det["O7"] = {k: v for k, v in neg.items()}
    # O8 compatibility: selftest; G5-P4a / G6-P1 / G6-P2 offline checks re-run (outputs redirected under e489/compat)
    st = subprocess.run([sys.executable, str(TOOLS / "r3hd_mods.py"), "selftest"], capture_output=True, text=True)
    comp = {"selftest": st.stdout.strip().splitlines()[-1] if st.stdout else st.stderr[-200:]}
    for name in ("g5p4a_pilot", "g6p1_pilot", "g6p2_pilot"):
        cw = WORK / "compat" / name
        cw.mkdir(parents=True, exist_ok=True)
        q = subprocess.run([sys.executable, "-c", (
            "import sys, pathlib; sys.path.insert(0, r'%s'); sys.path.insert(0, r'%s'); import %s as m; "
            "import g5p1_pilot as p1; m.WORK = pathlib.Path(r'%s'); p1.WORK = m.WORK; sys.exit(m.check())")
            % (TOOLS, HERE, name, cw)], cwd=ROOT, capture_output=True, text=True)
        (cw / "check.log").write_text(q.stdout + q.stderr)
        comp[name] = q.returncode
    O["O8_compatibility"] = (comp["selftest"].startswith("R3HD_MODS_SELFTEST PASS")
                             and all(comp[n] == 0 for n in ("g5p4a_pilot", "g6p1_pilot", "g6p2_pilot")))
    det["O8"] = comp
    ok = all(O.values())
    out = {"pass": ok, "O": O, "details": det}
    (WORK / "offline.json").write_text(json.dumps(out, indent=1, default=str) + "\n")
    print(json.dumps(O, indent=1))
    print("OFFLINE_G6P3", "PASS" if ok else "FAIL")
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
    texts = {sel: compile_plan(f"neg_{sel}", [(MOD[sel], [fairy(sel)])])[1] for sel in GRAPHS}
    base = p1.parse_plan(texts["a"])
    V = {}
    for sel in GRAPHS:
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
        """The reference swapped after compilation: the appended tail's two variable-2 words rewritten to graph B
        (an image the transaction did not declare)."""
        for k, r in enumerate(m["files"][li]["range"]):
            off, length, gb, nb, mid, blob = r.split(" ", 5)
            if int(off) == SIZE:
                b = bytearray(Path(blob).read_bytes())
                _, tx = compiled("a")
                for w_ in tx["info"]["reference_words"]:
                    struct.pack_into(">I", b, w_ - SIZE, GRAPHS["b"][1] - 4)
                q = nd / "retargeted_tail.bin"
                q.write_bytes(bytes(b))
                m["files"][li]["range"][k] = " ".join([off, length, gb, f"{g3a.fnv(bytes(b)):016x}", mid, str(q)])
    plans = {
        "valid": variant("valid"),
        "valid_b": variant("valid_b", src=p1.parse_plan(texts["b"])),
        "missing_transit": variant("missing_transit", lambda m: m["files"].pop(ti)),
        "missing_ptr": variant("missing_ptr", lambda m: m["files"].pop(pi)),
        "tampered_ptr": variant("tampered_ptr", lambda m: tamper(m, pi, 0)),
        "retargeted": variant("retargeted", retarget),
        "partial_list_edit": variant("partial_list_edit", lambda m: m["files"][li].update(
            range=[r for r in m["files"][li]["range"] if int(r.split(" ")[0]) != 0x1C74 + 8])),
        "corrupt_id": variant("corrupt_id", lambda m: m.update(
            txs=[m["txs"][0][:-1] + ("0" if m["txs"][0][-1] != "0" else "1")])),
        "version_1": variant("version_1", lambda m: m.update(txs=[m["txs"][0].replace("level-tx 2 ", "level-tx 1 ")])),
    }
    O = ("-", "-", "-")
    Va = (V[("a", "lvl")], V[("a", "ptr")], V[("a", "transit")])
    Vb = (V[("b", "lvl")], V[("b", "ptr")], V[("b", "transit")])
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
    dev = [("fairy a valid, lvl,ptr,transit", "valid", LEVEL, "active", "lvl,ptr,transit", Va, paths),
           ("fairy a valid, transit,ptr,lvl", "valid", LEVEL, "active", "transit,ptr,lvl", Va, paths),
           ("fairy a valid, repeated opens", "valid", LEVEL, "active", "ptr,transit,lvl,transit,ptr", Va, paths),
           ("fairy b valid, transit,lvl,ptr", "valid_b", LEVEL, "active", "transit,lvl,ptr", Vb, paths),
           ("fairy not enabled", "valid", "-", "level_tx_not_enabled", "lvl,ptr,transit", O, paths),
           ("fairy enabled for another level", "valid", "intro_10", "tx_level", "transit,lvl,ptr", O, paths),
           ("fairy missing transit member", "missing_transit", LEVEL, "tx_incomplete", "transit,lvl,ptr", O, paths),
           ("fairy missing ptr member", "missing_ptr", LEVEL, "tx_incomplete", "lvl,transit,ptr", O, paths),
           ("fairy tampered ptr, rehashed", "tampered_ptr", LEVEL, "tx_result_hash", "lvl,ptr,transit", O, paths),
           ("fairy reference swapped after compilation", "retargeted", LEVEL, "tx_result_hash", "lvl,ptr,transit", O,
            paths),
           ("fairy partial: personal-count edit dropped", "partial_list_edit", LEVEL, "tx_result_hash",
            "transit,ptr,lvl", O, paths),
           ("fairy corrupted id", "corrupt_id", LEVEL, "tx_id", "transit,lvl,ptr", O, paths),
           ("fairy relabelled version 1", "version_1", LEVEL, "tx_role", "lvl,ptr,transit", O, paths),
           ("fairy copies: host changes after activation", "copies", LEVEL, "active",
            "lvl,flip_transit,transit,flip_lvl,lvl,flip_ptr,ptr", Va, cpaths),
           ("fairy copies: lvl changed before activation", "copies", LEVEL, "tx_identity", "flip_lvl,transit,lvl,ptr",
            O, cpaths)]
    prod = [("production: fairy transaction (lvl first)", "valid", LEVEL, "unknown_record", "lvl,ptr,transit", O, paths),
            ("production: fairy transaction (transit first)", "valid", LEVEL, "unknown_record", "transit,ptr,lvl", O,
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
    # earlier suites with the new development header: G5-P4a (intro_20 version 1, corrected expectation) and G6-P2
    # (which re-runs G6-P1's, the G5 suites and production refusal), outputs redirected under e489/compat
    for name in ("g5p4a_pilot", "g6p2_pilot"):
        cw = WORK / "compat" / f"{name}_negtest"
        cw.mkdir(parents=True, exist_ok=True)
        q = subprocess.run([sys.executable, "-c", (
            "import sys, pathlib; sys.path.insert(0, r'%s'); sys.path.insert(0, r'%s'); import %s as m; "
            "import g5p1_pilot as p1; m.WORK = pathlib.Path(r'%s'); p1.WORK = m.WORK; sys.exit(m.negtest())")
            % (TOOLS, HERE, name, cw)], cwd=ROOT, capture_output=True, text=True, timeout=3600)
        (cw / "negtest.log").write_text(q.stdout + q.stderr)
        out[f"{name}_negtest_rc"] = q.returncode
    out["pass"] = all(out[k]["passed"] == out[k]["cases"] for k in ("dev", "prod")) and \
        out["g5p4a_pilot_negtest_rc"] == 0 and out["g6p2_pilot_negtest_rc"] == 0
    (nd / "summary.json").write_text(json.dumps(out, indent=1, default=str) + "\n")
    print("NEGTEST_G6P3", "PASS" if out["pass"] else "FAIL")
    return 0 if out["pass"] else 1


# --- the title's own Exit Game route (G5-P3's sequence; guest-scoped hidden input) ----------------------------------

DOWN = ["axis 301 -32767", "wait 0.3", "axis 301 0"]
LEFT = ["axis 300 -32767", "wait 0.3", "axis 300 0"]


def exit_steps(after):
    return (["log intro_20.lvl result=00000000 60", f"wait {after}", "press 40", "wait 3"]
            + sum([[*DOWN, "wait 1.2"] for _ in range(5)], []) + ["press 44", "wait 4", *LEFT, "wait 1.5", "press 44",
                                                                   "wait 20"])


def route(tag):
    st = subprocess.run([sys.executable, str(HERE / "g5p1_dev_gate.py"), "status"], capture_output=True, text=True)
    if st.stdout.strip() != "production":
        raise SystemExit("the route probe runs on the production build")
    row = run_case(tag, "X", steps=exit_steps(45), seconds=110)
    log = load_log(row["run"])
    opens = [o.rsplit("\\", 1)[-1].lower() for o in re.findall(r"vfs_open path=(\S+?\.lvl) result=00000000", log)]
    ok, s = safety(row)
    res = {"lvl_opens": opens, "level_change_t": row.get("level_change_t"), "safe": ok, "safety": s,
           "menumap_after_intro_20": "intro_20.lvl" in opens and "menumap.lvl" in opens[opens.index("intro_20.lvl"):]}
    (WORK / f"route_{tag}.json").write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps(res, indent=1))
    return 0


# --- the modified runs (development build) --------------------------------------------------------------------------

CASES = {"A": None, "B": "a", "C": "b", "D": "a"}
RUN_SECONDS, EXIT_AFTER, END_READ = 150, 85, 80


def run(tag):
    st = subprocess.run([sys.executable, str(HERE / "g5p1_dev_gate.py"), "status"], capture_output=True, text=True)
    if st.stdout.strip() != "patched":
        raise SystemExit("the development gate is not applied")
    for f in ("offline.json", "negtest/summary.json"):
        if not json.loads((WORK / f).read_text()).get("pass"):
            raise SystemExit(f"{f} did not pass")
    for case, sel in CASES.items():
        plan = paths = None
        env = None
        if sel:
            run_ = f"{PREFIX}_{tag}_{case}"
            res, text, paths = compile_plan(f"run_{tag}_{case}", [(MOD[sel], [fairy(sel)])],
                                            session=run_ if case != "D" else None)
            if res["active"] != [MOD[sel]] or text is None:
                raise SystemExit(f"compiler refused the run's mod: {res['mods']}")
            plan = paths["cache"] / rm.PLAN_NAME
            env = LEVEL if case != "D" else None
        row = run_case(tag, case, plan=plan, env_level=env, extra={"copy": COPY} if case in ("B", "C") else None,
                       session_paths=paths if case != "D" else None, steps=exit_steps(EXIT_AFTER),
                       seconds=RUN_SECONDS, end_read_at=END_READ)
        print(case, json.dumps(row, default=str)[:500], flush=True)
    return 0


def judge(tag):
    data, _, _ = files()
    ix, insts, graphs = index()
    wps = {n: waypoints(data, graphs[n]) for n in graphs}
    gw = {sel: waypoints(data, graphs[n]) for sel, (n, _) in GRAPHS.items()}
    out = {}
    for case in CASES:
        w = WORK / tag / case
        r = json.loads((w / "row.json").read_text())
        for k in ("samples", "live", "states"):
            r[k] = json.loads((w / f"{k}.json").read_text())
        r["log"] = load_log(r["run"])
        r["safe"], r["safety"] = safety(r)
        out[case] = r
    A, B, C, D = (out[c] for c in "ABCD")
    det, P, invalid = {}, {}, []
    for c, r in out.items():
        lf = r["live"].get("first")
        if r.get("error") or not lf or any("error" in a for a in lf["actors"].values()):
            invalid.append(f"{c}:read")
        if not r["samples"] or r["samples"][-1]["t"] - r["samples"][0]["t"] < 60:
            invalid.append(f"{c}:samples")

    def counts(r, label, pts):
        seq = arrivals(track_of(r["samples"], label), pts)
        return [sum(1 for _, h in seq if h == i) for i in range(len(pts))], seq
    movers = {c: {n: counts(r, f"f{n}", wps[n])[0] for n in MOVERS} for c, r in out.items()}
    det["movers"] = movers
    if any(min(v) < 3 for v in movers["A"].values()):
        invalid.append("A:movers")
    opens = {c: [o.rsplit("\\", 1)[-1].lower() for o in re.findall(r"vfs_open path=(\S+?\.lvl) result=00000000",
                                                                   r["log"])] for c, r in out.items()}
    route_ok = {c: "intro_20.lvl" in o and "menumap.lvl" in o[o.index("intro_20.lvl"):] and
                bool(out[c].get("level_change_t")) for c, o in opens.items()}
    det["route"] = {c: [opens[c], out[c].get("level_change_t")] for c in out}
    if not route_ok["A"]:
        invalid.append("A:route")
    if invalid:
        res = {"invalid": invalid, "verdict": "INVALID", "details": det}
        (WORK / f"judgement_{tag}.json").write_text(json.dumps(res, indent=1, default=str) + "\n")
        print(json.dumps({"invalid": invalid, "verdict": "INVALID"}))
        return 1

    # P1
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

    # P2
    def union(r, which="first"):
        ls = r["live"][which]["lists"]
        return ls["dw"]["walk"] + ls["inactive"]["walk"]

    def p2(r, grown):
        ab = r["live"]["first"]["ab"]
        ls, la = r["live"]["first"]["lists"], A["live"]["first"]["lists"]
        cs = ab + COPY - 4
        u, ua = union(r), union(A)
        ok = "error" not in ls and ls["dw"]["prev_ok"] and ls["inactive"]["prev_ok"] and len(u) == len(set(u))
        if not grown:
            return ok and sorted(u) == sorted(ua) and ls["personal"]["count"] == 143 and cs not in u
        cp = r["live"]["first"]["actors"]["copy"]
        return (ok and cp.get("alive") and cp.get("model") == "NIN_m_FairyLight"
                and sorted(u) == sorted(ua + [cs]) and ls["rec"]["count"] == la["rec"]["count"] + 1
                and ls["rec"]["owners"].count(cs) == 1
                and ls["bak_targets"].count(ab + COPY + 0xC4 - 4) == 1
                and len(ls["bak_targets"]) == len(la["bak_targets"]) + 1
                and ls["personal"] == {"count": 144, "last_name": NEW_NAME.decode()})
    P["P2_registration"] = p2(B, True) and p2(C, True) and p2(A, False) and p2(D, False)
    det["P2"] = {c: {"union": len(union(r)), "rec": r["live"]["first"]["lists"].get("rec", {}).get("count"),
                     "bak": len(r["live"]["first"]["lists"].get("bak_targets", [])),
                     "personal": r["live"]["first"]["lists"].get("personal")} for c, r in out.items()}

    # P3
    def p3(r, sel):
        ok, d = True, {}
        for which in ("first", "end"):
            lv = r["live"].get(which)
            if not lv:
                return False, {"missing": which}
            ab = r["live"]["first"]["ab"]
            X = lambda o: ab + o - 4   # noqa: E731
            acts = lv["actors"]
            for n in graphs:
                want = X(OWN_GRAPH) if n == SRC_INST else X(graphs[n]["graph"])
                ok = ok and acts[f"f{n}"].get("var2") == [want, want]
            if sel is None:
                continue
            cp, src = acts["copy"], acts["f2"]
            C0 = COPY
            own = {"perso": X(C0 + 0x80), "3ddata": X(C0 + 0xAC), "brain": X(C0 + 0x5F8), "dsgmem": X(C0 + 0x770),
                   "initial": X(C0 + 0x77C), "current": X(C0 + 0x9E4)}
            got = {k: cp.get(k) for k in own}
            mind = cp.get("mind") or [None] * 4
            ok = ok and got == own and mind[1] == X(C0 + 0x618) and mind[3] == X(C0 + 0x770) \
                and mind[0] == (src.get("mind") or [None])[0] and cp.get("dsg_model") == src.get("dsg_model") \
                and cp.get("var2") == [X(GRAPHS[sel][1])] * 2
            d[which] = {"var2": cp.get("var2"), "own": got == own}
        if sel is not None:
            gr = r["live"]["first"]["graphs"].get(hex(GRAPHS[sel][1]), {})
            ok = ok and gr.get("problems") == [] and len(gr.get("nodes", [])) == 5 and \
                (gr.get("header") or {}).get("count") == 5
            d["graph"] = {"nodes": len(gr.get("nodes", [])), "problems": gr.get("problems"),
                          "header": gr.get("header")}
        return ok, d
    p3r = {c: p3(out[c], s if c in ("B", "C") else None) for c, s in CASES.items()}
    P["P3_reference_resolution"] = all(v[0] for v in p3r.values())
    det["P3"] = {c: v[1] for c, v in p3r.items()}

    # P4 / P5
    cc = {}
    for c in ("B", "C"):
        sel = CASES[c]
        other = "b" if sel == "a" else "a"
        cnt, seq = counts(out[c], "copy", gw[sel])
        ocnt, _ = counts(out[c], "copy", gw[other])
        tr = track_of(out[c]["samples"], "copy")
        excl = [min(math.dist(pp, wps[SRC_INST][i]) for _, pp in tr) for i in OWN_EXCLUSIVE]
        cyc, bad = cycle_ok(seq, CYCLE[sel])
        src_cnt, _ = counts(out[c], "f2", wps[SRC_INST])
        acts = out[c]["live"]["first"]["actors"]
        cc[c] = {"target_counts": cnt, "other_counts": ocnt, "exclusive_min": excl, "cycle_ok": cyc,
                 "irregular": bad, "source_counts": src_cnt, "seq": seq[:30],
                 "behaviour": [acts["copy"].get("behaviour"), acts["f2"].get("behaviour")]}
    det["P4_P5"] = cc
    P["P4_reference_consumption"] = all(min(v["target_counts"]) >= 3 and v["behaviour"][0]
                                        and v["behaviour"][0] == v["behaviour"][1] for v in cc.values())
    P["P5_reference_specific"] = all(v["cycle_ok"] and max(v["other_counts"]) == 0 and min(v["exclusive_min"]) >= 3.0
                                     and min(v["source_counts"]) >= 3 for v in cc.values())

    # P6
    def p6(r, grown):
        ok = True
        for which in ("first", "end"):
            ls = r["live"].get(which, {}).get("lists", {})
            ok = ok and "error" not in ls and ls.get("dw", {}).get("prev_ok") and ls.get("inactive", {}).get("prev_ok")
        if grown:
            ab = r["live"]["first"]["ab"]
            u = union(r, "end")
            ok = ok and u.count(ab + COPY - 4) == 1 and r["live"]["end"]["actors"]["copy"].get("alive")
        return ok and all(min(v) >= 3 for v in movers[r["case"]].values()) and r["safety"]["fault_line"] is False \
            and set(r["safety"]["fault_codes"]) <= {"406D1388"}
    P["P6_integrity"] = all(p6(out[c], c in ("B", "C")) for c in out)

    # P7
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

    # P8
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
        verdict = "G6-P3 VERIFIED — CROSS-REFERENCED ACTOR INSERTION"
    elif all(P[k] for k in ("P1_transaction", "P2_registration", "P3_reference_resolution")):
        verdict = "G6-P3 PARTIAL — REFERENCE RESOLVED, CONSUMPTION UNVERIFIED" if not (
            P["P4_reference_consumption"] and P["P5_reference_specific"]) else "NOT PASSED"
    else:
        verdict = "NOT PASSED"
    res = {"invalid": invalid, "P": P, "verdict": verdict, "details": det}
    (WORK / f"judgement_{tag}.json").write_text(json.dumps(res, indent=1, default=str) + "\n")
    print(json.dumps({k: res[k] for k in ("invalid", "P", "verdict")}, indent=1))
    return 0 if verdict.startswith("G6-P3 VERIFIED") else 1


def main():
    a = sys.argv[1:]
    if len(a) == 2 and a[0] == "run":
        return run(a[1])
    if len(a) == 2 and a[0] == "judge":
        return judge(a[1])
    if a == ["census"]:
        return census()
    if len(a) == 2 and a[0] == "route":
        return route(a[1])
    if a == ["check"]:
        return check()
    if a == ["negtest"]:
        return negtest()
    if len(a) == 2 and a[0] == "oracle":
        return oracle(a[1])
    if len(a) == 2 and a[0] == "oracle-judge":
        return oracle_judge(a[1])
    raise SystemExit(__doc__)


if __name__ == "__main__":
    sys.exit(main())
