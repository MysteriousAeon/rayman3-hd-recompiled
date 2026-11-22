#!/usr/bin/env python3
"""G6-P29 (D-285): authoring core of the private visual level editor (no GUI code here).

The editor UI (r3hd_level_editor.py) owns selection and drawing. This module owns:
  * the spatial model, decoded ONLY by the existing compiler decoders in r3hd_mods (collision_triangles,
    read_script_index, terrain_region, LEVEL_PATCH_ROUTES / PROBE / WITNESSES) from the person's own level files;
  * the versioned editor project (an editable description: no game bytes), its strict loader and atomic save;
  * the adapter project -> level-patch-v1 declaration, and validation / export through r3hd_mods.cmd_level_patch
    (the authoritative compiler; nothing here re-implements terrain, graph or transaction rules).
Development-only: validation and export need R3HD_DEV_STRUCTURAL_TX=intro_20 in the environment that started the
editor (the editor never sets it). The production runtime refuses level transactions.
"""
import copy
import json
import math
import os
import struct
import tempfile
from pathlib import Path

import r3hd_mods as rm

PROJECT_FORMAT = "r3hd-level-editor-project-v1"
PROJECT_KEYS = {"format", "level", "target", "region", "terrain", "route", "fairylight", "meta"}
META_KEYS = {"id", "name", "description"}
LEVEL = "intro_20"
REGIONS = ("start-floor-v1", "start-floor-v2")
GRAPH_NAMES = {0: "graph A", 1: "graph B"}
MAX_PROJECT_BYTES = 64 * 1024
DEFAULT_ID = "custom.intro20-map"


class EditorError(Exception):
    """A refusal shown to the person (code, message)."""

    def __init__(self, code, detail):
        super().__init__(f"{code}: {detail}")
        self.code, self.detail = code, detail


def f32(v):
    return struct.unpack(">f", struct.pack(">f", v))[0]


def default_game_dir():
    """The game data the mod manager uses: R3HD_GAME_DIR, else R3HD_HOME/data/content, else the repository layout."""
    return Path(mod_paths()["game"])


def gate_enabled():
    """True when the development-only structural compile gate names this level (never set by the editor)."""
    return rm.structural_enabled(LEVEL)


def targets():
    return {"lvl_sha256": rm.STRUCT_ALLOW[LEVEL]["lvl"][1], "ptr_sha256": rm.STRUCT_ALLOW[LEVEL]["ptr"][1],
            "transit_sha256": rm.FAIRY_ALLOW[LEVEL]["transit"][1]}


# ------------------------------------------------------------------------------------------------ spatial model
class LevelModel:
    """Read-only spatial data of intro_20 from the person's files, decoded by the compiler's own readers."""

    def __init__(self, game_dir):
        self.game = Path(game_dir)
        try:
            lvl_p, ptr_p, _ = rm.script_level_files(self.game, LEVEL)
            tl_p = lvl_p.with_name("transit.lvl")   # as actor_level_inputs
            self.lvl, self.ptr, tl = lvl_p.read_bytes(), ptr_p.read_bytes(), tl_p.read_bytes()
        except (OSError, rm.Refusal) as x:
            raise EditorError("TARGET_MISSING", f"the intro_20 level files were not found under {self.game} ({x})")
        got = {"lvl_sha256": rm.sha256_bytes(self.lvl), "ptr_sha256": rm.sha256_bytes(self.ptr),
               "transit_sha256": rm.sha256_bytes(tl)}
        bad = [k for k, v in targets().items() if got[k] != v]
        if bad:
            raise EditorError("TARGET_CHANGED", "these files are not the exact supported originals: "
                              + ", ".join(f"{k[:-7]} {got[k][:8]}... (expected {targets()[k][:8]}...)" for k in bad))
        self.hashes = got
        self.verts, self.tris = rm.collision_triangles(self.lvl, self.ptr, LEVEL)
        self.regions = {r: rm.terrain_region(LEVEL, r) for r in REGIONS}
        ix = rm.read_script_index(self.game, LEVEL)
        rs = rm.LEVEL_PATCH_ROUTES[LEVEL]
        self.route_spec = rs
        e = ix["graphs"].get((rs["model"], rs["instance"], rs["variable"]))
        if e is None or e["graph"] != rs["graph"] or len(e["nodes"]) != rs["nodes"] or e["safe"] or e["wsafe"]:
            raise EditorError("TARGET_CHANGED", "graph C is not the verified graph")
        self.route = [struct.unpack_from(">3f", self.lvl, w) for _, w in e["nodes"]]
        self.graphs = {}
        for sel, t in rm.FAIRY_ALLOW[LEVEL]["targets"].items():
            g = next((v for (m, n, var), v in ix["graphs"].items() if v["graph"] == t["graph"]), None)
            self.graphs[sel] = [struct.unpack_from(">3f", self.lvl, w) for _, w in g["nodes"]] if g else []
        src = rm.FAIRY_ALLOW[LEVEL]["instance"]
        m = ix["placements"][rm.FAIRY20][src]["matrix"]
        self.fairy_source = struct.unpack_from(">3f", self.lvl, m + 0x34)
        self.probes = [("start (probe l1)", rm.LEVEL_PATCH_PROBE[LEVEL]["xyz"])] + [
            (w["name"], w["xyz"]) for w in rm.LEVEL_PATCH_WITNESSES.get(LEVEL, ())]
        self.probe_triangles = [("start", tuple(rm.LEVEL_PATCH_PROBE[LEVEL]["triangle"]))] + [
            (w["name"], tuple(w["triangle"])) for w in rm.LEVEL_PATCH_WITNESSES.get(LEVEL, ())]

    def vertex_triangles(self, v):
        return sorted(t for t, ix in self.tris.items() if v in ix)

    def edited_verts(self, terrain):
        """Vertices after z-only lowering {vertex: delta_z}: float32(z + dz), the compiler's own rule."""
        out = list(self.verts)
        for v, dz in terrain.items():
            x, y, z = self.verts[v]
            out[v] = (x, y, f32(z + dz))
        return out

    def edited_route(self, route):
        return [tuple(f32(a + b) for a, b in zip(p, route.get(n, (0.0, 0.0, 0.0)))) for n, p in enumerate(self.route)]


def triangle_normal_z(a, b, c):
    ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
    nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
    n = math.sqrt(nx * nx + ny * ny + nz * nz)
    return nz / n if n else 0.0


# ------------------------------------------------------------------------------------------------ project
def new_project():
    return {"format": PROJECT_FORMAT, "level": LEVEL, "target": targets(), "region": "start-floor-v2",
            "terrain": {}, "route": {}, "fairylight": {"follow_graph_of": 0},
            "meta": {"id": DEFAULT_ID, "name": "Untitled intro_20 map", "description": ""}}


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def check_project(p):
    """Validate a project object strictly (structure and the published allow-list ranges; the compiler decides the
    rest). Returns the normalized project (vertex / node keys as strings, numbers as floats)."""
    if not isinstance(p, dict):
        raise EditorError("BAD_PROJECT", "a project must be a JSON object")
    if p.get("format") != PROJECT_FORMAT:
        raise EditorError("UNSUPPORTED", f"project format {p.get('format')!r} (supported: {PROJECT_FORMAT})")
    if set(p) != PROJECT_KEYS:
        raise EditorError("BAD_PROJECT", f"unknown keys {sorted(set(p) - PROJECT_KEYS)}, missing "
                                         f"{sorted(PROJECT_KEYS - set(p))}")
    if p["level"] != LEVEL:
        raise EditorError("UNSUPPORTED", f"level {p['level']!r} (this editor supports {LEVEL} only)")
    if p["target"] != targets():
        raise EditorError("UNSUPPORTED", "the project's target hashes are not the supported intro_20 originals")
    if p["region"] not in REGIONS:
        raise EditorError("UNSUPPORTED", f"region {p['region']!r} (supported: {', '.join(REGIONS)})")
    reg = rm.terrain_region(LEVEL, p["region"])
    lo, hi = reg["delta_z"]
    t = p["terrain"]
    if not isinstance(t, dict):
        raise EditorError("BAD_PROJECT", "'terrain' must be an object {vertex: delta_z}")
    terrain = {}
    for k, dz in t.items():
        if not (isinstance(k, str) and k.isdigit()) or int(k) not in reg["vertices"]:
            raise EditorError("UNSUPPORTED", f"terrain vertex {k!r} is not editable in {p['region']} "
                                             f"(editable: {', '.join(map(str, reg['vertices']))})")
        vlo, vhi = reg.get("vertex_delta_z", {}).get(int(k), (lo, hi))
        if not _num(dz) or not vlo <= dz <= vhi:
            raise EditorError("UNSUPPORTED", f"terrain vertex {k}: delta_z {dz!r} outside {vlo:.2f}..{vhi:.2f}")
        terrain[str(int(k))] = float(dz)
    r = p["route"]
    rs = rm.LEVEL_PATCH_ROUTES[LEVEL]
    if not isinstance(r, dict):
        raise EditorError("BAD_PROJECT", "'route' must be an object {node: [dx, dy, dz]}")
    route = {}
    for k, off in r.items():
        if not (isinstance(k, str) and k.isdigit()) or not 0 <= int(k) < rs["nodes"]:
            raise EditorError("UNSUPPORTED", f"route node {k!r} (graph C has nodes 0-{rs['nodes'] - 1})")
        if not isinstance(off, list) or len(off) != 3 or not all(_num(v) for v in off):
            raise EditorError("BAD_PROJECT", f"route node {k}: offset must be [dx, dy, dz]")
        n = math.sqrt(sum(v * v for v in off))
        if n == 0 or n > rs["max_move"]:
            raise EditorError("UNSUPPORTED", f"route node {k}: move {n:.3f} units (allowed: above 0, at most "
                                             f"{rs['max_move']:g})")
        route[str(int(k))] = [float(v) for v in off]
    f = p["fairylight"]
    if not isinstance(f, dict) or set(f) != {"follow_graph_of"} or f["follow_graph_of"] not in GRAPH_NAMES \
            or isinstance(f["follow_graph_of"], bool):
        raise EditorError("UNSUPPORTED", "'fairylight' must be {\"follow_graph_of\": 0 or 1}")
    m = p["meta"]
    if not isinstance(m, dict) or set(m) != META_KEYS:
        raise EditorError("BAD_PROJECT", f"'meta' needs exactly {sorted(META_KEYS)}")
    if not isinstance(m["id"], str) or not rm.ID_RE.match(m["id"]):
        raise EditorError("BAD_PROJECT", "meta.id must be a mod id (lower case a-z 0-9 . _ -, 2-64 characters)")
    for k in ("name", "description"):
        if not isinstance(m[k], str) or len(m[k]) > 200 or not all(32 <= ord(c) < 127 for c in m[k]):
            raise EditorError("BAD_PROJECT", f"meta.{k} must be at most 200 printable ASCII characters")
    return {"format": PROJECT_FORMAT, "level": LEVEL, "target": targets(), "region": p["region"],
            "terrain": dict(sorted(terrain.items(), key=lambda x: int(x[0]))),
            "route": dict(sorted(route.items(), key=lambda x: int(x[0]))),
            "fairylight": {"follow_graph_of": f["follow_graph_of"]}, "meta": dict(m)}


def load_project(path):
    raw = Path(path).read_bytes()
    if len(raw) > MAX_PROJECT_BYTES:
        raise EditorError("BAD_PROJECT", f"the project file is larger than {MAX_PROJECT_BYTES} bytes")
    try:
        p = rm._terrain_json(raw, Path(path).name)   # UTF-8, no duplicate keys, no NaN / Infinity
    except rm.Refusal as x:
        raise EditorError("BAD_PROJECT", x.detail)
    return check_project(p)


def project_bytes(p):
    return (json.dumps(check_project(p), indent=1) + "\n").encode("utf-8")


def atomic_write(path, data: bytes):
    path = Path(path)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def save_project(p, path):
    atomic_write(path, project_bytes(p))


# ------------------------------------------------------------------------------------------------ adapter
def declaration(p):
    """The level-patch-v1 declaration of a project (one terrain group per lowered vertex, route moves sorted by node).
    Group-count, range and geometry rules are left to the compiler."""
    p = check_project(p)
    name = "editor-terrain"
    decl = {"format": rm.LEVEL_PATCH_FORMAT, "level": LEVEL, **targets(), "id": p["meta"]["id"],
            "components": [
                {"type": "terrain", "patch": {
                    "format": rm.TERRAIN_FORMAT, "level": LEVEL, "lvl_sha256": targets()["lvl_sha256"],
                    "region": p["region"], "name": name,
                    "groups": [{"name": f"vertex-{v}", "vertices": [int(v)], "delta_z": dz}
                               for v, dz in p["terrain"].items()]}},
                {"type": "fairylight", "follow_graph_of": p["fairylight"]["follow_graph_of"]}]}
    if p["meta"]["description"]:
        decl["description"] = p["meta"]["description"]
    if p["route"]:
        decl["components"].append({"type": "route", "waypoints": [{"node": int(n), "offset": o}
                                                                   for n, o in p["route"].items()]})
    return decl


def precheck(p, model=None):
    """Fast local findings for the interface (the compiler remains authoritative): [(severity, text)]."""
    p = check_project(p)
    out = []
    reg = rm.terrain_region(LEVEL, p["region"])
    lo_g, hi_g = reg["groups"]
    n = len(p["terrain"])
    if n < lo_g:
        out.append(("error", f"terrain: lower at least {lo_g} vertices (level-patch-v1 needs {lo_g}-{hi_g} terrain "
                             f"groups; the editor makes one group per lowered vertex)"))
    if n > hi_g:
        out.append(("error", f"terrain: at most {hi_g} lowered vertices in {p['region']}"))
    if model is not None and n:
        vs = model.edited_verts({int(v): dz for v, dz in p["terrain"].items()})
        tri = sorted({t for v in p["terrain"] for t in model.vertex_triangles(int(v))})
        low = min((triangle_normal_z(*(vs[i] for i in model.tris[t])), t) for t in tri)
        if low[0] < reg["min_normal_z"]:
            out.append(("error", f"terrain: triangle {low[1][0]}/{low[1][1]} would be steeper than allowed "
                                 f"(normal z {low[0]:.4f} < {reg['min_normal_z']})"))
    ok, why = production_status(p)
    if not ok:
        out.append(("warn", f"development-only content: {why}. The production game refuses it"
                            + ("" if gate_enabled() else f"; validating or exporting it needs {rm.STRUCT_ENV}={LEVEL} "
                               "(a private development setup)")))
    return out


def production_status(p):
    """(True, summary) when the project's declaration is inside the production policy (D-286), else (False, why).
    The tool's level_patch_production decides; the production runtime enforces the content again."""
    why = rm.level_patch_production(declaration(p))
    return (not why, why or "start-floor terrain + FairyLight on graph A (production policy D-286)")


def validate(p, game_dir, out_dir=None):
    """Run the authoritative compiler (r3hd_mods level-patch --check, or --out DIR) on the project's declaration.
    {"ok": True, "report": ...} or {"ok": False, "code", "detail", "advice"}. Writes nothing unless out_dir.
    G6-P30 (D-286): without the development variable the compiler accepts only production-policy content."""
    decl = declaration(p)
    with tempfile.TemporaryDirectory(prefix="r3hd-editor-") as td:
        src = Path(td) / "level_patch.json"
        src.write_text(json.dumps(decl, indent=1) + "\n", encoding="utf-8")
        # the installation's home (R3HD_HOME: data\intake.json names the release) as the mod manager resolves it
        paths = {"home": mod_paths()["home"], "game": Path(game_dir), "mods": Path(td) / "mods",
                 "cache": Path(td) / "cache"}
        try:
            r = rm.cmd_level_patch(paths, src, Path(out_dir) if out_dir else None, check=out_dir is None)
        except rm.Refusal as x:
            return {"ok": False, "code": x.code, "detail": x.detail, "advice": rm.LEVEL_PATCH_ADVICE.get(x.code, "")}
    r["result"] = "ok"
    return {"ok": True, "report": r, "text": rm.level_patch_text(r, f"{p['meta']['id']} (editor project)"),
            "declaration": decl}


def mod_paths():
    """The mod manager's own folders (r3hd_mods resolve_paths: R3HD_HOME / R3HD_GAME_DIR or the repository layout)."""
    import argparse
    return rm.resolve_paths(argparse.Namespace(home=None, mods_root=None, cache=None, game_dir=None))


def installed_mod_info(paths, mod_id):
    """G6-P63: what the mod manager holds under an id (read only): name, version, enabled, priority, source folder
    name and the installed files' SHA-256 (installed.json), or {} when nothing is installed under it."""
    info = {}
    try:
        state = rm.load_state(paths)
    except rm.Refusal:
        state = {"mods": []}
    ids = [e["id"] for e in state["mods"]]
    if mod_id in ids:
        info["enabled"] = state["mods"][ids.index(mod_id)]["enabled"]
        info["priority"] = ids.index(mod_id) + 1
    d = rm.installed_dir(paths, mod_id)
    if d.is_dir():
        info["folder"] = True
        try:
            rec = json.loads((d / "installed.json").read_text(encoding="utf-8"))
            info["source_name"], info["files"] = str(rec.get("source_name", "")), dict(rec.get("files") or {})
        except (OSError, ValueError, AttributeError, TypeError):
            pass
        try:
            m = json.loads((d / "mod.json").read_text(encoding="utf-8-sig"))
            info["name"], info["version"] = str(m.get("name", "")), str(m.get("version", ""))
        except (OSError, ValueError, AttributeError):
            pass
    return info


def import_mod(folder, paths=None, replace=False):
    """Import and enable an exported mod folder through the existing mod manager (r3hd_mods import --enable). The
    game applies it at its next start (plan); nothing else is changed. {"ok": True, "id", "mods"} or a refusal.
    G6-P63: an installed mod with the same id is replaced only with replace=True (the person's explicit choice, as
    the launcher's Mods page and `r3hd_mods import` without --replace); otherwise the refusal EXISTS describes the
    installed mod and nothing changes. Re-importing a byte-identical package is not a replacement and goes ahead.
    A replacement keeps the mod's priority (the mod manager's own rule)."""
    paths = paths or mod_paths()
    folder = Path(folder)
    try:
        r = rm.cmd_import(paths, folder, replace=replace, enable=True)
    except rm.Refusal as x:
        if x.code != "EXISTS":
            return {"ok": False, "code": x.code, "detail": x.detail, "advice": ""}
        info = installed_mod_info(paths, x.detail)
        try:
            same = bool(info.get("files")) and info["files"] == {
                rel: rm.sha256_bytes(b) for rel, b in rm.read_package(folder).items()}
        except rm.Refusal:
            same = False
        if not same:
            what = " ".join(v for v in (info.get("name") and repr(info["name"]), info.get("version") and
                                        f"version {info['version']}") if v) or "a mod"
            state = {True: "enabled", False: "disabled"}.get(info.get("enabled"), "not in the mod list")
            src = f", imported from a folder named {info['source_name']!r}" if info.get("source_name") else ""
            return {"ok": False, "code": "EXISTS", "existing": info, "mod_id": x.detail,
                    "detail": f"An installed mod already uses the id {x.detail}: {what} ({state}{src}). "
                              "Nothing was changed.",
                    "advice": "To keep both, give this project another mod id and export it again. To overwrite "
                              "the installed mod with this one, confirm the replacement (its priority is kept)."}
        try:
            r = rm.cmd_import(paths, folder, replace=True, enable=True)
        except rm.Refusal as y:
            return {"ok": False, "code": y.code, "detail": y.detail, "advice": ""}
        r["unchanged"] = True
    return {"ok": True, "result": r, "mods": str(paths["mods"])}


def export_declaration(p, path):
    atomic_write(path, (json.dumps(declaration(p), indent=1) + "\n").encode("utf-8"))


def export_mod(p, game_dir, out_dir):
    """Validate, then write a mod folder (mod.json) through the compiler. The mod is NOT imported or activated."""
    out_dir = Path(out_dir)
    if out_dir.exists() and (not out_dir.is_dir() or any(out_dir.iterdir())):
        return {"ok": False, "code": "USAGE", "detail": f"{out_dir} must be a new or empty folder", "advice": ""}
    return validate(copy.deepcopy(p), game_dir, out_dir)


# ================================================================================================ G6-P33 (D-289)
# Multi-level remix: actor and waypoint positions of existing levels, one level per project. Every edit is an existing
# in-place override of r3hd_mods (`actor-position` D-228 / D-229, `waypoint-position` D-231): same-size ranges the
# production overlay already serves; the compiler (compile_mod through cmd_validate / cmd_import) stays authoritative.
# Nothing here writes game bytes. A remix project never carries a level transaction: on intro_20 the terrain /
# FairyLight level patch stays a separate v1 project and a separate mod. The mod manager refuses an in-place range
# that overlaps a transaction's ranges (STRUCTURAL_CONFLICT) and accepts disjoint ones; the production overlay checks
# the transaction's declared image first and then serves other mods' disjoint ranges over it (m33_mod_overlay.h,
# G5-P3). No editable remix item overlaps the intro_20 production transaction (E-522); the combination is not
# runtime-tested.
REMIX_FORMAT = "r3hd-level-editor-project-v2"
REMIX_KEYS = {"format", "level", "target", "actors", "waypoints", "meta"}
ACTOR_KEYS = {"model", "instance", "matrix_sha256", "position"}
WAYPOINT_KEYS = {"model", "instance", "variable", "node", "waypoint_sha256", "position"}
# exact level identities: lvl / ptr equal the repository's existing pins (STRUCT_ALLOW intro_10 / intro_20,
# COLLISION_ALLOW intro_15); transit is the file the in-place readers also check for references
REMIX_LEVELS = {
    "intro_10": {"lvl": "a37638bf1370357db21f33df5c4d37ae806b3c4b9f81b331503ba62d1b19e2ee",
                 "ptr": "6c9dd70c488a1cac95efc0a55a6086255dae2d851bacd93f5abefdcc8200e940",
                 "transit": "d300ba3a4a3c03cec6a73eb9da8a8d820fcc3a669591e976b357e804315bf275",
                 "note": "flight level (E-461 lum placement and E-464 flight-graph waypoint verified here)"},
    "intro_15": {"lvl": "474596d68f86de3eba7f3cb19d1595abdc62b37252e2d6d13c6c83483416f4e2",
                 "ptr": "aaafc65cdf088e2fdb42425288a6f038e7bf7d99023f2aca3b828b231aa43457",
                 "transit": "7510ea812092bd4ccbe468ac4c85af01bca37d9491a01e787a3733ab1379afc8",
                 "note": "walking level (static collision file-backed, G6-P12 / G6-P13; script-placed bridge E-462)"},
    "intro_20": {"lvl": "a21aa7691db4cedb3892e685e5395fd23b530b0bde4d64a09035dfb5f2d0b11f",
                 "ptr": "be90b58a3bfa78d19f3335489edcc79214442d52cbde04c6ad5a465f9fb17cb1",
                 "transit": "51c0fbf1239acd6188316a6d64507761903d5a087df1ea717426d5cb810e6aa8",
                 "note": "walking level (graph C consumer measured, E-480; terrain / FairyLight in v1 level-patch "
                         "projects)"},
}
# G6-P66 (D-315): development-only level entries. Not part of the editor's supported levels: such a level is offered,
# opened, validated, exported or reopened only while R3HD_DEV_EDITOR_LEVELS names it (comma-separated) in the
# environment that started the editor; otherwise it is refused like any other level. Pinned by exact lvl / ptr /
# transit SHA-256 like REMIX_LEVELS. Edits are narrowed to the listed actor models (instances the compiler accepts),
# moves of at most `max_actor_move`, and no waypoints: every other actor and every graph is shown read-only (LOCKED).
DEV_LEVELS_ENV = "R3HD_DEV_EDITOR_LEVELS"
DEV_LEVELS = {
    "wood_10": {"lvl": "d2402e23f771143d5906569b9562abce5ba4c2af3b1f342106b394c1b5b0bedc",
                "ptr": "ead99e4313d3aceb54304a7bb5f221585bce97451545a7572c7997868eba6a1b",
                "transit": "f570b6ed498f2966f70efd94a3d82e8fb5d00038d578f7244d6e0cd37163a701",
                "note": "DEVELOPMENT ONLY (G6-P66): first post-intro level; Powerz / Chameleon positions only, "
                        "no waypoints",
                "actor_models": ("YAM_mPowerz", "NIK_mChameleon"), "waypoints": False, "max_actor_move": 5.0},
}


def dev_levels_enabled(env=None):
    """The DEV_LEVELS the environment enables (R3HD_DEV_EDITOR_LEVELS, comma-separated; unknown names ignored)."""
    v = (os.environ if env is None else env).get(DEV_LEVELS_ENV, "")
    return sorted({x.strip() for x in v.split(",")} & set(DEV_LEVELS))


def level_entry(level):
    """The pinned entry of an editable level: REMIX_LEVELS, or an enabled DEV_LEVELS entry; else EditorError."""
    if level in REMIX_LEVELS:
        return REMIX_LEVELS[level]
    if level in DEV_LEVELS and level in dev_levels_enabled():
        return DEV_LEVELS[level]
    if level in DEV_LEVELS:
        raise EditorError("UNSUPPORTED", f"level {level!r} is a development-only editor level; it needs "
                                         f"{DEV_LEVELS_ENV}={level} in the environment that started the editor")
    raise EditorError("UNSUPPORTED", f"level {level!r} (supported: {', '.join(REMIX_LEVELS)})")


def is_dev_level(level):
    return level in DEV_LEVELS and level not in REMIX_LEVELS


def remix_level_names():
    return list(REMIX_LEVELS) + [lv for lv in dev_levels_enabled() if lv not in REMIX_LEVELS]


def actor_move_limit(level):
    try:
        return float(level_entry(level).get("max_actor_move", MAX_ACTOR_MOVE))
    except EditorError:
        return MAX_ACTOR_MOVE


LUM10 = "lum\\NIN_m_Lums_Int10\\NIN_m_Lums_Int10.rul^CreateIntelligence^CreateComport:NIN_C_RedLums_Init"
# Runtime evidence, never inferred: only these exact items are VERIFIED. Everything else that the compiler accepts
# is EXPERIMENTAL (bytes verified, gameplay behaviour not measured).
# G6-P34 (D-290, E-523): runtime classes of exact tested items, keyed (level, model short name, instance):
#   verified   = placed, kept, and the expected interaction observed at the authored place
#   placement  = appeared at and kept the authored place in a production run; behaviour there not observed
#   supported  = (graphs) the consumer followed the moved waypoints, pre-registered judgement not fully met
#   script_overridden = the live position was replaced (none observed so far; such items would be refused)
# Untested items stay "experimental". One instance never promotes its whole model.
RUNTIME_ACTORS = {
    ("intro_10", "NIN_m_Lums_Int10", 0): ("verified", "E-461: placed exactly at the edited position (up to 25 units) "
                                                      "and collected by the flight there"),
    ("intro_10", "NIN_m_Lums_Int10", 1): ("verified", "E-523: appeared at and kept the authored position; the flight "
                                                      "collected it there (lum count +1)"),
    ("intro_10", "NIN_m_Lums_Int10", 3): ("verified", "E-523: appeared at and kept the authored position; the flight "
                                                      "collected it there (lum count +1)"),
    ("intro_10", "NIN_m_Lums_Int10", 4): ("placement", "E-523: appeared at and kept a position 23 units off the flight "
                                                       "path for 200 s; collection there not tested"),
    ("intro_10", "NIN_m_ToadIntro", 0): ("placement", "E-523: appeared at the authored position, then moved 0.16 units "
                                                      "by itself; its behaviour there was not observed"),
    ("intro_20", "NIK_mChameleon", 0): ("placement", "E-523: appeared at and kept the authored position (80 s); "
                                                     "behaviour there not observed"),
    ("intro_20", "YAM_mPowerz", 1): ("placement", "E-523: appeared at and kept the authored position (80 s); "
                                                  "behaviour there not observed"),
    ("intro_20", "Mic_mBoing2", 11): ("placement", "E-523: appeared at and kept the authored position (80 s); its "
                                                   "bounce / collision there was not tested"),
    ("intro_15", "NIK_mChameleon", 0): ("placement", "E-523: appeared at and kept the authored position (200 s); "
                                                     "behaviour there not observed"),
    ("intro_15", "ODA_mVerduleBase", 0): ("placement", "E-523: appeared at and kept the authored position (200 s); "
                                                       "behaviour there not observed"),
}
RUNTIME_GRAPHS = {
    ("intro_10", "NIN_m_GenFlyIntro_10", 0, 0): ("verified", "E-464: the flight steers toward a waypoint moved 6 "
                                                             "units"),
    ("intro_20", "NIN_m_FairyLight", 2, 2): ("supported", "E-523: original FairyLight 2 reached each moved waypoint "
                                                          "within 0.29 and arrived 3-4 times at every node of the "
                                                          "edited loop; the pre-registered judgement failed on an "
                                                          "unmoved node (0.354 > 0.30)"),
    ("intro_15", "NIN_m_MurfyIntro15", 0, 0): ("experimental", "E-523: the edited waypoints were served and read back, "
                                                               "but no actor was seen using this graph in 200 s"),
}
VERIFIED_ACTORS = {k: v[1] for k, v in RUNTIME_ACTORS.items() if v[0] == "verified"}   # compatibility view
MAX_ACTOR_MOVE = 25.0      # E-461 control: an actor placed 25 units away stood exactly there
MAX_WAYPOINT_MOVE = 6.0    # E-464 / E-480: the largest waypoint displacement the guest has executed
MAX_REMIX_EDITS = 512


def _target_fn(lvl, slots, me=1):
    def target(o):
        if slots.get(o) != me or o + 4 > len(lvl):
            return None
        t = struct.unpack_from(">I", lvl, o)[0] + 4
        return t if t < len(lvl) else None
    return target


def level_collision(lvl, slots):
    """(triangles, meshes): world-space static collision triangles [(a, b, c)], a, b, c = (x, y, z), and the number of
    distinct zdr meshes drawn.
    Read-only display data. The walk is the G6-P12 file audit's (E-498; layout VERIFIED against retained snapshots):
    IPO / IPO_2 SuperObject +4 -> data +0 -> PhysicalObject +4 -> collide set +0xC -> zdr mesh {+0 u16 vertices,
    +2 u16 elements, +8 vertices, +0xC element types, +0x10 elements}; triangle element {+4 indices, +0xC u16 count};
    world matrix = the SuperObject's matrix (+0x20, 4 x 4 floats column by column at +4) times every parent's (+0x1C).
    A mesh whose links do not decode is skipped, never guessed."""
    target = _target_fn(lvl, slots)
    U32 = lambda o: struct.unpack_from(">I", lvl, o)[0]   # noqa: E731

    def world(so):
        w = [[1.0 if r == c else 0.0 for c in range(4)] for r in range(4)]
        depth = 0
        while so is not None and depth < 32:
            mp = target(so + 0x20)
            if mp is not None and mp + 0x44 <= len(lvl):
                f = struct.unpack_from(">16f", lvl, mp + 4)
                m = [[f[4 * c + r] for c in range(4)] for r in range(4)]
                w = [[sum(m[r][k] * w[k][c] for k in range(4)) for c in range(4)] for r in range(4)]
            so, depth = target(so + 0x1C), depth + 1
        return w

    tris, seen, meshes = [], set(), set()
    for f in sorted(slots):
        so = f - 4
        if f % 4 or so < 0 or so + 0x24 > len(lvl) or U32(so) not in (0x20, 0x40):
            continue
        data = target(so + 4)
        po = target(data) if data is not None else None
        cs = target(po + 4) if po is not None else None
        zdr = target(cs + 0xC) if cs is not None else None
        if zdr is None or (zdr, so) in seen:
            continue
        seen.add((zdr, so))
        nv, ne = struct.unpack_from(">HH", lvl, zdr)
        vo, to, eo = target(zdr + 8), target(zdr + 0xC), target(zdr + 0x10)
        if not nv or not ne or ne > 512 or None in (vo, to, eo) or vo + 12 * nv > len(lvl):
            continue
        verts = [struct.unpack_from(">3f", lvl, vo + 12 * i) for i in range(nv)]
        if not all(math.isfinite(c) for v in verts for c in v):
            continue
        w = world(so)
        wv = [tuple(w[r][0] * v[0] + w[r][1] * v[1] + w[r][2] * v[2] + w[r][3] for r in range(3)) for v in verts]
        for i, t in enumerate(struct.unpack_from(f">{ne}H", lvl, to)):
            blk = target(eo + 4 * i)
            if t != 1 or blk is None:
                continue
            ix_ = target(blk + 4)
            nt = struct.unpack_from(">H", lvl, blk + 0xC)[0]
            if ix_ is None or ix_ + 6 * nt > len(lvl):
                continue
            idx = struct.unpack_from(f">{3 * nt}H", lvl, ix_)
            if any(k >= nv for k in idx):
                continue
            tris += [(wv[idx[3 * j]], wv[idx[3 * j + 1]], wv[idx[3 * j + 2]]) for j in range(nt)]
            meshes.add(zdr)
    return tris, len(meshes)


def short_name(key):
    parts = key.split("\\")
    return parts[1] if len(parts) > 2 else key.split("^")[0]


def _matches(spec_key, level, key):
    """VERIFIED_GRAPHS keys name a model by folder and behaviour suffix (as the E-464 harness found it)."""
    lv, model, suffix = spec_key[:3]
    return lv == level and key.endswith(suffix) and f"\\{model}\\" in key


class RemixModel:
    """Read-only actors, graphs and collision of one supported level from the person's files. Eligibility comes only
    from the compiler's own readers (read_script_index -> placement_rows / waypoint_rows, D-229 refusal)."""

    view_only = False

    def __init__(self, game_dir, level):
        entry = self._entry(level)
        self.level, self.game = level, Path(game_dir)
        self.dev = not self.view_only and is_dev_level(level)
        self.max_actor_move = 0.0 if self.view_only else actor_move_limit(level)
        try:
            lvl_p, ptr_p, _ = rm.script_level_files(self.game, level)
            files = {"lvl": lvl_p, "ptr": ptr_p, "transit": lvl_p.with_name("transit.lvl")}
            raw = {k: p.read_bytes() for k, p in files.items()}
        except OSError as x:
            raise EditorError("TARGET_MISSING", f"the {level} level files were not found under {self.game} ({x})")
        self.hashes = {k: rm.sha256_bytes(b) for k, b in raw.items()}
        bad = [k for k in ("lvl", "ptr", "transit") if entry is not None and self.hashes[k] != entry[k]]
        if bad:
            raise EditorError("TARGET_CHANGED", f"{level}: these files are not the exact supported originals: "
                              + ", ".join(f"{k} {self.hashes[k][:8]}... (expected {entry[k][:8]}...)"
                                          for k in bad))
        try:
            ix = rm.read_script_index(self.game, level)
        except rm.Refusal as x:
            raise EditorError(x.code, x.detail)
        self.ix, self.lvl = ix, ix["data"]
        self.tris, self.meshes = level_collision(self.lvl, ix["slots"])
        self.actors, self.graphs = {}, {}
        for key, insts in sorted(ix["placements"].items()):
            if insts is None:
                continue
            rows = rm.placement_rows(ix, insts, key)
            for row, inst in zip(rows, insts):
                m = inst["matrix"]
                if m is None or m + rm.PLACEMENT_SIZE > len(self.lvl):
                    continue                              # not placed in this file: nothing to show
                pos = struct.unpack_from(">3f", self.lvl, m + 0x34)
                if not all(math.isfinite(c) for c in pos):
                    continue
                ident = (key, row["instance"])
                a = {"key": key, "instance": row["instance"], "name": short_name(key), "position": pos,
                     "matrix_sha256": row.get("matrix_sha256")}
                rt = RUNTIME_ACTORS.get((level, a["name"], row["instance"]))
                if "cannot_change" in row:
                    a["status"], a["why"] = "locked", row["cannot_change"]
                elif rt:
                    a["status"], a["why"] = rt
                else:
                    a["status"], a["why"] = "experimental", (
                        "the compiler accepts this actor (exact matrix, single snapshot, model does not set positions "
                        "by script), but its gameplay behaviour at a new position has not been measured")
                self.actors[ident] = a
        target = _target_fn(self.lvl, ix["slots"])
        for (key, n, var), e in sorted(ix["graphs"].items()):
            nodes = []
            for i, (nd, w) in enumerate(e["nodes"]):
                if w is None or w + rm.WAYPOINT_SIZE > len(self.lvl):
                    nodes.append(None)
                    continue
                d = self.lvl[w:w + rm.WAYPOINT_SIZE]
                why = e["safe"] or e["wsafe"].get(i, "")
                nodes.append({"node": i, "position": struct.unpack(">3f", d[:12]), "why": why,
                              "waypoint_sha256": None if why else rm.sha256_bytes(d)})
            index = {nd: i for i, (nd, _) in enumerate(e["nodes"])}
            edges = set()
            for i, (nd, _) in enumerate(e["nodes"]):   # arc list +0x18 -> arcs {+0 next, +0xC -> node} (G5-P1)
                a, k = target(target(nd + 0x18)) if target(nd + 0x18) is not None else None, 0
                while a is not None and k < 16:
                    j = index.get(target(a + 0xC))
                    if j is not None:
                        edges.add((i, j))
                    a, k = target(a), k + 1
            g = {"key": key, "instance": n, "variable": var, "name": short_name(key), "nodes": nodes,
                 "edges": sorted(edges), "graph_offset": e["graph"]}
            rt = RUNTIME_GRAPHS.get((level, g["name"], n, var))
            if e["safe"]:
                g["status"], g["why"] = "locked", e["safe"]
            elif rt and rt[0] != "experimental":
                g["status"], g["why"] = rt
            else:
                g["status"], g["why"] = "experimental", (rt[1] + "; " if rt else "") + (
                    "the compiler accepts these waypoints (owned by one actor, unshared), but no measurement shows "
                    "that an active actor follows this graph at the new positions")
            self.graphs[(key, n, var)] = g
        if self.dev:
            self._narrow_dev(entry)
        if self.view_only:
            self._lock_all()

    def _entry(self, level):
        return level_entry(level)

    def _lock_all(self):
        pass

    def _narrow_dev(self, entry):
        """G6-P66 (D-315): a development level edits only its listed actor models, never waypoints."""
        allowed = set(entry.get("actor_models", ()))
        for a in self.actors.values():
            if a["status"] in ("locked", "script_overridden"):
                continue
            if a["name"] not in allowed:
                a["status"], a["why"] = "locked", (
                    f"view only: {self.level} is a development-only editor level whose edits are limited to "
                    f"{' / '.join(sorted(allowed))} positions (G6-P66)")
            else:
                a["why"] = (f"DEVELOPMENT ONLY ({self.level}, G6-P66): " + a["why"]
                            + f"; moves of at most {self.max_actor_move:g} units")
        if not entry.get("waypoints"):
            for g in self.graphs.values():
                if g["status"] != "locked":
                    g["status"], g["why"] = "locked", (f"view only: waypoints of the development-only level "
                                                       f"{self.level} are not editable (G6-P66)")

    def ground_index(self):
        """G6-P35: the ground-like static collision on a grid (built once per loaded level)."""
        if getattr(self, "_ground", None) is None:
            self._ground = GroundIndex(self.tris)
        return self._ground

    def counts(self):
        a = [x["status"] for x in self.actors.values()]
        wp = [(g["status"], nd) for g in self.graphs.values() for nd in g["nodes"] if nd]
        return {"actors": len(a), "actors_verified": a.count("verified"), "actors_placement": a.count("placement"),
                "actors_experimental": a.count("experimental"),
                "actors_locked": a.count("locked"), "graphs": len(self.graphs),
                "waypoints": len(wp), "waypoints_editable": sum(1 for s, nd in wp if s != "locked" and not nd["why"]),
                "triangles": len(self.tris), "meshes": self.meshes}


# G6-P68 (D-317): read-only level browsing in the Experimental 3D Level Viewer. A view-only level is never an editor
# level: no project, no validation, no export, no import. The catalog (r3hd_view_levels.json beside this module) is
# written by tools/g6p68_view_catalog_check.py from measurements of the person's own files and records, per level, the
# exact lvl / ptr / transit SHA-256 that was measured and what the viewer showed. Levels the editor can edit (the
# supported intros, and a development level while its variable enables it) are not offered as view-only.
VIEW_CATALOG_FILE = Path(__file__).resolve().with_name("r3hd_view_levels.json")
VIEW_CATALOG_FORMAT = "r3hd-view-levels-v1"
VIEW_ENTRY_KEYS = {"lvl", "ptr", "transit", "class", "reason", "measured", "limits"}


def _level_name_ok(level):
    return (isinstance(level, str) and 0 < len(level) <= 32 and level[0].isalpha()
            and all(c.isascii() and (c.isalnum() or c == "_") for c in level) and level == level.lower())


def load_view_catalog(path=None):
    """{level: entry} of the read-only catalog; {} if the file is absent or malformed (the viewer then offers only the
    editor's own levels). Never raises."""
    try:
        d = json.loads(Path(path or VIEW_CATALOG_FILE).read_text(encoding="utf-8"))
        if not isinstance(d, dict) or d.get("format") != VIEW_CATALOG_FORMAT or not isinstance(d.get("levels"), dict):
            return {}
        out = {}
        for lv, e in d["levels"].items():
            if (_level_name_ok(lv) and isinstance(e, dict) and set(e) == VIEW_ENTRY_KEYS
                    and e["class"] in ("view", "excluded")
                    and all(isinstance(e[k], str) and len(e[k]) == 64 for k in ("lvl", "ptr"))):
                out[lv] = e
        return out
    except (OSError, ValueError, UnicodeDecodeError):
        return {}


_VIEW_CATALOG = None


def view_catalog():
    global _VIEW_CATALOG
    if _VIEW_CATALOG is None:
        _VIEW_CATALOG = load_view_catalog()
    return _VIEW_CATALOG


def view_level_names(catalog=None):
    """Levels the 3D viewer offers as VIEW ONLY: catalogued as viewable and not editable in this process."""
    cat = view_catalog() if catalog is None else catalog
    editable = set(remix_level_names())
    return sorted(lv for lv, e in cat.items() if e["class"] == "view" and lv not in editable)


class ViewModel(RemixModel):
    """G6-P68 (D-317): actors, graphs and collision of any level, read with the editor's own readers but never
    editable: every actor and graph is LOCKED ("view only"), the compiler's own verdict is kept as `compiler_status`
    for display. No identity pin is required; `identity` says whether the files are the catalogued measured copy."""
    view_only = True

    def _entry(self, level):
        if not _level_name_ok(level):
            raise EditorError("UNSUPPORTED", f"level name {level!r}")
        return None

    def _lock_all(self):
        why = f"view only: {self.level} is not an editor level; the 3D viewer only shows it (G6-P68)"
        for a in self.actors.values():
            a["compiler_status"], a["compiler_why"] = a["status"], a["why"]
            a["status"], a["why"] = "locked", why
        for g in self.graphs.values():
            g["compiler_status"], g["compiler_why"] = g["status"], g["why"]
            g["status"], g["why"] = "locked", why
        e = view_catalog().get(self.level)
        if e is None:
            self.identity = "uncatalogued"
        else:
            same = all(self.hashes[k] == e[k] for k in ("lvl", "ptr", "transit") if e[k])
            self.identity = "measured" if same else "differs"


def new_remix(level):
    level_entry(level)
    return {"format": REMIX_FORMAT, "level": level, "target": remix_target(level), "actors": [], "waypoints": [],
            "meta": {"id": f"custom.{level.replace('_', '')}-remix", "name": f"Untitled {level} remix",
                     "description": ""}}


def remix_target(level):
    e = level_entry(level)
    return {f"{k}_sha256": e[k] for k in ("lvl", "ptr", "transit")}


def _pos(v, where):
    if not isinstance(v, list) or len(v) != 3 or not all(_num(c) for c in v):
        raise EditorError("BAD_PROJECT", f"{where}: position must be [x, y, z] (finite numbers)")
    return [f32(float(c)) for c in v]


def _idx(v, where, name):
    if not isinstance(v, int) or isinstance(v, bool) or not 0 <= v < 4096:
        raise EditorError("BAD_PROJECT", f"{where}: '{name}' must be an index 0..4095")
    return v


def check_remix(p):
    """Strict structure of a v2 remix project (no game data needed). Returns the canonical form: actors and waypoints
    sorted by identity, positions as float32 values. Identity, eligibility and bounds against the level are checked by
    check_remix_level (with a RemixModel) and again by the compiler."""
    if not isinstance(p, dict):
        raise EditorError("BAD_PROJECT", "a project must be a JSON object")
    if p.get("format") != REMIX_FORMAT:
        raise EditorError("UNSUPPORTED", f"project format {p.get('format')!r} (expected {REMIX_FORMAT})")
    if set(p) != REMIX_KEYS:
        raise EditorError("BAD_PROJECT", f"unknown keys {sorted(set(p) - REMIX_KEYS)}, missing "
                                         f"{sorted(REMIX_KEYS - set(p))}")
    if not isinstance(p["level"], str):
        raise EditorError("UNSUPPORTED", f"level {p['level']!r} (supported: {', '.join(REMIX_LEVELS)})")
    entry = level_entry(p["level"])
    if p["target"] != remix_target(p["level"]):
        raise EditorError("UNSUPPORTED", f"the project's target hashes are not the supported {p['level']} originals")
    if not isinstance(p["actors"], list) or not isinstance(p["waypoints"], list):
        raise EditorError("BAD_PROJECT", "'actors' and 'waypoints' must be lists")
    if len(p["actors"]) + len(p["waypoints"]) > MAX_REMIX_EDITS:
        raise EditorError("UNSUPPORTED", f"at most {MAX_REMIX_EDITS} edits per project")
    actors, seen = [], set()
    for i, a in enumerate(p["actors"]):
        where = f"actor edit {i}"
        if not isinstance(a, dict) or set(a) != ACTOR_KEYS:
            raise EditorError("BAD_PROJECT", f"{where}: needs exactly {sorted(ACTOR_KEYS)}")
        if not isinstance(a["model"], str) or not 3 <= len(a["model"]) < 0x100:
            raise EditorError("BAD_PROJECT", f"{where}: 'model' must be the model key")
        if not isinstance(a["matrix_sha256"], str) or len(a["matrix_sha256"]) != 64:
            raise EditorError("BAD_PROJECT", f"{where}: 'matrix_sha256' must be a SHA-256")
        ident = (a["model"], _idx(a["instance"], where, "instance"))
        if ident in seen:
            raise EditorError("BAD_PROJECT", f"{where}: the same actor is edited twice")
        seen.add(ident)
        actors.append({"model": a["model"], "instance": a["instance"], "matrix_sha256": a["matrix_sha256"],
                       "position": _pos(a["position"], where)})
    wps, seen = [], set()
    for i, w in enumerate(p["waypoints"]):
        where = f"waypoint edit {i}"
        if not isinstance(w, dict) or set(w) != WAYPOINT_KEYS:
            raise EditorError("BAD_PROJECT", f"{where}: needs exactly {sorted(WAYPOINT_KEYS)}")
        if not isinstance(w["model"], str) or not 3 <= len(w["model"]) < 0x100:
            raise EditorError("BAD_PROJECT", f"{where}: 'model' must be the model key")
        if not isinstance(w["waypoint_sha256"], str) or len(w["waypoint_sha256"]) != 64:
            raise EditorError("BAD_PROJECT", f"{where}: 'waypoint_sha256' must be a SHA-256")
        ident = (w["model"], _idx(w["instance"], where, "instance"), _idx(w["variable"], where, "variable"),
                 _idx(w["node"], where, "node"))
        if ident in seen:
            raise EditorError("BAD_PROJECT", f"{where}: the same waypoint is edited twice")
        seen.add(ident)
        wps.append({"model": w["model"], "instance": w["instance"], "variable": w["variable"], "node": w["node"],
                    "waypoint_sha256": w["waypoint_sha256"], "position": _pos(w["position"], where)})
    if is_dev_level(p["level"]):   # G6-P66 (D-315): the development level's narrow edit class, before any game data
        allowed = set(entry.get("actor_models", ()))
        for a in actors:
            if short_name(a["model"]) not in allowed:
                raise EditorError("UNSUPPORTED", f"actor {short_name(a['model'])} #{a['instance']}: {p['level']} "
                                                 f"(development only) edits only {' / '.join(sorted(allowed))}")
        if wps and not entry.get("waypoints"):
            raise EditorError("UNSUPPORTED", f"{p['level']} (development only) has no editable waypoints")
    m = p["meta"]
    if not isinstance(m, dict) or set(m) != META_KEYS:
        raise EditorError("BAD_PROJECT", f"'meta' needs exactly {sorted(META_KEYS)}")
    if not isinstance(m["id"], str) or not rm.ID_RE.match(m["id"]):
        raise EditorError("BAD_PROJECT", "meta.id must be a mod id (lower case a-z 0-9 . _ -, 2-64 characters)")
    for k in ("name", "description"):
        if not isinstance(m[k], str) or len(m[k]) > 200 or not all(32 <= ord(c) < 127 for c in m[k]):
            raise EditorError("BAD_PROJECT", f"meta.{k} must be at most 200 printable ASCII characters")
    return {"format": REMIX_FORMAT, "level": p["level"], "target": remix_target(p["level"]),
            "actors": sorted(actors, key=lambda a: (a["model"], a["instance"])),
            "waypoints": sorted(wps, key=lambda w: (w["model"], w["instance"], w["variable"], w["node"])),
            "meta": dict(m)}


def check_remix_level(p, model):
    """Every edit against the loaded level: the item exists, is editable, carries the original's hash, and lies within
    the evidence bound of its original position. Returns [] or a list of problems (the export refuses on any)."""
    p = check_remix(p)
    if model is None or model.level != p["level"]:
        return [f"the {p['level']} level is not loaded"]
    if getattr(model, "view_only", False):                 # G6-P68: a view-only model never validates an edit
        return [f"the {p['level']} level is loaded view only (G6-P68); it cannot validate edits"]
    out = []
    for a in p["actors"]:
        x = model.actors.get((a["model"], a["instance"]))
        name = f"actor {short_name(a['model'])} #{a['instance']}"
        if x is None:
            out.append(f"{name}: not in this level")
        elif x["status"] in ("locked", "script_overridden"):
            out.append(f"{name}: {x['status'].replace('_', '-')} ({x['why']}); revert this edit to export the rest "
                       "of the project")
        elif x["matrix_sha256"] != a["matrix_sha256"]:
            out.append(f"{name}: the project was made for a different actor matrix")
        elif math.dist(a["position"], x["position"]) > actor_move_limit(p["level"]) + 1e-4:
            out.append(f"{name}: moved {math.dist(a['position'], x['position']):.3f} units (at most "
                       f"{actor_move_limit(p['level']):g})")
    for w in p["waypoints"]:
        g = model.graphs.get((w["model"], w["instance"], w["variable"]))
        nd = g["nodes"][w["node"]] if g and w["node"] < len(g["nodes"]) else None
        name = f"waypoint {short_name(w['model'])} #{w['instance']} var {w['variable']} node {w['node']}"
        if nd is None:
            out.append(f"{name}: not in this level")
        elif g["status"] == "locked" or nd["why"]:
            out.append(f"{name}: locked ({g['why'] if g['status'] == 'locked' else nd['why']})")
        elif nd["waypoint_sha256"] != w["waypoint_sha256"]:
            out.append(f"{name}: the project was made for a different waypoint")
        elif math.dist(w["position"], nd["position"]) > MAX_WAYPOINT_MOVE + 1e-4:
            out.append(f"{name}: moved {math.dist(w['position'], nd['position']):.3f} units (at most "
                       f"{MAX_WAYPOINT_MOVE:g})")
    return out


def remix_manifest(p, paths):
    """The mod.json (format 1) of a remix project: one `actor-position` / `waypoint-position` override per edit, in
    canonical order. Deterministic: the same project gives the same bytes."""
    p = check_remix(p)
    ov = [{"type": "actor-position", "level": p["level"], "model": a["model"], "instance": a["instance"],
           "matrix_sha256": a["matrix_sha256"], "position": a["position"]} for a in p["actors"]]
    ov += [{"type": "waypoint-position", "level": p["level"], "model": w["model"], "instance": w["instance"],
            "variable": w["variable"], "node": w["node"], "waypoint_sha256": w["waypoint_sha256"],
            "position": w["position"]} for w in p["waypoints"]]
    m = {"format": rm.FORMAT, "id": p["meta"]["id"], "name": p["meta"]["name"] or p["meta"]["id"], "version": "1.0.0",
         "description": p["meta"]["description"] or _remix_description(p["level"], len(p["actors"]),
                                                                       len(p["waypoints"])),
         "target": {"title_id": rm.TITLE_ID, "releases": rm.release_ids(paths), "min_port_version": "0.0.1"},
         "overrides": ov}
    return m


def manifest_bytes(m):
    return (json.dumps(m, indent=1) + "\n").encode("utf-8")


def validate_remix(p, game_dir, out_dir=None, model=None):
    """Compile the project's manifest with the mod manager's own compiler (cmd_validate: parse_manifest + compile_mod).
    {"ok": True, "ranges", "report", "manifest"} or {"ok": False, "code", "detail", "advice"}. Writes nothing unless
    out_dir (a new or empty folder), and then only mod.json after the whole mod compiled."""
    try:
        p = check_remix(p)
        if model is not None:
            probs = check_remix_level(p, model)
            if probs:
                return {"ok": False, "code": "UNSUPPORTED", "detail": "\n".join(probs), "advice": ""}
        if not p["actors"] and not p["waypoints"]:
            return {"ok": False, "code": "EMPTY", "detail": "the project has no edits", "advice": "Move an actor or a "
                    "waypoint first."}
    except EditorError as x:
        return {"ok": False, "code": x.code, "detail": x.detail, "advice": ""}
    if out_dir is not None:
        out_dir = Path(out_dir)
        if out_dir.exists() and (not out_dir.is_dir() or any(out_dir.iterdir())):
            return {"ok": False, "code": "USAGE", "detail": f"{out_dir} must be a new or empty folder", "advice": ""}
    mp = mod_paths()
    with tempfile.TemporaryDirectory(prefix="r3hd-remix-") as td:
        paths = {"home": mp["home"], "game": Path(game_dir), "mods": Path(td) / "mods", "cache": Path(td) / "cache"}
        m = remix_manifest(p, paths)
        pkg = Path(td) / "pkg"
        pkg.mkdir()
        (pkg / "mod.json").write_bytes(manifest_bytes(m))
        try:
            r = rm.cmd_validate(paths, pkg)
            files = rm.read_package(pkg)
            ranges = rm.compile_mod(rm.parse_manifest(files), files, paths)
        except rm.Refusal as x:
            return {"ok": False, "code": x.code, "detail": x.detail, "advice": ""}
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        atomic_write(out_dir / "mod.json", manifest_bytes(m))
    lines = [f"{p['level']} remix '{p['meta']['id']}': {len(p['actors'])} actor and {len(p['waypoints'])} waypoint "
             f"edit(s) -> {r['ranges']} same-size range(s) in {p['level']}.lvl",
             "Production: in-place actor-position / waypoint-position ranges (no level transaction, no growth); the "
             "mod is marked as changing game logic (no new achievements while it is enabled, D-224).",
             "Gameplay: only items marked VERIFIED have runtime evidence; EXPERIMENTAL items are byte-verified only."]
    if is_dev_level(p["level"]):
        lines.insert(0, f"DEVELOPMENT ONLY ({DEV_LEVELS_ENV}): {p['level']} is not a supported editor level; this "
                        "export is for development testing, not for players (G6-P66, D-315).")
    lines += [f"  {Path(f).name} +0x{o:X} {len(d)} bytes  {w}" for f, o, d, w in ranges]
    return {"ok": True, "ranges": r["ranges"], "report": r, "manifest": m, "text": "\n".join(lines) + "\n",
            "range_list": [(Path(f).name, o, d.hex(), w) for f, o, d, w in ranges]}


def save_remix(p, path):
    atomic_write(path, (json.dumps(check_remix(p), indent=1) + "\n").encode("utf-8"))


def load_any(path):
    """("v1", level-patch project) or ("v2", remix project) from a project file; v1 files load unchanged."""
    raw = Path(path).read_bytes()
    if len(raw) > MAX_PROJECT_BYTES * 4:
        raise EditorError("BAD_PROJECT", f"the project file is larger than {MAX_PROJECT_BYTES * 4} bytes")
    try:
        p = rm._terrain_json(raw, Path(path).name)
    except rm.Refusal as x:
        raise EditorError("BAD_PROJECT", x.detail)
    if isinstance(p, dict) and p.get("format") == REMIX_FORMAT:
        return "v2", check_remix(p)
    if isinstance(p, dict) and p.get("format") == rm.FORMAT and "overrides" in p:
        raise EditorError("UNSUPPORTED", "this is an exported mod (mod.json), not a project file; open it with "
                                         "File > Open to edit it as a new project")
    if len(raw) > MAX_PROJECT_BYTES:
        raise EditorError("BAD_PROJECT", f"the project file is larger than {MAX_PROJECT_BYTES} bytes")
    return "v1", check_project(p)


# ================================================================================================ G6-P63
# Reopening an exported editor mod. An export carries everything its project held except, for a level patch, the
# project's display name: a remix mod.json has one actor-position / waypoint-position override per edit, and a
# level-patch mod.json embeds the editor's exact level-patch-v1 declaration. A mod is reopened only when re-exporting
# the reopened project would give the same manifest (apart from target.releases, which names the installation's
# release); anything else - a hand-edited, merged or foreign manifest, other override types, extra package files - is
# refused, because editing it here would silently drop or rewrite content. The reopened project has no file path:
# Save asks for a project file and never writes over the mod.json. Nothing is written or imported.
REMIX_OVERRIDES = {"actor-position", "waypoint-position"}


def _remix_description(level, n_actors, n_waypoints):
    """The description remix_manifest generates for a project without one."""
    dev = " - DEVELOPMENT ONLY, not verified in game (G6-P66)" if is_dev_level(level) else ""
    return f"{level} remix: {n_actors} actor and {n_waypoints} waypoint position(s){dev}"


def _without_releases(m):
    t = m.get("target")
    return {**m, "target": {**t, "releases": None}} if isinstance(t, dict) else m


def project_from_mod(path):
    """("v1" | "v2", project) from an editor-exported mod: a mod folder or its mod.json. Refusals are EditorError:
    NOT_EDITOR_MOD (not an export this editor can reproduce), or the mod manager's own package / manifest codes."""
    path = Path(path)
    folder = path if path.is_dir() else path.parent
    if not path.is_dir() and path.name.lower() != "mod.json":
        raise EditorError("NOT_EDITOR_MOD", f"{path.name}: an exported mod is a folder with a mod.json")
    try:
        files = rm.read_package(folder)
        rm.parse_manifest(dict(files))
    except rm.Refusal as x:
        raise EditorError(x.code, x.detail)
    m = json.loads(files["mod.json"].decode("utf-8-sig"))
    extra = set(files) - {"mod.json"}
    if extra == {"installed.json"}:   # a mod manager's installed copy: its own record, not package content
        try:
            rec = json.loads(files["installed.json"].decode("utf-8"))
            if isinstance(rec, dict) and rec.get("schema") == 1 and rec.get("id") == m["id"]:
                extra = set()
        except (UnicodeDecodeError, ValueError):
            pass
    if extra:
        raise EditorError("NOT_EDITOR_MOD", f"the mod has files the editor does not make ({', '.join(sorted(extra))})"
                                            "; reopening it would drop them")
    types = sorted({o.get("type") for o in m["overrides"]})
    if set(types) <= REMIX_OVERRIDES:
        kind, p = "v2", _remix_from_manifest(m)
        expected = remix_manifest(p, mod_paths())
    elif types == ["level-patch"] and len(m["overrides"]) == 1:
        kind, p = "v1", _patch_from_manifest(m)
        decl = declaration(p)
        expected = {"format": rm.FORMAT, "id": decl["id"], "name": f"Level patch {decl['id']}", "version": "1.0.0",
                    "description": decl.get("description", "") or f"{rm.LEVEL_PATCH_FORMAT} {decl['id']}",
                    "target": {"title_id": rm.TITLE_ID, "releases": None, "min_port_version": "0.0.1"},
                    "overrides": [{"type": "level-patch", "patch": decl}]}   # as r3hd_mods.cmd_level_patch writes it
    else:
        raise EditorError("NOT_EDITOR_MOD", f"the mod's overrides ({', '.join(map(str, types))}) are not an editor "
                                            "export (remix: actor-position / waypoint-position; level patch: one "
                                            "level-patch)")
    if _without_releases(expected) != _without_releases(m):
        diff = sorted(k for k in set(m) | set(expected)
                      if _without_releases(m).get(k) != _without_releases(expected).get(k))
        raise EditorError("NOT_EDITOR_MOD", f"the mod.json differs from what the editor would export for it "
                                            f"({', '.join(diff)}); it was changed by hand or made elsewhere, and "
                                            "editing it here would rewrite those parts")
    return kind, p


def _remix_from_manifest(m):
    ov = m["overrides"]
    levels = sorted({o.get("level") for o in ov})
    if len(levels) != 1 or levels[0] not in remix_level_names():
        if len(levels) == 1 and is_dev_level(levels[0]):
            level_entry(levels[0])   # raises: a development-only level that this environment does not enable
        raise EditorError("NOT_EDITOR_MOD", f"a remix mod edits exactly one of {', '.join(remix_level_names())} "
                                            f"(this one: {', '.join(map(str, levels))})")
    level = levels[0]
    try:
        actors = [{k: o[k] for k in ACTOR_KEYS} for o in ov if o["type"] == "actor-position"]
        wps = [{k: o[k] for k in WAYPOINT_KEYS} for o in ov if o["type"] == "waypoint-position"]
    except KeyError as x:
        raise EditorError("NOT_EDITOR_MOD", f"an override lacks {x.args[0]!r}")
    desc = m.get("description", "")
    if desc == _remix_description(level, len(actors), len(wps)):
        desc = ""    # the export's generated text, regenerated from the edits on the next export
    return check_remix({"format": REMIX_FORMAT, "level": level, "target": remix_target(level), "actors": actors,
                        "waypoints": wps, "meta": {"id": m["id"], "name": m["name"], "description": desc}})


def _patch_from_manifest(m):
    d = m["overrides"][0]["patch"]
    try:
        comps = {c["type"]: c for c in d["components"]}
        tp = comps["terrain"]["patch"]
        groups = tp["groups"]
        terrain = {}
        for g in groups:
            if g["name"] != f"vertex-{g['vertices'][0]}" or len(g["vertices"]) != 1:
                raise EditorError("NOT_EDITOR_MOD", "the terrain groups are not the editor's one-vertex groups")
            terrain[str(g["vertices"][0])] = g["delta_z"]
        route = {str(w["node"]): w["offset"] for w in comps.get("route", {}).get("waypoints", [])}
        p = {"format": PROJECT_FORMAT, "level": d["level"], "target": targets(), "region": tp["region"],
             "terrain": terrain, "route": route,
             "fairylight": {"follow_graph_of": comps["fairylight"]["follow_graph_of"]},
             "meta": {"id": d["id"], "name": m["name"], "description": d.get("description", "")}}
    except (KeyError, TypeError, IndexError, AttributeError) as x:
        raise EditorError("NOT_EDITOR_MOD", f"the level patch is not an editor declaration ({x!r})")
    return check_project(p)


def open_file(path):
    """(kind, project, source) for File > Open: a project file ("project") or an exported editor mod ("mod")."""
    path = Path(path)
    if path.is_dir() or path.name.lower() == "mod.json":
        return project_from_mod(path) + ("mod",)
    return load_any(path) + ("project",)


# ================================================================================================ G6-P35 (D-291)
# Placement assistance from the decoded static collision (read-only, advisory). Nothing here changes what the compiler
# accepts: warnings and ground observations are computed beside the project, never written into it, and a snap only
# proposes a position that then goes through the normal bounded edit (and later the compiler) like a typed one.
# Assumptions, stated in the report: z is up (the intro_20 terrain rules and every runtime trace use it); triangle
# winding is NOT trusted (the decoded meshes mix both orientations), so a surface is any triangle with |normal z| >=
# GROUND_MIN_NZ, whichever side faces up; only the static file-backed collision is known (no dynamic platforms, no
# script-placed geometry, no terrain-patch heights); a prediction never says how an actor behaves.
GROUND_MIN_NZ = 0.5        # ground-like: slope at most 60 degrees
SNAP_MIN_NZ = 0.7          # snap target: slope at most about 45 degrees
SNAP_DOWN, SNAP_UP = 4.0, 1.0   # vertical search window around the point for a snap target
SAME_SURFACE = 0.05        # surfaces closer than this at one x / y are one surface (shared edges, duplicated meshes)
NEAR_COLLISION = 6.0       # horizontal reach of "near known collision"
NEAR_BOUND = 0.8           # warn when a move uses more than 80 % of its evidence bound
GRID_CELL = 4.0
GROUND_STATES = {
    "ground": "GROUND BELOW",
    "ambiguous": "AMBIGUOUS (stacked surfaces)",
    "below_surface": "UNDER A SURFACE",
    "no_surface": "NO SURFACE FOUND",
}


def _tri_z(t, x, y):
    """z of triangle t's plane at (x, y) when (x, y) lies in its x / y projection (edges included), else None."""
    (ax, ay, az), (bx, by, bz), (cx, cy, cz) = t
    d = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
    if abs(d) < 1e-12:
        return None
    l1 = ((by - cy) * (x - cx) + (cx - bx) * (y - cy)) / d
    l2 = ((cy - ay) * (x - cx) + (ax - cx) * (y - cy)) / d
    l3 = 1.0 - l1 - l2
    e = -1e-7
    if l1 < e or l2 < e or l3 < e:
        return None
    return l1 * az + l2 * bz + l3 * cz


def _seg2(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    L = dx * dx + dy * dy
    t = 0.0 if L == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L))
    return math.hypot(px - ax - t * dx, py - ay - t * dy)


class GroundIndex:
    """Ground-like static collision triangles of one level on a fixed x / y grid (deterministic: triangles keep the
    decoder's order; every query result is sorted)."""

    def __init__(self, tris):
        self.tris, self.grid = [], {}
        self.skipped = 0
        for t in tris:
            nz = abs(triangle_normal_z(*t))
            if nz < GROUND_MIN_NZ:
                self.skipped += 1          # walls / steep faces: not a ground candidate
                continue
            xs, ys = [p[0] for p in t], [p[1] for p in t]
            i = len(self.tris)
            self.tris.append((t, nz))
            for gx in range(math.floor(min(xs) / GRID_CELL), math.floor(max(xs) / GRID_CELL) + 1):
                for gy in range(math.floor(min(ys) / GRID_CELL), math.floor(max(ys) / GRID_CELL) + 1):
                    self.grid.setdefault((gx, gy), []).append(i)

    def surfaces(self, x, y):
        """Distinct ground-like surfaces at (x, y), lowest first: [(z, normal_z)]. Surfaces within SAME_SURFACE of
        each other merge, keeping the lower z and the steeper (smaller) normal z, so a merge never makes a slope look
        flatter."""
        cell = (math.floor(x / GRID_CELL), math.floor(y / GRID_CELL))
        hits = sorted((z, nz) for z, nz in ((_tri_z(self.tris[i][0], x, y), self.tris[i][1])
                                            for i in self.grid.get(cell, ())) if z is not None)
        out = []
        for z, nz in hits:
            if out and z - out[-1][0] <= SAME_SURFACE:
                out[-1] = (out[-1][0], min(out[-1][1], nz))
                continue
            out.append((z, nz))
        return out

    def horizontal_distance(self, x, y, reach=NEAR_COLLISION):
        """Horizontal distance from (x, y) to the nearest ground-like triangle's x / y projection (0 inside one), or
        None when none lies within reach."""
        best = None
        r = math.ceil(reach / GRID_CELL)
        cx, cy = math.floor(x / GRID_CELL), math.floor(y / GRID_CELL)
        seen = set()
        for gx in range(cx - r, cx + r + 1):
            for gy in range(cy - r, cy + r + 1):
                for i in self.grid.get((gx, gy), ()):
                    if i in seen:
                        continue
                    seen.add(i)
                    t = self.tris[i][0]
                    if _tri_z(t, x, y) is not None:
                        return 0.0
                    d = min(_seg2(x, y, t[k][0], t[k][1], t[(k + 1) % 3][0], t[(k + 1) % 3][1]) for k in range(3))
                    best = d if best is None or d < best else best
        return best if best is not None and best <= reach else None


def ground_query(index, pos):
    """Conservative geometric observation of a point against the static collision (advisory, never authoritative):
    {"state", "label", "surfaces", "below", "above", "dz", "window", "horizontal"}.
      ground        - at least one surface at or below the point and exactly one inside the snap window
                      [z - SNAP_DOWN, z + SNAP_UP], or none in the window but a single surface below
      ambiguous     - two or more distinct surfaces inside the snap window (stacked floors, bridges, overhangs)
      below_surface - surfaces only above the point (it is probably under the ground / inside a floor)
      no_surface    - no ground-like triangle at this x / y (outside the decoded collision, a pit, or geometry the
                      editor cannot see); never reported as unsafe
    dz = point z - the nearest surface at or below it (None without one)."""
    x, y, z = pos
    s = index.surfaces(x, y)
    below = [q for q in s if q[0] <= z + SAME_SURFACE]
    above = [q for q in s if q[0] > z + SAME_SURFACE]
    window = [q for q in s if z - SNAP_DOWN <= q[0] <= z + SNAP_UP]
    if not s:
        state = "no_surface"
    elif len(window) >= 2:
        state = "ambiguous"
    elif not below:
        state = "below_surface"
    else:
        state = "ground"
    nb = below[-1] if below else None
    return {"state": state, "label": GROUND_STATES[state], "z": z, "surfaces": s, "below": nb,
            "above": above[0] if above else None, "dz": (z - nb[0]) if nb else None, "window": window,
            "horizontal": index.horizontal_distance(x, y) if not s else 0.0}


def ground_text(q):
    """One or two lines for the inspector; always marked as a prediction."""
    head = f"Ground (static collision only, a prediction): {q['label']}"
    if q["state"] == "no_surface":
        h = q["horizontal"]
        return head + (f" - nearest known collision {h:.2f} units away horizontally" if h is not None else
                       f" - no known collision within {NEAR_COLLISION:g} units horizontally") + \
            " (the decoded static collision does not cover this point; this is not a safety verdict)"
    if q["state"] == "below_surface":
        return head + f" - a surface lies {q['above'][0] - q['z']:.3f} above the point and none below it"
    lines = head
    if q["below"]:
        lines += f" - {q['dz']:.3f} above the surface below (normal z {q['below'][1]:.2f})"
    if q["state"] == "ambiguous":
        lines += "; surfaces in reach at z " + ", ".join(f"{zz:.3f}" for zz, _ in q["window"])
    elif q["above"]:
        lines += f"; another surface {q['above'][0] - q['z']:.3f} above"
    return lines


def snap_proposal(index, pos, original, max_move, original_query=None):
    """Proposal to put an item on the ground below it, keeping the ORIGINAL item's own height above its original
    ground (the editor does not know whether an actor's origin is at its feet or its centre). Deterministic; nothing
    is changed here. {"ok": True, "position", "dz", "surface_z", "normal_z", "clearance", "text"} or
    {"ok": False, "code", "text"}. Refusals (never a clamp or a guess):
      NO_REFERENCE - the original position has no single unambiguous surface below it within SNAP_DOWN
      NO_SURFACE   - no ground-like surface inside the snap window at the proposed x / y
      AMBIGUOUS    - two or more surfaces inside the window (stacked floors)
      STEEP        - the only surface is steeper than SNAP_MIN_NZ allows
      OUT_OF_BOUND - the snapped point would be farther than the evidence bound from the original
      BLOCKED      - the snapped point would sit in a different surface stack than the one found
      NO_CHANGE    - already there (within 0.001)"""
    oq = original_query or ground_query(index, original)
    if oq["state"] != "ground" or oq["dz"] is None or not -SAME_SURFACE <= oq["dz"] <= SNAP_DOWN \
            or len(oq["window"]) != 1:
        return {"ok": False, "code": "NO_REFERENCE", "text": (
            "Snap refused: the original position has no single surface below it within "
            f"{SNAP_DOWN:g} units, so this item's own height above the ground is unknown (it may float or fly). "
            "Set Z by hand.")}
    clr = max(0.0, oq["dz"])
    q = ground_query(index, pos)
    x, y, z = pos
    if not q["window"]:
        return {"ok": False, "code": "NO_SURFACE", "text": (
            f"Snap refused: no ground-like surface within {SNAP_DOWN:g} below / {SNAP_UP:g} above this point "
            f"({q['label']}).")}
    if len(q["window"]) > 1:
        return {"ok": False, "code": "AMBIGUOUS", "text": (
            "Snap refused: stacked surfaces in reach at z " + ", ".join(f"{a:.3f}" for a, _ in q["window"])
            + "; move the item horizontally or set Z by hand.")}
    sz, nz = q["window"][0]
    if nz < SNAP_MIN_NZ:
        return {"ok": False, "code": "STEEP", "text": (
            f"Snap refused: the surface is too steep (normal z {nz:.2f} < {SNAP_MIN_NZ}).")}
    new = [f32(x), f32(y), f32(sz + clr)]
    nq = ground_query(index, new)
    if len(nq["window"]) != 1 or abs(nq["window"][0][0] - sz) > SAME_SURFACE or nq["state"] != "ground":
        return {"ok": False, "code": "BLOCKED", "text": (
            "Snap refused: at the snapped height the point would be in a different stack of surfaces "
            f"({nq['label']}).")}
    if math.dist(new, original) > max_move + 1e-4:
        return {"ok": False, "code": "OUT_OF_BOUND", "text": (
            f"Snap refused: the snapped point would be {math.dist(new, original):.3f} units from the original "
            f"position (at most {max_move:g}). Nothing was clamped.")}
    if abs(new[2] - z) < 1e-3:
        return {"ok": False, "code": "NO_CHANGE", "text": "Already on the ground (same height above it as the "
                                                          "original)."}
    return {"ok": True, "position": new, "dz": new[2] - z, "surface_z": sz, "normal_z": nz, "clearance": clr,
            "text": (f"Snap proposal: Z {z:.3f} -> {new[2]:.3f} ({new[2] - z:+.3f}); surface z {sz:.3f} (normal z "
                     f"{nz:.2f}) plus the original's own height above ground {clr:.3f}. A geometric prediction: it "
                     "does not show that the item behaves correctly there.")}


# ------------------------------------------------------------------------------------------------ route helpers
# Graph followers with runtime evidence (the actor seen moving along the graph). A graph's STORAGE owner (the actor
# whose designer variable names it) is always known from the script index; its FOLLOWER is UNKNOWN unless listed.
GRAPH_FOLLOWERS = {
    ("intro_10", "NIN_m_GenFlyIntro_10", 0, 0): "Rayman's flight path (the flight generator; E-460 / E-464 measured)",
    ("intro_20", "NIN_m_FairyLight", 2, 2): "original FairyLight instance 2 (E-480 / E-523 measured)",
}


def graph_owner(model, ident):
    """(storage owner text, follower text or 'UNKNOWN') of a graph identity (model key, instance, variable)."""
    g = model.graphs[ident]
    store = f"{g['name']} #{ident[1]} (designer variable {ident[2]})"
    return store, GRAPH_FOLLOWERS.get((model.level, g["name"], ident[1], ident[2]), "UNKNOWN")


def route_sequence(g):
    """The connected waypoint sequence of a graph from its decoded arcs: ("loop" | "path", [nodes]) when every node
    has at most one outgoing arc, else ("branching", [arcs])."""
    out = {}
    for i, j in g["edges"]:
        out.setdefault(i, []).append(j)
    if not g["edges"]:
        return "unconnected", list(range(len(g["nodes"])))
    if any(len(v) > 1 for v in out.values()):
        return "branching", list(g["edges"])
    targets = {j for i, j in g["edges"]}
    starts = sorted(set(out) - targets) or [min(out)]
    seq, n = [starts[0]], starts[0]
    while n in out and len(seq) <= len(g["nodes"]):
        n = out[n][0]
        if n == seq[0]:
            return "loop", seq
        if n in seq:
            break
        seq.append(n)
    return "path", seq


def route_compare(model, p, ident):
    """Per node of a graph: {"node", "original", "current", "moved"} for the project's current edits."""
    g = model.graphs[ident]
    ed = {w["node"]: tuple(w["position"]) for w in check_remix(p)["waypoints"]
          if (w["model"], w["instance"], w["variable"]) == ident}
    out = []
    for i, nd in enumerate(g["nodes"]):
        if nd is None:
            out.append({"node": i, "original": None, "current": None, "moved": 0.0})
            continue
        cur = ed.get(i, nd["position"])
        out.append({"node": i, "original": nd["position"], "current": cur, "moved": math.dist(cur, nd["position"])})
    return out


def revert_waypoint(p, ident4):
    q = check_remix(p)
    q["waypoints"] = [w for w in q["waypoints"] if (w["model"], w["instance"], w["variable"], w["node"]) != ident4]
    return check_remix(q)


def revert_route(p, ident3):
    q = check_remix(p)
    q["waypoints"] = [w for w in q["waypoints"] if (w["model"], w["instance"], w["variable"]) != ident3]
    return check_remix(q)


NODE_INSERTION_TEXT = ("Waypoint positions only. Adding or removing graph nodes or arcs changes the graph's size and is "
                       "a development-only level transaction (graph-node insertion, G6-P16 to G6-P28); this editor "
                       "never inserts nodes.")


# ------------------------------------------------------------------------------------------------ warnings
def remix_warnings(p, model):
    """Advisory findings for a remix project: [(severity "warn" | "info", code, text)], sorted deterministically.
    They never change the project or the compiler's verdict; strict refusals stay check_remix_level's / the
    compiler's."""
    p = check_remix(p)
    out = []
    gi = model.ground_index()
    for a in p["actors"]:
        x = model.actors.get((a["model"], a["instance"]))
        if x is None or x["status"] in ("locked", "script_overridden"):
            continue
        name = f"actor {x['name']} #{a['instance']}"
        q, oq = ground_query(gi, a["position"]), ground_query(gi, x["position"])
        if q["state"] == "no_surface" and q["horizontal"] is None and oq["state"] != "no_surface":
            out.append(("warn", "FAR_FROM_COLLISION", f"{name}: moved away from any known collision (none within "
                                                      f"{NEAR_COLLISION:g} units horizontally; the original stood "
                                                      "over collision)"))
        if q["state"] == "below_surface" and oq["state"] != "below_surface":
            out.append(("warn", "BELOW_SURFACE", f"{name}: probably under a surface ({q['above'][0] - a['position'][2]:.3f} "
                                                 "below it, nothing underneath)"))
        if q["state"] == "ambiguous":
            out.append(("warn", "STACKED", f"{name}: stacked surfaces in reach (z "
                                           + ", ".join(f"{zz:.2f}" for zz, _ in q["window"]) + "); which floor it "
                                           "lands on is not predictable from geometry"))
        d = math.dist(a["position"], x["position"])
        lim = getattr(model, "max_actor_move", MAX_ACTOR_MOVE)
        if d > NEAR_BOUND * lim:
            out.append(("info", "NEAR_BOUND", f"{name}: moved {d:.2f} of at most {lim:g} units"))
        if x["status"] != "verified":
            out.append(("info", "BEHAVIOUR_UNVERIFIED", f"{name}: {x['status'].upper()} - its behaviour at the new "
                                                        "position is not verified"))
    graphs = sorted({(w["model"], w["instance"], w["variable"]) for w in p["waypoints"]})
    for gid in graphs:
        g = model.graphs.get(gid)
        if g is None:
            continue
        store, follower = graph_owner(model, gid)
        if follower == "UNKNOWN":
            out.append(("warn", "ROUTE_FOLLOWER_UNKNOWN", f"graph {store}: no actor has been seen following it; "
                                                          "the edit may have no visible effect"))
        if g["status"] == "supported":
            out.append(("warn", "ROUTE_SUPPORTED", f"graph {store}: ROUTE SUPPORTED, not verified ({g['why']})"))
        for w in p["waypoints"]:
            if (w["model"], w["instance"], w["variable"]) != gid or w["node"] >= len(g["nodes"]) \
                    or g["nodes"][w["node"]] is None:
                continue
            d = math.dist(w["position"], g["nodes"][w["node"]]["position"])
            if d > NEAR_BOUND * MAX_WAYPOINT_MOVE:
                out.append(("info", "NEAR_BOUND", f"graph {store} node {w['node']}: moved {d:.2f} of at most "
                                                  f"{MAX_WAYPOINT_MOVE:g} units"))
    return sorted(set(out), key=lambda t: (t[0] != "warn", t[1], t[2]))


# ------------------------------------------------------------------------------------------------ presets
# Reusable edit sets taken from accepted runtime evidence. A preset only declares identities and positions (absolute
# coordinates or offsets from the person's own original); matrix / waypoint hashes come from the person's files when
# applied, and the result goes through the same check_remix / validate_remix path as manual edits. A preset's
# evidence covers ITS exact items and positions only, never the model in general.
PRESETS = [
    {"id": "intro10-lums-on-flight-path", "level": "intro_10", "evidence": "verified",
     "title": "intro_10: two red lums moved onto the flight path (VERIFIED, E-523)",
     "limit": "Runtime-verified for exactly lums #1 and #3 at exactly these positions (collected there in a production "
              "run). Other lums or other positions are EXPERIMENTAL.",
     "actors": [("NIN_m_Lums_Int10", 1, "abs", (16.823, -3.345, -31.034)),
                ("NIN_m_Lums_Int10", 3, "abs", (11.139, -73.227, -45.188))], "waypoints": []},
    {"id": "intro10-flight-bend", "level": "intro_10", "evidence": "verified",
     "title": "intro_10: bend the flight path at node 13 (VERIFIED, E-464)",
     "limit": "Runtime-verified for flight-graph node 13 moved 6 units sideways: the flight bends toward it locally "
              "(about 2.7 of 6 units realised). Other nodes are covered by the same graph's VERIFIED status only as "
              "far as E-464 measured one node.",
     "actors": [], "waypoints": [("NIN_m_GenFlyIntro_10", 0, 0, 13, "abs", (25.08, -34.13, -40.10))]},
    {"id": "intro20-graph-c-reshape", "level": "intro_20", "evidence": "supported",
     "title": "intro_20: reshape FairyLight 2's loop (graph C nodes 0 / 3 / 5) (ROUTE SUPPORTED, E-523)",
     "limit": "ROUTE SUPPORTED, not verified: original FairyLight 2 reached each moved node within 0.29 units in one "
              "production run, but one pre-registered criterion failed (unmoved node 2 at 0.354 > 0.30, a 0.11 s "
              "sampling artifact by the G6-P35 offline review). Exactly these three offsets.",
     "actors": [], "waypoints": [("NIN_m_FairyLight", 2, 2, 0, "off", (-4.0, -3.0, -2.0)),
                                 ("NIN_m_FairyLight", 2, 2, 3, "off", (0.0, -5.0, 3.0)),
                                 ("NIN_m_FairyLight", 2, 2, 5, "off", (-3.0, 0.0, -4.0))]},
    {"id": "intro20-placement-trio", "level": "intro_20", "evidence": "placement",
     "title": "intro_20: Chameleon #0, Powerz #1 and Boing2 #11 moved 3 units (PLACEMENT VERIFIED, E-523)",
     "limit": "Each appeared at and kept its new position for 80 s in a production run; their behaviour there (attack, "
              "bounce, collision) was not observed.",
     "actors": [("NIK_mChameleon", 0, "off", (3.0, 0.0, 0.0)), ("YAM_mPowerz", 1, "off", (3.0, 0.0, 0.0)),
                ("Mic_mBoing2", 11, "off", (3.0, 0.0, 0.0))], "waypoints": []},
]
# The production intro_20 level patch (v1 project, separate mod): the G6-P25 west-basin terrain values with the
# inserted FairyLight on graph A, the content the G6-P30 production run activated (E-519). The editor writes one
# terrain group per vertex, so the declaration differs from g6p25_west_basin_fairy.json in grouping only.
PATCH_PRESET = {"id": "intro20-west-basin", "evidence": "verified",
                "title": "intro_20 level patch: west-basin terrain + FairyLight on graph A (production, E-519)",
                "limit": "Production-supported content (D-286). Verified in the production run with the G6-P25 "
                         "grouping; the editor's per-vertex grouping gives the same vertex heights.",
                "region": "start-floor-v2", "terrain": {"2": -0.15, "4": -0.15, "6": -0.2}, "follow_graph_of": 0}


def preset_by_id(pid):
    if pid == PATCH_PRESET["id"]:
        return PATCH_PRESET
    for ps in PRESETS:
        if ps["id"] == pid:
            return ps
    raise EditorError("UNSUPPORTED", f"unknown preset {pid!r}")


def _model_key(model, name, graphs=False):
    keys = sorted({k[0] for k in (model.graphs if graphs else model.actors)
                   if short_name(k[0]) == name})
    if len(keys) != 1:
        raise EditorError("TARGET_CHANGED", f"model {name} is not uniquely present in {model.level}")
    return keys[0]


def apply_preset(p, pid, model):
    """The remix project p with a preset's edits added (replacing edits of the same items). Hashes come from the
    loaded level; positions are float32. Refuses when the level differs or an item is missing / not editable."""
    ps = preset_by_id(pid)
    if ps is PATCH_PRESET:
        raise EditorError("UNSUPPORTED", "the level-patch preset makes an intro_20 terrain project (patch_preset)")
    q = check_remix(p)
    if q["level"] != ps["level"] or model is None or model.level != ps["level"]:
        raise EditorError("UNSUPPORTED", f"preset {pid} is for {ps['level']}")
    for name, inst, how, v in ps["actors"]:
        k = _model_key(model, name)
        a = model.actors.get((k, inst))
        if a is None or a["status"] in ("locked", "script_overridden"):
            raise EditorError("TARGET_CHANGED", f"preset {pid}: actor {name} #{inst} is not editable here")
        pos = [f32(c) for c in (v if how == "abs" else [o + d for o, d in zip(a["position"], v)])]
        q["actors"] = [x for x in q["actors"] if (x["model"], x["instance"]) != (k, inst)]
        q["actors"].append({"model": k, "instance": inst, "matrix_sha256": a["matrix_sha256"], "position": pos})
    for name, inst, var, node, how, v in ps["waypoints"]:
        k = _model_key(model, name, graphs=True)
        g = model.graphs.get((k, inst, var))
        nd = g["nodes"][node] if g and node < len(g["nodes"]) else None
        if nd is None or nd["why"] or g["status"] == "locked":
            raise EditorError("TARGET_CHANGED", f"preset {pid}: waypoint {name} #{inst} node {node} is not editable")
        pos = [f32(c) for c in (v if how == "abs" else [o + d for o, d in zip(nd["position"], v)])]
        ident = (k, inst, var, node)
        q["waypoints"] = [w for w in q["waypoints"] if (w["model"], w["instance"], w["variable"], w["node"]) != ident]
        q["waypoints"].append({"model": k, "instance": inst, "variable": var, "node": node,
                               "waypoint_sha256": nd["waypoint_sha256"], "position": pos})
    q = check_remix(q)
    probs = check_remix_level(q, model)
    if probs:
        raise EditorError("UNSUPPORTED", "; ".join(probs))
    return q


def patch_preset():
    """The v1 intro_20 level-patch project of PATCH_PRESET."""
    p = new_project()
    p["region"], p["terrain"] = PATCH_PRESET["region"], dict(PATCH_PRESET["terrain"])
    p["fairylight"] = {"follow_graph_of": PATCH_PRESET["follow_graph_of"]}
    p["meta"] = {"id": "custom.intro20-west-basin", "name": "intro_20 west basin", "description": ""}
    return check_project(p)
