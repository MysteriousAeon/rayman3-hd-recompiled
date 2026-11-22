#!/usr/bin/env python3
"""G6-P37 / G6-P39: a small textured 3D view of a level's static scene (Windows, OpenGL 1.1 through _r3hd_scene_gl).

    python tools/r3hd_scene_gl.py render-test LEVEL --out FILE.png [--game DIR] [--view NAME]   # hidden, offscreen
    python tools/r3hd_scene_gl.py view LEVEL [--game DIR]                                     # visible window (a person)

G6-P39 (E-528 / D-295): all native drawing goes through `_r3hd_scene_gl` (tools/scene_gl/r3hd_scene_gl.cpp), a narrow
extension built with the project's own toolchain against the payload's pinned CPython: a context on the editor's own
viewport window (or a hidden offscreen target for tests), checked texture / triangle / line uploads that the extension
copies and owns, a frame of batches in the traced material states, overlay lines and points, swap and one bounded
readback. There is no pointer, DLL name or function name in its interface, and the packaged runtime still has no
ctypes. In a repository checkout the extension is taken from its build folder (tools/scene_gl/build_scene_gl.bat ->
private/work/scene_gl).

Drawing happens on demand (an input, a resize or an expose event), never in a loop, so an idle view uses no CPU or GPU.
The render test never shows a window: it draws into the offscreen target and reads that one frame back once (D-024
bound: one readback per context, enforced by the extension).

Scene data comes from `r3hd_level_scene.Scene` (the person's own files; nothing is cached on disk).
"""
import argparse
import array
import math
import struct
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import r3hd_level_scene as ls  # noqa: E402

MODES = {"opaque": 0, "test": 1, "blend": 2, "add": 3}    # the bridge's mode numbers
_bridge = None


def bridge():
    """The _r3hd_scene_gl extension: beside the packaged Python, or a repository checkout's build folder."""
    global _bridge
    if _bridge is not None:
        return _bridge
    if sys.platform != "win32":
        raise ls.SceneError("UNSUPPORTED", "the 3D view needs Windows (opengl32.dll)")
    try:
        import _r3hd_scene_gl as b
    except ImportError:
        root = Path(__file__).resolve().parents[1]
        dev = root / "private" / "work" / "scene_gl"
        if not (root / "config" / "release" / "payload.json").is_file() or not (dev / "_r3hd_scene_gl.pyd").is_file():
            raise ls.SceneError("GL_UNAVAILABLE", "the 3D view's OpenGL bridge (_r3hd_scene_gl) is not installed; "
                                                  "a checkout builds it with tools\\scene_gl\\build_scene_gl.bat")
        sys.path.append(str(dev))
        try:
            import _r3hd_scene_gl as b
        except ImportError as x:
            raise ls.SceneError("GL_UNAVAILABLE", f"the 3D view's OpenGL bridge could not load: {x}")
    if abs(b.LIMITS["alpha_ref"] - ls.ALPHA_REF) > 1e-6:
        raise ls.SceneError("GL_UNAVAILABLE", "the OpenGL bridge was built for another alpha reference")
    _bridge = b
    return b


class Context:
    """The bridge's context on a window of this thread (the editor's Tk viewport), or offscreen=(w, h) for tests."""

    def __init__(self, hwnd=None, offscreen=None):
        b = bridge()
        try:
            self.n = b.Context(hwnd=hwnd) if offscreen is None else b.Context(offscreen=tuple(offscreen))
        except (ValueError, TypeError, RuntimeError) as x:
            raise ls.SceneError("GL_UNAVAILABLE", str(x))
        i = self.n.info()
        self.info = {k: i[k] for k in ("vendor", "renderer", "version")}

    def current(self):
        self.n.make_current()

    def swap(self):
        self.n.present()

    def finish(self):
        self.n.finish()

    def close(self):
        self.n.close()


# ------------------------------------------------------------------------------------------------- math
def perspective(fovy, aspect, near, far):
    f = 1.0 / math.tan(math.radians(fovy) / 2)
    return [[f / aspect, 0, 0, 0], [0, f, 0, 0], [0, 0, (far + near) / (near - far), 2 * far * near / (near - far)],
            [0, 0, -1, 0]]


def look_at(eye, target, up=(0.0, 0.0, 1.0)):
    fw = [t - e for t, e in zip(target, eye)]
    n = math.sqrt(sum(c * c for c in fw)) or 1.0
    fw = [c / n for c in fw]
    s = [fw[1] * up[2] - fw[2] * up[1], fw[2] * up[0] - fw[0] * up[2], fw[0] * up[1] - fw[1] * up[0]]
    n = math.sqrt(sum(c * c for c in s)) or 1.0
    s = [c / n for c in s]
    u = [s[1] * fw[2] - s[2] * fw[1], s[2] * fw[0] - s[0] * fw[2], s[0] * fw[1] - s[1] * fw[0]]
    return [[s[0], s[1], s[2], -sum(a * b for a, b in zip(s, eye))],
            [u[0], u[1], u[2], -sum(a * b for a, b in zip(u, eye))],
            [-fw[0], -fw[1], -fw[2], sum(a * b for a, b in zip(fw, eye))], [0, 0, 0, 1]]


def mul(a, b):
    return [[sum(a[r][k] * b[k][c] for k in range(4)) for c in range(4)] for r in range(4)]


def column_major(m):
    return [float(m[r][c]) for c in range(4) for r in range(4)]


def inverse(m):
    """4x4 inverse (Gauss-Jordan); used only to unproject a mouse position."""
    a = [list(map(float, row)) + [1.0 if i == j else 0.0 for j in range(4)] for i, row in enumerate(m)]
    for c in range(4):
        p = max(range(c, 4), key=lambda r: abs(a[r][c]))
        a[c], a[p] = a[p], a[c]
        d = a[c][c] or 1e-12
        a[c] = [v / d for v in a[c]]
        for r in range(4):
            if r != c:
                k = a[r][c]
                a[r] = [x - k * y for x, y in zip(a[r], a[c])]
    return [row[4:] for row in a]


class Camera:
    """Orbit camera around a target, z up (the title's world axes). yaw / pitch in degrees."""

    def __init__(self):
        self.target, self.yaw, self.pitch, self.dist, self.fov = [0.0, 0.0, 0.0], -60.0, 25.0, 50.0, 55.0

    def eye(self):
        cy, sy = math.cos(math.radians(self.yaw)), math.sin(math.radians(self.yaw))
        cp, sp = math.cos(math.radians(self.pitch)), math.sin(math.radians(self.pitch))
        return [self.target[0] + self.dist * cp * cy, self.target[1] + self.dist * cp * sy,
                self.target[2] + self.dist * sp]

    def matrices(self, w, h):
        near = max(0.05, self.dist * 0.002)
        return perspective(self.fov, w / max(h, 1), near, max(2000.0, self.dist * 20)), look_at(self.eye(), self.target)

    def fit(self, lo, hi):
        self.target = [(a + b) / 2 for a, b in zip(lo, hi)]
        r = max(1.0, math.dist(lo, hi) / 2)
        self.dist = r / math.tan(math.radians(self.fov) / 2) * 1.05

    def orbit(self, dx, dy):
        self.yaw -= dx * 0.4
        self.pitch = max(-89.0, min(89.0, self.pitch + dy * 0.4))

    def look(self, dx, dy):
        """Free-look: turn the view about the eye (the eye stays where it is), 0.25 degrees per pixel."""
        eye = self.eye()
        self.yaw -= dx * 0.25
        self.pitch = max(-89.0, min(89.0, self.pitch + dy * 0.25))
        cy, sy = math.cos(math.radians(self.yaw)), math.sin(math.radians(self.yaw))
        cp, sp = math.cos(math.radians(self.pitch)), math.sin(math.radians(self.pitch))
        self.target = [eye[0] - self.dist * cp * cy, eye[1] - self.dist * cp * sy, eye[2] - self.dist * sp]

    def basis(self):
        e = self.eye()
        fw = [t - c for t, c in zip(self.target, e)]
        n = math.sqrt(sum(c * c for c in fw)) or 1.0
        fw = [c / n for c in fw]
        right = [fw[1], -fw[0], 0.0]
        n = math.hypot(right[0], right[1]) or 1.0
        right = [right[0] / n, right[1] / n, 0.0]
        up = [right[1] * fw[2], -right[0] * fw[2], right[0] * fw[1] - right[1] * fw[0]]
        return fw, right, up

    def pan(self, dx, dy, h):
        _, right, up = self.basis()
        k = 2 * self.dist * math.tan(math.radians(self.fov) / 2) / max(h, 1)
        self.target = [t - right[i] * dx * k + up[i] * dy * k for i, t in enumerate(self.target)]

    def zoom(self, factor):
        self.dist = max(0.5, min(5000.0, self.dist * factor))

    def fly(self, forward, sideways, vertical, step):
        fw, right, _ = self.basis()
        flat = [fw[0], fw[1], 0.0]
        n = math.hypot(flat[0], flat[1]) or 1.0
        for i in range(3):
            self.target[i] += (flat[i] / n * forward + right[i] * sideways) * step
        self.target[2] += vertical * step


# ------------------------------------------------------------------------------------------------- renderer
STATUS_RGB = {"verified": (0.15, 0.85, 0.30), "placement": (0.10, 0.75, 0.85), "experimental": (1.0, 0.70, 0.10),
              "supported": (0.55, 0.65, 1.0), "locked": (0.55, 0.55, 0.55), "script_overridden": (0.55, 0.55, 0.55)}
# G6-P38 (E-527 / D-294): draw order and states per material mode, from the traced intro_15 frames:
#   opaque  blend ONE / ZERO, depth write, no alpha test
#   test    alpha test GEQUAL 0.7529 (traced RB_ALPHA_REF), depth write
#   add     SRC_ALPHA / ONE, depth test without depth write
#   blend   (layer byte 0x03, never traced) SRC_ALPHA / 1-SRC_ALPHA without depth write: labelled approximation
# Backdrops (sky domes) are drawn first without depth writes and only while the camera is inside them; an opaque
# backdrop layer is alpha-blended as the traced clouds draw (blend 0x0706). Runtime-placed objects are not drawn.
MODE_ORDER = ("opaque", "test", "blend", "add")
BACKGROUND = (0.30, 0.36, 0.45)          # neutral backdrop colour when no sky dome surrounds the camera


TEXTURE_ERRORS = (ls.SceneError, OSError, ValueError, TypeError, RuntimeError, IndexError, KeyError, struct.error)


class Cancelled(Exception):
    """G6-P69: a CPU preparation abandoned because a newer request or a closing window superseded it."""


class Prepared:
    """G6-P69: everything a Renderer needs that is CPU work only - vertex batches expanded from the scene and textures
    decoded from the bundle - as plain bytes / arrays. No OpenGL and no Tk: it may be built on a worker thread and is
    handed to Renderer on the thread that owns the GL context. `cancelled` (a callable) is polled between objects and
    textures; when it returns true, Cancelled is raised and the partial work is dropped."""

    def __init__(self, scene: ls.Scene, max_side=256, shade=True, cancelled=None):
        self.max_side, self.shade = max_side, shade
        self.groups, self.boxes, self.textures = {}, {}, {}
        self.hidden_runtime_placed = 0
        self.seconds = {}
        stop = cancelled or (lambda: False)
        t0 = time.perf_counter()
        self._expand(scene, stop)
        t1 = time.perf_counter()
        for key in self.groups:                    # the textures of drawn batches only, in batch order
            if key[0] is None or key[0] in self.textures:
                continue
            if stop():
                raise Cancelled()
            try:
                self.textures[key[0]] = scene.decode_texture(key[0], max_side)
            except TEXTURE_ERRORS as x:             # a damaged texture is reported, the rest still draws
                self.textures[key[0]] = f"{scene.textures[key[0]]['name']}: {x}"
        self.seconds = {"expand": round(t1 - t0, 4), "decode": round(time.perf_counter() - t1, 4)}

    def _expand(self, scene, stop):
        groups, boxes = self.groups, self.boxes
        light = (0.35, -0.45, 0.82)
        for o in scene.objects:
            if stop():
                raise Cancelled()
            role = o.get("role", "scene")
            if role == "runtime_placed":
                self.hidden_runtime_placed += 1
                continue
            V = o["vertices"]
            for e in o["elements"]:
                key = (e["texture"], e["mode"] if e["texture"] is not None else "opaque", role,
                       o["superobject"] if role == "backdrop" else None)
                if role == "backdrop":
                    boxes[key] = o.get("box") or ([min(v[k] for v in V) for k in range(3)],
                                                  [max(v[k] for v in V) for k in range(3)])
                pos, uv, col = groups.setdefault(key, (array.array("f"), array.array("f"), array.array("B")))
                t = e["tri"]
                lit = self.shade and role == "scene" and key[1] in ("opaque", "test")
                for j in range(e["triangles"]):
                    a, b, c = V[t[3 * j]], V[t[3 * j + 1]], V[t[3 * j + 2]]
                    s = 255
                    if lit:
                        nx = (b[1] - a[1]) * (c[2] - a[2]) - (b[2] - a[2]) * (c[1] - a[1])
                        ny = (b[2] - a[2]) * (c[0] - a[0]) - (b[0] - a[0]) * (c[2] - a[2])
                        nz = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
                        n = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
                        s = int(255 * (0.55 + 0.45 * abs(nx * light[0] + ny * light[1] + nz * light[2]) / n))
                    grey = 150 if e["texture"] is None else 255
                    shade = (s * grey // 255,) * 3 + (255,)
                    for k, p in enumerate((a, b, c)):
                        pos.extend(p)
                        if e["uvt"]:
                            ui = e["uvt"][3 * j + k]
                            uv.extend((e["uv"][2 * ui], e["uv"][2 * ui + 1]))
                        else:
                            uv.extend((0.0, 0.0))
                        col.extend(shade)


class Renderer:
    """Batches of a Scene grouped by (texture, mode, role); textures from the bundle's own stored mip levels. The
    vertex data and textures are copied into the bridge, which owns them until close().

    G6-P69: the CPU part is a `Prepared` (built here when not given); the constructor itself only uploads, so it runs
    on the GL context's thread. If an upload fails, everything already handed to the bridge is released again."""

    def __init__(self, ctx: Context, scene: ls.Scene, max_side=256, shade=True, prepared=None):
        self.ctx, self.scene, self.n = ctx, scene, ctx.n
        self.batches, self.tex_ids = [], {}
        self.stats = {"textures": 0, "texture_errors": [], "texels": 0, "hidden_runtime_placed": 0}
        self.overlays = {"points": [], "lines": [], "selected": None, "ghost": None}
        self.show = {"scene": True, "backdrop": True, "collision": False, "overlays": True}
        self.collision = None
        self.shade = shade
        t0 = time.perf_counter()
        if prepared is None:
            prepared = Prepared(scene, max_side, shade)
        t1 = time.perf_counter()
        try:
            self._build(prepared)
        except BaseException:
            self.close()                             # no handle of a half-built renderer is left in the bridge
            raise
        self.stats["upload_seconds"] = round(time.perf_counter() - t1, 4)
        self.stats["prepare_seconds"] = prepared.seconds
        self.stats["build_seconds"] = round(time.perf_counter() - t0, 3)

    def _upload(self, key, prepared):
        if key in self.tex_ids:
            return self.tex_ids[key]
        got = prepared.textures.get(key)
        try:
            if isinstance(got, str):
                raise ls.SceneError("TEXTURE", got)
            w, h, rgba = got
            tid = self.n.texture(w, h, bytes(rgba))
        except TEXTURE_ERRORS as x:                 # a damaged texture is reported, the rest still draws
            self.stats["texture_errors"].append(got if isinstance(got, str)
                                                else f"{self.scene.textures[key]['name']}: {x}")
            self.tex_ids[key] = 0
            return 0
        self.tex_ids[key] = tid
        self.stats["textures"] += 1
        self.stats["texels"] += w * h
        return tid

    def _build(self, prepared):
        self.stats["hidden_runtime_placed"] = prepared.hidden_runtime_placed
        for key, (pos, uv, col) in prepared.groups.items():
            tid = self._upload(key[0], prepared) if key[0] is not None else 0
            try:
                h = self.n.batch(tid, pos, uv, col)
            except (ValueError, TypeError, RuntimeError) as x:
                raise ls.SceneError("GL_UNAVAILABLE", f"the scene could not be handed to the 3D view: {x}")
            self.batches.append({"texture": key[0], "mode": key[1], "role": key[2], "box": prepared.boxes.get(key),
                                 "tid": tid, "count": len(pos) // 3, "handle": h})
        self.stats["batches"] = len(self.batches)
        self.stats["vertices"] = sum(b["count"] for b in self.batches)
        self.stats["modes"] = {m: sum(b["count"] // 3 for b in self.batches if b["mode"] == m and b["role"] == "scene")
                               for m in MODE_ORDER}
        self.stats["backdrop_batches"] = sum(1 for b in self.batches if b["role"] == "backdrop")

    def set_collision(self, tris):
        if self.collision is not None:
            self.n.release(self.collision[0])
            self.collision = None
        if not tris:
            return
        a = array.array("f")
        for t in tris:
            for i, j in ((0, 1), (1, 2), (2, 0)):
                a.extend(t[i])
                a.extend(t[j])
        self.collision = (self.n.lines(a), len(a) // 3)

    def visible_backdrops(self, eye):
        return [b for b in self.batches if b["role"] == "backdrop" and b["box"]
                and all(b["box"][0][k] <= eye[k] <= b["box"][1][k] for k in range(3))]

    def draw(self, cam: Camera, w, h):
        n = self.n
        proj, view = cam.matrices(w, h)
        n.begin(w, h, BACKGROUND, column_major(proj), column_major(view))
        try:
            if self.show["scene"]:
                if self.show["backdrop"]:
                    for b in self.visible_backdrops(cam.eye()):
                        n.draw(b["handle"], MODES[b["mode"]], True)
                for mode in MODE_ORDER:
                    for b in self.batches:
                        if b["role"] == "scene" and b["mode"] == mode:
                            n.draw(b["handle"], MODES[mode], False)
            if self.show["collision"] and self.collision:
                n.draw_lines(self.collision[0], (0.95, 0.95, 0.35), 1.0)
            if self.show["overlays"]:
                self._overlays()
        finally:
            n.end()
        return proj, view

    def _overlays(self):
        """Editor aids, drawn without depth test: route lines (with chevrons), status markers, the selection and the
        preview ghost; one bridge call per (width, stipple) or point size."""
        n = self.n
        groups = {}

        def rgba(rgb):
            return tuple(int(round(max(0.0, min(1.0, v)) * 255)) for v in rgb) + (255,)

        def seg(a, b, rgb, width, stipple):
            pos, col = groups.setdefault((width, stipple), (array.array("f"), array.array("B")))
            pos.extend(a)
            pos.extend(b)
            col.extend(rgba(rgb) * 2)
        for a, b, rgb, width, stipple, arrow in self.overlays["lines"]:
            st = (2, 0x0F0F) if stipple else (0, 0xFFFF)
            seg(a, b, rgb, width, st)
            if arrow:                                      # a chevron at 60 %, in the horizontal plane
                d = [b[i] - a[i] for i in range(3)]
                ln = math.hypot(d[0], d[1]) or 1.0
                ux, uy = d[0] / ln, d[1] / ln
                m = [a[i] + 0.6 * d[i] for i in range(3)]
                s = min(0.9, 0.25 * math.sqrt(sum(c * c for c in d)))
                for side in (-1, 1):
                    seg(m, (m[0] - s * ux + side * s * 0.6 * -uy, m[1] - s * uy + side * s * 0.6 * ux, m[2]), rgb,
                        width, st)
        gh = self.overlays["ghost"]
        if gh:                                             # (original, preview) and a drop line below the preview
            seg(gh[0], gh[1], (1.0, 1.0, 1.0), 2.0, (1, 0x3333))
            seg(gh[1], (gh[1][0], gh[1][1], gh[1][2] - 30.0), (1.0, 1.0, 1.0), 2.0, (1, 0x3333))
        for (width, (factor, pattern)), (pos, col) in groups.items():
            n.overlay_lines(pos, col, width, factor, pattern)

        def points(items, size):
            if not items:
                return
            pos, col = array.array("f"), array.array("B")
            for p, rgb in items:
                pos.extend(p)
                col.extend(rgba(rgb))
            n.overlay_points(pos, col, size)
        # markers: a dark rim then the status colour, so they read as editor symbols, not as the object's model
        pts = self.overlays["points"]
        points([(p, (0.05, 0.05, 0.08)) for p, _, _ in pts], 11.0)
        points([(p, rgb) for p, rgb, _ in pts], 7.0)
        sel = self.overlays["selected"]
        if sel:
            points([(sel, (1.0, 1.0, 1.0))], 17.0)
            points([(sel, (1.0, 0.2, 0.8))], 9.0)
        if gh:
            points([(gh[1], (1.0, 1.0, 1.0))], 15.0)
            points([(gh[1], (0.1, 0.1, 0.1))], 9.0)

    def close(self):
        """Free every texture, batch and line set this renderer handed to the bridge."""
        ids = [t for t in self.tex_ids.values() if t]
        for h in ids + [b["handle"] for b in self.batches] + ([self.collision[0]] if self.collision else []):
            self.n.release(h)
        self.stats["textures_freed"] = len(ids)
        self.tex_ids, self.batches, self.collision = {}, [], None


def project(proj, view, w, h, p):
    """Screen position (x, y from top) and clip w of a world point, or None behind the camera."""
    m = mul(proj, view)
    v = [sum(m[r][k] * (p[k] if k < 3 else 1.0) for k in range(4)) for r in range(4)]
    if v[3] <= 1e-6:
        return None
    return ((v[0] / v[3] + 1) * w / 2, (1 - v[1] / v[3]) * h / 2, v[3])


def unproject_ray(proj, view, w, h, x, y):
    inv = inverse(mul(proj, view))
    nx, ny = 2 * x / w - 1, 1 - 2 * y / h
    pts = []
    for z in (-1.0, 1.0):
        v = [sum(inv[r][k] * c for k, c in enumerate((nx, ny, z, 1.0))) for r in range(4)]
        pts.append([v[i] / v[3] for i in range(3)])
    d = [b - a for a, b in zip(*pts)]
    n = math.sqrt(sum(c * c for c in d)) or 1.0
    return pts[0], [c / n for c in d]


# ------------------------------------------------------------------------------------------------- offscreen test
VIEWS = {   # named cameras for the render test: (yaw, pitch, distance factor of the fitted distance)
    "overview": (-60.0, 35.0, 0.9),
    "low": (-120.0, 12.0, 0.45),
}


def classified_scene(game, level, model=None, view=False):
    """Scene with G6-P38 roles from the editor's own read-only model (collision + actor positions). view=True (G6-P68)
    reads any other level with the never-editable ViewModel; a level whose actors cannot be read is drawn unclassified."""
    import r3hd_level_editor_core as core
    scene = ls.Scene(game, level)
    if model is None and level in core.remix_level_names():
        model = core.RemixModel(game, level)
    elif model is None and view:
        try:
            model = core.ViewModel(game, level)
        except core.EditorError:
            model = None
    if model is not None:
        scene.classify([p for t in model.tris for p in t] + [a["position"] for a in model.actors.values()])
    return scene, model


def render_test(game, level, out: Path, view="overview", size=(960, 540), max_side=256, camera=None, markers=False,
                frames=30, view_only=False):
    """Draw the scene into a framebuffer object of a never-shown window: `frames` timed frames of a moving camera
    (no readback), then the requested camera once with one bounded readback to a private PNG. Statistics only."""
    t0 = time.perf_counter()
    scene, model = classified_scene(game, level, view=view_only)
    t_scene = time.perf_counter() - t0
    w, h = size
    ctx = Context(offscreen=(w, h))
    try:
        t1 = time.perf_counter()
        r = Renderer(ctx, scene, max_side=max_side)
        if markers and model is not None:
            r.overlays["points"] = [(a["position"], STATUS_RGB.get(a["status"], (1, 1, 1)), ("actor", ident))
                                    for ident, a in model.actors.items()]
        t2 = time.perf_counter()
        cam = Camera()
        cam.fit(*scene.view_bounds())
        times = []
        for i in range(frames):                       # interactive cost: orbiting camera, no readback
            cam.orbit(4.0, 0.0)
            ts = time.perf_counter()
            r.draw(cam, w, h)
            ctx.finish()
            times.append(time.perf_counter() - ts)
        cam = Camera()
        cam.fit(*scene.view_bounds())
        if camera:
            cam.target, cam.yaw, cam.pitch, cam.dist = list(camera["target"]), camera["yaw"], camera["pitch"], camera["dist"]
        else:
            yaw, pitch, k = VIEWS[view]
            cam.yaw, cam.pitch, cam.dist = yaw, pitch, cam.dist * k
        ts = time.perf_counter()
        r.draw(cam, w, h)
        ctx.finish()
        t_frame = time.perf_counter() - ts
        raw = ctx.n.read_pixels()                                             # the one readback
        rows = b"".join(raw[(h - 1 - y) * w * 4:(h - y) * w * 4] for y in range(h))   # GL rows are bottom-up
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(ls.rm.write_png(w, h, rows))
        bg = bytes(int(round(c * 255)) for c in BACKGROUND)
        covered = sum(1 for i in range(0, len(rows), 4 * 7) if rows[i:i + 3] != bg)
        dark = sum(1 for i in range(0, len(rows), 4 * 7) if max(rows[i:i + 3]) < 8)
        distinct = len({rows[i:i + 3] for i in range(0, len(rows), 4 * 13)})
        info = ctx.n.info()
        backdrops = len(r.visible_backdrops(cam.eye()))
        err = ctx.n.error()
        r.close()
        freed = ctx.n.info()
        times.sort()
        return {"level": level, "hashes": scene.hashes, "gl": ctx.info, "size": [w, h], "view": camera or view,
                "camera": {"target": [round(c, 3) for c in cam.target], "yaw": cam.yaw, "pitch": cam.pitch,
                           "dist": round(cam.dist, 3)},
                "renderer": r.stats, "roles": scene.summary()["roles"], "scene_seconds": round(t_scene, 3),
                "upload_seconds": round(t2 - t1, 3), "first_frame_ms": round(t_frame * 1000, 2),
                "interactive_frames": frames,
                "interactive_ms_median": round(times[len(times) // 2] * 1000, 2) if times else None,
                "interactive_ms_max": round(times[-1] * 1000, 2) if times else None,
                "readbacks": info["readbacks"], "window_visible": info["window_visible"],
                "backdrops_drawn": backdrops, "bridge_bytes": info["bytes"],
                "bridge_after_close": {k: freed[k] for k in ("textures", "batches", "bytes")},
                "covered_share_sampled": round(covered / (w * h / 7), 3),
                "near_black_share_sampled": round(dark / (w * h / 7), 4), "distinct_colours_sampled": distinct,
                "gl_error": err,
                "out": str(out), "note": "game-derived picture: keep it under private/"}
    finally:
        ctx.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", choices=("render-test", "view"))
    ap.add_argument("level", nargs="?", default="intro_20")
    ap.add_argument("--game", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--view", default="overview", choices=sorted(VIEWS))
    ap.add_argument("--max-side", type=int, default=256)
    ap.add_argument("--camera", help="x,y,z,yaw,pitch,distance (orbit target and angles, world units)")
    ap.add_argument("--markers", action="store_true", help="draw the editor's actor markers")
    a = ap.parse_args()
    import json
    if a.game is None:
        import r3hd_level_editor_core as core
        a.game = core.default_game_dir()
    if a.cmd == "render-test":
        if not a.out:
            ap.error("--out is required (a path under private/)")
        cam = None
        if a.camera:
            v = [float(x) for x in a.camera.split(",")]
            cam = {"target": v[:3], "yaw": v[3], "pitch": v[4], "dist": v[5]}
        print(json.dumps(render_test(a.game, a.level, a.out, a.view, max_side=a.max_side, camera=cam,
                                     markers=a.markers), indent=1, default=str))
        return 0
    import r3hd_scene_view as sv
    return sv.standalone(a.game, a.level)


if __name__ == "__main__":
    sys.exit(main())
