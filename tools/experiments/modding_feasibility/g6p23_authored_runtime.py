#!/usr/bin/env python3
"""E-512 (D-279) G6-P23: runtime acceptance of the authored G6-P22 terrain `west-dip` + one FairyLight (graph A), built
from the checked-in level-patch-v1 declaration. Development-only; private; hidden.

    g6p23_authored_runtime.py preflight   Phase A: CLI compile -> mod.json -> import / plan; identities, hashes, members,
                                          combined checker, difference from G6-P20, growth within the gate's limits
    g6p23_authored_runtime.py negtest     G6-P20's negtest (real overlay code, development + production headers) on
                                          this declaration's plan
    g6p23_authored_runtime.py run TAG     the single hidden run M (development build)
    g6p23_authored_runtime.py judge TAG   P1-P6
Outputs: private/work/e512/ (numbers only).

The G6-P20 harness is reused unchanged except for one hook (g6p20_fairy_terrain.run_ranges: the run's compiled
ranges and terrain name, default = the fixed operation): here it returns the level-patch compile, so the runner reads
back the 50 west-dip terrain ranges AND the 10 FairyLight words (the corrected E-509 filter). Module constants of the
G6-P20 judge are re-pointed: work folder e512, mod id, expected settled z, terrain bytes (standalone west-dip compile).

INPUT
  declaration tools/experiments/modding_feasibility/level_patch_examples/g6p22_west_dip_fairy.json (file SHA-256 and
  canonical identity recorded by preflight; identity bc7c4f5c...); mod id g6p22.custom-terrain-fairy; terrain west-dip
  (start-floor-v1: vertex 0 -0.10, 2 -0.25, 4 -0.20); fairylight follow_graph_of 0 (graph A 0x3226A8).
  Sources: intro_20.lvl 6,135,684 a21aa769..., intro_20.ptr 273,540 be90b58a..., transit.lvl 26,140 51c0fbf1....
  Expected transaction: level-tx 2 intro_20 g6p22.custom-terrain-fairy 3e74d122bdb042e3; results lvl 5cec9e4d...,
  ptr 40934d08..., transit 2be9a434... (ptr / transit = G6-P20's); 63 ranges (13 fairy + 50 terrain).

RUNTIME PROTOCOL (committed before the run; thresholds are not changed after results)
Build: g5p1_dev_gate.py apply (existing rows; no new native code) + tools\\build_incremental.bat (INCREMENTAL_BUILD_OK).
No retained development runtime existed (only negtest test executables), so reuse was not possible. Production before:
r3hd.exe 9bc7070c1bc6ab3a..., rexruntime.dll cd173e9913674797.... Development build used by the run: r3hd.exe
acbc19b87d937f2457e29febada4e46c7d5ca7c1d13fadf6794796dbcd3086c7, rexruntime.dll
cfc3d065d2aae97d3dd0965f19eecdc16681af2213fd5df8de82f06ab874d08c (development string present in rexruntime.dll).
Before the run: preflight 10 / 10 PASS, negtest of this plan development 9 / 9 + production 2 / 2 PASS. Afterwards: g5p1_dev_gate.py revert, the same incremental build, `status`
production, no R3HD_DEV_STRUCTURAL_TX string in rexruntime.dll / r3hd.exe, new production hashes recorded; M33 / M36 /
M38 production regressions (the production binaries are relinked).
One run M `e512_<tag>_M`: G6-P20's run_case unchanged (m9_license_run.py hidden, non-activating, muted, no physical
pad, private user root, --test-level intro_20, 150 s; plan = this mod, session = the run, marker armed; the game
process gets R3HD_DEV_STRUCTURAL_TX=intro_20; guest-scoped input only for G6-P3's Exit Game sequence 85 s after
intro_20.lvl opens). Reads (read-only, no captures): block-8 snapshot at every area-table change; 6 s after the area
appears: the eight fairies and the copy, lists, graphs, the 60 read-back words (50 terrain ranges + 10 fairy words) and
Rayman's actor discovery; positions every 0.1 s until the area is left; the same actor / list / range reads at 80 s.
Controls reused, not rerun: G6-P3 h1 A (actor union, records, backups, personal types, movers, block-8 phases) as in
G6-P20; G6-P19 probe l1 standing point (the base of the prediction).
  P1 atomic activation: G6-P20's P1 with this plan: one `M33 mods state=active`; `G5P1 level-tx active level=intro_20
     mod=g6p22.custom-terrain-fairy id=<plan id>`; version 2, members lvl, ptr, transit; snapshots 6,138,576 /
     273,948 / 26,140; grow lvl / ptr, transit unchanged; served exactly the three files and all 63 planned ranges; no
     host_changed.
  P2 guest readback, judged in two parts:
     P2a terrain: at both reads the 50 west-dip terrain ranges hold the plan image's bytes;
     P2b FairyLight: at both reads the 10 fairy-edited words (original-file 4-byte fairy ranges) hold the plan image's
         values. A word not read is NOT observed (never PASS).
  P3 physics: Rayman's settled z (G6-P13 summary window, samples before the exit) within 0.02 of -25.1408, spread <=
     0.02, x / y within 0.05 of probe l1's; no pre-exit sample below the modified surface - 0.10.
  P4 FairyLight: G6-P20's P4 unchanged (registration, reference resolution at both reads incl. both variable-2 words =
     X(0x3226A8) and the 5-node graph walk, consumption >= 3 arrivals per graph-A waypoint, specificity: cycle with <= 1
     irregular step, 0 graph-B arrivals, >= 3.0 from the source's exclusive waypoints, source and movers >= 3 arrivals).
  P5 exit and cleanup: G6-P20's P5 unchanged (route to menumap; loaded block-8 state - A = area 1 +2,892, free / largest
     -2,892; fix-only between levels 20,795,836 free, 1 / 1; menumap = A; lists consistent, copy alive at 80 s; marker
     armed before and cleared after the controlled end).
  P6 safety: G6-P20's P6 (M21 / M22 / M23 0 = no focus change, cursor move or global input; haptics policy; runner exit
     0; no game process left; fault codes within {406D1388}; gameplay line; only fix / transit / intro_20 / menumap
     opened) with the negtest of THIS plan (development without the gate: level_tx_not_enabled; production header:
     unknown_record 2 / 2); production restored afterwards (checked outside the run).
  Invalid (one repeat allowed, unchanged): process / area not found, Rayman or a tracked actor unreadable at the first
     read, < 60 s of samples, the route not taken.
  Classes: P1-P6 PASS (P2a and P2b) -> G6-P23 VERIFIED — AUTHORED TERRAIN + FAIRYLIGHT RUNTIME; everything PASS except P2b
     not observed -> PARTIAL — FAIRYLIGHT READBACK GAP; P1 failing -> FAILED — TRANSACTION; P2a or P3 failing -> FAILED —
     AUTHORED TERRAIN; P4 failing -> FAILED — FAIRYLIGHT; P5 / P6 failing -> FAILED — EXIT / SAFETY.
"""
import json
import os
import shutil
import struct
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1]))
import r3hd_mods as rm  # noqa: E402
import g6p20_fairy_terrain as g20  # noqa: E402
import g6p21_level_patch as g21  # noqa: E402
import g6p22_intro20_terrain as g22  # noqa: E402

g3, p1, g19 = g20.g3, g20.p1, g20.g19
ROOT, TOOLS, GAME, LEVEL = g20.ROOT, g20.TOOLS, g20.GAME, g20.LEVEL
PREFIX = "e512"
WORK = ROOT / "private" / "work" / PREFIX
DECL = HERE / "level_patch_examples" / "g6p22_west_dip_fairy.json"
LD = json.loads(DECL.read_text(encoding="utf-8"))
MID = LD["id"]
EXPECTED_Z = -25.1408
WANT_TX = "3e74d122bdb042e3"
WANT_RES = {"lvl": "5cec9e4dbcd1d39377188898eab7970868ea0324aedb81ecd46885060576db48",
            "ptr": "40934d08eeed74d87eb0dd385d82a7382cce6e2c53166083741be16d5ee8979c",
            "transit": "2be9a434eed49c9625efe0462a67510216813aff7edc3e75e4e083bff3a0a7e4"}
OVERRIDE = {"type": "level-patch", "patch": LD}


def terrain_canon():
    with p1.dev_env(LEVEL):
        c = rm.parse_level_patch(LD, "decl")
    return next(x for x in c["components"] if x["type"] == "terrain")["patch"]


def terrain_edits():
    lvl, ptr = g19.files()
    return rm.collision_edit(lvl, ptr, LEVEL, rm.terrain_spec(terrain_canon()), "west-dip")


def run_ranges():
    with p1.dev_env(LEVEL):
        _, rs, _ = rm.compile_level_patch(LD, {"game": GAME})
    return rs, terrain_canon()["name"]


def configure():
    WORK.mkdir(parents=True, exist_ok=True)
    g20.WORK, g20.PREFIX, g20.MID, g20.EXPECTED_Z, g20.SEL = WORK, PREFIX, MID, EXPECTED_Z, "a"
    g20.terrain_edits, g20.run_ranges = terrain_edits, run_ranges
    g20.op = lambda **kw: dict(OVERRIDE)   # negtest's plan_of: the declaration, not the fixed operation
    g3.WORK = WORK
    p1.WORK = WORK


def jdump(name, obj):
    (WORK / name).write_text(json.dumps(obj, indent=1, default=str) + "\n", encoding="utf-8")


# ------------------------------------------------------------------------------------------------- Phase A preflight
def preflight():
    configure()
    P = {"game": GAME}
    out, det = {}, {}
    raw = DECL.read_bytes()
    with p1.dev_env(LEVEL):
        canon = rm.parse_level_patch(LD, "decl")
        op = rm.level_patch_operation(canon)
    tc = terrain_canon()
    det["declaration"] = {"file_sha256": rm.sha256_bytes(raw), "identity": rm.level_patch_identity(canon),
                          "terrain_identity": rm.terrain_identity(tc), "id": MID}
    out["declaration: west-dip (0 -0.10, 2 -0.25, 4 -0.20) + fairylight follow_graph_of 0"] = (
        tc["name"] == "west-dip" and tc["region"] == "start-floor-v1"
        and {v: g["delta_z"] for g in tc["groups"] for v in g["vertices"]} == {0: -0.10, 2: -0.25, 4: -0.20}
        and op["follow_graph_of"] == 0 and "terrain_preset" not in op)
    cdir = WORK / "preflight"
    if cdir.exists():
        shutil.rmtree(cdir)
    cdir.mkdir(parents=True)
    rc, cli = g21.cli(["level-patch", str(DECL)], LEVEL, cdir / "mod")
    det["cli"] = cli
    out["CLI level-patch: exit 0, mod.json written, tx 3e74d122bdb042e3, 63 ranges (13 + 50), growth +2892 / +408 / 0"] = (
        rc == 0 and (cdir / "mod" / "mod.json").is_file() and cli.get("transaction", {}).get("id") == WANT_TX
        and cli.get("range_count") == 63 and cli.get("terrain_ranges") == 50 and cli.get("fairylight_ranges") == 13
        and cli.get("growth") == {"lvl": 2892, "ptr": 408, "transit": 0})
    mj = json.loads((cdir / "mod" / "mod.json").read_text(encoding="utf-8")) if rc == 0 else None
    res, text, _ = g3.compile_plan("preflight_cli_mod", [(mj["id"], mj["overrides"])]) if mj else ({}, None, None)
    det["resolve"] = {"active": res.get("active"), "structural_active": res.get("structural_active")}
    m = p1.parse_plan(text) if text else None
    out["import + plan of the CLI mod: active, one level-tx 2 intro_20 g6p22.custom-terrain-fairy 3e74d122bdb042e3"] = (
        m is not None and res.get("active") == [MID] and m["txs"] == [f"level-tx 2 {LEVEL} {MID} {WANT_TX}"])
    if m:
        tx = {f["tx"][0].split(" ")[0]: f["tx"][0].split(" ") for f in m["files"]}
        out["members exactly lvl / ptr / transit; original hashes = the allow-list; results = expected"] = (
            sorted(tx) == ["lvl", "ptr", "transit"]
            and tx["lvl"][1] == rm.STRUCT_ALLOW[LEVEL]["lvl"][1] and tx["ptr"][1] == rm.STRUCT_ALLOW[LEVEL]["ptr"][1]
            and tx["transit"][1] == rm.FAIRY_ALLOW[LEVEL]["transit"][1]
            and {k: v[3] for k, v in tx.items()} == WANT_RES)
        _, text_d, _ = g3.compile_plan("preflight_direct", [(MID, [OVERRIDE])])
        out["CLI mod plan = direct declaration plan (blobs by content)"] = g21.body(text) == g21.body(text_d)
        fc = g22.combined_check(text, "a", MID, tc)
        det["combined_check"] = {k: v for k, v in fc.items() if not isinstance(v, dict)}
        out["independent combined checker (final_check + declaration-derived geometry) ok; expected z -25.1408"] = bool(
            fc.get("ok")) and fc.get("expected_settled_z") == EXPECTED_Z
        out["differs from G6-P20 as predicted: other tx id and lvl result; ptr / transit results equal"] = (
            WANT_TX != g21.REF_ID and WANT_RES["lvl"] != g21.REF_RESULTS["lvl"]
            and WANT_RES["ptr"] == g21.REF_RESULTS["ptr"] and WANT_RES["transit"] == g21.REF_RESULTS["transit"])
        out["run hook: 50 terrain + 10 fairy-word read-backs"] = None
        rs, tname = run_ranges()
        fw = [o for p_, o, d, w in rs if p_.name.lower() == f"{LEVEL}.lvl" and len(d) == 4 and o < g20.SIZE
              and f".terrain.{tname} " not in w]
        out["run hook: 50 terrain + 10 fairy-word read-backs"] = len(terrain_edits()) == 50 and len(fw) == 10
        det["fairy_words"] = [hex(o) for o in fw]
    with p1.dev_env(LEVEL):
        a = rm.compile_level_patch(LD, P)
        b = rm.compile_level_patch(LD, P)
    out["deterministic (two compiles equal)"] = a[1] == b[1] and a[2]["images"] == b[2]["images"]
    out["growth within the development gate's intro_20 v2 rows (lvl <= 4096, ptr <= 1024, transit same size)"] = (
        2892 <= 4096 and 408 <= 1024)
    gate = subprocess.run([sys.executable, str(HERE / "g5p1_dev_gate.py"), "status"], capture_output=True, text=True)
    det["gate_status"] = gate.stdout.strip()
    res_ = {"pass": all(v for v in out.values()), "checks": out, "details": det}
    jdump("preflight.json", res_)
    print(json.dumps({"pass": res_["pass"], "checks": out}, indent=1))
    return 0 if res_["pass"] else 1


def negtest():
    configure()
    return g20.negtest()


def run(tag):
    configure()
    st = subprocess.run([sys.executable, str(HERE / "g5p1_dev_gate.py"), "status"], capture_output=True, text=True)
    if st.stdout.strip() != "patched":
        raise SystemExit("the development gate is not applied")
    for f in ("preflight.json", "negtest/summary.json"):
        if not json.loads((WORK / f).read_text()).get("pass"):
            raise SystemExit(f"{f} did not pass")
    run_ = f"{PREFIX}_{tag}_M"
    res, text, paths = g20.plan_of(f"run_{tag}", [(MID, [dict(OVERRIDE)])], session=run_)
    if res["active"] != [MID] or text is None or p1.parse_plan(text)["txs"] != [f"level-tx 2 {LEVEL} {MID} {WANT_TX}"]:
        raise SystemExit(f"compiler refused or changed the run's mod: {res.get('mods')}")
    row = g20.run_case(tag, "M", paths["cache"] / rm.PLAN_NAME, paths)
    print(json.dumps(row, default=str)[:800])
    return 0


def judge(tag):
    configure()
    g20.judge(tag)   # writes judgement_<tag>.json (verdict text names G6-P20's classes; re-classified below)
    j = json.loads((WORK / f"judgement_{tag}.json").read_text())
    if j.get("invalid"):
        print(json.dumps({"invalid": j["invalid"], "verdict": "INVALID"}))
        return 1
    w = WORK / tag / "M"
    r = json.loads((w / "row.json").read_text())
    live = json.loads((w / "live.json").read_text())
    m = p1.parse_plan((w / "plan_copy.txt").read_text(encoding="utf-8"))
    img = p1.images(m)[f"{LEVEL}.lvl"]
    ter = {o for o, _, _ in terrain_edits()}
    want = {o: img[o:o + n].hex() for o, n in r["reads_at"]}
    got = {k: dict(tuple(x) for x in live.get(k, {}).get("ranges", [])) for k in ("first", "end")}
    t_offs = [o for o, _ in r["reads_at"] if o in ter]
    f_offs = [o for o, _ in r["reads_at"] if o not in ter]
    raw_want = dict(want)
    # Judge correction after the first call (E-512, disclosed; first output kept as judgement_g6p23_m1_first_call.json):
    # a word that the plan's own rebuilt pointer table lists as an own-file slot (file id 1) is relocated by the
    # loader, so its live value is file value + area base (the same rule as live address = area base + offset - 4).
    # The comparison stays exact; only the expected value of listed own-file pointer slots is relocated.
    pimg = p1.images(m)[f"{LEVEL}.ptr"]
    n_ = struct.unpack_from(">I", pimg, 0)[0]
    own = {struct.unpack_from(">iI", pimg, 4 + 8 * i)[1] + 4 for i in range(n_)
           if struct.unpack_from(">iI", pimg, 4 + 8 * i)[0] == 1}
    ab = live["first"]["ab"]
    for o in f_offs:
        if o in own:
            want[o] = f"{(int(raw_want[o], 16) + ab) & 0xFFFFFFFF:08x}"
    p2a = len(t_offs) == 50 and all(got[k].get(o) == want[o] for k in got for o in t_offs) \
        and not any(o in own for o in t_offs)
    observed_f = len(f_offs) == 10 and all(o in got[k] and got[k][o] for k in got for o in f_offs)
    p2b = observed_f and all(got[k][o] == want[o] for k in got for o in f_offs)
    P = dict(j["P"])
    P.pop("P2 terrain loading", None)
    P["P2a terrain readback"] = p2a
    P["P2b FairyLight readback"] = p2b
    det = {"P2a": {k: sum(got[k].get(o) == want[o] for o in t_offs) for k in got} | {"of": len(t_offs)},
           "P2b": {k: sum(got[k].get(o) == want[o] for o in f_offs) for k in got} | {"of": len(f_offs),
                                                                                    "observed": observed_f},
           "P2b words": {hex(o): {"file": raw_want[o], "relocated_slot": o in own, "want_live": want[o],
                                  "first": got["first"].get(o), "end": got["end"].get(o)} for o in f_offs}}
    others = [k for k in P if not k.startswith("P2b")]
    if all(P.values()):
        verdict = "G6-P23 VERIFIED — AUTHORED TERRAIN + FAIRYLIGHT RUNTIME"
    elif not P["P1 atomic activation"]:
        verdict = "G6-P23 FAILED — TRANSACTION (P1)"
    elif not (P["P2a terrain readback"] and P["P3 physics"]):
        verdict = "G6-P23 FAILED — AUTHORED TERRAIN (P2a / P3)"
    elif not P["P4 FairyLight"]:
        verdict = "G6-P23 FAILED — FAIRYLIGHT (P4)"
    elif not (P["P5 exit and cleanup"] and P["P6 safety"]):
        verdict = "G6-P23 FAILED — EXIT / SAFETY (P5 / P6)"
    elif all(P[k] for k in others) and not observed_f:
        verdict = "G6-P23 PARTIAL — FAIRYLIGHT READBACK GAP"
    else:
        verdict = "G6-P23 FAILED — FAIRYLIGHT READBACK MISMATCH (P2b)"
    res = {"P": P, "verdict": verdict, "details": {**j["details"], **det}}
    jdump(f"judgement_g6p23_{tag}.json", res)
    print(json.dumps({"P": P, "verdict": verdict, "P2": det["P2a"] | {"fairy": det["P2b"]},
                      "P3": j["details"].get("P3")}, indent=1, default=str))
    return 0 if verdict.startswith("G6-P23 VERIFIED") else 1


if __name__ == "__main__":
    cmd = sys.argv[1:]
    if cmd == ["preflight"]:
        sys.exit(preflight())
    if cmd == ["negtest"]:
        sys.exit(negtest())
    if len(cmd) == 2 and cmd[0] == "run":
        sys.exit(run(cmd[1]))
    if len(cmd) == 2 and cmd[0] == "judge":
        sys.exit(judge(cmd[1]))
    print(__doc__)
    sys.exit(2)
