// G6-P39 (E-528 / D-295): _r3hd_scene_gl, the narrow OpenGL bridge of the 3D Level Remix Editor.
//
// The packaged Python runtime has no _ctypes / libffi (config/release/payload.json). This extension gives the 3D view
// exactly the drawing it needs and nothing general:
//
//   Context(hwnd=H)            a WGL context on H, which must be a live child window created by THIS thread of THIS
//                              process (the editor's own Tk viewport); one context per window
//   Context(offscreen=(w, h))  a never-shown window of the module's own plus a w x h framebuffer object (tests)
//   texture(w, h, rgba)        upload one RGBA8 texture (bytes, 1..4096 per side, exactly w*h*4 bytes) -> handle
//   batch(tex, pos, uv, col)   copy one triangle list (float32 xyz / float32 uv / uint8 rgba per vertex) -> handle
//   lines(pos)                 copy one line list (float32 xyz) -> handle
//   release(handle)            free one texture or batch of this context
//   begin(w, h, clear_rgb, projection16, view16)
//   draw(batch, mode, backdrop)            mode 0 opaque, 1 alpha test (traced ref 0.7529), 2 blend, 3 additive
//   draw_lines(lines, rgb, width)
//   overlay_lines(pos, col, width, stipple_factor, stipple_pattern)   editor aids, drawn without depth test
//   overlay_points(pos, col, size)
//   end()  finish()  present()  read_pixels()  error()  info()  close()
//
// There is no pointer, address, DLL name, function name or callback anywhere in this interface. Every buffer is
// copied into memory owned by the context after its type (array 'f' / bytes 'B'), length, count, range and
// finiteness are checked; handles are this context's own counters, never GL names or addresses. A context is
// confined to the thread that created it. Limits are in kLimits below and exposed as LIMITS. This is not a sandbox:
// it removes the general native-call facility from the editor's runtime; it does not make arbitrary Python safe.
#define PY_SSIZE_T_CLEAN
#include <Python.h>

#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <GL/gl.h>

#include <climits>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <memory>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <new>
#include <vector>

namespace {

// ------------------------------------------------------------------------------------------------ limits
constexpr int kMaxTextureSide = 4096;
constexpr int kMaxOffscreenSide = 4096;
constexpr int kMaxViewportSide = 16384;
constexpr Py_ssize_t kMaxBatchVertices = 4 * 1024 * 1024;   // per batch / line set
constexpr Py_ssize_t kMaxOverlayVertices = 262144;          // per overlay call
constexpr unsigned long long kMaxContextBytes = 1ull << 30;  // copied geometry + texture bytes per context
constexpr size_t kMaxHandles = 65536;                        // live textures + batches per context
constexpr double kMaxCoordinate = 1.0e9;                     // |x| of any position, uv or matrix element
constexpr GLfloat kAlphaRef = 0.7529f;                       // traced RB_ALPHA_REF (E-527)
constexpr int kMaxReadbacks = 1;                             // per offscreen context (D-024 style bound)
constexpr size_t kMaxContexts = 8;                           // live contexts per process
constexpr int kMaxErrorDrain = 64;                           // glGetError calls before an upload

constexpr GLenum kGenerateMipmap = 0x8191, kFramebuffer = 0x8D40, kRenderbuffer = 0x8D41,
                 kColorAttachment0 = 0x8CE0, kDepthAttachment = 0x8D00, kDepthComponent24 = 0x81A6,
                 kRgba8 = 0x8058, kFramebufferComplete = 0x8CD5;

enum Mode { kOpaque = 0, kTest = 1, kBlend = 2, kAdd = 3 };

typedef void(APIENTRY* GenFn)(GLsizei, GLuint*);
typedef void(APIENTRY* BindFn)(GLenum, GLuint);
typedef void(APIENTRY* StorageFn)(GLenum, GLenum, GLsizei, GLsizei);
typedef void(APIENTRY* AttachFn)(GLenum, GLenum, GLenum, GLuint);
typedef GLenum(APIENTRY* StatusFn)(GLenum);
typedef void(APIENTRY* DeleteFn)(GLsizei, const GLuint*);

struct FboFns {
  GenFn gen_fb = nullptr, gen_rb = nullptr;
  BindFn bind_fb = nullptr, bind_rb = nullptr;
  StorageFn storage = nullptr;
  AttachFn attach = nullptr;
  StatusFn status = nullptr;
  DeleteFn del_fb = nullptr, del_rb = nullptr;
};

// windows that carry a context of this module (one context per window; the GIL guards the set)
std::unordered_set<HWND>& Windows() {
  static std::unordered_set<HWND> w;
  return w;
}

struct Texture {
  GLuint name = 0;
  size_t bytes = 0;
};

struct Batch {
  bool lines = false;
  unsigned texture = 0;  // a texture handle of the same context, 0 = untextured
  std::vector<float> pos, uv;
  std::vector<unsigned char> col;
  GLsizei count = 0;
  size_t bytes = 0;
};

// Everything a context owns. The destructor releases it all, in reverse order of creation, also after a failed
// construction; GL objects are deleted only on the owning thread with the context current.
struct State {
  HWND hwnd = nullptr;
  HDC hdc = nullptr;
  HGLRC rc = nullptr;
  bool owns_window = false, registered = false;
  bool dead = false;  // the window was seen destroyed once: never used again, even if its id is recycled
  DWORD thread = 0;
  GLuint fbo = 0, rb[2] = {0, 0};
  int off_w = 0, off_h = 0;
  FboFns f;
  std::unordered_map<unsigned, Texture> textures;
  std::unordered_map<unsigned, Batch> batches;
  unsigned next = 1;
  unsigned long long bytes = 0;
  bool in_frame = false;
  int frame_w = 0, frame_h = 0, readbacks = 0;
  std::string vendor, renderer, version;

  ~State() {
    bool here = GetCurrentThreadId() == thread;
    if (rc && here && hdc && wglMakeCurrent(hdc, rc)) {
      for (auto& t : textures)
        if (t.second.name) glDeleteTextures(1, &t.second.name);
      if (f.bind_fb) f.bind_fb(kFramebuffer, 0);
      if (rb[0] || rb[1]) f.del_rb(2, rb);
      if (fbo) f.del_fb(1, &fbo);
      glFinish();
    }
    textures.clear();
    batches.clear();
    if (rc) {
      if (here && wglGetCurrentContext() == rc) wglMakeCurrent(nullptr, nullptr);
      wglDeleteContext(rc);
    }
    if (hdc) ReleaseDC(hwnd, hdc);
    if (owns_window && hwnd && here) DestroyWindow(hwnd);
    if (registered) Windows().erase(hwnd);
  }
};

struct Ctx {
  PyObject_HEAD
  State* st;
};

// ------------------------------------------------------------------------------------------------ helpers
PyObject* Fail(PyObject* type, const char* msg) {
  PyErr_SetString(type, msg);
  return nullptr;
}

// A held buffer of an exact item format: 'f' (float32, e.g. array('f')) or 'B' (bytes / bytearray / array('B')).
struct Held {
  Py_buffer view{};
  bool held = false;
  ~Held() {
    if (held) PyBuffer_Release(&view);
  }
  bool Get(PyObject* o, char fmt, const char* what) {
    if (PyObject_GetBuffer(o, &view, PyBUF_C_CONTIGUOUS | PyBUF_FORMAT) != 0) {
      PyErr_Clear();
      PyErr_Format(PyExc_TypeError, "%s must be a contiguous buffer", what);
      return false;
    }
    held = true;
    const char* f = view.format ? view.format : "B";
    if (f[0] == '<' || f[0] == '=' || f[0] == '@') ++f;
    bool ok = f[0] == fmt && f[1] == '\0' && view.itemsize == (fmt == 'f' ? 4 : 1) && view.len >= 0 &&
              (fmt != 'f' || view.len == 0 || reinterpret_cast<uintptr_t>(view.buf) % alignof(float) == 0);
    if (!ok) {
      PyErr_Format(PyExc_TypeError, "%s must hold %s", what, fmt == 'f' ? "float32 items (array('f'))" : "bytes");
      return false;
    }
    return true;
  }
};

bool FiniteFloats(const float* p, size_t n, double bound, const char* what) {
  for (size_t i = 0; i < n; ++i) {
    if (!std::isfinite(p[i]) || std::fabs(p[i]) > bound) {
      PyErr_Format(PyExc_ValueError, "%s holds a value that is not finite or out of range", what);
      return false;
    }
  }
  return true;
}

// exactly n finite floats from a Python sequence of numbers
bool Floats(PyObject* o, Py_ssize_t n, float* out, double lo, double hi, const char* what) {
  PyObject* seq = PySequence_Fast(o, what);
  if (!seq) {
    PyErr_Clear();
    PyErr_Format(PyExc_TypeError, "%s must be a sequence of %zd numbers", what, n);
    return false;
  }
  bool ok = PySequence_Fast_GET_SIZE(seq) == n;
  for (Py_ssize_t i = 0; ok && i < n; ++i) {
    double v = PyFloat_AsDouble(PySequence_Fast_GET_ITEM(seq, i));
    if (v == -1.0 && PyErr_Occurred()) {
      PyErr_Clear();
      ok = false;
      break;
    }
    ok = std::isfinite(v) && v >= lo && v <= hi;
    out[i] = static_cast<float>(v);
  }
  Py_DECREF(seq);
  if (!ok) PyErr_Format(PyExc_ValueError, "%s must be %zd finite numbers in [%g, %g]", what, n, lo, hi);
  return ok;
}

// the context, on its own thread, with its window alive and the context current; else an exception
// a window of this thread of this process
bool OwnWindow(HWND h) {
  DWORD pid = 0;
  DWORD tid = GetWindowThreadProcessId(h, &pid);
  return pid == GetCurrentProcessId() && tid == GetCurrentThreadId();
}

State* Usable(Ctx* self) {
  State* st = self->st;
  const char* err = nullptr;
  if (!st)
    err = "the OpenGL context is closed";
  else if (GetCurrentThreadId() != st->thread)
    err = "the OpenGL context belongs to another thread";
  else if (st->dead || !IsWindow(st->hwnd) || !OwnWindow(st->hwnd)) {
    st->dead = true;
    err = "the window of this OpenGL context no longer exists";
  }
  else if (wglGetCurrentContext() != st->rc && !wglMakeCurrent(st->hdc, st->rc))
    err = "the OpenGL context could not be made current";
  if (err) {
    PyErr_SetString(PyExc_RuntimeError, err);
    return nullptr;
  }
  return st;
}

bool Room(State* st, unsigned long long add) {
  if (st->textures.size() + st->batches.size() >= kMaxHandles || st->next == UINT_MAX) {
    PyErr_SetString(PyExc_ValueError, "too many textures and batches in this context");
    return false;
  }
  if (add > kMaxContextBytes || st->bytes + add > kMaxContextBytes) {
    PyErr_SetString(PyExc_ValueError, "the context's memory limit would be exceeded");
    return false;
  }
  return true;
}

bool Handle(PyObject* o, unsigned* out) {
  unsigned long v = PyLong_AsUnsignedLong(o);
  if (v == static_cast<unsigned long>(-1) && PyErr_Occurred()) {
    PyErr_Clear();
    PyErr_SetString(PyExc_TypeError, "a handle is a non-negative integer");
    return false;
  }
  if (v > UINT_MAX) {
    PyErr_SetString(PyExc_ValueError, "unknown handle");
    return false;
  }
  *out = static_cast<unsigned>(v);
  return true;
}

PROC Proc(const char* name) {
  PROC p = wglGetProcAddress(name);
  intptr_t v = reinterpret_cast<intptr_t>(p);
  return (v == 0 || v == 1 || v == 2 || v == 3 || v == -1) ? nullptr : p;
}

// an internal framebuffer-object entry point (offscreen contexts only; never exposed)
template <typename T>
T Ext(const char* core, const char* ext) {
  PROC p = Proc(core);
  if (!p) p = Proc(ext);
  return reinterpret_cast<T>(reinterpret_cast<void*>(p));
}

// ------------------------------------------------------------------------------------------------ Context
void Ctx_dealloc(Ctx* self) {
  delete self->st;
  self->st = nullptr;
  Py_TYPE(self)->tp_free(reinterpret_cast<PyObject*>(self));
}

PyObject* Ctx_new(PyTypeObject* type, PyObject*, PyObject*) {
  Ctx* self = reinterpret_cast<Ctx*>(type->tp_alloc(type, 0));
  if (self) self->st = nullptr;
  return reinterpret_cast<PyObject*>(self);
}

int Ctx_init(Ctx* self, PyObject* args, PyObject* kw) {
  static const char* names[] = {"hwnd", "offscreen", nullptr};
  PyObject *hwnd_o = Py_None, *off_o = Py_None;
  if (!PyArg_ParseTupleAndKeywords(args, kw, "|$OO", const_cast<char**>(names), &hwnd_o, &off_o)) return -1;
  if (self->st) {
    PyErr_SetString(PyExc_RuntimeError, "the context is already initialised");
    return -1;
  }
  if ((hwnd_o == Py_None) == (off_o == Py_None)) {
    PyErr_SetString(PyExc_TypeError, "give exactly one of hwnd= (the editor's own window) or offscreen=(w, h)");
    return -1;
  }
  std::unique_ptr<State> st(new State());
  st->thread = GetCurrentThreadId();
  if (hwnd_o != Py_None) {
    if (!PyLong_Check(hwnd_o)) {
      PyErr_SetString(PyExc_TypeError, "hwnd must be an integer window id");
      return -1;
    }
    unsigned long long v = PyLong_AsUnsignedLongLong(hwnd_o);
    if (PyErr_Occurred()) {
      PyErr_Clear();
      PyErr_SetString(PyExc_ValueError, "hwnd is not a window id");
      return -1;
    }
    HWND h = reinterpret_cast<HWND>(static_cast<uintptr_t>(v));
    DWORD pid = 0;
    if (!h || !IsWindow(h)) {
      PyErr_SetString(PyExc_ValueError, "hwnd is not a live window");
      return -1;
    }
    DWORD tid = GetWindowThreadProcessId(h, &pid);
    if (pid != GetCurrentProcessId() || tid != GetCurrentThreadId()) {
      PyErr_SetString(PyExc_ValueError, "hwnd must be a window of this thread of this process");
      return -1;
    }
    if (!(GetWindowLongPtrW(h, GWL_STYLE) & WS_CHILD)) {
      PyErr_SetString(PyExc_ValueError, "hwnd must be a child window (the editor's viewport)");
      return -1;
    }
    st->hwnd = h;
  } else {
    int w = 0, h = 0;
    if (!PyArg_ParseTuple(off_o, "ii", &w, &h)) {
      PyErr_Clear();
      PyErr_SetString(PyExc_TypeError, "offscreen must be (width, height)");
      return -1;
    }
    if (w < 1 || h < 1 || w > kMaxOffscreenSide || h > kMaxOffscreenSide) {
      PyErr_SetString(PyExc_ValueError, "offscreen size must be 1..4096 per side");
      return -1;
    }
    // never shown: no WS_VISIBLE, never passed to ShowWindow
    st->hwnd = CreateWindowExW(0, L"STATIC", L"", WS_POPUP, 0, 0, 16, 16, nullptr, nullptr,
                               GetModuleHandleW(nullptr), nullptr);
    if (!st->hwnd) {
      PyErr_SetString(PyExc_RuntimeError, "could not create the hidden window");
      return -1;
    }
    st->owns_window = true;
    st->off_w = w;
    st->off_h = h;
  }
  for (auto it = Windows().begin(); it != Windows().end();)  // windows destroyed under an open context
    it = IsWindow(*it) ? std::next(it) : Windows().erase(it);
  if (Windows().size() >= kMaxContexts && !Windows().count(st->hwnd)) {
    if (st->owns_window) {
      DestroyWindow(st->hwnd);
      st->owns_window = false;
    }
    st->hwnd = nullptr;
    PyErr_SetString(PyExc_RuntimeError, "too many OpenGL contexts are open in this process");
    return -1;
  }
  if (Windows().count(st->hwnd)) {
    if (st->owns_window) {
      DestroyWindow(st->hwnd);
      st->owns_window = false;
    }
    st->hwnd = nullptr;
    PyErr_SetString(PyExc_ValueError, "this window already has an OpenGL context");
    return -1;
  }
  Windows().insert(st->hwnd);
  st->registered = true;
  st->hdc = GetDC(st->hwnd);
  if (!st->hdc) {
    PyErr_SetString(PyExc_RuntimeError, "GetDC failed");
    return -1;
  }
  PIXELFORMATDESCRIPTOR pfd;
  std::memset(&pfd, 0, sizeof pfd);
  pfd.nSize = sizeof pfd;
  pfd.nVersion = 1;
  pfd.dwFlags = PFD_DRAW_TO_WINDOW | PFD_SUPPORT_OPENGL | PFD_DOUBLEBUFFER;
  pfd.iPixelType = PFD_TYPE_RGBA;
  pfd.cColorBits = 32;
  pfd.cDepthBits = 24;
  pfd.cAlphaBits = 8;
  int fmt = ChoosePixelFormat(st->hdc, &pfd);
  if (!fmt || !SetPixelFormat(st->hdc, fmt, &pfd)) {
    PyErr_SetString(PyExc_RuntimeError, "no OpenGL pixel format for this window");
    return -1;
  }
  st->rc = wglCreateContext(st->hdc);
  if (!st->rc || !wglMakeCurrent(st->hdc, st->rc)) {
    PyErr_SetString(PyExc_RuntimeError, "wglCreateContext / wglMakeCurrent failed");
    return -1;
  }
  auto str = [](GLenum e) {
    const GLubyte* s = glGetString(e);
    return s ? std::string(reinterpret_cast<const char*>(s)).substr(0, 200) : std::string();
  };
  st->vendor = str(GL_VENDOR);
  st->renderer = str(GL_RENDERER);
  st->version = str(GL_VERSION);
  if (st->owns_window) {
    FboFns& f = st->f;
    f.gen_fb = Ext<GenFn>("glGenFramebuffers", "glGenFramebuffersEXT");
    f.gen_rb = Ext<GenFn>("glGenRenderbuffers", "glGenRenderbuffersEXT");
    f.bind_fb = Ext<BindFn>("glBindFramebuffer", "glBindFramebufferEXT");
    f.bind_rb = Ext<BindFn>("glBindRenderbuffer", "glBindRenderbufferEXT");
    f.storage = Ext<StorageFn>("glRenderbufferStorage", "glRenderbufferStorageEXT");
    f.attach = Ext<AttachFn>("glFramebufferRenderbuffer", "glFramebufferRenderbufferEXT");
    f.status = Ext<StatusFn>("glCheckFramebufferStatus", "glCheckFramebufferStatusEXT");
    f.del_fb = Ext<DeleteFn>("glDeleteFramebuffers", "glDeleteFramebuffersEXT");
    f.del_rb = Ext<DeleteFn>("glDeleteRenderbuffers", "glDeleteRenderbuffersEXT");
    if (!f.gen_fb || !f.gen_rb || !f.bind_fb || !f.bind_rb || !f.storage || !f.attach || !f.status || !f.del_fb ||
        !f.del_rb) {
      f = FboFns();
      PyErr_SetString(PyExc_RuntimeError, "framebuffer objects are not available");
      return -1;
    }
    f.gen_fb(1, &st->fbo);
    f.bind_fb(kFramebuffer, st->fbo);
    f.gen_rb(2, st->rb);
    const GLenum fmts[2] = {kRgba8, kDepthComponent24}, atts[2] = {kColorAttachment0, kDepthAttachment};
    for (int i = 0; i < 2; ++i) {
      f.bind_rb(kRenderbuffer, st->rb[i]);
      f.storage(kRenderbuffer, fmts[i], st->off_w, st->off_h);
      f.attach(kFramebuffer, atts[i], kRenderbuffer, st->rb[i]);
    }
    if (f.status(kFramebuffer) != kFramebufferComplete) {
      PyErr_SetString(PyExc_RuntimeError, "framebuffer incomplete");
      return -1;
    }
  }
  self->st = st.release();
  return 0;
}

PyObject* Ctx_make_current(Ctx* self, PyObject*) {
  if (!Usable(self)) return nullptr;
  Py_RETURN_NONE;
}

PyObject* Ctx_texture(Ctx* self, PyObject* args) {
  int w = 0, h = 0;
  PyObject* data = nullptr;
  if (!PyArg_ParseTuple(args, "iiO", &w, &h, &data)) return nullptr;
  State* st = Usable(self);
  if (!st) return nullptr;
  if (st->in_frame) return Fail(PyExc_RuntimeError, "textures cannot be uploaded inside a frame");
  if (w < 1 || h < 1 || w > kMaxTextureSide || h > kMaxTextureSide)
    return Fail(PyExc_ValueError, "texture size must be 1..4096 per side");
  Held b;
  if (!b.Get(data, 'B', "texture data")) return nullptr;
  size_t need = static_cast<size_t>(w) * static_cast<size_t>(h) * 4;
  if (static_cast<size_t>(b.view.len) != need) return Fail(PyExc_ValueError, "texture data must be exactly w*h*4 bytes");
  if (!Room(st, need)) return nullptr;
  for (int i = 0; i < kMaxErrorDrain && glGetError() != GL_NO_ERROR; ++i) {
  }
  unsigned id = st->next;
  Texture& slot = st->textures[id];  // the map entry first: nothing GL-side leaks if this allocation fails
  GLuint name = 0;
  glGenTextures(1, &name);
  glBindTexture(GL_TEXTURE_2D, name);
  glPixelStorei(GL_UNPACK_ALIGNMENT, 1);
  glTexParameteri(GL_TEXTURE_2D, kGenerateMipmap, 1);
  glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR_MIPMAP_LINEAR);
  glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
  glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_REPEAT);
  glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_REPEAT);
  glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, w, h, 0, GL_RGBA, GL_UNSIGNED_BYTE, b.view.buf);
  glBindTexture(GL_TEXTURE_2D, 0);
  if (!name || glGetError() != GL_NO_ERROR) {
    if (name) glDeleteTextures(1, &name);
    st->textures.erase(id);
    return Fail(PyExc_RuntimeError, "the texture upload failed");
  }
  st->next++;
  slot = Texture{name, need};
  st->bytes += need;
  return PyLong_FromUnsignedLong(id);
}

PyObject* AddBatch(State* st, Batch&& bt) {
  unsigned id = st->next++;
  st->bytes += bt.bytes;
  st->batches.emplace(id, std::move(bt));
  return PyLong_FromUnsignedLong(id);
}

// float32 xyz positions: vertex count, a multiple of `group`, 1..limit groups
bool Positions(Held& p, Py_ssize_t group, Py_ssize_t limit, Py_ssize_t* n, const char* what) {
  if (p.view.len % 12) {
    PyErr_Format(PyExc_ValueError, "%s must hold whole xyz triples", what);
    return false;
  }
  *n = p.view.len / 12;
  if (*n < group || *n % group || *n > limit) {
    PyErr_Format(PyExc_ValueError, "%s must hold %zd..%zd vertices in groups of %zd", what, group, limit, group);
    return false;
  }
  return FiniteFloats(static_cast<const float*>(p.view.buf), static_cast<size_t>(*n) * 3, kMaxCoordinate, what);
}

PyObject* Ctx_batch(Ctx* self, PyObject* args) {
  PyObject *tex_o, *pos_o, *uv_o, *col_o;
  if (!PyArg_ParseTuple(args, "OOOO", &tex_o, &pos_o, &uv_o, &col_o)) return nullptr;
  State* st = Usable(self);
  if (!st) return nullptr;
  unsigned tex = 0;
  if (!Handle(tex_o, &tex)) return nullptr;
  if (tex && !st->textures.count(tex)) return Fail(PyExc_ValueError, "unknown texture handle");
  Held p, u, c;
  Py_ssize_t n = 0;
  if (!p.Get(pos_o, 'f', "positions") || !u.Get(uv_o, 'f', "uvs") || !c.Get(col_o, 'B', "colours")) return nullptr;
  if (!Positions(p, 3, kMaxBatchVertices, &n, "positions")) return nullptr;
  if (u.view.len != n * 8) return Fail(PyExc_ValueError, "uvs must hold one float32 pair per vertex");
  if (c.view.len != n * 4) return Fail(PyExc_ValueError, "colours must hold four bytes per vertex");
  if (!FiniteFloats(static_cast<const float*>(u.view.buf), static_cast<size_t>(n) * 2, kMaxCoordinate, "uvs"))
    return nullptr;
  size_t bytes = static_cast<size_t>(n) * (12 + 8 + 4);
  if (!Room(st, bytes)) return nullptr;
  Batch bt;
  bt.texture = tex;
  bt.count = static_cast<GLsizei>(n);
  bt.bytes = bytes;
  const float* pf = static_cast<const float*>(p.view.buf);
  const float* uf = static_cast<const float*>(u.view.buf);
  const unsigned char* cb = static_cast<const unsigned char*>(c.view.buf);
  bt.pos.assign(pf, pf + n * 3);
  bt.uv.assign(uf, uf + n * 2);
  bt.col.assign(cb, cb + n * 4);
  return AddBatch(st, std::move(bt));
}

PyObject* Ctx_lines(Ctx* self, PyObject* args) {
  PyObject* pos_o;
  if (!PyArg_ParseTuple(args, "O", &pos_o)) return nullptr;
  State* st = Usable(self);
  if (!st) return nullptr;
  Held p;
  Py_ssize_t n = 0;
  if (!p.Get(pos_o, 'f', "positions") || !Positions(p, 2, kMaxBatchVertices, &n, "positions")) return nullptr;
  size_t bytes = static_cast<size_t>(n) * 12;
  if (!Room(st, bytes)) return nullptr;
  Batch bt;
  bt.lines = true;
  bt.count = static_cast<GLsizei>(n);
  bt.bytes = bytes;
  const float* pf = static_cast<const float*>(p.view.buf);
  bt.pos.assign(pf, pf + n * 3);
  return AddBatch(st, std::move(bt));
}

PyObject* Ctx_release(Ctx* self, PyObject* args) {
  PyObject* h_o;
  if (!PyArg_ParseTuple(args, "O", &h_o)) return nullptr;
  State* st = Usable(self);
  if (!st) return nullptr;
  if (st->in_frame) return Fail(PyExc_RuntimeError, "nothing can be released inside a frame");
  unsigned h = 0;
  if (!Handle(h_o, &h)) return nullptr;
  auto t = st->textures.find(h);
  if (t != st->textures.end()) {
    glDeleteTextures(1, &t->second.name);
    st->bytes -= t->second.bytes;
    st->textures.erase(t);
    Py_RETURN_NONE;
  }
  auto b = st->batches.find(h);
  if (b != st->batches.end()) {
    st->bytes -= b->second.bytes;
    st->batches.erase(b);
    Py_RETURN_NONE;
  }
  return Fail(PyExc_ValueError, "unknown handle");
}

PyObject* Ctx_begin(Ctx* self, PyObject* args) {
  int w = 0, h = 0;
  PyObject *clear_o, *proj_o, *view_o;
  if (!PyArg_ParseTuple(args, "iiOOO", &w, &h, &clear_o, &proj_o, &view_o)) return nullptr;
  State* st = Usable(self);
  if (!st) return nullptr;
  if (st->in_frame) return Fail(PyExc_RuntimeError, "a frame is already open");
  int mw = st->owns_window ? st->off_w : kMaxViewportSide, mh = st->owns_window ? st->off_h : kMaxViewportSide;
  if (w < 1 || h < 1 || w > mw || h > mh) return Fail(PyExc_ValueError, "frame size out of range for this context");
  float clear[3], proj[16], view[16];
  if (!Floats(clear_o, 3, clear, 0.0, 1.0, "clear colour") ||
      !Floats(proj_o, 16, proj, -kMaxCoordinate, kMaxCoordinate, "projection") ||
      !Floats(view_o, 16, view, -kMaxCoordinate, kMaxCoordinate, "view"))
    return nullptr;
  if (st->fbo) st->f.bind_fb(kFramebuffer, st->fbo);
  glViewport(0, 0, w, h);
  glClearColor(clear[0], clear[1], clear[2], 1.0f);
  glDepthMask(GL_TRUE);
  glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT);
  glMatrixMode(GL_PROJECTION);
  glLoadMatrixf(proj);
  glMatrixMode(GL_MODELVIEW);
  glLoadMatrixf(view);
  glDisable(GL_CULL_FACE);
  glEnable(GL_DEPTH_TEST);
  glDepthFunc(GL_LEQUAL);
  glEnableClientState(GL_VERTEX_ARRAY);
  st->in_frame = true;
  st->frame_w = w;
  st->frame_h = h;
  Py_RETURN_NONE;
}

// the traced states of E-527 (see tools/r3hd_scene_gl.py)
void ModeState(int mode, bool backdrop) {
  if (mode == kTest) {
    glEnable(GL_ALPHA_TEST);
    glAlphaFunc(GL_GEQUAL, kAlphaRef);
  } else {
    glDisable(GL_ALPHA_TEST);
  }
  if (backdrop || mode == kBlend || mode == kAdd) {
    glEnable(GL_BLEND);
    glBlendFunc(GL_SRC_ALPHA, mode == kAdd ? GL_ONE : GL_ONE_MINUS_SRC_ALPHA);
    glDepthMask(GL_FALSE);
  } else {
    glDisable(GL_BLEND);
    glDepthMask(GL_TRUE);
  }
  if (mode == kOpaque && !backdrop) {
    glEnable(GL_POLYGON_OFFSET_FILL);
    glPolygonOffset(1.0f, 1.0f);
  } else {
    glDisable(GL_POLYGON_OFFSET_FILL);
  }
}

void ResetState() {
  glDisableClientState(GL_COLOR_ARRAY);
  glDisableClientState(GL_TEXTURE_COORD_ARRAY);
  glDisable(GL_TEXTURE_2D);
  glDisable(GL_ALPHA_TEST);
  glDisable(GL_BLEND);
  glDisable(GL_POLYGON_OFFSET_FILL);
  glDisable(GL_LINE_STIPPLE);
  glDepthMask(GL_TRUE);
  glEnable(GL_DEPTH_TEST);
  glBindTexture(GL_TEXTURE_2D, 0);
}

State* InFrame(Ctx* self) {
  State* st = Usable(self);
  if (st && !st->in_frame) {
    PyErr_SetString(PyExc_RuntimeError, "no frame is open (begin first)");
    return nullptr;
  }
  return st;
}

PyObject* Ctx_draw(Ctx* self, PyObject* args) {
  PyObject* h_o;
  int mode = 0, backdrop = 0;
  if (!PyArg_ParseTuple(args, "Oip", &h_o, &mode, &backdrop)) return nullptr;
  State* st = InFrame(self);
  if (!st) return nullptr;
  unsigned h = 0;
  if (!Handle(h_o, &h)) return nullptr;
  auto it = st->batches.find(h);
  if (it == st->batches.end() || it->second.lines) return Fail(PyExc_ValueError, "unknown triangle batch handle");
  if (mode < kOpaque || mode > kAdd) return Fail(PyExc_ValueError, "mode must be 0..3");
  const Batch& b = it->second;
  ModeState(mode, backdrop != 0);
  auto t = b.texture ? st->textures.find(b.texture) : st->textures.end();
  if (t != st->textures.end()) {
    glEnable(GL_TEXTURE_2D);
    glBindTexture(GL_TEXTURE_2D, t->second.name);
  } else {
    glDisable(GL_TEXTURE_2D);
  }
  glEnableClientState(GL_COLOR_ARRAY);
  glEnableClientState(GL_TEXTURE_COORD_ARRAY);
  glVertexPointer(3, GL_FLOAT, 0, b.pos.data());
  glTexCoordPointer(2, GL_FLOAT, 0, b.uv.data());
  glColorPointer(4, GL_UNSIGNED_BYTE, 0, b.col.data());
  glDrawArrays(GL_TRIANGLES, 0, b.count);
  ResetState();
  Py_RETURN_NONE;
}

PyObject* Ctx_draw_lines(Ctx* self, PyObject* args) {
  PyObject *h_o, *rgb_o;
  double width = 1.0;
  if (!PyArg_ParseTuple(args, "OOd", &h_o, &rgb_o, &width)) return nullptr;
  State* st = InFrame(self);
  if (!st) return nullptr;
  unsigned h = 0;
  if (!Handle(h_o, &h)) return nullptr;
  auto it = st->batches.find(h);
  if (it == st->batches.end() || !it->second.lines) return Fail(PyExc_ValueError, "unknown line set handle");
  float rgb[3];
  if (!Floats(rgb_o, 3, rgb, 0.0, 1.0, "colour")) return nullptr;
  if (!(width >= 0.5 && width <= 16.0)) return Fail(PyExc_ValueError, "line width must be 0.5..16");
  ResetState();
  glColor4f(rgb[0], rgb[1], rgb[2], 1.0f);
  glLineWidth(static_cast<GLfloat>(width));
  glVertexPointer(3, GL_FLOAT, 0, it->second.pos.data());
  glDrawArrays(GL_LINES, 0, it->second.count);
  Py_RETURN_NONE;
}

// overlays: per-vertex colours, depth test off (editor aids stay visible through walls). Everything is checked
// before any state changes; the state is reset afterwards.
PyObject* Overlay(Ctx* self, PyObject* pos_o, PyObject* col_o, bool lines, double width, int factor, int pattern,
                  double size) {
  State* st = InFrame(self);
  if (!st) return nullptr;
  Held p, c;
  Py_ssize_t n = 0;
  if (!p.Get(pos_o, 'f', "positions") || !c.Get(col_o, 'B', "colours")) return nullptr;
  if (p.view.len == 0 && c.view.len == 0) Py_RETURN_NONE;
  if (!Positions(p, lines ? 2 : 1, kMaxOverlayVertices, &n, "positions")) return nullptr;
  if (c.view.len != n * 4) return Fail(PyExc_ValueError, "colours must hold four bytes per vertex");
  std::vector<float> pos(static_cast<const float*>(p.view.buf), static_cast<const float*>(p.view.buf) + n * 3);
  std::vector<unsigned char> col(static_cast<const unsigned char*>(c.view.buf),
                                 static_cast<const unsigned char*>(c.view.buf) + n * 4);
  ResetState();
  glDisable(GL_DEPTH_TEST);
  if (lines) {
    glLineWidth(static_cast<GLfloat>(width));
    if (factor) {
      glEnable(GL_LINE_STIPPLE);
      glLineStipple(factor, static_cast<GLushort>(pattern));
    }
  } else {
    glPointSize(static_cast<GLfloat>(size));
  }
  glEnableClientState(GL_COLOR_ARRAY);
  glVertexPointer(3, GL_FLOAT, 0, pos.data());
  glColorPointer(4, GL_UNSIGNED_BYTE, 0, col.data());
  glDrawArrays(lines ? GL_LINES : GL_POINTS, 0, static_cast<GLsizei>(n));
  ResetState();
  Py_RETURN_NONE;
}

PyObject* Ctx_overlay_lines(Ctx* self, PyObject* args) {
  PyObject *pos_o, *col_o;
  double width = 1.0;
  int factor = 0, pattern = 0xFFFF;
  if (!PyArg_ParseTuple(args, "OOdii", &pos_o, &col_o, &width, &factor, &pattern)) return nullptr;
  if (!(width >= 0.5 && width <= 16.0)) return Fail(PyExc_ValueError, "line width must be 0.5..16");
  if (factor < 0 || factor > 256 || pattern < 0 || pattern > 0xFFFF)
    return Fail(PyExc_ValueError, "stipple factor must be 0..256 and pattern 0..0xFFFF");
  return Overlay(self, pos_o, col_o, true, width, factor, pattern, 1.0);
}

PyObject* Ctx_overlay_points(Ctx* self, PyObject* args) {
  PyObject *pos_o, *col_o;
  double size = 1.0;
  if (!PyArg_ParseTuple(args, "OOd", &pos_o, &col_o, &size)) return nullptr;
  if (!(size >= 1.0 && size <= 64.0)) return Fail(PyExc_ValueError, "point size must be 1..64");
  return Overlay(self, pos_o, col_o, false, 1.0, 0, 0xFFFF, size);
}

PyObject* Ctx_end(Ctx* self, PyObject*) {
  State* st = InFrame(self);
  if (!st) return nullptr;
  ResetState();
  glDisableClientState(GL_VERTEX_ARRAY);
  st->in_frame = false;
  Py_RETURN_NONE;
}

PyObject* Ctx_finish(Ctx* self, PyObject*) {
  if (!Usable(self)) return nullptr;
  glFinish();
  Py_RETURN_NONE;
}

PyObject* Ctx_present(Ctx* self, PyObject*) {
  State* st = Usable(self);
  if (!st) return nullptr;
  if (st->owns_window) return Fail(PyExc_RuntimeError, "an offscreen context has nothing to present");
  if (st->in_frame) return Fail(PyExc_RuntimeError, "end the frame first");
  SwapBuffers(st->hdc);
  Py_RETURN_NONE;
}

PyObject* Ctx_read_pixels(Ctx* self, PyObject*) {
  State* st = Usable(self);
  if (!st) return nullptr;
  if (!st->owns_window) return Fail(PyExc_RuntimeError, "only an offscreen context can be read back");
  if (st->in_frame || !st->frame_w) return Fail(PyExc_RuntimeError, "draw and end one frame first");
  if (st->readbacks >= kMaxReadbacks) return Fail(PyExc_RuntimeError, "this context's one readback was used");
  Py_ssize_t n = static_cast<Py_ssize_t>(st->frame_w) * st->frame_h * 4;
  PyObject* out = PyBytes_FromStringAndSize(nullptr, n);
  if (!out) return nullptr;
  std::memset(PyBytes_AS_STRING(out), 0, static_cast<size_t>(n));  // never stale heap bytes, whatever the driver does
  st->readbacks++;
  for (int i = 0; i < kMaxErrorDrain && glGetError() != GL_NO_ERROR; ++i) {
  }
  glPixelStorei(GL_PACK_ALIGNMENT, 1);
  glReadPixels(0, 0, st->frame_w, st->frame_h, GL_RGBA, GL_UNSIGNED_BYTE, PyBytes_AS_STRING(out));
  if (glGetError() != GL_NO_ERROR) {
    Py_DECREF(out);
    return Fail(PyExc_RuntimeError, "the readback failed");
  }
  return out;
}

PyObject* Ctx_error(Ctx* self, PyObject*) {
  if (!Usable(self)) return nullptr;
  return PyLong_FromUnsignedLong(glGetError());
}

PyObject* Ctx_info(Ctx* self, PyObject*) {
  State* st = self->st;
  if (!st) return Py_BuildValue("{s:O}", "closed", Py_True);
  return Py_BuildValue("{s:s,s:s,s:s,s:O,s:(ii),s:O,s:n,s:n,s:K,s:i,s:O}", "vendor", st->vendor.c_str(), "renderer",
                       st->renderer.c_str(), "version", st->version.c_str(), "offscreen",
                       st->owns_window ? Py_True : Py_False, "size", st->off_w, st->off_h, "window_visible",
                       IsWindowVisible(st->hwnd) ? Py_True : Py_False, "textures",
                       static_cast<Py_ssize_t>(st->textures.size()), "batches",
                       static_cast<Py_ssize_t>(st->batches.size()), "bytes", st->bytes, "readbacks", st->readbacks,
                       "closed", Py_False);
}

PyObject* Ctx_close(Ctx* self, PyObject*) {
  State* st = self->st;
  if (!st) Py_RETURN_NONE;  // closing twice is harmless
  if (GetCurrentThreadId() != st->thread) return Fail(PyExc_RuntimeError, "the OpenGL context belongs to another thread");
  self->st = nullptr;
  delete st;
  Py_RETURN_NONE;
}

// C++ exceptions never cross into CPython: out of memory is MemoryError, anything else RuntimeError
template <PyObject* (*F)(Ctx*, PyObject*)>
PyObject* Guarded(Ctx* self, PyObject* args) {
  try {
    return F(self, args);
  } catch (const std::bad_alloc&) {
    return PyErr_NoMemory();
  } catch (...) {
    return Fail(PyExc_RuntimeError, "internal error in the OpenGL bridge");
  }
}

int GuardedInit(Ctx* self, PyObject* args, PyObject* kw) {
  try {
    return Ctx_init(self, args, kw);
  } catch (const std::bad_alloc&) {
    PyErr_NoMemory();
  } catch (...) {
    PyErr_SetString(PyExc_RuntimeError, "internal error in the OpenGL bridge");
  }
  return -1;
}

PyMethodDef kMethods[] = {
    {"make_current", reinterpret_cast<PyCFunction>(Guarded<Ctx_make_current>), METH_NOARGS, "make this context current"},
    {"texture", reinterpret_cast<PyCFunction>(Guarded<Ctx_texture>), METH_VARARGS, "texture(w, h, rgba_bytes) -> handle"},
    {"batch", reinterpret_cast<PyCFunction>(Guarded<Ctx_batch>), METH_VARARGS,
     "batch(texture_or_0, positions_f32, uvs_f32, colours_u8) -> handle"},
    {"lines", reinterpret_cast<PyCFunction>(Guarded<Ctx_lines>), METH_VARARGS, "lines(positions_f32) -> handle"},
    {"release", reinterpret_cast<PyCFunction>(Guarded<Ctx_release>), METH_VARARGS, "release(handle)"},
    {"begin", reinterpret_cast<PyCFunction>(Guarded<Ctx_begin>), METH_VARARGS, "begin(w, h, clear_rgb, projection16, view16)"},
    {"draw", reinterpret_cast<PyCFunction>(Guarded<Ctx_draw>), METH_VARARGS, "draw(batch, mode 0..3, backdrop)"},
    {"draw_lines", reinterpret_cast<PyCFunction>(Guarded<Ctx_draw_lines>), METH_VARARGS, "draw_lines(lines, rgb, width)"},
    {"overlay_lines", reinterpret_cast<PyCFunction>(Guarded<Ctx_overlay_lines>), METH_VARARGS,
     "overlay_lines(positions_f32, colours_u8, width, stipple_factor, stipple_pattern)"},
    {"overlay_points", reinterpret_cast<PyCFunction>(Guarded<Ctx_overlay_points>), METH_VARARGS,
     "overlay_points(positions_f32, colours_u8, size)"},
    {"end", reinterpret_cast<PyCFunction>(Guarded<Ctx_end>), METH_NOARGS, "end the frame"},
    {"finish", reinterpret_cast<PyCFunction>(Guarded<Ctx_finish>), METH_NOARGS, "wait for the GPU (timing)"},
    {"present", reinterpret_cast<PyCFunction>(Guarded<Ctx_present>), METH_NOARGS, "swap a window context's buffers"},
    {"read_pixels", reinterpret_cast<PyCFunction>(Guarded<Ctx_read_pixels>), METH_NOARGS,
     "the last frame of an offscreen context as RGBA bytes, bottom row first (once per context)"},
    {"error", reinterpret_cast<PyCFunction>(Guarded<Ctx_error>), METH_NOARGS, "the pending GL error code"},
    {"info", reinterpret_cast<PyCFunction>(Guarded<Ctx_info>), METH_NOARGS, "driver strings and resource counts"},
    {"close", reinterpret_cast<PyCFunction>(Guarded<Ctx_close>), METH_NOARGS, "free everything (idempotent)"},
    {nullptr, nullptr, 0, nullptr}};

PyTypeObject kCtxType = {PyVarObject_HEAD_INIT(nullptr, 0)};

PyModuleDef kModule = {PyModuleDef_HEAD_INIT, "_r3hd_scene_gl",
                       "G6-P39 (D-295): the narrow OpenGL bridge of the 3D Level Remix Editor; no general native "
                       "calls, no pointers, every buffer checked and copied.",
                       -1, nullptr};

}  // namespace

PyMODINIT_FUNC PyInit__r3hd_scene_gl(void) {
  kCtxType.tp_name = "_r3hd_scene_gl.Context";
  kCtxType.tp_basicsize = sizeof(Ctx);
  kCtxType.tp_flags = Py_TPFLAGS_DEFAULT;  // not subclassable
  kCtxType.tp_doc = "an OpenGL context on the editor's own window or a hidden offscreen target";
  kCtxType.tp_new = Ctx_new;
  kCtxType.tp_init = reinterpret_cast<initproc>(GuardedInit);
  kCtxType.tp_dealloc = reinterpret_cast<destructor>(Ctx_dealloc);
  kCtxType.tp_methods = kMethods;
  if (PyType_Ready(&kCtxType) < 0) return nullptr;
  PyObject* m = PyModule_Create(&kModule);
  if (!m) return nullptr;
  Py_INCREF(&kCtxType);
  if (PyModule_AddObject(m, "Context", reinterpret_cast<PyObject*>(&kCtxType)) < 0) {
    Py_DECREF(&kCtxType);
    Py_DECREF(m);
    return nullptr;
  }
  PyObject* lim = Py_BuildValue("{s:i,s:i,s:i,s:n,s:n,s:K,s:n,s:d,s:d,s:i,s:n}", "texture_side", kMaxTextureSide,
                                "offscreen_side", kMaxOffscreenSide, "viewport_side", kMaxViewportSide,
                                "batch_vertices", kMaxBatchVertices, "overlay_vertices", kMaxOverlayVertices,
                                "context_bytes", kMaxContextBytes, "handles", static_cast<Py_ssize_t>(kMaxHandles),
                                "coordinate", kMaxCoordinate, "alpha_ref", static_cast<double>(kAlphaRef),
                                "readbacks", kMaxReadbacks, "contexts", static_cast<Py_ssize_t>(kMaxContexts));
  if (!lim || PyModule_AddObject(m, "LIMITS", lim) < 0) {
    Py_XDECREF(lim);
    Py_DECREF(m);
    return nullptr;
  }
  if (PyModule_AddStringConstant(m, "__version__", "1") < 0) {
    Py_DECREF(m);
    return nullptr;
  }
  return m;
}
