#!/usr/bin/env python3
"""E-528 (D-295) G6-P39: the 3D editor's narrow OpenGL bridge (_r3hd_scene_gl), in the checkout and in a private stage.

    g6p39_bridge_check.py check STAGE [--skip-parity]

STAGE is a payload staged by `r3hd_stage.py build` (it contains app/python/_r3hd_scene_gl.pyd). Groups:
  S1  boundary: valid operations draw; malformed sizes, formats, handles, indices, buffer lengths, matrices, windows,
      threads and repeated teardown are refused with Python exceptions (run in this Python AND in the staged one)
  S2  parity: the G6-P38 renderer (ctypes, taken from commit ceeabf7 into private/work, development Python only) and
      the bridge renderer draw the same cameras; pixels compared (private PNGs, never committed)
  S3  interaction: g6p38_editor_check (--skip-stage) and g6p37_scene_check pass on the bridge
  S4  restricted runtime: the staged python.exe (-I, no system Python on PATH) has no ctypes / _ctypes / libffi /
      _socket / _ssl, exactly two extension modules, and the bridge's whole surface is Context + LIMITS
  S6  lifecycle in the staged runtime: open / level switch / close / reopen, resources freed (bridge counters)
  S7  the staged 3D editor edits through the editor's own methods: select, preview, apply, validate, save, export,
      import, undo; the classic 2D editor still works; missing or corrupt level data refuses
  S8  static safety of the bridge source and the 3D modules
Windows are never shown: Tk roots are withdrawn, contexts are offscreen or on withdrawn frames; no input is sent; the
owner's game files are read only. Prints PASS/FAIL rows and G6P39_BRIDGE PASS|FAIL; private/work/g6p39/bridge.json.
"""
import json
import os
import re
import struct
import subprocess
import sys
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOLS = HERE.parents[1]
ROOT = TOOLS.parent
OUT = ROOT / "private" / "work" / "g6p39"
BRIDGE_SRC = TOOLS / "scene_gl" / "r3hd_scene_gl.cpp"
REF_COMMIT = "ceeabf7"                       # G6-P38: the ctypes renderer

# ------------------------------------------------------------------------------------------------ S1 probe
BOUNDARY = r'''
import array, gc, json, sys, threading
sys.path.insert(0, sys.argv[1])
foreign = json.loads(sys.argv[2])
import tkinter as tk
import r3hd_scene_gl as sg
b = sg.bridge()
R, D = {}, {}

def refused(fn):
    try:
        fn()
    except (ValueError, TypeError, RuntimeError, OverflowError) as x:
        return type(x).__name__ + ": " + str(x)[:80]
    except BaseException as x:
        return "WRONG " + type(x).__name__
    return None

R["module surface is Context, LIMITS, __version__"] = sorted(n for n in dir(b) if not n.startswith("__")) == ["Context", "LIMITS"]
R["Context methods are the drawing interface only"] = sorted(n for n in dir(b.Context) if not n.startswith("_")) == sorted(
    ["make_current", "texture", "batch", "lines", "release", "begin", "draw", "draw_lines", "overlay_lines",
     "overlay_points", "end", "finish", "present", "read_pixels", "error", "info", "close"])
D["limits"] = dict(b.LIMITS)
F = lambda xs: array.array("f", xs)
tri, uv, col = F([0, 0, 0, 1, 0, 0, 0, 1, 0]), F([0] * 6), bytes([255] * 12)
I16 = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
c = b.Context(offscreen=(64, 64))
t = c.texture(2, 2, bytes(range(16)))
bh = c.batch(t, tri, uv, col)
bu = c.batch(0, tri, uv, col)
lh = c.lines(F([0, 0, 0, 1, 1, 1]))
c.begin(64, 64, (0.1, 0.2, 0.3), I16, I16)
for m in range(4):
    c.draw(bh, m, False)
    c.draw(bu, m, True)
c.draw_lines(lh, (1, 1, 1), 1.0)
c.overlay_lines(F([0, 0, 0, 0.5, 0.5, 0]), bytes([255] * 8), 2.0, 2, 0x0F0F)
c.overlay_points(F([0, 0, 0]), bytes([255] * 4), 9.0)
c.overlay_points(F([]), b"", 9.0)
c.end()
R["valid operations draw without a GL error"] = c.error() == 0
inside = {}
c.begin(64, 64, (0, 0, 0), I16, I16)
inside["begin twice"] = refused(lambda: c.begin(64, 64, (0, 0, 0), I16, I16))
inside["read_pixels inside a frame"] = refused(lambda: c.read_pixels())
inside["release inside a frame"] = refused(lambda: c.release(bh))
inside["texture inside a frame"] = refused(lambda: c.texture(1, 1, bytes(4)))
inside["draw mode 4"] = refused(lambda: c.draw(bh, 4, False))
inside["draw mode -1"] = refused(lambda: c.draw(bh, -1, False))
inside["draw a line set as triangles"] = refused(lambda: c.draw(lh, 0, False))
inside["draw_lines a triangle batch"] = refused(lambda: c.draw_lines(bh, (1, 1, 1), 1.0))
inside["draw unknown handle"] = refused(lambda: c.draw(999999, 0, False))
inside["draw handle 2**40"] = refused(lambda: c.draw(2 ** 40, 0, False))
inside["draw handle -1"] = refused(lambda: c.draw(-1, 0, False))
inside["draw handle 'x'"] = refused(lambda: c.draw("x", 0, False))
inside["draw_lines width 0"] = refused(lambda: c.draw_lines(lh, (1, 1, 1), 0.0))
inside["draw_lines width 100"] = refused(lambda: c.draw_lines(lh, (1, 1, 1), 100.0))
inside["draw_lines colour 2.0"] = refused(lambda: c.draw_lines(lh, (2, 1, 1), 1.0))
inside["overlay_lines odd vertex count"] = refused(lambda: c.overlay_lines(F([0] * 9), bytes(12), 1.0, 0, 0xFFFF))
inside["overlay_lines colours short"] = refused(lambda: c.overlay_lines(F([0] * 6), bytes(7), 1.0, 0, 0xFFFF))
inside["overlay_lines stipple factor 300"] = refused(lambda: c.overlay_lines(F([0] * 6), bytes(8), 1.0, 300, 1))
inside["overlay_lines pattern 0x10000"] = refused(lambda: c.overlay_lines(F([0] * 6), bytes(8), 1.0, 1, 0x10000))
inside["overlay_lines width -1"] = refused(lambda: c.overlay_lines(F([0] * 6), bytes(8), -1.0, 0, 1))
inside["overlay_points size 0"] = refused(lambda: c.overlay_points(F([0] * 3), bytes(4), 0.0))
inside["overlay_points size 100"] = refused(lambda: c.overlay_points(F([0] * 3), bytes(4), 100.0))
inside["overlay_points NaN"] = refused(lambda: c.overlay_points(F([float("nan"), 0, 0]), bytes(4), 2.0))
inside["overlay_points over the vertex limit"] = refused(
    lambda: c.overlay_points(F([0.0]) * (3 * (b.LIMITS["overlay_vertices"] + 1)), bytes(4 * (b.LIMITS["overlay_vertices"] + 1)), 2.0))
inside["overlay positions as bytes"] = refused(lambda: c.overlay_points(bytes(12), bytes(4), 2.0))
c.end()
outside = {
    "draw outside a frame": refused(lambda: c.draw(bh, 0, False)),
    "end outside a frame": refused(lambda: c.end()),
    "overlay outside a frame": refused(lambda: c.overlay_points(F([0] * 3), bytes(4), 2.0)),
    "present an offscreen context": refused(lambda: c.present()),
    "begin larger than the offscreen target": refused(lambda: c.begin(65, 64, (0, 0, 0), I16, I16)),
    "begin width 0": refused(lambda: c.begin(0, 64, (0, 0, 0), I16, I16)),
    "begin clear colour out of range": refused(lambda: c.begin(8, 8, (2, 0, 0), I16, I16)),
    "begin 15 matrix numbers": refused(lambda: c.begin(8, 8, (0, 0, 0), I16[:15], I16)),
    "begin NaN matrix": refused(lambda: c.begin(8, 8, (0, 0, 0), [float("nan")] + I16[1:], I16)),
    "begin infinite matrix": refused(lambda: c.begin(8, 8, (0, 0, 0), I16, [float("inf")] + I16[1:])),
    "begin matrix of strings": refused(lambda: c.begin(8, 8, (0, 0, 0), ["a"] * 16, I16)),
    "begin matrix not a sequence": refused(lambda: c.begin(8, 8, (0, 0, 0), 5, I16)),
    "texture 0 x 1": refused(lambda: c.texture(0, 1, b"")),
    "texture 4097 wide": refused(lambda: c.texture(4097, 1, bytes(4097 * 4))),
    "texture -1 high": refused(lambda: c.texture(1, -1, b"")),
    "texture 2**31 wide": refused(lambda: c.texture(2 ** 31, 1, b"")),
    "texture one byte short": refused(lambda: c.texture(2, 2, bytes(15))),
    "texture one byte long": refused(lambda: c.texture(2, 2, bytes(17))),
    "texture data as str": refused(lambda: c.texture(2, 2, "x" * 16)),
    "texture data as float array": refused(lambda: c.texture(2, 2, F([0] * 4))),
    "texture data None": refused(lambda: c.texture(2, 2, None)),
    "batch unknown texture": refused(lambda: c.batch(999999, tri, uv, col)),
    "batch texture -1": refused(lambda: c.batch(-1, tri, uv, col)),
    "batch texture 2**40": refused(lambda: c.batch(2 ** 40, tri, uv, col)),
    "batch a line set as texture": refused(lambda: c.batch(lh, tri, uv, col)),
    "batch positions as bytes": refused(lambda: c.batch(0, bytes(36), uv, col)),
    "batch positions not whole triples": refused(lambda: c.batch(0, F([0] * 8), uv, col)),
    "batch two vertices": refused(lambda: c.batch(0, F([0] * 6), F([0] * 4), bytes(8))),
    "batch four vertices": refused(lambda: c.batch(0, F([0] * 12), F([0] * 8), bytes(16))),
    "batch uvs short": refused(lambda: c.batch(0, tri, F([0] * 5), col)),
    "batch colours long": refused(lambda: c.batch(0, tri, uv, bytes(13))),
    "batch colours as floats": refused(lambda: c.batch(0, tri, uv, F([0] * 3))),
    "batch NaN position": refused(lambda: c.batch(0, F([float("nan")] + [0] * 8), uv, col)),
    "batch infinite uv": refused(lambda: c.batch(0, tri, F([float("inf")] + [0] * 5), col)),
    "batch coordinate 1e30": refused(lambda: c.batch(0, F([1e30] + [0] * 8), uv, col)),
    "batch strided view": refused(lambda: c.batch(0, memoryview(F([0] * 18))[::2], uv, col)),
    "batch over the vertex limit": refused(
        lambda: c.batch(0, F([0.0]) * (3 * (b.LIMITS["batch_vertices"] + 3)), uv, col)),
    "lines one vertex": refused(lambda: c.lines(F([0, 0, 0]))),
    "lines three vertices": refused(lambda: c.lines(F([0] * 9))),
    "release unknown handle": refused(lambda: c.release(424242)),
}
px = c.read_pixels()
R["one readback of the offscreen frame (w*h*4 bytes, bottom row first)"] = len(px) == 64 * 64 * 4
outside["a second readback"] = refused(lambda: c.read_pixels())
c.release(bu)
outside["release twice"] = refused(lambda: c.release(bu))
err = []
th = threading.Thread(target=lambda: err.extend([refused(lambda: c.texture(1, 1, bytes(4))), refused(lambda: c.close())]))
th.start(); th.join()
R["another thread is refused (texture, close)"] = all(e and "another thread" in e for e in err)
D["threads"] = err
info_before = c.info()
c.close()
c.close()
after = {"after close: " + n: refused(f) for n, f in (
    ("texture", lambda: c.texture(1, 1, bytes(4))), ("begin", lambda: c.begin(8, 8, (0, 0, 0), I16, I16)),
    ("draw", lambda: c.draw(bh, 0, False)), ("read_pixels", lambda: c.read_pixels()),
    ("make_current", lambda: c.make_current()), ("release", lambda: c.release(t)))}
R["closing twice is harmless; everything after close is refused"] = all(after.values()) and c.info().get("closed") is True
ctor = {
    "Context()": refused(lambda: b.Context()),
    "both hwnd and offscreen": refused(lambda: b.Context(hwnd=1, offscreen=(8, 8))),
    "positional hwnd": refused(lambda: b.Context(1)),
    "hwnd 0": refused(lambda: b.Context(hwnd=0)),
    "hwnd -1": refused(lambda: b.Context(hwnd=-1)),
    "hwnd 2**70": refused(lambda: b.Context(hwnd=2 ** 70)),
    "hwnd 'x'": refused(lambda: b.Context(hwnd="x")),
    "hwnd 1.5": refused(lambda: b.Context(hwnd=1.5)),
    "offscreen (0, 0)": refused(lambda: b.Context(offscreen=(0, 0))),
    "offscreen (5000, 10)": refused(lambda: b.Context(offscreen=(5000, 10))),
    "offscreen 'ab'": refused(lambda: b.Context(offscreen="ab")),
    "offscreen (1, 2, 3)": refused(lambda: b.Context(offscreen=(1, 2, 3))),
}
for i, h in enumerate(foreign):
    ctor[f"a window of another process ({i})"] = refused(lambda: b.Context(hwnd=h))
root = tk.Tk(); root.withdraw()
fr = tk.Frame(root, width=64, height=64); fr.pack(); root.update_idletasks()
top_wrapper = int(root.wm_frame(), 16)
ctor["a top-level window of this process"] = refused(lambda: b.Context(hwnd=top_wrapper))
w = b.Context(hwnd=fr.winfo_id())
ctor["a second context on the same window"] = refused(lambda: b.Context(hwnd=fr.winfo_id()))
D["window_context"] = {k: v for k, v in w.info().items() if k in ("offscreen", "window_visible")}
w.close()
fr2 = tk.Frame(root, width=64, height=64); fr2.pack(); root.update_idletasks()
w2 = b.Context(hwnd=fr2.winfo_id())
fr2.destroy(); root.update_idletasks()
ctor["using a context whose window was destroyed"] = refused(lambda: w2.texture(1, 1, bytes(4)))
w2.close()
root.destroy()
class_ok = refused(lambda: type("X", (b.Context,), {}))
R["Context cannot be subclassed"] = class_ok is not None
R["every malformed call inside a frame is refused"] = all(inside.values())
R["every malformed call outside a frame is refused"] = all(outside.values())
R["every malformed context request is refused (windows of other processes, top-level, duplicate, dead window)"] = all(ctor.values())
R["no Python exception other than ValueError / TypeError / RuntimeError / OverflowError"] = not any(
    str(v).startswith("WRONG") for d in (inside, outside, ctor, after) for v in d.values())
for k in range(40):
    x = b.Context(offscreen=(32, 32))
    tt = x.texture(4, 4, bytes(64))
    x.batch(tt, tri, uv, col)
    if k % 2:
        x.close()
    del x
gc.collect()
many = []
try:
    for k in range(b.LIMITS["contexts"] + 1):
        many.append(b.Context(offscreen=(8, 8)))
    cap = None
except RuntimeError as x:
    cap = str(x)
R["at most LIMITS['contexts'] live contexts per process; the next one is refused"] = (
    cap is not None and "too many" in cap and len(many) == b.LIMITS["contexts"])
for m in many:
    m.close()
mis = memoryview(bytearray(40))[1:37].cast("f")
y = b.Context(offscreen=(8, 8))
R["a misaligned float view is refused (TypeError)"] = (refused(lambda: y.batch(0, mis, uv, col)) or "").startswith("TypeError")
y.close()
z = b.Context(offscreen=(16, 16))
R["40 contexts created and freed (closed or collected), a new one still works"] = z.info()["textures"] == 0 and z.error() == 0
z.close()
D.update(inside=inside, outside=outside, ctor=ctor, after=after, info_before={k: info_before[k] for k in ("textures", "batches", "bytes", "readbacks")})
print("BOUNDARY " + json.dumps({"R": R, "D": D}))
'''

# ------------------------------------------------------------------------------------------------ S4 / S6 / S7 probe
STAGED = r'''
import glob, json, os, sys, time, zipfile
from pathlib import Path
tools, game, work = sys.argv[1], sys.argv[2], Path(sys.argv[3])
sys.path.insert(0, tools)
pydir = Path(sys.executable).parent
out = {"prefix": sys.prefix, "executable": sys.executable, "path": sys.path, "isolated": sys.flags.isolated}
def imp(name):
    try:
        m = __import__(name)
        return getattr(m, "__file__", "builtin")
    except ImportError as x:
        return "ImportError"
out["imports"] = {n: imp(n) for n in ("ctypes", "_ctypes", "_socket", "socket", "_ssl", "ssl", "_overlapped", "select")}
out["extension_files"] = sorted(p.name for p in pydir.iterdir() if p.suffix.lower() in (".pyd", ".dll"))
with zipfile.ZipFile(pydir / "python311.zip") as z:
    out["zip_ctypes"] = [n for n in z.namelist() if n.startswith("ctypes/")]
import _r3hd_scene_gl
out["bridge_file"] = _r3hd_scene_gl.__file__
import tkinter as tk
import r3hd_level_editor as ed
import r3hd_level_editor_core as core
import r3hd_level_scene as ls
import r3hd_scene_gl as sg
import r3hd_scene_view as sv
r = sg.render_test(game, "intro_20", work / "staged_intro20.png", frames=10)
out["render"] = {k: r[k] for k in ("first_frame_ms", "interactive_ms_median", "upload_seconds", "gl_error",
                                    "window_visible", "readbacks", "covered_share_sampled", "bridge_after_close")}
out["render"]["textures"] = r["renderer"]["textures"]
# S6: open, draw, switch levels, close; three times
cycles = []
for cycle in range(3):
    root = tk.Tk(); root.withdraw()
    t0 = time.perf_counter()
    app, v = sv.open_editor(root, game, show=False)
    v.vp.configure(width=800, height=480); root.update_idletasks()
    c = {"gl": v.ensure_gl(), "open_seconds": round(time.perf_counter() - t0, 3)}
    v.ensure_scene()
    for k in range(3):
        v.cam.orbit(15.0, 2.0); v._draw()
    c["frames"] = v.timing["frames"]
    c["intro_20"] = {"textures": v.r.stats["textures"], "bridge": v.ctx.n.info()["textures"]}
    if cycle == 0:
        for lv in ("intro_15", "intro_10", "intro_20"):
            label = next(ch[2] for ch in ed.CHOICES if ch[0] == "remix" and ch[1] == lv)
            app.dirty = False
            v.choose_level(label)
            v._draw()
            c[lv + "_switch"] = {"level": app.remix["level"], "textures": v.r.stats["textures"],
                                 "bridge": v.ctx.n.info()["textures"], "batches": v.ctx.n.info()["batches"],
                                 "renderer_batches": len(v.r.batches) + (1 if v.r.collision else 0)}
        # S7: the editor's own methods
        ident = next(i for i, a in app.rmodel.actors.items() if a["name"] == "NIK_mChameleon")
        v.select(("actor", ident))
        p = list(app.rmodel.actors[ident]["position"]); p[0] += 2.0
        v.preview = {"sel": ("actor", ident), "pos": tuple(p)}
        v._draw()
        v.apply()
        c["applied"] = len(app.remix["actors"]) == 1
        vr = app.validate_now()
        c["valid"] = vr["ok"]
        app.set_meta("id", "g6p39.staged-remix")
        proj = work / "g6p39_staged.r3hdmap.json"
        app.save_project(proj)
        c["saved_reopen_same"] = core.load_any(proj) == ("v2", app.remix)
        e = app.export_mod(work / "g6p39_staged_mod")
        c["export"] = bool(e["ok"])
        mp = dict(core.mod_paths())
        mp.update(mods=work / "mods", cache=work / "cache", game=Path(game))   # never a real installation's mods
        i = app.import_mod(work / "g6p39_staged_mod", mp) if e["ok"] else {"ok": False}
        c["import_mods"] = str(i.get("mods"))
        c["import"] = bool(i["ok"])
        v.undo()
        c["undone"] = not app.remix["actors"]
        app.dirty = False
    c["viewable"] = bool(v.top.winfo_viewable() or root.winfo_viewable())
    n = v.ctx.n
    v.close(ask=False)
    c["closed"] = n.info().get("closed") is True and v.ctx is None and v.r is None
    try:
        root.destroy()
    except tk.TclError:
        pass
    cycles.append(c)
out["cycles"] = cycles
# S7: the classic 2D editor on the same runtime
root = tk.Tk(); root.withdraw()
a = ed.EditorApp(root, game)
a.set_mode("remix", "intro_20")
k = next(k for k, x in a.rmodel.actors.items() if x["status"] not in ed.REFUSED)
a.set_remix_position(("actor", k), [x + 1.0 for x in a.rmodel.actors[k]["position"]])
out["classic"] = {"loaded": a.rmodel is not None, "valid": a.validate_now()["ok"],
                  "viewable": bool(root.winfo_viewable())}
a.dirty = False
root.destroy()
# S7: missing and corrupt level data
def scene_refusal(g):
    try:
        sg.classified_scene(g, "intro_20")
    except ls.SceneError as x:
        return "SceneError " + x.code
    except (core.EditorError, OSError) as x:
        return type(x).__name__
    except Exception as x:
        return "WRONG " + type(x).__name__ + ": " + str(x)[:120]
    return None
import r3hd_mods as rm
out["missing_data"] = scene_refusal(work / "no_such_game")
bad = work / "corrupt_game"
for lv in ("intro_20", "fix"):
    lvl, ptr, _ = rm.script_level_files(bad, lv)
    for f, n in ((lvl, 4096), (ptr, 64)):
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(bytes((i * 37 + 11) & 0xFF for i in range(n)))
out["corrupt_data"] = scene_refusal(bad)
print("STAGED " + json.dumps(out, default=str))
'''


def run_probe(py, text, args, tag, timeout=900):
    env = {k: v for k, v in os.environ.items() if k.upper() not in ("PYTHONPATH", "PYTHONHOME")}
    env["PATH"] = os.pathsep.join(p for p in env.get("PATH", "").split(os.pathsep) if "python" not in p.lower())
    work = OUT / "probes"
    work.mkdir(parents=True, exist_ok=True)
    f = work / f"{tag}.py"
    f.write_text(text, encoding="utf-8")
    flags = ["-I", "-B"]
    r = subprocess.run([str(py), *flags, str(f), *map(str, args)], capture_output=True, text=True, env=env,
                       cwd=str(work), timeout=timeout)
    for ln in r.stdout.splitlines():
        if ln.startswith(tag.upper() + " "):
            return json.loads(ln[len(tag) + 1:])
    return {"error": r.returncode, "stdout": r.stdout[-600:], "stderr": r.stderr[-1500:]}


def foreign_windows():
    """Window ids of other processes (the desktop and the shell window), read with the development Python only."""
    import ctypes
    u = ctypes.windll.user32
    u.GetDesktopWindow.restype = u.GetShellWindow.restype = ctypes.c_void_p
    return [h for h in (u.GetDesktopWindow(), u.GetShellWindow()) if h]


# ------------------------------------------------------------------------------------------------ S2 parity
def png_pixels(p: Path):
    d = p.read_bytes()
    w, h = struct.unpack(">II", d[16:24])
    pos, idat = 8, b""
    while pos < len(d):
        n, kind = struct.unpack(">I4s", d[pos:pos + 8])
        if kind == b"IDAT":
            idat += d[pos + 8:pos + 8 + n]
        pos += 12 + n
    raw = zlib.decompress(idat)
    rows = [raw[y * (w * 4 + 1) + 1:(y + 1) * (w * 4 + 1)] for y in range(h)]
    assert all(raw[y * (w * 4 + 1)] == 0 for y in range(h))
    return w, h, b"".join(rows)


PARITY_PROBE = r'''
import importlib.util, json, sys
from pathlib import Path
tools, ref, game, out = sys.argv[1], sys.argv[2], sys.argv[3], Path(sys.argv[4])
sys.path.insert(0, tools)
spec = importlib.util.spec_from_file_location("ref_scene_gl", ref)
old = importlib.util.module_from_spec(spec); spec.loader.exec_module(old)
import r3hd_scene_gl as new
CASES = [("intro_20", "overview", False), ("intro_20", "low", True), ("intro_15", "overview", False),
         ("intro_15", "low", False), ("intro_10", "overview", True)]
res = []
for lv, view, markers in CASES:
    row = {"level": lv, "view": view, "markers": markers}
    for rep, (tag, mod) in enumerate((("ctypes", old), ("bridge", new), ("ctypes", old), ("bridge", new))):
        # alternating, twice each: the frame cost is the lower median of the two runs (driver clock noise)
        r = mod.render_test(game, lv, out / f"{lv}_{view}_{int(markers)}_{tag}{rep // 2}.png", view, markers=markers,
                            frames=30)
        if tag in row:
            row[tag]["interactive_ms_median"] = min(row[tag]["interactive_ms_median"], r["interactive_ms_median"])
            row[tag]["runs_ms_median"].append(r["interactive_ms_median"])
            continue
        row[tag] = {k: r[k] for k in ("first_frame_ms", "interactive_ms_median", "interactive_ms_max", "upload_seconds",
                                      "near_black_share_sampled", "distinct_colours_sampled", "covered_share_sampled",
                                      "backdrops_drawn", "gl_error", "readbacks", "window_visible")}
        row[tag]["textures"] = r["renderer"]["textures"]
        row[tag]["vertices"] = r["renderer"]["vertices"]
        row[tag]["png"] = r["out"]
        row[tag]["runs_ms_median"] = [r["interactive_ms_median"]]
    res.append(row)
print("PARITY " + json.dumps(res))
'''


def parity(game: Path):
    ref_dir = OUT / "ref_g6p38"
    ref_dir.mkdir(parents=True, exist_ok=True)
    src = subprocess.run(["git", "show", f"{REF_COMMIT}:tools/r3hd_scene_gl.py"], cwd=ROOT, capture_output=True,
                         check=True).stdout
    (ref_dir / "r3hd_scene_gl_g6p38.py").write_bytes(src)
    shots = OUT / "parity"
    shots.mkdir(parents=True, exist_ok=True)
    res = run_probe(sys.executable, PARITY_PROBE, [TOOLS, ref_dir / "r3hd_scene_gl_g6p38.py", game, shots], "parity")
    if isinstance(res, dict):
        return res
    for row in res:
        w1, h1, a = png_pixels(Path(row["ctypes"]["png"]))
        w2, h2, b = png_pixels(Path(row["bridge"]["png"]))
        n = w1 * h1
        diff = [max(abs(a[i + k] - b[i + k]) for k in range(3)) for i in range(0, len(a), 4)] if (w1, h1) == (w2, h2) \
            else [255]
        row["pixels"] = n
        row["identical_share"] = round(sum(1 for d in diff if d == 0) / n, 5)
        row["over_8_share"] = round(sum(1 for d in diff if d > 8) / n, 5)
        row["max_channel_diff"] = max(diff)
    return res


# ------------------------------------------------------------------------------------------------ check
def check(stage: Path, skip_parity=False):
    sys.path.insert(0, str(TOOLS))
    import r3hd_level_editor_core as core
    game = Path(core.default_game_dir())
    R, D = {}, {}
    OUT.mkdir(parents=True, exist_ok=True)
    foreign = foreign_windows()
    D["foreign_windows"] = len(foreign)
    # S1 in the development Python (the checkout's build) and in the staged runtime
    spy = stage / "payload" / "app" / "python" / "python.exe"
    stools = stage / "payload" / "app" / "tools"
    for tag, py, tools in (("dev", sys.executable, TOOLS), ("staged", spy, stools)):
        b = run_probe(py, BOUNDARY, [tools, json.dumps(foreign)], "boundary")
        D[f"S1_{tag}"] = b
        for k, v in b.get("R", {"probe ran": False}).items():
            R[f"S1 ({tag}) {k}"] = bool(v)
    # S2
    if skip_parity:
        D["S2"] = "skipped"
    else:
        rows = parity(game)
        D["S2"] = rows
        ok = isinstance(rows, list) and len(rows) == 5
        R["S2 five cameras drawn by the G6-P38 ctypes renderer and by the bridge (same scene statistics)"] = ok and all(
            r["ctypes"]["textures"] == r["bridge"]["textures"] and r["ctypes"]["vertices"] == r["bridge"]["vertices"]
            and r["ctypes"]["backdrops_drawn"] == r["bridge"]["backdrops_drawn"] and r["bridge"]["gl_error"] == 0
            and r["bridge"]["readbacks"] == 1 and r["bridge"]["window_visible"] is False for r in rows)
        R["S2 pixels: >= 99.5 % identical and <= 0.1 % differ by more than 8 levels on every camera"] = ok and all(
            r["identical_share"] >= 0.995 and r["over_8_share"] <= 0.001 for r in rows)
        R["S2 no black glow quads come back (near-black share as G6-P38)"] = ok and all(
            r["bridge"]["near_black_share_sampled"] <= r["ctypes"]["near_black_share_sampled"] + 0.001 for r in rows)
        R["S2 interactive frame cost not worse than 1.5x the ctypes renderer (+0.5 ms)"] = ok and all(
            r["bridge"]["interactive_ms_median"] <= 1.5 * r["ctypes"]["interactive_ms_median"] + 0.5 for r in rows)
    # S3
    for name, args, want in (("g6p38_editor_check.py", ["check", "--skip-stage"], "G6-P38 editor check 47/47"),
                             ("g6p37_scene_check.py", ["check"], "G6-P37 scene check 29/29")):
        r = subprocess.run([sys.executable, "-B", str(HERE / name), *args], cwd=ROOT, capture_output=True, text=True,
                           timeout=1800)
        last = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr[-300:]
        D[f"S3_{name}"] = last
        R[f"S3 {name} passes on the bridge ({want})"] = r.returncode == 0 and last == want
    # S4 / S6 / S7 in the staged runtime (the stage itself must not change)
    def snap():
        return sorted((str(f.relative_to(stage)), f.stat().st_size, f.stat().st_mtime_ns)
                      for f in stage.rglob("*") if f.is_file())
    before = snap()
    s = run_probe(spy, STAGED, [stools, game, OUT / "probes"], "staged", timeout=1800)
    R["S7 the staged run wrote nothing into the stage (imports went to a private work folder)"] = (
        snap() == before and str(OUT / "probes").lower() in str(s.get("cycles", [{}])[0].get("import_mods", "")).lower())
    D["staged"] = s
    pydir = str(spy.parent).lower()
    R["S4 the staged python.exe runs isolated from its own folder (no system Python)"] = (
        s.get("prefix", "").lower() == pydir and s.get("isolated") == 1
        and all(str(p).lower().startswith(str(stage).lower()) for p in s.get("path", [""])))
    R["S4 ctypes, _ctypes, socket, _socket, ssl, _ssl, _overlapped and select cannot be imported"] = (
        bool(s.get("imports")) and all(v == "ImportError" for v in s["imports"].values()))
    R["S4 the runtime's native files are the pinned Python, Tk and the bridge only (no _ctypes.pyd, libffi)"] = (
        s.get("extension_files") == sorted(["_r3hd_scene_gl.pyd", "_tkinter.pyd", "python3.dll", "python311.dll",
                                            "tcl86t.dll", "tk86t.dll"]) and s.get("zip_ctypes") == [])
    R["S4 the bridge is imported from the stage"] = str(s.get("bridge_file", "")).lower().startswith(pydir)
    rr = s.get("render", {})
    R["S4 hidden offscreen render on the staged runtime: no GL error, one readback, never visible, all freed"] = (
        rr.get("gl_error") == 0 and rr.get("readbacks") == 1 and rr.get("window_visible") is False
        and rr.get("bridge_after_close") == {"textures": 0, "batches": 0, "bytes": 0} and rr.get("textures", 0) > 0)
    cy = s.get("cycles", [])
    R["S6 the staged 3D editor opens, draws and closes three times; contexts closed; never viewable"] = (
        len(cy) == 3 and all(c["gl"] and c["frames"] >= 3 and c["closed"] and c["viewable"] is False for c in cy))
    c0 = cy[0] if cy else {}
    R["S6 level switches intro_15 / intro_10 / intro_20 free the previous level (bridge textures = renderer textures)"] = (
        all(c0.get(f"{lv}_switch", {}).get("level") == lv and c0[f"{lv}_switch"]["textures"] == c0[f"{lv}_switch"]["bridge"]
            and c0[f"{lv}_switch"]["batches"] == c0[f"{lv}_switch"]["renderer_batches"]
            for lv in ("intro_15", "intro_10", "intro_20")))
    R["S7 staged 3D editor: select, preview, apply, validate, save / reopen, export, import, undo"] = (
        c0.get("applied") and c0.get("valid") and c0.get("saved_reopen_same") and c0.get("export") and c0.get("import")
        and c0.get("undone"))
    R["S7 the classic 2D editor still loads, edits and validates on the same runtime"] = (
        s.get("classic", {}).get("loaded") and s["classic"]["valid"] and s["classic"]["viewable"] is False)
    R["S7 missing level data refuses (TARGET_MISSING); corrupt data refuses with an error the editor handles"] = (
        str(s.get("missing_data", "")).startswith("SceneError") and s.get("corrupt_data") is not None
        and not str(s.get("corrupt_data")).startswith("WRONG"))
    # S8 static
    cpp = BRIDGE_SRC.read_text(encoding="utf-8")
    code = re.sub(r"//[^\n]*", "", cpp)
    R["S8 bridge: no library loading, process, file, network, registry, input, cursor, focus or show call"] = not re.search(
        r"\b(LoadLibrary\w*|GetProcAddress|CreateProcess\w*|ShellExecute\w*|CreateFile\w*|fopen|_wfopen|WinExec|socket|"
        r"connect|WSAStartup|Internet\w+|Reg\w+Key\w*|SendInput|keybd_event|mouse_event|SetCursorPos|ClipCursor|"
        r"SetCapture|SetForegroundWindow|SetFocus|ShowWindow|SetWindowPos|SetWindowsHookEx\w*|ChangeDisplaySettings\w*|"
        r"BitBlt|GetDC\(nullptr|GetDC\(NULL|GetWindowDC|PlaySound|Beep|XInput\w*)\b", code)
    procs = re.findall(r'Ext<\w+>\("(\w+)", "(\w+)"\)', code)
    R["S8 bridge: wglGetProcAddress only for the nine framebuffer-object entry points, never from Python data"] = (
        len(procs) == 9 and all(a.startswith("gl") and b == a + "EXT" and ("Framebuffer" in a or "Renderbuffer" in a)
                                for a, b in procs)
        and code.count("wglGetProcAddress(") == 1 and "Proc(name)" not in code.replace("Proc(core)", ""))
    fmts = re.findall(r'PyArg_ParseTuple\w*\(\s*\w+\s*,\s*(?:\w+\s*,\s*)?"([^"]*)"', code)
    D["S8_parse_formats"] = sorted(set(fmts))
    R["S8 bridge: the Python interface takes no pointer or address (argument formats only i / d / p / O; no "
      "PyLong_AsVoidPtr, capsule or buffer write-back)"] = (
        len(fmts) >= 10 and all(set(f) <= set("iOdp|$") for f in fmts) and "PyLong_AsVoidPtr" not in code
        and "PyCapsule" not in code and "PyBUF_WRITABLE" not in code)
    srcs = {n: (TOOLS / n).read_text(encoding="utf-8") for n in ("r3hd_scene_view.py", "r3hd_scene_gl.py",
                                                                 "r3hd_level_scene.py")}
    R["S8 the 3D modules no longer use ctypes (one renderer, through the bridge)"] = not any(
        re.search(r"^\s*(import ctypes|from ctypes)", t, re.M) for t in srcs.values())
    R["S8 no global input, cursor, grab, focus-forcing or desktop capture in the 3D modules"] = not any(
        x in t for t in srcs.values() for x in ("SetCursorPos", "SendInput", "SetWindowsHookEx", "keybd_event",
                                                 "mouse_event", "grab_set_global", "SetForegroundWindow",
                                                 "focus_force", "ImageGrab"))
    ok = all(R.values())
    (OUT / "bridge.json").write_text(json.dumps({"pass": ok, "R": R, "D": D}, indent=1, default=str) + "\n",
                                     encoding="utf-8")
    for k, v in R.items():
        print(f"{'PASS' if v else 'FAIL'} {k}")
    print(f"G6P39_BRIDGE {'PASS' if ok else 'FAIL'} {sum(R.values())}/{len(R)}")
    return 0 if ok else 1


def main(argv):
    if len(argv) < 2 or argv[0] != "check":
        print(__doc__)
        return 2
    return check(Path(argv[1]).resolve(), "--skip-parity" in argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
