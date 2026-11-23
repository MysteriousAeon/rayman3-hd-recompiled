#!/usr/bin/env python3
"""G6-P106 (D-345 / E-589): deterministic patch-chain, source-invariant, and ASan UAF regression.

Verifies:
1. Ordered SDK patch chain (`g6p106_sdl_audio_migration_patch.py` and `build_milestone8.bat`):
   - SDK pin (c94f5eb) and SDL3 submodule pin (8bf3b72) are preserved.
   - Working-tree `thirdparty/sdl3/src/audio/SDL_audio.c` matches patching pinned `8bf3b72` byte-for-byte (CRLF kept).
   - Reapplying the patch is idempotent (`already_applied`, byte-identical).
   - Source drift (modified or duplicated anchor) is detected and raises RuntimeError.
   - `build_milestone8.bat` applies the patch before `cmake -S external` and runs this regression before `M8_BUILD_OK`.
2. Verbatim source-extracted ASan C verification (compiled with `clang -fsanitize=address`):
   - Extracts the exact list-unlink / prepend statements from `SDL_OpenAudioDevice`, `DestroyLogicalAudioDevice`,
     and `SDL_DefaultAudioDeviceChanged` directly from:
       (a) unpatched pinned `git show 8bf3b72:src/audio/SDL_audio.c` (negative control), and
       (b) patched working-tree `external/rexglue-sdk/thirdparty/sdl3/src/audio/SDL_audio.c` (positive control).
   - Negative control MUST fail with AddressSanitizer `heap-use-after-free` on `logdev->paused` (non-zero exit).
   - Positive control MUST pass with 0 ASan findings across:
       * normal open/close ordering (head, middle, tail),
       * 2-client default migration + tail close + playback iterate (Rayman 3 HD topology),
       * 3-client default migration + multiple close orders,
       * migration onto a new default device that already has a pre-existing logical device,
       * mixed default + non-default logical devices,
       * back-to-back double migration (devA -> devB -> devC).
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SDK = ROOT / "external" / "rexglue-sdk"
SDL = SDK / "thirdparty" / "sdl3"
SDL_AUDIO_C = SDL / "src" / "audio" / "SDL_audio.c"

sys.path.insert(0, str(ROOT / "tools"))
import g6p106_sdl_audio_migration_patch as patch_mod  # noqa: E402

DEFAULT_VCVARS = r"C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
DEFAULT_LLVM_BIN = r"C:\Program Files\LLVM\bin"


def git_show_unpatched_sdl_audio() -> bytes:
    return subprocess.check_output(
        ["git", "-C", str(SDL), "show", f"{patch_mod.EXPECTED_SDL_PIN}:src/audio/SDL_audio.c"]
    )


def extract_snippet(source: str, start_anchor: str, end_anchor: str) -> str:
    s_idx = source.find(start_anchor)
    if s_idx < 0:
        raise RuntimeError(f"Start anchor not found: {start_anchor!r}")
    e_idx = source.find(end_anchor, s_idx)
    if e_idx < 0:
        raise RuntimeError(f"End anchor not found: {end_anchor!r}")
    return source[s_idx : e_idx + len(end_anchor)]


def extract_sdl_snippets(sdl_audio_text: str) -> tuple[str, str, str]:
    norm = sdl_audio_text.replace("\r\n", "\n")

    open_fn = norm[norm.index("SDL_AudioDeviceID SDL_OpenAudioDevice(") :]
    open_snip = extract_snippet(
        open_fn,
        "            logdev->next = device->logical_devices;",
        "            device->logical_devices = logdev;",
    )

    destroy_fn = norm[norm.index("static void DestroyLogicalAudioDevice(") :]
    destroy_snip = extract_snippet(
        destroy_fn,
        "    if (logdev->next) {",
        "    if (logdev->physical_device->logical_devices == logdev) {\n"
        "        logdev->physical_device->logical_devices = logdev->next;\n"
        "    }",
    )

    mig_fn = norm[norm.index("void SDL_DefaultAudioDeviceChanged(") :]
    mig_snip = extract_snippet(
        mig_fn,
        "                if (logdev->next) {",
        "                new_default_device->logical_devices = logdev;",
    )
    return open_snip, destroy_snip, mig_snip


HARNESS_C = r"""
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>

typedef struct SDL_LogicalAudioDevice SDL_LogicalAudioDevice;
typedef struct SDL_AudioDevice SDL_AudioDevice;

typedef struct SDL_AtomicInt {
    int value;
} SDL_AtomicInt;

static int SDL_GetAtomicInt(const SDL_AtomicInt *a) {
    return a->value;
}

struct SDL_LogicalAudioDevice {
    int id;
    SDL_AtomicInt paused;
    bool opened_as_default;
    SDL_AudioDevice *physical_device;
    SDL_LogicalAudioDevice *next;
    SDL_LogicalAudioDevice *prev;
};

struct SDL_AudioDevice {
    SDL_LogicalAudioDevice *logical_devices;
    bool simple_copy;
};

static bool audio_device_can_use_simple_copy(const SDL_AudioDevice *device) {
    return device->logical_devices && !device->logical_devices->next;
}

static void update_simple_copy(SDL_AudioDevice *device) {
    device->simple_copy = audio_device_can_use_simple_copy(device);
}

static void check_list_invariants(const SDL_AudioDevice *device, int expected_count) {
    int count = 0;
    const SDL_LogicalAudioDevice *prev = NULL;
    for (const SDL_LogicalAudioDevice *cur = device->logical_devices; cur; cur = cur->next) {
        assert(cur->physical_device == device);
        assert(cur->prev == prev);
        if (prev) {
            assert(prev->next == cur);
        }
        prev = cur;
        count++;
        assert(count <= 64);
    }
    assert(count == expected_count);
    assert(device->simple_copy == audio_device_can_use_simple_copy(device));
}

static SDL_LogicalAudioDevice *open_logical(SDL_AudioDevice *device, int id, bool opened_as_default) {
    SDL_LogicalAudioDevice *logdev = (SDL_LogicalAudioDevice *)calloc(1, sizeof(*logdev));
    assert(logdev != NULL);
    logdev->id = id;
    logdev->paused.value = 0;
    logdev->opened_as_default = opened_as_default;
    logdev->physical_device = device;
#include "sdl_open_snippet.inc"
    update_simple_copy(device);
    return logdev;
}

static void destroy_logical(SDL_LogicalAudioDevice *logdev) {
    SDL_AudioDevice *phys = logdev->physical_device;
#include "sdl_destroy_snippet.inc"
    update_simple_copy(phys);
    free(logdev);
}

static void migrate_default(SDL_AudioDevice *current_default_device, SDL_AudioDevice *new_default_device) {
    SDL_LogicalAudioDevice *next = NULL;
    for (SDL_LogicalAudioDevice *logdev = current_default_device->logical_devices; logdev; logdev = next) {
        next = logdev->next;
        if (!logdev->opened_as_default) {
            continue;
        }
#include "sdl_migrate_snippet.inc"
    }
    update_simple_copy(current_default_device);
    update_simple_copy(new_default_device);
}

static int playback_iterate(SDL_AudioDevice *device) {
    int sum = 0;
    if (device->simple_copy) {
        SDL_LogicalAudioDevice *logdev = device->logical_devices;
        if (logdev && !SDL_GetAtomicInt(&logdev->paused)) {
            sum += logdev->id;
        }
    } else {
        for (SDL_LogicalAudioDevice *logdev = device->logical_devices; logdev; logdev = logdev->next) {
            if (SDL_GetAtomicInt(&logdev->paused)) {
                continue;
            }
            sum += logdev->id;
        }
    }
    return sum;
}

static int run_negative_uaf_scenario(void) {
    SDL_AudioDevice old_dev = {0};
    SDL_AudioDevice new_dev = {0};

    SDL_LogicalAudioDevice *l1 = open_logical(&old_dev, 1, true);
    SDL_LogicalAudioDevice *l2 = open_logical(&old_dev, 2, true);
    migrate_default(&old_dev, &new_dev);

    /* Close non-head tail L2 (movie client unregister). */
    destroy_logical(l2);

    /* Unpatched SDL leaves l1->next dangling -> ASan heap-use-after-free here. */
    int res = playback_iterate(&new_dev);
    int clean = (new_dev.simple_copy && l1->next == NULL && res == 1);
    printf("uaf_scenario iterate=%d simple_copy=%d head_next=%p\n",
           res, (int)new_dev.simple_copy, (void *)l1->next);
    destroy_logical(l1);
    return clean ? 0 : 1;
}

static void run_full_matrix(void) {
    /* Case 1: Normal open/close ordering (head, middle, tail). */
    {
        SDL_AudioDevice dev = {0};
        SDL_LogicalAudioDevice *a = open_logical(&dev, 10, true);
        check_list_invariants(&dev, 1);
        SDL_LogicalAudioDevice *b = open_logical(&dev, 20, true);
        check_list_invariants(&dev, 2);
        SDL_LogicalAudioDevice *c = open_logical(&dev, 30, true);
        check_list_invariants(&dev, 3);
        assert(playback_iterate(&dev) == 60);

        destroy_logical(b); /* middle */
        check_list_invariants(&dev, 2);
        assert(playback_iterate(&dev) == 40);

        destroy_logical(c); /* head */
        check_list_invariants(&dev, 1);
        assert(playback_iterate(&dev) == 10);

        destroy_logical(a); /* last */
        check_list_invariants(&dev, 0);
        assert(playback_iterate(&dev) == 0);
    }

    /* Case 2: Rayman 3 HD two-client migration + tail close + playback iterate. */
    {
        SDL_AudioDevice old_dev = {0};
        SDL_AudioDevice new_dev = {0};
        SDL_LogicalAudioDevice *game = open_logical(&old_dev, 1, true);
        SDL_LogicalAudioDevice *movie = open_logical(&old_dev, 2, true);
        check_list_invariants(&old_dev, 2);

        migrate_default(&old_dev, &new_dev);
        check_list_invariants(&old_dev, 0);
        check_list_invariants(&new_dev, 2);
        assert(playback_iterate(&new_dev) == 3);

        destroy_logical(movie);
        check_list_invariants(&new_dev, 1);
        assert(new_dev.simple_copy == true);
        assert(playback_iterate(&new_dev) == 1);

        destroy_logical(game);
        check_list_invariants(&new_dev, 0);
    }

    /* Case 3: Three migrated default clients closed in tail -> middle -> head order. */
    {
        SDL_AudioDevice d1 = {0};
        SDL_AudioDevice d2 = {0};
        SDL_LogicalAudioDevice *l1 = open_logical(&d1, 1, true);
        SDL_LogicalAudioDevice *l2 = open_logical(&d1, 2, true);
        SDL_LogicalAudioDevice *l3 = open_logical(&d1, 4, true);
        migrate_default(&d1, &d2);
        check_list_invariants(&d1, 0);
        check_list_invariants(&d2, 3);
        assert(playback_iterate(&d2) == 7);

        destroy_logical(l3); /* tail after reversal */
        check_list_invariants(&d2, 2);
        assert(playback_iterate(&d2) == 3);

        destroy_logical(l2); /* middle */
        check_list_invariants(&d2, 1);
        assert(playback_iterate(&d2) == 1);

        destroy_logical(l1); /* head */
        check_list_invariants(&d2, 0);
    }

    /* Case 4: Pre-existing explicit logical device on new_dev + 2 migrated default clients. */
    {
        SDL_AudioDevice d1 = {0};
        SDL_AudioDevice d2 = {0};
        SDL_LogicalAudioDevice *pre = open_logical(&d2, 100, false);
        SDL_LogicalAudioDevice *m1 = open_logical(&d1, 1, true);
        SDL_LogicalAudioDevice *m2 = open_logical(&d1, 2, true);
        migrate_default(&d1, &d2);
        check_list_invariants(&d1, 0);
        check_list_invariants(&d2, 3);
        assert(playback_iterate(&d2) == 103);

        destroy_logical(pre); /* original head, now tail */
        check_list_invariants(&d2, 2);
        assert(playback_iterate(&d2) == 3);

        destroy_logical(m1);
        check_list_invariants(&d2, 1);
        destroy_logical(m2);
        check_list_invariants(&d2, 0);
    }

    /* Case 5: Mixed default + non-default logical devices on old_dev. */
    {
        SDL_AudioDevice d1 = {0};
        SDL_AudioDevice d2 = {0};
        SDL_LogicalAudioDevice *def1 = open_logical(&d1, 1, true);
        SDL_LogicalAudioDevice *exp1 = open_logical(&d1, 10, false);
        SDL_LogicalAudioDevice *def2 = open_logical(&d1, 2, true);
        SDL_LogicalAudioDevice *exp2 = open_logical(&d1, 20, false);
        migrate_default(&d1, &d2);
        check_list_invariants(&d1, 2);
        check_list_invariants(&d2, 2);
        assert(playback_iterate(&d1) == 30);
        assert(playback_iterate(&d2) == 3);

        destroy_logical(def2);
        check_list_invariants(&d2, 1);
        destroy_logical(exp1);
        check_list_invariants(&d1, 1);
        destroy_logical(def1);
        destroy_logical(exp2);
        check_list_invariants(&d1, 0);
        check_list_invariants(&d2, 0);
    }

    /* Case 6: Back-to-back double migration (dA -> dB -> dC) + tail close. */
    {
        SDL_AudioDevice dA = {0};
        SDL_AudioDevice dB = {0};
        SDL_AudioDevice dC = {0};
        SDL_LogicalAudioDevice *l1 = open_logical(&dA, 1, true);
        SDL_LogicalAudioDevice *l2 = open_logical(&dA, 2, true);
        migrate_default(&dA, &dB);
        check_list_invariants(&dB, 2);
        migrate_default(&dB, &dC);
        check_list_invariants(&dB, 0);
        check_list_invariants(&dC, 2);

        destroy_logical(l1); /* tail after second reversal */
        check_list_invariants(&dC, 1);
        assert(playback_iterate(&dC) == 2);
        destroy_logical(l2);
        check_list_invariants(&dC, 0);
    }
}

int main(void) {
#if RUN_FULL_MATRIX
    run_full_matrix();
    printf("FULL_MATRIX_PASS\n");
    return 0;
#else
    return run_negative_uaf_scenario();
#endif
}
"""


def compile_and_run_asan(
    work_dir: Path,
    tag: str,
    sdl_text: str,
    full_matrix: bool,
) -> subprocess.CompletedProcess:
    open_snip, destroy_snip, mig_snip = extract_sdl_snippets(sdl_text)
    sub = work_dir / tag
    sub.mkdir(parents=True, exist_ok=True)
    (sub / "sdl_open_snippet.inc").write_text(open_snip + "\n", encoding="utf-8")
    (sub / "sdl_destroy_snippet.inc").write_text(destroy_snip + "\n", encoding="utf-8")
    (sub / "sdl_migrate_snippet.inc").write_text(mig_snip + "\n", encoding="utf-8")
    src = sub / "harness.c"
    exe = sub / f"harness_{tag}.exe"
    src.write_text(HARNESS_C, encoding="utf-8")

    llvm_bin = os.environ.get("R3HD_LLVM_BIN", DEFAULT_LLVM_BIN)
    vcvars = os.environ.get("R3HD_VCVARS", DEFAULT_VCVARS)
    clang = str(Path(llvm_bin) / "clang.exe")
    define = "-DRUN_FULL_MATRIX=1" if full_matrix else "-DRUN_FULL_MATRIX=0"

    if os.environ.get("LIB") and os.environ.get("INCLUDE"):
        compile_cmd = [clang, "-O1", "-g", "-fsanitize=address", define, str(src), "-o", str(exe)]
        res = subprocess.run(compile_cmd, capture_output=True, text=True)
    else:
        bat = sub / "build.bat"
        bat.write_text(
            f'@echo off\r\n'
            f'call "{vcvars}" >nul 2>&1\r\n'
            f'if errorlevel 1 exit /b 2\r\n'
            f'"{clang}" -O1 -g -fsanitize=address {define} "{src}" -o "{exe}"\r\n',
            encoding="utf-8",
        )
        res = subprocess.run(["cmd", "/c", str(bat)], capture_output=True, text=True)

    if res.returncode != 0:
        raise RuntimeError(
            f"ASan compile failed for {tag} (rc={res.returncode}):\n{res.stdout}\n{res.stderr}"
        )

    env = os.environ.copy()
    extra_paths = [llvm_bin]
    llvm_root = Path(llvm_bin).parent
    for dll in llvm_root.glob("lib/clang/*/lib/windows/clang_rt.asan_dynamic-x86_64.dll"):
        extra_paths.append(str(dll.parent))
    env["PATH"] = ";".join(extra_paths) + ";" + env.get("PATH", "")
    return subprocess.run([str(exe)], capture_output=True, text=True, env=env)


def main() -> int:
    results: dict[str, bool] = {}

    def check(name: str, cond: bool) -> None:
        results[name] = bool(cond)

    # 1. Pin & working-tree patch verification.
    pin_ok = True
    try:
        patch_mod.verify_pins()
    except Exception:
        pin_ok = False
    check("SDK pin (c94f5eb) and SDL3 submodule pin (8bf3b72) match", pin_ok)

    unpatched_bytes = git_show_unpatched_sdl_audio()
    unpatched_text = unpatched_bytes.decode("utf-8")
    working_bytes = SDL_AUDIO_C.read_bytes()
    working_text = working_bytes.decode("utf-8")

    # Applying patch to unpatched pinned source produces working tree (with CRLF on Windows checkout).
    patched_from_pin, status1 = patch_mod.apply_patch_text(unpatched_text)
    check("patching pinned SDL_audio.c returns status='patched'", status1 == "patched")
    check("patched pinned SDL_audio.c matches working-tree SDL_audio.c content",
          patched_from_pin.replace("\r\n", "\n") == working_text.replace("\r\n", "\n"))
    check("patched SDL_audio.c preserves CRLF line endings",
          b"\r\n" in working_bytes and (working_bytes.count(b"\n") == working_bytes.count(b"\r\n")))

    # Idempotency check.
    reapplied, status2 = patch_mod.apply_patch_text(working_text)
    check("reapplying patch returns status='already_applied'", status2 == "already_applied")
    check("reapplying patch leaves SDL_audio.c byte-identical", reapplied == working_text)

    # Drift detection negative controls.
    drift_missing_caught = False
    try:
        patch_mod.apply_patch_text(unpatched_text.replace("logdev->prev = NULL;", "logdev->prev = 0;", 1))
    except RuntimeError:
        drift_missing_caught = True
    check("source drift (modified anchor) raises RuntimeError", drift_missing_caught)

    drift_dup_caught = False
    try:
        patch_mod.apply_patch_text(unpatched_text + "\n" + patch_mod.BEFORE_LF)
    except RuntimeError:
        drift_dup_caught = True
    check("source drift (duplicate anchor) raises RuntimeError", drift_dup_caught)

    drift_both_caught = False
    try:
        patch_mod.apply_patch_text(working_text + "\n" + patch_mod.BEFORE_LF)
    except RuntimeError:
        drift_both_caught = True
    check("source drift (both before and after present) raises RuntimeError", drift_both_caught)

    # Build script integration check.
    bat_text = (ROOT / "tools" / "build_milestone8.bat").read_text(encoding="utf-8")
    p_line = r"python tools\g6p106_sdl_audio_migration_patch.py || exit /b 1"
    r_line = r"python tools\g6p106_sdl_audio_migration_regression.py || exit /b 1"
    check("build_milestone8.bat applies g6p106 patch once before cmake -S external",
          bat_text.count(p_line) == 1 and bat_text.index(p_line) < bat_text.index("cmake -S external"))
    check("build_milestone8.bat runs g6p106 regression once before M8_BUILD_OK",
          bat_text.count(r_line) == 1 and bat_text.index(r_line) < bat_text.index("echo M8_BUILD_OK"))

    # 2. Verbatim source-extracted ASan negative & positive controls.
    with tempfile.TemporaryDirectory(prefix="g6p106_asan_") as td:
        tmp = Path(td)
        neg = compile_and_run_asan(tmp, "unpatched_neg", unpatched_text, full_matrix=False)
        neg_combined = (neg.stdout or "") + "\n" + (neg.stderr or "")
        check("ASan negative control (unpatched 8bf3b72) exits non-zero", neg.returncode != 0)
        check("ASan negative control reports heap-use-after-free",
              "AddressSanitizer: heap-use-after-free" in neg_combined)

        pos_uaf = compile_and_run_asan(tmp, "patched_uaf", working_text, full_matrix=False)
        pos_uaf_combined = (pos_uaf.stdout or "") + "\n" + (pos_uaf.stderr or "")
        check("ASan positive control (patched working tree, 2-client migration) exits 0",
              pos_uaf.returncode == 0)
        check("ASan positive control reports 0 ASan errors and clean simple_copy=1",
              "AddressSanitizer" not in pos_uaf_combined and "simple_copy=1" in pos_uaf.stdout)

        pos_mat = compile_and_run_asan(tmp, "patched_matrix", working_text, full_matrix=True)
        pos_mat_combined = (pos_mat.stdout or "") + "\n" + (pos_mat.stderr or "")
        check("ASan full matrix (open/close, 2/3-client, pre-existing, mixed, double migration) exits 0",
              pos_mat.returncode == 0)
        check("ASan full matrix reports FULL_MATRIX_PASS and 0 ASan errors",
              "FULL_MATRIX_PASS" in pos_mat.stdout and "AddressSanitizer" not in pos_mat_combined)

    passed = sum(1 for v in results.values() if v)
    total = len(results)
    for k, v in results.items():
        print(f"{'PASS' if v else 'FAIL'} {k}")
    print(f"G6P106_SDL_AUDIO_MIGRATION_REGRESSION {'PASS' if passed == total else 'FAIL'} {passed}/{total}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
