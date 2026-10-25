// M21 (D-050): cursor rule and time-zone bias, deterministic checks. Host-only, no game material.
#include "m21_cursor.h"
#include "m21_timezone.h"
#include <cstdio>
#include <initializer_list>

static int checks = 0, failures = 0;
static void Check(bool ok, const char* what) {
  ++checks;
  if (!ok) {
    ++failures;
    std::printf("FAIL %s\n", what);
  }
}

// FILETIME (100 ns since 1601-01-01) of a civil UTC time; days-from-civil after Howard Hinnant.
static uint64_t FileTime(int y, unsigned m, unsigned d, unsigned hh, unsigned mm, unsigned ss) {
  y -= m <= 2;
  const int era = (y >= 0 ? y : y - 399) / 400;
  const unsigned yoe = unsigned(y - era * 400);
  const unsigned doy = (153 * (m + (m > 2 ? -3 : 9)) + 2) / 5 + d - 1;
  const unsigned doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
  const int64_t days_1970 = int64_t(era) * 146097 + int64_t(doe) - 719468;
  const int64_t days_1601 = days_1970 + 134774;
  return uint64_t((days_1601 * 86400 + hh * 3600 + mm * 60 + ss) * 10000000);
}

static void CursorChecks() {
  using namespace m21cursor;
  // Decision table: every combination of the seven inputs.
  for (int bits = 0; bits < 32; ++bits) {
    for (int r = 0; r < 3; ++r) {
      State s;
      s.nonintrusive = bits & 1;
      s.open = bits & 2;
      s.focused = bits & 4;
      s.minimized = bits & 8;
      s.mouse_recent = bits & 16;
      s.requested = Requested(r);
      const Action a = Decide(s);
      if (s.nonintrusive) {
        Check(a == Action::kNone, "a hidden test window never touches the cursor");
        continue;
      }
      Check(a != Action::kNone, "a visible window always has a definite cursor state");
      if (!s.open || !s.focused || s.minimized) {
        Check(a == Action::kShow, "shown whenever the window is closed, unfocused or minimized");
      } else if (s.requested == Requested::kHidden) {
        Check(a == Action::kHide, "mouse capture keeps the cursor hidden");
      } else {
        Check(a == (s.mouse_recent ? Action::kShow : Action::kHide), "focused: hidden unless the mouse moved");
      }
    }
  }

  // A controller session: open, focus, play, alt-tab away and back, minimize, restore, close.
  {
    Tracker t;
    Check(t.Request(Requested::kVisible) == Action::kShow, "before the window exists");
    Check(t.Opened(false, false) == Action::kShow, "open without focus");
    Check(t.Focus(true) == Action::kHide && t.changed(), "focus gained hides");
    Check(t.Focus(true) == Action::kHide && !t.changed(), "repeated focus event changes nothing");
    Check(!t.wants_idle_timer(), "no timer while nothing shows the cursor");
    Check(t.Focus(false) == Action::kShow && t.changed(), "focus lost restores");
    Check(t.MouseIdle() == Action::kShow, "a late idle timer after focus loss does not hide");
    Check(t.MouseMoved() == Action::kShow && !t.wants_idle_timer(), "hover over the unfocused window stays shown");
    Check(t.Focus(true) == Action::kHide, "focus regained hides again, the earlier hover is forgotten");
    Check(t.Minimized() == Action::kShow, "minimize restores");
    Check(t.Focus(false) == Action::kShow, "focus lost while minimized");
    Check(t.Restored() == Action::kShow, "restored without focus stays shown");
    Check(t.Focus(true) == Action::kHide, "restored and focused hides");
    Check(t.Minimized() == Action::kShow && t.Restored() == Action::kHide, "minimize / restore keeping the focus");
    Check(t.Closed() == Action::kShow && t.changed(), "close restores");
    Check(t.MouseIdle() == Action::kShow && t.Focus(true) == Action::kShow, "nothing hides after the close");
  }
  // Mouse use: movement shows, idle hides, capture overrides, release returns to the rule.
  {
    Tracker t;
    t.Opened(true, false);
    Check(t.state().focused && Decide(t.state()) == Action::kHide, "opened with focus hides");
    Check(t.MouseMoved() == Action::kShow && t.wants_idle_timer(), "movement shows and arms the timer");
    Check(t.MouseMoved() == Action::kShow && !t.changed(), "continued movement is one state");
    Check(t.MouseIdle() == Action::kHide && !t.wants_idle_timer(), "idle hides");
    t.MouseMoved();
    Check(t.Request(Requested::kHidden) == Action::kHide && !t.wants_idle_timer(), "capture hides at once");
    Check(t.MouseMoved() == Action::kHide, "captured movement stays hidden");
    Check(t.Focus(false) == Action::kShow, "capture does not survive focus loss");
    Check(t.Focus(true) == Action::kHide, "capture still requested on return");
    Check(t.Request(Requested::kVisible) == Action::kHide, "release without movement: hidden by the rule");
    Check(t.MouseMoved() == Action::kShow, "release then movement shows");
    Check(t.Request(Requested::kAutoHidden) == Action::kShow && t.MouseIdle() == Action::kHide, "auto-hidden request follows the same rule");
  }
  // Capture released after captured movement: no timer was armed while captured, so nothing may be left
  // that keeps the cursor shown (it would stay on the picture until the mouse is touched again).
  {
    Tracker t;
    t.Opened(true, false);
    t.MouseMoved();
    Check(t.Request(Requested::kHidden) == Action::kHide, "capture after movement hides");
    Check(t.MouseMoved() == Action::kHide && !t.wants_idle_timer() && !t.state().mouse_recent, "captured movement is not cursor use");
    Check(t.Request(Requested::kVisible) == Action::kHide && !t.wants_idle_timer(), "release after captured movement stays hidden");
    Check(t.MouseMoved() == Action::kShow && t.wants_idle_timer(), "the next free movement shows and arms the timer");
  }
  // Whenever the cursor is shown in a focused window, the idle timer is wanted: no shown state without a way out.
  {
    Tracker t;
    t.Opened(true, false);
    bool ok = true;
    const Requested requests[] = {Requested::kVisible, Requested::kHidden, Requested::kAutoHidden};
    unsigned seed = 12345;
    for (int i = 0; i < 20000; ++i) {
      seed = seed * 1103515245u + 12345u;
      Action a = Action::kNone;
      switch ((seed >> 16) % 5) {
        case 0: a = t.MouseMoved(); break;
        case 1: a = t.MouseIdle(); break;
        case 2: a = t.Request(requests[(seed >> 8) % 3]); break;
        case 3: a = t.Focus(true); break;
        default: a = t.Request(requests[(seed >> 4) % 3]); break;
      }
      ok = ok && a != Action::kNone && (a == Action::kHide || t.wants_idle_timer());
    }
    Check(ok, "focused window: every shown state has the idle timer wanted (20000 random events)");
  }
  // Hidden test window: the whole sequence yields no action and no change to log.
  {
    Tracker t(true);
    bool none = true, quiet = true;
    auto step = [&](Action a) {
      none = none && a == Action::kNone;
      quiet = quiet && !t.changed() && !t.wants_idle_timer();
    };
    step(t.Request(Requested::kVisible));
    step(t.Opened(true, false));
    step(t.Focus(true));
    step(t.MouseMoved());
    step(t.MouseIdle());
    step(t.Request(Requested::kHidden));
    step(t.Focus(false));
    step(t.Minimized());
    step(t.Restored());
    step(t.Closed());
    Check(none, "hidden test window: no cursor action in any event");
    Check(quiet, "hidden test window: nothing to log, no timer");
  }
  Check(ModeFromEnv(nullptr) == Mode::kAuto && ModeFromEnv("") == Mode::kAuto && ModeFromEnv("auto") == Mode::kAuto,
        "default mode");
  Check(ModeFromEnv("visible") == Mode::kPinned, "visible keeps the SDK's behaviour");
  Check(ModeFromEnv("hidden") == Mode::kAuto && ModeFromEnv("VISIBLE") == Mode::kAuto, "unknown values keep the default");
}

static void TimeZoneChecks() {
  using namespace m21tz;
  const HostZone istanbul{true, 0, -180, 0, 0};        // UTC+03:00, no daylight rule
  const HostZone berlin_winter{true, 1, -60, 0, -60};  // UTC+01:00
  const HostZone berlin_summer{true, 2, -60, 0, -60};  // UTC+02:00
  const HostZone new_york_summer{true, 2, 300, 0, -60};
  const HostZone kolkata{true, 0, -330, 0, 0};
  const HostZone utc{true, 0, 0, 0, 0};
  Check(EffectiveHostBias(istanbul) == -180, "Istanbul");
  Check(EffectiveHostBias(berlin_winter) == -60 && EffectiveHostBias(berlin_summer) == -120, "Berlin both halves");
  Check(EffectiveHostBias(new_york_summer) == 240, "New York in summer");
  Check(EffectiveHostBias(kolkata) == -330 && EffectiveHostBias(utc) == 0, "half-hour zone, UTC");
  Check(EffectiveHostBias(HostZone{}) == 0, "host query failed: the pinned answer");
  Check(EffectiveHostBias(HostZone{true, 3, -180, 0, 0}) == 0, "unknown zone id: the pinned answer");
  Check(EffectiveHostBias(HostZone{true, 0, 100000, 0, 0}) == 0 && EffectiveHostBias(HostZone{true, 0, -901, 0, 0}) == 0,
        "implausible bias: the pinned answer");
  Check(EffectiveHostBias(HostZone{true, 0, -180, 77, 99}) == -180, "without a daylight rule the extra biases are unused");
  Check(EffectiveHostBias(HostZone{true, 0, -840, 0, 0}) == -840 && EffectiveHostBias(HostZone{true, 0, 720, 0, 0}) == 720,
        "extreme real zones");

  Check(ParsePolicy(nullptr).kind == Kind::kHost && ParsePolicy("").kind == Kind::kHost &&
            ParsePolicy("host").kind == Kind::kHost, "default policy");
  Check(ParsePolicy("utc").kind == Kind::kUtc && ParsePolicy("utc").recognised, "utc policy");
  Check(ParsePolicy("bias:-180").kind == Kind::kFixed && ParsePolicy("bias:-180").fixed == -180, "fixed negative");
  Check(ParsePolicy("bias:300").fixed == 300 && ParsePolicy("bias:0").kind == Kind::kFixed, "fixed positive, zero");
  for (const char* bad : {"bias:", "bias:abc", "bias:12x", "bias:901", "bias:-901", "UTC", "local", "bias", "-180"}) {
    const Policy p = ParsePolicy(bad);
    Check(p.kind == Kind::kHost && !p.recognised, "unrecognised value keeps the host policy and is flagged");
  }
  Check(GuestBias(ParsePolicy("utc"), istanbul) == 0, "utc policy ignores the host");
  Check(GuestBias(ParsePolicy("bias:-330"), istanbul) == -330, "fixed policy ignores the host");
  Check(GuestBias(ParsePolicy(nullptr), istanbul) == -180, "host policy");
  Check(GuestBias(ParsePolicy(nullptr), HostZone{}) == 0, "host policy with a failed query");

  // The title's conversion with the bias it is given. The observation of the session: 15:13 shown as 12:13.
  const uint64_t save = FileTime(2026, 10, 11, 12, 13, 36);
  Check(FileTime(1601, 1, 1, 0, 0, 0) == 0 && FileTime(1970, 1, 1, 0, 0, 0) == 116444736000000000ull, "file time epoch");
  Check(TitleLocalFileTime(save, 0) == save, "pinned answer: the title shows UTC");
  Check(TitleLocalFileTime(save, GuestBias(ParsePolicy(nullptr), istanbul)) == FileTime(2026, 10, 11, 15, 13, 36),
        "UTC+03:00: 12:13 UTC is shown as 15:13");
  Check(TitleLocalFileTime(FileTime(2026, 10, 5, 22, 30, 0), -180) == FileTime(2026, 10, 6, 1, 30, 0),
        "the date rolls over with the hour");
  Check(TitleLocalFileTime(FileTime(2026, 1, 1, 2, 0, 0), 300) == FileTime(2025, 12, 31, 21, 0, 0), "west of UTC, year boundary");
  Check(TitleLocalFileTime(save, -330) == FileTime(2026, 10, 11, 17, 43, 36), "half-hour zone");
  // One conversion only: the bias is applied by the title, once; daylight time comes from the host's bias and
  // not from a second rule (settings 2..7 are 0, so the title's zone id is 0 and it uses the bias alone).
  Check(TitleLocalFileTime(save, EffectiveHostBias(berlin_summer)) == FileTime(2026, 10, 11, 14, 13, 36),
        "daylight time is applied once");
  Check(TitleLocalFileTime(TitleLocalFileTime(save, -180), 180) == save, "the conversion is an exact offset");

  // The machine running the test: sane, whatever its zone is.
  const HostZone here = QueryHostZone();
  const int32_t bias = EffectiveHostBias(here);
  Check(here.ok, "host zone query succeeds");
  Check(bias >= -kMaxBias && bias <= kMaxBias, "host bias in range");
  std::printf("host zone: ok=%d id=%u bias=%d standard=%d daylight=%d effective=%d\n", here.ok, here.id, here.bias,
              here.standard_bias, here.daylight_bias, bias);
}

int main() {
  CursorChecks();
  TimeZoneChecks();
  std::printf("m21_host_test: %d checks, %d failures\n", checks, failures);
  return failures ? 1 : 0;
}
