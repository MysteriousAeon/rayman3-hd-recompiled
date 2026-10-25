"""Build-time regression for D-034: input drivers are detached before the window is destroyed.

Static check of the patched SDK sources (no game process). It guards the order of operations in the shutdown
path, which the next SDK patch or pin change could silently undo. The behavioural regression is the hidden run
    python tools/m9_license_run.py RUN config/m11/menu_exit.txt --license-mask 1 --seconds 120 --play
which selects the title's own Exit Game and passes only when the process ends with exit code 0.
"""
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
SDK = ROOT / 'external/rexglue-sdk'


def body(text, signature):
    """Text of the function starting at `signature`, by brace matching."""
    start = text.index(signature)
    i = text.index('{', start)
    depth = 0
    for j in range(i, len(text)):
        if text[j] == '{':
            depth += 1
        elif text[j] == '}':
            depth -= 1
            if depth == 0:
                return text[i:j + 1]
    raise ValueError(signature)


def main():
    checks = failures = 0

    def check(ok, what):
        nonlocal checks, failures
        checks += 1
        if not ok:
            failures += 1
            print('FAIL', what)

    app = (SDK / 'src/ui/rex_app.cpp').read_text()
    destroy = body(app, 'void ReXApp::OnDestroy()')
    detach = destroy.find('->AttachWindow(nullptr)')
    window = destroy.find('window_.reset()')
    runtime = destroy.find('runtime_.reset()')
    check(window >= 0 and runtime >= 0, 'OnDestroy releases window and runtime')
    check(destroy.count('window_.reset()') == 1 and destroy.count('runtime_.reset()') == 1, 'single release each')
    check(detach >= 0, 'OnDestroy detaches the input system from the window')
    check(0 <= detach < window, 'detach precedes window destruction')
    check(destroy.find('module_thread_.join()') < detach, 'detach follows the guest module thread join')
    check('exit(' not in destroy and 'TerminateProcess' not in destroy and '__try' not in destroy,
          'no early process exit or exception guard in OnDestroy')

    system = (SDK / 'src/input/input_system.cpp').read_text()
    attach = body(system, 'void InputSystem::AttachWindow(')
    check('window_ = window' in attach, 'AttachWindow records the window (null included)')
    check(re.search(r'driver->OnWindowAvailable\(window\)', attach) is not None, 'AttachWindow notifies every driver')
    shutdown = body(system, 'void InputSystem::Shutdown()')
    check('drivers_.clear()' in shutdown, 'Shutdown still destroys the drivers')

    mnk = (SDK / 'src/input/mnk/mnk_input_driver.cpp').read_text()
    available = body(mnk, 'void MnkInputDriver::OnWindowAvailable(')
    null_at = available.find('if (!window)')
    check(null_at >= 0 and 'DetachFromWindow();' in available[null_at:available.find('}', null_at)],
          'keyboard driver detaches on a null window')
    check(0 <= null_at < available.find('AddInputListener'), 'null check precedes the attach')
    detach_body = body(mnk, 'void MnkInputDriver::DetachFromWindow()')
    early = detach_body.find('if (!window)')
    check(0 <= early < detach_body.find('CallInUIThreadSynchronous'), 'detach is a no-op once detached')
    check('attached_window_ = nullptr' in detach_body, 'detach clears the window pointer')
    check('RemoveInputListener(this)' in detach_body and 'RemoveListener(this)' in detach_body,
          'detach removes both listener registrations')
    destructor = body(mnk, 'MnkInputDriver::~MnkInputDriver()')
    check('DetachFromWindow();' in destructor, 'destructor still detaches (driver destroyed before the window)')

    print(f'm11 shutdown regression: {checks} checks, {failures} failures')
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
