"""Point-and-click front end for convert.py (standard library tkinter). Built into a single exe with
build_exe.bat. Flow: choose the PC .sav -> find (or choose) the HD slot file -> show what will be converted
-> confirm -> convert into the slot, keeping a .bak of the old slot file. The PC file is only read.
"""
import contextlib
import io
import os
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

import convert

TITLE = 'Rayman 3 PC save converter'
SLOT_GLOB = 'profiles/*/user/*/5841123F/00000001/*/*'


def run_convert(*argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        code = convert.main(list(argv))
    return code, out.getvalue()


def default_roots():
    """The installed edition's home, and the folder the exe sits in and its parent (portable)."""
    roots = []
    if os.environ.get('LOCALAPPDATA'):
        roots.append(Path(os.environ['LOCALAPPDATA']) / 'Rayman3HDRecomp')
    here = Path(sys.executable if getattr(sys, 'frozen', False) else __file__).resolve().parent
    return roots + [here, here.parent]


def find_slots(roots=None):
    """HD slot files of the installed edition, and of a portable folder the exe sits in or beside."""
    roots = default_roots() if roots is None else roots
    found = set()
    for root in roots:  # fixed depth only: never a recursive walk of a user folder (Downloads -> whole profile)
        for pattern in (SLOT_GLOB, '*/' + SLOT_GLOB):
            for p in root.glob(pattern) if root.is_dir() else []:
                if p.is_file() and convert.is_slot_file(p):
                    found.add(p.resolve())
    return sorted(found)


def game_running():
    try:
        out = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq r3hd.exe'], capture_output=True, text=True,
                             creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)).stdout
        return 'r3hd.exe' in out.lower()
    except OSError:
        return False


def summary(text):
    keep = ('resume level', 'highest world', 'revisit', 'cages', 'score', 'life', 'WARNING')
    return '\n'.join(l for l in text.splitlines() if l.startswith(keep))


def main():
    root = tk.Tk()
    root.withdraw()
    messagebox.showinfo(TITLE, 'Before converting:\n\n1. In Rayman 3 HD Recompiled start a New Game, confirm the '
                               'player name, then quit the game.\n2. Back up your profiles folder.\n\n'
                               'Next, choose your original PC save (.sav).')
    pc = filedialog.askopenfilename(title='Choose your Rayman 3 PC save', filetypes=[('PC save', '*.sav'), ('All', '*.*')])
    if not pc:
        return
    code, text = run_convert('--input', pc, '--dry-run')
    if code:
        messagebox.showerror(TITLE, 'This file cannot be converted:\n\n' + text[-1500:])
        return
    slots = find_slots()
    slot = None
    if len(slots) == 1 and messagebox.askyesno(TITLE, 'Convert into this HD save slot?\n\n%s' % slots[0]):
        slot = str(slots[0])
    if slot is None:
        messagebox.showinfo(TITLE, 'Choose the HD slot file:\nprofiles\\default\\user\\B13EBABEBABEBABE\\5841123F\\'
                                   '00000001\\<NAME>\\<NAME> (no extension).')
        slot = filedialog.askopenfilename(title='Choose the HD save slot file (e.g. RAY\\RAY)')
        if not slot:
            return
    code, check = run_convert('--input', slot, '--dry-run')
    if code or 'format HD' not in check:
        messagebox.showerror(TITLE, 'That is not an HD Recompiled save slot:\n\n' + check[-1000:])
        return
    if not messagebox.askyesno(TITLE, 'PC save:\n%s\n\n%s\n\nReplace the HD slot with this progress? A .bak copy of the '
                                      'old slot file is kept in the save_converter_backups folder.' % (pc, summary(text))):
        return
    if game_running():
        messagebox.showerror(TITLE, 'Rayman 3 HD Recompiled is running. Quit the game and try again.')
        return
    code, text = run_convert('--input', pc, '--donor', slot, '--output', slot, '--force')
    if code:
        messagebox.showerror(TITLE, 'Conversion failed; nothing was replaced unless stated below:\n\n' + text[-1500:])
        return
    backup = next((l.split(' to ', 1)[1] for l in text.splitlines() if l.startswith('existing output backed up')), '?')
    messagebox.showinfo(TITLE, 'Done. Start the game, choose Load and pick your slot.\n\nBackup of the old slot:\n'
                               + backup)


if __name__ == '__main__':
    main()
