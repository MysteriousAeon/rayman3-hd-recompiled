"""Separate Stage2D guard update; frozen original runner/workspace remain unchanged."""
import argparse
from pathlib import Path
import sys
import subprocess
import gameplay as G
import proc_guard as P

HERE=Path(__file__).resolve().parent


def seal():
    rows={}
    for line in (HERE/'SHA256SUMS').read_text().splitlines():
        h,n=line.split('  ');G.C.need(n not in rows and '/' not in n and '\\' not in n and n not in ('.','..'),'invalid toolkit manifest')
        rows[n]=h;G.C.file_hash(HERE/n,h)


def guard(allow_root,record):
    seal();G.N.native()
    if allow_root:
        G.C.need(sys.stdin.isatty(),'administrator observer requires a realTTY')
        print('Explicit optional administrator READ ONLY observer for denied proc executable identities. sudo may prompt. Only four root-owned service paths can pass. No game runs as root; no system configuration or permission changes.')
    dest=HERE/record;G.C.need(not dest.exists(),'guard evidence exists; preserve it, use a separately named check')
    try:
        result=P.scan(G.root()/'installation/bin/r3hd',allow_root)
    except (ValueError,OSError,subprocess.SubprocessError,StopIteration,IndexError) as e:
        G.C.write(dest,{'result':'STOP','reason':str(e)});raise
    G.C.write(dest,result);print('R3HD_STAGE2D_GUARD SNAPSHOT PASS (no game execution by guard)')


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='action',required=True)
    c=sub.add_parser('check');c.add_argument('--allow-protected-inspection',action='store_true')
    h=sub.add_parser('human');h.add_argument('phase',choices=('a','save','load'));h.add_argument('--human-present',action='store_true');h.add_argument('--allow-protected-inspection',action='store_true')
    sub.add_parser('collect');a=p.parse_args();seal();G.N.native()
    if a.action=='collect':G.collect()
    elif a.action=='check':
        # Original guard failed before creation of a/ or any launch state. Never delete it.
        root=G.workspace()
        G.C.need(not any((root/n).exists() or (root/n).is_symlink() for n in ('a','save','load','test-user','test-cache','session-home')),'unexpected launch state exists; preserve and STOP for review')
        guard(a.allow_protected_inspection,'guard-preflight.json')
    else:
        G.no_other_game=lambda:guard(a.allow_protected_inspection,'guard-'+a.phase+'.json')
        G.run(a.phase,a.human_present)  # unchanged TTY/phrase, all original integrity/acceptance gates


if __name__=='__main__':
    try:main()
    except (ValueError,KeyError,OSError,subprocess.SubprocessError,StopIteration,IndexError) as e:
        raise SystemExit('R3HD_STAGE2D_GUARD STOP: '+str(e)+'; preserve all artifacts; no fallback/retry')
