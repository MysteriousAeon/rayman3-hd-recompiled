"""Shared read-only live-process helpers for the M5 probes (Windows only).

Layout (VERIFIED locally by reciprocal links and by decoded behaviour names, see RE_NOTES.md):
SuperObject: +0 type(2) +4 Perso +0x20 matrix; matrix: translation floats at +0x34.
Perso: +4 StdGame +8 Dynam +0xC Brain; Brain: +0 Mind; Mind: +0 AIModel +4 normal
Intelligence +8 reflex Intelligence +0xC DsgMem; Intelligence: +8 current Behavior.
Behavior: 0x100-byte name, then script-array pointer, schedule pointer, count byte.
StdGame: +0xC SuperObject, +0x20 custom bits. No WriteProcessMemory anywhere.
"""
import ctypes, struct
from ctypes import wintypes as wt

_k = ctypes.WinDLL('kernel32', use_last_error=True)
_k.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]; _k.OpenProcess.restype = wt.HANDLE
_k.ReadProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
_k.GetExitCodeProcess.argtypes = [wt.HANDLE, ctypes.POINTER(wt.DWORD)]


class Process:
    def __init__(self, pid, base):
        self.base = base
        self.handle = _k.OpenProcess(0x410, False, pid)  # QUERY_INFORMATION | VM_READ
        if not self.handle: raise ctypes.WinError(ctypes.get_last_error())

    def running(self):
        code = wt.DWORD()
        return bool(_k.GetExitCodeProcess(self.handle, ctypes.byref(code))) and code.value == 259

    def read(self, addr, length):
        if not 0x10000 <= addr < 0xFFFF0000: return None
        b = ctypes.create_string_buffer(length); n = ctypes.c_size_t()
        if not _k.ReadProcessMemory(self.handle, self.base + addr, b, length, ctypes.byref(n)) or n.value != length: return None
        return b.raw

    def words(self, addr, count):
        b = self.read(addr, count * 4)
        return struct.unpack(f'>{count}I', b) if b else None

    def cstr(self, addr, limit=0x100):
        b = self.read(addr, limit)
        if not b: return None
        b = b.split(b'\0', 1)[0]
        return b.decode('ascii') if b and all(32 <= c < 127 for c in b) else None


def short(name):
    """'fam\\model\\model.rul^...^CreateComport:X' -> 'X'."""
    return name.rsplit(':', 1)[-1] if name else name


class Actor:
    def __init__(self, process, so):
        self.p = process; self.so = so
        s = process.words(so, 9); self.perso, self.matrix = s[1], s[8]
        p = process.words(self.perso, 4); self.std, self.dynam = p[1], p[2]
        brain = process.words(p[3], 1) if p[3] else None
        self.mind = process.words(brain[0], 4) if brain and brain[0] else None
        self.model = ''
        if self.mind:
            model = process.words(self.mind[0], 1)
            first = process.words(model[0], 2) if model and model[0] else None
            name = process.cstr(first[0]) if first and first[0] else None
            parts = name.split(chr(92)) if name else []
            if len(parts) > 1: self.model = parts[1]

    def alive(self):  # the reciprocal link breaks when the actor is freed or the level changes
        s = self.p.words(self.so, 2); std = self.p.words(self.std, 4)
        return bool(s and std and s[0] == 2 and s[1] == self.perso and std[3] == self.so)

    def position(self):
        m = self.p.read(self.matrix, 0x40)
        return struct.unpack_from('>3f', m, 0x34) if m else None

    def custom_bits(self):
        w = self.p.words(self.std + 0x20, 1)
        return w[0] if w else 0

    def comport(self, reflex=False):
        w = self.p.words(self.mind[2 if reflex else 1], 3) if self.mind and self.mind[2 if reflex else 1] else None
        return short(self.p.cstr(w[2])) if w and w[2] else None

    def dsg(self):
        """Current designer-variable buffer as [(buffer, offset)] indexed by variable number."""
        mem = self.p.words(self.mind[3], 3); var = self.p.words(self.p.words(mem[0], 1)[0], 4)
        infos = [self.p.words(var[1] + i * 16, 2) for i in range(var[3] >> 24)]
        buf = self.p.read(mem[2], var[2])
        return [(buf, off) for off, _ in infos]


def f32(v): return struct.unpack_from('>f', v[0], v[1])[0]
def u8(v): return v[0][v[1]]
def i32(v): return struct.unpack_from('>i', v[0], v[1])[0]
def vec(v): return struct.unpack_from('>3f', v[0], v[1])
