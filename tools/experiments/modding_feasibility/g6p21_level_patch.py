#!/usr/bin/env python3
"""E-510 (D-277) G6-P21: declarative multi-component level authoring (`level-patch-v1`). Offline only; private outputs.

    g6p21_level_patch.py check      O1-O5 (schema, G6-P20 byte equivalence, canonicalization + graph-B variation,
                                    independent combined final-image checker incl. corrupted plans, regressions)
Outputs: private/work/e510/ (numbers only).

level-patch-v1 is a thin typed adapter over the unchanged G6-P20 compiler (compile_insert_fairy_with_terrain): a JSON
document names the owning mod id, the exact intro_20 source hashes and exactly one terrain component (preset
start-two-step-v1) + exactly one fairylight component (follow_graph_of 0 = graph A 0x3226A8, 1 = graph B 0x335660).
Examples: level_patch_examples/g6p20_reference.json (= G6-P20's runtime-verified mod) and graph_b.json.

Equivalence reference: the plan G6-P20 run m1 used (private/work/e509/m1/M/plan_copy.txt) and its range blobs, plus the
fixed operation compiled now. The combined final-image checker is G6-P20's `final_check` (independent of the compiler:
G6-P3's constructor and loader simulator, the standalone G6-P19 preset bytes, terrain geometry re-checked), run with its
selector / mod id set to the declaration's. No game run: the reference output is byte-identical to a verified run.
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1]))
import r3hd_mods as rm  # noqa: E402
import g6p20_fairy_terrain as g20  # noqa: E402

g3, p1 = g20.g3, g20.p1
ROOT, TOOLS, GAME = g20.ROOT, g20.TOOLS, g20.GAME
WORK = ROOT / "private" / "work" / "e510"
g3.WORK = WORK
LEVEL = "intro_20"
EX = HERE / "level_patch_examples"
REF_PLAN = ROOT / "private" / "work" / "e509" / "m1" / "M" / "plan_copy.txt"
REF_ID = "1b1f404eaf81a240"
REF_RESULTS = {"lvl": "4507437c0877ef21c933eec3aef72b64d558e9b5f26c2ef5dfbbcc0a0d267eda",
               "ptr": "40934d08eeed74d87eb0dd385d82a7382cce6e2c53166083741be16d5ee8979c",
               "transit": "2be9a434eed49c9625efe0462a67510216813aff7edc3e75e4e083bff3a0a7e4"}


def doc(name):
    return json.loads((EX / name).read_text(encoding="utf-8"))


def plan(name, patch):
    """Import a mod whose only override is the level-patch (mod id = the patch id) and write its plan."""
    return g3.compile_plan(name, [(patch["id"], [{"type": "level-patch", "patch": patch}])])


def body(text):
    """Plan lines without the timestamp comment, range blob paths replaced by their bytes' SHA-256."""
    out = []
    for ln in text.splitlines():
        if ln.startswith("#"):
            continue
        if ln.startswith("range "):
            head, blob = ln.rsplit(" ", 1)
            ln = f"{head} sha256={rm.sha256_bytes(Path(blob).read_bytes())}"
        out.append(ln)
    return out


def final(text, sel, mid):
    old = (g20.SEL, g20.MID)
    g20.SEL, g20.MID = sel, mid
    try:
        return g20.final_check(text)
    finally:
        g20.SEL, g20.MID = old


def cli(args, env_level, out=None):
    env = dict(os.environ)
    env.pop(rm.STRUCT_ENV, None)
    if env_level:
        env[rm.STRUCT_ENV] = env_level
    cmd = [sys.executable, "-I", str(TOOLS / "r3hd_mods.py"), *args, "--game-dir", str(GAME), "--json"]
    if out:
        cmd += ["--out", str(out)]
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, env=env)
    try:
        return r.returncode, json.loads(r.stdout)
    except ValueError:
        return r.returncode, {"raw": r.stdout[-400:], "err": r.stderr[-400:]}


def check():
    WORK.mkdir(parents=True, exist_ok=True)
    O, det = {}, {}
    A, B = doc("g6p20_reference.json"), doc("graph_b.json")
    P = {"game": GAME}
    ref = lambda fn, code, env=LEVEL: g3.refused(fn, code, env)   # noqa: E731

    # O1 schema and resource safety (valid compile via the CLI; refusals leave no output)
    o1 = {}
    tmp = WORK / "cli"
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)
    rc_a, out_a = cli(["level-patch", str(EX / "g6p20_reference.json")], LEVEL, tmp / "mod_a")
    rc_b, out_b = cli(["level-patch", str(EX / "graph_b.json")], LEVEL, tmp / "mod_b")
    det["cli_a"], det["cli_b"] = out_a, out_b
    o1["CLI compiles the reference (exit 0, mod folder written)"] = rc_a == 0 and (tmp / "mod_a" / "mod.json").is_file()
    o1["CLI compiles graph B (exit 0, mod folder written)"] = rc_b == 0 and (tmp / "mod_b" / "mod.json").is_file()
    o1["CLI summary: 63 ranges (13 fairy + 50 terrain), growth +2892 / +408 / 0, id 1b1f404eaf81a240"] = (
        out_a.get("range_count") == 63 and out_a.get("fairylight_ranges") == 13 and out_a.get("terrain_ranges") == 50
        and out_a.get("growth") == {"lvl": 2892, "ptr": 408, "transit": 0}
        and out_a.get("transaction", {}).get("id") == REF_ID)
    bads = {
        "wrong level": (dict(A, level="intro_15"), "UNSUPPORTED"),
        "wrong lvl hash": (dict(A, lvl_sha256="0" * 64), "UNSUPPORTED"),
        "wrong ptr hash": (dict(A, ptr_sha256="1" * 64), "UNSUPPORTED"),
        "unsupported version": (dict(A, format="level-patch-v2"), "UNSUPPORTED"),
        "duplicate terrain": (dict(A, components=[A["components"][0]] * 2 + [A["components"][1]]), "BAD_MANIFEST"),
        "duplicate fairylight": (dict(A, components=A["components"] + [A["components"][1]]), "BAD_MANIFEST"),
        "missing terrain": (dict(A, components=[A["components"][1]]), "BAD_MANIFEST"),
        "missing fairylight": (dict(A, components=[A["components"][0]]), "BAD_MANIFEST"),
        "third component": (dict(A, components=A["components"] + [{"type": "fairylight", "follow_graph_of": 1}]),
                            "BAD_MANIFEST"),
        "unknown component": (dict(A, components=A["components"] + [{"type": "toad"}]), "UNSUPPORTED"),
        "unsupported graph (follow_graph_of 2)": (dict(A, components=[A["components"][0],
                                                                       {"type": "fairylight", "follow_graph_of": 2}]),
                                                  "UNSUPPORTED"),
        "unsupported terrain preset": (dict(A, components=[{"type": "terrain", "preset": "spawn-multi-surface-v1"},
                                                           A["components"][1]]), "UNSUPPORTED"),
        "unknown top-level key (offset)": (dict(A, offset=4096), "BAD_MANIFEST"),
        "unknown component key (address)": (dict(A, components=[A["components"][0],
                                                                 dict(A["components"][1], address=0x3226A8)]),
                                            "BAD_MANIFEST"),
        "missing key (transit_sha256)": ({k: v for k, v in A.items() if k != "transit_sha256"}, "BAD_MANIFEST"),
        "bad mod id": (dict(A, id="G6P20 fairy"), "BAD_MANIFEST"),
    }
    neg = {}
    for i, (name, (p, code)) in enumerate(bads.items()):
        f = tmp / f"bad_{i}.json"
        f.write_text(json.dumps(p), encoding="utf-8")
        rc, out = cli(["level-patch", str(f)], LEVEL, tmp / f"out_bad_{i}")
        neg[name] = rc == 2 and out.get("code") == code and not (tmp / f"out_bad_{i}").exists() \
            and ref(lambda p=p: rm.compile_level_patch(p, P), code) is True
    f = tmp / "dup_keys.json"
    f.write_text(json.dumps(A)[:-1] + ', "level": "intro_20"}', encoding="utf-8")
    rc, out = cli(["level-patch", str(f)], LEVEL, tmp / "out_dup")
    neg["duplicate JSON key"] = rc == 2 and out.get("code") == "BAD_MANIFEST" and not (tmp / "out_dup").exists()
    o1["refusals (CLI exit 2 with the expected code, no output folder; library refuses the same)"] = all(neg.values())
    det["O1_refusals"] = neg
    O["O1"] = all(o1.values())
    det["O1"] = o1

    # O2 G6-P20 byte equivalence
    o2 = {}
    res_a, text_a, _ = plan("decl_a", A)
    det["resolve_a"] = {"active": res_a.get("active"), "structural_active": res_a.get("structural_active")}
    ref_text = REF_PLAN.read_text(encoding="utf-8")
    ba, br = body(text_a), body(ref_text)
    o2["plan = retained G6-P20 run plan (all lines; range blobs by content)"] = ba == br
    if ba != br:
        det["plan_diff"] = [(x, y) for x, y in zip(ba, br) if x != y][:6] + [("lengths", len(ba), len(br))]
    m_a = p1.parse_plan(text_a)
    o2["level-tx line = 2 intro_20 g6p20.fairy-terrain 1b1f404eaf81a240"] = m_a["txs"] == [
        f"level-tx 2 {LEVEL} g6p20.fairy-terrain {REF_ID}"]
    o2["member results = committed G6-P20 values"] = {f["tx"][0].split(" ")[0]: f["tx"][0].split(" ")[3]
                                                      for f in m_a["files"]} == REF_RESULTS
    o2["images = retained run plan images"] = p1.images(m_a) == p1.images(p1.parse_plan(ref_text))
    with p1.dev_env(LEVEL):
        canon, r_decl, tx_decl = rm.compile_level_patch(A, P)
        r_fix, tx_fix = rm.compile_insert_fairy_with_terrain(g20.op(), P)
    o2["ranges = fixed operation's (file, offset, bytes, label, order), 63"] = r_decl == r_fix and len(r_decl) == 63
    o2["transaction (files, images, version, same-size, info) = fixed operation's"] = tx_decl == tx_fix
    o2["the selected operation = G6-P20's manifest operation"] = rm.level_patch_operation(canon) == g20.op()
    o2["transaction_summary id / results = plan"] = rm.transaction_summary(A["id"], tx_decl)["id"] == REF_ID
    labels = [r[3] for r in r_decl]
    o2["13 fairy + 50 terrain ranges"] = sum(".terrain." in x for x in labels) == 50 and len(labels) - 50 == 13
    fa = final(text_a, "a", A["id"])
    det["final_a"] = fa
    O["O2"] = all(o2.values())
    det["O2"] = o2

    # O3 canonicalization and authoring variation
    o3 = {}
    A2 = dict(A, components=list(reversed(A["components"])))
    A3 = json.loads(json.dumps(A, sort_keys=True))
    A3.pop("description")
    with p1.dev_env(LEVEL):
        c1, c2, c3 = (rm.parse_level_patch(x, "o") for x in (A, A2, A3))
    o3["reordered components -> same canonical form and identity"] = c1 == c2 \
        and rm.level_patch_identity(c1) == rm.level_patch_identity(c2)
    o3["key order / description -> same identity"] = rm.level_patch_identity(c1) == rm.level_patch_identity(c3)
    res_r, text_r, _ = plan("decl_a_reordered", A2)
    o3["reordered plan = reference plan"] = body(text_r) == ba
    res_b, text_b, _ = plan("decl_b", B)
    det["resolve_b"] = {"active": res_b.get("active"), "structural_active": res_b.get("structural_active")}
    m_b = p1.parse_plan(text_b) if text_b else None
    with p1.dev_env(LEVEL):
        cb, r_b, tx_b = rm.compile_level_patch(B, P)
        r_bfix, tx_bfix = rm.compile_insert_fairy_with_terrain(g20.op(follow_graph_of=1), P)
    o3["graph B selects follow_graph_of 1 and = the fixed operation with follow_graph_of 1"] = (
        rm.level_patch_operation(cb)["follow_graph_of"] == 1 and r_b == r_bfix and tx_b == tx_bfix)
    o3["graph B: distinct declaration identity"] = rm.level_patch_identity(cb) != rm.level_patch_identity(c1)
    ia, ib = tx_decl["images"], tx_b["images"]
    diff = [i for i in range(len(ia["lvl"])) if ia["lvl"][i] != ib["lvl"][i]]
    o3["graph B vs A: same lengths, ptr and transit equal"] = all(len(ia[k]) == len(ib[k]) for k in ia) \
        and ia["ptr"] == ib["ptr"] and ia["transit"] == ib["transit"]
    words = sorted({(i - (i - len(g3.files()[0])) % 4) for i in diff})
    gw = {rm._u32(ib["lvl"], w) for w in words}, {rm._u32(ia["lvl"], w) for w in words}
    o3["graph B vs A: lvl differs only in the appended copy's two variable-2 words (B -> 0x335660, A -> 0x3226A8)"] = (
        bool(diff) and min(diff) >= len(g3.files()[0]) and len(words) == 2
        and gw[0] == {0x335660 - 4} and gw[1] == {0x3226A8 - 4})
    det["graph_b_vs_a"] = {"changed_bytes": len(diff), "words": [hex(w) for w in words],
                           "values_b": sorted(hex(x) for x in gw[0]), "values_a": sorted(hex(x) for x in gw[1])}
    o3["graph B: different transaction id and lvl result"] = m_b is not None and m_b["txs"][0].split(" ")[4] != REF_ID \
        and rm.transaction_summary(B["id"], tx_b)["members"]["lvl"]["result_sha256"] != REF_RESULTS["lvl"]
    det["graph_b_tx"] = rm.transaction_summary(B["id"], tx_b)
    O["O3"] = all(o3.values())
    det["O3"] = o3

    # O4 combined-final-resource integrity (independent checker on both; corrupted plans refused)
    fb = final(text_b, "b", B["id"]) if text_b else {"ok": False}
    det["final_b"] = fb
    o4 = {"checker: reference (graph A)": bool(fa.get("ok")), "checker: graph B": bool(fb.get("ok"))}
    li = next(i for i, f in enumerate(m_a["files"]) if f["path"].endswith(f"{LEVEL}.lvl"))
    ter = {o for o, _, _ in g20.terrain_edits()}
    cdir = WORK / "corrupt"
    if cdir.exists():
        shutil.rmtree(cdir)
    cdir.mkdir(parents=True)

    def corrupt(name, fn):
        m = json.loads(json.dumps(m_a))
        fn(m)
        return not final(p1.emit(m), "a", A["id"]).get("ok")

    def flip(m, pick):
        for k, r in enumerate(m["files"][li]["range"]):
            off, length, gb, nb, mid, blob = r.split(" ", 5)
            if pick(int(off)):
                b = bytearray(Path(blob).read_bytes())
                b[0] ^= 1
                q = cdir / f"blob_{off}.bin"
                q.write_bytes(bytes(b))
                m["files"][li]["range"][k] = " ".join([off, length, gb, nb, mid, str(q)])
                return
    o4["corrupted terrain byte refused"] = corrupt("t", lambda m: flip(m, lambda o: o in ter))
    o4["corrupted fairy word refused"] = corrupt("f", lambda m: flip(m, lambda o: o not in ter and o < g3.SIZE))
    o4["dropped terrain range refused"] = corrupt("d", lambda m: m["files"][li].update(
        range=[r for r in m["files"][li]["range"] if int(r.split(" ")[0]) != min(ter)]))
    o4["missing transit member refused"] = corrupt("m", lambda m: m["files"].pop(
        next(i for i, f in enumerate(m["files"]) if f["path"].endswith("transit.lvl"))))
    o4["corrupted transaction id refused"] = corrupt("i", lambda m: m.update(
        txs=[m["txs"][0][:-1] + ("0" if m["txs"][0][-1] != "0" else "1")]))
    o4["graph B plan judged as graph A refused (checker is selector-specific)"] = not final(text_b, "a", B["id"]).get("ok")
    O["O4"] = all(o4.values())
    det["O4"] = o4

    # O5 existing behaviour and production isolation
    o5 = {}
    for sel in ("a", "b"):
        _, txs = g3.compiled(sel)
        data, ptr, tl = g3.files()
        cl, cp, ct, _ = g3.construct(data, ptr, tl, sel)
        o5[f"standalone fairy {sel} = independent constructor"] = (txs["images"]["lvl"], txs["images"]["ptr"],
                                                                   txs["images"]["transit"]) == (cl, cp, ct)
    o5["fixed operation insert-fairy-with-terrain still compiles to the G6-P20 id"] = \
        rm.transaction_summary("g6p20.fairy-terrain", tx_fix)["id"] == REF_ID
    lpo = {"type": "level-patch", "patch": A}

    def man(mid, *ovs):
        return lambda: rm.parse_manifest({"mod.json": json.dumps(p1.manifest(mid, list(ovs))).encode()})
    o5["generic fairy + terrain preset mod still refused (D-274)"] = ref(man("t.mix", g3.fairy("a"), g20.g19.op()),
                                                                          "BAD_MANIFEST") is True
    o5["level-patch + fixed composition / fairy / preset / second level-patch refused"] = all(
        ref(man(A["id"], lpo, x), "BAD_MANIFEST") is True for x in (g20.op(), g3.fairy("a"), g20.g19.op(), lpo))
    o5["level-patch whose id is not the mod id refused"] = ref(man("t.other", lpo), "BAD_MANIFEST") is True
    rc, out = cli(["level-patch", str(EX / "g6p20_reference.json")], None, tmp / "out_prod")
    o5["CLI without the development gate refused, nothing written"] = rc == 2 and out.get("code") == "UNSUPPORTED" \
        and not (tmp / "out_prod").exists()
    rc, out = cli(["level-patch", str(EX / "g6p20_reference.json")], "intro_15", tmp / "out_other")
    o5["CLI with the gate naming another level refused, nothing written"] = rc == 2 \
        and out.get("code") == "UNSUPPORTED" and not (tmp / "out_other").exists()
    o5["manifest without the gate refused"] = ref(man(A["id"], lpo), "UNSUPPORTED", env=None) is True
    # an import refused at compile leaves no plan and no active mod
    p1.WORK = WORK
    rp = p1.fresh("refused")
    with p1.dev_env(LEVEL):
        try:
            p1.install(rp, "t.bad", [{"type": "level-patch", "patch": dict(A, id="t.bad", components=[
                A["components"][0], {"type": "fairylight", "follow_graph_of": 2}])}])
            imported = True
        except rm.Refusal as x:
            imported = x.code
        r2 = rm.resolve_all(rp, write_plan=rp["cache"])
    o5["refused level-patch import: no plan, no active mod"] = imported == "UNSUPPORTED" \
        and not (rp["cache"] / rm.PLAN_NAME).is_file() and not r2.get("active")
    o5["CLI --out mod.json imports and plans identically to the reference"] = False
    if (tmp / "mod_a" / "mod.json").is_file():
        mj = json.loads((tmp / "mod_a" / "mod.json").read_text(encoding="utf-8"))
        _, text_c, _ = g3.compile_plan("cli_mod", [(mj["id"], mj["overrides"])])
        o5["CLI --out mod.json imports and plans identically to the reference"] = text_c is not None \
            and body(text_c) == ba
    o5["gameplay-affecting; plan carries the gameplay record"] = rm.changes_game_logic({"overrides": [lpo]}) \
        and f"\ngameplay {A['id']}\n" in text_a
    st = subprocess.run([sys.executable, "-I", str(TOOLS / "r3hd_mods.py"), "selftest"], cwd=ROOT, capture_output=True,
                        text=True)
    o5["r3hd_mods selftest"] = st.stdout.strip().splitlines()[-1] if st.stdout.strip() else st.stderr[-200:]
    o5["selftest pass"] = "PASS" in o5["r3hd_mods selftest"]
    O["O5"] = all(v for v in o5.values() if isinstance(v, bool))
    det["O5"] = o5

    res = {"O": O, "pass": all(O.values()), "details": det}
    (WORK / "offline.json").write_text(json.dumps(res, indent=1, default=str) + "\n")
    print(json.dumps({"O": O, "pass": res["pass"]}, indent=1))
    for k in ("O1", "O2", "O3", "O4", "O5"):
        for n, v in det[k].items():
            if v is False:
                print("FAIL", k, n)
    for n, v in det["O1_refusals"].items():
        if v is not True:
            print("FAIL O1 refusal", n)
    for k in ("final_a", "final_b"):
        for n, v in det[k].items():
            if v is False:
                print("FAIL", k, n)
    return 0 if res["pass"] else 1


if __name__ == "__main__":
    if sys.argv[1:] == ["check"]:
        with p1.dev_env(LEVEL):   # every gate-off / other-level case sets its own environment explicitly
            sys.exit(check())
    print(__doc__)
    sys.exit(2)
