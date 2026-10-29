"""Replay after M6 at the same pin: human-playtest diagnostic profile (R3HD_PLAY).

Observational only. With R3HD_PLAY set, a normal visible launch keeps the M2..M6 census
(imports, file opens, swaps, faults) but writes no game-derived dumps into the working
directory (except explicit private Combo event captures) and no per-key / per-stick-sample
trace into the log. Emulation semantics, the
hidden XAM test source and the capture policy of hidden runs are unchanged.
"""
from m3_runtime_patch import SDK


def patch_once(rel, edits):
    path = SDK / rel
    text = path.read_text()
    for before, after in edits:
        if after in text:
            continue
        assert text.count(before) == 1, (rel, before[:60], text.count(before))
        text = text.replace(before, after)
    if path.read_text() != text:
        path.write_text(text)
        print('patched', rel)


if __name__ == '__main__':
    patch_once('include/rex/m3_gpu_trace.h', [
        # No shader microcode dumps and no fixed-swap frame captures in a playtest session.
        ('  if (FILE* f = std::getenv("R3HD_NONINTRUSIVE") ? nullptr : std::fopen(name, "wb")) {',
         '  if (FILE* f = (std::getenv("R3HD_NONINTRUSIVE") || std::getenv("R3HD_PLAY")) ? nullptr : std::fopen(name, "wb")) {'),
        ('  if (std::getenv("R3HD_NONINTRUSIVE")) return m6frame::CaptureAt(swap);',
         '  if (std::getenv("R3HD_NONINTRUSIVE")) return m6frame::CaptureAt(swap);\n'
         '  const char* combo_capture = std::getenv("R3HD_TEST_COMBO_CAPTURE");\n'
         '  if (std::getenv("R3HD_PLAY") && combo_capture && !std::strcmp(combo_capture, "1") &&\n'
         '      std::getenv("R3HD_FRAME_REQUEST")) return m6frame::CaptureAt(swap);\n'
         '  if (std::getenv("R3HD_PLAY")) return false;'),
    ])
    patch_once('src/kernel/xam/xam_input.cpp', [
        # A physical stick changes on almost every poll; the per-change trace is test evidence, not play data.
        ('    REXKRNL_INFO("M4 input_state user={} api=XamInputGetState',
         '    static const bool m8_play = std::getenv("R3HD_PLAY") != nullptr;\n'
         '    if (!m8_play) REXKRNL_INFO("M4 input_state user={} api=XamInputGetState'),
    ])
    patch_once('src/input/mnk/mnk_input_driver.cpp', [
        # Never record a person's keystrokes in a playtest log.
        ('  REXLOG_INFO("M4 host_key down={} vk={} focus={} active={}", true,',
         '  if (!std::getenv("R3HD_PLAY")) REXLOG_INFO("M4 host_key down={} vk={} focus={} active={}", true,'),
        ('  REXLOG_INFO("M4 host_key down={} vk={} focus={} active={}", false,',
         '  if (!std::getenv("R3HD_PLAY")) REXLOG_INFO("M4 host_key down={} vk={} focus={} active={}", false,'),
    ])
