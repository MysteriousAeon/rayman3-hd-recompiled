// M49 (D-088): hold-to-walk for the keyboard. While the Walk key is held, the keyboard's left stick keeps its
// direction and gets the length `magnitude` (a fraction of full deflection), the same for straight and diagonal
// directions. Without the key the stick is exactly what the keys gave before (full deflection per axis). Only the
// keyboard driver calls this; a physical controller's stick never passes through here.
#pragma once
#include <cmath>
#include <cstdint>

namespace m49walk {

inline void Apply(int32_t& lx, int32_t& ly, bool held, double magnitude) {
  if (!held || (lx == 0 && ly == 0)) return;
  if (!(magnitude > 0.0) || magnitude > 1.0) magnitude = 1.0;
  const double length = std::sqrt(double(lx) * lx + double(ly) * ly);
  const double scale = magnitude * 32767.0 / length;
  lx = static_cast<int32_t>(std::lround(lx * scale));
  ly = static_cast<int32_t>(std::lround(ly * scale));
}

}  // namespace m49walk
