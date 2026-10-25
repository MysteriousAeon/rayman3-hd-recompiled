"""Replay after M10 at the same pin: shutdown-order fix (D-034) and frame-pacing statistics (D-035).

1. Detach the input drivers before the window is destroyed.

Second human playtest: the title's own "Exit Game" ended the process with 0xC0000374. `ReXApp::OnDestroy`
destroys the window and then the runtime; `~MnkInputDriver` (reached from `Runtime::Shutdown`) still held the
window pointer and erased its listener entry from the destroyed window's containers: a use-after-free, reported
by the heap as corruption. A window close (Alt+F4, timed test exit) sends `OnClosing` first, which detaches the
driver, so only a guest-initiated exit (`XamLoaderLaunchTitle`) took the faulty order.

The fix gives the guest-exit path the detach the close path already has: the application tells the input system
the window is going away while it still exists, and the keyboard driver treats "no window" as a detach. No
destructor is skipped, nothing is caught or suppressed, and the close path is unchanged (its detach has already
cleared the pointer, so the second call returns at once).

2. `tools/m11_frame_pacing.h`: interval statistics for guest swaps and host presents, one log line per 600.
Observational only; it does not wait and does not change what is presented or when.
"""
import shutil

from m3_runtime_patch import ROOT, SDK
from m8_runtime_patch import patch_once

if __name__ == '__main__':
    # Frame-pacing statistics (observational): one log line per 600 guest swaps / host presents.
    target = SDK / 'include/rex/m11_frame_pacing.h'
    source = ROOT / 'tools/m11_frame_pacing.h'
    if not target.exists() or target.read_bytes() != source.read_bytes():
        shutil.copyfile(source, target)
        print('installed', target.name)
    patch_once('include/rex/m3_gpu_trace.h', [
        ('#include <rex/ui/presenter.h>\n', '#include <rex/ui/presenter.h>\n#include <rex/m11_frame_pacing.h>\n'),
        ('  uint64_t n = ++c.swaps;\n', '  uint64_t n = ++c.swaps;\n  m11pace::GuestSwap();\n'),
    ])
    patch_once('src/ui/d3d12/d3d12_presenter.cpp', [
        ('#include <rex/logging.h>\n#include <atomic>\n',
         '#include <rex/logging.h>\n#include <atomic>\n#include <rex/m11_frame_pacing.h>\n'),
        ('    uint64_t m3_n = ++m3_presents;\n', '    uint64_t m3_n = ++m3_presents;\n    m11pace::HostPresent();\n'),
    ])
    patch_once('src/input/mnk/mnk_input_driver.cpp', [
        ('void MnkInputDriver::OnWindowAvailable(rex::ui::Window* window) {\n'
         '  if (window) {',
         'void MnkInputDriver::OnWindowAvailable(rex::ui::Window* window) {\n'
         '  // M11 (D-034): a null window means the window is about to be destroyed; let go of it now.\n'
         '  if (!window) {\n'
         '    DetachFromWindow();\n'
         '    return;\n'
         '  }\n'
         '  if (window) {'),
    ])
    patch_once('src/ui/rex_app.cpp', [
        ('    window_->RemoveListener(this);\n'
         '  }\n'
         '  window_.reset();\n'
         '  runtime_.reset();',
         '    window_->RemoveListener(this);\n'
         '  }\n'
         '  // M11 (D-034): the runtime outlives the window here, and its input drivers hold the window pointer.\n'
         '  // A guest-initiated exit sends no OnClosing, so detach them while the window still exists.\n'
         '  if (window_ && runtime_ && runtime_->input_system()) {\n'
         '    static_cast<rex::input::InputSystem*>(runtime_->input_system())->AttachWindow(nullptr);\n'
         '  }\n'
         '  window_.reset();\n'
         '  runtime_.reset();'),
    ])
