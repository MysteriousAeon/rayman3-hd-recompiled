#!/usr/bin/env python3
"""M48-P (D-087): the playtest setup's real wizard on a private desktop (CreateDesktop; never the person's desktop,
no global input, no focus change). Messages go only to this setup's own windows (PostMessage / SendMessage).

    python tools/m48p_setup_ui_check.py SETUP.exe PACKAGE OUTDIR --scenario switch|turkish|cancel|layout
                                        [--lang en|tr|auto] [--tag NAME] [--home DIR]

  switch   start in English: both language controls (text + flag) are labelled, tab stops, the active one marked;
           Turkish chosen with the keyboard (Space on the text button) restarts the wizard in Turkish; forward to the
           options page (subtitles unticked), back to the language page, English chosen with the mouse (a click on the
           flag): folder, package, preset and options carried; then install in English to the Finish page
  turkish  start without /LANG (Windows UI language) or --lang: every page to Finish in that language; on the progress
           page the page's Cancel opens the translated prompt, No continues; Finish text names the Turkish preview
  cancel   install, Cancel at about 30 % (Yes): the cancelled message, the wizard ends, the folder has no installation
  layout   every page up to Ready (no install) with the layout judge, then the wizard's Cancel and its exit prompt
Every page: a screenshot (PrintWindow) and the layout judge: each visible control inside the window's client area and
its parent, single-line captions not wider than their control, wrapped labels not taller than their control, no two
visible leaf controls overlapping, the window inside the work area. Result: OUTDIR/<tag>.json and <tag>_*.png;
exit 0 when the scenario ran to its end and every rule held.
"""
import argparse
import ctypes
import ctypes.wintypes as wt
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import m32_setup_ui_check as m32  # noqa: E402  (private desktop, window enumeration)

user32, kernel32 = m32.user32, m32.kernel32
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
user32.GetDC.restype = wt.HDC
user32.GetDC.argtypes = [wt.HWND]
user32.ReleaseDC.argtypes = [wt.HWND, wt.HDC]
user32.PrintWindow.argtypes = [wt.HWND, wt.HDC, wt.UINT]
user32.DrawTextW.argtypes = [wt.HDC, wt.LPCWSTR, ctypes.c_int, ctypes.POINTER(wt.RECT), wt.UINT]
user32.GetParent.restype = wt.HWND
user32.GetParent.argtypes = [wt.HWND]
user32.GetWindowLongW.argtypes = [wt.HWND, ctypes.c_int]
gdi32.SelectObject.restype = wt.HGDIOBJ
gdi32.SelectObject.argtypes = [wt.HDC, wt.HGDIOBJ]
gdi32.CreateCompatibleDC.restype = wt.HDC
gdi32.CreateCompatibleDC.argtypes = [wt.HDC]
gdi32.CreateCompatibleBitmap.restype = wt.HBITMAP
gdi32.CreateCompatibleBitmap.argtypes = [wt.HDC, ctypes.c_int, ctypes.c_int]
gdi32.GetTextExtentPoint32W.argtypes = [wt.HDC, wt.LPCWSTR, ctypes.c_int, ctypes.POINTER(wt.SIZE)]
gdi32.GetDIBits.argtypes = [wt.HDC, wt.HBITMAP, wt.UINT, wt.UINT, ctypes.c_void_p, ctypes.c_void_p, wt.UINT]
gdi32.DeleteObject.argtypes = [wt.HGDIOBJ]
gdi32.DeleteDC.argtypes = [wt.HDC]
gdi32.GetObjectW.argtypes = [wt.HGDIOBJ, ctypes.c_int, ctypes.c_void_p]
gdi32.CreateFontIndirectW.restype = wt.HFONT
gdi32.CreateFontIndirectW.argtypes = [ctypes.c_void_p]
gdi32.GetDeviceCaps.argtypes = [wt.HDC, ctypes.c_int]

WM_GETFONT, WM_KEYDOWN, WM_KEYUP, WM_LBUTTONDOWN, WM_LBUTTONUP = 0x0031, 0x0100, 0x0101, 0x0201, 0x0202
BM_CLICK, BM_GETCHECK = 0x00F5, 0x00F0
VK_SPACE = 0x20
WS_TABSTOP, WS_DISABLED = 0x00010000, 0x08000000
GWL_STYLE = -16
DT_CALCRECT, DT_WORDBREAK, DT_NOPREFIX, DT_EXPANDTABS = 0x400, 0x10, 0x800, 0x40
IDNO = 7
LEAF = {"TNewStaticText", "TNewButton", "TNewCheckBox", "TBitmapButton", "TNewEdit", "TEdit", "TNewRadioButton",
        "TNewProgressBar", "TNewCheckListBox", "TRichEditViewer", "TNewMemo", "TButton", "Button", "TBitmapImage",
        "TPasswordEdit"}
CAPTIONS = {"en": {"next": "&Next >", "back": "< &Back", "install": "&Install", "finish": "&Finish", "cancel": "Cancel",
                   "page_cancel": "&Cancel installation", "package": "Package file:", "lang_active": "✓ &English", "preset_title": "Game profile",
                   "lang_other": "&Türkçe", "options": "Turkish translation",
                   "subs": "Subtitles for voiced lines during gameplay",
                   "note_fresh": "The game will be installed in English.",
                   "finish_short": "You can start the game from the desktop or the Start menu."},
            "tr": {"next": "&Sonraki >", "back": "< Ö&nceki", "install": "&Kur", "finish": "&Bitti", "cancel": "İptal",
                   "page_cancel": "Kurulumu &iptal et", "package": "Paket dosyası:", "lang_active": "✓ &Türkçe", "preset_title": "Oyun profili",
                   "lang_other": "&English", "options": "Türkçe çeviri",
                   "subs": "Oynanış sırasında seslendirilen satırlar için altyazı",
                   "note_fresh": "Türkçe çeviri kurulur ve açılır.",
                   "finish_short": "Oyunu masaüstünden ya da Başlat menüsünden başlatabilirsiniz."}}
LANG_PROMPT = "Kurulum dilini seçin  /  Choose the setup language"


class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


def rect(h):
    r = wt.RECT()
    user32.GetWindowRect(h, ctypes.byref(r))
    return (r.left, r.top, r.right, r.bottom)


def client_screen(h):
    r = wt.RECT()
    user32.GetClientRect(h, ctypes.byref(r))
    pt = wt.POINT(0, 0)
    user32.ClientToScreen(h, ctypes.byref(pt))
    return (pt.x, pt.y, pt.x + r.right, pt.y + r.bottom)


def visible_children(wiz):
    return [c for c in m32.children(wiz) if user32.IsWindowVisible(c)]


def texts(wiz):
    return [m32.text_of(c) for c in visible_children(wiz) if m32.text_of(c)]


def norm(t: str) -> str:
    """Inno Setup 6.7's modern style shows "&Next >" as "Next": compare captions without accelerators and arrows."""
    return t.replace("&", "").replace(">", "").replace("<", "").strip()


def find(wiz, caption, cls=None):
    for c in visible_children(wiz):
        if norm(m32.text_of(c)) == norm(caption) and (cls is None or m32.class_of(c) == cls):
            return c
    return None


def find_class(wiz, cls):
    return [c for c in visible_children(wiz) if m32.class_of(c) == cls]


FONT = {"base": 0, "bold": 0, "pt": 9}


def text_size(h, text, width=None, bold=False):
    """The caption's size in the wizard's dialog font (or its bold variant); with width, the wrapped height."""
    dc = user32.GetDC(h)
    font = FONT["bold" if bold else "base"]  # WM_GETFONT of Inno's controls is not their drawing font
    old = gdi32.SelectObject(dc, font) if font else None
    try:
        if width is None:
            sz = wt.SIZE()
            t = text.replace("&", "")
            gdi32.GetTextExtentPoint32W(dc, t, len(t), ctypes.byref(sz))
            return sz.cx, sz.cy
        r = wt.RECT(0, 0, width, 0)
        user32.DrawTextW(dc, text, -1, ctypes.byref(r), DT_CALCRECT | DT_WORDBREAK | DT_EXPANDTABS)
        return r.right, r.bottom
    finally:
        if old:
            gdi32.SelectObject(dc, old)
        user32.ReleaseDC(h, dc)


def work_area():
    r = wt.RECT()
    user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(r), 0)  # SPI_GETWORKAREA
    return (r.left, r.top, r.right, r.bottom)


def inside(inner, outer, slack=1):
    return inner[0] >= outer[0] - slack and inner[1] >= outer[1] - slack and inner[2] <= outer[2] + slack \
        and inner[3] <= outer[3] + slack


LABEL_NOTES = []


class LOGFONTW(ctypes.Structure):
    _fields_ = [("lfHeight", ctypes.c_long), ("lfWidth", ctypes.c_long), ("lfEscapement", ctypes.c_long),
                ("lfOrientation", ctypes.c_long), ("lfWeight", ctypes.c_long), ("lfItalic", ctypes.c_ubyte),
                ("lfUnderline", ctypes.c_ubyte), ("lfStrikeOut", ctypes.c_ubyte), ("lfCharSet", ctypes.c_ubyte),
                ("lfOutPrecision", ctypes.c_ubyte), ("lfClipPrecision", ctypes.c_ubyte), ("lfQuality", ctypes.c_ubyte),
                ("lfPitchAndFamily", ctypes.c_ubyte), ("lfFaceName", ctypes.c_wchar * 32)]


def init_fonts(wiz):
    """The wizard's dialog font (Inno: Segoe UI, DialogFontSize pt; its controls answer no WM_GETFONT) and bold."""
    if FONT["base"]:
        return
    dc = user32.GetDC(wiz)
    dpi = gdi32.GetDeviceCaps(dc, 90)  # LOGPIXELSY
    user32.ReleaseDC(wiz, dc)
    for key, weight in (("base", 400), ("bold", 700)):
        lf = LOGFONTW()
        lf.lfHeight = -round(FONT["pt"] * dpi / 72)
        lf.lfWeight = weight
        lf.lfCharSet = 1  # DEFAULT_CHARSET
        lf.lfQuality = 5  # CLEARTYPE_QUALITY
        lf.lfFaceName = "Segoe UI"
        FONT[key] = gdi32.CreateFontIndirectW(ctypes.byref(lf))


def layout_findings(wiz):
    init_fonts(wiz)
    out = []
    wr, wc = rect(wiz), client_screen(wiz)
    if not inside(wr, work_area(), 0):
        out.append(f"window {wr} outside the work area {work_area()}")
    leaves = []
    for c in visible_children(wiz):
        cls, t, r = m32.class_of(c), m32.text_of(c), rect(c)
        if r[2] - r[0] <= 0 or r[3] - r[1] <= 0:
            continue
        if not inside(r, wc):
            out.append(f"{cls} '{t[:40]}' {r} outside the client area {wc}")
        p = user32.GetParent(c)
        if p and p != wiz and user32.IsWindowVisible(p) and not inside(r, client_screen(p)):
            out.append(f"{cls} '{t[:40]}' {r} clipped by its parent {m32.class_of(p)} {client_screen(p)}")
        if cls in LEAF:
            leaves.append((c, cls, t, r))
        w, h = r[2] - r[0], r[3] - r[1]
        if t and cls in ("TNewButton", "TButton", "Button"):
            tw, _ = text_size(c, t)
            if tw + 8 > w:
                out.append(f"button '{t}' needs {tw + 8} px, has {w}")
        elif t and cls in ("TNewCheckBox", "TNewRadioButton"):
            tw, th = text_size(c, t)
            if tw + 18 > w or th > h + 1:
                out.append(f"check box '{t[:40]}' needs {tw + 18}x{th} px, has {w}x{h}")
        elif t and cls == "TNewStaticText" and t.strip():
            _, th = text_size(c, t, w)
            if th > h + 2:
                out.append(f"label '{t[:40]}' needs {w}x{th} px, has {w}x{h}")
            elif text_size(c, t, w, bold=True)[1] > h + 2:
                LABEL_NOTES.append(f"label '{t[:40]}' would need {text_size(c, t, w, bold=True)[1]} px in bold, has {h}"
                                   " (bold labels: judge on the screenshot)")
    for i in range(len(leaves)):
        for j in range(i + 1, len(leaves)):
            a, b = leaves[i][3], leaves[j][3]
            ix = min(a[2], b[2]) - max(a[0], b[0])
            iy = min(a[3], b[3]) - max(a[1], b[1])
            if ix > 1 and iy > 1:
                out.append(f"overlap: {leaves[i][1]} '{leaves[i][2][:30]}' {a} / {leaves[j][1]} '{leaves[j][2][:30]}' {b}")
    return out


def screenshot(wiz, path: Path):
    try:
        from PIL import Image
    except ImportError:
        return False
    l, t, r, b = rect(wiz)
    w, h = r - l, b - t
    sdc = user32.GetDC(wiz)
    mdc = gdi32.CreateCompatibleDC(sdc)
    bmp = gdi32.CreateCompatibleBitmap(sdc, w, h)
    old = gdi32.SelectObject(mdc, bmp)
    ok = False
    for flag in (2, 0):  # PW_RENDERFULLCONTENT, then WM_PRINT
        if user32.PrintWindow(wiz, mdc, flag):
            buf = ctypes.create_string_buffer(w * h * 4)

            class BIH(ctypes.Structure):
                _fields_ = [("biSize", wt.DWORD), ("biWidth", ctypes.c_long), ("biHeight", ctypes.c_long),
                            ("biPlanes", wt.WORD), ("biBitCount", wt.WORD), ("biCompression", wt.DWORD),
                            ("biSizeImage", wt.DWORD), ("biXPelsPerMeter", ctypes.c_long), ("biYPelsPerMeter", ctypes.c_long),
                            ("biClrUsed", wt.DWORD), ("biClrImportant", wt.DWORD)]
            bi = BIH(ctypes.sizeof(BIH), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
            gdi32.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(bi), 0)
            img = Image.frombuffer("RGBA", (w, h), buf, "raw", "BGRA", 0, 1).convert("RGB")
            if img.getextrema() != ((0, 0), (0, 0), (0, 0)):
                img.save(path)
                ok = True
                break
    gdi32.SelectObject(mdc, old)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mdc)
    user32.ReleaseDC(wiz, sdc)
    return ok


class Run:
    def __init__(self, a):
        self.a, self.row, self.n = a, {"tag": a.tag, "scenario": a.scenario, "pages": [], "steps": [], "errors": []}, 0
        self.desk = m32.Desk(f"r3hd_m48p_{os.getpid()}_{a.tag}")
        self.lang = None

    def err(self, msg):
        self.row["errors"].append(msg)
        print("  ERROR " + msg, flush=True)

    def step(self, msg):
        self.row["steps"].append(msg)

    def wizard(self, timeout=60, exclude=None):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            w = self.desk.wizard()
            if w and w != exclude and user32.IsWindowEnabled(w):
                return w
            time.sleep(0.2)
        return None

    def detect_lang(self, wiz):
        tx = [norm(t) for t in texts(wiz)]
        return "tr" if any(norm(x) in tx for x in (CAPTIONS["tr"]["next"], CAPTIONS["tr"]["install"], CAPTIONS["tr"]["finish"])) \
            else "en" if any(norm(x) in tx for x in (CAPTIONS["en"]["next"], CAPTIONS["en"]["install"], CAPTIONS["en"]["finish"])) else None

    def page_name(self, wiz):
        tx = texts(wiz)
        C = CAPTIONS[self.lang or "en"]
        if LANG_PROMPT in tx:
            return "language"
        if C["package"] in tx:
            return "package"
        if C["options"] in tx:
            return "options"
        if find(wiz, C["page_cancel"]):
            return "progress"
        if find(wiz, C["finish"]):
            return "finished"
        if find(wiz, C["install"]):
            return "ready"
        if find_class(wiz, "TNewCheckListBox"):
            return "preset" if C["preset_title"] in tx else "tasks"
        if any(cls in ("TNewEdit", "TEdit", "TPathEdit", "Edit") or "Edit" in cls
               for cls in (m32.class_of(c) for c in visible_children(wiz))):
            return "selectdir"
        return "other"

    def record_page(self, wiz, note=""):
        name = self.page_name(wiz)
        self.n += 1
        png = self.a.out / f"{self.a.tag}_{self.n:02d}_{self.lang}_{name}.png"
        found = layout_findings(wiz)
        shot = screenshot(wiz, png)
        r = rect(wiz)
        if name == "other":
            note = (note + " classes=" + ",".join(sorted({m32.class_of(c) for c in visible_children(wiz)}))).strip()
        self.row["pages"].append({"n": self.n, "lang": self.lang, "page": name, "note": note, "window": r,
                                  "size": [r[2] - r[0], r[3] - r[1]], "screenshot": png.name if shot else None,
                                  "layout_findings": found})
        print(f"  page {self.n:02d} {self.lang} {name:9s} {r[2] - r[0]}x{r[3] - r[1]} layout={'ok' if not found else found[:2]}",
              flush=True)
        return name

    def click(self, wiz, caption, wait_page_change=True, timeout=60):
        b = find(wiz, caption)
        if not b or not user32.IsWindowEnabled(b):
            self.err(f"no enabled button '{caption}' on {self.page_name(wiz)}")
            return None
        before = self.page_name(wiz)
        user32.PostMessageW(b, BM_CLICK, 0, 0)
        self.step(f"click {caption}")
        if not wait_page_change:
            return wiz
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            time.sleep(0.25)
            if self.desk.dialogs():
                return wiz
            w = self.desk.wizard()
            if w and user32.IsWindowEnabled(w) and self.page_name(w) != before:
                time.sleep(0.3)
                return w
        self.err(f"page did not change after '{caption}' on {before}")
        return None

    def to_page(self, wiz, target, limit=8):
        for _ in range(limit):
            name = self.page_name(wiz)
            if name == target:
                return wiz
            self.record_page(wiz)
            wiz = self.click(wiz, CAPTIONS[self.lang]["next"])
            if not wiz:
                return None
            if self.desk.dialogs():
                d = self.desk.dialogs()[0]
                self.err("message box: " + " ".join(m32.text_of(c) for c in m32.children(d) if m32.text_of(c))[:300])
                return None
        return wiz if self.page_name(wiz) == target else None

    def wait_switch(self, old):
        """The old wizard closes and a new one (the restarted setup) appears."""
        end = time.monotonic() + 60
        while time.monotonic() < end:
            time.sleep(0.3)
            if user32.IsWindow(old) and user32.IsWindowVisible(old):
                continue
            w = self.wizard(timeout=1, exclude=old)
            if w and self.page_name_safe(w) == "language":
                time.sleep(0.5)
                return w
        return None

    def page_name_safe(self, w):
        self.lang = self.detect_lang(w) or self.lang
        return self.page_name(w)


def lang_controls(run, wiz):
    C = CAPTIONS[run.lang]
    act, oth = find(wiz, C["lang_active"], "TNewButton"), find(wiz, C["lang_other"], "TNewButton")
    flags = find_class(wiz, "TBitmapButton")
    names = sorted(m32.text_of(f) for f in flags)
    tab = all(user32.GetWindowLongW(h, GWL_STYLE) & WS_TABSTOP for h in [act, oth, *flags] if h)
    ok = bool(act and oth and len(flags) == 2 and names == ["English (İngilizce)", "Türkçe (Turkish)"] and tab)
    run.row.setdefault("language_controls", []).append({"lang": run.lang, "active": bool(act), "other": bool(oth),
                                                        "flags": names, "tab_stops": tab})
    if not ok:
        run.err(f"language controls: active={bool(act)} other={bool(oth)} flags={names} tab={tab}")
    return act, oth, {m32.text_of(f): f for f in flags}


def edits(wiz):
    return [m32.text_of(c) for c in visible_children(wiz) if "Edit" in m32.class_of(c)]


def click_window(h):
    r = rect(h)
    lp = ((r[3] - r[1]) // 2 << 16) | ((r[2] - r[0]) // 2)
    user32.PostMessageW(h, WM_LBUTTONDOWN, 1, lp)
    user32.PostMessageW(h, WM_LBUTTONUP, 0, lp)


def press_space(h):
    user32.PostMessageW(h, WM_KEYDOWN, VK_SPACE, 0x00390001)
    user32.PostMessageW(h, WM_KEYUP, VK_SPACE, 0xC0390001)


def finish_install(run, wiz, cancel_probe=False, cancel_at=None):
    """Ready -> Install -> progress (optional probes) -> Finished or the cancelled message."""
    C = CAPTIONS[run.lang]
    run.record_page(wiz)
    wiz = run.click(wiz, C["install"], timeout=30)
    if not wiz:
        return None
    probed, shot = False, False
    end = time.monotonic() + 900
    while time.monotonic() < end:
        time.sleep(0.3)
        w = run.desk.wizard()
        if not w:
            if run.desk.dialogs():
                continue
            break
        cancel = find(w, C["page_cancel"])
        bar = next((c for c in visible_children(w) if "Progress" in m32.class_of(c)), None)
        if cancel and bar:
            top = user32.SendMessageW(bar, 0x0407, 0, 0) or 1
            pos = user32.SendMessageW(bar, 0x0408, 0, 0) * 1000 // top
            if not shot and pos >= 50:
                run.record_page(w, f"progress {pos} permille")
                shot = True
            if (cancel_probe or cancel_at is not None) and not probed and pos >= (cancel_at or 150) and user32.IsWindowEnabled(cancel):
                probed = True
                user32.PostMessageW(cancel, BM_CLICK, 0, 0)
                for _ in range(50):
                    time.sleep(0.1)
                    d = run.desk.dialogs()
                    if d:
                        txt = " ".join(m32.text_of(c) for c in m32.children(d[0]) if m32.text_of(c))
                        run.row["cancel_prompt"] = txt[:300]
                        run.row["cancel_prompt_at_permille"] = int(pos)
                        if cancel_at is not None:
                            m32.yes(d[0])
                            run.step("cancel: Yes")
                        else:
                            b = user32.GetDlgItem(d[0], IDNO)
                            if b:
                                user32.PostMessageW(b, BM_CLICK, 0, 0)
                            else:
                                user32.PostMessageW(d[0], m32.TDM_CLICK_BUTTON, IDNO, 0)
                            run.step("cancel: No (continue)")
                        break
            continue
        if find(w, C["finish"]):
            time.sleep(0.5)
            run.record_page(w)
            run.row["finished_text"] = " | ".join(t for t in texts(w) if len(t) > 40)[:1500]
            return w
        d = run.desk.dialogs()
        if d and cancel_at is not None:
            run.row["after_cancel_message"] = " ".join(m32.text_of(c) for c in m32.children(d[0]) if m32.text_of(c))[:400]
            b = user32.GetDlgItem(d[0], 1) or user32.GetDlgItem(d[0], 2)
            if b:
                user32.PostMessageW(b, BM_CLICK, 0, 0)
            else:
                user32.PostMessageW(d[0], m32.TDM_CLICK_BUTTON, 1, 0)
            time.sleep(0.5)
            continue
        if cancel_at is not None and not cancel and run.page_name(w) in ("ready", "other", "preset", "options"):
            run.row["page_after_cancel"] = run.page_name(w)
            return w
    run.err("no Finish page")
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("setup", type=Path)
    ap.add_argument("package", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--scenario", required=True, choices=["switch", "turkish", "cancel", "layout", "finish"])
    ap.add_argument("--toggle", default="", help="finish: Finish-page items to click (0 = Play, 1 = Settings), e.g. 0,1")
    ap.add_argument("--expect-play-refused-running", action="store_true",
                    help="finish: judge checkbox dispatch and the active-game refusal; does not verify launch")
    ap.add_argument("--lang", default="auto", choices=["auto", "en", "tr"])
    ap.add_argument("--tag")
    ap.add_argument("--home")
    ap.add_argument("--font-pt", type=int, default=9, help="the build's DialogFontSize (DPI proxy builds)")
    a = ap.parse_args()
    FONT["pt"] = a.font_pt
    a.tag = a.tag or f"{a.scenario}_{a.lang}"
    a.setup, a.package, a.out = a.setup.resolve(), a.package.resolve(), a.out.resolve()
    a.out.mkdir(parents=True, exist_ok=True)
    home = Path(a.home).resolve() if a.home else a.out / f"{a.tag}_home"
    menu, desktop = a.out / f"{a.tag}_menu", a.out / f"{a.tag}_desktop"
    menu.mkdir(exist_ok=True)
    desktop.mkdir(exist_ok=True)
    args = ["/R3HDTEST=1", "/SP-", f"/DIR={home}", f"/PACKAGE={a.package}", f"/STARTMENUDIR={menu}",
            f"/DESKTOPDIR={desktop}", f"/LOG={a.out / (a.tag + '_setup.log')}"]
    if a.lang != "auto":
        args.append(f"/LANG={a.lang}")
    run = Run(a)
    hproc, _ = run.desk.start(str(a.setup), args)
    t0 = time.monotonic()
    try:
        wiz = run.wizard(90)
        if not wiz:
            run.err("no wizard")
            raise StopIteration
        run.lang = run.detect_lang(wiz)
        run.row["start_language"] = run.lang
        print(f"  start language {run.lang}", flush=True)
        if run.page_name(wiz) != "language":
            run.err(f"first page is {run.page_name(wiz)}, not the language page")
        if a.scenario == "switch":
            run.record_page(wiz)
            act, oth, flags = lang_controls(run, wiz)
            if run.lang != "en":
                run.err("the switch scenario starts in English (--lang en)")
                raise StopIteration
            press_space(oth)  # keyboard: Space on the Türkçe text button
            run.step("Space on Türkçe")
            w2 = run.wait_switch(wiz)
            if not w2:
                run.err("no Turkish wizard after Space on Türkçe")
                raise StopIteration
            run.row["first_switch_old_closed"] = not user32.IsWindow(wiz)
            wiz = w2
            if run.lang != "tr":
                run.err(f"after switching the wizard is {run.lang}")
            run.record_page(wiz, "after keyboard switch")
            lang_controls(run, wiz)
            wiz = run.click(wiz, CAPTIONS["tr"]["next"])
            sd = edits(wiz)
            run.row["selectdir_tr"] = sd
            if str(home) not in sd:
                run.err(f"folder not carried: {sd}")
            wiz = run.to_page(wiz, "options")
            if not wiz:
                raise StopIteration
            # M49: no Turkish box; a fresh Turkish wizard says the translation is installed and turned on
            run.row["turkish_note_tr"] = any(CAPTIONS["tr"]["note_fresh"] in t for t in texts(wiz))
            subs = find(wiz, CAPTIONS["tr"]["subs"])
            user32.SendMessageW(subs, BM_CLICK, 0, 0)  # untick
            run.row["subs_before_switch"] = user32.SendMessageW(subs, BM_GETCHECK, 0, 0)
            run.record_page(wiz, "subtitles unticked")
            for _ in range(6):
                if run.page_name(wiz) == "language":
                    break
                wiz = run.click(wiz, CAPTIONS["tr"]["back"])
                if not wiz:
                    raise StopIteration
            act, oth, flags = lang_controls(run, wiz)
            click_window(flags.get("English (İngilizce)"))  # mouse: the English flag
            run.step("click on the English flag")
            w2 = run.wait_switch(wiz)
            if not w2:
                run.err("no English wizard after the flag click")
                raise StopIteration
            wiz = w2
            run.record_page(wiz, "after mouse switch")
            if run.lang != "en":
                run.err(f"after the second switch the wizard is {run.lang}")
            wiz = run.click(wiz, CAPTIONS["en"]["next"])
            run.row["selectdir_en"] = edits(wiz)
            if str(home) not in run.row["selectdir_en"]:
                run.err(f"folder not carried to English: {run.row['selectdir_en']}")
            wiz = run.to_page(wiz, "package")
            pk = edits(wiz)
            run.row["package_en"] = pk
            if str(a.package) not in pk:
                run.err(f"package not carried: {pk}")
            wiz = run.to_page(wiz, "options")
            if not wiz:
                raise StopIteration
            subs = find(wiz, CAPTIONS["en"]["subs"])
            run.row["subs_after_switch"] = user32.SendMessageW(subs, BM_GETCHECK, 0, 0) if subs else None
            # M49: the English wizard says the game is installed in English (the Turkish .zip goes to extras)
            run.row["turkish_note_en"] = any(CAPTIONS["en"]["note_fresh"] in t for t in texts(wiz))
            run.row["turkish_box_present"] = bool(find_class(wiz, "TNewCheckBox")) and bool(
                find(wiz, "Install the Turkish translation preview and turn it on"))
            if run.row["subs_after_switch"] != 0 or not run.row["turkish_note_en"] or not run.row.get("turkish_note_tr"):
                run.err(f"options: subs={run.row['subs_after_switch']} notes tr={run.row.get('turkish_note_tr')} "
                        f"en={run.row['turkish_note_en']}")
            wiz = run.to_page(wiz, "ready")
            if wiz and finish_install(run, wiz):
                run.click(run.desk.wizard(), CAPTIONS["en"]["finish"], wait_page_change=False)
        elif a.scenario == "finish":
            # M49: the Finish page's two boxes (Play checked, Settings unchecked by default); clicks on the items'
            # check boxes, then Finish; the test-mode entries run the launcher without a window into the setup log.
            wiz = run.to_page(wiz, "ready", limit=10)
            if not wiz:
                raise StopIteration
            w = finish_install(run, wiz)
            if w:
                lists = find_class(w, "TNewCheckListBox")
                run.row["finish_items"] = [m32.text_of(h) for h in lists]
                if len(lists) != 1:
                    run.err(f"finish: {len(lists)} check lists on the Finish page")
                else:
                    lb = lists[0]
                    run.row["finish_item_count"] = user32.SendMessageW(lb, 0x018B, 0, 0)  # LB_GETCOUNT
                    for i in [int(x) for x in a.toggle.split(",") if x != ""]:
                        r = wt.RECT()
                        user32.SendMessageW(lb, 0x0198, i, ctypes.cast(ctypes.pointer(r), ctypes.c_void_p).value)  # LB_GETITEMRECT
                        lp = (((r.top + r.bottom) // 2) << 16) | (r.left + 10)
                        user32.PostMessageW(lb, WM_LBUTTONDOWN, 1, lp)
                        user32.PostMessageW(lb, WM_LBUTTONUP, 0, lp)
                        time.sleep(0.4)
                    run.record_page(w, f"toggled {a.toggle or 'nothing'}")
                run.click(w, CAPTIONS[run.lang]["finish"], wait_page_change=False)
        elif a.scenario in ("turkish", "layout", "cancel"):
            wiz = run.to_page(wiz, "ready", limit=10)
            if not wiz:
                raise StopIteration
            if a.scenario == "layout":
                run.record_page(wiz)
                user32.PostMessageW(find(wiz, CAPTIONS[run.lang]["cancel"]), BM_CLICK, 0, 0)
                for _ in range(50):
                    time.sleep(0.1)
                    d = run.desk.dialogs()
                    if d:
                        run.row["exit_prompt"] = " ".join(m32.text_of(c) for c in m32.children(d[0]) if m32.text_of(c))[:300]
                        m32.yes(d[0])
                        break
            elif a.scenario == "turkish":
                w = finish_install(run, wiz, cancel_probe=True)
                if w:
                    run.click(w, CAPTIONS[run.lang]["finish"], wait_page_change=False)
            else:
                finish_install(run, wiz, cancel_at=300)
                w = run.desk.wizard()
                if w:
                    user32.PostMessageW(find(w, CAPTIONS[run.lang]["cancel"]), BM_CLICK, 0, 0)
                    for _ in range(50):
                        time.sleep(0.1)
                        d = run.desk.dialogs()
                        if d:
                            m32.yes(d[0])
                            break
    except StopIteration:
        pass
    finally:
        end = time.monotonic() + 60
        while time.monotonic() < end and run.desk.wizard():
            time.sleep(0.5)
        run.row["wizard_closed"] = run.desk.wizard() is None
        if not run.row["wizard_closed"]:
            kernel32.TerminateJobObject(run.desk.job, 99)
            run.row["terminated_by_test"] = True
        m32.wait_exit(hproc, 10)
        kernel32.CloseHandle(hproc)
        kernel32.CloseHandle(run.desk.job)
        user32.CloseDesktop(run.desk.h)
    run.row["seconds"] = round(time.monotonic() - t0, 1)
    run.row["installed"] = (home / "installer.json").is_file()
    st = home / "mods" / "state.json"
    run.row["mods_state"] = json.loads(st.read_text(encoding="utf-8")) if st.is_file() else None
    sj = home / "settings.json"
    run.row["settings"] = json.loads(sj.read_text(encoding="utf-8")) if sj.is_file() else None
    layout = [f for p in run.row["pages"] for f in p["layout_findings"]]
    run.row["layout_findings_total"] = len(layout)
    run.row["bold_label_notes"] = sorted(set(LABEL_NOTES))
    if a.scenario == "switch":
        if not run.row["installed"] or (run.row["settings"] or {}).get("overrides", {}).get("gameplay_subtitles") == "all":
            run.err("switch: expected an installation with gameplay subtitles off (unticked before the switch)")
        # M49: the installation finished in English: no Turkish mod, its .zip in extras
        if (run.row["mods_state"] or {}).get("mods") or not list((home / "extras").glob("*.zip")):
            run.err(f"switch: English install expected without Turkish, .zip in extras: {run.row['mods_state']}")
    if a.scenario == "turkish":
        if not run.row["installed"] or "cancel_prompt" not in run.row:
            run.err("turkish: expected an installation and a cancel prompt")
        if CAPTIONS[run.lang or "en"]["finish_short"] not in run.row.get("finished_text", ""):
            run.err("turkish: the Finish page does not name the enabled Turkish preview")
    if a.scenario == "finish":
        log_path = a.out / (a.tag + "_setup.log")
        log_text = log_path.read_text(encoding="utf-8", errors="replace") if log_path.is_file() else ""
        refused_running = ("R3HD_LAUNCHER PLAY FAILED" in log_text and "Another r3hd.exe is already running" in log_text)
        ran_play = "R3HD_LAUNCHER PLAY ENDED" in log_text or (a.expect_play_refused_running and refused_running)
        ran_settings = "R3HD_LAUNCHER MODEL_OK" in log_text
        toggled = {int(x) for x in a.toggle.split(",") if x != ""}
        want_play, want_settings = 0 not in toggled, 1 in toggled
        run.row.update(ran_play=ran_play, ran_settings=ran_settings, want_play=want_play, want_settings=want_settings,
                       play_refused_running=refused_running, expect_play_refused_running=a.expect_play_refused_running,
                       play_binary_ok=str(home / "bin" / "r3hd.exe").lower() in log_text.lower(),
                       play_profile_ok=str(home / "profiles" / "default" / "user").lower() in log_text.lower())
        if not run.row["installed"] or (ran_play, ran_settings) != (want_play, want_settings):
            run.err(f"finish: ran play={ran_play} settings={ran_settings}, wanted {want_play} / {want_settings}")
        if ran_play and not (a.expect_play_refused_running and refused_running) and not (run.row["play_binary_ok"] and run.row["play_profile_ok"]):
            run.err("finish: the Play dry run did not name the installed r3hd.exe and the default profile")
        if CAPTIONS[run.lang]["finish_short"] not in run.row.get("finished_text", ""):
            run.err("finish: the short Finish text is missing")
    if a.scenario == "cancel" and (run.row["installed"] or "cancel_prompt" not in run.row):
        run.err("cancel: expected no installation after Yes")
    ok = not run.row["errors"] and not layout and run.row["wizard_closed"]
    (a.out / f"{a.tag}.json").write_text(json.dumps(run.row, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"M48P_SETUP_UI {'PASS' if ok else 'FAIL'} {a.tag} pages={len(run.row['pages'])} layout_findings={len(layout)} "
          f"errors={len(run.row['errors'])} seconds={run.row['seconds']}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
