"""Prepare two isolated copies of a registered save; never launches gameplay."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import time
import uuid

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'tools'))
import m12_save_entry as saves
import r3hd_settings as settings

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--entry',default='knaar_20_human')
    a=ap.parse_args();entry=saves.load_entry(a.entry)
    if not saves.stored_profile_matches(entry):raise SystemExit('Registered source save differs; no copies made')
    executable=ROOT/'private/work/rex/out/build/win-amd64-release/r3hd.exe'
    executable_hash=hashlib.sha256(executable.read_bytes()).hexdigest()
    source=ROOT/'private/saves'/a.entry/'profile'
    if any(p.is_symlink() or p.lstat().st_file_attributes&0x400 for p in [source,*source.rglob('*')]):
        raise SystemExit('Redirected source refused')
    root=ROOT/'private/work/power_swirl/acceptance'/f'{time.strftime("%Y%m%d_%H%M%S")}_{uuid.uuid4().hex[:8]}'
    root.mkdir(parents=True,exist_ok=False)
    reg=settings.load_registry()
    for mode,value in [('A','original'),('B','restored')]:
        dst=root/'play/profiles'/mode/'user';shutil.copytree(source,dst)
        doc=settings.make_settings(reg,'custom','hdplus',[f'power_swirl={value}'])
        (root/(mode+'.json')).write_text(json.dumps(doc,indent=2),encoding='utf-8')
        command=f'@echo off\r\npowershell -NoProfile -ExecutionPolicy Bypass -File "{Path(__file__).with_name("visual_ab.ps1")}" -Workspace "{root}" -Mode {mode} -Manual\r\n'
        (root/(mode+'.cmd')).write_text(command,encoding='utf-8',newline='')
    (root/'acceptance.json').write_text(json.dumps(dict(schema=1,entry=a.entry,source_files=entry['files'],candidate_executable_sha256=executable_hash,
        created=time.strftime('%Y-%m-%d %H:%M:%S'),checklist=['Spiral shape and placement around Rayman',
        'Color matches the acquired power','Animation and alpha fade','Pickup and expiry after leaving the can',
        'No changes to canister beams, rings, charged attacks or later effects']),indent=2),encoding='utf-8')
    if not saves.stored_profile_matches(entry):raise SystemExit('Source identity changed while copying')
    print(root)
if __name__=='__main__':main()
