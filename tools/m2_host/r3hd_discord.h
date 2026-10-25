#pragma once
// D-096: documented Discord RPC v1, Windows local IPC only. No Discord SDK binary.
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#include <nlohmann/json.hpp>
#include <array>
#include <cstdlib>
#include <ctime>
#include <string>
#include <string_view>
#include <cstdint>
#include <thread>

namespace r3hd {
class DiscordPresence {
 public:
  DiscordPresence() = default;
  DiscordPresence(const DiscordPresence&) = delete;
  DiscordPresence& operator=(const DiscordPresence&) = delete;
  ~DiscordPresence() { Stop(); }

  static bool Enabled() noexcept {
    const char* preference = std::getenv("R3HD_DISCORD");
    return !std::getenv("R3HD_NONINTRUSIVE") &&
           (!preference || std::string_view(preference) != "off");
  }
  void Start() noexcept {
    if (Enabled()) StartWorker();
  }
  void Stop() noexcept {
    if (!stop_) return;
    SetEvent(stop_);
    if (worker_.joinable()) worker_.join();
    CloseHandle(stop_);
    stop_ = nullptr;
  }

#ifdef R3HD_DISCORD_TEST
  // Test executable only: never connects to the person's Discord pipe.
  void StartTest(std::wstring prefix, DWORD retry = 50) noexcept {
    if (stop_) return;  // keep repeated test starts from mutating the worker's prefix
    prefix_ = std::move(prefix);
    retry_ = retry;
    StartWorker();
  }
#endif

 private:
  HANDLE stop_ = nullptr;
  std::thread worker_;
  std::wstring prefix_ = L"\\\\?\\pipe\\discord-ipc-";
  DWORD retry_ = 15000;
  std::time_t started_ = 0;

  struct Handle {
    HANDLE value;
    ~Handle() { if (value && value != INVALID_HANDLE_VALUE) CloseHandle(value); }
  };
  void StartWorker() noexcept {
    if (stop_) return;
    stop_ = CreateEventW(nullptr, TRUE, FALSE, nullptr);
    if (!stop_) return;
    started_ = std::time(nullptr);  // once per game session, including reconnects
    try { worker_ = std::thread([this] { try { Run(); } catch (...) {} }); }
    catch (...) { CloseHandle(stop_); stop_ = nullptr; }
  }

  // Each request is overlapped, interruptible, and bounded. No I/O on a guest/render thread.
  bool Transfer(HANDLE pipe, void* data, DWORD size, bool write,
                DWORD timeout, bool stopping = false) {
    auto* bytes = static_cast<char*>(data);
    const auto deadline = timeout == INFINITE ? 0 : GetTickCount64() + timeout;
    while (size) {
      Handle event{CreateEventW(nullptr, TRUE, FALSE, nullptr)};
      if (!event.value) return false;
      OVERLAPPED ov{};
      ov.hEvent = event.value;
      DWORD done = 0;
      BOOL ok = write ? WriteFile(pipe, bytes, size, &done, &ov)
                      : ReadFile(pipe, bytes, size, &done, &ov);
      if (!ok && GetLastError() == ERROR_IO_PENDING) {
        HANDLE waits[] = {stop_, event.value};
        DWORD remaining = INFINITE;
        if (timeout != INFINITE) {
          const auto now = GetTickCount64();
          remaining = now >= deadline ? 0 : static_cast<DWORD>(deadline - now);
        }
        DWORD result = stopping ? WaitForSingleObject(event.value, remaining)
                                : WaitForMultipleObjects(2, waits, FALSE, remaining);
        if (result != (stopping ? WAIT_OBJECT_0 : WAIT_OBJECT_0 + 1)) {
          CancelIoEx(pipe, &ov);
          GetOverlappedResult(pipe, &ov, &done, TRUE); // reclaim before stack OVERLAPPED dies
          return false;
        }
        ok = GetOverlappedResult(pipe, &ov, &done, FALSE);
      }
      if (!ok || !done) return false;
      bytes += done;
      size -= done;
      if (!stopping && WaitForSingleObject(stop_, 0) == WAIT_OBJECT_0) return false;
    }
    return true;
  }
  bool Send(HANDLE pipe, uint32_t opcode, const std::string& payload, bool stopping = false) {
    std::array<uint32_t, 2> header{opcode, static_cast<uint32_t>(payload.size())};
    return Transfer(pipe, header.data(), 8, true, stopping ? 100 : 2000, stopping) &&
           Transfer(pipe, const_cast<char*>(payload.data()), header[1], true,
                    stopping ? 100 : 2000, stopping);
  }
  bool Receive(HANDLE pipe, uint32_t& opcode, std::string& payload, DWORD timeout) {
    std::array<uint32_t, 2> header{};
    if (!Transfer(pipe, header.data(), 8, false, timeout) || header[1] > 65536) return false;
    opcode = header[0];
    payload.resize(header[1]);
    return payload.empty() || Transfer(pipe, payload.data(), header[1], false, 2000);
  }
  std::string Activity(bool clear = false) const {
    using nlohmann::json;
    json activity = nullptr;
    if (!clear) activity = {{"type", 0}, {"timestamps", {{"start", started_}}},
                           {"assets", {{"large_image", "rayman3hd"}}}};
    return json{{"cmd", "SET_ACTIVITY"}, {"args", {{"pid", GetCurrentProcessId()},
                  {"activity", activity}}}, {"nonce", clear ? "clear" : "session"}}.dump();
  }
  void Session(HANDLE pipe) {
    if (!Send(pipe, 0, R"({"v":1,"client_id":"1561411727084486686"})")) return;
    uint32_t opcode;
    std::string payload;
    if (!Receive(pipe, opcode, payload, 3000) || opcode != 1) return;
    auto ready = nlohmann::json::parse(payload, nullptr, false);
    if (!ready.is_object()) return;
    auto event = ready.find("evt");
    if (event == ready.end() || *event != "READY") return;
    if (!Send(pipe, 1, Activity())) return;
    // An idle connection sleeps in an interruptible read: no frame polling or refresh loop.
    while (Receive(pipe, opcode, payload, INFINITE)) {
      if (opcode == 2) break;
      if (opcode == 3) { if (!Send(pipe, 4, payload)) break; }
      else if (opcode == 1) {
        auto reply = nlohmann::json::parse(payload, nullptr, false);
        if (!reply.is_object()) break;
        auto evt = reply.find("evt");
        if (evt != reply.end() && *evt == "ERROR") break;
      } else if (opcode != 4) break;
    }
    // Best effort clear, never wait for a reply at shutdown. Closing IPC also ends the session.
    if (WaitForSingleObject(stop_, 0) == WAIT_OBJECT_0) Send(pipe, 1, Activity(true), true);
  }
  void Run() {
    while (WaitForSingleObject(stop_, 0) != WAIT_OBJECT_0) {
      for (int index = 0; index < 10; ++index) {
        if (WaitForSingleObject(stop_, 0) == WAIT_OBJECT_0) return;
        const auto name = prefix_ + std::to_wstring(index);
        Handle pipe{CreateFileW(name.c_str(), GENERIC_READ | GENERIC_WRITE, 0, nullptr,
                               OPEN_EXISTING, FILE_FLAG_OVERLAPPED | SECURITY_SQOS_PRESENT |
                               SECURITY_IDENTIFICATION, nullptr)};
        if (pipe.value == INVALID_HANDLE_VALUE) continue;
        Session(pipe.value);
        break;
      }
      if (WaitForSingleObject(stop_, retry_) == WAIT_OBJECT_0) return;
    }
  }
};
}  // namespace r3hd
