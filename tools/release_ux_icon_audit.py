#!/usr/bin/env python3
"""Read-only PE/ICO audit, including native 16 px loading (no Explorer cache).

EXE OUT.json --kind settings|setup|game. No executable code is loaded. The only
writes are the JSON and deterministic reference ICOs beside it, under private/.
Inno's Z_GROUPICON is its internal checkbox strip, not the application icon.
"""
import argparse
import ctypes as c
from ctypes import wintypes as w
import hashlib
import json
from pathlib import Path
import shutil
import struct

import make_r3hd_icon as source

k, u, g = (c.WinDLL(n, use_last_error=True) for n in ('kernel32', 'user32', 'gdi32'))
k.LoadLibraryExW.argtypes = [w.LPCWSTR, w.HANDLE, w.DWORD]
k.LoadLibraryExW.restype = w.HMODULE
k.FreeLibrary.argtypes = [w.HMODULE]
k.FindResourceW.argtypes = [w.HMODULE, c.c_void_p, c.c_void_p]
k.FindResourceW.restype = w.HANDLE
k.SizeofResource.argtypes = [w.HMODULE, w.HANDLE]
k.LoadResource.argtypes = [w.HMODULE, w.HANDLE]
k.LoadResource.restype = w.HANDLE
k.LockResource.argtypes = [w.HANDLE]
k.LockResource.restype = c.c_void_p
u.LoadImageW.argtypes = [w.HINSTANCE, c.c_void_p, w.UINT, c.c_int, c.c_int, w.UINT]
u.LoadImageW.restype = w.HANDLE
u.DestroyIcon.argtypes = [w.HANDLE]


class IconInfo(c.Structure):
    _fields_ = [('icon', w.BOOL), ('x', w.DWORD), ('y', w.DWORD),
                ('mask', w.HBITMAP), ('color', w.HBITMAP)]


class Bitmap(c.Structure):
    _fields_ = [('type', w.LONG), ('width', w.LONG), ('height', w.LONG),
                ('stride', w.LONG), ('planes', w.WORD), ('bits', w.WORD), ('data', c.c_void_p)]


u.GetIconInfo.argtypes = [w.HICON, c.POINTER(IconInfo)]
g.GetObjectW.argtypes = [w.HANDLE, c.c_int, c.c_void_p]
g.DeleteObject.argtypes = [w.HANDLE]
g.CreateCompatibleDC.argtypes = [w.HDC]
g.CreateCompatibleDC.restype = w.HDC
g.DeleteDC.argtypes = [w.HDC]
g.GetDIBits.argtypes = [w.HDC, w.HBITMAP, w.UINT, w.UINT, c.c_void_p, c.c_void_p, w.UINT]


def pixels(icon):
    assert icon, c.get_last_error()
    info, bitmap = IconInfo(), Bitmap()
    assert u.GetIconInfo(icon, c.byref(info))
    try:
        assert g.GetObjectW(info.color, c.sizeof(bitmap), c.byref(bitmap))
        header = c.create_string_buffer(struct.pack('<IiiHHIIiiII', 40, bitmap.width, -bitmap.height,
                                                    1, 32, 0, 0, 0, 0, 0, 0))
        data = c.create_string_buffer(bitmap.width * bitmap.height * 4)
        dc = g.CreateCompatibleDC(None)
        try:
            assert g.GetDIBits(dc, info.color, 0, bitmap.height, data, header, 0) == bitmap.height
        finally:
            g.DeleteDC(dc)
        return bitmap.width, bitmap.height, hashlib.sha256(data.raw).hexdigest()
    finally:
        for handle in (info.color, info.mask):
            if handle:
                g.DeleteObject(handle)


def audit(exe, out, kind, shell_copy=False):
    out.parent.mkdir(parents=True, exist_ok=True)
    expected = {1: 'game', 2: 'settings'} if kind == 'settings' else {
        'MAINICON' if kind == 'setup' else 1: 'game'}
    module = k.LoadLibraryExW(str(exe.resolve()), None, 0x22)  # datafile + image resources only
    assert module, c.get_last_error()
    checks = []
    try:
        for group_id, variant in expected.items():
            blob = source.build(variant)
            ico = out.parent / ('reference_' + variant + '.ico')
            ico.write_bytes(blob)
            frames = {}
            for n in range(struct.unpack_from('<H', blob, 4)[0]):
                entry = struct.unpack_from('<BBBBHHII', blob, 6 + 16 * n)
                frames[entry[0] or 256] = blob[entry[-1]:entry[-1] + entry[-2]]

            def resource(typ, name):
                ptr = c.cast(c.c_wchar_p(name), c.c_void_p) if isinstance(name, str) else c.c_void_p(name)
                handle = k.FindResourceW(module, ptr, c.c_void_p(typ))
                assert handle, (typ, name, c.get_last_error())
                return c.string_at(k.LockResource(k.LoadResource(module, handle)), k.SizeofResource(module, handle))

            group = resource(14, group_id)
            assert struct.unpack_from('<H', group, 4)[0] == len(frames)
            for n in range(len(frames)):
                entry = struct.unpack_from('<BBBBHHIH', group, 6 + 14 * n)
                size = entry[0] or 256
                checks.append({'group': group_id, 'frame': size, 'resource_id': entry[-1],
                               'exact': resource(3, entry[-1]) == frames[size]})
            ptr = c.cast(c.c_wchar_p(group_id), c.c_void_p) if isinstance(group_id, str) else c.c_void_p(group_id)
            # Exercise the shared-load order used by Settings: large first, then small.
            for size in (32, 16, 24, 48, 64, 256):
                native = u.LoadImageW(module, ptr, 1, size, size, 0)
                shared = u.LoadImageW(module, ptr, 1, size, size, 0x8000)
                reference = u.LoadImageW(None, c.cast(c.c_wchar_p(str(ico.resolve())), c.c_void_p),
                                         1, size, size, 0x10)
                try:
                    want = pixels(reference)
                    actual, cached = pixels(native), pixels(shared)
                    checks.append({'group': group_id, 'native_size': size,
                                   'exact': actual == cached == want and want[:2] == (size, size),
                                   'pixel_sha256': actual[2]})
                finally:
                    u.DestroyIcon(native)
                    u.DestroyIcon(reference)
                    # LR_SHARED belongs to Windows.
    finally:
        k.FreeLibrary(module)
    if shell_copy:
        # ExtractIconEx exercises shell resource selection rather than just
        # LoadImage on a datafile module. The copy has a new path, separating
        # path-keyed shell state from embedded resources. Neither file runs.
        shell = c.WinDLL('shell32', use_last_error=True)
        shell.ExtractIconExW.argtypes = [w.LPCWSTR, c.c_int, c.POINTER(w.HICON), c.POINTER(w.HICON), w.UINT]
        copy = out.parent / ('isolated_' + exe.name)
        if copy.exists():
            raise ValueError('shell-copy fixture already exists; use a new output directory')
        shutil.copyfile(exe, copy)
        for index, (_, variant) in enumerate(expected.items()):
            reference = out.parent / ('reference_' + variant + '.ico')
            for path in (exe, copy):
                large, small = w.HICON(), w.HICON()
                assert shell.ExtractIconExW(str(path.resolve()), index, c.byref(large), c.byref(small), 1) == 2
                try:
                    for size, handle in ((16, small), (32, large)):
                        want = u.LoadImageW(None, c.cast(c.c_wchar_p(str(reference)), c.c_void_p), 1, size, size, 0x10)
                        try:
                            actual = pixels(handle)
                            checks.append({'shell_index': index, 'copy': path == copy, 'size': size,
                                           'exact': actual == pixels(want), 'pixel_sha256': actual[2]})
                        finally:
                            u.DestroyIcon(want)
                finally:
                    u.DestroyIcon(small)
                    u.DestroyIcon(large)
    report = {'exe': str(exe), 'sha256': hashlib.file_digest(exe.open('rb'), 'sha256').hexdigest(),
              'checks': checks, 'pass': all(x['exact'] for x in checks)}
    out.write_bytes((json.dumps(report, indent=1) + '\n').encode())
    print('UX_ICON_AUDIT', 'PASS' if report['pass'] else 'FAIL', exe.name, len(checks))
    return report['pass']


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('exe', type=Path)
    ap.add_argument('out', type=Path)
    ap.add_argument('--kind', choices=['settings', 'setup', 'game'], required=True)
    ap.add_argument('--shell-copy', action='store_true', help='also compare shell extraction from a new private copy')
    args = ap.parse_args()
    if not args.out.resolve().is_relative_to((source.ROOT / 'private').resolve()):
        ap.error('OUT must be under private/')
    raise SystemExit(0 if audit(args.exe, args.out, args.kind, args.shell_copy) else 1)
