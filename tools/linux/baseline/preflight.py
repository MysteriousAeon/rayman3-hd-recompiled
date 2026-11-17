#!/usr/bin/env python3
"""Read-only CachyOS checks. Prints JSON; creates no files and never invokes podman info.

No network, namespaces, container creation, package install, write probes or remediation.
Exit 0 = static prerequisites only; exit 2 = STOP. Run as the future unprivileged builder.
"""
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tomllib

MIN_FREE = 50_000_000_000
PREFERRED_FREE = 70_000_000_000
MIN_RAM = 16_000_000_000
ARCH_DROPIN = Path('/usr/share/containers/containers.conf.d/00-containers-arch.conf')
ARCH_SETTINGS = {'containers': {'log_driver': 'journald'}, 'network': {'firewall_driver': 'nftables'}}


def containers_configuration(configs, approved_dropin=ARCH_DROPIN):
    """Read base configs and only the reported Arch vendor drop-in; never ignore files.

    TOML rejects duplicate keys/tables within a file. Across files, even equal explicit
    leaf assignments are refused: this gate does not implement general override semantics.
    The injected path is used only by synthetic tests; production uses the fixed vendor path.
    """
    seen, recorded = {}, {}
    copytmp = '/var/tmp'

    def consume(path, dropin=False):
        nonlocal copytmp
        require(str(path) not in recorded, 'duplicate configuration file: '+str(path))
        require(not path.is_symlink() and path.is_file(), 'configuration must be a regular file: '+str(path))
        data = tomllib.loads(path.read_text())
        if dropin:
            require(data == ARCH_SETTINGS, 'unreviewed Arch drop-in settings: '+str(path))
        def leaves(value, prefix=()):
            for key, item in value.items():
                setting = prefix+(key,)
                if isinstance(item, dict):
                    leaves(item, setting)
                else:
                    require(not any(setting[:len(old)] == old or old[:len(setting)] == setting for old in seen),
                            'duplicate/conflicting configuration: '+'.'.join(setting))
                    seen[setting] = str(path)
        leaves(data)
        recorded[str(path)] = data
        copytmp = data.get('engine', {}).get('image_copy_tmp_dir', copytmp)

    for conf in configs:
        if conf.exists() or conf.is_symlink():
            consume(conf)
        drop = conf.parent/(conf.name+'.d')
        require(not drop.is_symlink(), 'symlink drop-in directory requires review: '+str(drop))
        if drop.exists():
            require(drop.is_dir(), 'invalid drop-in directory: '+str(drop))
            for path in sorted(drop.iterdir()):
                require(path == approved_dropin, 'unexpected containers.conf drop-in: '+str(path))
                consume(path, dropin=True)
    return copytmp, recorded


def ancestor(path):
    path = Path(path).resolve()
    while not path.exists():
        path = path.parent
    return path


def allocation(text, user, uid):
    rows = []
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        name, first, size = line.split(':')
        rows.append((name, int(first), int(size)))
    own = [r for r in rows if r[0] in (user, str(uid))]
    if not own or sum(r[2] for r in own) < 65536:
        raise ValueError('need >=65536 subordinate IDs')
    for name, first, size in own:
        if first <= uid < first + size or first <= 0 or size <= 0:
            raise ValueError('invalid subordinate range')
        for other in rows:
            if other != (name, first, size) and max(first, other[1]) < min(first+size, other[1]+other[2]):
                raise ValueError('overlapping subordinate IDs')
    return own


def filesystem(path):
    existing = ancestor(path)
    p = subprocess.run(['findmnt', '--json', '--target', str(existing), '--output',
                        'TARGET,SOURCE,FSTYPE,UUID,OPTIONS'], capture_output=True, text=True, check=True)
    mount = json.loads(p.stdout)['filesystems'][0]
    mount['requested'] = str(path)
    mount['existing_ancestor'] = str(existing)
    mount['available_bytes'] = shutil.disk_usage(existing).free
    return mount


def check_storage(rows):
    identities = {r.get('uuid') or r['source'].split('[')[0] for r in rows}
    if len(identities) != 1:
        raise ValueError('workspace/graphroot/image-copy temp must use the one suitable filesystem; STOP, no relocation')
    for row in rows:
        if row['fstype'] not in ('ext4', 'btrfs', 'xfs') or 'ro' in row['options'].split(','):
            raise ValueError('unsupported/read-only backing filesystem; review required')
        if row['available_bytes'] < MIN_FREE:
            raise ValueError('less than 50,000,000,000 available bytes; do not delete existing data automatically')
    return 'preferred >=70GB' if min(r['available_bytes'] for r in rows) >= PREFERRED_FREE else 'minimum only; 70GB preferred'


def main():
    result = {'status': 'STOP', 'scope': 'static read-only host checks; no Podman namespace/storage initialization',
              'checks': {}, 'failures': [], 'limits': [
                  'Actual Podman info/mapping/overlay/network operation NOT tested',
                  'No write/allocate/quota test; free bytes are advisory and must be rechecked before each phase',
                  'No image/package/compiler/SDK/game/hardware compatibility tested']}
    def check(name, fn):
        try:
            result['checks'][name] = fn()
        except Exception as e:
            result['failures'].append(f'{name}: {e}')
    if platform.system() != 'Linux' or platform.machine() != 'x86_64' or not hasattr(os, 'getuid'):
        result['failures'].append('Run only on native CachyOS x86_64, never Windows/WSL/container')
    else:
        import pwd
        uid = os.getuid()
        home = Path.home().resolve()
        user = pwd.getpwuid(uid).pw_name
        check('unprivileged', lambda: require(uid != 0, 'do not use sudo/root'))
        check('native', lambda: require('microsoft' not in platform.release().lower()
              and not Path('/.dockerenv').exists() and not Path('/run/.containerenv').exists(), 'native host required'))
        check('os', lambda: require(re.search(r'(?m)^ID=["\x27]?cachyos["\x27]?$', Path('/etc/os-release').read_text()) is not None,
                                    'CachyOS identity not established'))
        check('environment', lambda: require(not any(os.environ.get(k) for k in (
              'CONTAINER_HOST', 'CONTAINER_CONNECTION', 'CONTAINERS_STORAGE_CONF', 'STORAGE_DRIVER', 'STORAGE_OPTS',
              'CONTAINERS_CONF', 'CONTAINERS_CONF_OVERRIDE', 'CONTAINERS_CONF_MODULES', 'TMPDIR')),
              'container/storage/TMPDIR override present; review rather than guessing'))
        for name in ('podman', 'conmon', 'newuidmap', 'newgidmap', 'passt', 'findmnt', 'git', 'sha256sum', 'tar'):
            check('tool:'+name, lambda n=name: require(shutil.which(n), 'missing prerequisite '+n))
        check('oci-runtime', lambda: require(shutil.which('crun') or shutil.which('runc'), 'missing OCI runtime'))
        for kind in ('subuid', 'subgid'):
            check(kind, lambda k=kind: allocation(Path('/etc/'+k).read_text(), user,
                                                 uid if k == 'subuid' else os.getgid()))
        check('userns', lambda: require(int(Path('/proc/sys/user/max_user_namespaces').read_text()) > 0,
                                       'user namespaces disabled; no sysctl changes'))
        def ram():
            values = dict(re.findall(r'^(\w+):\s+(\d+) kB', Path('/proc/meminfo').read_text(), re.M))
            available = int(values['MemAvailable'])*1024
            require(available >= MIN_RAM, 'need >=16,000,000,000 available RAM bytes; close own work and retry, no tuning')
            return {'available_bytes': available, 'total_bytes': int(values['MemTotal'])*1024}
        check('ram', ram)
        def storage():
            graphroot = str(Path(os.environ.get('XDG_DATA_HOME', str(home/'.local/share')))/'containers/storage')
            configs = [Path('/usr/share/containers/storage.conf'), Path('/etc/containers/storage.conf'),
                       Path(os.environ.get('XDG_CONFIG_HOME', str(home/'.config')))/'containers/storage.conf']
            recorded = {}
            for path in configs:
                if path.exists():
                    data = tomllib.loads(path.read_text()).get('storage', {})
                    recorded[str(path)] = data
                    # rootless_storage_path overrides system graphroot; user graphroot overrides the default.
                    if data.get('rootless_storage_path'):
                        graphroot = data['rootless_storage_path']
                    elif path == configs[-1] and data.get('graphroot'):
                        graphroot = data['graphroot']
                    require(data.get('driver', 'overlay') == 'overlay', 'non-overlay storage requires review')
                    require(not data.get('imagestore') and not data.get('transient_store'), 'split/transient storage requires review')
                    require(not data.get('options', {}).get('additionalimagestores'), 'additional image stores require review')
            graphroot = graphroot.replace('${HOME}', str(home)).replace('$HOME', str(home)).replace('$UID', str(uid))
            require('$' not in graphroot and Path(graphroot).is_absolute(), 'unresolved storage configuration')
            task = home/'Projects/R3HD-baseline-noble-01'
            # image_copy_tmp_dir defaults to /var/tmp (may be a different filesystem): inspect containers.conf.
            container_configs = [Path('/usr/share/containers/containers.conf'), Path('/etc/containers/containers.conf'),
                                 Path(os.environ.get('XDG_CONFIG_HOME', str(home/'.config')))/'containers/containers.conf']
            copytmp, container_records = containers_configuration(container_configs)
            require(copytmp != 'storage' and Path(copytmp).is_absolute(), 'special image-copy temp requires explicit review')
            rows = [filesystem(p) for p in (task, Path(graphroot), Path(copytmp))]
            budget = check_storage(rows)
            # /run and /tmp are separately reported, never substituted as bulk storage.
            return {'graphroot_predicted': str(Path(graphroot).resolve()), 'config': recorded,
                    'containers_config': container_records,
                    'image_copy_tmp_dir_predicted': copytmp, 'filesystems': rows, 'budget': budget,
                    'shared_budget_counted_once': True, 'runtime_free_bytes': shutil.disk_usage('/run').free,
                    'tmp_free_bytes': shutil.disk_usage('/tmp').free}
        check('storage', storage)
        if shutil.which('podman'):
            check('podman-version', lambda: subprocess.check_output(['podman', '--version'], text=True).strip())
    if not result['failures']:
        result['status'] = 'STATIC_PREFLIGHT_PASS'
    print(json.dumps(result, indent=2))
    return 0 if not result['failures'] else 2


def require(condition, message):
    if not condition:
        raise ValueError(message)
    return condition


if __name__ == '__main__':
    sys.exit(main())
