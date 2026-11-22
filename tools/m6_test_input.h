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
// G6-P77 (test only, hidden runs): R3HD_TEST_INPUT_USER names the guest user that receives the schedule.
// Unset or "0" keeps the M6 behaviour (schedule on user 0, users 1-3 not connected). "1".."3" moves the
// schedule to that user; user 0 then stays an idle connected pad, as the keyboard keeps user 0 connected in a
// normal session. Any other value is invalid and fails closed: no user receives input at all.
enum Route { kNotConnected = 0, kSchedule = 1, kIdle = 2 };
inline int ParseTestUser(const char* text) {
  if (!text || !*text) return 0;
  if (text[1] == '\0' && text[0] >= '0' && text[0] <= '3') return text[0] - '0';
  return -1;
}
inline Route RouteFor(unsigned user, int test_user) {
  if (test_user < 0) return kNotConnected;
  if (user == unsigned(test_user)) return kSchedule;
  if (user == 0) return kIdle;
  return kNotConnected;
}
inline int TestUser() {
  static const int user = ParseTestUser(std::getenv("R3HD_TEST_INPUT_USER"));
  return user;
}
// G6-P79 (test only): the schedule may also re-route itself at run time. Scancode 310+N (N = 0..3, value 1) moves
// the schedule to guest user N from then on; the users that had it stay connected and idle. Scancode 320+N with
// value 1 disconnects guest user N (not connected), value 0 reconnects it. Schedules without these codes route
// exactly as RouteFor(user, test_user); the codes were ignored before G6-P79.
struct Routing {
  int schedule_user = 0;     // -1: invalid R3HD_TEST_INPUT_USER, nobody connected (fail closed)
  unsigned seen_mask = 0;    // users that have had the schedule: idle when they no longer have it
  unsigned disconnected = 0; // users disconnected by code 320+N
};
inline Route RouteFor(unsigned user, const Routing& r) {
  if (r.schedule_user < 0 || user > 3) return kNotConnected;
  if (r.disconnected & (1u << user)) return kNotConnected;
  if (user == unsigned(r.schedule_user)) return kSchedule;
  if (user == 0 || (r.seen_mask & (1u << user))) return kIdle;
  return kNotConnected;
}
// Applies a route code to r; returns false for any other scancode.
inline bool ApplyRouteCode(Routing& r, unsigned scan, int down) {
  if (scan >= 310 && scan <= 313 && down == 1) {
    if (r.schedule_user < 0) return true;  // fail closed stays closed
    r.seen_mask |= 1u << unsigned(r.schedule_user);
    r.schedule_user = int(scan - 310);
    return true;
  }
  if (scan >= 320 && scan <= 323 && (down == 0 || down == 1)) {
    const unsigned bit = 1u << (scan - 320);
    r.disconnected = down ? (r.disconnected | bit) : (r.disconnected & ~bit);
    return true;
  }
  return false;
}
inline std::mutex& RoutingLock() { static std::mutex m; return m; }
inline Routing& LiveRouting() {
  static Routing r = [] { Routing x; x.schedule_user = TestUser(); return x; }();
  return r;
}
inline bool UserEventsEnabled();         // G6-P80, below
inline Route UeRouteFor(unsigned user);  // G6-P80, below
inline Route RouteFor(unsigned user) {
  if (UserEventsEnabled()) return UeRouteFor(user);  // G6-P80 (test only): per-user connection state
  std::lock_guard<std::mutex> guard(RoutingLock());
  return RouteFor(user, LiveRouting());
}
inline void ApplyLiveRouteCode(unsigned scan, int down) {
  std::lock_guard<std::mutex> guard(RoutingLock());
  ApplyRouteCode(LiveRouting(), scan, down);
}
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
  void (*route_)(unsigned, int) = nullptr;  // G6-P79 route codes 310-313 / 320-323
 public:
  using RouteHook = void (*)(unsigned scan, int down);
  explicit Source(const char* path, RouteHook route = nullptr) : file_(path ? path : ""), route_(route) {}
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
      if ((scan_ >= 310 && scan_ <= 313) || (scan_ >= 320 && scan_ <= 323)) { if (route_) route_(scan_, down_); continue; }  // G6-P79
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
  static Source source(std::getenv("R3HD_INPUT_SCHEDULE"), &ApplyLiveRouteCode);
  return source.SampleNow(consume);
}

// ---- G6-P80 (test only, hidden runs): user-scoped schedule events ----
// With R3HD_NONINTRUSIVE set and R3HD_TEST_USER_EVENTS exactly "1", the schedule is applied in file order from ANY
// guest user's XamInputGetState call (Pump), not only from the scheduled user's own poll. So routing, connection and
// dialog-answer codes take effect even while the targeted user is unplugged, and a code and the press after it can no
// longer reach the old user in one poll. Semantics in this mode:
//   - button / axis lines belong to the user targeted when the line is applied (initially R3HD_TEST_INPUT_USER);
//   - 310+N (value 1) targets user N from then on and makes N present (user 0 is always present, as before);
//   - 320+N value 1 unplugs user N (its held buttons, pending presses and axes are cleared), value 0 replugs it;
//     connection state is per user and independent of the target;
//   - a press for an unplugged target is dropped and reported, never redirected;
//   - each user's press edges wait for THAT user's own consuming poll; delivery is reported per event (seq, user);
//   - 340+B (value 1, B 0..3) queues an answer (button B) for the title's open message box (g6p80_test_dialog.h).
// Bounded: at most kUeMaxLines schedule lines, kUeLedger tracked presses, kUeAnswers queued answers. Without the flag
// nothing here runs and the routing and sampling above are unchanged. Nothing leaves the XAM boundary.
inline bool ParseUserEvents(const char* nonintrusive, const char* flag) {
  return nonintrusive != nullptr && flag != nullptr && flag[0] == '1' && flag[1] == '\0';
}
inline bool UserEventsEnabled() {
  static const bool enabled = ParseUserEvents(std::getenv("R3HD_NONINTRUSIVE"), std::getenv("R3HD_TEST_USER_EVENTS"));
  return enabled;
}
constexpr unsigned kUeUsers = 4, kUeMaxLines = 1024, kUeLedger = 128, kUeAnswers = 8;
struct UeNote {
  enum Kind { kTarget, kConnect, kQueued, kDeliver, kDrop, kAnswer, kAnswerDrop, kLimit } kind;
  unsigned seq = 0, user = 0, value = 0;
};
class UserEvents {
  bool closed_ = false;           // invalid R3HD_TEST_INPUT_USER: nobody present, every event dropped
  unsigned target_ = 0, seen_ = 1, disconnected_ = 0, seq_ = 0, lines_ = 0, ledger_n_ = 0;
  std::array<std::array<bool, 256>, kUeUsers> held_{};
  std::array<unsigned short, kUeUsers> pending_{};
  std::array<std::array<int, 4>, kUeUsers> analog_{};
  std::array<State, kUeUsers> previous_{};
  struct Entry { unsigned seq, user; unsigned short buttons; bool delivered; };
  std::array<Entry, kUeLedger> ledger_{};
  std::array<int, kUeAnswers> answers_{}; unsigned answers_n_ = 0;
  bool limit_noted_ = false;
  template <class Notes> void Clear(unsigned u, Notes& notes) {  // unplug: undelivered presses are dropped, reported
    held_[u] = {}; pending_[u] = 0; analog_[u] = {};
    for (unsigned i = 0; i < ledger_n_; ++i)
      if (ledger_[i].user == u && !ledger_[i].delivered) {
        ledger_[i].delivered = true;
        notes.push_back({UeNote::kDrop, ledger_[i].seq, u, ledger_[i].buttons});
      }
  }
 public:
  explicit UserEvents(int test_user) {
    if (test_user < 0 || test_user > 3) { closed_ = true; return; }
    target_ = unsigned(test_user); seen_ = 1u | (1u << target_);
  }
  bool Present(unsigned user) const {
    return !closed_ && user < kUeUsers && (seen_ & (1u << user)) && !(disconnected_ & (1u << user));
  }
  unsigned Target() const { return target_; }
  unsigned Lines() const { return lines_; }
  // Applies one schedule line, in file order. Notes describe what happened (for the run log and the judges).
  template <class Notes> void Apply(unsigned scan, int value, Notes& notes) {
    if (lines_ >= kUeMaxLines) {
      if (!limit_noted_) { limit_noted_ = true; notes.push_back({UeNote::kLimit, seq_, 0, lines_}); }
      return;
    }
    ++lines_;
    if (scan >= 310 && scan <= 313 && value == 1) {
      if (closed_) return;
      target_ = scan - 310; seen_ |= 1u << target_;
      notes.push_back({UeNote::kTarget, seq_, target_, 1});
      return;
    }
    if (scan >= 320 && scan <= 323 && (value == 0 || value == 1)) {
      const unsigned u = scan - 320;
      if (closed_) return;
      if (value) { disconnected_ |= 1u << u; Clear(u, notes); } else { disconnected_ &= ~(1u << u); seen_ |= 1u << u; }
      notes.push_back({UeNote::kConnect, seq_, u, unsigned(!value)});
      return;
    }
    if (scan >= 340 && scan <= 343 && value == 1) {
      if (answers_n_ < kUeAnswers) { answers_[answers_n_++] = int(scan - 340); notes.push_back({UeNote::kAnswer, seq_, 0, scan - 340}); }
      else notes.push_back({UeNote::kAnswerDrop, seq_, 0, scan - 340});
      return;
    }
    if (scan >= 300 && scan <= 303) {
      if (Present(target_)) analog_[target_][scan - 300] = value < -32767 ? -32767 : value > 32767 ? 32767 : value;
      return;
    }
    if (scan >= 256 || value < 0 || value > 1) return;
    const unsigned short button = Source::Button(scan);
    if (!Present(target_)) {
      if (value == 1 && button) notes.push_back({UeNote::kDrop, ++seq_, closed_ ? kUeUsers : target_, button});
      return;
    }
    if (value && !held_[target_][scan] && button) {
      pending_[target_] |= button;
      const unsigned seq = ++seq_;
      if (ledger_n_ < kUeLedger) ledger_[ledger_n_++] = {seq, target_, button, false};
      notes.push_back({UeNote::kQueued, seq, target_, button});
    }
    held_[target_][scan] = value != 0;
  }
  // The state of one guest user. A consuming poll delivers that user's pending presses (and only that user's).
  template <class Notes> State Sample(unsigned user, bool consume, Notes& notes) {
    State s;
    if (!Present(user)) return s;
    const auto& h = held_[user];
    for (unsigned i = 0; i < h.size(); ++i) if (h[i]) s.buttons |= Source::Button(i);
    s.buttons |= pending_[user];
    s.lx = short((int(h[7]) - int(h[4])) * 32767); s.ly = short((int(h[26]) - int(h[22])) * 32767);
    s.rx = short((int(h[79]) - int(h[80])) * 32767); s.ry = short((int(h[82]) - int(h[81])) * 32767);
    const auto& a = analog_[user];
    if (a[0]) s.lx = short(a[0]); if (a[1]) s.ly = short(a[1]); if (a[2]) s.rx = short(a[2]); if (a[3]) s.ry = short(a[3]);
    s.lt = (h[20] || h[12]) ? 255 : 0; s.rt = (h[8] || h[18]) ? 255 : 0;
    State& p = previous_[user];
    s.packet = p.packet + (s.buttons != p.buttons || s.lx != p.lx || s.ly != p.ly || s.rx != p.rx || s.ry != p.ry ||
                           s.lt != p.lt || s.rt != p.rt);
    p = s;
    if (consume && pending_[user]) {
      for (unsigned i = 0; i < ledger_n_; ++i)
        if (ledger_[i].user == user && !ledger_[i].delivered) {
          ledger_[i].delivered = true;
          notes.push_back({UeNote::kDeliver, ledger_[i].seq, user, ledger_[i].buttons});
        }
      pending_[user] = 0;
    }
    return s;
  }
  int TakeAnswer() {
    if (!answers_n_) return -1;
    const int b = answers_[0];
    for (unsigned i = 1; i < answers_n_; ++i) answers_[i - 1] = answers_[i];
    --answers_n_;
    return b;
  }
};
// Runtime wrapper: one process-wide instance fed from R3HD_INPUT_SCHEDULE (same "ms scan value" lines, appended live).
using UeNoteHook = void (*)(const UeNote&);
struct UeRuntime {
  std::mutex lock;
  UserEvents events{TestUser()};
  std::ifstream file{std::getenv("R3HD_INPUT_SCHEDULE") ? std::getenv("R3HD_INPUT_SCHEDULE") : ""};
  std::chrono::steady_clock::time_point start = std::chrono::steady_clock::now();
  unsigned ms = 0, scan = 0; int value = 0; bool waiting = false;
  UeNoteHook hook = nullptr;  // set once by the XAM input code: logs notes and reports connection changes
};
inline UeRuntime& Ue() { static UeRuntime r; return r; }
inline void SetUeHook(UeNoteHook hook) { std::lock_guard<std::mutex> g(Ue().lock); Ue().hook = hook; }
struct UeNotes {  // fixed-capacity note buffer: no allocation under the lock
  std::array<UeNote, 32> items{}; unsigned n = 0, lost = 0;
  void push_back(const UeNote& note) { if (n < items.size()) items[n++] = note; else ++lost; }
};
inline void UeFlush(const UeNotes& notes, UeNoteHook hook) {
  if (!hook) return;
  for (unsigned i = 0; i < notes.n; ++i) hook(notes.items[i]);
  if (notes.lost) hook({UeNote::kLimit, 0, kUeUsers, notes.lost});
}
// Applies every due schedule line. Called first in every test-mode XamInputGetState, for any user.
inline void Pump() {
  if (!UserEventsEnabled()) return;
  UeNotes notes; UeNoteHook hook;
  {
    auto& r = Ue(); std::lock_guard<std::mutex> g(r.lock); hook = r.hook;
    const unsigned elapsed = unsigned(std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::steady_clock::now() - r.start).count());
    for (unsigned guard = 0; guard < 64; ++guard) {  // bounded per call; the rest waits for the next poll
      if (!r.waiting) {
        auto pos = r.file.tellg(); std::string line;
        if (!std::getline(r.file, line) || r.file.eof()) { r.file.clear(); r.file.seekg(pos); break; }
        if (std::sscanf(line.c_str(), "%u %u %d", &r.ms, &r.scan, &r.value) != 3) continue;
        r.waiting = true;
      }
      if (r.ms > elapsed) break;
      r.waiting = false;
      r.events.Apply(r.scan, r.value, notes);
    }
  }
  UeFlush(notes, hook);
}
inline Route UeRouteFor(unsigned user) {
  std::lock_guard<std::mutex> g(Ue().lock);
  return Ue().events.Present(user) ? kSchedule : kNotConnected;
}
inline State SampleFor(unsigned user, bool consume) {
  if (!UserEventsEnabled()) return Sample(consume);
  UeNotes notes; UeNoteHook hook; State s;
  { auto& r = Ue(); std::lock_guard<std::mutex> g(r.lock); hook = r.hook; s = r.events.Sample(user, consume, notes); }
  UeFlush(notes, hook);
  return s;
}
inline int TakeDialogAnswer() {
  if (!UserEventsEnabled()) return -1;
  std::lock_guard<std::mutex> g(Ue().lock);
  return Ue().events.TakeAnswer();
}
}
