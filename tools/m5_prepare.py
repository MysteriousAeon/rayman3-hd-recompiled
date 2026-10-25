"""Install repository-owned host input automation into the ignored host project."""
from m2_prepare import ROOT, W, write_text_if_changed
import shutil
import sys

# Inserted before the function's final restore call by `instrument` (read-only input trace, M5). Also used by
# tools/r3hd_build_step.py to leave this block out of the generated-code digest.
M5_FUNCTION = 'DEFINE_REX_FUNC(sub_822331D8) {'
M5_BLOCK = '''
  static uint32_t previous_buttons = ~0u, previous_lx = ~0u, previous_ly = ~0u, previous_rx = ~0u;
  static uint64_t samples = 0;
  uint32_t controller = ctx.r29.u32;
  uint32_t buttons = REX_LOAD_U16(controller), lx = REX_LOAD_U16(controller + 20), ly = REX_LOAD_U16(controller + 22), rx = REX_LOAD_U16(controller + 24);
  ++samples;
  // M8: the human-playtest profile (R3HD_PLAY) keeps per-input traces out of the log.
  static const bool m8_play = std::getenv("R3HD_PLAY") != nullptr;
  if (!m8_play && (buttons != previous_buttons || lx != previous_lx || ly != previous_ly || rx != previous_rx || (samples & (samples - 1)) == 0)) {
    REXLOG_INFO("M5 consumed function=822331D8 samples={} controller={:08X} buttons={:04X} a={} lx={} ly={} rx={} normalized_lx={} normalized_ly={} normalized_rx={}",
      samples, controller, buttons, REX_LOAD_U8(controller + 4), int16_t(lx), int16_t(ly), int16_t(rx),
      std::bit_cast<float>(REX_LOAD_U32(controller + 28)), std::bit_cast<float>(REX_LOAD_U32(controller + 32)), std::bit_cast<float>(REX_LOAD_U32(controller + 36)));
    previous_buttons = buttons; previous_lx = lx; previous_ly = ly; previous_rx = rx;
  }
'''
if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'instrument':
        # Local executable-derived offsets: 822331D8 stores buttons at r3+0,
        # A at +4, raw sticks +20..26, normalized sticks +28..40.
        # M28: the partition that holds the function depends on codegen's partition assignment (a fresh work
        # tree differs from the developer's, E-151), so it is looked up instead of assumed to be file 87.
        hits = [q for q in sorted((W/'generated/default').glob('r3hd_recomp.*.cpp')) if M5_FUNCTION in q.read_text()]
        assert len(hits) == 1, f'sub_822331D8 found in {len(hits)} partitions'
        p = hits[0]
        text = p.read_text()
        begin = text.index(M5_FUNCTION)
        end = text.find('\nDEFINE_REX_FUNC(', begin + 1)
        end = len(text) if end < 0 else end
        f = text[begin:end]
        if 'M5 consumed' not in f:
            old = '\t__restgprlr_22(ctx, base);'
            assert f.count(old) == 1
            f = f.replace(old, M5_BLOCK + old)
            write_text_if_changed(p, text[:begin] + f + text[end:])
        sys.exit(0)
    shutil.copyfile(ROOT/'tools/m5_host_input.h', W/'src/m5_host_input.h')
    p = W/'src/r3hd_app.h'
    text = (ROOT/'tools/m2_host/r3hd_app.h').read_text()
    text = text.replace('#include "m2_trace.h"', '#include "m2_trace.h"\n#include "m5_host_input.h"')
    text = text.replace(' public:', '  M5HostInput m5_input_;\n public:')
    text = text.replace('REXLOG_INFO("M2 launch_prepared");', 'REXLOG_INFO("M2 launch_prepared"); m5_input_.Start(window());')
    # D-094/D-096: preserve the host's icon/presence shutdown in the replayed project.
    shutdown = '  void OnShutdown() override {'
    assert text.count(shutdown) == 1, 'host must own exactly one shutdown method'
    text = text.replace(shutdown, shutdown + '\n    m5_input_.Stop();')
    write_text_if_changed(p, text)
    p = W/'CMakeLists.txt'
    mark = '\n# --- Milestone 5 instrumentation ---\n'
    text = p.read_text().split(mark)[0] + mark + '''add_custom_target(m5_instrument
 COMMAND ${Python3_EXECUTABLE} "${CMAKE_CURRENT_SOURCE_DIR}/../../../tools/m5_prepare.py" instrument)
add_dependencies(m5_instrument m2_instrument)
add_dependencies(r3hd_recomp m5_instrument)
'''
    write_text_if_changed(p, text)
