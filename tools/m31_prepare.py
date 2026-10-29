"""M31 host additions (D-068): the project icon as r3hd.exe's first icon resource (SDL registers the game window's
class with it, so the window and its taskbar button show it). tools/make_r3hd_icon.py draws the icon into the game
project (private/work/rex, a build output like the generated code) with a one-line resource script beside it.
Runs after m26_prepare.py (each prepare script rewrites everything after its own marker)."""
import hashlib
import json
import subprocess
import sys

from m2_prepare import W, write_text_if_changed

if __name__ == '__main__':
    subprocess.run([sys.executable, str(W.parents[2] / 'tools' / 'make_r3hd_icon.py'), '--out', str(W / 'r3hd.ico')],
                   check=True)
    # M33: the build does not see the .ico as an input of the resource script, so the script names the icon's hash:
    # a new icon changes the script and r3hd.exe is relinked with it (the M33 redesign found this).
    digest = hashlib.sha256((W / 'r3hd.ico').read_bytes()).hexdigest()
    version = json.loads((W.parents[2] / 'config/release/payload.json').read_text(encoding='utf-8'))['version']
    numbers = version.split('.')
    assert len(numbers) == 3 and all(n.isdecimal() and 0 <= int(n) <= 65535 for n in numbers), version
    numeric = ','.join(numbers + ['0'])
    write_text_if_changed(W / 'r3hd_icon.rc', f'// M31: written by tools/m31_prepare.py; icon sha256 {digest}\n'
                                              '1 ICON "r3hd.ico"\n' + f'''
1 VERSIONINFO
FILEVERSION {numeric}
PRODUCTVERSION {numeric}
FILEFLAGSMASK 0x3F
FILEFLAGS 0
FILEOS 0x40004
FILETYPE 1
BEGIN
  BLOCK "StringFileInfo"
  BEGIN
    BLOCK "040904B0"
    BEGIN
      VALUE "FileDescription", "Rayman 3 HD Recompiled"
      VALUE "ProductName", "Rayman 3 HD Recompiled"
      VALUE "FileVersion", "{version}"
      VALUE "ProductVersion", "{version}"
      VALUE "InternalName", "r3hd"
      VALUE "OriginalFilename", "r3hd.exe"
    END
  END
  BLOCK "VarFileInfo"
  BEGIN
    VALUE "Translation", 0x409, 1200
  END
END
''')
    p = W / 'CMakeLists.txt'
    mark = '\n# --- Milestone 31 targets ---\n'
    write_text_if_changed(p, p.read_text().split(mark)[0] + mark + '''enable_language(RC)
target_sources(r3hd PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/r3hd_icon.rc")
target_link_options(r3hd PRIVATE "LINKER:/MANIFESTINPUT:${CMAKE_CURRENT_SOURCE_DIR}/../../../tools/m2_host/r3hd.manifest")
''')
