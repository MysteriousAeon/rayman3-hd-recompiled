"""Explicit private capture-session control; never sends keyboard or mouse input."""
import argparse
import json
from pathlib import Path

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('session', type=Path)
    parser.add_argument('mode', choices=['hide', 'show'])
    args = parser.parse_args()
    session = args.session.resolve()
    record = json.loads((session / 'capture_session.json').read_bytes())
    if record.get('kind') != 'R3HD_PRIVATE_CAPTURE_BUILD_V1':
        raise SystemExit('Not a private capture session')
    control = session / 'hud.control'
    if control.is_symlink():
        raise SystemExit('Refusing linked control file')
    sequence = int(control.read_text().split()[0]) + 1
    if not 0 < sequence <= 0xFFFFFFFF:
        raise SystemExit('Invalid command sequence')
    # The hook accepts only a complete sequence + exact command. A short/partial read is ignored and retried.
    control.write_bytes(f'{sequence} {args.mode}\n'.encode('ascii'))
    print(f'HUD {args.mode} requested. Menus, cinematics and level changes reset it to visible.')

if __name__ == '__main__': main()
