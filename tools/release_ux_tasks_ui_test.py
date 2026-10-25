#!/usr/bin/env python3
"""Observe the actual Additional Tasks page on a private desktop; never install.

Use a fixture made by release_presentation_shortcuts.py. No registry writes,
global input, visible windows or game. The fixture's fabricated data is tiny.
"""
import argparse
import ctypes
import json
from pathlib import Path
import shutil
import time
from types import SimpleNamespace

import m48p_setup_ui_check as ui


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('fixture', type=Path)
    ap.add_argument('out', type=Path)
    ap.add_argument('--setup', type=Path)
    a = ap.parse_args()
    root = Path(__file__).resolve().parents[1] / 'private'
    fixture, out = a.fixture.resolve(), a.out.resolve()
    if not fixture.is_relative_to(root) or not out.is_relative_to(root):
        ap.error('fixture and OUT must be private/')
    out.mkdir(parents=True, exist_ok=False)
    setup = a.setup.resolve() if a.setup else next((fixture / 'current').glob('*-setup.exe'))
    rows = []
    for tag, want in [('fresh', (True, True)), ('home_00', (False, False)),
                      ('home_01', (False, True)), ('home_10', (True, False)), ('home_11', (True, True)),
                      ('deleted', (False, True)), ('deleted_both', (False, False)), ('reused', (True, True))]:
        home = fixture / tag if tag.startswith('home_') else out / (tag + '_home')
        desktop, menu = fixture / (tag + '_desktop'), out / (tag + '_menu')
        if not tag.startswith('home_'):
            desktop = out / (tag + '_desktop')
        if tag.startswith('deleted'):
            shutil.copytree(fixture / 'home_11', home)
            shutil.copytree(fixture / 'home_11_desktop', desktop)
            (desktop / 'Rayman 3 HD Recompiled.lnk').unlink()
            if tag == 'deleted_both':
                # The person's 2026-10-19 setup log: recorded 1/1, both links gone -> both offered unchecked.
                (desktop / 'Rayman 3 HD Recompiled - Settings.lnk').unlink()
        elif tag == 'reused':
            home.mkdir()
            shutil.copyfile(fixture / 'home_01/settings.json', home / 'settings.json')
        desktop.mkdir(exist_ok=True)
        menu.mkdir(exist_ok=True)
        run = ui.Run(SimpleNamespace(out=out, tag=tag, scenario='tasks'))
        log = out / (tag + '.log')
        hproc, _ = run.desk.start(str(setup), ['/R3HDTEST=1','/SP-','/LANG=en',f'/DIR={home}',
            f'/PACKAGE={fixture / "src_tree"}',f'/DESKTOPDIR={desktop}',f'/STARTMENUDIR={menu}',f'/LOG={log}'])
        try:
            wiz = run.wizard(90)
            assert wiz, 'no wizard'
            run.lang = run.detect_lang(wiz)
            wiz = run.to_page(wiz, 'tasks', limit=10)
            assert wiz, run.row
            run.record_page(wiz)
            wiz = run.to_page(wiz, 'ready')
            assert wiz, run.row
            texts = []
            for child in ui.visible_children(wiz):
                buffer = ctypes.create_unicode_buffer(32768)
                ui.user32.SendMessageW(child, 0x000D, len(buffer), ctypes.cast(buffer, ctypes.c_void_p).value)
                texts.append(buffer.value)
            text = '\n'.join(texts)
            actual = tuple(label in text.replace('&', '') for label in
                           ('Create a desktop shortcut (Play)', 'Create a desktop shortcut for Settings'))
            # Match the actual localized task descriptions, rather than list-box
            # check-state internals (TNewCheckListBox is not a Win32 ListView).
            rows.append({'name':tag,'expected':want,'ready_text':text,'actual':actual,'pass':actual == want})
            ui.user32.PostMessageW(ui.find(wiz,ui.CAPTIONS['en']['cancel']),ui.BM_CLICK,0,0)
            end = time.monotonic()+8
            while time.monotonic()<end:
                dialogs = run.desk.dialogs()
                if dialogs:
                    ui.m32.yes(dialogs[0]); break
                time.sleep(.1)
        finally:
            if not ui.m32.wait_exit(hproc,15):
                ui.kernel32.TerminateJobObject(run.desk.job,99)
            ui.kernel32.CloseHandle(hproc)
            ui.kernel32.CloseHandle(run.desk.job)
            ui.user32.CloseDesktop(run.desk.h)
    (out/'result.json').write_bytes((json.dumps(rows,indent=1)+'\n').encode())
    passed = sum(row['pass'] for row in rows)
    print('UX_TASKS_UI', 'PASS' if passed == len(rows) else 'FAIL',f'{passed}/{len(rows)}')
    return int(passed != len(rows))


if __name__ == '__main__':
    raise SystemExit(main())
