#!/usr/bin/env python3
"""E-491 (D-258) G6-P5: shared actor construction, byte-identical. Offline only; private; no game process.

The four verified structural actor operations (insert-passive-lum, insert-scripted-frog, insert-fairy-on-graph,
insert-gensound-manager) share their construction mechanisms after G6-P5. This harness freezes the pre-refactor
compiler's complete observable output and later compares the refactored compiler against that baseline.

  g6p5_equivalence.py freeze      run the CURRENT compiler over every fixture and write the baseline:
                                  private/work/e491/baseline/ (full JSON plus the compiled images, for byte-level
                                  diffs; never committed) and tools/experiments/modding_feasibility/g6p5_baseline.json
                                  (hashes, counts, offsets and labels only; committed)
  g6p5_equivalence.py compare     E1-E7: the current compiler against the frozen baseline AND against the
                                  baseline compiler itself (git show BASELINE:tools/r3hd_mods.py, loaded under
                                  another module name), byte for byte; writes private/work/e491/compare.json
  g6p5_equivalence.py e8          E8: G6-P4's offline check (independent constructors and simulators O1-O8 of
                                  G6-P4, plus G5-P4a / G6-P1 / G6-P2 / G6-P3 checks it chains), redirected to
                                  private/work/e491/compat/

Fixtures (valid): lum beside_source / flight_path, frog 500 / 2000 ms, fairy follows instance 0 / 1, manager moves
Forest / SmallRiver; plans: those eight single-mod sets plus the two verified exit configurations (the lum with
G6-P1's gen5 designer default, the 2000 ms Frog with G5-P2b's lums-6), each through resolve_all and the plan writer.
Fixtures (negative): manifest parse refusals, compile refusals (gate, level, model, instance, hashes, targets,
presets, missing transit, budget), structural refusals of each builder on mutated copies of the original files or
on altered allow-list facts, and conflict refusals (two structural operations in one mod, an actor with a graph
insertion, two structural mods on one level). Each is recorded with its exact code and detail.
"""
import contextlib
import hashlib
import importlib.util
import json
import shutil
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
import g5p1_pilot as p1  # noqa: E402
import g6p1_pilot as g61  # noqa: E402
import g6p2_pilot as g62  # noqa: E402
import g6p3_pilot as g63  # noqa: E402
import g6p4_pilot as g64  # noqa: E402

PREFIX = "e491"
WORK = ROOT / "private" / "work" / PREFIX
BASE = WORK / "baseline"
PUBLIC = HERE / "g6p5_baseline.json"
BASELINE = "89e836d"
p1.WORK = WORK
GAME = g64.GAME


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def jsha(o) -> str:
    return sha(json.dumps(o, sort_keys=True, default=str).encode())


@contextlib.contextmanager
def env(level):
    with p1.dev_env(level):
        yield


# --- fixtures --------------------------------------------------------------------------------------------------------

def valid_fixtures():
    """name -> (level, manifest, compile function name)."""
    return {
        "lum.beside_source": ("intro_10", g61.lum("off"), "compile_insert_passive_lum"),
        "lum.flight_path": ("intro_10", g61.lum("on"), "compile_insert_passive_lum"),
        "frog.500": ("intro_10", g62.frog(500), "compile_insert_scripted_frog"),
        "frog.2000": ("intro_10", g62.frog(2000), "compile_insert_scripted_frog"),
        "fairy.0": ("intro_20", g63.fairy("a"), "compile_insert_fairy_on_graph"),
        "fairy.1": ("intro_20", g63.fairy("b"), "compile_insert_fairy_on_graph"),
        "manager.forest": ("intro_10", g64.manager(0), "compile_insert_gensound_manager"),
        "manager.smallriver": ("intro_10", g64.manager(1), "compile_insert_gensound_manager"),
    }


def plan_fixtures():
    """name -> (level, [(mod id, overrides)])."""
    return {
        "lum.beside_source": ("intro_10", g61.mods_for("off")),
        "lum.flight_path": ("intro_10", g61.mods_for("on")),
        "lum.exit": ("intro_10", g61.mods_for("exit")),
        "frog.500": ("intro_10", g62.mods_for("same")),
        "frog.2000": ("intro_10", g62.mods_for("diff")),
        "frog.exit": ("intro_10", g62.mods_for("exit")),
        "fairy.0": ("intro_20", [(g63.MOD["a"], [g63.fairy("a")])]),
        "fairy.1": ("intro_20", [(g63.MOD["b"], [g63.fairy("b")])]),
        "manager.forest": ("intro_10", [(g64.MOD[0], [g64.manager(0)])]),
        "manager.smallriver": ("intro_10", [(g64.MOD[1], [g64.manager(1)])]),
    }


def record_compile(ranges, tx):
    """Every observable of one compiled operation. Full form (private) and public form (hashes / numbers)."""
    imgs = tx["images"]
    files = {r: (Path(v[0]).name, v[1], v[2]) for r, v in tx["files"].items()}
    old_ptr = Path(tx["files"]["ptr"][0]).read_bytes()
    n0, n = struct.unpack_from(">I", old_ptr, 0)[0], struct.unpack_from(">I", imgs["ptr"], 0)[0]
    added = [list(struct.unpack_from(">iI", imgs["ptr"], 4 + 8 * i)) for i in range(n0, n)]
    rng = [[Path(p).name, off, len(b), sha(b), label, b.hex() if len(b) == 4 else None] for p, off, b, label in ranges]
    full = {"version": tx["version"], "level": tx["level"], "same_size": list(tx["same_size"]), "files": files,
            "images": {r: {"size": len(b), "sha256": sha(b)} for r, b in imgs.items()},
            "relocations": {"original": n0, "added": added}, "ranges": rng,
            "info": json.loads(json.dumps(tx["info"], default=str))}
    pub = dict(full, relocations={"original": n0, "added_count": len(added), "added_sha256": jsha(added)},
               info_sha256=jsha(full["info"]), info=None)
    return full, pub


def normalize_plan(text, root):
    """The plan with the fresh root's path replaced and every blob path replaced by its content hash."""
    out = []
    for ln in text.splitlines():
        if ln.startswith("range "):
            parts = ln.split(" ", 7)
            parts[7] = "blob:" + sha(Path(parts[7]).read_bytes())
            ln = " ".join(parts)
        if ln.startswith("# written by "):
            ln = "# written by <TIME>"   # the writer's timestamp, the only time-dependent line
        for path, tag in ((root, "<ROOT>"), (GAME, "<GAME>"), (ROOT, "<REPO>")):   # no local paths in the record
            ln = ln.replace(str(path), tag).replace(str(path).replace("\\", "/"), tag)
        out.append(ln)
    return "\n".join(out)


def record_plan(name, level, mods):
    paths = p1.fresh(f"plan_{name}")
    with env(level):
        for mid, ov in mods:
            p1.install(paths, mid, ov)
        res = rm.resolve_all(paths, write_plan=paths["cache"])
    plan = paths["cache"] / rm.PLAN_NAME
    text = plan.read_text(encoding="utf-8") if plan.is_file() else None
    raw = plan.read_bytes() if plan.is_file() else b""
    norm = normalize_plan(text, paths["_dir"]) if text else None
    m = p1.parse_plan(text) if text else None
    rec = {"active": res.get("active"), "codes": [r.get("code") for r in res["mods"]],
           "plan_sha256_normalized": sha(norm.encode()) if norm else None,
           "plan_terminated": raw.endswith(b"\n") and not raw.endswith(b"\n\n") if raw else None,
           "txs": m["txs"] if m else None, "mods": m["mods"] if m else None, "gameplay": m["gameplay"] if m else None,
           "tx_id_recomputed": g61.canonical_id(m) if m and m["txs"] else None,
           "ranges": [ln for ln in norm.splitlines() if ln.startswith("range ")] if norm else None,
           "files": [ln for ln in norm.splitlines() if ln.startswith(("file ", "tx-file", "end"))] if norm else None}
    return rec, norm


# --- negative fixtures -------------------------------------------------------------------------------------------------

def outcome(fn):
    try:
        r = fn()
    except rm.Refusal as x:
        return {"code": x.code, "detail": x.detail.replace(str(WORK), "<WORK>").replace(str(GAME), "<GAME>")
                .replace(str(ROOT), "<REPO>")}
    except Exception as x:   # an unexpected exception is an outcome too (recorded, compared)
        return {"exception": type(x).__name__, "detail": str(x)}
    return {"accepted": True, "type": type(r).__name__}


def capture(mod, builder, compile_fn):
    """The builder's arguments as the compiler passes them (the builder replaced by a recording wrapper)."""
    orig, box = getattr(mod, builder), {}

    def wrap(*a, **k):
        box["a"], box["k"] = a, k
        return orig(*a, **k)
    setattr(mod, builder, wrap)
    try:
        compile_fn()
    finally:
        setattr(mod, builder, orig)
    return box["a"], box["k"]


OPS = {   # op -> (level, manifest builder, compile name, build name)
    "lum": ("intro_10", lambda: g61.lum("on"), "compile_insert_passive_lum", "build_passive_lum"),
    "frog": ("intro_10", lambda: g62.frog(500), "compile_insert_scripted_frog", "build_scripted_frog"),
    "fairy": ("intro_20", lambda: g63.fairy("a"), "compile_insert_fairy_on_graph", "build_fairy_on_graph"),
    "manager": ("intro_10", lambda: g64.manager(0), "compile_insert_gensound_manager", "build_gensound_manager"),
}
PARSE = {"lum": "parse_insert_passive_lum", "frog": "parse_insert_scripted_frog",
         "fairy": "parse_insert_fairy_on_graph", "manager": "parse_insert_gensound_manager"}
TARGET_KEY = {"lum": ("position", [0.0, 0.0, 0.0]), "frog": ("period_ms", 1000), "fairy": ("follow_graph_of", 2),
              "manager": ("moves_gensound_instance", 2)}


def _w(b, o, v):
    b = bytearray(b)
    struct.pack_into(">I", b, o, v)
    return bytes(b)


def _u(b, o):
    return struct.unpack_from(">I", b, o)[0]


def file_mutations(spec, lvl, ptr, tl, me):
    """name -> (lvl, ptr, tl): one precondition of the original files broken at a time."""
    SO = spec["so"]
    n = _u(ptr, 0)
    ents = [struct.unpack_from(">iI", ptr, 4 + 8 * i) for i in range(n)]
    drop = next(i for i, (f, loc) in enumerate(ents) if f == me and loc + 4 == SO + 0x20)
    no_slot = struct.pack(">I", n - 1) + b"".join(ptr[4 + 8 * i:12 + 8 * i] for i in range(n) if i != drop) \
        + ptr[4 + 8 * n:]
    dup = struct.pack(">I", n + 1) + ptr[4:12] + ptr[4:]
    out = {
        "census_slot_removed": (lvl, no_slot, tl),
        "duplicate_slot": (lvl, dup, tl),
        "truncated_ptr": (lvl, ptr[:-4], tl),
        "personal_count": (_w(lvl, spec["personal"] + 8, _u(lvl, spec["personal"] + 8) + 1), ptr, tl),
        "records_count": (_w(lvl, spec["records"] + 8, _u(lvl, spec["records"] + 8) + 1), ptr, tl),
        "backups_last": (_w(lvl, spec["backups"] + 4, _u(lvl, spec["backups"] + 4) + 0x10), ptr, tl),
        "world_count": (lvl, ptr, _w(tl, spec["world"] + 0x10, _u(tl, spec["world"] + 0x10) + 1)),
        "sibling_prev": (_w(lvl, SO + 0x18, _u(lvl, SO + 0x18) + 4), ptr, tl),
        "not_superobject": (_w(lvl, SO, 3), ptr, tl),
    }
    if "always" in spec:
        out["always_count"] = (_w(lvl, spec["always"] + 8, _u(lvl, spec["always"] + 8) + 1), ptr, tl)
        out["always_owner_count"] = (_w(lvl, spec["always_owner"] + 8, _u(lvl, spec["always_owner"] + 8) + 1), ptr,
                                     tl)
    if "resolve" in spec:
        st = _u(lvl, spec["resolve"]["ref"]) + 4
        a, b = _u(lvl, st), _u(lvl, st + 4)
        out["resolve_unsorted"] = (_w(_w(lvl, st, b), st + 4, a), ptr, tl)
    if "buffers" in spec:
        ib = SO + spec["buffers"][0]
        out["designer_buffers_differ"] = (_w(lvl, ib + 24, _u(lvl, ib + 24) ^ 1), ptr, tl)
    return out


def spec_mutations(op, spec):
    """name -> altered allow-list facts (each must be refused by the builder's checks of the original files)."""
    out = {"census": dict(spec, census=tuple(c + 1 for c in spec["census"])),
           "new_name_foreign": dict(spec, new_name=b"ZZZ_G6P5"),
           "matrix_offset": dict(spec, matrix=spec["matrix"] + 4),
           "world_offset": dict(spec, world=spec["world"] + 4)}
    if "owned" in spec:
        out["owned_extra"] = dict(spec, owned=tuple(spec["owned"]) + (0x8,))
    if "backup_targets" in spec:
        out["backup_targets"] = dict(spec, backup_targets=tuple(spec["backup_targets"][:-1]))
    if op == "lum":
        out["translations"] = dict(spec, translations=(spec["translations"][0], spec["translations"][1] + 4,
                                                       spec["translations"][2]))
        out["buffer_word"] = dict(spec, buffer=spec["buffer"] + 4)
    if op == "frog":
        out["foreign_refs"] = dict(spec, foreign_refs=(spec["foreign_refs"][0] + 4, spec["foreign_refs"][1]))
        out["events"] = dict(spec, events=(0, 4, 8, 16))
        out["resolve_count"] = dict(spec, resolve=dict(spec["resolve"], count=spec["resolve"]["count"] + 1))
    if op == "fairy":
        out["graph_region"] = dict(spec, graph_region=(spec["graph_region"][0] + 0x14, spec["graph_region"][1]))
        t = {k: dict(v) for k, v in spec["targets"].items()}
        t[0]["named_by"] = (0,)
        out["target_named_by"] = dict(spec, targets=t)
        t2 = {k: dict(v) for k, v in spec["targets"].items()}
        t2[0]["nodes"] = 4
        out["target_nodes"] = dict(spec, targets=t2)
        out["own_graph"] = dict(spec, own_graph=spec["targets"][0]["graph"])
    if op == "manager":
        out["kept_missing"] = dict(spec, kept=tuple(spec["kept"][1:]))
        out["regions_model"] = dict(spec, regions=dict(spec["regions"], model=(spec["regions"]["model"][0] + 4,
                                                                                spec["regions"]["model"][1])))
        out["own_target"] = dict(spec, own_target=spec["targets"][0])
        out["target_is_own"] = dict(spec, targets={0: spec["own_target"], 1: spec["targets"][1]})
        out["target_not_actor"] = dict(spec, targets={0: spec["records"], 1: spec["targets"][1]})
        out["graph_nodes"] = dict(spec, graph_nodes=7)
        out["other_words"] = dict(spec, other=((0x1C, 2),))
    return out


def negative_fixtures():
    neg = {}
    g = {"game": GAME}
    for op, (level, mk, comp, build) in OPS.items():
        o = mk()
        P = getattr(rm, PARSE[op])
        C = getattr(rm, comp)
        tk, bad = TARGET_KEY[op]
        with env(level):
            neg[f"{op}.parse.missing_key"] = outcome(lambda: P({k: v for k, v in o.items() if k != "lvl_sha256"}, "o"))
            neg[f"{op}.parse.extra_key"] = outcome(lambda: P(dict(o, offset=4), "o"))
            neg[f"{op}.parse.bad_level"] = outcome(lambda: P(dict(o, level="../x"), "o"))
            neg[f"{op}.parse.unsupported_level"] = outcome(lambda: P(dict(o, level="intro_15"), "o"))
            neg[f"{op}.parse.bad_hash"] = outcome(lambda: P(dict(o, ptr_sha256="xyz"), "o"))
            neg[f"{op}.parse.bad_instance"] = outcome(lambda: P(dict(o, instance=True), "o"))
            neg[f"{op}.parse.bad_target"] = outcome(lambda: P(dict(o, **{tk: bad}), "o"))
            neg[f"{op}.parse.bool_target"] = outcome(lambda: P(dict(o, **{tk: True}), "o"))
            neg[f"{op}.compile.wrong_model"] = outcome(lambda: C(dict(o, model=rm.LUM10 if op != "lum" else rm.FROG10),
                                                                 g))
            neg[f"{op}.compile.wrong_instance"] = outcome(lambda: C(dict(o, instance=o["instance"] + 1), g))
            for role in ("lvl", "ptr", "transit"):
                neg[f"{op}.compile.wrong_{role}_hash"] = outcome(lambda: C(dict(o, **{f"{role}_sha256": "0" * 64}), g))
            neg[f"{op}.compile.bad_target"] = outcome(lambda: C(dict(o, **{tk: bad}), g))
            old = dict(rm.STRUCT_MAX_GROW)
            rm.STRUCT_MAX_GROW.update(lvl=1000)
            try:
                neg[f"{op}.compile.lvl_budget"] = outcome(lambda: C(o, g))
            finally:
                rm.STRUCT_MAX_GROW.clear()
                rm.STRUCT_MAX_GROW.update(old)
            old_m = rm.STRUCT_MEMORY_MARGIN
            rm.STRUCT_MEMORY_MARGIN = 1 << 30
            try:
                neg[f"{op}.compile.memory_budget"] = outcome(lambda: C(o, g))
            finally:
                rm.STRUCT_MEMORY_MARGIN = old_m
        with env(None):
            neg[f"{op}.parse.gate_off"] = outcome(lambda: P(o, "o"))
            neg[f"{op}.compile.gate_off"] = outcome(lambda: C(o, g))
        with env("intro_15"):
            neg[f"{op}.compile.gate_other_level"] = outcome(lambda: C(o, g))
        # missing transit (a private fake game folder holding copies of the level and pointer files only)
        fake = WORK / "fake_game"
        if fake.exists():
            shutil.rmtree(fake)
        (fake / "GAMEDATAbin" / level).mkdir(parents=True)
        for suffix in ("lvl", "ptr"):
            shutil.copyfile(GAME / "GAMEDATAbin" / level / f"{level}.{suffix}",
                            fake / "GAMEDATAbin" / level / f"{level}.{suffix}")
        with env(level):
            neg[f"{op}.compile.missing_transit"] = outcome(lambda: C(o, {"game": fake}))
        shutil.rmtree(fake)
        # structural refusals of the builder (arguments captured from a valid compile)
        with env(level):
            a, k = capture(rm, build, lambda: C(o, g))
        B = getattr(rm, build)
        lvl, ptr, tl, me, spec = a[:5]
        for name, (ml, mp, mt) in file_mutations(spec, lvl, ptr, tl, me).items():
            neg[f"{op}.build.file.{name}"] = outcome(lambda: B(ml, mp, mt, me, spec, *a[5:], **k))
        for name, sp in spec_mutations(op, spec).items():
            neg[f"{op}.build.spec.{name}"] = outcome(lambda: B(lvl, ptr, tl, me, sp, *a[5:], **k))
        if op == "lum":
            neg["lum.build.peers_empty"] = outcome(lambda: B(lvl, ptr, tl, me, spec, [], *a[6:], **k))
        if op == "frog":
            neg["frog.build.period"] = outcome(lambda: B(lvl, ptr, tl, me, spec, a[5], a[6], 1000, a[8], **k))
            neg["frog.build.foreign_empty"] = outcome(lambda: B(lvl, ptr, tl, me, spec, a[5], [], *a[7:], **k))
        if op == "fairy":
            neg["fairy.build.sel_unknown"] = outcome(lambda: B(lvl, ptr, tl, me, spec, a[5], 5, *a[7:], **k))
            neg["fairy.build.named_empty"] = outcome(lambda: B(lvl, ptr, tl, me, spec, a[5], a[6], {}, *a[8:], **k))
        if op == "manager":
            neg["manager.build.sel_unknown"] = outcome(lambda: B(lvl, ptr, tl, me, spec, a[5], 5, *a[7:], **k))
            prev = _u(lvl, spec["targets"][0] + 0x18) + 4   # a relocated word naming the target (its sibling link)
            neg["manager.build.foreign_names_target"] = outcome(lambda: B(
                lvl, ptr, tl, me, spec, a[5], 0, [(prev + 0x14, 4)] + list(a[7]), *a[8:], **k))
    # conflicts
    mk = lambda ov: {"mod.json": json.dumps(p1.manifest("x.conflict", ov)).encode()}   # noqa: E731
    graph13 = {"type": "insert-graph-node", "level": "intro_10", "model": rm.FLY10, "instance": 0, "variable": 0,
               "after_node": 13, "lvl_sha256": g64.LVL_SHA, "ptr_sha256": g64.PTR_SHA, "position": [18.0, -33.0, -42.0]}
    with env("intro_10"):
        neg["conflict.two_lums_one_mod"] = outcome(lambda: rm.parse_manifest(mk([g61.lum("on"), g61.lum("off")])))
        neg["conflict.lum_and_graph_one_mod"] = outcome(lambda: rm.parse_manifest(mk([g61.lum("on"), graph13])))
        neg["conflict.frog_and_lum_one_mod"] = outcome(lambda: rm.parse_manifest(mk([g62.frog(500), g61.lum("on")])))
        neg["conflict.two_managers_one_mod"] = outcome(lambda: rm.parse_manifest(mk([g64.manager(0), g64.manager(1)])))
        neg["conflict.manager_and_frog_one_mod"] = outcome(lambda: rm.parse_manifest(mk([g64.manager(0),
                                                                                         g62.frog(500)])))
        neg["conflict.manager_and_graph_one_mod"] = outcome(lambda: rm.parse_manifest(mk([g64.manager(0), graph13])))
    with env("intro_20"):
        neg["conflict.two_fairies_one_mod"] = outcome(lambda: rm.parse_manifest(mk([g63.fairy("a"), g63.fairy("b")])))
    for name, level, mods in (("two_structural_mods_intro_10", "intro_10",
                               [("x.m0", [g64.manager(0)]), ("x.f0", [g62.frog(500)])]),
                              ("lum_and_manager_mods", "intro_10", [("x.l0", [g61.lum("on")]),
                                                                    ("x.m1", [g64.manager(1)])]),
                              ("two_fairy_mods", "intro_20", [("x.fa", [g63.fairy("a")]),
                                                              ("x.fb", [g63.fairy("b")])])):
        paths = p1.fresh(f"conflict_{name}")
        with env(level):
            for mid, ov in mods:
                p1.install(paths, mid, ov)
            res = rm.resolve_all(paths, write_plan=paths["cache"])
        neg[f"conflict.{name}"] = {"active": res.get("active"), "plan": (paths["cache"] / rm.PLAN_NAME).is_file(),
                                   "mods": [{"id": r.get("id"), "code": r.get("code"),
                                             "detail": str(r.get("detail", "")).replace(str(WORK), "<WORK>")}
                                            for r in res["mods"]]}
    return neg


# --- primitive isolation (G6-P5's shared helpers; new tests, run after the refactor) ---------------------------------

SOURCE = {"lum": ("_lum_source", lambda a: a[5:6]), "frog": ("_frog_source", lambda a: a[5:7]),
          "fairy": ("_fairy_source", lambda a: a[5:8]), "manager": ("_gmgr_source", lambda a: a[5:8])}


def primitives():
    """Each shared primitive refuses what its callers' explicit facts do not allow, and one actor's facts cannot be
    used for another actor: name -> True (refused / behaved as required) or the unexpected outcome."""
    if not hasattr(rm, "actor_copy"):
        return {"skipped": "the compiler has no shared actor primitives"}
    out, ctx, args = {}, {}, {}
    g = {"game": GAME}
    for op, (level, mk, comp, build) in OPS.items():
        with env(level):
            a, _ = capture(rm, build, lambda: getattr(rm, comp)(mk(), g))
        lvl, ptr, tl, me, spec = a[:5]
        src, extra = SOURCE[op]
        args[op] = a
        ctx[op] = (lvl, ptr, tl, me, spec, getattr(rm, src)(lvl, ptr, tl, me, spec, *extra(a), "iso"))

    def refuses(fn):
        r = outcome(fn)
        return r.get("code") == "STRUCTURE_CHECK" or r

    def fail(why):
        raise rm.Refusal("STRUCTURE_CHECK", f"iso: {why}")

    def copy_with(op, kinds_fn, segs_fn=None):
        lvl, ptr, tl, me, spec, s = ctx[op]
        segs, cs, cmap = segs_fn(spec, s) if segs_fn else rm.actor_segments(spec["block"], (), packed=False)
        new = bytearray(lvl) + bytearray(cs + 16)
        return lambda: rm.actor_copy(new, lvl, s, spec["so"], len(lvl), segs, cmap, kinds_fn(spec, s), fail)

    def base_kinds(spec, s):
        SO = spec["so"]
        k = {o: "owned" for o in s["inner"]}
        k.update({o: "shared" for o in s["ext"]})
        k.update({SO + 0x14: "link", SO + 0x18: "link", SO + 0x1C: "other"})
        return k

    def fairy_segs(spec, s):
        return rm.actor_segments(spec["block"], [(s["region"][0] - spec["so"], s["region"][1] - spec["so"])],
                                 packed=False)
    out["copy_accepts_verified_lum_classes"] = outcome(copy_with("lum", base_kinds)).get("type") == "list"
    out["copy_unclassified_word"] = refuses(copy_with("lum", lambda sp, s: {
        o: v for o, v in base_kinds(sp, s).items() if o != s["inner"][0]}))
    out["copy_unknown_class"] = refuses(copy_with("lum", lambda sp, s: {**base_kinds(sp, s), s["inner"][0]: "rebase"}))
    out["copy_malformed_reference"] = refuses(copy_with("lum", lambda sp, s: {**base_kinds(sp, s), s["ext"][2]: ("ref", None)}))
    out["copy_links_unclassified"] = refuses(copy_with("frog", lambda sp, s: {**base_kinds(sp, s), sp["so"] + 0x14: "shared"}))
    # the fairy's graph reference treated as an owned pointer: its target lies in the left-out region
    out["fairy_reference_as_owned"] = refuses(copy_with("fairy", base_kinds, fairy_segs))
    # the lum's / Frog's ownership policy applied to the manager: pointers into its shared model / graph regions
    # classified owned must refuse (their targets are not copied)
    out["manager_with_frog_policy"] = refuses(copy_with("manager", base_kinds, lambda sp, s: rm.gmgr_layout(sp)))
    segs, cs, cmap = rm.gmgr_layout(ctx["manager"][4])
    out["packed_layout_region_unmapped"] = outcome(lambda: cmap(0x400)).get("exception") == "KeyError"
    out["unpacked_layout_identity"] = rm.actor_segments(0x520, (), packed=False)[:2] == ([(0, 0x520, 0)], 0x520)
    out["layout_misaligned_name"] = refuses(lambda: rm.actor_layout(100, 0x10, 0x20, 3, 1, fail))
    # one actor's list facts on another's source
    lvl, ptr, tl, me, spec, s = ctx["lum"]
    slots, cross, target, tail = rm.actor_tables(lvl, ptr, tl, me, fail)
    frog_on_lum = dict(rm.FROG_ALLOW["intro_10"], so=spec["so"], block=spec["block"])
    links = rm.actor_backup_links(target, tail, spec, fail)
    out["frog_backup_facts_on_lum"] = refuses(lambda: rm.actor_backup_records(lvl, slots, target, links, frog_on_lum,
                                                                             [], "four", fail))
    out["always_facts_on_lum"] = refuses(lambda: rm.actor_always(lvl, slots, target, tail, frog_on_lum, [], True,
                                                                 fail))
    fl, fp, ft, fme, fspec, fs = ctx["frog"]
    fsl, _, ftg, ftail = rm.actor_tables(fl, fp, ft, fme, fail)
    gm_on_frog = dict(rm.GMGR_ALLOW["intro_10"], so=fspec["so"], block=fspec["block"])
    out["manager_backup_facts_on_frog"] = refuses(lambda: rm.actor_backup_records(
        fl, fsl, ftg, rm.actor_backup_links(ftg, ftail, fspec, fail), gm_on_frog, [], "three", fail))
    out["name_rule_on_frog"] = refuses(lambda: rm.actor_personal_types(
        fl, fsl, ftg, ftail, dict(fspec, new_name=b"MAN_mGenSound_Other_G6P5"), fs["std"], False, fail))
    out["registration_without_always_for_lum_and_fairy"] = "always" not in rm.LUM_ALLOW["intro_10"] \
        and "always" not in rm.FAIRY_ALLOW["intro_20"]
    # edit planner, actor count, simulator
    out["edits_duplicate_word"] = refuses(lambda: rm.apply_original_edits(lvl, bytearray(lvl), [
        (0x1C78, _u(lvl, 0x1C78), 1, "a"), (0x1C78, _u(lvl, 0x1C78), 2, "b")], fail))
    out["edits_wrong_original"] = refuses(lambda: rm.apply_original_edits(lvl, bytearray(lvl), [
        (0x1C78, _u(lvl, 0x1C78) + 1, 1, "a")], fail))
    out["actor_count_mismatch"] = refuses(lambda: rm.bump_actor_count(tl, spec, s["world_count"] + 1, fail))
    va, _ = capture(rm, "verify_passive_lum", lambda: rm.build_passive_lum(*args["lum"]))
    nl = bytearray(va[3])
    nl[0x100] ^= 1
    out["simulator_untouched_word_changed"] = refuses(lambda: rm.verify_passive_lum(*va[:3], bytes(nl), *va[4:]))
    np_ = bytearray(va[4])
    last = 4 + 8 * (_u(va[4], 0) - 1) + 4   # the last new entry's slot word
    struct.pack_into(">I", np_, last, _u(np_, last) + 4)
    out["simulator_moved_relocation"] = refuses(lambda: rm.verify_passive_lum(*va[:4], bytes(np_), *va[5:]))
    return out


# --- snapshot / freeze / compare ---------------------------------------------------------------------------------------

def snapshot(mod=None):
    """Every fixture through the compiler module `mod` (default: the current r3hd_mods)."""
    global rm
    saved = rm
    if mod is not None:
        rm = mod
        for m in (p1, g61, g62, g63, g64):
            m.rm = mod
    try:
        valid, images = {}, {}
        for name, (level, o, comp) in valid_fixtures().items():
            with env(level):
                ranges, tx = getattr(rm, comp)(o, {"game": GAME})
            full, pub = record_compile(ranges, tx)
            valid[name] = {"manifest_sha256": jsha(o), "full": full, "public": pub}
            images[name] = tx["images"]
        plans, norms = {}, {}
        for name, (level, mods) in plan_fixtures().items():
            plans[name], norms[name] = record_plan(name, level, mods)
        neg = negative_fixtures()
    finally:
        rm = saved
        for m in (p1, g61, g62, g63, g64):
            m.rm = saved
    snap = json.loads(json.dumps({"valid": valid, "plans": plans, "negative": neg}, default=str))   # as frozen
    return snap, images, norms


def git_head():
    return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()


def freeze():
    if subprocess.run(["git", "diff", "--quiet", "--", "tools/r3hd_mods.py"], cwd=ROOT).returncode:
        print("refusing to freeze: tools/r3hd_mods.py differs from HEAD")
        return 1
    snap, images, norms = snapshot()
    if BASE.exists():
        shutil.rmtree(BASE)   # our own folder under private/work/e491
    BASE.mkdir(parents=True)
    for name, imgs in images.items():
        for role, b in imgs.items():
            (BASE / f"{name}.{role}.bin").write_bytes(b)
    for name, t in norms.items():
        if t:
            (BASE / f"{name}.plan.txt").write_text(t, encoding="utf-8")
    head = git_head()
    (BASE / "baseline_full.json").write_text(json.dumps(dict(snap, head=head), indent=1, default=str) + "\n")
    pub = {"head": head, "compiler_sha256": sha((TOOLS / "r3hd_mods.py").read_bytes()),
           "valid": {n: dict(v["public"], manifest_sha256=v["manifest_sha256"]) for n, v in snap["valid"].items()},
           "plans": snap["plans"], "negative": snap["negative"]}
    PUBLIC.write_text(json.dumps(pub, indent=1, default=str) + "\n", encoding="utf-8")
    print("frozen at", head, ":", len(snap["valid"]), "valid,", len(snap["plans"]), "plans,", len(snap["negative"]),
          "negative")
    return 0


def baseline_compiler():
    d = WORK / "baseline_compiler"
    d.mkdir(parents=True, exist_ok=True)
    src = subprocess.run(["git", "show", f"{BASELINE}:tools/r3hd_mods.py"], cwd=ROOT, capture_output=True,
                         check=True).stdout
    p = d / f"r3hd_mods_{BASELINE}.py"
    p.write_bytes(src)
    spec = importlib.util.spec_from_file_location(f"r3hd_mods_{BASELINE}", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.TOOLS, mod.ROOT = rm.TOOLS, rm.ROOT   # the repository it belongs to (release ids, port version)
    return mod


def first_diff(a: bytes, b: bytes):
    if a == b:
        return None
    for i in range(min(len(a), len(b))):
        if a[i] != b[i]:
            return i
    return min(len(a), len(b))


def compare():
    frozen = json.loads((BASE / "baseline_full.json").read_text())
    pub = json.loads(PUBLIC.read_text(encoding="utf-8"))
    cur, images, norms = snapshot()
    old, old_images, old_norms = snapshot(baseline_compiler())
    det, E = {}, {}
    groups = {"E1": "lum.", "E2": "frog.", "E3": "fairy.", "E4": "manager."}
    for e, pre in groups.items():
        rows = {}
        for name in [n for n in frozen["valid"] if n.startswith(pre)]:
            img_ok = {}
            for role, b in images[name].items():
                ref = (BASE / f"{name}.{role}.bin").read_bytes()
                img_ok[role] = {"frozen_bin": first_diff(ref, b), "baseline_compiler": first_diff(old_images[name][role], b),
                                "sha_public": sha(b) == pub["valid"][name]["images"][role]["sha256"]}
            rows[name] = {"images": img_ok,
                          "full_record_equal": cur["valid"][name]["full"] == frozen["valid"][name]["full"],
                          "baseline_compiler_record_equal": cur["valid"][name]["full"] == old["valid"][name]["full"],
                          "public_equal": json.loads(json.dumps(cur["valid"][name]["public"], default=str))
                          == {k: v for k, v in pub["valid"][name].items() if k != "manifest_sha256"}}
        for name in [n for n in frozen["plans"] if n.startswith(pre)]:
            rows[f"plan:{name}"] = {"plan_equal": cur["plans"][name] == frozen["plans"][name] == pub["plans"][name],
                                    "baseline_compiler_plan_equal": cur["plans"][name] == old["plans"][name],
                                    "normalized_text_equal": norms[name] == old_norms[name] and (
                                        norms[name] is None or norms[name] == (BASE / f"{name}.plan.txt").read_text(
                                            encoding="utf-8"))}
        ok = all(all(v["frozen_bin"] is None and v["baseline_compiler"] is None and v["sha_public"]
                     for v in r["images"].values()) and r["full_record_equal"] and r["baseline_compiler_record_equal"]
                 and r["public_equal"] if "images" in r else all(r.values()) for r in rows.values())
        E[e] = ok
        det[e] = rows
    # E5: relocations (every added entry, in order) and E6: transactions (plans, ids, recomputed ids)
    E["E5"] = all(cur["valid"][n]["full"]["relocations"] == frozen["valid"][n]["full"]["relocations"]
                  == old["valid"][n]["full"]["relocations"] for n in frozen["valid"])
    det["E5"] = {n: len(cur["valid"][n]["full"]["relocations"]["added"]) for n in frozen["valid"]}
    E["E6"] = all(cur["plans"][n]["txs"] == frozen["plans"][n]["txs"] == old["plans"][n]["txs"]
                  and (cur["plans"][n]["txs"] is None or cur["plans"][n]["txs"][0].split(" ")[4]
                       == cur["plans"][n]["tx_id_recomputed"]) for n in frozen["plans"]) \
        and all(cur["plans"][n]["plan_sha256_normalized"] == frozen["plans"][n]["plan_sha256_normalized"]
                for n in frozen["plans"])
    det["E6"] = {n: (p["txs"][0].split(" ")[4] if p["txs"] else None) for n, p in cur["plans"].items()}
    neg_diff = {n: {"now": cur["negative"].get(n), "frozen": v} for n, v in frozen["negative"].items()
                if cur["negative"].get(n) != v or old["negative"].get(n) != v}
    new_keys = sorted(set(cur["negative"]) - set(frozen["negative"]))
    accepted = [n for n, v in cur["negative"].items() if isinstance(v, dict) and v.get("accepted")]
    E["E7"] = not neg_diff and not new_keys   # accepted entries (accepted at that stage before too) are compared
    det["E7"] = {"fixtures": len(frozen["negative"]), "differences": neg_diff, "new": new_keys, "accepted": accepted,
                 "codes": sorted({v.get("code") for v in cur["negative"].values() if isinstance(v, dict)} - {None})}
    prim = primitives()
    det["E7"]["primitive_isolation"] = prim
    E["E7"] = E["E7"] and all(v is True for v in prim.values())
    out = {"pass": all(E.values()), "E": E, "head": git_head(), "baseline": frozen["head"], "details": det}
    (WORK / "compare.json").write_text(json.dumps(out, indent=1, default=str) + "\n")
    print(json.dumps(E, indent=1))
    print("EQUIVALENCE_G6P5", "PASS" if out["pass"] else "FAIL")
    return 0 if out["pass"] else 1


def e8():
    """G6-P4's offline check (its independent constructor / simulator O3-O5 and the G5-P4a / G6-P1 / G6-P2 / G6-P3
    checks it chains, each with its own independent constructor), redirected to private/work/e491/compat."""
    cw = WORK / "compat" / "g6p4_pilot"
    cw.mkdir(parents=True, exist_ok=True)
    src = ROOT / "private" / "work" / "e490"
    for f in ("oracle_o1.json", "census.json"):
        if (src / f).is_file():
            shutil.copyfile(src / f, cw / f)
    q = subprocess.run([sys.executable, "-c", (
        "import sys, pathlib; sys.path.insert(0, r'%s'); sys.path.insert(0, r'%s'); import g6p4_pilot as m; "
        "import g5p1_pilot as p1; m.WORK = pathlib.Path(r'%s'); p1.WORK = m.WORK; sys.exit(m.check())")
        % (TOOLS, HERE, cw)], cwd=ROOT, capture_output=True, text=True, timeout=5400)
    (cw / "check.log").write_text(q.stdout + q.stderr)
    off = json.loads((cw / "offline.json").read_text()) if (cw / "offline.json").is_file() else {}
    out = {"pass": q.returncode == 0 and off.get("pass") is True, "rc": q.returncode, "O": off.get("O"),
           "compat": (off.get("details") or {}).get("O8")}
    (WORK / "e8.json").write_text(json.dumps(out, indent=1, default=str) + "\n")
    print(json.dumps(out, indent=1, default=str))
    print("E8_G6P5", "PASS" if out["pass"] else "FAIL")
    return 0 if out["pass"] else 1


def negtest():
    """The deterministic transaction tests (g5p1_tx_test.cpp against the development and production headers; no game):
    G6-P4's suite, which re-runs G6-P3's (and through it G5-P4a's, G6-P2's, G6-P1's and the G5 suites: version-1 and
    version-2 transactions, missing members, tampering, unsupported versions, production refusal), redirected to
    private/work/e491/compat/g6p4_negtest."""
    cw = WORK / "compat" / "g6p4_negtest"
    cw.mkdir(parents=True, exist_ok=True)
    q = subprocess.run([sys.executable, "-c", (
        "import sys, pathlib; sys.path.insert(0, r'%s'); sys.path.insert(0, r'%s'); import g6p4_pilot as m; "
        "import g5p1_pilot as p1; m.WORK = pathlib.Path(r'%s'); p1.WORK = m.WORK; sys.exit(m.negtest())")
        % (TOOLS, HERE, cw)], cwd=ROOT, capture_output=True, text=True, timeout=7200)
    (cw / "negtest.log").write_text(q.stdout + q.stderr)
    summ = cw / "negtest" / "summary.json"
    out = json.loads(summ.read_text()) if summ.is_file() else {}
    res = {"pass": q.returncode == 0 and out.get("pass") is True, "rc": q.returncode,
           "dev": [out.get("dev", {}).get(k) for k in ("passed", "cases")],
           "prod": [out.get("prod", {}).get(k) for k in ("passed", "cases")], "g6p3_negtest_rc": out.get("g6p3_negtest_rc")}
    (WORK / "negtest.json").write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps(res, indent=1))
    print("NEGTEST_G6P5", "PASS" if res["pass"] else "FAIL")
    return 0 if res["pass"] else 1


def main():
    a = sys.argv[1:]
    if a == ["freeze"]:
        return freeze()
    if a == ["compare"]:
        return compare()
    if a == ["e8"]:
        return e8()
    if a == ["negtest"]:
        return negtest()
    if a == ["primitives"]:
        r = primitives()
        print(json.dumps(r, indent=1, default=str))
        return 0 if all(v is True for v in r.values()) else 1
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
