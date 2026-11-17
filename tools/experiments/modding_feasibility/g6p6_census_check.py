#!/usr/bin/env python3
"""E-492 (D-259) G6-P6: calibration, holdout and T1-T10 for tools/actor_pointer_census.py. Offline; read-only.

  g6p6_census_check.py calibrate     C1-C4: the census's proposals for the four verified source actors against the
                                     compiler's own class maps (the oracle, captured from actor_copy during a real
                                     compile; never an input of the census)
  g6p6_census_check.py holdout       the holdout's first-pass census (run once; the result is kept)
  g6p6_census_check.py tests         T1-T10
Outputs: private/work/e492/.
"""
import contextlib
import hashlib
import json
import os
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TOOLS = ROOT / "tools"
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(HERE))
import r3hd_mods as rm  # noqa: E402
import actor_pointer_census as apc  # noqa: E402
import g5p1_pilot as p1  # noqa: E402
import g6p5_equivalence as g65  # noqa: E402

WORK = ROOT / "private" / "work" / "e492"
GAME = g65.GAME
p1.WORK = WORK
CASES = {   # case -> (op in g6p5's OPS, level, model, instance)
    "C1": ("lum", "intro_10", rm.LUM10, 6),
    "C2": ("frog", "intro_10", rm.FROG10, 2),
    "C3": ("fairy", "intro_20", rm.FAIRY20, 2),
    "C4": ("manager", "intro_10", rm.GM10, 0),
}
HOLDOUT = ("intro_10", rm.FLY10, 0)
ORACLE_NAME = {"owned": "owned", "shared": "shared", "other": "other-file", "link": "sibling link"}


def oracle(op):
    """{slot offset: class or 'left-out'} from the compiler's actor_copy call for the verified operation."""
    level, mk, comp, _ = g65.OPS[op]
    orig, box = rm.actor_copy, {}

    def wrap(new, lvl, s, so, fc, segs, cmap, kinds, fail):
        box.update(lvl=lvl, s=s, so=so, segs=segs, kinds=dict(kinds))
        return orig(new, lvl, s, so, fc, segs, cmap, kinds, fail)
    rm.actor_copy = wrap
    try:
        with p1.dev_env(level):
            getattr(rm, comp)(mk(), {"game": GAME})
    finally:
        rm.actor_copy = orig
    so, slots = box["so"], box["s"]["slots"]
    blk = rm.__dict__[{"lum": "LUM_ALLOW", "frog": "FROG_ALLOW", "fairy": "FAIRY_ALLOW",
                       "manager": "GMGR_ALLOW"}[op]][level]["block"]
    out = {}
    for o in range(so, so + blk, 4):
        if o not in slots:
            continue
        if not any(so + a <= o < so + b for a, b, _ in box["segs"]):
            out[o] = "left-out"
            continue
        k = box["kinds"][o]
        out[o] = "reference" if isinstance(k, tuple) else ORACLE_NAME[k]
    return out, blk


def judge(rows, orc):
    """Per-slot comparison. incorrect = a confident proposal that differs from the oracle's class; on a left-out slot
    (not copied by the verified operation) a confident proposal is reported, and is UNSAFE if it would modify the word
    (owned / sibling link / reference)."""
    res = {"agree": [], "unknown": [], "conflicting": [], "incorrect": [], "left_out_keep": [], "left_out_unsafe": [],
           "left_out_unknown": []}
    for r in rows:
        o, p, want = r["offset"], r["proposal"], orc.get(r["offset"])
        tag = {"field": r["field"], "proposal": p, "oracle": want}
        if want == "left-out":
            (res["left_out_unknown"] if p in ("UNKNOWN", "CONFLICTING") else
             res["left_out_unsafe"] if p in ("owned", "sibling link", "reference") else res["left_out_keep"]).append(tag)
        elif p == "UNKNOWN":
            res["unknown"].append(tag)
        elif p == "CONFLICTING":
            res["conflicting"].append(tag)
        elif p == want:
            res["agree"].append(tag)
        else:
            res["incorrect"].append(tag)
    return res


def calibrate():
    WORK.mkdir(parents=True, exist_ok=True)
    out, ok = {}, True
    for case, (op, level, model, inst) in CASES.items():
        c = apc.census(GAME, level, model, inst)
        orc, blk = oracle(op)
        j = judge(c["rows"], orc)
        scope_ok = c["scope"] == [c["superobject"], c["superobject"] + blk]
        enumerated = sorted(r["offset"] for r in c["rows"]) == sorted(orc)
        copied = sum(v != "left-out" for v in orc.values())
        out[case] = {"op": op, "total": c["total"], "counts": c["counts"], "coverage": c["coverage"],
                     "scope_equals_verified_block": scope_ok, "enumeration_equals_oracle": enumerated,
                     "copied_slots": copied, "agree": len(j["agree"]), "unknown": len(j["unknown"]),
                     "conflicting": len(j["conflicting"]), "incorrect": j["incorrect"],
                     "left_out": {k: len(j[k]) for k in ("left_out_keep", "left_out_unsafe", "left_out_unknown")},
                     "left_out_unsafe": j["left_out_unsafe"],
                     "oracle_classes": {k: sum(v == k for v in orc.values()) for k in sorted(set(orc.values()))},
                     "unknown_fields": [f"+{t['field']:#x}:{t['oracle']}" for t in j["unknown"]]}
        ok &= scope_ok and enumerated and not j["incorrect"] and not j["left_out_unsafe"] and not j["conflicting"]
    res = {"pass": ok, "cases": out}
    (WORK / "calibration.json").write_text(json.dumps(res, indent=1) + "\n")
    for case, v in out.items():
        print(case, v["op"], "total", v["total"], "agree", v["agree"], "unknown", v["unknown"], "conflicting",
              v["conflicting"], "incorrect", len(v["incorrect"]), "left-out", v["left_out"], "scope",
              v["scope_equals_verified_block"], "enum", v["enumeration_equals_oracle"])
    print("CALIBRATION_G6P6", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def holdout(name="holdout_first_pass.json"):
    p = WORK / name
    if p.exists():
        print("the holdout's first pass already exists (kept, never rerun over):", p)
        return 1
    WORK.mkdir(parents=True, exist_ok=True)
    level, model, inst = HOLDOUT
    c = apc.census(GAME, level, model, inst)
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout
    tool_sha = hashlib.sha256((TOOLS / "actor_pointer_census.py").read_bytes()).hexdigest()
    with open(p, "x", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps({"head": head.strip(), "tool_sha256": tool_sha, "census": c}, indent=1, sort_keys=True)
                 + "\n")
    print(apc.summary(c))
    return 0


# --- T1-T10 -----------------------------------------------------------------------------------------------------------

def file_hashes(level):
    lvl, ptr, _ = rm.script_level_files(GAME, level)
    ps = [lvl, ptr, lvl.with_name("transit.lvl"), GAME / "GAMEDATAbin" / "fix.lvl"]
    return {str(q.name): (hashlib.sha256(q.read_bytes()).hexdigest(), q.stat().st_mtime_ns) for q in ps}


def tests():
    WORK.mkdir(parents=True, exist_ok=True)
    T, det = {}, {}
    before = {lv: file_hashes(lv) for lv in ("intro_10", "intro_20")}
    cens = {case: apc.census(GAME, lv, m, i) for case, (_, lv, m, i) in CASES.items()}
    # T1 complete enumeration: every relocated word of the scope exactly once (independent scan of the .ptr)
    t1 = {}
    for case, c in cens.items():
        L = apc.load_level(GAME, c["level"])
        ptr = L["data"]["ptr"]
        n = struct.unpack_from(">I", ptr, 0)[0]
        locs = [struct.unpack_from(">iI", ptr, 4 + 8 * i)[1] + 4 for i in range(n)]
        want = sorted(o for o in locs if c["scope"][0] <= o < c["scope"][1])
        got = [r["offset"] for r in c["rows"]]
        t1[case] = got == want and len(set(got)) == len(got)
    T["T1_enumeration"] = all(t1.values())
    det["T1"] = t1
    # T2 address mapping: own-file targets inside the level, region consistent; other-file targets inside that file
    t2 = {}
    for case, c in cens.items():
        sz = {r: c["resources"][r]["size"] for r in c["resources"]}
        ok = True
        for r in c["rows"]:
            if r["target"] is None:
                continue
            if r["file"] == 1:
                ok &= 0 <= r["target"] < sz["lvl"] and r["target_resource"] == f"{c['level']}.lvl" \
                    and (r["region"] == "outside block") == (not c["scope"][0] <= r["target"] < c["scope"][1])
            else:
                ok &= 0 <= r["target"] < sz["fix" if r["file"] == 0 else "transit"]
        t2[case] = ok
    T["T2_address_mapping"] = all(t2.values())
    det["T2"] = t2
    # T3 conservative: nothing authorizes compilation; the compiler has no path from census output to a class map
    src = (TOOLS / "r3hd_mods.py").read_text(encoding="utf-8")
    T["T3_no_authorization"] = all(c["authorizes_compilation"] is False for c in cens.values()) \
        and "actor_pointer_census" not in src
    # T4 calibration
    q = subprocess.run([sys.executable, str(Path(__file__)), "calibrate"], capture_output=True, text=True)
    T["T4_calibration"] = q.returncode == 0
    det["T4"] = q.stdout.strip().splitlines()[-6:]
    # T5 unknown handling: an unmapped target and an evidence-free in-block target stay UNKNOWN (synthetic rows
    # through the same rule engine), and every real UNKNOWN row carries a note or has no candidates
    T["T5_unknown"], det["T5"] = synthetic_rules("unknown")
    # T6 conflicting evidence: two rules for incompatible classes -> CONFLICTING, never a priority pick
    T["T6_conflicting"], det["T6"] = synthetic_rules("conflict")
    # T7 resource protection: hashes and mtimes unchanged after every census; the tool opens nothing for writing
    for case, (_, lv, m, i) in CASES.items():
        apc.census(GAME, lv, m, i)
    after = {lv: file_hashes(lv) for lv in ("intro_10", "intro_20")}
    tool = (TOOLS / "actor_pointer_census.py").read_text(encoding="utf-8")
    T["T7_resource_protection"] = before == after and "write_bytes" not in tool and "\"wb\"" not in tool \
        and "'wb'" not in tool
    # T8 determinism: two runs (fresh processes) give identical JSON
    runs = []
    for _ in range(2):
        r = subprocess.run([sys.executable, str(TOOLS / "actor_pointer_census.py"), "--level", "intro_10", "--model",
                            "NIK_mGenManager", "--instance", "0", "--json", "-"], capture_output=True, text=True)
        runs.append(r.stdout)
    T["T8_deterministic"] = runs[0] == runs[1] and json.loads(runs[0])["total"] > 0 and \
        json.dumps(apc.census(GAME, "intro_10", rm.GM10, 0), indent=1, sort_keys=True) == runs[0].strip()
    # T9 CLI validation
    def cli(*args, env=None):
        e = dict(os.environ, **(env or {}))
        r = subprocess.run([sys.executable, str(TOOLS / "actor_pointer_census.py"), *args], capture_output=True,
                           text=True, env=e)
        return r.returncode, r.stderr.strip()
    fake = WORK / "fake_game"
    import shutil
    if fake.exists():
        shutil.rmtree(fake)
    (fake / "GAMEDATAbin" / "intro_10").mkdir(parents=True)
    src10 = GAME / "GAMEDATAbin" / "intro_10"
    for nm in ("intro_10.lvl", "intro_10.ptr"):
        shutil.copyfile(src10 / nm, fake / "GAMEDATAbin" / "intro_10" / nm)
    shutil.copyfile(GAME / "GAMEDATAbin" / "fix.lvl", fake / "GAMEDATAbin" / "fix.lvl")
    t9 = {"unsupported_level": cli("--level", "intro_15", "--model", "x", "--instance", "0"),
          "unknown_model": cli("--level", "intro_10", "--model", "NO_SUCH_MODEL", "--instance", "0"),
          "ambiguous_model": cli("--level", "intro_10", "--model", "NIK_m", "--instance", "0"),
          "bad_instance": cli("--level", "intro_10", "--model", "NIK_mGenSound", "--instance", "9"),
          "missing_file": cli("--level", "intro_10", "--model", "NIK_mGenSound", "--instance", "0", "--game", str(fake))}
    tl = fake / "GAMEDATAbin" / "intro_10" / "transit.lvl"
    b = bytearray((src10 / "transit.lvl").read_bytes())
    b[0x100] ^= 1
    tl.write_bytes(bytes(b))
    t9["wrong_hash"] = cli("--level", "intro_10", "--model", "NIK_mGenSound", "--instance", "0", "--game", str(fake))
    t9["output_outside_private"] = cli("--level", "intro_10", "--model", "NIK_mGenSound", "--instance", "0", "--json",
                                       str(ROOT / "census.json"))
    t9["output_in_game_dir"] = cli("--level", "intro_10", "--model", "NIK_mGenSound", "--instance", "0", "--json",
                                   str(GAME / "x.json"))
    existing = WORK / "exists.json"
    existing.write_text("{}")
    t9["output_exists"] = cli("--level", "intro_10", "--model", "NIK_mGenSound", "--instance", "0", "--json",
                              str(existing))
    shutil.rmtree(fake)
    want9 = {"unsupported_level": "UNSUPPORTED", "unknown_model": "UNSUPPORTED", "ambiguous_model": "UNSUPPORTED",
             "bad_instance": "UNSUPPORTED", "missing_file": "TARGET_MISSING", "wrong_hash": "TARGET_CHANGED",
             "output_outside_private": "UNSAFE_OUTPUT", "output_in_game_dir": "UNSAFE_OUTPUT",
             "output_exists": "UNSAFE_OUTPUT"}
    T["T9_cli_validation"] = all(t9[k][0] == 2 and f"REFUSED {v}" in t9[k][1] for k, v in want9.items()) \
        and existing.read_text() == "{}" and not (ROOT / "census.json").exists() and not (GAME / "x.json").exists()
    det["T9"] = {k: v[1][:120] for k, v in t9.items()}
    # T10 compiler isolation: G6-P5's frozen equivalence, compiler file unchanged since ff076ad except G6-P7's one
    # documented additive script-index key (D-260: ix["headers"], read-only consumers), header unchanged, gate production
    hdr = subprocess.run(["git", "diff", "--quiet", "ff076ad", "--", "tools/m33_mod_overlay.h"], cwd=ROOT).returncode
    lines = [ln for ln in subprocess.run(["git", "diff", "-U0", "ff076ad", "--", "tools/r3hd_mods.py"], cwd=ROOT,
                                         capture_output=True, text=True).stdout.splitlines()
             if ln[:1] in "+-" and not ln.startswith(("+++", "---"))]
    allowed = ['-    ix = {"lvl": lvl_p, "data": lvl, "slots": slots, "behaviours": behaviours}',
               '+    ix = {"lvl": lvl_p, "data": lvl, "slots": slots, "behaviours": behaviours,',
               '+          "headers": headers}   # G6-P7 (D-260): behaviour-list headers {header offset: names}, '
               'read-only consumers']
    # G6-P8 (D-261): the compiler then gained the typed insert-toad-intro (commit a1a7c97: G6-P7's key + the D-261
    # operation, additive except one extended override-type tuple); the census still never edits it: the file must
    # equal either the G6-P7 state above or exactly a1a7c97's
    g6p8 = subprocess.run(["git", "diff", "--quiet", "a1a7c97", "--", "tools/r3hd_mods.py"], cwd=ROOT).returncode
    # G6-P9 (D-262): or exactly the compiler of commit 51276fe (the development-only insert-toad-intro-pair, additive
    # except two default-preserving keyword parameters and one extended override-type tuple)
    g6p9 = subprocess.run(["git", "diff", "--quiet", "51276fe", "--", "tools/r3hd_mods.py"], cwd=ROOT).returncode
    # G6-P11 (D-264): or exactly the compiler of commit 29023bc (the development-only insert-lum-toad-pair, additive
    # except one extended override-type tuple and the manifest / compile dispatch entries)
    g6p11 = subprocess.run(["git", "diff", "--quiet", "29023bc", "--", "tools/r3hd_mods.py"], cwd=ROOT).returncode
    diff = 0 if hdr == 0 and ([ln.rstrip("\r") for ln in lines] in ([], allowed) or 0 in (g6p8, g6p9, g6p11)) else 1
    gate = subprocess.run([sys.executable, str(HERE / "g5p1_dev_gate.py"), "status"], capture_output=True,
                          text=True).stdout.strip().splitlines()[-1:]
    eq = subprocess.run([sys.executable, str(HERE / "g6p5_equivalence.py"), "compare"], capture_output=True, text=True)
    T["T10_compiler_isolation"] = diff == 0 and gate == ["production"] and eq.returncode == 0
    det["T10"] = {"compiler_and_header_unchanged": diff == 0, "gate": gate,
                  "g6p5_compare": eq.stdout.strip().splitlines()[-1:]}
    out = {"pass": all(T.values()), "T": T, "details": det}
    (WORK / "tests.json").write_text(json.dumps(out, indent=1, default=str) + "\n")
    print(json.dumps(T, indent=1))
    print("TESTS_G6P6", "PASS" if out["pass"] else "FAIL")
    return 0 if out["pass"] else 1


def synthetic_rules(kind):
    """Synthetic levels for the census's rule engine (no game data): census() run on a fabricated, self-consistent
    file set through a stubbed script index and allow-list, restored afterwards."""
    import tempfile
    with tempfile.TemporaryDirectory(dir=str(WORK)) as td:
        game = Path(td)
        g = game / "GAMEDATAbin" / "lv_s"
        g.mkdir(parents=True)
        # level layout: header word 0 = cross count 0; SO-record list header at 0x200 (named by 0x1CFC);
        # two records -> actors A (0x1000) and B (0x1100), a terminator actor C at 0x1200
        lvl = bytearray(0x2000)
        slots = {}

        def ptr_(o, t, f=1):
            struct.pack_into(">I", lvl, o, t - 4)
            slots[o] = f
        A, B, C = 0x1000, 0x1100, 0x1200
        ptr_(apc.RECORDS_REF, 0x200)
        ptr_(0x200, 0x300)            # first record
        for i, (r, so) in enumerate(((0x300, A), (0x320, B), (0x340, C))):
            if i < 2:
                ptr_(r, r + 0x20)
            ptr_(r + 4, so)
        if kind == "unknown":
            ptr_(A + 0x40, A + 0x80)  # in-block target, no evidence -> UNKNOWN
            struct.pack_into(">I", lvl, A + 0x44, 0x7FFFFFF0)   # own-file slot pointing outside the level
            slots[A + 0x44] = 1
            ptr_(B + 0x40, B + 0x90)  # the peer points elsewhere (disagreement)
        else:
            # a decoded model-descriptor field (Mind+0, R-chain-model: shared) whose peer points to the same relative
            # place inside its own block (R-peer-own: owned): two credible rules, incompatible classes
            for so in (A, B):
                ptr_(so + 4, so + 0x80)      # Perso
                ptr_(so + 0x8C, so + 0x90)   # Perso+0xC -> Brain
                ptr_(so + 0x90, so + 0xA0)   # Brain+0 -> Mind
                ptr_(so + 0xA0, so + 0xC0)   # Mind+0 -> "AI model", here inside the block
        ents = sorted(slots.items())
        ptrb = struct.pack(">I", len(ents)) + b"".join(struct.pack(">iI", f, o - 4) for o, f in ents)
        (g / "lv_s.lvl").write_bytes(bytes(lvl))
        (g / "lv_s.ptr").write_bytes(ptrb)
        (g / "transit.lvl").write_bytes(bytes(0x40))
        (game / "GAMEDATAbin" / "fix.lvl").write_bytes(bytes(0x40))
        saved_allow, saved_ix = dict(rm.STRUCT_ALLOW), rm.read_script_index
        saved_lum = dict(rm.LUM_ALLOW)
        try:
            rm.STRUCT_ALLOW["lv_s"] = {"lvl": (len(lvl), hashlib.sha256(bytes(lvl)).hexdigest()),
                                       "ptr": (len(ptrb), hashlib.sha256(ptrb).hexdigest())}
            rm.LUM_ALLOW["lv_s"] = {"transit": (0x40, hashlib.sha256(bytes(0x40)).hexdigest())}
            rm.read_script_index = lambda game_, level_: {
                "data": bytes(lvl), "placements": {"SYN_MODEL": [{"so": A, "safe": ""}, {"so": B, "safe": ""}]},
                "defaults": {}}
            c = apc.census(game, "lv_s", "SYN_MODEL", 0)
        finally:
            rm.STRUCT_ALLOW.clear()
            rm.STRUCT_ALLOW.update(saved_allow)
            rm.LUM_ALLOW.clear()
            rm.LUM_ALLOW.update(saved_lum)
            rm.read_script_index = saved_ix
    rows = {r["field"]: r for r in c["rows"]}
    if kind == "unknown":
        ok = rows[0x40]["proposal"] == "UNKNOWN" and rows[0x44]["proposal"] == "UNKNOWN" \
            and rows[0x44]["target"] is None and any("unmapped" in n for n in rows[0x44]["notes"])
        return ok, {f"+{k:#x}": (r["proposal"], r["notes"]) for k, r in rows.items()}
    r = rows[0xA0]
    ok = r["proposal"] == "CONFLICTING" and set(r["candidates"]) == {"owned", "shared"} \
        and {e["rule"] for v in r["candidates"].values() for e in v} == {"R-chain-model", "R-peer-own"}
    return ok, {"+0xa0": (r["proposal"], sorted(r["candidates"]), r["notes"])}


def main():
    a = sys.argv[1:]
    if a == ["calibrate"]:
        return calibrate()
    if a == ["holdout"]:
        return holdout()
    if a == ["holdout-revision1"]:   # after the first pass is kept: the same actor with revision 1 (larger graph decode)
        return holdout("holdout_revision1.json")
    if a == ["tests"]:
        return tests()
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
