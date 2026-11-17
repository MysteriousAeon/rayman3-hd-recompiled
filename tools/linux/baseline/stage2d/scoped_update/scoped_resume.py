"""Stage2D scoped controller; original gameplay supervisor/acceptance remain frozen."""
import argparse
from pathlib import Path
import subprocess
import sys
import gameplay as G
import scoped_guard as S
HERE=Path(__file__).resolve().parent


def seal():
    seen=set()
    for row in (HERE/'SHA256SUMS').read_text().splitlines():
        h,n=row.split('  ');G.C.need(n not in seen and n not in ('.','..') and not any(c in n for c in '/\\:'),'bad toolkit inventory')
        seen.add(n);G.C.file_hash(HERE/n,h)


def control_path():return Path.home()/'Projects/R3HD-baseline-noble-2d-control-01'


def examine(control,ref):
    control.check_children()
    return S.scan(ref)


class SpawnAdapter:
    """Forward helper calls unchanged; only the authenticated target inherits lock."""
    def __init__(self,module,control,ref,game):self.module=module;self.control=control;self.ref=ref;self.game=str(game)
    def __getattr__(self,n):return getattr(self.module,n)
    def Popen(self,args,**kw):
        G.C.need(str(args[0])==self.game,'unexpected supervisor target')
        examine(self.control,self.ref)  # recheck immediately before spawn, under lock
        kw['pass_fds']=tuple(set(kw.get('pass_fds',()))|{self.control.fd})
        child=self.module.Popen(args,**kw)
        try:self.control.register(child,self.ref)
        except (OSError,ValueError,KeyError,IndexError) as e:
            # Never lose the already-created child by throwing out of Popen.
            # The unchanged original supervisor still owns/waits/bounds it.
            self.control.registration_error=True
            print('SCOPED CONTROL registration error; keep attending, exit test normally; original supervisor remains active: '+str(e),file=sys.stderr)
        return child


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='action',required=True)
    sub.add_parser('check');h=sub.add_parser('human');h.add_argument('phase',choices=('a','save','load'));h.add_argument('--human-present',action='store_true');sub.add_parser('collect')
    a=p.parse_args();seal();G.N.native();S.require_unprivileged()
    if a.action=='collect':G.collect();return
    root=G.workspace();game=root/'installation/bin/r3hd';ref=S.identity(game)
    if a.action=='check':
        G.C.need(not any((root/n).exists() or (root/n).is_symlink() for n in ('a','save','load','test-user','test-cache','session-home')),'unexpected launch state; preserve and STOP')
    else:G.C.need(a.human_present and sys.stdin.isatty(),'realTTY/human present required; no unattended launch')
    with S.Control(control_path()) as control:
        summary=examine(control,ref)
        record=HERE/('scoped-preflight.json' if a.action=='check' else 'scoped-'+a.phase+'.json')
        G.C.write(record,summary);print(summary)
        if a.action=='check':
            print('R3HD_SCOPED_PREFLIGHT READY WITH LIMITS; NO GAME EXECUTION; not global game-absence proof');return
        print('Other protected/opaque external processes may remain unresolved. Lock coordinates this revised harness only. Close ALL other r3hd instances yourself; do not start another. No names are trusted as service exemptions.')
        G.C.need(input('Type I CLOSED OTHER R3HD INSTANCES: ')=='I CLOSED OTHER R3HD INSTANCES','external-game attestation not given')
        original=G.subprocess
        try:
            G.no_other_game=lambda:examine(control,ref)
            G.subprocess=SpawnAdapter(original,control,ref,game)
            G.run(a.phase,a.human_present)  # original authorization, integrity, routing, timeout, input and A-F gates
            G.C.need(not control.registration_error,'task child/lock registration incomplete; return evidence, no further phases')
        finally:G.subprocess=original


if __name__=='__main__':
    try:main()
    except (ValueError,KeyError,OSError,subprocess.SubprocessError,IndexError) as e:
        raise SystemExit('R3HD_SCOPED STOP: '+str(e)+'; preserve all evidence; no automatic retry')
