"""M6 host timer, disable SDL schedule in hidden mode, add controller regression."""
from m2_prepare import ROOT, W, write_text_if_changed
if __name__ == '__main__':
    p = W/'src/m5_host_input.h'
    text = (ROOT/'tools/m5_host_input.h').read_text()
    text = text.replace('    const char* path =', '''    if (std::getenv("R3HD_NONINTRUSIVE")) {
      const char* duration = std::getenv("R3HD_TEST_SECONDS");
      if (!duration) return;
      int seconds = std::atoi(duration);
      if (seconds < 1 || seconds > 1500) return;
      worker_ = std::jthread([window, seconds](std::stop_token stop) {
        auto end = std::chrono::steady_clock::now() + std::chrono::seconds(seconds);
        while (!stop.stop_requested() && std::chrono::steady_clock::now() < end)
          std::this_thread::sleep_for(std::chrono::milliseconds(10));
        if (!stop.stop_requested()) window->app_context().CallInUIThreadDeferred([window] {
          REXLOG_INFO("M6 bounded_exit request_close=true"); window->RequestClose();
        });
      });
      REXLOG_INFO("M6 input source=XAM_schedule desktop_events=false");
      return;
    }
    const char* path =''')
    write_text_if_changed(p, text)
    p = W/'CMakeLists.txt'
    mark = '\n# --- Milestone 6 targets ---\n'
    write_text_if_changed(p, p.read_text().split(mark)[0] + mark + '''add_executable(m6_input_test "${CMAKE_CURRENT_SOURCE_DIR}/../../../tools/m6_input_test.cpp")
target_compile_features(m6_input_test PRIVATE cxx_std_20)
''')
