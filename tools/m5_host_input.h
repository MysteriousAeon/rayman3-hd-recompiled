// Test-only host SDL events. No guest memory or input API results are modified.
#pragma once
#include <rex/ui/window_sdl.h>
#include <chrono>
#include <cstdio>
#include <fstream>
#include <string>
#include <thread>
#include <cstdlib>
#include <rex/logging.h>
class M5HostInput {
  std::jthread worker_;
 public:
  void Stop() { worker_.request_stop(); if (worker_.joinable()) worker_.join(); }
  void Start(rex::ui::Window* window) {
    const char* path = std::getenv("R3HD_INPUT_SCHEDULE");
    if (!path) return;
    if (!window) { REXLOG_ERROR("M5 schedule no_window"); return; }
    worker_ = std::jthread([file = std::string(path), window](std::stop_token stop) {
      auto start = std::chrono::steady_clock::now();
      std::ifstream input(file);
      // R3HD_INPUT_FOLLOW: keep reading lines appended by a closed-loop test driver
      // (tools/m5_flight_pilot.py). Events still enter through WindowSDL only.
      const bool follow = std::getenv("R3HD_INPUT_FOLLOW") != nullptr;
      unsigned ms, scan, down;
      for (;;) {
        auto position = input.tellg();
        std::string line;
        const bool got = bool(std::getline(input, line));
        if (!got || (follow && input.eof())) {  // nothing yet, or a partially written line
          if (!follow || stop.stop_requested()) break;
          input.clear(); input.seekg(position);
          std::this_thread::sleep_for(std::chrono::milliseconds(5));
          continue;
        }
        if (std::sscanf(line.c_str(), "%u %u %u", &ms, &scan, &down) != 3) continue;
        while (!stop.stop_requested() && std::chrono::steady_clock::now() - start < std::chrono::milliseconds(ms))
          std::this_thread::sleep_for(std::chrono::milliseconds(5));
        if (stop.stop_requested()) break;
        auto actual = std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now() - start).count();
        window->app_context().CallInUIThreadDeferred([window, ms, actual, scan, down] {
          SDL_Event event{};
          event.type = down ? SDL_EVENT_KEY_DOWN : SDL_EVENT_KEY_UP;
          event.key.scancode = SDL_Scancode(scan);
          event.key.down = down != 0;
          static_cast<rex::ui::WindowSDL*>(window)->HandleKeyEvent(event);
          REXLOG_INFO("M5 schedule planned_ms={} actual_ms={} scancode={} down={} dispatched=true", ms, actual, scan, down);
        });
      }
    });
  }
};
