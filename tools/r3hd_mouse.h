// D-138: native mouse controls, SDK-free (tools/r3hd_mouse_test.cpp tests it; tools/r3hd_mouse_patch.py installs it
// and wires it into the keyboard / mouse driver and VdSwap).
//
// Context: the guest facts of r3hd_ds_state.h (world 1..9, not a front-end level, pause word 0), published once per
// VdSwap. They only ever withhold the mouse: outside gameplay, or before the first swap, mouse buttons and the mouse
// camera do nothing and the pointer is not captured. They are never a reason to send input (D-123: no attack
// eligibility predicate); in gameplay a mouse button is exactly its bound pad input, as a key or a pad would be.
//
// Buttons: separate from the keyboard's key state (D-122). A press reaches at least one guest poll (latched like a key
// tap); a release is always accepted; any loss of context (focus, a host overlay taking the mouse, leaving gameplay,
// the option off) disarms a held button, which then needs a fresh press.
//
// Camera: relative counts (SDL relative mode, raw and unaccelerated, so independent of the window size and the
// desktop cursor) become time at full right-stick deflection (see "camera" below, RE_NOTES "Mouse camera"). A poll
// uses at most kMaxCountsPerPoll counts, the owed time is bounded, and every context change drops pending motion.
#pragma once
#include <algorithm>
#include <atomic>
#include <cmath>
#include <cstdint>
#include <cstdlib>

namespace r3hd_mouse {

enum Button : uint8_t { kLeft, kRight, kMiddle, kX1, kX2, kButtonCount };
// The runtime's virtual keys of the five buttons (rex::ui::VirtualKey kLButton, kRButton, kMButton, kXButton1/2).
inline constexpr uint8_t kVk[kButtonCount] = {0x01, 0x02, 0x04, 0x05, 0x06};

// --- guest context (VdSwap thread writes, the input poll reads) -------------------------------------------------
// bit 0 gameplay, bits 1.. a count of changes (so a poll sees a pause -> resume between two of its polls).
inline std::atomic<uint32_t> g_context{0};

inline std::atomic<bool> g_log{false};  // a mouse option is on: VdSwap logs context changes

// Returns true when the fact changed.
inline bool PublishGameplay(bool gameplay) {
  uint32_t v = g_context.load(std::memory_order_relaxed);
  if (((v & 1u) != 0) == gameplay) return false;
  g_context.store(((v & ~1u) + 2u) | (gameplay ? 1u : 0u), std::memory_order_relaxed);
  return true;
}
inline bool Gameplay(uint32_t context) { return (context & 1u) != 0; }
inline uint32_t Context() { return g_context.load(std::memory_order_relaxed); }

// --- buttons ----------------------------------------------------------------------------------------------------
class Buttons {
  bool held_[kButtonCount] = {};
  bool armed_[kButtonCount] = {};
  bool latched_[kButtonCount] = {};
  uint32_t context_[kButtonCount] = {};  // the guest context a press was armed in

 public:
  // live = the mouse may act now (option on, focus, input active, gameplay). A press while not live never arms.
  void Down(Button b, bool live, uint32_t context = 0) {
    if (b >= kButtonCount) return;
    held_[b] = true;
    if (!live) return;
    if (!armed_[b]) latched_[b] = true;
    armed_[b] = true;
    context_[b] = context;
  }
  // The guest context changed since the last poll: presses armed before it need a fresh press; a press made in the
  // new context (between the swap and this poll) keeps acting.
  void DisarmOlder(uint32_t context) {
    for (int i = 0; i < kButtonCount; ++i)
      if (context_[i] != context) armed_[i] = latched_[i] = false;
  }
  void Up(Button b) {
    if (b >= kButtonCount) return;
    held_[b] = false;
    armed_[b] = false;  // a latched press still reaches its poll
  }
  // A held button needs a fresh press; a press not yet polled is dropped.
  void Disarm() {
    for (int i = 0; i < kButtonCount; ++i) armed_[i] = latched_[i] = false;
  }
  void Clear() {
    for (int i = 0; i < kButtonCount; ++i) held_[i] = armed_[i] = latched_[i] = false;
  }
  // One guest poll: bit i = button i pressed for the guest; the latches are spent.
  uint8_t Poll(bool live) {
    if (!live) {
      Disarm();
      return 0;
    }
    uint8_t mask = 0;
    for (int i = 0; i < kButtonCount; ++i) {
      if ((held_[i] && armed_[i]) || latched_[i]) mask |= uint8_t(1u << i);
      latched_[i] = false;
    }
    return mask;
  }
  bool held(Button b) const { return b < kButtonCount && held_[b]; }
};

// --- camera -----------------------------------------------------------------------------------------------------
// The title turns the camera at its own fixed rate while the horizontal stick is past its dead zone (about 0.7) and
// eases the start; stick length beyond that changes nothing (E-315). So the mouse buys stick time, not stick length:
// counts become milliseconds of full deflection, spent one poll at a time. Rotation then follows the distance the
// mouse moved; a fast flick is limited by the title's rate and by the bounded backlog (max_backlog_ms).
struct CameraTuning {
  double ms_per_count = 1.0;           // horizontal: full-stick milliseconds per count at sensitivity 1
  double vertical_ms_per_count = 0.5;  // vertical: the title moves the camera height to its limits in about 1 s
  double vertical_min_ms = 60.0;       // vertical starts only after a deliberate motion (small jitter does nothing)
  double max_backlog_ms = 150.0;       // the camera never runs on longer than this after the mouse stops
  double idle_drop_ms = 250.0;         // a remainder too small for one poll is dropped after this long without motion
};
inline constexpr double kPollMs = 1000.0 / 60.0;  // one gameplay poll = one guest frame (D-046: fixed 16 ms step)
inline constexpr float kMaxCountsPerPoll = 1000.0f;  // one poll's counts are bounded (a stall never dumps a backlog)

// Settings slider 1..100 -> the runtime's mnk_sensitivity (0.25 .. 4, 50 = 1, geometric).
inline double SensitivityFromPercent(int percent) {
  percent = std::clamp(percent, 1, 100);
  return std::pow(2.0, (percent - 50) / 25.0);
}

class Camera {
  // Sigma-delta: each poll at full stick spends a whole poll of owed time, so a remainder carries as a small debt and
  // the stick time follows the motion exactly on average, slow motion included.
  struct Axis {
    int dir = 0;              // direction of the last motion
    double owed_ms = 0.0;     // full-stick time still owed in that direction (negative: a debt of under half a poll)
    double idle_ms = 0.0;     // time since the last motion
    bool running = false;     // the start threshold was passed

    // Returns -1, 0 or 1 for this poll.
    int Poll(double counts, double ms_per_count, double min_ms, double dt_ms, const CameraTuning& t) {
      if (counts != 0.0) {
        const int d = counts > 0.0 ? 1 : -1;
        if (d != dir) dir = d, owed_ms = 0.0, running = false;  // a reversal turns at once: nothing owed survives
        owed_ms = std::min(owed_ms + std::fabs(counts) * ms_per_count, t.max_backlog_ms);
        idle_ms = 0.0;
      } else {
        idle_ms += dt_ms;
      }
      if (!running && owed_ms >= std::max(min_ms, dt_ms * 0.5)) running = true;
      if (running && owed_ms >= dt_ms * 0.5) {
        owed_ms -= dt_ms;
        return dir;
      }
      running = false;
      if (idle_ms >= t.idle_drop_ms) owed_ms = 0.0;
      return 0;
    }
  };
  float dx_ = 0.0f, dy_ = 0.0f;  // counts since the last poll
  Axis x_, y_;
  int last_x_ = 0, last_y_ = 0;

 public:
  void Add(float dx, float dy) {
    if (!std::isfinite(dx) || !std::isfinite(dy)) return;  // never poison the owed time
    dx_ += dx;
    dy_ += dy;
  }
  void Drop() {
    dx_ = dy_ = 0.0f;
    x_ = Axis{};
    y_ = Axis{};
    last_x_ = last_y_ = 0;
  }
  // One guest poll, dt_ms since the previous one. live = pointer captured in gameplay; not live drops everything.
  // Adds the stick (int16 units, full deflection while time is owed) to rx / ry; mouse down = stick down.
  void Poll(bool live, double dt_ms, double sens, const CameraTuning& t, int32_t& rx, int32_t& ry) {
    if (!live) {
      Drop();
      return;
    }
    dt_ms = std::clamp(dt_ms, 1.0, 100.0);
    sens = std::clamp(sens, 0.01, 10.0);
    const double cx = std::clamp(dx_, -kMaxCountsPerPoll, kMaxCountsPerPoll);
    const double cy = std::clamp(dy_, -kMaxCountsPerPoll, kMaxCountsPerPoll);
    dx_ = dy_ = 0.0f;
    last_x_ = x_.Poll(cx, t.ms_per_count * sens, 0.0, dt_ms, t);
    last_y_ = y_.Poll(-cy, t.vertical_ms_per_count * sens, t.vertical_min_ms, dt_ms, t);
    rx += last_x_ * 32767;
    ry += last_y_ * 32767;
  }
  int stick_x() const { return last_x_; }
  int stick_y() const { return last_y_; }
  double backlog_x_ms() const { return x_.owed_ms; }
};

// --- Look Mode (D-145) ------------------------------------------------------------------------------------------
// While the title is in its first-person Look Mode (byte 82C07D5C = 1 and 82C5C770 = FF, D-143; published by VdSwap
// with the gameplay fact) it looks with the LEFT stick and ignores the right one, so the mouse drives the left stick
// there. The title's response (E-327, RE_NOTES "Look Mode flag"), per guest frame: rate = full * (m - 0.29) / 0.5 for
// a deflection m in 0.45 .. 0.80 (nothing at or below 0.40, full from 0.80), full = 2.71 deg turn / 2.93 deg tilt;
// the first frame already turns at the rate, a release halves the speed each frame (one frame's worth in all). Each
// stick direction is calibrated by the title on its first full deflection; before it, partial values act twice as
// strongly. So a direction gets only full frames until a full one has been sent there in Look Mode since the last
// level change (the title then knows the full range), and analog after it. Mouse counts become a wanted angle; each
// frame the stick is chosen so that the title's predicted rotation follows it. Stick up tilts the view UP in the
// title (E-331: the camera's forward axis, signed from the third-person frames, rises; E-327's "down" read the backward
// axis), so mouse up drives the stick up.
inline std::atomic<bool> g_look{false};        // Look Mode (only ever true together with gameplay)
inline std::atomic<uint32_t> g_level{0};       // a hash of the level name (a change re-arms the calibration guard)

inline bool PublishLook(bool look) { return g_look.exchange(look, std::memory_order_relaxed) != look; }
inline bool LookMode() { return g_look.load(std::memory_order_relaxed); }
inline void PublishLevel(const char* name) {
  uint32_t h = 2166136261u;  // FNV-1a
  for (; name && *name; ++name) h = (h ^ uint8_t(*name)) * 16777619u;
  g_level.store(h, std::memory_order_relaxed);
}
inline uint32_t Level() { return g_level.load(std::memory_order_relaxed); }

struct LookTuning {
  double deg_per_count = 0.05;    // at sensitivity 1, both axes (the D-138 normal camera turns about 0.05 deg per count)
  double max_backlog_frames = 9;  // owed angle never above 9 frames at full (150 ms, as D-138's camera)
  int idle_drop_frames = 15;      // a remainder too small for a pulse is dropped after 250 ms without motion
};
inline constexpr double kLookFullDeg[2] = {2.71, 2.93};  // per guest frame at full deflection: turn, tilt
inline constexpr double kLookZero = 0.29;                // the linear part's zero (rate = full * (m - zero) / span)
inline constexpr double kLookSpan = 0.50;
inline constexpr double kLookMinStick = 0.45;            // smallest deflection that acts (0.40 does not)
inline constexpr double kLookMinFraction = (kLookMinStick - kLookZero) / kLookSpan;  // 0.32 of full

class LookStick {
  struct Axis {
    int dir = 0;              // direction of the last motion (+1 / -1)
    double owed = 0.0;        // angle still wanted in that direction (deg); negative = turned too far (a debt)
    double v = 0.0;           // the title's predicted speed (deg per frame, signed)
    int idle = 0;             // frames without motion
    bool calibrated[2] = {};  // the title knows the full range in + / - (a full deflection was sent there)

    // One frame: counts in, stick (int16 units) out. full = this axis' full rate. Every frame the title's predicted
    // rotation (its release decay included) is taken from the owed angle, so a pulse's tail is paid for; an overshoot
    // is a debt the next motion in the same direction pays first, never a turn back.
    int32_t Poll(double deg, double full, const LookTuning& t) {
      const double bound = t.max_backlog_frames * full;
      if (deg != 0.0) {
        const int d = deg > 0 ? 1 : -1;
        if (d != dir) dir = d, owed = 0.0;  // a reversal turns at once: nothing owed (or in debt) survives
        owed = std::min(owed + std::fabs(deg), bound);
        idle = 0;
      } else if (++idle >= t.idle_drop_frames && owed < 1.5 * kLookMinFraction * full) {
        owed = 0.0;  // a remainder too small to act on, or a debt, is forgotten after a pause in the motion
      }
      const bool along = dir != 0 && v * dir > 0;
      const double tail = along ? std::fabs(v) * 0.5 : 0.0;  // the title turns this much anyway this frame
      double s = 0.0;  // the speed asked for this frame (deg per frame, magnitude)
      if (dir != 0 && owed > 0.0) {
        const double want = owed * 0.5;  // this frame and its own release tail finish the owed angle
        if (!calibrated[dir > 0 ? 0 : 1]) {
          s = owed >= 1.5 * full ? full : 0.0;
        } else if (want >= kLookMinFraction * full) {
          s = std::min(want, full);
        } else if (owed >= 1.5 * kLookMinFraction * full) {
          s = kLookMinFraction * full;  // slow motion: pulses of the smallest acting speed
        }
        if (s <= tail) s = 0.0;  // the title's own decay already turns at least this much
      }
      // the title: a held stick turns at its rate at once; otherwise the speed halves
      double nv = (std::fabs(v) * 0.5 < 0.005) ? 0.0 : v * 0.5;
      if (s > 0.0) nv = dir * std::max(s, along ? std::fabs(nv) : 0.0);
      v = nv;
      if (dir != 0) owed = std::clamp(owed - v * dir, -full, bound);
      if (s <= 0.0) return 0;
      const bool full_frame = s >= full - 1e-9;
      if (full_frame) calibrated[dir > 0 ? 0 : 1] = true;
      const double m = full_frame ? 1.0 : std::max(kLookZero + kLookSpan * (s / full), kLookMinStick);
      return dir * static_cast<int32_t>(std::ceil(std::min(m, 1.0) * 32767.0 - 1e-6));
    }
    void Drop() { dir = 0, owed = 0.0, v = 0.0, idle = 0; }
    // A key holds this axis (it wins): no owed angle; the title's speed follows the key's deflection (full, or the
    // M49 walk magnitude), and only a full one calibrates.
    void Key(int32_t value, double full) {
      owed = 0.0, idle = 0;
      const double m = std::min(1.0, std::abs(value) / 32767.0);
      const int d = value > 0 ? 1 : 0;
      if (m >= 1.0) calibrated[d ? 0 : 1] = true;
      const double frac = calibrated[d ? 0 : 1] ? std::clamp((m - kLookZero) / kLookSpan, 0.0, 1.0) : 1.0;
      v = (value > 0 ? 1.0 : -1.0) * full * (m <= 0.40 ? 0.0 : frac);
    }
  };
  float dx_ = 0.0f, dy_ = 0.0f;
  Axis x_, y_;
  uint32_t level_ = 0;
  bool have_level_ = false;

 public:
  void Add(float dx, float dy) {
    if (!std::isfinite(dx) || !std::isfinite(dy)) return;
    dx_ += dx;
    dy_ += dy;
  }
  void Drop() {
    dx_ = dy_ = 0.0f;
    x_.Drop();
    y_.Drop();
  }
  // A new level (or the first one): the title's calibration is not assumed to survive it.
  void SetLevel(uint32_t level) {
    if (have_level_ && level == level_) return;
    have_level_ = true;
    level_ = level;
    x_ = Axis{};
    y_ = Axis{};
  }
  // One guest poll in Look Mode. live = Mouse Camera on, pointer captured, gameplay, Look Mode; not live drops the
  // motion. lx / ly hold the keys' deflection: a key on an axis wins and that axis' mouse motion is dropped.
  void Poll(bool live, double sens, const LookTuning& t, int32_t& lx, int32_t& ly) {
    if (!live) {
      Drop();
      return;
    }
    sens = std::clamp(sens, 0.01, 10.0);
    const double cx = std::clamp(double(dx_), double(-kMaxCountsPerPoll), double(kMaxCountsPerPoll));
    const double cy = std::clamp(double(dy_), double(-kMaxCountsPerPoll), double(kMaxCountsPerPoll));
    dx_ = dy_ = 0.0f;
    if (lx != 0) {
      x_.Key(lx, kLookFullDeg[0]);
    } else {
      lx = x_.Poll(cx * t.deg_per_count * sens, kLookFullDeg[0], t);
    }
    if (ly != 0) {
      y_.Key(ly, kLookFullDeg[1]);
    } else {
      ly = y_.Poll(-cy * t.deg_per_count * sens, kLookFullDeg[1], t);  // mouse up = stick up = view up (E-331)
    }
  }
  bool calibrated(int axis, int dir) const { return (axis ? y_ : x_).calibrated[dir > 0 ? 0 : 1]; }
  double owed(int axis) const { return std::max(0.0, (axis ? y_ : x_).owed); }
};

}  // namespace r3hd_mouse
