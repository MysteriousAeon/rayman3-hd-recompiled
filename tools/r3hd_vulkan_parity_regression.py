"""LX-3 / LX-1 regression (E-374): the patched SDK after the chain.

  * the Vulkan IssueDraw carries the D3D12 UVS / M23 block verbatim, once, before the pixel-shader memexport use,
    with both headers included; the D3D12 file still has its block (the Windows behaviour is untouched);
  * threading_posix.cpp carries the LX-1 teardown edits once (the start-wait abandon protocol);
  * both patch scripts are in the build chain, last, thread teardown first.
Reads the SDK copy the build patched (external/rexglue-sdk); fails if the chain was not applied.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import r3hd_thread_teardown_patch as T  # noqa: E402
import r3hd_vulkan_parity_patch as V  # noqa: E402


def main() -> int:
    sdk = ROOT / "external/rexglue-sdk"
    fails = []
    vk = (sdk / V.VULKAN).read_text(encoding="utf-8")
    block = V.shared_block()
    if vk.count(block) != 1:
        fails.append("Vulkan IssueDraw lacks the verbatim D3D12 UVS/M23 block")
    elif vk.index(block) > vk.index(V.ANCHOR) or vk.index(V.ANCHOR) - vk.index(block) != len(block):
        fails.append("the block is not right before the pixel-shader memexport line")
    for inc in ("#include <rex/m23_water_layers.h>", "#include <rex/uvs_lit_scroll.h>",
                "#include <rex/hdl_red_correction.h>"):
        if vk.count(inc) != 1:
            fails.append(f"Vulkan file include {inc}")
    posix = (sdk / T.REL).read_text(encoding="utf-8")
    for _, after in T.EDITS:
        if posix.count(after) != 1:
            fails.append(f"threading_posix.cpp edit missing: {after.strip()[:60]}")
    bat = (ROOT / "tools/build_milestone8.bat").read_text(encoding="utf-8").splitlines()
    chain = [ln.strip() for ln in bat if ln.strip().startswith("python tools\\") and "_patch.py" in ln]
    # D-219: the beam overlay runs after every step whose anchors it must not move; D-220 adds the D3D12
    # display V-Sync step after it (D3D12 presenter files only, no anchor shared with an earlier step).
    # D-221 adds the lock-on colour read overlay (host file read path and one D3D12 mode line only).
    # D-324 adds the controller-motor stop (input / SDL driver files and ReXApp::OnClosing only).
    # D-328 adds the test-only profile handoff prototype (XAM user / input / UI files only).
    # D-345 adds the SDL_DefaultAudioDeviceChanged prev-pointer fix (thirdparty/sdl3/src/audio/SDL_audio.c only).
    # D-346 adds the AudioSystem client-lifetime fix last (include/rex/audio/audio_system.h and src/audio/audio_system.cpp only).
    tail = [c.split("\\")[1].split()[0] for c in chain[-11:]]
    if tail != ["r3hd_thread_teardown_patch.py", "r3hd_vulkan_parity_patch.py", "r3hd_xex_case_patch.py",
                "r3hd_button_prompts_patch.py", "r3hd_beam_runtime_patch.py", "r3hd_display_vsync_patch.py",
                "r3hd_lockon_runtime_patch.py", "r3hd_pad_motors_patch.py", "g6p79_profile_handoff_patch.py",
                "g6p106_sdl_audio_migration_patch.py", "g6p109_audio_client_lifetime_patch.py"]:
        fails.append(f"chain tail {tail}")
    for _, after in V.red_edits():
        if vk.count(after) != 1:
            fails.append("Vulkan red correction edit missing or duplicated")
    print(f"R3HD_VULKAN_PARITY_REGRESSION {'PASS' if not fails else 'FAIL'} block_lines={block.count(chr(10))} {fails}")
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
