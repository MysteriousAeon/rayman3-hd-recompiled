#!/usr/bin/env python3
"""M32 (D-069): is the setup wizard responsive while the engine works? The real wizard, on a private desktop.

    python tools/m32_setup_ui_check.py SETUP.exe PACKAGE OUTDIR [--cancel-at PERMILLE] [--tasks TASKS] [--tag NAME]

Starts SETUP.exe (test mode /R3HDTEST=1, folders under OUTDIR) on a desktop of its own (CreateDesktop; never the
person's desktop, nothing can take their focus), clicks through the wizard with BM_CLICK, and while the engine runs
samples every 100 ms:
  - the wizard's enabled state (a disabled top-level window gets no mouse input: it can be neither dragged nor clicked;
    Inno Setup's Exec disables it, M32 enables it again), its message-loop latency (SendMessageTimeout WM_NULL),
    its caption hit test (HTCAPTION: a press there starts a move), and the page Cancel button's enabled state;
  - the progress bar (PBM_GETPOS, permille).
With --cancel-at, it presses the page's Cancel at that permille (PostMessage BM_CLICK, then Yes in the confirmation by
its control ID) and records what the engine and the wizard did; then the wizard's own Cancel ends setup.
A posted BM_CLICK reaches a button even inside a disabled window, so it proves the button's handler and the engine's
cancellation, never that a person's mouse could click: that is the enabled / hit-test sampling (and a person's check).
Result: OUTDIR/<tag>.json; exit 0 when setup ran to its end (or its cancellation) and every rule held.
"""
import argparse
import ctypes
import ctypes.wintypes as wt
import json
import os
import subprocess
import sys
import time
from pathlib import Path

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

GENERIC_ALL = 0x10000000
WM_NULL, WM_GETTEXT, WM_GETTEXTLENGTH, WM_NCHITTEST = 0x0000, 0x000D, 0x000E, 0x0084
BM_CLICK, PBM_GETPOS, PBM_GETRANGE = 0x00F5, 0x0408, 0x0407
SMTO_ABORTIFHUNG = 0x0002
HTCAPTION = 2
IDYES = 6

WNDENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)


class STARTUPINFOW(ctypes.Structure):
    _fields_ = [("cb", wt.DWORD), ("lpReserved", wt.LPWSTR), ("lpDesktop", wt.LPWSTR), ("lpTitle", wt.LPWSTR),
                ("dwX", wt.DWORD), ("dwY", wt.DWORD), ("dwXSize", wt.DWORD), ("dwYSize", wt.DWORD),
                ("dwXCountChars", wt.DWORD), ("dwYCountChars", wt.DWORD), ("dwFillAttribute", wt.DWORD),
                ("dwFlags", wt.DWORD), ("wShowWindow", wt.WORD), ("cbReserved2", wt.WORD), ("lpReserved2", ctypes.c_void_p),
                ("hStdInput", wt.HANDLE), ("hStdOutput", wt.HANDLE), ("hStdError", wt.HANDLE)]


class PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [("hProcess", wt.HANDLE), ("hThread", wt.HANDLE), ("dwProcessId", wt.DWORD), ("dwThreadId", wt.DWORD)]


user32.CreateDesktopW.restype = wt.HANDLE
user32.CreateDesktopW.argtypes = [wt.LPCWSTR, wt.LPCWSTR, ctypes.c_void_p, wt.DWORD, wt.DWORD, ctypes.c_void_p]
user32.EnumDesktopWindows.argtypes = [wt.HANDLE, WNDENUMPROC, wt.LPARAM]
user32.EnumChildWindows.argtypes = [wt.HWND, WNDENUMPROC, wt.LPARAM]
user32.SendMessageTimeoutW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM, wt.UINT, wt.UINT, ctypes.POINTER(ctypes.c_size_t)]
user32.SendMessageTimeoutW.restype = ctypes.c_size_t
user32.SendMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.SendMessageW.restype = ctypes.c_ssize_t
user32.PostMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.GetDlgItem.argtypes = [wt.HWND, ctypes.c_int]
user32.GetDlgItem.restype = wt.HWND
user32.CloseDesktop.argtypes = [wt.HANDLE]
for _f, _a in (("IsWindowVisible", [wt.HWND]), ("IsWindowEnabled", [wt.HWND]), ("GetClassNameW", [wt.HWND, wt.LPWSTR, ctypes.c_int]),
               ("GetWindowRect", [wt.HWND, ctypes.POINTER(wt.RECT)])):
    getattr(user32, _f).argtypes = _a
kernel32.WaitForSingleObject.argtypes = [wt.HANDLE, wt.DWORD]
kernel32.GetExitCodeProcess.argtypes = [wt.HANDLE, ctypes.POINTER(wt.DWORD)]
kernel32.CloseHandle.argtypes = [wt.HANDLE]
kernel32.TerminateProcess.argtypes = [wt.HANDLE, wt.UINT]
TDM_CLICK_BUTTON = 0x0400 + 102
class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", wt.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wt.DWORD),
                ("Affinity", ctypes.c_size_t), ("PriorityClass", wt.DWORD), ("SchedulingClass", wt.DWORD)]


class IO_COUNTERS(ctypes.Structure):
    _fields_ = [(n, ctypes.c_uint64) for n in ("r", "w", "o", "rb", "wb", "ob")]


class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION), ("IoInfo", IO_COUNTERS),
                ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]


kernel32.CreateJobObjectW.restype = wt.HANDLE
kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wt.LPCWSTR]
kernel32.SetInformationJobObject.argtypes = [wt.HANDLE, ctypes.c_int, ctypes.c_void_p, wt.DWORD]
kernel32.AssignProcessToJobObject.argtypes = [wt.HANDLE, wt.HANDLE]
kernel32.TerminateJobObject.argtypes = [wt.HANDLE, wt.UINT]
kernel32.ResumeThread.argtypes = [wt.HANDLE]
kernel32.CreateProcessW.argtypes = [wt.LPCWSTR, wt.LPWSTR, ctypes.c_void_p, ctypes.c_void_p, wt.BOOL, wt.DWORD,
                                    ctypes.c_void_p, wt.LPCWSTR, ctypes.POINTER(STARTUPINFOW), ctypes.POINTER(PROCESS_INFORMATION)]


def text_of(h) -> str:
    buf = ctypes.create_unicode_buffer(512)
    r = ctypes.c_size_t()
    if not user32.SendMessageTimeoutW(h, WM_GETTEXT, 512, ctypes.addressof(buf), SMTO_ABORTIFHUNG, 1000, ctypes.byref(r)):
        return ""
    return buf.value


def class_of(h) -> str:
    buf = ctypes.create_unicode_buffer(128)
    user32.GetClassNameW(h, buf, 128)
    return buf.value


def top_windows(desk):
    out = []
    cb = WNDENUMPROC(lambda h, _: out.append(h) or True)
    user32.EnumDesktopWindows(desk, cb, 0)
    return out


def children(h):
    out = []
    cb = WNDENUMPROC(lambda c, _: out.append(c) or True)
    user32.EnumChildWindows(h, cb, 0)
    return out


def latency_ms(h) -> float:
    r = ctypes.c_size_t()
    t = time.perf_counter()
    ok = user32.SendMessageTimeoutW(h, WM_NULL, 0, 0, SMTO_ABORTIFHUNG, 3000, ctypes.byref(r))
    return round((time.perf_counter() - t) * 1000, 1) if ok else 9999.0


class Desk:
    def __init__(self, name):
        self.name = name
        self.h = user32.CreateDesktopW(name, None, None, 0, GENERIC_ALL, None)
        if not self.h:
            raise OSError(f"CreateDesktop failed: {ctypes.get_last_error()}")

    def start(self, exe, args):
        si = STARTUPINFOW()
        si.cb = ctypes.sizeof(si)
        si.lpDesktop = self.name
        pi = PROCESS_INFORMATION()
        cmd = ctypes.create_unicode_buffer(subprocess.list2cmdline([exe] + args))
        # A job that ends with this test: setup's loader starts the real wizard as a child (.tmp), and a stopped test
        # must end both, and nothing else.
        self.job = kernel32.CreateJobObjectW(None, None)
        info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        kernel32.SetInformationJobObject(self.job, 9, ctypes.byref(info), ctypes.sizeof(info))
        if not kernel32.CreateProcessW(exe, cmd, None, None, False, 0x4, None, None, ctypes.byref(si), ctypes.byref(pi)):
            raise OSError(f"CreateProcess failed: {ctypes.get_last_error()}")
        kernel32.AssignProcessToJobObject(self.job, pi.hProcess)
        kernel32.ResumeThread(pi.hThread)
        kernel32.CloseHandle(pi.hThread)
        return pi.hProcess, pi.dwProcessId

    def wizard(self):
        for h in top_windows(self.h):
            if user32.IsWindowVisible(h) and class_of(h) == "TWizardForm":
                return h
        return None

    def dialogs(self):
        return [h for h in top_windows(self.h) if user32.IsWindowVisible(h) and class_of(h) == "#32770"]


def button(wiz, caption):
    for c in children(wiz):
        if user32.IsWindowVisible(c) and text_of(c) == caption:
            return c
    return None


def yes(dialog):
    """Yes in a message box (a button with ID IDYES) or a task dialog (TDM_CLICK_BUTTON)."""
    b = user32.GetDlgItem(dialog, IDYES)
    if b:
        user32.PostMessageW(b, BM_CLICK, 0, 0)
    else:
        user32.PostMessageW(dialog, TDM_CLICK_BUTTON, IDYES, 0)


def wait_exit(hproc, seconds):
    return kernel32.WaitForSingleObject(hproc, int(seconds * 1000)) == 0


def exit_code(hproc):
    code = wt.DWORD()
    kernel32.GetExitCodeProcess(hproc, ctypes.byref(code))
    return code.value


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("setup", type=Path)
    ap.add_argument("package", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--cancel-at", type=int, default=-1)
    ap.add_argument("--tasks", default="")
    ap.add_argument("--tag", default="ui")
    ap.add_argument("--home")
    a = ap.parse_args()
    a.setup, a.package, a.out = a.setup.resolve(), a.package.resolve(), a.out.resolve()  # setup runs elsewhere
    a.out.mkdir(parents=True, exist_ok=True)
    home = Path(a.home) if a.home else a.out / f"{a.tag}_home"
    menu, desktop = a.out / f"{a.tag}_menu", a.out / f"{a.tag}_desktop"
    menu.mkdir(exist_ok=True)
    desktop.mkdir(exist_ok=True)
    args = ["/R3HDTEST=1", "/SP-", f"/DIR={home}", f"/PACKAGE={a.package}", f"/STARTMENUDIR={menu}",
            f"/DESKTOPDIR={desktop}", f"/LOG={a.out / (a.tag + '_setup.log')}"]
    if a.tasks:
        args.append(f"/MERGETASKS={a.tasks}")
    desk = Desk(f"r3hd_setup_ui_{os.getpid()}")
    row = {"tag": a.tag, "setup": a.setup.name, "home": str(home), "cancel_at": a.cancel_at, "clicks": [], "samples": []}
    hproc, pid = desk.start(str(a.setup), args)
    t0 = time.monotonic()
    try:
        # Click through the pages until the engine's progress page shows (its own Cancel button).
        last, deadline = None, time.monotonic() + 120
        while time.monotonic() < deadline:
            if wait_exit(hproc, 0):
                row["error"] = "setup ended before the progress page"
                break
            wiz = desk.wizard()
            if not wiz:
                time.sleep(0.3)
                continue
            if button(wiz, "&Cancel installation"):
                break
            if not user32.IsWindowEnabled(wiz):  # a short engine check (Exec) runs
                time.sleep(0.2)
                continue
            # The package page of a setup without the /PACKAGE prefill (M31): fill its visible edit box.
            kids = [c for c in children(wiz) if user32.IsWindowVisible(c)]
            if any(text_of(c) == "Package file:" for c in kids):
                for c in kids:
                    if "Edit" in class_of(c) and not text_of(c):
                        path = ctypes.create_unicode_buffer(str(a.package))  # kept alive across the call
                        user32.SendMessageW(c, 0x000C, 0, ctypes.addressof(path))  # WM_SETTEXT
                        row["clicks"].append("package typed")
            b = button(wiz, "&Install") or button(wiz, "&Next") or button(wiz, "&Next >")
            if b and user32.IsWindowEnabled(b) and (b, text_of(b)) != last:
                row["clicks"].append(text_of(b))
                user32.PostMessageW(b, BM_CLICK, 0, 0)
                last = (b, text_of(b))
                time.sleep(1.0)
                last = None
            else:
                time.sleep(0.3)
        wiz = desk.wizard()
        cancel = button(wiz, "&Cancel installation") if wiz else None
        bar = next((c for c in children(wiz) if "Progress" in class_of(c) and user32.IsWindowVisible(c)), None) if wiz else None
        row["progress_page"] = bool(cancel and bar)
        cancelled_at = None
        engine_t0 = time.monotonic()
        rect = wt.RECT()
        while row["progress_page"] and not wait_exit(hproc, 0):
            wiz = desk.wizard()
            if not wiz or not user32.IsWindowVisible(cancel):
                break
            top = user32.SendMessageW(bar, PBM_GETRANGE, 0, 0) or 1  # the bar's own range (0..65535 here)
            pos = user32.SendMessageW(bar, PBM_GETPOS, 0, 0) * 1000 // top
            user32.GetWindowRect(wiz, ctypes.byref(rect))
            hit = user32.SendMessageW(wiz, WM_NCHITTEST, 0, ((rect.top + 12) << 16) | ((rect.left + 120) & 0xFFFF))
            row["samples"].append({"t": round(time.monotonic() - engine_t0, 2), "permille": int(pos),
                                   "enabled": bool(user32.IsWindowEnabled(wiz)), "cancel_enabled": bool(user32.IsWindowEnabled(cancel)),
                                   "latency_ms": latency_ms(wiz), "caption_hit": int(hit)})
            # The window's close (title-bar X / Alt+F4) while the engine works: Inno must ignore it on this page
            # (its Cancel is disabled there), so the engine keeps running and no dialog appears.
            if "close_probe" not in row and pos >= 100:
                user32.PostMessageW(wiz, 0x0112, 0xF060, 0)  # WM_SYSCOMMAND SC_CLOSE
                user32.PostMessageW(wiz, 0x0010, 0, 0)       # WM_CLOSE
                time.sleep(1.5)
                row["close_probe"] = {"at_permille": int(pos), "setup_still_running": not wait_exit(hproc, 0),
                                      "dialogs": len(desk.dialogs()),
                                      "permille_after": int(user32.SendMessageW(bar, PBM_GETPOS, 0, 0) * 1000 // top)}
                for dl in desk.dialogs():  # should be none; never confirm an exit
                    user32.PostMessageW(user32.GetDlgItem(dl, 7) or dl, BM_CLICK if user32.GetDlgItem(dl, 7) else TDM_CLICK_BUTTON, 0 if user32.GetDlgItem(dl, 7) else 7, 0)
            if a.cancel_at >= 0 and cancelled_at is None and pos >= a.cancel_at:
                cancelled_at = int(pos)
                user32.PostMessageW(cancel, BM_CLICK, 0, 0)
                for _ in range(50):
                    time.sleep(0.1)
                    dl = desk.dialogs()
                    if dl:
                        row["confirm_text"] = " ".join(text_of(c) for c in children(dl[0]) if text_of(c))[:200]
                        yes(dl[0])
                        row["cancel_confirmed_after_s"] = round(time.monotonic() - engine_t0, 2)
                        break
            time.sleep(0.1)
        row["engine_seconds"] = round(time.monotonic() - engine_t0, 1)
        row["cancelled_at_permille"] = cancelled_at
        # After the engine: the cancellation message (wizard Cancel, Yes) or Finish.
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline and not wait_exit(hproc, 0.3):
            wiz = desk.wizard()
            if not wiz:
                continue
            if row.get("end_page") is None:
                row["end_page"] = " | ".join(t for t in (text_of(c) for c in children(wiz) if user32.IsWindowVisible(c)) if t)[:600]
            fin = button(wiz, "&Finish")
            if fin and user32.IsWindowEnabled(fin):
                user32.PostMessageW(fin, BM_CLICK, 0, 0)
                row["clicks"].append("&Finish")
                continue
            canc = button(wiz, "Cancel")
            if canc and user32.IsWindowEnabled(canc) and "Cancel" not in row["clicks"][-1:]:
                user32.PostMessageW(canc, BM_CLICK, 0, 0)
                row["clicks"].append("Cancel")
                for _ in range(30):
                    time.sleep(0.1)
                    dl = desk.dialogs()
                    if dl:
                        yes(dl[0])
                        break
        row["setup_exited"] = wait_exit(hproc, 5)
        row["setup_exit_code"] = exit_code(hproc) if row["setup_exited"] else None
    finally:
        if not wait_exit(hproc, 0):
            kernel32.TerminateJobObject(desk.job, 99)  # only the setup this test started (its job: loader + wizard)
            row["terminated_by_test"] = True
            wait_exit(hproc, 10)
        kernel32.CloseHandle(hproc)
        kernel32.CloseHandle(desk.job)
        user32.CloseDesktop(desk.h)
    s = row["samples"]
    row["sample_count"] = len(s)
    row["enabled_share"] = round(sum(x["enabled"] for x in s) / len(s), 3) if s else None
    row["cancel_clickable_share"] = round(sum(x["enabled"] and x["cancel_enabled"] for x in s) / len(s), 3) if s else None
    row["latency_ms_max"] = max((x["latency_ms"] for x in s), default=None)
    row["latency_ms_median"] = sorted(x["latency_ms"] for x in s)[len(s) // 2] if s else None
    row["caption_hits"] = sorted({x["caption_hit"] for x in s})
    row["permille_max"] = max((x["permille"] for x in s), default=None)
    row["permille_monotonic"] = all(s[i]["permille"] <= s[i + 1]["permille"] for i in range(len(s) - 1))
    row["seconds_total"] = round(time.monotonic() - t0, 1)
    log = a.out / f"{a.tag}_setup.log"
    text = log.read_text(encoding="utf-8", errors="replace") if log.is_file() else ""
    row["log_wizard_enabled"] = "wizard enabled during the engine run" in text
    row["log_cancel_requested"] = "cancel requested:" in text
    (a.out / f"{a.tag}.json").write_text(json.dumps(row, indent=1) + "\n", encoding="utf-8")
    summary = {k: v for k, v in row.items() if k not in ("samples", "end_page")}
    print("M32_SETUP_UI " + json.dumps(summary))
    return 0 if row.get("setup_exited") and not row.get("terminated_by_test") and not row.get("error") else 1


if __name__ == "__main__":
    sys.exit(main())
