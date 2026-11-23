#!/usr/bin/env python3
"""G6-P105 (E-588): read-only static audit of SDL 3.5.0 / ReXGlue XMA / DualSense audio lifecycle facts."""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SDK = ROOT / "external" / "rexglue-sdk"
SDL = SDK / "thirdparty" / "sdl3"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def extract_block(text: str, start_pat: str, end_pat: str) -> str:
    m1 = re.search(start_pat, text, re.MULTILINE)
    if not m1:
        return ""
    m2 = re.search(end_pat, text[m1.start():], re.MULTILINE)
    if not m2:
        return text[m1.start():]
    return text[m1.start(): m1.start() + m2.end()]


def audit_sdl_default_migration(sdl_audio_c: str) -> dict:
    """Check whether SDL_DefaultAudioDeviceChanged updates new_default_device->logical_devices->prev."""
    mig = extract_block(
        sdl_audio_c,
        r"if \(needs_migration\)",
        r"SDL_UnlockRWLock\(current_audio\.subsystem_rwlock\);",
    )
    open_dev = extract_block(
        sdl_audio_c,
        r"SDL_AudioDeviceID SDL_OpenAudioDevice\(",
        r"return result;",
    )
    destroy_dev = extract_block(
        sdl_audio_c,
        r"static void DestroyLogicalAudioDevice\(",
        r"SDL_free\(logdev\);",
    )
    iterate = extract_block(
        sdl_audio_c,
        r"bool SDL_PlaybackAudioThreadIterate\(",
        r"return true;",
    )
    mig_prepends = (
        "logdev->prev = NULL;" in mig
        and "logdev->next = new_default_device->logical_devices;" in mig
        and "new_default_device->logical_devices = logdev;" in mig
    )
    mig_sets_old_head_prev = "new_default_device->logical_devices->prev = logdev;" in mig
    open_sets_old_head_prev = "device->logical_devices->prev = logdev;" in open_dev
    destroy_uses_prev = (
        "if (logdev->prev)" in destroy_dev
        and "logdev->prev->next = logdev->next;" in destroy_dev
        and "SDL_free(logdev);" in destroy_dev
    )
    iterate_walks_paused = (
        "for (SDL_LogicalAudioDevice *logdev = device->logical_devices; logdev; logdev = logdev->next)" in iterate
        and "SDL_GetAtomicInt(&logdev->paused)" in iterate
    )
    return {
        "mig_prepends": mig_prepends,
        "mig_missing_prev_fix": mig_prepends and not mig_sets_old_head_prev,
        "open_sets_old_head_prev": open_sets_old_head_prev,
        "destroy_uses_prev": destroy_uses_prev,
        "iterate_walks_paused": iterate_walks_paused,
    }


def run_selftest() -> bool:
    """Negative controls: mutated SDL_audio.c with the prev-pointer fix must clear mig_missing_prev_fix."""
    fake_buggy = """
    if (needs_migration) {
        logdev->physical_device = new_default_device;
        logdev->prev = NULL;
        logdev->next = new_default_device->logical_devices;
        new_default_device->logical_devices = logdev;
        SDL_UnlockRWLock(current_audio.subsystem_rwlock);
    }
    """
    fake_fixed = fake_buggy.replace(
        "new_default_device->logical_devices = logdev;",
        "if (new_default_device->logical_devices) { new_default_device->logical_devices->prev = logdev; }\n"
        "        new_default_device->logical_devices = logdev;",
    )
    r_bug = audit_sdl_default_migration(fake_buggy)
    r_fix = audit_sdl_default_migration(fake_fixed)
    checks = {
        "selftest detects missing prev assignment": r_bug["mig_missing_prev_fix"] is True,
        "selftest clears defect when prev assignment present": r_fix["mig_missing_prev_fix"] is False,
        "selftest detects empty input as non-matching": audit_sdl_default_migration("")["mig_prepends"] is False,
    }
    ok = all(checks.values())
    for k, v in checks.items():
        print(f"{'PASS' if v else 'FAIL'} {k}")
    print(f"G6P105_SELFTEST {'PASS' if ok else 'FAIL'} {sum(checks.values())}/{len(checks)}")
    return ok


def main() -> int:
    if "--selftest" in sys.argv[1:]:
        return 0 if run_selftest() else 1

    results = {}

    def check(name: str, cond: bool) -> None:
        results[name] = bool(cond)

    rev_h = read_text(SDK / "out" / "install" / "win-amd64" / "include" / "SDL3" / "SDL_revision.h")
    check("pinned SDL revision is SDL-3.5.0-8bf3b72", "SDL-3.5.0-8bf3b72" in rev_h)

    unpatched_sdl_audio_c = subprocess.check_output(
        ["git", "-C", str(SDL), "show", "8bf3b7215ad9fc3deb583c6a3a37c6c67f2e24e4:src/audio/SDL_audio.c"],
        text=True,
        errors="replace",
    )
    mig_unpatched = audit_sdl_default_migration(unpatched_sdl_audio_c)
    check("pinned unpatched SDL_DefaultAudioDeviceChanged omits new_default_device->logical_devices->prev = logdev (negative control)",
          mig_unpatched["mig_missing_prev_fix"])

    sdl_audio_c = read_text(SDL / "src" / "audio" / "SDL_audio.c")
    mig = audit_sdl_default_migration(sdl_audio_c)
    check("SDL_DefaultAudioDeviceChanged prepends migrated logdev", mig["mig_prepends"])
    check("patched working-tree SDL_DefaultAudioDeviceChanged sets new_default_device->logical_devices->prev = logdev (G6-P106)",
          mig["mig_prepends"] and not mig["mig_missing_prev_fix"])
    check("SDL_OpenAudioDevice sets device->logical_devices->prev = logdev (contrast)", mig["open_sets_old_head_prev"])
    check("DestroyLogicalAudioDevice unlinks via logdev->prev before SDL_free", mig["destroy_uses_prev"])
    check("SDL_PlaybackAudioThreadIterate walks logical_devices and reads SDL_GetAtomicInt(&logdev->paused)", mig["iterate_walks_paused"])

    sdl_wasapi_c = read_text(SDL / "src" / "audio" / "wasapi" / "SDL_wasapi.c")
    prep = extract_block(sdl_wasapi_c, r"static bool mgmtthrtask_PrepDevice\(", r"^\}")
    check(
        "WASAPI mgmtthrtask_PrepDevice calls SDL_AudioDeviceFormatChangedAlreadyLocked",
        "SDL_AudioDeviceFormatChangedAlreadyLocked(" in prep,
    )
    wait_fn = extract_block(sdl_wasapi_c, r"static bool WASAPI_WaitDevice\(", r"^\}")
    check("WASAPI_WaitDevice calls RecoverWasapiIfLost without device->lock", "RecoverWasapiIfLost(" in wait_fn)

    sdl_c = read_text(SDL / "src" / "SDL.c")
    check("SDL_SubsystemRefCount is plain Uint8 array", "static Uint8 SDL_SubsystemRefCount[32];" in sdl_c)

    sdl_drv = read_text(SDK / "src" / "audio" / "sdl" / "sdl_audio_driver.cpp")
    ds_hdr = read_text(ROOT / "tools" / "r3hd_ds_speaker_sdl.h")
    check("SDLAudioDriver calls SDL_InitSubSystem/SDL_QuitSubSystem(SDL_INIT_AUDIO)",
          "SDL_InitSubSystem(SDL_INIT_AUDIO)" in sdl_drv and "SDL_QuitSubSystem(SDL_INIT_AUDIO)" in sdl_drv)
    check("DualSense speaker calls SDL_InitSubSystem/SDL_QuitSubSystem(SDL_INIT_AUDIO) only when not suppressed",
          "SDL_InitSubSystem(SDL_INIT_AUDIO)" in ds_hdr
          and "SDL_QuitSubSystem(SDL_INIT_AUDIO)" in ds_hdr
          and "m23haptics::Suppressed()" in ds_hdr)

    ff_cfg = read_text(SDK / "thirdparty" / "FFmpeg" / "config_windows_x86_64.h")
    wmapro = read_text(SDK / "thirdparty" / "FFmpeg" / "libavcodec" / "wmaprodec.c")
    xma_dec = extract_block(wmapro, r"AVCodec ff_xmaframes_decoder", r"^\};")
    check("Windows FFmpeg enables HAVE_THREADS and HAVE_W32THREADS",
          "#define HAVE_THREADS 1" in ff_cfg and "#define HAVE_W32THREADS 1" in ff_cfg)
    check("ff_xmaframes_decoder omits FF_CODEC_CAP_INIT_THREADSAFE (serialized by codec_mutex)",
          bool(xma_dec) and "FF_CODEC_CAP_INIT_THREADSAFE" not in xma_dec)

    unpatched_audio_sys = subprocess.check_output(
        ["git", "-C", str(SDK), "show", "c94f5ebdcb3c9d1a460ca48e04f9758448f8d518:src/audio/audio_system.cpp"],
        text=True,
        errors="replace",
    )
    unpatched_unreg_fn = extract_block(unpatched_audio_sys, r"void AudioSystem::UnregisterClient\(", r"^\}")
    check("pinned unpatched AudioSystem::UnregisterClient clears clients_[index] after DestroyDriver (negative control)",
          "DestroyDriver(clients_[index].driver);" in unpatched_unreg_fn
          and "clients_[index] = {nullptr, 0, 0, 0, false};" in unpatched_unreg_fn)

    audio_sys = read_text(SDK / "src" / "audio" / "audio_system.cpp")
    xma_ctx = read_text(SDK / "src" / "audio" / "xma_context.cpp")
    unreg_fn = extract_block(audio_sys, r"void AudioSystem::UnregisterClient\(", r"^\}")
    check("patched working-tree AudioSystem::UnregisterClient defers FinalizeClientLocked while callbacks are in flight (G6-P109)",
          "client.unregister_pending = true;" in unreg_fn
          and "if (client.in_flight_callbacks == 0)" in unreg_fn
          and "FinalizeClientLocked(index);" in unreg_fn)
    work_fn = extract_block(xma_ctx, r"bool XmaContext::Work\(\)", r"std::unique_lock")
    check("XmaContext::Work checks is_allocated/is_enabled before lock_",
          "!is_allocated() || !is_enabled()" in work_fn)

    passed = sum(1 for v in results.values() if v)
    total = len(results)
    for k, v in results.items():
        print(f"{'PASS' if v else 'FAIL'} {k}")
    print(f"G6P105_AUDIO_LIFECYCLE_AUDIT {'PASS' if passed == total else 'FAIL'} {passed}/{total}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
