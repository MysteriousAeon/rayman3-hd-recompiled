"""Replay after the M32 patch at the same pin: data-only mods as a verified byte overlay on game-file reads (M33, D-070).

`tools/m33_mod_overlay.h`: with R3HD_MODS_PLAN naming a plan written by tools/r3hd_mods.py, a host read of a game file
the plan lists returns the plan's replacement bytes where its ranges overlap the read. The plan is verified as a whole
(sizes, the game's own bytes, the replacement bytes) before anything is served; any failure leaves it unused.
Without the variable nothing changes: the read returns the file's bytes, and the cost is one flag test per read.

One site: HostPathFile::ReadSync, after a successful host read and after the M26 correction (so a mod wins over it).
host_path_file.cpp is rebuilt from the pin by m20_runtime_patch.py on every replay, then m26 and this script patch
it in order. One log line per process (`M33 mods=plan|off`) beside the M26 one. Host-only: no generated code, no
guest patch, no file written.
"""
from m8_runtime_patch import patch_once
from m16_runtime_patch import install

if __name__ == '__main__':
    install('m33_mod_overlay.h')

    patch_once('src/filesystem/devices/host_path_file.cpp', [
        ('#include <rex/m26_texture_orient.h>\n',
         '#include <rex/m26_texture_orient.h>\n#include <rex/m33_mod_overlay.h>\n'),
        ('static void M26Log(const char* line) {\n  REXLOG_INFO("{}", line);\n}\n',
         'static void M26Log(const char* line) {\n  REXLOG_INFO("{}", line);\n}\n\n'
         '// M33 (D-070): data-only mods, see tools/m33_mod_overlay.h.\n'
         'static void M33Log(const char* line) {\n  REXLOG_INFO("{}", line);\n}\n'),
        ('                        out_bytes_read ? *out_bytes_read : buffer.size());\n'
         '    }\n'
         '    return X_STATUS_SUCCESS;\n',
         '                        out_bytes_read ? *out_bytes_read : buffer.size());\n'
         '    }\n'
         '    // M33 (D-070): off unless R3HD_MODS_PLAN names a verified plan; listed ranges of listed files only.\n'
         '    if (m33mods::Enabled()) {\n'
         '      m33mods::state().log = &M33Log;\n'
         '      m33mods::AfterRead(static_cast<HostPathEntry*>(entry())->host_path(), byte_offset, buffer.data(),\n'
         '                         out_bytes_read ? *out_bytes_read : buffer.size());\n'
         '    }\n'
         '    return X_STATUS_SUCCESS;\n'),
    ])

    patch_once('src/graphics/d3d12/command_processor.cpp', [
        ('#include <rex/m26_texture_orient.h>\n', '#include <rex/m26_texture_orient.h>\n#include <rex/m33_mod_overlay.h>\n'),
        # In front of the M26 line: the M26 and M23 patches still find their own lines together on a replay.
        ('  REXGPU_INFO("M26 texture_orient={}", m26tex::Enabled() ? "corrected" : "original");\n',
         '  REXGPU_INFO("M33 mods={}", m33mods::Enabled() ? "plan" : "off");\n'
         '  REXGPU_INFO("M26 texture_orient={}", m26tex::Enabled() ? "corrected" : "original");\n'),
    ])
