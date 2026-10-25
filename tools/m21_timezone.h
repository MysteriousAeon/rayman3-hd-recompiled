// M21 (D-050): the console's time-zone bias as the title reads it. Host-only, no game material.
//
// The title converts UTC to local time itself: its statically linked system library reads the console's zone
// from ExGetXConfigSetting (user category 3, settings 1..7), picks Bias (+ StandardBias / DaylightBias by its
// own zone id) and subtracts it from the UTC time (RE_NOTES "M21"). The pinned runtime answers 0 for all
// seven settings, so every local time the title shows is UTC: the save list read 12:13 at 15:13 in UTC+03:00.
//
// The correction answers setting 1 (bias, minutes, UTC = local + bias, the Win32 sign) with the host's
// current effective bias and leaves settings 2..7 at 0. With no transition dates the title's zone id is 0 and
// it uses the bias alone, so the host's daylight state is applied once, by the host, and never a second time
// by the title. The guest clock (KeQuerySystemTime), file times and the save itself stay UTC.
//
// R3HD_TIMEZONE: unset / "host" = the host's zone; "utc" = the pinned answer 0; "bias:N" = N minutes
// (hidden experiments only; play.ps1 never passes it).
#pragma once

#include <cstdint>
#include <cstdlib>
#include <cstring>

namespace m21tz {

// What the host reports (Win32 GetTimeZoneInformation): its return value and the three biases in minutes.
struct HostZone {
  bool ok = false;
  uint32_t id = 0;  // 0 no daylight rule, 1 standard time now, 2 daylight time now
  int32_t bias = 0;
  int32_t standard_bias = 0;
  int32_t daylight_bias = 0;
};

enum class Kind { kHost, kUtc, kFixed };
struct Policy {
  Kind kind = Kind::kHost;
  int32_t fixed = 0;
  bool recognised = true;
};

// No zone on Earth is further than 14 hours from UTC; one more hour of margin for a daylight bias.
constexpr int32_t kMaxBias = 15 * 60;

constexpr int32_t EffectiveHostBias(const HostZone& z) {
  if (!z.ok) return 0;
  int64_t b = z.bias;
  if (z.id == 1) b += z.standard_bias;
  else if (z.id == 2) b += z.daylight_bias;
  else if (z.id != 0) return 0;
  if (b < -kMaxBias || b > kMaxBias) return 0;
  return int32_t(b);
}

inline Policy ParsePolicy(const char* value) {
  Policy p;
  if (!value || !*value || std::strcmp(value, "host") == 0) return p;
  if (std::strcmp(value, "utc") == 0) {
    p.kind = Kind::kUtc;
    return p;
  }
  if (std::strncmp(value, "bias:", 5) == 0 && value[5]) {
    char* end = nullptr;
    long n = std::strtol(value + 5, &end, 10);
    if (end && !*end && n >= -kMaxBias && n <= kMaxBias) {
      p.kind = Kind::kFixed;
      p.fixed = int32_t(n);
      return p;
    }
  }
  p.recognised = false;  // an unknown value keeps the default rather than silently showing UTC
  return p;
}

constexpr int32_t GuestBias(const Policy& p, const HostZone& z) {
  return p.kind == Kind::kUtc ? 0 : p.kind == Kind::kFixed ? p.fixed : EffectiveHostBias(z);
}

// The title's own conversion (its routine at 82307B70, used by 822FF348 and 822FF468), for the regression:
// local file time = UTC file time - bias * 60 s, in 100 ns units.
constexpr uint64_t TitleLocalFileTime(uint64_t utc_file_time, int32_t guest_bias) {
  return uint64_t(int64_t(utc_file_time) - int64_t(guest_bias) * 60 * 10000000);
}

}  // namespace m21tz

#if defined(_WIN32) && !defined(M21_TIMEZONE_NO_HOST)
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>

namespace m21tz {

inline HostZone QueryHostZone() {
  HostZone z;
  TIME_ZONE_INFORMATION tzi{};
  DWORD id = GetTimeZoneInformation(&tzi);
  if (id == TIME_ZONE_ID_INVALID) return z;
  z.ok = true;
  z.id = id;
  z.bias = tzi.Bias;
  z.standard_bias = tzi.StandardBias;
  z.daylight_bias = tzi.DaylightBias;
  return z;
}

}  // namespace m21tz
#elif !defined(M21_TIMEZONE_NO_HOST)
namespace m21tz {
inline HostZone QueryHostZone() { return {}; }  // other hosts keep the pinned answer
}  // namespace m21tz
#endif
