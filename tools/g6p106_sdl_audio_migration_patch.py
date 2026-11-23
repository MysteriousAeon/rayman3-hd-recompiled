#!/usr/bin/env python3
"""Replay last in the SDK patch chain (G6-P106, D-345): fix SDL_DefaultAudioDeviceChanged prev-pointer corruption.

Pinned SDL-3.5.0-8bf3b72 (external/rexglue-sdk/thirdparty/sdl3/src/audio/SDL_audio.c:2455-2458) prepends each
migrated `opened_as_default` logical device onto `new_default_device->logical_devices` without updating
`new_default_device->logical_devices->prev = logdev`. Unlike SDL_OpenAudioDevice (L1902-1906), this leaves the
previous head's `prev` pointer NULL, so later closing that non-head logical device in DestroyLogicalAudioDevice
frees it without clearing the head's `next` pointer or restoring `simple_copy`, causing a UAF on the next
SDL_PlaybackAudioThreadIterate pass even while `device->lock` is held.

This narrow, idempotent patch inserts the missing 3-line `prev` update under the existing
`new_default_device->lock` + `current_default_device->lock` + `subsystem_rwlock` write-lock critical section.
It preserves the SDK pin (c94f5eb), the SDL3 submodule pin (8bf3b72), exact line endings, and all unrelated
SDK working-tree modifications, and fails closed on source drift.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SDK = ROOT / "external" / "rexglue-sdk"
SDL = SDK / "thirdparty" / "sdl3"
REL = Path("src/audio/SDL_audio.c")
TARGET = SDL / REL

EXPECTED_SDK_PIN = "c94f5ebdcb3c9d1a460ca48e04f9758448f8d518"
EXPECTED_SDL_PIN = "8bf3b7215ad9fc3deb583c6a3a37c6c67f2e24e4"

BEFORE_LF = (
    "                logdev->physical_device = new_default_device;\n"
    "                logdev->prev = NULL;\n"
    "                logdev->next = new_default_device->logical_devices;\n"
    "                new_default_device->logical_devices = logdev;\n"
    "                SDL_UnlockRWLock(current_audio.subsystem_rwlock);\n"
)

AFTER_LF = (
    "                logdev->physical_device = new_default_device;\n"
    "                logdev->prev = NULL;\n"
    "                logdev->next = new_default_device->logical_devices;\n"
    "                if (new_default_device->logical_devices) {\n"
    "                    new_default_device->logical_devices->prev = logdev;\n"
    "                }\n"
    "                new_default_device->logical_devices = logdev;\n"
    "                SDL_UnlockRWLock(current_audio.subsystem_rwlock);\n"
)


def _detect_eol(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"


def apply_patch_text(text: str) -> tuple[str, str]:
    """Apply the G6-P106 SDL_DefaultAudioDeviceChanged fix to SDL_audio.c text.

    Returns (result_text, status) where status is 'patched' or 'already_applied'.
    Raises RuntimeError if the expected anchor has drifted or appears multiple times.
    """
    eol = _detect_eol(text)
    norm = text.replace("\r\n", "\n")

    before_count = norm.count(BEFORE_LF)
    after_count = norm.count(AFTER_LF)

    if after_count == 1 and before_count == 0:
        return text, "already_applied"
    if before_count == 1 and after_count == 0:
        patched = norm.replace(BEFORE_LF, AFTER_LF, 1)
        if eol == "\r\n":
            patched = patched.replace("\n", "\r\n")
        return patched, "patched"
    raise RuntimeError(
        f"SDL_audio.c source drift detected: before_count={before_count}, after_count={after_count}"
    )


def verify_pins(sdk_dir: Path = SDK, sdl_dir: Path = SDL) -> None:
    sdk_head = subprocess.check_output(
        ["git", "-C", str(sdk_dir), "rev-parse", "HEAD"], text=True
    ).strip()
    if sdk_head != EXPECTED_SDK_PIN:
        raise RuntimeError(f"SDK pin mismatch: expected {EXPECTED_SDK_PIN}, got {sdk_head}")
    sdl_head = subprocess.check_output(
        ["git", "-C", str(sdl_dir), "rev-parse", "HEAD"], text=True
    ).strip()
    if sdl_head != EXPECTED_SDL_PIN:
        raise RuntimeError(f"SDL3 pin mismatch: expected {EXPECTED_SDL_PIN}, got {sdl_head}")


def patch_file(path: Path = TARGET, check_only: bool = False) -> str:
    if not path.is_file():
        raise RuntimeError(f"Target file not found: {path}")
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    new_text, status = apply_patch_text(text)
    if check_only:
        if status != "already_applied":
            raise RuntimeError(f"G6-P106 SDL patch not applied to {path} (status={status})")
        return status
    if status == "patched":
        path.write_bytes(new_text.encode("utf-8"))
    return status


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    check_only = "--check" in args
    verify_pins()
    status = patch_file(TARGET, check_only=check_only)
    print(f"g6p106_sdl_audio_migration_patch: {status} thirdparty/sdl3/{REL.as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
