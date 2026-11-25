#!/usr/bin/env python3
"""G6-P137 (E-618): read-only static lock-order and teardown audit for pinned SDL3 WASAPI & ReXGlue audio."""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SDK = ROOT / "external" / "rexglue-sdk"
SDL = SDK / "thirdparty" / "sdl3"

EXPECTED_SDK_PIN = "c94f5ebdcb3c9d1a460ca48e04f9758448f8d518"
EXPECTED_SDL_PIN = "8bf3b7215ad9fc3deb583c6a3a37c6c67f2e24e4"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def extract_fn(text: str, start_pat: str) -> str:
    m1 = re.search(start_pat, text, re.MULTILINE)
    if not m1:
        return ""
    m2 = re.search(r"^\}", text[m1.start():], re.MULTILINE)
    if not m2:
        return text[m1.start():]
    return text[m1.start(): m1.start() + m2.end()]


def analyze_wasapi_edges(wasapi_c: str, audio_c: str) -> dict:
    """Extract key synchronization edges for H4, C1 (open vs default-change), and C2 (recover vs default-change)."""
    wait_fn = extract_fn(wasapi_c, r"^static bool WASAPI_WaitDevice\(")
    recover_if_lost = extract_fn(wasapi_c, r"^static bool RecoverWasapiIfLost\(")
    recover_dev = extract_fn(wasapi_c, r"^static bool RecoverWasapiDevice\(")
    activate_dev = extract_fn(wasapi_c, r"^static bool ActivateWasapiDevice\(")
    mgmt_activate = extract_fn(wasapi_c, r"^static bool mgmtthrtask_ActivateDevice\(")
    prep_dev = extract_fn(wasapi_c, r"^static bool mgmtthrtask_PrepDevice\(")
    open_wasapi = extract_fn(wasapi_c, r"^static bool WASAPI_OpenDevice\(")
    mgmt_default = extract_fn(wasapi_c, r"^static bool mgmtthrtask_DefaultAudioDeviceChanged\(")
    proxy_fn = extract_fn(wasapi_c, r"^bool WASAPI_ProxyToManagementThread\(")

    open_phys = extract_fn(audio_c, r"^static bool OpenPhysicalAudioDevice\([^\r\n]+\)\r?\n\{")
    close_phys = extract_fn(audio_c, r"^static void ClosePhysicalAudioDevice\([^\r\n]+\)\r?\n\{")
    default_changed = extract_fn(audio_c, r"^void SDL_DefaultAudioDeviceChanged\(")
    fmt_changed_locked = extract_fn(audio_c, r"^bool SDL_AudioDeviceFormatChangedAlreadyLocked\(")

    return {
        # H4: unlocked format change during recovery + shared open path
        "h4_recover_calls_activate": (
            "RecoverWasapiIfLost(device)" in wait_fn
            and "RecoverWasapiDevice(device)" in recover_if_lost
            and "ActivateWasapiDevice(device)" in recover_dev
            and "SDL_LockMutex(device->lock)" not in wait_fn
            and "SDL_LockMutex(device->lock)" not in recover_dev
        ),
        "h4_prep_calls_already_locked": (
            "WASAPI_PrepDevice(device)" in mgmt_activate
            and "SDL_AudioDeviceFormatChangedAlreadyLocked(device, &newspec, new_sample_frames)" in prep_dev
            and "SDL_LockMutex(device->lock)" not in prep_dev
        ),
        "h4_already_locked_mutates_device": (
            "UpdateAudioStreamFormatsPhysical(device);" in fmt_changed_locked
            and "for (SDL_LogicalAudioDevice *logdev = device->logical_devices;" in fmt_changed_locked
            and "SDL_aligned_free(device->work_buffer);" in fmt_changed_locked
        ),
        "h4_open_shares_activate_under_lock": (
            "current_audio.impl.OpenDevice(device)" in open_phys
            and "SDL_UnlockMutex(device->lock)" not in open_phys
            and "ActivateWasapiDevice(device)" in open_wasapi
        ),
        # C1: OpenPhysicalAudioDevice (holds device->lock, waits on mgmt) vs mgmtthrtask_DefaultAudioDeviceChanged (acquires device->lock)
        "c1_sync_proxy_blocks_infinite": (
            "WASAPI_ProxyToManagementThread(mgmtthrtask_ActivateDevice, device, &rc)" in activate_dev
            and "SDL_WaitSemaphore(pending->task_complete_sem);" in proxy_fn
        ),
        "c1_mgmt_default_locks_devices": (
            "SDL_DefaultAudioDeviceChanged(device);" in mgmt_default
            and "ObtainPhysicalAudioDeviceObj(new_default_device);" in default_changed
            and "ObtainPhysicalAudioDevice(current_devid);" in default_changed
        ),
        # C2: PlaybackAudioThread (in RecoverWasapiDevice -> SDL_WaitSemaphore) vs SDLWASAPIMgmt (in DefaultAudioDeviceChanged -> ClosePhysicalAudioDevice -> SDL_WaitThread)
        "c2_mgmt_default_closes_old_physical": (
            "ClosePhysicalAudioDevice(current_default_device);" in default_changed
            and "SDL_UnlockMutex(device->lock);" in close_phys
            and "SDL_WaitThread(device->thread, NULL);" in close_phys
        ),
    }


def run_selftest() -> bool:
    fake_wasapi = """
bool WASAPI_ProxyToManagementThread(ManagementThreadTask task, void *userdata, bool *wait_on_result)
{
    SDL_WaitSemaphore(pending->task_complete_sem);
    return true;
}
static bool mgmtthrtask_DefaultAudioDeviceChanged(void *userdata)
{
    SDL_DefaultAudioDeviceChanged(device);
    return true;
}
static bool mgmtthrtask_ActivateDevice(void *userdata)
{
    WASAPI_PrepDevice(device);
    return true;
}
static bool ActivateWasapiDevice(SDL_AudioDevice *device)
{
    return WASAPI_ProxyToManagementThread(mgmtthrtask_ActivateDevice, device, &rc);
}
static bool RecoverWasapiDevice(SDL_AudioDevice *device)
{
    return ActivateWasapiDevice(device);
}
static bool RecoverWasapiIfLost(SDL_AudioDevice *device)
{
    return RecoverWasapiDevice(device);
}
static bool WASAPI_WaitDevice(SDL_AudioDevice *device)
{
    while (RecoverWasapiIfLost(device)) {}
    return true;
}
static bool mgmtthrtask_PrepDevice(void *userdata)
{
    return SDL_AudioDeviceFormatChangedAlreadyLocked(device, &newspec, new_sample_frames);
}
static bool WASAPI_OpenDevice(SDL_AudioDevice *device)
{
    return ActivateWasapiDevice(device);
}
"""
    fake_audio = """
static void ClosePhysicalAudioDevice(SDL_AudioDevice *device)
{
    SDL_UnlockMutex(device->lock);
    SDL_WaitThread(device->thread, NULL);
}
static bool OpenPhysicalAudioDevice(SDL_AudioDevice *device, const SDL_AudioSpec *inspec)
{
    return current_audio.impl.OpenDevice(device);
}
void SDL_DefaultAudioDeviceChanged(SDL_AudioDevice *new_default_device)
{
    ObtainPhysicalAudioDeviceObj(new_default_device);
    ObtainPhysicalAudioDevice(current_devid);
    ClosePhysicalAudioDevice(current_default_device);
}
bool SDL_AudioDeviceFormatChangedAlreadyLocked(SDL_AudioDevice *device, const SDL_AudioSpec *newspec, int new_sample_frames)
{
    UpdateAudioStreamFormatsPhysical(device);
    SDL_aligned_free(device->work_buffer);
    for (SDL_LogicalAudioDevice *logdev = device->logical_devices; logdev; logdev = logdev->next) {}
    return true;
}
"""
    pos = analyze_wasapi_edges(fake_wasapi, fake_audio)
    neg = analyze_wasapi_edges(
        fake_wasapi.replace("SDL_AudioDeviceFormatChangedAlreadyLocked", "SDL_AudioDeviceFormatChanged"),
        fake_audio,
    )
    empty = analyze_wasapi_edges("", "")
    checks = {
        "selftest positive synthetic detects all 7 WASAPI lock/wait edges": all(pos.values()),
        "selftest mutated PrepDevice clears h4_prep_calls_already_locked": not neg["h4_prep_calls_already_locked"],
        "selftest empty input rejects all edges": not any(empty.values()),
    }
    ok = all(checks.values())
    for k, v in checks.items():
        print(f"{'PASS' if v else 'FAIL'} {k}")
    print(f"G6P137_SELFTEST {'PASS' if ok else 'FAIL'} {sum(checks.values())}/{len(checks)}")
    return ok


def main() -> int:
    if "--selftest" in sys.argv[1:]:
        return 0 if run_selftest() else 1

    results = {}

    def check(name: str, cond: bool) -> None:
        results[name] = bool(cond)

    sdk_head = subprocess.check_output(["git", "-C", str(SDK), "rev-parse", "HEAD"], text=True).strip()
    sdl_head = subprocess.check_output(["git", "-C", str(SDL), "rev-parse", "HEAD"], text=True).strip()
    check("ReXGlue SDK pin matches c94f5eb", sdk_head == EXPECTED_SDK_PIN)
    check("SDL3 pin matches 8bf3b72", sdl_head == EXPECTED_SDL_PIN)

    wasapi_status = subprocess.check_output(
        ["git", "-C", str(SDL), "status", "--porcelain", "src/audio/wasapi/SDL_wasapi.c"],
        text=True,
    ).strip()
    check("SDL_wasapi.c is unmodified vs pinned 8bf3b72", wasapi_status == "")

    wasapi_c = read_text(SDL / "src" / "audio" / "wasapi" / "SDL_wasapi.c")
    wasapi_h = read_text(SDL / "src" / "audio" / "wasapi" / "SDL_wasapi.h")
    audio_c = read_text(SDL / "src" / "audio" / "SDL_audio.c")

    # Verify exact line 843 in SDL_wasapi.c
    wasapi_lines = wasapi_c.splitlines()
    check(
        "SDL_wasapi.c:843 is SDL_AudioDeviceFormatChangedAlreadyLocked",
        len(wasapi_lines) >= 843 and "SDL_AudioDeviceFormatChangedAlreadyLocked(device, &newspec, new_sample_frames)" in wasapi_lines[842],
    )
    check(
        "SDL_wasapi.h documents lock-held synchronous proxy deadlock warning",
        "if you are holding the device lock and proxy to the management thread with wait_until_complete" in wasapi_h,
    )

    edges = analyze_wasapi_edges(wasapi_c, audio_c)
    for k, v in edges.items():
        check(f"WASAPI/SDL edge verified: {k}", v)

    # Verify ReXGlue AudioSystem & SDLAudioDriver teardown/lock invariants (clean side)
    audio_sys = read_text(SDK / "src" / "audio" / "audio_system.cpp")
    sdl_drv = read_text(SDK / "src" / "audio" / "sdl" / "sdl_audio_driver.cpp")
    rex_app = read_text(SDK / "src" / "ui" / "rex_app.cpp")

    shutdown_fn = extract_fn(audio_sys, r"^void AudioSystem::Shutdown\(\)")
    submit_fn = extract_fn(sdl_drv, r"^void SDLAudioDriver::SubmitFrame\(")
    drv_shutdown = extract_fn(sdl_drv, r"^void SDLAudioDriver::Shutdown\(\)")
    sdl_cb = extract_fn(sdl_drv, r"^void SDLAudioDriver::SDLCallback\(")
    on_closing = extract_fn(rex_app, r"^void ReXApp::OnClosing\(")

    check(
        "AudioSystem::Shutdown joins/terminates worker_thread_ before acquiring global_critical_region_",
        0 < shutdown_fn.find("worker_thread_.reset()") < shutdown_fn.find("global_critical_region_.Acquire()"),
    )
    check(
        "SDLAudioDriver::SubmitFrame makes zero SDL calls under frames_mutex_/global_critical_region_",
        "SDL_" not in submit_fn,
    )
    check(
        "SDLAudioDriver::SDLCallback never acquires global_critical_region_",
        "global_critical_region_" not in sdl_cb,
    )
    check(
        "SDLAudioDriver::Shutdown destroys sdl_stream_ before SDL_QuitSubSystem and buffer deletion",
        0 < drv_shutdown.find("SDL_DestroyAudioStream(sdl_stream_)")
        < drv_shutdown.find("SDL_QuitSubSystem(SDL_INIT_AUDIO)")
        < drv_shutdown.find("frames_mutex_"),
    )
    check(
        "ReXApp::OnClosing hard-exits via std::_Exit(0) bypassing AudioSystem::Shutdown/SDL_QuitAudio",
        "std::_Exit(0);" in on_closing,
    )

    passed = sum(1 for v in results.values() if v)
    total = len(results)
    for k, v in results.items():
        print(f"{'PASS' if v else 'FAIL'} {k}")
    print(f"G6P137_WASAPI_LOCK_ORDER_AUDIT {'PASS' if passed == total else 'FAIL'} {passed}/{total}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
