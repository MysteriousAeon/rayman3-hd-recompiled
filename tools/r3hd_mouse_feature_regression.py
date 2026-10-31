"""D-138 regression (in the build, after the runtime is installed): native mouse controls.

1. The patch is in the SDK tree as tools/r3hd_mouse_patch.py writes it, last in the chain: mouse buttons keep their own
   state (no mouse virtual key reaches the keyboard's key state outside a poll), the camera counts only relative
   motion of a locked pointer and never warps the cursor, MB4 / MB5 parse, VdSwap publishes the guest context.
2. The installed header equals tools/r3hd_mouse.h.
3. The real driver (tools/r3hd_mouse_driver_test.cpp, window-less, against the built runtime) passes every case.
4. --run RUN...: a hidden run's log names its mouse configuration and never captured the pointer.
No game is started here; tools/r3hd_mouse_game.py is the in-game proof.
    python tools/r3hd_mouse_feature_regression.py [--run RUN...]
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SDK = ROOT / "external" / "rexglue-sdk"
RUNS = ROOT / "private" / "work" / "m6_runs"
DRIVER_CASES = 55
results = []


def check(label, ok, detail=""):
    results.append(ok)
    print(("PASS " if ok else "FAIL ") + label + ("" if ok or not detail else f" ({detail})"))


def source_checks():
    driver = (SDK / "src/input/mnk/mnk_input_driver.cpp").read_text()
    header = (SDK / "include/rex/input/mnk/mnk_input_driver.h").read_text()
    keybinds = (SDK / "src/ui/keybinds.cpp").read_text()
    video = (SDK / "src/kernel/xboxkrnl/xboxkrnl_video.cpp").read_text()
    chain = (ROOT / "tools/build_milestone8.bat").read_text()
    check("driver: mnk_mouse_buttons defined once, default off",
          driver.count('REXCVAR_DEFINE_BOOL(mnk_mouse_buttons, false,') == 1)
    check("driver: mouse down / up use the mouse's own state, never SetKeyState",
          "mouse_buttons_.Down(" in driver and "mouse_buttons_.Up(" in driver
          and not re.search(r"SetKeyState\(static_cast<uint16_t>\(VirtualKey::k[LRM]Button\)", driver))
    check("driver: a release is taken with the driver off (no IsEnabled test in OnMouseUp)",
          re.search(r"void MnkInputDriver::OnMouseUp\(rex::ui::MouseEvent& e\) \{(?:(?!\n\}\n).)*?IsEnabled",
                    driver, re.S) is None)
    poll = driver[driver.index("X_RESULT MnkInputDriver::GetDeviceState("):driver.index("X_RESULT MnkInputDriver::SetDeviceVibration(")]
    set_at, clear_at = poll.find("key_down_[r3hd_mouse::kVk[i]] = ((mouse_pressed"), poll.find("key_down_[r3hd_mouse::kVk[i]] = false;")
    check("driver: mouse keys are set for the poll's bindings and cleared before it returns",
          0 < set_at < poll.find("IsBindPressed(") < clear_at < poll.find("auto clamp16"))
    check("driver: buttons and camera wait for gameplay", poll.count("mouse_gameplay") >= 3
          and "const uint32_t context = r3hd_mouse::Context();" in driver and "r3hd_mouse::Gameplay(context);" in driver)
    check("driver: no cursor warp, no absolute-position camera",
          "RecenterCursorFromUIThread(x, y);" not in driver and "mouse_dx_ += float(x - prev_mouse_x_);" not in driver)
    check("driver: focus loss clears the mouse; a failed pointer lock turns the camera off without a fallback",
          "mouse_buttons_.Clear();" in driver and "mouse_lock_failed_ = true;" in driver
          and "falls back to recentering" not in driver)
    check("driver: a hidden run (R3HD_NONINTRUSIVE) never requests a capture; a press is stamped with its context",
          'if (std::getenv("R3HD_NONINTRUSIVE")) should_capture = false;' in driver
          and "mouse_buttons_.DisarmOlder(mouse_context);" in driver and "live, context);" in driver)
    check("driver: one configuration line at Setup", driver.count('"R3HD mouse camera={} buttons={} sensitivity={}') == 1)
    check("header: mouse members and test hooks, relative mode atomic",
          "r3hd_mouse::Buttons mouse_buttons_;" in header and "void TestMouseMotion(float dx, float dy);" in header
          and "std::atomic<bool> relative_mouse_mode_{false};" in header and header.count("#include <rex/r3hd_mouse.h>") == 1)
    check("keybinds: MB4 / MB5 are the side buttons",
          '{"MB4", VirtualKey::kXButton1}' in keybinds and '{"MB5", VirtualKey::kXButton2}' in keybinds)
    check("VdSwap: the guest context is published once, read-only",
          video.count("r3hd_mouse::PublishGameplay(") == 1 and video.count("#include <rex/r3hd_mouse.h>") == 1
          and video.index("r3hd_mouse::PublishGameplay(") > video.index("void VdSwap_entry(")
          and "Store" not in video[video.index("D-138: the mouse's guest context"):video.index("r3hd_mouse::PublishGameplay(")])
    check("VdSwap (D-145): the Look Mode flag and the level are published once, read-only, in gameplay only",
          video.count("r3hd_mouse::PublishLook(") == 1 and video.count("r3hd_mouse::PublishLevel(") == 1
          and "const bool look = gameplay && membase[0x82C07D5Cu] == 1 && membase[0x82C5C770u] == 0xFF;" in video)
    look_at, cam_at = poll.find("mouse_look_.Poll("), poll.find("mouse_camera_.Poll(")
    check("driver (D-145): in Look Mode the mouse drives the left stick, otherwise the D-138 camera; each drops the other",
          0 < look_at < cam_at and "const bool look_mode = r3hd_mouse::LookMode() && mouse_gameplay;" in poll
          and "if (look_mode != mouse_look_mode_) {" in poll
          and poll.count("mouse_camera_.Drop();") >= 2 and "mouse_look_.Drop();" in poll
          and poll.index("int32_t lx = 0;") < look_at and poll.index("m49walk::Apply(") < look_at)
    check("driver (D-145): focus loss, capture changes and inactive polls drop the Look Mode motion",
          driver.count("mouse_look_.Drop();  // D-145") >= 4)
    installed = SDK / "include/rex/r3hd_mouse.h"
    check("installed r3hd_mouse.h equals tools/r3hd_mouse.h",
          installed.is_file() and installed.read_bytes() == (ROOT / "tools/r3hd_mouse.h").read_bytes())
    padmap_at, mouse_at = chain.find("python tools\\r3hd_padmap_patch.py"), chain.find("python tools\\r3hd_mouse_patch.py")
    check("build: the mouse patch is replayed last, after the controller map",
          0 < padmap_at < mouse_at < chain.find("python tools\\m2_prepare.py"))


def driver_test():
    done = subprocess.run(["cmd", "/d", "/c", str(ROOT / "tools/devenv.bat"), str(ROOT / "tools/build_mouse_driver_test.bat")],
                          cwd=ROOT, capture_output=True, text=True, timeout=300)
    out = done.stdout + done.stderr
    (ROOT / "private/work/mouse").mkdir(parents=True, exist_ok=True)
    (ROOT / "private/work/mouse/driver_test.log").write_text(out, encoding="utf-8")
    m = re.search(r"R3HD_MOUSE_DRIVER (PASS|FAIL) (\d+)/(\d+)", out)
    check(f"real driver: R3HD_MOUSE_DRIVER PASS {DRIVER_CASES}/{DRIVER_CASES}",
          done.returncode == 0 and bool(m) and m[1] == "PASS" and int(m[2]) == int(m[3]) == DRIVER_CASES,
          (m[0] if m else out[-300:]))


def run_checks(names):
    for name in names:
        d = RUNS / name if not Path(name).is_dir() else Path(name)
        text = "\n".join(p.read_text(errors="replace") for p in sorted(d.glob("runtime*.log")))
        lines = re.findall(r"R3HD mouse camera=(\w+) buttons=(\w+) sensitivity=\S+ test_instance=(\w+)", text)
        check(f"{d.name}: the mouse configuration is logged", bool(lines))
        check(f"{d.name}: a hidden run never captures the pointer", "R3HD mouse capture=" not in text)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", nargs="*", default=[])
    a = ap.parse_args()
    if a.run:
        run_checks(a.run)
    else:
        source_checks()
        driver_test()
    print(f"R3HD_MOUSE_REGRESSION {'PASS' if all(results) else 'FAIL'} {sum(results)}/{len(results)}")
    sys.exit(0 if all(results) else 1)
