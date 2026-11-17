"""Cooperative task serialization plus limited, unprivileged external-game detection.

No service allowlist, sudo, process-memory access or process termination.
Unknown external identities are reported, never certified as non-game.
"""
import errno
import hashlib
import json
import os
from pathlib import Path
import stat
import uuid
try:import fcntl
except ImportError:fcntl=None

GAME_SHA='00cdd8f61a7393b00fb78c93dd2ebdea215332f02bbcf5ef3ff41cd466636d40'


def need(ok,message):
    if not ok:raise ValueError(message)


def write(path,data):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'w') as f:json.dump(data,f,sort_keys=True,indent=2);f.write('\n')


def boot():return Path('/proc/sys/kernel/random/boot_id').read_text().strip()


def read_at(fd,name,limit=65536):
    n=os.open(name,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW,dir_fd=fd)
    with os.fdopen(n,'rb') as f:return f.read(limit)


def snapshot(fd):
    rows={s.split(':',1)[0]:s.split(':',1)[1].strip() for s in read_at(fd,'status').decode().splitlines() if ':' in s}
    fields=read_at(fd,'stat').decode().rsplit(')',1)[1].split();s=os.fstat(fd)
    uids=list(map(int,rows['Uid'].split()));need(len(uids)==4,'invalid kernel UID tuple')
    return {'uids':uids,'start':int(fields[19]),'state':fields[0],'threads':int(rows['Threads']),
        'caps':int(rows['CapEff'],16),'permitted':int(rows['CapPrm'],16),'ambient':int(rows.get('CapAmb','0'),16),
        'proc_dev':s.st_dev,'proc_ino':s.st_ino}


def same(a,b):return all(a[n]==b[n] for n in ('uids','start','proc_dev','proc_ino'))


def dead(s):return s['state'] in ('Z','X') and s['threads']==1


def require_unprivileged():
    fd=os.open('/proc/'+str(os.getpid()),os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC|os.O_NOFOLLOW)
    try:
        s=snapshot(fd);uid=os.getuid()
        need(uid!=0 and s['uids']==[uid]*4 and not any(s[n] for n in ('caps','permitted','ambient')),'ordinary unprivileged caller required; do not use sudo/capabilities')
    finally:os.close(fd)


def digest(fd):
    h=hashlib.sha256()
    while True:
        b=os.read(fd,1024*1024)
        if not b:break
        h.update(b)
    return h.hexdigest()


def identity(path):
    fd=os.open(path,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW)
    try:
        s=os.fstat(fd)
        need(stat.S_ISREG(s.st_mode) and s.st_uid==os.getuid() and not s.st_mode&0o6022,'untrusted/privileged target executable mode')
        try:cap=os.getxattr(fd,'security.capability')
        except OSError as e:
            if e.errno not in (errno.ENODATA,errno.EOPNOTSUPP):raise
            cap=b''
        need(not cap,'file capabilities on target are unsupported')
        need(digest(fd)==GAME_SHA,'target executable hash mismatch')
        return {'size':s.st_size,'dev':s.st_dev,'ino':s.st_ino,'sha256':GAME_SHA}
    finally:os.close(fd)


def hint(fd,with_args=False):
    """Positive suspicion only; absence never proves a process is non-game."""
    values=[]
    for name in (('comm','cmdline') if with_args else ('comm',)):
        try:values.extend(read_at(fd,name,4096).decode(errors='replace').replace('\0','\n').splitlines())
        except (PermissionError,FileNotFoundError):continue
    return any(Path(s.strip()).name.lower() in ('r3hd','r3hd.exe') for s in values)


def probe(fd,ref,uid):
    suspect=hint(fd)
    try:s=snapshot(fd)
    except PermissionError:
        suspect=suspect or hint(fd,with_args=True)
        need(not suspect,'relevant game identity has inaccessible credentials')
        return 'UNKNOWN_CREDENTIALS'
    if dead(s):return 'EXITED'
    if uid not in s['uids']:
        need(not suspect,'possible game under another UID; close it yourself')
        return 'OTHER_UID_NOT_CHECKED'
    # Normal Stage2D is all-user, no effective capabilities. Mixed/setuid helpers
    # are outside that target model, not authenticated by their names or paths.
    ordinary=s['uids']==[uid]*4 and s['caps']==0
    if not ordinary and not suspect:return 'OUTSIDE_UNPRIVILEGED_TARGET_MODEL'
    try:
        target=os.readlink('exe',dir_fd=fd)
        image=os.open('exe',os.O_RDONLY|os.O_CLOEXEC,dir_fd=fd)
        try:
            obj=os.fstat(image)
            need(Path(target.removesuffix(' (deleted)')).name.lower() not in ('r3hd','r3hd.exe'),'concurrent game executable')
            need((obj.st_dev,obj.st_ino)!=(ref['dev'],ref['ino']),'concurrent game inode')
            if obj.st_size==ref['size']:need(digest(image)!=ref['sha256'],'concurrent renamed/copied sealed game')
            after=os.stat('exe',dir_fd=fd)
            stable=(after.st_dev,after.st_ino)==(obj.st_dev,obj.st_ino) and same(s,snapshot(fd))
        finally:os.close(image)
        need(not suspect,'game indicator remains ambiguous despite different executable; STOP')
        return 'READABLE_IMAGE_NOT_MATCHED' if stable else 'UNKNOWN_EXEC_RACE'
    except (PermissionError,FileNotFoundError):
        try:now=snapshot(fd)
        except FileNotFoundError:return 'EXITED'
        if dead(now):return 'EXITED'
        suspect=suspect or hint(fd,with_args=True)
        need(not suspect,'relevant game executable is inaccessible; STOP')
        return 'UNKNOWN_IMAGE'


def scan(ref,proc=Path('/proc')):
    counts={}
    for p in proc.iterdir():
        if not p.name.isdigit() or int(p.name)==os.getpid():continue
        try:fd=os.open(p,os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC|os.O_NOFOLLOW)
        except FileNotFoundError:continue
        except PermissionError:
            counts['UNKNOWN_PROCESS_DIRECTORY']=counts.get('UNKNOWN_PROCESS_DIRECTORY',0)+1;continue
        try:
            try:kind=probe(fd,ref,os.getuid())
            except FileNotFoundError:
                try:snapshot(fd)
                except FileNotFoundError:kind='EXITED'
                else:raise ValueError('unresolved proc race')
            except ValueError as e:raise ValueError('PID '+p.name+': '+str(e))
            counts[kind]=counts.get(kind,0)+1
        finally:os.close(fd)
    return {'scope':'cooperative task lock + limited external scan; NOT global game absence proof',
        'counts':counts,'unresolved_external_identities':sum(v for k,v in counts.items() if k.startswith('UNKNOWN')),
        'external_attestation_required':True,'privileged_inspection':False}


class Control:
    def __init__(self,path):self.path=path;self.fd=None;self.boot=boot();self.registration_error=False

    def __enter__(self):
        p=self.path;need(p.is_absolute() and p.parent.resolve()==p.parent,'real control parent required')
        if not p.exists():p.mkdir(mode=0o700)
        s=p.lstat();need(stat.S_ISDIR(s.st_mode) and not p.is_symlink() and s.st_uid==os.getuid() and stat.S_IMODE(s.st_mode)==0o700,'untrusted control directory')
        f=p/'task.lock';fd=os.open(f,os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW|os.O_CLOEXEC,0o600)
        try:
            s=os.fstat(fd);t=f.lstat()
            need(stat.S_ISREG(s.st_mode) and s.st_uid==os.getuid() and stat.S_IMODE(s.st_mode)==0o600 and s.st_nlink==1 and (s.st_dev,s.st_ino)==(t.st_dev,t.st_ino),'untrusted lock inode')
            try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:raise ValueError('another cooperative Stage2D owner/child holds task lock; no termination')
        except BaseException:os.close(fd);raise
        self.fd=fd
        return self

    def __exit__(self,*args):
        # Close only. LOCK_UN would also release a child's inherited OFD lock.
        os.close(self.fd);self.fd=None

    def check_children(self,proc=Path('/proc')):
        for p in self.path.glob('child-*.json'):
            f=p.lstat()
            need(stat.S_ISREG(f.st_mode) and not p.is_symlink() and f.st_uid==os.getuid() and stat.S_IMODE(f.st_mode)==0o600 and f.st_nlink==1,'untrusted task record')
            r=json.loads(p.read_text());need(r['schema']==1 and r['expected_game_sha256']==GAME_SHA and type(r['pid']) is int and 0<r['pid']<2**31,'invalid task registry identity')
            if r['boot']!=self.boot:continue
            if r.get('unresolved'):raise ValueError('unresolved prior owned launch; preserve record and request review')
            need(all(type(r[n]) is int for n in ('start','proc_dev','proc_ino')) and r['start']>0 and r['proc_dev']>=0 and r['proc_ino']>0,'invalid recorded process identity; STOP')
            try:fd=os.open(proc/str(r['pid']),os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC|os.O_NOFOLLOW)
            except FileNotFoundError:continue
            try:
                try:s=snapshot(fd)
                except FileNotFoundError:continue
                # Recycled PID is stale metadata, never a reason to signal it.
                if any(s[n]!=r[n] for n in ('start','proc_dev','proc_ino')):continue
                need(dead(s),'previous authenticated task child still live/ambiguous; no termination')
            finally:os.close(fd)

    def register(self,child,ref):
        record={'schema':1,'boot':self.boot,'pid':child.pid,'expected_game_sha256':GAME_SHA}
        try:
            fd=os.open('/proc/'+str(child.pid),os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC|os.O_NOFOLLOW)
            try:
                s=snapshot(fd);record.update({n:s[n] for n in ('uids','start','proc_dev','proc_ino')})
                need(s['uids']==[os.getuid()]*4 and not any(s[n] for n in ('caps','permitted','ambient')),'unexpected child privilege')
                image=os.stat('exe',dir_fd=fd)
                need((image.st_dev,image.st_ino)==(ref['dev'],ref['ino']),'spawned executable identity mismatch')
                record.update(image_dev=image.st_dev,image_ino=image.st_ino,child_executable_inode_verified=True)
                try:
                    inherited=os.stat('fd/'+str(self.fd),dir_fd=fd);held=os.fstat(self.fd)
                    record['inherited_lock_observed']=(inherited.st_dev,inherited.st_ino)==(held.st_dev,held.st_ino)
                except OSError:record['inherited_lock_observed']=False
                if not record['inherited_lock_observed']:raise ValueError('child lock inheritance could not be verified')
                after=os.stat('exe',dir_fd=fd)
                need(same(s,snapshot(fd)) and (after.st_dev,after.st_ino)==(image.st_dev,image.st_ino),'child identity changed during registration')
            finally:os.close(fd)
        except (OSError,ValueError,KeyError,IndexError):
            if child.poll() is not None:return  # already exited, no orphan to serialize
            record['unresolved']=True;self.registration_error=True
        write(self.path/('child-'+uuid.uuid4().hex+'.json'),record)
