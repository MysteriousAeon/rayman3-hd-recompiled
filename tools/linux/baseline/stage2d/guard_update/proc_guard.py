"""Fail-closed concurrent-game snapshot; names/cmdline are never exemption evidence."""
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import protected_read as P

GAME_SHA='00cdd8f61a7393b00fb78c93dd2ebdea215332f02bbcf5ef3ff41cd466636d40'


def digest(fd):
    h=hashlib.sha256()
    while True:
        b=os.read(fd,1024*1024)
        if not b:break
        h.update(b)
    return h.hexdigest()


def game_identity(path):
    fd=os.open(path,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW)
    try:
        s=os.fstat(fd);P.need(stat.S_ISREG(s.st_mode) and digest(fd)==GAME_SHA,'test executable identity mismatch')
        return (s.st_size,s.st_dev,s.st_ino)
    finally:os.close(fd)


def privileged(pid,before,proc_stat):
    # Fixed observer bytes, isolated system Python, numeric arguments only.
    # No shell, target executable, attach, signals, memory, services or file writes.
    for path in ('/usr/bin/sudo',str(Path('/usr/bin/python3').resolve(strict=True))):P.trusted_path(path)
    code=(Path(__file__).parent/'protected_read.py').read_text()
    args=['/usr/bin/sudo','--','/usr/bin/python3','-I','-S','-B','-c',code,str(pid),str(before['start']),str(os.getuid()),str(proc_stat.st_dev),str(proc_stat.st_ino)]
    r=subprocess.run(args,stdout=subprocess.PIPE,text=True,check=True,timeout=90,env={'PATH':'/usr/bin:/bin','LANG':'C'})
    return json.loads(r.stdout)


def validate_proof(proof,pid,before,proc_stat):
    P.need(proof.get('root_service_inode_verified') is True and proof.get('pid')==pid and
        proof.get('start')==before['start'] and proof.get('uids')==before['uids'] and
        proof.get('proc_dev')==proc_stat.st_dev and proof.get('proc_ino')==proc_stat.st_ino and
        proof.get('executable') in P.ALLOWED,'invalid privileged identity proof')


def inspect(fd,pid,identity,allow_root):
    before=P.snapshot(fd)
    if os.getuid() not in before['uids']:return {'pid':pid,'result':'other UID'}
    if P.dead(fd,before):return {'pid':pid,'result':'dead'}
    s=os.fstat(fd)
    try:
        target=os.readlink('exe',dir_fd=fd)
        image=os.open('exe',os.O_RDONLY|os.O_CLOEXEC,dir_fd=fd)
        try:
            obj=os.fstat(image)
            P.need(Path(target.removesuffix(' (deleted)')).name.lower() not in ('r3hd','r3hd.exe'),'concurrent game executable')
            P.need((obj.st_dev,obj.st_ino)!=identity[1:],'concurrent game inode')
            if obj.st_size==identity[0]:P.need(digest(image)!=GAME_SHA,'concurrent renamed/copied game')
            after=os.stat('exe',dir_fd=fd)
            P.need((after.st_dev,after.st_ino)==(obj.st_dev,obj.st_ino),'exec raced inspection; STOP')
        finally:os.close(image)
        result={'pid':pid,'result':'readable executable checked'}
    except PermissionError:
        P.need(allow_root,'cannot verify same-user executable; explicit administrator observer required')
        proof=privileged(pid,before,s);validate_proof(proof,pid,before,s)
        result={'pid':pid,'result':'verified protected service','proof':proof}
    except FileNotFoundError:
        # Missing exe is not necessarily exit (main thread may have terminated).
        # Only disappearance of this bound proc directory or a dead state can pass.
        try:now=P.snapshot(fd)
        except FileNotFoundError:return {'pid':pid,'result':'bound process exited'}
        P.need(P.dead(fd,now),'live process has unavailable executable; STOP')
        return {'pid':pid,'result':'dead'}
    P.need(P.same(P.snapshot(fd),before),'process identity changed during scan; STOP')
    return result


def scan(game,allow_root=False,proc=Path('/proc')):
    identity=game_identity(game);rows=[]
    for d in sorted(proc.iterdir(),key=lambda p:p.name):
        if not d.name.isdigit():continue
        try:fd=os.open(d,os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC|os.O_NOFOLLOW)
        except FileNotFoundError:continue
        # Any inaccessible process directory/status remains unresolved, not exempt.
        try:
            try:rows.append(inspect(fd,int(d.name),identity,allow_root))
            except FileNotFoundError:
                # Bound proc fd cannot redirect to a reused PID; confirm it is gone.
                try:P.snapshot(fd)
                except FileNotFoundError:rows.append({'pid':int(d.name),'result':'bound process exited'})
                else:raise ValueError('unresolved process race; STOP')
        finally:os.close(fd)
    return {'result':'GUARD SNAPSHOT PASS','processes':rows,
        'limit':'snapshot only; cannot prevent a separate process starting/execing after inspection'}
