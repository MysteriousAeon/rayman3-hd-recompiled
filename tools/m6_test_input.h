// Test-only controller source. Schedule vocabulary retains M5 SDL scancode IDs,
// but no SDL or desktop input events are emitted. Used only at the XAM boundary.
#pragma once
#include <array>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <mutex>
#include <string>
namespace m6input {
inline bool Enabled() { return std::getenv("R3HD_NONINTRUSIVE") != nullptr; }
struct State { unsigned packet = 0; unsigned short buttons = 0; short lx=0, ly=0, rx=0, ry=0; unsigned char lt=0, rt=0; };
class Source {
  std::ifstream file_;
  std::chrono::steady_clock::time_point start_ = std::chrono::steady_clock::now();
  std::array<bool, 256> held_{};
  unsigned short pending_ = 0;
  State previous_{};
  // Scancodes 300..303 set an analog axis (lx, ly, rx, ry) to the signed third field;
  // a nonzero analog value replaces the digital key pair for that axis.
  std::array<int, 4> analog_{};
  unsigned ms_=0, scan_=0; int down_=0;
  bool waiting_=false;
 public:
  explicit Source(const char* path) : file_(path ? path : "") {}
  static unsigned short Button(unsigned scan) {
    switch(scan) { case 40: case 27: return 0x10; case 44: case 51: return 0x1000;
      case 15: return 0x4000; case 19: return 0x8000; case 52: case 42: return 0x2000;
      case 30: return 0x100; case 32: return 0x200; case 29: case 43: return 0x20;
      default: return 0; }
  }
  // Null queries don't consume a pending discrete press.
  State Sample(unsigned elapsed, bool consume=true) {
    for (;;) {
      if (!waiting_) {
        auto pos = file_.tellg(); std::string line;
        if (!std::getline(file_, line) || file_.eof()) {
          file_.clear(); file_.seekg(pos); break; // retry incomplete appended line
        }
        if (std::sscanf(line.c_str(), "%u %u %d", &ms_, &scan_, &down_) != 3) continue;
        waiting_=true;
      }
      if (ms_ > elapsed) break;
      waiting_=false;
      if (scan_ >= 300 && scan_ <= 303) { analog_[scan_-300] = down_ < -32767 ? -32767 : down_ > 32767 ? 32767 : down_; continue; }
      if (scan_ >= held_.size() || down_ < 0 || down_ > 1) continue;
      if (down_ && !held_[scan_]) pending_ |= Button(scan_);
      held_[scan_]=down_ != 0;
    }
    State s;
    for (unsigned i=0; i<held_.size(); ++i) if (held_[i]) s.buttons |= Button(i);
    s.buttons |= pending_;
    s.lx = short((int(held_[7])-int(held_[4]))*32767);
    s.ly = short((int(held_[26])-int(held_[22]))*32767);
    s.rx = short((int(held_[79])-int(held_[80]))*32767);
    s.ry = short((int(held_[82])-int(held_[81]))*32767);
    if (analog_[0]) s.lx = short(analog_[0]); if (analog_[1]) s.ly = short(analog_[1]);
    if (analog_[2]) s.rx = short(analog_[2]); if (analog_[3]) s.ry = short(analog_[3]);
    s.lt = (held_[20] || held_[12]) ? 255 : 0; s.rt = (held_[8] || held_[18]) ? 255 : 0;
    s.packet = previous_.packet + (s.buttons != previous_.buttons || s.lx != previous_.lx || s.ly != previous_.ly || s.rx != previous_.rx || s.ry != previous_.ry || s.lt != previous_.lt || s.rt != previous_.rt);
    previous_=s;
    if (consume) pending_=0;
    return s;
  }
  State SampleNow(bool consume) {
    return Sample(unsigned(std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now()-start_).count()), consume);
  }
};
inline State Sample(bool consume) {
  static std::mutex lock; std::lock_guard guard(lock);
  static Source source(std::getenv("R3HD_INPUT_SCHEDULE"));
  return source.SampleNow(consume);
}
}
