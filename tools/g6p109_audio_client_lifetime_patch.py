#!/usr/bin/env python3
"""Replay last in the SDK patch chain (G6-P109, D-346): fix AudioSystem client lifetime hazards.

Pinned ReXGlue SDK (c94f5ebdcb3c9d1a460ca48e04f9758448f8d518) releases `global_critical_region_`
in `AudioSystem::WorkerThreadMain` before invoking `client_callback` without tracking an in-flight
callback or pinning client resources. When `AudioSystem::UnregisterClient` races an in-flight
callback (for example Rayman 3 HD unregistering movie client 1 while "Audio Worker" pumps client
callbacks), three verified defects occur:
  - Hazard A: Release NULL-pointer dereference in `SubmitFrame` (`assert_true` compiles out under NDEBUG).
  - Hazard B: Guest-heap UAF on `wrapped_callback_arg` freed by `SystemHeapFree` while callback uses it.
  - Hazard C: Slot-reuse ABA cross-client frame misdelivery when `RegisterClient` reuses the slot before
    the old callback completes.

This narrow, idempotent patch adds in-flight callback tracking (`in_flight_callbacks`), deferred
teardown (`unregister_pending` + `FinalizeClientLocked` via an RAII scope guard in `WorkerThreadMain`),
slot reservation until quiescence (`FindFreeClient`), locked `Shutdown()` cleanup, and runtime
bounds/null/active checks in `RegisterClient`, `SubmitFrame`, and `UnregisterClient`.
It preserves the SDK pin (c94f5eb), SDL3 pin (8bf3b72), guest-visible XAudio handle encoding
(`0x41550000 | index`), exact line endings, and all unrelated SDK modifications, and fails closed
on source drift.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SDK = ROOT / "external" / "rexglue-sdk"
REL_H = Path("include/rex/audio/audio_system.h")
REL_CPP = Path("src/audio/audio_system.cpp")
TARGET_H = SDK / REL_H
TARGET_CPP = SDK / REL_CPP

EXPECTED_SDK_PIN = "c94f5ebdcb3c9d1a460ca48e04f9758448f8d518"

H_EDITS: list[tuple[str, str, str]] = [
    (
        "clients_struct_and_finalize_decl",
        (
            "  struct {\n"
            "    AudioDriver* driver;\n"
            "    uint32_t callback;\n"
            "    uint32_t callback_arg;\n"
            "    uint32_t wrapped_callback_arg;\n"
            "    bool in_use;\n"
            "  } clients_[kMaximumClientCount];\n"
            "\n"
            "  int FindFreeClient();\n"
        ),
        (
            "  struct {\n"
            "    AudioDriver* driver;\n"
            "    uint32_t callback;\n"
            "    uint32_t callback_arg;\n"
            "    uint32_t wrapped_callback_arg;\n"
            "    bool in_use;\n"
            "    bool unregister_pending;\n"
            "    uint32_t in_flight_callbacks;\n"
            "  } clients_[kMaximumClientCount];\n"
            "\n"
            "  int FindFreeClient();\n"
            "  void FinalizeClientLocked(size_t index);\n"
        ),
    ),
]

CPP_EDITS: list[tuple[str, str, str]] = [
    (
        "worker_dispatch_in_flight_guard",
        (
            "      auto global_lock = global_critical_region_.Acquire();\n"
            "      uint32_t client_callback = clients_[index].callback;\n"
            "      uint32_t client_callback_arg = clients_[index].wrapped_callback_arg;\n"
            "      global_lock.unlock();\n"
            "\n"
            "      if (client_callback) {\n"
            "        if (diag_pump_count < 10) {\n"
            '          REXAPU_DEBUG("AudioWorker: dispatching callback {:08X} with arg {:08X} for client {}",\n'
            "                       client_callback, client_callback_arg, index);\n"
            "        }\n"
            '        SCOPE_profile_cpu_i("apu", "rex::audio::AudioSystem->client_callback");\n'
            "        uint64_t args[] = {client_callback_arg};\n"
            "        function_dispatcher_->Execute(worker_thread_->thread_state(), client_callback, args,\n"
            "                                      rex::countof(args));\n"
            "        if (diag_pump_count < 10) {\n"
            '          REXAPU_DEBUG("AudioWorker: callback returned for client {}", index);\n'
            "        }\n"
            "        diag_pump_count++;\n"
            "      } else {\n"
            '        REXAPU_DEBUG("AudioWorker: semaphore signaled for client {} but callback is 0", index);\n'
            "      }\n"
        ),
        (
            "      auto global_lock = global_critical_region_.Acquire();\n"
            "      uint32_t client_callback = 0;\n"
            "      uint32_t client_callback_arg = 0;\n"
            "      if (index < kMaximumClientCount && clients_[index].in_use &&\n"
            "          !clients_[index].unregister_pending && clients_[index].callback) {\n"
            "        client_callback = clients_[index].callback;\n"
            "        client_callback_arg = clients_[index].wrapped_callback_arg;\n"
            "        ++clients_[index].in_flight_callbacks;\n"
            "      }\n"
            "      global_lock.unlock();\n"
            "\n"
            "      if (client_callback) {\n"
            "        struct InFlightCallbackGuard {\n"
            "          AudioSystem* self;\n"
            "          size_t idx;\n"
            "          ~InFlightCallbackGuard() {\n"
            "            auto lock = self->global_critical_region_.Acquire();\n"
            "            auto& client = self->clients_[idx];\n"
            "            if (client.in_flight_callbacks > 0) {\n"
            "              --client.in_flight_callbacks;\n"
            "            }\n"
            "            if (client.in_flight_callbacks == 0 && client.unregister_pending) {\n"
            "              self->FinalizeClientLocked(idx);\n"
            "            }\n"
            "          }\n"
            "        } in_flight_guard{this, index};\n"
            "\n"
            "        if (diag_pump_count < 10) {\n"
            '          REXAPU_DEBUG("AudioWorker: dispatching callback {:08X} with arg {:08X} for client {}",\n'
            "                       client_callback, client_callback_arg, index);\n"
            "        }\n"
            '        SCOPE_profile_cpu_i("apu", "rex::audio::AudioSystem->client_callback");\n'
            "        uint64_t args[] = {client_callback_arg};\n"
            "        function_dispatcher_->Execute(worker_thread_->thread_state(), client_callback, args,\n"
            "                                      rex::countof(args));\n"
            "        if (diag_pump_count < 10) {\n"
            '          REXAPU_DEBUG("AudioWorker: callback returned for client {}", index);\n'
            "        }\n"
            "        diag_pump_count++;\n"
            "      } else {\n"
            '        REXAPU_DEBUG("AudioWorker: semaphore signaled for client {} but callback is 0", index);\n'
            "      }\n"
        ),
    ),
    (
        "find_free_client_slot_reservation",
        (
            "int AudioSystem::FindFreeClient() {\n"
            "  for (size_t i = 0; i < kMaximumClientCount; i++) {\n"
            "    auto& client = clients_[i];\n"
            "    if (!client.in_use) {\n"
            "      return i;\n"
            "    }\n"
            "  }\n"
            "\n"
            "  return -1;\n"
            "}\n"
        ),
        (
            "int AudioSystem::FindFreeClient() {\n"
            "  for (size_t i = 0; i < kMaximumClientCount; i++) {\n"
            "    auto& client = clients_[i];\n"
            "    if (!client.in_use && !client.unregister_pending && client.in_flight_callbacks == 0) {\n"
            "      return i;\n"
            "    }\n"
            "  }\n"
            "\n"
            "  return -1;\n"
            "}\n"
        ),
    ),
    (
        "shutdown_locked_finalize",
        (
            "void AudioSystem::Shutdown() {\n"
            "  if (!worker_running_) {\n"
            "    return;\n"
            "  }\n"
            "\n"
            "  // Shut down XMA decoder first - its worker can stall in FFmpeg\n"
            "  if (xma_decoder_) {\n"
            "    xma_decoder_->Shutdown();\n"
            "  }\n"
            "\n"
            "  worker_running_ = false;\n"
            "  shutdown_event_->Set();\n"
            "  if (worker_thread_) {\n"
            "    // The worker may be stuck inside a guest callback that is itself blocked on\n"
            "    // guest objects (e.g. KeWaitForMultipleObjects), so terminating is the last\n"
            "    // resort. Give it a chance to unwind first: TerminateThread abandons any\n"
            "    // lock the thread holds, including the CRT heap lock.\n"
            "    rex::thread::Thread* host_thread = worker_thread_->thread();\n"
            "    bool exited = host_thread && rex::thread::Wait(host_thread, false, kWorkerShutdownTimeout) ==\n"
            "                                     rex::thread::WaitResult::kSuccess;\n"
            "    if (!exited) {\n"
            '      REXAPU_WARN("Audio worker did not exit within {} ms; terminating",\n'
            "                  kWorkerShutdownTimeout.count());\n"
            "      worker_thread_->Terminate(0);\n"
            "    }\n"
            "    worker_thread_.reset();\n"
            "  }\n"
            "\n"
            "  // Destroy all active client drivers (closes SDL audio devices, stopping\n"
            "  // callback threads) before the semaphores they reference are destroyed.\n"
            "  for (size_t i = 0; i < kMaximumClientCount; i++) {\n"
            "    if (clients_[i].in_use) {\n"
            "      DestroyDriver(clients_[i].driver);\n"
            "      if (clients_[i].wrapped_callback_arg) {\n"
            "        memory()->SystemHeapFree(clients_[i].wrapped_callback_arg);\n"
            "      }\n"
            "      clients_[i] = {nullptr, 0, 0, 0, false};\n"
            "    }\n"
            "  }\n"
            "}\n"
        ),
        (
            "void AudioSystem::Shutdown() {\n"
            "  if (worker_running_) {\n"
            "    // Shut down XMA decoder first - its worker can stall in FFmpeg\n"
            "    if (xma_decoder_) {\n"
            "      xma_decoder_->Shutdown();\n"
            "    }\n"
            "\n"
            "    worker_running_ = false;\n"
            "    shutdown_event_->Set();\n"
            "    if (worker_thread_) {\n"
            "      // The worker may be stuck inside a guest callback that is itself blocked on\n"
            "      // guest objects (e.g. KeWaitForMultipleObjects), so terminating is the last\n"
            "      // resort. Give it a chance to unwind first: TerminateThread abandons any\n"
            "      // lock the thread holds, including the CRT heap lock.\n"
            "      rex::thread::Thread* host_thread = worker_thread_->thread();\n"
            "      bool exited = host_thread && rex::thread::Wait(host_thread, false, kWorkerShutdownTimeout) ==\n"
            "                                       rex::thread::WaitResult::kSuccess;\n"
            "      if (!exited) {\n"
            '        REXAPU_WARN("Audio worker did not exit within {} ms; terminating",\n'
            "                    kWorkerShutdownTimeout.count());\n"
            "        worker_thread_->Terminate(0);\n"
            "      }\n"
            "      worker_thread_.reset();\n"
            "    }\n"
            "  }\n"
            "\n"
            "  // Destroy all active or deferred-unregister client drivers (closes SDL audio\n"
            "  // devices, stopping callback threads) before the semaphores they reference\n"
            "  // are destroyed.\n"
            "  auto global_lock = global_critical_region_.Acquire();\n"
            "  for (size_t i = 0; i < kMaximumClientCount; i++) {\n"
            "    if (clients_[i].in_use || clients_[i].driver || clients_[i].wrapped_callback_arg) {\n"
            "      FinalizeClientLocked(i);\n"
            "    }\n"
            "  }\n"
            "}\n"
        ),
    ),
    (
        "register_submit_unregister_finalize",
        (
            "X_STATUS AudioSystem::RegisterClient(uint32_t callback, uint32_t callback_arg, size_t* out_index) {\n"
            '  REXAPU_DEBUG("AudioSystem::RegisterClient: callback={:08X} callback_arg={:08X}", callback,\n'
            "               callback_arg);\n"
            "  auto global_lock = global_critical_region_.Acquire();\n"
            "\n"
            "  auto index = FindFreeClient();\n"
            "  assert_true(index >= 0);\n"
            '  REXAPU_DEBUG("AudioSystem::RegisterClient: using client index={} queued_frames={}", index,\n'
            "               queued_frames_);\n"
            "\n"
            "  auto client_semaphore = client_semaphores_[index].get();\n"
            "  auto ret = client_semaphore->Release(queued_frames_, nullptr);\n"
            "  assert_true(ret);\n"
            "\n"
            "  AudioDriver* driver;\n"
            "  auto result = CreateDriver(index, client_semaphore, &driver);\n"
            "  if (XFAILED(result)) {\n"
            "    return result;\n"
            "  }\n"
            "  assert_not_null(driver);\n"
            "\n"
            "  uint32_t ptr = memory()->SystemHeapAlloc(0x4);\n"
            "  memory::store_and_swap<uint32_t>(memory()->TranslateVirtual(ptr), callback_arg);\n"
            "\n"
            "  clients_[index] = {driver, callback, callback_arg, ptr, true};\n"
            "\n"
            "  if (out_index) {\n"
            "    *out_index = index;\n"
            "  }\n"
            "\n"
            "  return X_STATUS_SUCCESS;\n"
            "}\n"
            "\n"
            "void AudioSystem::SubmitFrame(size_t index, uint32_t samples_ptr) {\n"
            '  SCOPE_profile_cpu_f("apu");\n'
            "\n"
            "  static uint32_t submit_count = 0;\n"
            "  if (submit_count < 10) {\n"
            '    REXAPU_DEBUG("AudioSystem::SubmitFrame called: index={} samples_ptr={:08X}", index,\n'
            "                 samples_ptr);\n"
            "    submit_count++;\n"
            "  }\n"
            "\n"
            "  auto global_lock = global_critical_region_.Acquire();\n"
            "  assert_true(index < kMaximumClientCount);\n"
            "  assert_true(clients_[index].driver != NULL);\n"
            "  (clients_[index].driver)->SubmitFrame(samples_ptr);\n"
            "}\n"
            "\n"
            "void AudioSystem::UnregisterClient(size_t index) {\n"
            '  SCOPE_profile_cpu_f("apu");\n'
            "\n"
            "  auto global_lock = global_critical_region_.Acquire();\n"
            "  assert_true(index < kMaximumClientCount);\n"
            "  DestroyDriver(clients_[index].driver);\n"
            "  memory()->SystemHeapFree(clients_[index].wrapped_callback_arg);\n"
            "  clients_[index] = {nullptr, 0, 0, 0, false};\n"
            "\n"
            "  // Drain the semaphore of its count.\n"
            "  auto client_semaphore = client_semaphores_[index].get();\n"
            "  rex::thread::WaitResult wait_result;\n"
            "  do {\n"
            "    wait_result = rex::thread::Wait(client_semaphore, false, std::chrono::milliseconds(0));\n"
            "  } while (wait_result == rex::thread::WaitResult::kSuccess);\n"
            "  assert_true(wait_result == rex::thread::WaitResult::kTimeout);\n"
            "}\n"
        ),
        (
            "void AudioSystem::FinalizeClientLocked(size_t index) {\n"
            "  if (index >= kMaximumClientCount) {\n"
            "    return;\n"
            "  }\n"
            "  auto& client = clients_[index];\n"
            "  AudioDriver* driver = client.driver;\n"
            "  uint32_t wrapped_callback_arg = client.wrapped_callback_arg;\n"
            "  client = {nullptr, 0, 0, 0, false, false, 0};\n"
            "\n"
            "  if (driver) {\n"
            "    DestroyDriver(driver);\n"
            "  }\n"
            "  if (wrapped_callback_arg) {\n"
            "    memory()->SystemHeapFree(wrapped_callback_arg);\n"
            "  }\n"
            "\n"
            "  // Drain the semaphore of its count.\n"
            "  auto client_semaphore = client_semaphores_[index].get();\n"
            "  rex::thread::WaitResult wait_result;\n"
            "  do {\n"
            "    wait_result = rex::thread::Wait(client_semaphore, false, std::chrono::milliseconds(0));\n"
            "  } while (wait_result == rex::thread::WaitResult::kSuccess);\n"
            "  assert_true(wait_result == rex::thread::WaitResult::kTimeout);\n"
            "}\n"
            "\n"
            "X_STATUS AudioSystem::RegisterClient(uint32_t callback, uint32_t callback_arg, size_t* out_index) {\n"
            '  REXAPU_DEBUG("AudioSystem::RegisterClient: callback={:08X} callback_arg={:08X}", callback,\n'
            "               callback_arg);\n"
            "  auto global_lock = global_critical_region_.Acquire();\n"
            "\n"
            "  auto index = FindFreeClient();\n"
            "  if (index < 0) {\n"
            '    REXAPU_WARN("AudioSystem::RegisterClient: no free client slots");\n'
            "    return X_STATUS_UNSUCCESSFUL;\n"
            "  }\n"
            '  REXAPU_DEBUG("AudioSystem::RegisterClient: using client index={} queued_frames={}", index,\n'
            "               queued_frames_);\n"
            "\n"
            "  auto client_semaphore = client_semaphores_[index].get();\n"
            "  auto ret = client_semaphore->Release(queued_frames_, nullptr);\n"
            "  assert_true(ret);\n"
            "\n"
            "  AudioDriver* driver = nullptr;\n"
            "  auto result = CreateDriver(index, client_semaphore, &driver);\n"
            "  if (XFAILED(result)) {\n"
            "    rex::thread::WaitResult wait_result;\n"
            "    do {\n"
            "      wait_result = rex::thread::Wait(client_semaphore, false, std::chrono::milliseconds(0));\n"
            "    } while (wait_result == rex::thread::WaitResult::kSuccess);\n"
            "    return result;\n"
            "  }\n"
            "  assert_not_null(driver);\n"
            "\n"
            "  uint32_t ptr = memory()->SystemHeapAlloc(0x4);\n"
            "  memory::store_and_swap<uint32_t>(memory()->TranslateVirtual(ptr), callback_arg);\n"
            "\n"
            "  clients_[index] = {driver, callback, callback_arg, ptr, true, false, 0};\n"
            "\n"
            "  if (out_index) {\n"
            "    *out_index = index;\n"
            "  }\n"
            "\n"
            "  return X_STATUS_SUCCESS;\n"
            "}\n"
            "\n"
            "void AudioSystem::SubmitFrame(size_t index, uint32_t samples_ptr) {\n"
            '  SCOPE_profile_cpu_f("apu");\n'
            "\n"
            "  static uint32_t submit_count = 0;\n"
            "  if (submit_count < 10) {\n"
            '    REXAPU_DEBUG("AudioSystem::SubmitFrame called: index={} samples_ptr={:08X}", index,\n'
            "                 samples_ptr);\n"
            "    submit_count++;\n"
            "  }\n"
            "\n"
            "  auto global_lock = global_critical_region_.Acquire();\n"
            "  if (index >= kMaximumClientCount) {\n"
            '    REXAPU_WARN("AudioSystem::SubmitFrame: invalid client index {}", index);\n'
            "    return;\n"
            "  }\n"
            "  auto& client = clients_[index];\n"
            "  if (!client.in_use || client.unregister_pending || !client.driver) {\n"
            "    return;\n"
            "  }\n"
            "  client.driver->SubmitFrame(samples_ptr);\n"
            "}\n"
            "\n"
            "void AudioSystem::UnregisterClient(size_t index) {\n"
            '  SCOPE_profile_cpu_f("apu");\n'
            "\n"
            "  auto global_lock = global_critical_region_.Acquire();\n"
            "  if (index >= kMaximumClientCount) {\n"
            '    REXAPU_WARN("AudioSystem::UnregisterClient: invalid client index {}", index);\n'
            "    return;\n"
            "  }\n"
            "  auto& client = clients_[index];\n"
            "  if (!client.in_use || client.unregister_pending) {\n"
            "    return;\n"
            "  }\n"
            "  client.unregister_pending = true;\n"
            "  client.callback = 0;\n"
            "  if (client.in_flight_callbacks == 0) {\n"
            "    FinalizeClientLocked(index);\n"
            "  }\n"
            "}\n"
        ),
    ),
    (
        "save_skip_unregister_pending",
        (
            "  uint32_t used_clients = 0;\n"
            "  for (size_t i = 0; i < kMaximumClientCount; i++) {\n"
            "    if (clients_[i].in_use) {\n"
            "      used_clients++;\n"
            "    }\n"
            "  }\n"
            "\n"
            "  stream->Write(used_clients);\n"
            "  for (uint32_t i = 0; i < kMaximumClientCount; i++) {\n"
            "    auto& client = clients_[i];\n"
            "    if (!client.in_use) {\n"
            "      continue;\n"
            "    }\n"
        ),
        (
            "  uint32_t used_clients = 0;\n"
            "  for (size_t i = 0; i < kMaximumClientCount; i++) {\n"
            "    if (clients_[i].in_use && !clients_[i].unregister_pending) {\n"
            "      used_clients++;\n"
            "    }\n"
            "  }\n"
            "\n"
            "  stream->Write(used_clients);\n"
            "  for (uint32_t i = 0; i < kMaximumClientCount; i++) {\n"
            "    auto& client = clients_[i];\n"
            "    if (!client.in_use || client.unregister_pending) {\n"
            "      continue;\n"
            "    }\n"
        ),
    ),
    (
        "restore_clear_pending_fields",
        (
            "    client.in_use = true;\n"
            "\n"
            "    auto client_semaphore = client_semaphores_[id].get();\n"
        ),
        (
            "    client.in_use = true;\n"
            "    client.unregister_pending = false;\n"
            "    client.in_flight_callbacks = 0;\n"
            "\n"
            "    auto client_semaphore = client_semaphores_[id].get();\n"
        ),
    ),
]


def _detect_eol(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"


def apply_edits_text(
    text: str, edits: list[tuple[str, str, str]], label: str
) -> tuple[str, str]:
    """Apply ordered hunks idempotently, failing closed on source drift."""
    eol = _detect_eol(text)
    norm = text.replace("\r\n", "\n")

    statuses: list[str] = []
    for name, before_lf, after_lf in edits:
        before_count = norm.count(before_lf)
        after_count = norm.count(after_lf)
        if after_count == 1 and before_count == 0:
            statuses.append("already_applied")
        elif before_count == 1 and after_count == 0:
            norm = norm.replace(before_lf, after_lf, 1)
            statuses.append("patched")
        else:
            raise RuntimeError(
                f"{label} source drift detected in hunk '{name}': "
                f"before_count={before_count}, after_count={after_count}"
            )

    if all(s == "already_applied" for s in statuses):
        return text, "already_applied"
    if all(s == "patched" for s in statuses):
        out = norm.replace("\n", "\r\n") if eol == "\r\n" else norm
        return out, "patched"
    raise RuntimeError(
        f"{label} partial patch drift detected: statuses={statuses}"
    )


def apply_header_text(text: str) -> tuple[str, str]:
    return apply_edits_text(text, H_EDITS, REL_H.as_posix())


def apply_source_text(text: str) -> tuple[str, str]:
    return apply_edits_text(text, CPP_EDITS, REL_CPP.as_posix())


def verify_pin(sdk_dir: Path = SDK) -> None:
    sdk_head = subprocess.check_output(
        ["git", "-C", str(sdk_dir), "rev-parse", "HEAD"], text=True
    ).strip()
    if sdk_head != EXPECTED_SDK_PIN:
        raise RuntimeError(f"SDK pin mismatch: expected {EXPECTED_SDK_PIN}, got {sdk_head}")


def patch_file(
    path: Path,
    apply_fn,
    check_only: bool = False,
) -> str:
    if not path.is_file():
        raise RuntimeError(f"Target file not found: {path}")
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    new_text, status = apply_fn(text)
    if check_only:
        if status != "already_applied":
            raise RuntimeError(f"G6-P109 AudioSystem patch not applied to {path} (status={status})")
        return status
    if status == "patched":
        path.write_bytes(new_text.encode("utf-8"))
    return status


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    check_only = "--check" in args
    verify_pin()
    h_status = patch_file(TARGET_H, apply_header_text, check_only=check_only)
    cpp_status = patch_file(TARGET_CPP, apply_source_text, check_only=check_only)
    print(f"g6p109_audio_client_lifetime_patch: {h_status} {REL_H.as_posix()}")
    print(f"g6p109_audio_client_lifetime_patch: {cpp_status} {REL_CPP.as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
