#!/usr/bin/env python3
"""Inspect real Settings HWND/class icons on its test-only private desktop.

No user windows, global input, display change or game. OUT must be new/private.
"""
import argparse
import ctypes as c
from ctypes import wintypes as w
import json
from pathlib import Path
import subprocess
import time

import m30_launcher_regression as launcher
import m43_regression as observer
import r3hd_installer as engine
import release_ux_icon_audit as icons

ROOT = Path(__file__).resolve().parents[1]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('out', type=Path)
    ap.add_argument('--launcher', type=Path, default=ROOT / 'private/work/launcher/r3hd_launcher.exe')
    a = ap.parse_args()
    out = a.out.resolve()
    if not out.is_relative_to(ROOT / 'private'):
        ap.error('OUT must be private/')
    out.mkdir(parents=True, exist_ok=False)
    payload, tree, releases = engine.make_fixture(out)
    home = out / 'home'
    engine.install(home, payload, source=tree, preset='vanilla', releases=releases, log=lambda _: None)
    script = out / 'script.txt'
    script.write_bytes(b'dump ready\nwait 4000\nclick close\n')
    proc = subprocess.Popen([str(a.launcher.resolve()), '--home', str(home), '--tools', str(ROOT / 'tools'),
        '--python', __import__('sys').executable, '--releases', str(out / 'releases.json'),
        '--ui-test', str(script), '--out', str(out)], env=launcher.launcher_env(),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    u = observer.user32
    u.GetClassLongPtrW.argtypes = [w.HWND, c.c_int]
    u.GetClassLongPtrW.restype = c.c_size_t
    u.SendMessageTimeoutW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM, w.UINT, w.UINT, c.POINTER(c.c_size_t)]
    found = []
    until = time.monotonic() + 40
    while proc.poll() is None and time.monotonic() < until and not found:
        desk = u.OpenDesktopW(f'r3hd_ui_test_{proc.pid}', 0, False, 0x41)
        if desk:
            def cb(hwnd, _):
                name = c.create_unicode_buffer(64)
                u.GetClassNameW(hwnd, name, 64)
                if name.value == 'R3HDRecompSettings':
                    large, small = u.GetClassLongPtrW(hwnd, -14), u.GetClassLongPtrW(hwnd, -34)
                    if large and small:
                        found.append((hwnd, large, small))
                return True
            u.EnumDesktopWindows(desk, observer.EnumProc(cb), 0)
            u.CloseDesktop(desk)
        if not found:
            time.sleep(.05)
    checks = []
    test_desktop = None
    try:
        assert found, 'Settings test HWND not observed'
        # WM_GETICON is read on the same private desktop, never the user's desktop.
        test_desktop = u.OpenDesktopW(f'r3hd_ui_test_{proc.pid}', 0, False, 0x10000000)
        u.SetThreadDesktop.argtypes = [w.HANDLE]
        assert test_desktop and u.SetThreadDesktop(test_desktop), c.get_last_error()
        hwnd, large, small = found[0]
        ico = out / 'reference_settings.ico'
        ico.write_bytes(icons.source.build('settings'))
        for size, handle, message in ((32, large, 1), (16, small, 0), (16, small, 2)):
            reference = icons.u.LoadImageW(None, c.cast(c.c_wchar_p(str(ico)), c.c_void_p), 1, size, size, 0x10)
            value = c.c_size_t()
            assert u.SendMessageTimeoutW(hwnd, 0x7f, message, 0, 2, 1000, c.byref(value))
            try:
                expected = icons.pixels(reference)
                actual = icons.pixels(value.value or handle)
                checks.append({'wm_geticon': message, 'size': size, 'class_and_window_match':
                    actual == icons.pixels(handle) == expected and expected[:2] == (size, size),
                    'pixel_sha256': actual[2]})
            finally:
                icons.u.DestroyIcon(reference)
    finally:
        output = proc.communicate(timeout=60)[0]
        (out / 'process.log').write_bytes(output)
        if test_desktop:
            u.CloseDesktop(test_desktop)
    ok = proc.returncode == 0 and all(row['class_and_window_match'] for row in checks)
    (out / 'result.json').write_bytes((json.dumps({'pass': ok, 'checks': checks}, indent=1) + '\n').encode())
    print('UX_SMALL_WINDOW', 'PASS' if ok else 'FAIL', len(checks))
    return int(not ok)


if __name__ == '__main__':
    raise SystemExit(main())
