"""Replay last in the patch chain: HD+ out-of-range lock-on indicator colour as a verified read overlay (D-221).

`tools/r3hd_lockon_color.h`: with R3HD_LOCKON_COLOR=restored a host read of fix.btf returns the `ago_targetfar` page
(the distant-target indicator) with its DXT1 endpoints mapped onto the original PC blue ramp, gated by file size and
the stored and restored page hashes. Without the variable nothing changes.

One site: HostPathFile::ReadSync, after the M26 correction and the D-219 beam overlay and before the M33 mod overlay,
so a data-only mod that replaces the page still wins. Inserted next to blocks that earlier steps leave in place and
run after every other step, so no earlier step's anchor moves. One start-up mode line beside the beam line (D3D12).
Host-only: no generated code, no guest patch, no file written.
"""
from m8_runtime_patch import patch_once
from m16_runtime_patch import install

if __name__ == '__main__':
    install('r3hd_lockon_color.h')

    patch_once('src/filesystem/devices/host_path_file.cpp', [
        ('#include <rex/r3hd_beam_color.h>\n',
         '#include <rex/r3hd_beam_color.h>\n#include <rex/r3hd_lockon_color.h>\n'),
        ('    // M33 (D-070): off unless R3HD_MODS_PLAN names a verified plan; listed ranges of listed files only.\n',
         '    // D-221: HD+ out-of-range lock-on colour, off unless R3HD_LOCKON_COLOR=restored; one fix page only.\n'
         '    // Before M33 so that a mod replacing the page wins.\n'
         '    if (r3hdlockon::Enabled()) {\n'
         '      r3hdlockon::state().log = &M26Log;\n'
         '      r3hdlockon::AfterRead(static_cast<HostPathEntry*>(entry())->host_path(), byte_offset, buffer.data(),\n'
         '                            out_bytes_read ? *out_bytes_read : buffer.size());\n'
         '    }\n'
         '    // M33 (D-070): off unless R3HD_MODS_PLAN names a verified plan; listed ranges of listed files only.\n'),
    ])

    patch_once('src/graphics/d3d12/command_processor.cpp', [
        ('#include <rex/r3hd_beam_color.h>\n', '#include <rex/r3hd_beam_color.h>\n#include <rex/r3hd_lockon_color.h>\n'),
        ('  REXGPU_INFO("R3HD beam_color={}", r3hdbeam::Enabled() ? "restored" : "original");\n',
         '  REXGPU_INFO("R3HD beam_color={}", r3hdbeam::Enabled() ? "restored" : "original");\n'
         '  REXGPU_INFO("R3HD lockon_color={}", r3hdlockon::Enabled() ? "restored" : "original");\n'),
    ])
