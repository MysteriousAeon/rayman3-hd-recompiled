"""Replay after the M45 patch at the same pin: FFmpeg and libmspack as their own DLLs (M46, D-084).

The pinned SDK links FFmpeg (libavutil + libavcodec, LGPL-2.1-or-later) and libmspack's lzxd.c (LGPL-2.1) statically
into rexruntime.dll (release blocker L-4, reports/milestone42). LGPL-2.1 section 6(b) allows a work to use the
Library through a shared library mechanism that the user can replace. This script

  * builds libmspack's lzxd.c as mspack.dll (SHARED, every external symbol exported: lzxd_*);
  * adds ffmpeg.dll: the unchanged static libavutil / libavcodec archives linked into one DLL, exports written by
    m46_ffmpeg_def.cmake from the archives (all "av*" symbols, as upstream's libavutil.v / libavcodec.v);
  * links rexaudio (inside rexruntime.dll) to ffmpeg instead of the static archives, and rexruntime to bcrypt
    itself (xboxkrnl_crypt.cpp; it was reached only through libavutil's link interface before);
  * installs and exports both DLLs with the SDK, and stages them next to every host binary that the SDK's
    rexglue_configure_target sets up (beside rexruntime.dll).

The FFmpeg and libmspack sources, their configuration (config_windows_x86_64.h) and source lists are not changed.
The static libavutil / libavcodec targets stay as they were (tools/m40_asan builds them). Host-only: no generated
code, no guest patch. Files keep their own line endings (bytes in, bytes out); a second run changes nothing.
"""
import shutil

from m3_runtime_patch import ROOT, SDK
from m45_runtime_patch import patch_bytes

OVERLAY = 'thirdparty/ffmpeg-overlay'


def install_overlay(name):
    source = ROOT / 'tools' / name
    target = SDK / OVERLAY / name
    if not target.exists() or target.read_bytes() != source.read_bytes():
        shutil.copyfile(source, target)
        print('installed', OVERLAY + '/' + name)


FFMPEG_DLL = '''
#=============================================================================
# M46 (D-084): FFmpeg as its own DLL, replaceable by the user (LGPL-2.1 s.6b).
# ffmpeg.dll holds the static libavutil and libavcodec archives above; its
# exports are their "av*" symbols (upstream's libavutil.v / libavcodec.v),
# listed by m46_ffmpeg_def.cmake. The per-config list sits in the build tree.
#=============================================================================
set(FFMPEG_DLL_DEF "${CMAKE_CURRENT_BINARY_DIR}/ffmpeg-dll/$<CONFIG>/ffmpeg.def")
add_custom_command(
    OUTPUT "${FFMPEG_DLL_DEF}"
    COMMAND "${CMAKE_COMMAND}" "-DNM=${CMAKE_NM}" "-DAVUTIL=$<TARGET_FILE:libavutil>"
            "-DAVCODEC=$<TARGET_FILE:libavcodec>" "-DOUT=${FFMPEG_DLL_DEF}"
            -P "${FFMPEG_OVERLAY_SRC_DIR}/m46_ffmpeg_def.cmake"
    DEPENDS libavutil libavcodec "${FFMPEG_OVERLAY_SRC_DIR}/m46_ffmpeg_def.cmake"
    COMMENT "Listing the av* exports of ffmpeg.dll"
    VERBATIM
)
add_custom_target(ffmpeg_def DEPENDS "${FFMPEG_DLL_DEF}")
add_library(ffmpeg SHARED "${FFMPEG_OVERLAY_SRC_DIR}/m46_ffmpeg_dll.c")
add_dependencies(ffmpeg ffmpeg_def)
target_link_libraries(ffmpeg PRIVATE libavcodec libavutil)
target_link_options(ffmpeg PRIVATE "LINKER:/DEF:${FFMPEG_DLL_DEF}")
target_include_directories(ffmpeg INTERFACE
    $<BUILD_INTERFACE:${FFMPEG_DIR}>
    $<INSTALL_INTERFACE:${CMAKE_INSTALL_INCLUDEDIR}>
)
set_target_properties(ffmpeg ffmpeg_def PROPERTIES FOLDER "FFmpeg")
'''


if __name__ == '__main__':
    install_overlay('m46_ffmpeg_def.cmake')
    install_overlay('m46_ffmpeg_dll.c')
    # Two edits below keep their anchor text, so patch_bytes alone would repeat them: skip patched files.
    if b'M46 (D-084)' in (SDK / 'thirdparty/CMakeLists.txt').read_bytes():
        print('thirdparty/CMakeLists.txt already patched')
    else:
        patch_bytes('thirdparty/CMakeLists.txt', [
            ('add_library(mspack STATIC\n    ${MSPACK_DIR}/lzxd.c\n)\n',
             '# M46 (D-084): its own DLL, replaceable by the user (LGPL-2.1 s.6b); exports lzxd_*.\n'
             'add_library(mspack SHARED\n    ${MSPACK_DIR}/lzxd.c\n)\n'
             'set_target_properties(mspack PROPERTIES WINDOWS_EXPORT_ALL_SYMBOLS TRUE)\n'),
            ('    VISIBILITY_INLINES_HIDDEN ON\n    FOLDER "FFmpeg")\n',
             '    VISIBILITY_INLINES_HIDDEN ON\n    FOLDER "FFmpeg")\n' + FFMPEG_DLL),
        ])
    patch_bytes('src/audio/CMakeLists.txt', [
        ('    PRIVATE libavcodec libavutil\n',
         '    PRIVATE ffmpeg  # M46 (D-084): ffmpeg.dll, not the static archives\n'),
    ])
    patch_bytes('src/system/CMakeLists.txt', [
        ('    target_link_libraries(rexruntime PRIVATE ws2_32)\n',
         '    # M46 (D-084): xboxkrnl_crypt.cpp calls BCrypt*; bcrypt came only through the static libavutil before.\n'
         '    target_link_libraries(rexruntime PRIVATE ws2_32 bcrypt)\n'),
    ])
    patch_bytes('cmake/rexglue_install.cmake', [
        ('    libavcodec libavutil\n)\n',
         '    libavcodec libavutil\n    ffmpeg  # M46 (D-084): ffmpeg.dll; mspack above is mspack.dll\n)\n'),
    ])
    if b'M46 (D-084)' in (SDK / 'cmake/rexglue_helpers.cmake').read_bytes():
        print('cmake/rexglue_helpers.cmake already patched')
        raise SystemExit(0)
    patch_bytes('cmake/rexglue_helpers.cmake', [
        ('        # FidelityFX is linked PRIVATE by rexui (to avoid propagating DLL\n',
         '        # M46 (D-084): rexruntime links the LGPL DLLs (ffmpeg, mspack)\n'
         '        # PRIVATE, so TARGET_RUNTIME_DLLS misses them: copy them explicitly.\n'
         '        foreach(_lgpl rex::ffmpeg ffmpeg rex::mspack mspack)\n'
         '            if(TARGET ${_lgpl})\n'
         '                get_target_property(_lgpl_type ${_lgpl} TYPE)\n'
         '                if(_lgpl_type STREQUAL "SHARED_LIBRARY")\n'
         '                    add_custom_command(TARGET ${target_name} POST_BUILD\n'
         '                        COMMAND ${CMAKE_COMMAND} -E copy_if_different\n'
         '                            $<TARGET_FILE:${_lgpl}>\n'
         '                            $<TARGET_FILE_DIR:${target_name}>\n'
         '                        VERBATIM\n'
         '                    )\n'
         '                endif()\n'
         '            endif()\n'
         '        endforeach()\n'
         '        # FidelityFX is linked PRIVATE by rexui (to avoid propagating DLL\n'),
    ])
