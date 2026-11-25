"""Replay last in the patch chain: HD+ Grand Minimus crown cutout overlay (G6-P127 / G6-P128, D-362 / D-363).

`tools/g6p127_crown_blend.h`: with `R3HD_CROWN_CUTOUT=cutout` (HD+ preset, Custom override) — or, only when
`R3HD_CROWN_CUTOUT` is unset/empty, developer diagnostic `R3HD_TEST_CROWN_BLEND=cutout` — a host read of any of the
10 independently verified `charact\\teensy_cour.dds` `.lvl` bundles overlapping its crown material `+0x6C` blend_byte
returns `0x08` (cutout, depth-write on, alpha-test GEQUAL) instead of `0x03` (alpha-blended, depth-write off), gated
fail-closed by exact filename, file size, LVL header, material flags/texture signature, source byte, and stored/patched
128-byte FNV-1a hashes. When disabled (`original` or unset), nothing changes.

One read site: `HostPathFile::ReadSync`, strictly after M26 / D-219 beam / D-221 lock-on and strictly before M33 mods
so any M33 data-only mod still wins. One start-up mode line beside `lockon_color` in `d3d12/command_processor.cpp`.
Host-only: no generated code, no guest patch, no file written to disk.
"""
from m8_runtime_patch import patch_once
from m16_runtime_patch import install

if __name__ == '__main__':
    install('g6p127_crown_blend.h')

    patch_once('src/filesystem/devices/host_path_file.cpp', [
        ('#include <rex/r3hd_lockon_color.h>\n',
         '#include <rex/r3hd_lockon_color.h>\n#include <rex/g6p127_crown_blend.h>\n'),
        ('    // M33 (D-070): off unless R3HD_MODS_PLAN names a verified plan; listed ranges of listed files only.\n',
         '    // G6-P127 / G6-P128 (D-362, D-363): HD+ Grand Minimus crown cutout (0x03 -> 0x08) across all 10\n'
         '    // verified teensy_cour.dds .lvl bundles; off unless R3HD_CROWN_CUTOUT=cutout (or diagnostic fallback\n'
         '    // R3HD_TEST_CROWN_BLEND=cutout when R3HD_CROWN_CUTOUT is unset). Before M33 so mods win.\n'
         '    if (g6p127crown::Enabled()) {\n'
         '      g6p127crown::state().log = &M26Log;\n'
         '      g6p127crown::AfterRead(static_cast<HostPathEntry*>(entry())->host_path(), byte_offset, buffer.data(),\n'
         '                             out_bytes_read ? *out_bytes_read : buffer.size());\n'
         '    }\n'
         '    // M33 (D-070): off unless R3HD_MODS_PLAN names a verified plan; listed ranges of listed files only.\n'),
    ])

    patch_once('src/graphics/d3d12/command_processor.cpp', [
        ('#include <rex/r3hd_lockon_color.h>\n',
         '#include <rex/r3hd_lockon_color.h>\n#include <rex/g6p127_crown_blend.h>\n'),
        ('  REXGPU_INFO("R3HD lockon_color={}", r3hdlockon::Enabled() ? "restored" : "original");\n',
         '  REXGPU_INFO("R3HD lockon_color={}", r3hdlockon::Enabled() ? "restored" : "original");\n'
         '  REXGPU_INFO("R3HD crown_cutout={}", g6p127crown::Enabled() ? "cutout" : "original");\n'),
    ])
