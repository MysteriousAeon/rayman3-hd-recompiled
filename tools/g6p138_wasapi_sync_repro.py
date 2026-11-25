#!/usr/bin/env python3
"""G6-P138 (E-619): Deterministic synthetic concurrency reproductions for pinned SDL3 WASAPI H4-A/B/C.

Scope and evidence boundary:
- Purely synthetic C++20 thread/lock/barrier model compiled with AddressSanitizer.
- Zero Windows Audio Engine interaction, zero SDL audio initialization, zero physical audio devices.
- Bounded timeouts (200 ms) guarantee deterministic termination with zero leaked or permanently blocked threads.
- Demonstrates the consequences of source-backed interleavings from pinned SDL-3.5.0-8bf3b72;
  does NOT constitute live WASAPI execution proof.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VCVARS = r"C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
DEFAULT_LLVM_BIN = r"C:\Program Files\LLVM\bin"

HARNESS_CPP = r"""
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <functional>
#include <mutex>
#include <queue>
#include <string>
#include <thread>

using namespace std::chrono_literals;

static constexpr auto kDeadlockTimeout = 200ms;

// Simple reusable latch / event for deterministic interleaving (no sleep-only races).
struct Event {
    std::mutex m;
    std::condition_variable cv;
    bool signaled = false;

    void signal() {
        {
            std::lock_guard<std::mutex> lk(m);
            signaled = true;
        }
        cv.notify_all();
    }

    bool wait_for(std::chrono::milliseconds timeout) {
        std::unique_lock<std::mutex> lk(m);
        return cv.wait_for(lk, timeout, [&] { return signaled; });
    }
};

struct SynthLogicalDevice {
    int id = 0;
    bool opened_as_default = true;
    struct SynthPhysicalDevice *physical = nullptr;
    SynthLogicalDevice *next = nullptr;
    SynthLogicalDevice *prev = nullptr;
    int magic = 0x13572468;
};

struct SynthPhysicalDevice {
    int id = 0;
    std::timed_mutex lock;
    std::atomic<int> shutdown{0};
    bool currently_opened = false;
    bool device_lost = false;
    int spec_freq = 48000;
    int sample_frames = 480;
    bool simple_copy = false;
    SynthLogicalDevice *logical_devices = nullptr;
    std::thread playback_thread;
};

struct PendingTask {
    std::function<bool()> fn;
    Event *done_sem = nullptr;  // non-null => synchronous wait (WASAPI_ProxyToManagementThread)
    bool result = false;
};

struct SynthMgmtThread {
    std::mutex q_lock;
    std::condition_variable q_cv;
    std::queue<PendingTask *> q;
    std::atomic<bool> stop{false};
    std::thread thr;
    std::thread::id tid;

    void start() {
        Event ready;
        thr = std::thread([this, &ready] {
            tid = std::this_thread::get_id();
            ready.signal();
            while (true) {
                PendingTask *t = nullptr;
                {
                    std::unique_lock<std::mutex> lk(q_lock);
                    q_cv.wait(lk, [&] { return !q.empty() || stop.load(); });
                    if (q.empty() && stop.load()) {
                        break;
                    }
                    t = q.front();
                    q.pop();
                }
                t->result = t->fn();
                if (t->done_sem) {
                    t->done_sem->signal();
                } else {
                    delete t;
                }
            }
        });
        ready.wait_for(2000ms);
    }

    // Returns true if task completed within timeout, false on deadlock timeout.
    bool proxy(std::function<bool()> fn, bool *wait_on_result, std::chrono::milliseconds timeout = kDeadlockTimeout) {
        if (wait_on_result && std::this_thread::get_id() == tid) {
            *wait_on_result = fn();
            return true;
        }
        auto *t = new PendingTask();
        t->fn = std::move(fn);
        Event sem;
        if (wait_on_result) {
            t->done_sem = &sem;
        }
        {
            std::lock_guard<std::mutex> lk(q_lock);
            q.push(t);
        }
        q_cv.notify_one();

        if (wait_on_result) {
            bool ok = sem.wait_for(timeout);
            if (!ok) {
                // Deadlock detected; detach ownership so mgmt thread can free/skip when unblocked.
                // Caller will signal abort so mgmt thread finishes and drains queue cleanly.
                // Wait briefly after caller triggers abort in teardown.
                return false;
            }
            *wait_on_result = t->result;
            delete t;
        }
        return true;
    }

    void shutdown_and_join() {
        {
            std::lock_guard<std::mutex> lk(q_lock);
            stop.store(true);
        }
        q_cv.notify_all();
        if (thr.joinable()) {
            thr.join();
        }
        // Clean up any leftover tasks
        while (!q.empty()) {
            auto *t = q.front();
            q.pop();
            if (!t->done_sem) delete t;
        }
    }
};

static void destroy_logical_locked(SynthLogicalDevice *logdev) {
    if (logdev->next) logdev->next->prev = logdev->prev;
    if (logdev->prev) logdev->prev->next = logdev->next;
    if (logdev->physical->logical_devices == logdev) {
        logdev->physical->logical_devices = logdev->next;
    }
    logdev->physical->simple_copy =
        (logdev->physical->logical_devices != nullptr && logdev->physical->logical_devices->next == nullptr);
    std::free(logdev);
}

// ---------------------------------------------------------------------------
// H4-A: Unlocked SDL_AudioDeviceFormatChangedAlreadyLocked during recovery
// ---------------------------------------------------------------------------
static int run_h4a_uaf() {
    SynthMgmtThread mgmt;
    mgmt.start();

    SynthPhysicalDevice d1;
    d1.id = 1;
    d1.currently_opened = true;
    d1.spec_freq = 48000;
    d1.sample_frames = 480;

    auto *l1 = (SynthLogicalDevice *)std::calloc(1, sizeof(SynthLogicalDevice));
    l1->id = 101;
    l1->physical = &d1;
    l1->magic = 0x13572468;
    d1.logical_devices = l1;

    Event mgmt_entered_walk;
    Event app_freed_logdev;

    // App thread closes l1 under d1.lock while mgmt thread walks logical_devices unlocked.
    std::thread app_thr([&] {
        mgmt_entered_walk.wait_for(2000ms);
        std::lock_guard<std::timed_mutex> lk(d1.lock);
        destroy_logical_locked(l1);
        app_freed_logdev.signal();
    });

    // PlaybackAudioThread runs RecoverWasapiDevice WITHOUT d1.lock.
    bool rc = false;
    int observed_id = 0;
    mgmt.proxy([&]() -> bool {
        // mgmtthrtask_PrepDevice -> SDL_AudioDeviceFormatChangedAlreadyLocked (unlocked!)
        const int new_freq = 44100;  // format changed -> skips early return L2516
        const int new_frames = 441;
        if (d1.spec_freq == new_freq && d1.sample_frames == new_frames) {
            return true;
        }
        d1.spec_freq = new_freq;
        d1.sample_frames = new_frames;
        // Walk device->logical_devices (SDL_audio.c:260, 2572) WITHOUT holding d1.lock
        SynthLogicalDevice *logdev = d1.logical_devices;
        mgmt_entered_walk.signal();
        app_freed_logdev.wait_for(2000ms);
        if (logdev) {
            // Deterministic ASan heap-use-after-free here!
            observed_id = logdev->id;
        }
        return true;
    }, &rc, 2000ms);

    app_thr.join();
    mgmt.shutdown_and_join();
    std::printf("H4A_UAF_UNEXPECTED_SURVIVE observed_id=%d\n", observed_id);
    return 0;
}

static int run_h4a_neg_same_format() {
    SynthMgmtThread mgmt;
    mgmt.start();

    SynthPhysicalDevice d1;
    d1.id = 1;
    d1.currently_opened = true;
    d1.spec_freq = 48000;
    d1.sample_frames = 480;

    auto *l1 = (SynthLogicalDevice *)std::calloc(1, sizeof(SynthLogicalDevice));
    l1->id = 101;
    l1->physical = &d1;
    d1.logical_devices = l1;

    // Negative control: same spec & sample_frames -> early return at SDL_audio.c:2516, no list walk.
    bool rc = false;
    bool ok = mgmt.proxy([&]() -> bool {
        const int new_freq = 48000;
        const int new_frames = 480;
        if (d1.spec_freq == new_freq && d1.sample_frames == new_frames) {
            return true;
        }
        return false;
    }, &rc, 2000ms);

    {
        std::lock_guard<std::timed_mutex> lk(d1.lock);
        destroy_logical_locked(l1);
    }
    mgmt.shutdown_and_join();
    if (!ok || !rc) return 2;
    std::printf("H4A_NEG_SAME_FORMAT_PASS\n");
    return 0;
}

static int run_h4a_naive_lock_self_deadlock() {
    SynthMgmtThread mgmt;
    mgmt.start();

    SynthPhysicalDevice d1;
    d1.id = 1;
    std::atomic<bool> mgmt_lock_timed_out{false};
    Event mgmt_done;

    // WASAPI_OpenDevice holds d1.lock and synchronously proxies mgmtthrtask_PrepDevice.
    d1.lock.lock();
    bool rc = false;
    bool ok = mgmt.proxy([&]() -> bool {
        // Naive fix: try to lock d1.lock inside mgmtthrtask_PrepDevice!
        if (!d1.lock.try_lock_for(kDeadlockTimeout)) {
            mgmt_lock_timed_out.store(true);
            mgmt_done.signal();
            return false;
        }
        d1.lock.unlock();
        mgmt_done.signal();
        return true;
    }, &rc, kDeadlockTimeout + 150ms);

    d1.lock.unlock();
    mgmt_done.wait_for(2000ms);
    mgmt.shutdown_and_join();

    if (ok && !rc && mgmt_lock_timed_out.load()) {
        std::printf("H4A_NAIVE_LOCK_SELF_DEADLOCK_VERIFIED\n");
        return 0;
    }
    std::printf("H4A_NAIVE_LOCK_UNEXPECTED ok=%d rc=%d to=%d\n", ok, rc, (int)mgmt_lock_timed_out.load());
    return 2;
}

// ---------------------------------------------------------------------------
// H4-B: PlaybackAudioThread(D1) RecoverWasapiDevice <-> SDLWASAPIMgmt ClosePhysicalAudioDevice(D1)
// ---------------------------------------------------------------------------
static int run_h4b_deadlock() {
    SynthMgmtThread mgmt;
    mgmt.start();

    SynthPhysicalDevice d1, d2;
    d1.id = 1;
    d1.currently_opened = true;
    d1.device_lost = true;
    d2.id = 2;

    Event playback_passed_shutdown_guard;
    Event mgmt_entered_default_changed;
    Event playback_queued_activate;
    std::atomic<bool> playback_wait_timed_out{false};
    std::atomic<bool> mgmt_join_timed_out{false};
    Event playback_exited;
    Event release_deadlock;

    // Enqueue mgmtthrtask_DefaultAudioDeviceChanged(D2) on SDLWASAPIMgmt first.
    mgmt.proxy([&]() -> bool {
        mgmt_entered_default_changed.signal();
        playback_queued_activate.wait_for(2000ms);

        // Migrate logical devices off D1, then ClosePhysicalAudioDevice(D1):
        d1.lock.lock();
        d1.shutdown.store(1);  // SDL_audio.c:1665
        d1.lock.unlock();      // SDL_audio.c:1668

        // SDL_WaitThread(D1->thread, NULL) (SDL_audio.c:1671) modeled with bounded timeout
        if (!playback_exited.wait_for(kDeadlockTimeout)) {
            mgmt_join_timed_out.store(true);
            release_deadlock.signal();
            playback_exited.wait_for(2000ms);
        }
        return true;
    }, nullptr);

    // PlaybackAudioThread(D1)
    d1.playback_thread = std::thread([&] {
        // RecoverWasapiIfLost checks shutdown == 0 BEFORE ClosePhysicalAudioDevice sets it
        if (d1.shutdown.load() == 0 && d1.device_lost) {
            playback_passed_shutdown_guard.signal();
            mgmt_entered_default_changed.wait_for(2000ms);

            // ActivateWasapiDevice -> synchronous proxy to SDLWASAPIMgmt
            Event sem;
            auto *t = new PendingTask();
            t->fn = [&]() -> bool { return true; };
            t->done_sem = &sem;
            {
                std::lock_guard<std::mutex> lk(mgmt.q_lock);
                mgmt.q.push(t);
            }
            mgmt.q_cv.notify_one();
            playback_queued_activate.signal();

            // Block in SDL_WaitSemaphore(task_complete_sem) (SDL_wasapi.c:158)
            if (!sem.wait_for(kDeadlockTimeout)) {
                playback_wait_timed_out.store(true);
            }
            release_deadlock.wait_for(2000ms);
            playback_exited.signal();
            // Wait for mgmt to finish draining t after playback_exited unblocks mgmt!
            sem.wait_for(2000ms);
            delete t;
            return;
        }
        playback_exited.signal();
    });

    d1.playback_thread.join();
    mgmt.shutdown_and_join();

    if (playback_wait_timed_out.load() && mgmt_join_timed_out.load()) {
        std::printf("H4B_DEADLOCK_VERIFIED\n");
        return 0;
    }
    std::printf("H4B_UNEXPECTED pb_to=%d mgmt_to=%d\n", (int)playback_wait_timed_out.load(), (int)mgmt_join_timed_out.load());
    return 2;
}

static int run_h4b_neg_shutdown_first() {
    SynthMgmtThread mgmt;
    mgmt.start();

    SynthPhysicalDevice d1;
    d1.id = 1;
    d1.currently_opened = true;
    d1.device_lost = true;

    Event shutdown_set;
    Event playback_exited;
    std::atomic<bool> mgmt_join_ok{false};

    mgmt.proxy([&]() -> bool {
        d1.lock.lock();
        d1.shutdown.store(1);
        d1.lock.unlock();
        shutdown_set.signal();
        mgmt_join_ok.store(playback_exited.wait_for(2000ms));
        return true;
    }, nullptr);

    d1.playback_thread = std::thread([&] {
        shutdown_set.wait_for(2000ms);
        // RecoverWasapiIfLost sees shutdown == 1 -> returns false immediately!
        if (d1.shutdown.load() != 0) {
            playback_exited.signal();
            return;
        }
        playback_exited.signal();
    });

    d1.playback_thread.join();
    mgmt.shutdown_and_join();

    if (mgmt_join_ok.load()) {
        std::printf("H4B_NEG_SHUTDOWN_FIRST_PASS\n");
        return 0;
    }
    return 2;
}

// ---------------------------------------------------------------------------
// H4-C: SDL_OpenAudioDevice (WASAPI_OpenDevice) <-> SDLWASAPIMgmt (SDL_DefaultAudioDeviceChanged)
// ---------------------------------------------------------------------------
static int run_h4c_deadlock_window(bool target_d2) {
    SynthMgmtThread mgmt;
    mgmt.start();

    SynthPhysicalDevice d1, d2;
    d1.id = 1;
    d2.id = 2;
    std::atomic<int> default_dev_id{1};

    Event rwlock_updated_to_d2;
    Event app_locked_and_queued;
    std::atomic<bool> app_wait_timed_out{false};
    std::atomic<bool> mgmt_lock_timed_out{false};
    Event mgmt_unblocked;

    // SDLWASAPIMgmt runs mgmtthrtask_DefaultAudioDeviceChanged(D2)
    mgmt.proxy([&]() -> bool {
        default_dev_id.store(2);  // SDL_audio.c:2374, then subsystem_rwlock unlocked at L2377
        rwlock_updated_to_d2.signal();
        app_locked_and_queued.wait_for(2000ms);

        // SDL_audio.c:2393 ObtainPhysicalAudioDeviceObj(D2)
        if (!d2.lock.try_lock_for(kDeadlockTimeout)) {
            mgmt_lock_timed_out.store(true);
            mgmt_unblocked.signal();
            return false;
        }
        // SDL_audio.c:2395 ObtainPhysicalAudioDevice(D1)
        if (!d1.lock.try_lock_for(kDeadlockTimeout)) {
            d2.lock.unlock();
            mgmt_lock_timed_out.store(true);
            mgmt_unblocked.signal();
            return false;
        }
        d1.lock.unlock();
        d2.lock.unlock();
        mgmt_unblocked.signal();
        return true;
    }, nullptr);

    // App / Guest thread calls SDL_OpenAudioDevice(DEFAULT_PLAYBACK) on unopened device
    std::thread app_thr([&] {
        if (target_d2) {
            // Window 1: opens D2 between L2377 and L2393
            rwlock_updated_to_d2.wait_for(2000ms);
        }
        SynthPhysicalDevice &target = target_d2 ? d2 : d1;
        target.lock.lock();  // ObtainPhysicalAudioDeviceDefaultAllowed

        // OpenPhysicalAudioDevice -> !currently_opened -> WASAPI_OpenDevice -> ActivateWasapiDevice
        Event sem;
        auto *t = new PendingTask();
        t->fn = [&]() -> bool { return true; };
        t->done_sem = &sem;
        {
            std::lock_guard<std::mutex> lk(mgmt.q_lock);
            mgmt.q.push(t);
        }
        mgmt.q_cv.notify_one();
        app_locked_and_queued.signal();

        // Block on task_complete_sem WHILE HOLDING target.lock!
        if (!sem.wait_for(kDeadlockTimeout)) {
            app_wait_timed_out.store(true);
        }
        mgmt_unblocked.wait_for(2000ms);
        target.lock.unlock();
        // Now mgmt thread can drain t and signal sem!
        sem.wait_for(2000ms);
        delete t;
    });

    app_thr.join();
    mgmt.shutdown_and_join();

    if (app_wait_timed_out.load() && mgmt_lock_timed_out.load()) {
        std::printf("H4C_DEADLOCK_%s_VERIFIED\n", target_d2 ? "D2" : "D1");
        return 0;
    }
    std::printf("H4C_UNEXPECTED_%s app_to=%d mgmt_to=%d\n",
                target_d2 ? "D2" : "D1", (int)app_wait_timed_out.load(), (int)mgmt_lock_timed_out.load());
    return 2;
}

static int run_h4c_neg_already_opened() {
    SynthMgmtThread mgmt;
    mgmt.start();

    SynthPhysicalDevice d1, d2;
    d1.id = 1;
    d1.currently_opened = true;  // Already open (e.g., movie client 1 opening on active D1)
    d2.id = 2;

    Event app_locked_d1;
    std::atomic<bool> mgmt_ok{false};

    mgmt.proxy([&]() -> bool {
        app_locked_d1.wait_for(2000ms);
        if (!d2.lock.try_lock_for(2000ms)) return false;
        if (!d1.lock.try_lock_for(2000ms)) {
            d2.lock.unlock();
            return false;
        }
        d1.lock.unlock();
        d2.lock.unlock();
        mgmt_ok.store(true);
        return true;
    }, nullptr);

    std::thread app_thr([&] {
        d1.lock.lock();
        app_locked_d1.signal();
        // OpenPhysicalAudioDevice sees d1.currently_opened == true -> returns immediately without mgmt proxy!
        if (!d1.currently_opened) {
            return;
        }
        d1.lock.unlock();
    });

    app_thr.join();
    mgmt.shutdown_and_join();
    if (mgmt_ok.load()) {
        std::printf("H4C_NEG_ALREADY_OPENED_PASS\n");
        return 0;
    }
    return 2;
}

int main(int argc, char **argv) {
    if (argc < 2) {
        std::fprintf(stderr, "Usage: %s <case>\n", argv[0]);
        return 1;
    }
    std::string mode = argv[1];
    if (mode == "h4a_uaf") return run_h4a_uaf();
    if (mode == "h4a_neg_same_format") return run_h4a_neg_same_format();
    if (mode == "h4a_naive_lock") return run_h4a_naive_lock_self_deadlock();
    if (mode == "h4b_deadlock") return run_h4b_deadlock();
    if (mode == "h4b_neg_shutdown_first") return run_h4b_neg_shutdown_first();
    if (mode == "h4c_deadlock_d2") return run_h4c_deadlock_window(true);
    if (mode == "h4c_deadlock_d1") return run_h4c_deadlock_window(false);
    if (mode == "h4c_neg_already_opened") return run_h4c_neg_already_opened();
    std::fprintf(stderr, "Unknown mode: %s\n", mode.c_str());
    return 1;
}
"""


def compile_harness(tmpdir: Path) -> Path:
    src = tmpdir / "g6p138_repro.cpp"
    exe = tmpdir / "g6p138_repro.exe"
    src.write_text(HARNESS_CPP, encoding="utf-8")

    vcvars = os.environ.get("R3HD_VCVARS", DEFAULT_VCVARS)
    llvm_bin = os.environ.get("R3HD_LLVM_BIN", DEFAULT_LLVM_BIN)
    clangxx = str(Path(llvm_bin) / "clang++.exe")

    if os.environ.get("LIB") and os.environ.get("INCLUDE"):
        proc = subprocess.run(
            [clangxx, "-std=c++20", "-O1", "-g", "-fsanitize=address", "-fno-omit-frame-pointer", str(src), "-o", str(exe)],
            capture_output=True,
            text=True,
            timeout=60,
        )
    else:
        bat = tmpdir / "build.bat"
        bat.write_text(
            f'@echo off\r\n'
            f'call "{vcvars}" >nul 2>&1\r\n'
            f'if errorlevel 1 exit /b 2\r\n'
            f'"{clangxx}" -std=c++20 -O1 -g -fsanitize=address -fno-omit-frame-pointer "{src}" -o "{exe}"\r\n',
            encoding="utf-8",
        )
        proc = subprocess.run(["cmd", "/c", str(bat)], capture_output=True, text=True, timeout=60)

    if proc.returncode != 0:
        raise RuntimeError(f"Compilation failed (rc={proc.returncode}):\n{proc.stdout}\n{proc.stderr}")
    return exe


def run_case(exe: Path, mode: str) -> tuple[int, str, str]:
    env = os.environ.copy()
    llvm_bin = os.environ.get("R3HD_LLVM_BIN", DEFAULT_LLVM_BIN)
    extra_paths = [llvm_bin]
    llvm_root = Path(llvm_bin).parent
    for dll in llvm_root.glob("lib/clang/*/lib/windows/clang_rt.asan_dynamic-x86_64.dll"):
        extra_paths.append(str(dll.parent))
    env["PATH"] = ";".join(extra_paths) + ";" + env.get("PATH", "")
    env["ASAN_OPTIONS"] = "detect_leaks=0:abort_on_error=0"
    proc = subprocess.run(
        [str(exe), mode],
        capture_output=True,
        text=True,
        env=env,
        timeout=15,
    )
    return proc.returncode, proc.stdout, proc.stderr


def main() -> int:
    selftest = "--selftest" in sys.argv[1:]
    results: dict[str, bool] = {}

    with tempfile.TemporaryDirectory(prefix="g6p138_repro_") as td:
        exe = compile_harness(Path(td))
        if selftest:
            rc, out, err = run_case(exe, "h4a_neg_same_format")
            results["selftest compiles and runs negative control cleanly"] = (rc == 0 and "H4A_NEG_SAME_FORMAT_PASS" in out)
            rc_bad, _, _ = run_case(exe, "nonexistent_mode")
            results["selftest unknown mode fails closed"] = (rc_bad != 0)
            ok = all(results.values())
            for k, v in results.items():
                print(f"{'PASS' if v else 'FAIL'} {k}")
            print(f"G6P138_SELFTEST {'PASS' if ok else 'FAIL'} {sum(results.values())}/{len(results)}")
            return 0 if ok else 1

        # 1. H4-A fault interleaving -> deterministic ASan heap-use-after-free
        rc, out, err = run_case(exe, "h4a_uaf")
        results["H4-A unlocked recovery format-change + concurrent close triggers ASan heap-use-after-free"] = (
            rc != 0 and "AddressSanitizer: heap-use-after-free" in (out + err)
        )

        # 2. H4-A negative control (same format/sample_frames early return)
        rc, out, err = run_case(exe, "h4a_neg_same_format")
        results["H4-A negative control (unchanged format/frames) passes with 0 ASan errors"] = (
            rc == 0 and "H4A_NEG_SAME_FORMAT_PASS" in out and "AddressSanitizer" not in (out + err)
        )

        # 3. H4-A naive locking self-deadlock on WASAPI_OpenDevice
        rc, out, err = run_case(exe, "h4a_naive_lock")
        results["H4-A naive device->lock in PrepDevice deterministically self-deadlocks WASAPI_OpenDevice"] = (
            rc == 0 and "H4A_NAIVE_LOCK_SELF_DEADLOCK_VERIFIED" in out
        )

        # 4. H4-B mutual deadlock cycle (PlaybackAudioThread Recover <-> SDLWASAPIMgmt ClosePhysical)
        rc, out, err = run_case(exe, "h4b_deadlock")
        results["H4-B RecoverWasapiDevice <-> ClosePhysicalAudioDevice reproduces 2-thread deadlock"] = (
            rc == 0 and "H4B_DEADLOCK_VERIFIED" in out
        )

        # 5. H4-B negative control (shutdown set before RecoverWasapiIfLost check)
        rc, out, err = run_case(exe, "h4b_neg_shutdown_first")
        results["H4-B negative control (shutdown visible before recovery) exits cleanly without deadlock"] = (
            rc == 0 and "H4B_NEG_SHUTDOWN_FIRST_PASS" in out
        )

        # 6. H4-C AB-BA deadlock Window 1 (D2 open between L2377 and L2393)
        rc, out, err = run_case(exe, "h4c_deadlock_d2")
        results["H4-C WASAPI_OpenDevice(D2) <-> SDL_DefaultAudioDeviceChanged(D2) reproduces AB-BA deadlock"] = (
            rc == 0 and "H4C_DEADLOCK_D2_VERIFIED" in out
        )

        # 7. H4-C AB-BA deadlock Window 2 (D1 first-open vs migration off D1)
        rc, out, err = run_case(exe, "h4c_deadlock_d1")
        results["H4-C WASAPI_OpenDevice(D1) <-> SDL_DefaultAudioDeviceChanged(D2) reproduces AB-BA deadlock"] = (
            rc == 0 and "H4C_DEADLOCK_D1_VERIFIED" in out
        )

        # 8. H4-C negative control (device already opened -> early return at L1790, no mgmt proxy)
        rc, out, err = run_case(exe, "h4c_neg_already_opened")
        results["H4-C negative control (already-opened physical device) completes without deadlock"] = (
            rc == 0 and "H4C_NEG_ALREADY_OPENED_PASS" in out
        )

    passed = sum(1 for v in results.values() if v)
    total = len(results)
    for k, v in results.items():
        print(f"{'PASS' if v else 'FAIL'} {k}")
    print(f"G6P138_WASAPI_SYNC_REPRO {'PASS' if passed == total else 'FAIL'} {passed}/{total}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
