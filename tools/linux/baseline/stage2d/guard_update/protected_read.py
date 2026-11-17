"""Optional administrator observer. Read-only proc/executable metadata; no target execution."""
import json
import os
from pathlib import Path
import stat
import sys

ALLOWED=('/usr/lib/systemd/systemd','/usr/bin/kwin_wayland',
         '/usr/lib/polkit-kde-authentication-agent-1',
         '/usr/lib/systemd/systemd-executor')


def need(ok,message):
    if not ok:raise ValueError(message)


def read_at(fd,name):
    n=os.open(name,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW,dir_fd=fd)
    with os.fdopen(n) as f:return f.read()


def snapshot(fd):
    status=read_at(fd,'status');uids=next(s for s in status.splitlines() if s.startswith('Uid:')).split()[1:]
    uids=list(map(int,uids));need(len(uids)==4,'invalid UID record')
    raw=read_at(fd,'stat');fields=raw.rsplit(')',1)[1].split()
    return {'uids':uids,'start':int(fields[19]),'state':fields[0]}


def same(a,b):return a['uids']==b['uids'] and a['start']==b['start']


def dead(fd,snap):
    if snap['state'] not in ('Z','X'):return False
    task=os.open('task',os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC|os.O_NOFOLLOW,dir_fd=fd)
    try:return len(os.listdir(task))<=1
    finally:os.close(task)


def trusted_path(path):
    """Canonical root-owned file and ancestors, no symlink/group/other write."""
    p=Path(path);need(p.is_absolute() and p.resolve(strict=True)==p,'noncanonical service path')
    for part in [p]+list(p.parents):
        s=part.lstat();need(s.st_uid==0 and not s.st_mode&0o022 and not stat.S_ISLNK(s.st_mode),'untrusted service path')
    need(p.is_file(),'not regular service executable')


def inspect(pid,start,uid,dev,ino):
    need(os.geteuid()==0,'administrator observer only')
    need(0<pid<2**31 and start>0 and uid>0,'invalid identity arguments')
    fd=os.open('/proc/'+str(pid),os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC|os.O_NOFOLLOW)
    try:
        s=os.fstat(fd);need((s.st_dev,s.st_ino)==(dev,ino),'PID directory changed')
        before=snapshot(fd);need(before['start']==start and uid in before['uids'],'process identity changed')
        need(before['state'] not in ('Z','X'),'process is dead; rescan')
        path=os.readlink('exe',dir_fd=fd);need(path in ALLOWED,'protected executable is not an allowed service')
        trusted_path(path)
        image=os.open('exe',os.O_RDONLY|os.O_CLOEXEC,dir_fd=fd)
        try:
            actual=os.fstat(image);known=os.stat(path,follow_symlinks=False)
            need(stat.S_ISREG(actual.st_mode) and actual.st_uid==0 and not actual.st_mode&0o022,'untrusted executable inode')
            need((actual.st_dev,actual.st_ino)==(known.st_dev,known.st_ino),'service pathname/inode mismatch')
            need(same(snapshot(fd),before) and os.readlink('exe',dir_fd=fd)==path,'identity/exec changed during inspection')
            # Repeat inode comparison: an exec of a different image at the same PID is not an exemption.
            after=os.stat('exe',dir_fd=fd)
            need((after.st_dev,after.st_ino)==(actual.st_dev,actual.st_ino),'executable changed')
            return {'pid':pid,'start':start,'uids':before['uids'],'proc_dev':dev,'proc_ino':ino,
                'executable':path,'image_dev':actual.st_dev,'image_ino':actual.st_ino,'root_service_inode_verified':True}
        finally:os.close(image)
    finally:os.close(fd)


if __name__=='__main__':
    try:
        need(len(sys.argv)==6,'five numeric identity arguments required')
        print(json.dumps(inspect(*map(int,sys.argv[1:]))))
    except (ValueError,OSError,StopIteration,IndexError) as e:
        print('R3HD_PROTECTED_READ STOP: '+str(e),file=sys.stderr);sys.exit(2)
