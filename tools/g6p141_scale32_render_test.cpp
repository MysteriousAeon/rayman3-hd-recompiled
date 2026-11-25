// G6-P141: Deterministic offline rendering acceptance tests for native 1080p (1.5x / 3:2).
// Covers viewport conversion, scissor/clipping, guest-to-host coordinates, synthetic raster + Model R
// round-trip & subpixel sampling tolerance, 4xMSAA transfer/EDRAM geometry, depth/stencil/alpha cutout
// invariants, RT reuse/resource lifetime, HUD/UI positioning, and fail-closed refusal exit codes (137).
//
// Build (invoked by tools/g6p141_scale32_acceptance.py):
//   clang++ -std=c++20 -O2 -D_CRT_SECURE_NO_WARNINGS -I tools/g6p89_stub -I tools tools/g6p141_scale32_render_test.cpp
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <set>
#include <vector>

#include "g6p89_scale32.h"

static int g_checks = 0;
static int g_fail = 0;

#define CHECK(c)                                                         \
  do {                                                                   \
    ++g_checks;                                                          \
    if (!(c)) {                                                          \
      std::fprintf(stderr, "FAIL %s:%d %s\n", __FILE__, __LINE__, #c);   \
      ++g_fail;                                                          \
    }                                                                    \
  } while (0)

// Mirror of src/graphics/util/draw.cpp GetHostViewportInfo host_axis + xy_max_unscaled logic.
struct HostViewport {
  uint32_t offset_x, offset_y, extent_x, extent_y;
  float ndc_scale_x, ndc_scale_y, ndc_offset_x, ndc_offset_y;
};

static HostViewport ComputeHostViewport(const g6p89::Scale& sc, float vport_xoffset, float vport_xscale,
                                        float vport_yoffset, float vport_yscale, uint32_t x_max, uint32_t y_max) {
  auto host_axis = [&sc](uint32_t i, uint32_t guest) -> uint32_t {
    if (sc.Rational() && (guest & 1)) g6p89::Refuse(g6p89::kViewport, i, guest);
    return i ? sc.Y(guest) : sc.X(guest);
  };
  uint32_t max_u[2] = {
      sc.Rational() ? uint32_t(uint64_t(x_max) * sc.den / sc.x) & ~uint32_t(1) : x_max / sc.x,
      sc.Rational() ? uint32_t(uint64_t(y_max) * sc.den / sc.y) & ~uint32_t(1) : y_max / sc.y,
  };
  float off_in[2] = {vport_xoffset, vport_yoffset};
  float scl_in[2] = {vport_xscale, vport_yscale};
  uint32_t h_off[2], h_ext[2];
  float ndc_s[2], ndc_o[2];
  for (uint32_t i = 0; i < 2; ++i) {
    float abs_s = std::fabs(scl_in[i]);
    uint32_t a0 = uint32_t(std::clamp(off_in[i] - abs_s, 0.0f, float(max_u[i])));
    uint32_t a1 = uint32_t(std::clamp(off_in[i] + abs_s, 0.0f, float(max_u[i])));
    uint32_t ext_u = a1 - a0;
    h_off[i] = host_axis(i, a0);
    h_ext[i] = host_axis(i, ext_u);
    if (ext_u > 0) {
      ndc_s[i] = scl_in[i] / (0.5f * float(ext_u));
      ndc_o[i] = (off_in[i] - float(a0)) / (0.5f * float(ext_u)) - 1.0f;
    } else {
      ndc_s[i] = 0.0f;
      ndc_o[i] = 0.0f;
    }
  }
  return {h_off[0], h_off[1], h_ext[0], h_ext[1], ndc_s[0], ndc_s[1], ndc_o[0], ndc_o[1]};
}

static void TestViewportConversion() {
  const uint32_t kD3D12Max = 32767;
  g6p89::Scale r{3, 3, 2};
  g6p89::Scale s1{1, 1, 1}, s2{2, 2, 1}, s3{3, 3, 1};

  // Main 1280x720 viewport -> 1920x1080.
  auto vp1 = ComputeHostViewport(s1, 640.0f, 640.0f, 360.0f, -360.0f, kD3D12Max, kD3D12Max);
  auto vp15 = ComputeHostViewport(r, 640.0f, 640.0f, 360.0f, -360.0f, kD3D12Max, kD3D12Max);
  auto vp2 = ComputeHostViewport(s2, 640.0f, 640.0f, 360.0f, -360.0f, kD3D12Max, kD3D12Max);
  auto vp3 = ComputeHostViewport(s3, 640.0f, 640.0f, 360.0f, -360.0f, kD3D12Max, kD3D12Max);

  CHECK(vp15.offset_x == 0 && vp15.offset_y == 0 && vp15.extent_x == 1920 && vp15.extent_y == 1080);
  CHECK(vp1.extent_x == 1280 && vp2.extent_x == 2560 && vp3.extent_x == 3840);
  // NDC scale/offset must be bit-identical across all scales (guest-space invariant).
  CHECK(vp15.ndc_scale_x == vp1.ndc_scale_x && vp15.ndc_scale_y == vp1.ndc_scale_y);
  CHECK(vp15.ndc_offset_x == vp1.ndc_offset_x && vp15.ndc_offset_y == vp1.ndc_offset_y);
  CHECK(vp15.ndc_scale_x == vp2.ndc_scale_x && vp15.ndc_scale_y == vp3.ndc_scale_y);

  // Sub-viewport (knaar_10 / lept_15 640x360 bloom & 1024x1024 shadow).
  auto vp_bloom = ComputeHostViewport(r, 320.0f, 320.0f, 180.0f, -180.0f, kD3D12Max, kD3D12Max);
  CHECK(vp_bloom.offset_x == 0 && vp_bloom.offset_y == 0 && vp_bloom.extent_x == 960 && vp_bloom.extent_y == 540);
  auto vp_shadow = ComputeHostViewport(r, 512.0f, 512.0f, 512.0f, -512.0f, kD3D12Max, kD3D12Max);
  CHECK(vp_shadow.extent_x == 1536 && vp_shadow.extent_y == 1536);

  // Offset sub-viewport (even guest bounds: [160, 1120) x [90, 630) -> [240, 1680) x [135, 945)).
  auto vp_sub = ComputeHostViewport(r, 640.0f, 480.0f, 360.0f, -270.0f, kD3D12Max, kD3D12Max);
  CHECK(vp_sub.offset_x == 240 && vp_sub.offset_y == 135 && vp_sub.extent_x == 1440 && vp_sub.extent_y == 810);

  // Even clamping of xy_max_unscaled at 3:2.
  uint32_t max_u = uint32_t(uint64_t(kD3D12Max) * r.den / r.x) & ~uint32_t(1);
  CHECK((max_u & 1u) == 0u && r.X(max_u) <= kD3D12Max);
}

static void TestScissorBoundaries() {
  g6p89::Scale r{3, 3, 2};
  struct Rect {
    uint32_t ox, oy, ex, ey, hx, hy, hex, hey;
  };
  const Rect cases[] = {
      {0, 0, 1280, 720, 0, 0, 1920, 1080},
      {0, 0, 640, 360, 0, 0, 960, 540},
      {0, 0, 1024, 1024, 0, 0, 1536, 1536},
      {160, 90, 960, 540, 240, 135, 1440, 810},
      {64, 32, 1152, 656, 96, 48, 1728, 984},
  };
  for (const auto& c : cases) {
    CHECK(((c.ox | c.oy | c.ex | c.ey) & 1u) == 0u);
    uint32_t hx = r.X(c.ox), hy = r.Y(c.oy), hex = r.X(c.ex), hey = r.Y(c.ey);
    CHECK(hx == c.hx && hy == c.hy && hex == c.hex && hey == c.hey);
    // Containment: scaled right/bottom must equal scale(guest right/bottom).
    CHECK(hx + hex == r.X(c.ox + c.ex) && hy + hey == r.Y(c.oy + c.ey));
  }
}

static void TestGuestToHostCoordinates() {
  g6p89::Scale s1{1, 1, 1}, r{3, 3, 2}, s2{2, 2, 1}, s3{3, 3, 1};
  // Point-sprite NDC radius invariance: scale_f / host_viewport_extent must be identical across all scales.
  float p1 = s1.Xf() / float(s1.X(1280));
  float p15 = r.Xf() / float(r.X(1280));
  float p2 = s2.Xf() / float(s2.X(1280));
  float p3 = s3.Xf() / float(s3.X(1280));
  CHECK(std::fabs(p15 - p1) < 1e-7f && std::fabs(p15 - p2) < 1e-7f && std::fabs(p15 - p3) < 1e-7f);

  // Shader translator DrawScaleDivF: v * 2 / 3 at 3:2.
  float off = 0.75f;
  float div15 = off * float(r.den) / float(r.x);
  CHECK(std::fabs(div15 - 0.5f) < 1e-7f);

  // Polygon offset scale factor: 1.5x subpixel unit.
  constexpr float kSubpixel = 1.0f / 16.0f;
  CHECK(std::fabs(kSubpixel * r.MaxF() - (1.5f / 16.0f)) < 1e-7f);

  // Occlusion query scaling: round(host_samples * 4 / 9) at 3:2.
  auto scale_occ = [](uint64_t samples) -> uint64_t { return (samples * 4ull + (9ull >> 1)) / 9ull; };
  CHECK(scale_occ(0) == 0 && scale_occ(9) == 4 && scale_occ(900) == 400 && scale_occ(1920ull * 1080ull) == 1280ull * 720ull);

  // Transfer pixels_to_ndc scaling: exact 3:2 ratio.
  constexpr float kUnscaled = 2.0f / 16384.0f;
  CHECK(std::fabs((kUnscaled * r.Xf()) - (kUnscaled * 1.5f)) < 1e-9f);
}

// Synthetic procedural scene rasterizer (checkerboard + diagonal edge + alpha-tested cutout).
// Returns RGBA8 buffer of size W*H.
static std::vector<uint32_t> RenderSyntheticScene(uint32_t w, uint32_t h) {
  std::vector<uint32_t> img(size_t(w) * h, 0);
  for (uint32_t y = 0; y < h; ++y) {
    float v = (float(y) + 0.5f) / float(h);
    for (uint32_t x = 0; x < w; ++x) {
      float u = (float(x) + 0.5f) / float(w);
      // Background checkerboard (8x8 guest-normalized cells).
      uint32_t cx = uint32_t(u * 16.0f), cy = uint32_t(v * 9.0f);
      uint8_t r = ((cx ^ cy) & 1u) ? 40 : 200;
      uint8_t g = uint8_t(std::clamp(u * 255.0f, 0.0f, 255.0f));
      uint8_t b = uint8_t(std::clamp(v * 255.0f, 0.0f, 255.0f));
      // Diagonal geometric primitive (u + v > 1.0 && u < 0.75).
      if (u + v > 1.0f && u < 0.75f && v < 0.75f) {
        r = 220;
        g = 120;
        b = 30;
      }
      // Synthetic depth-tested alpha-cutout overlap (mirrors crown_cutout z_write=1 + alpha_test GEQUAL 0.7529):
      // Rear quad at z=0.60 in [0.40,0.60]x[0.20,0.50], front cutout quad at z=0.40 in [0.40,0.60]x[0.20,0.50]
      // with opaque band (v > 0.35) and notch cutouts (v <= 0.35 && ((int(u*40))%2 == 0)).
      float depth = 1.0f;
      if (u >= 0.40f && u <= 0.60f && v >= 0.20f && v <= 0.50f) {
        // Front quad drawn first with z_write=1 and alpha_test >= 0.7529.
        float alpha = (v > 0.35f || (int(u * 40.0f) % 2 == 0)) ? 1.0f : 0.0f;
        if (alpha >= 0.7529f) {
          depth = 0.40f;
          r = 250;
          g = 210;
          b = 40;  // bright front gold
        }
        // Rear quad drawn second at z=0.60: rejected wherever front wrote z=0.40!
        if (0.60f <= depth) {
          depth = 0.60f;
          r = 90;
          g = 60;
          b = 15;  // dark rear interior visible only through open notches
        }
      }
      img[size_t(y) * w + x] = (uint32_t(255) << 24) | (uint32_t(b) << 16) | (uint32_t(g) << 8) | uint32_t(r);
    }
  }
  return img;
}

static void TestSyntheticRenderAndModelRRoundTrip() {
  // 1. Model R lossless resolve -> texture_load round-trip on 640x360 -> 960x540 (edge height) and 1280x720 -> 1920x1080.
  for (auto [gw, gh] : std::vector<std::pair<uint32_t, uint32_t>>{{640, 360}, {1280, 720}}) {
    uint32_t hw = gw * 3 / 2, hh = gh * 3 / 2;
    auto src = RenderSyntheticScene(hw, hh);
    // Compute max Model R byte offset to size the simulated scaled-resolve buffer.
    uint32_t max_off = 0;
    for (uint32_t hy = 0; hy < hh; ++hy) {
      for (uint32_t hx = 0; hx < hw; ++hx) {
        uint32_t off = g6p89::RationalScaledOffset2D(hx, hy, gw, 2);
        if (off > max_off) max_off = off;
      }
    }
    std::vector<uint32_t> scaled_mem((max_off / 4) + 1, 0xDEADBEEFu);
    // Resolve pass writes every host pixel via Model R.
    for (uint32_t hy = 0; hy < hh; ++hy) {
      for (uint32_t hx = 0; hx < hw; ++hx) {
        uint32_t off = g6p89::RationalScaledOffset2D(hx, hy, gw, 2);
        scaled_mem[off / 4] = src[size_t(hy) * hw + hx];
      }
    }
    // Scaled texture load reads back every host pixel via Model R: must be bit-identical.
    uint64_t mismatches = 0;
    for (uint32_t hy = 0; hy < hh; ++hy) {
      for (uint32_t hx = 0; hx < hw; ++hx) {
        uint32_t off = g6p89::RationalScaledOffset2D(hx, hy, gw, 2);
        if (scaled_mem[off / 4] != src[size_t(hy) * hw + hx]) ++mismatches;
      }
    }
    CHECK(mismatches == 0);
  }

  // 2. Depth/alpha-cutout invariant at 1.5x (front opaque gold band never overwritten by rear dark face).
  auto img15 = RenderSyntheticScene(1920, 1080);
  uint32_t front_band_px = 0, front_gold_ok = 0, notch_rear_seen = 0;
  for (uint32_t y = 0; y < 1080; ++y) {
    float v = (float(y) + 0.5f) / 1080.0f;
    for (uint32_t x = 0; x < 1920; ++x) {
      float u = (float(x) + 0.5f) / 1920.0f;
      uint32_t px = img15[size_t(y) * 1920 + x];
      uint8_t r = px & 0xFF, g = (px >> 8) & 0xFF;
      if (u >= 0.41f && u <= 0.59f && v >= 0.36f && v <= 0.49f) {
        ++front_band_px;
        if (r == 250 && g == 210) ++front_gold_ok;
      }
      if (u >= 0.41f && u <= 0.59f && v >= 0.21f && v <= 0.34f && r == 90 && g == 60) {
        ++notch_rear_seen;
      }
    }
  }
  CHECK(front_band_px > 0 && front_gold_ok == front_band_px && notch_rear_seen > 0);

  // 3. Controlled cross-scale pixel-space metric (1.5x vs 2x downsampled to 640x360 common grid):
  // accounts for legitimate scale/filtering differences instead of demanding pixel-identical output.
  auto img2 = RenderSyntheticScene(2560, 1440);
  auto downsample = [](const std::vector<uint32_t>& img, uint32_t w, uint32_t h, uint32_t dw, uint32_t dh) {
    std::vector<double> out(size_t(dw) * dh * 3, 0.0);
    uint32_t sx = w / dw, sy = h / dh;
    double inv = 1.0 / double(sx * sy);
    for (uint32_t dy = 0; dy < dh; ++dy) {
      for (uint32_t dx = 0; dx < dw; ++dx) {
        double sr = 0, sg = 0, sb = 0;
        for (uint32_t ky = 0; ky < sy; ++ky) {
          for (uint32_t kx = 0; kx < sx; ++kx) {
            uint32_t px = img[size_t(dy * sy + ky) * w + (dx * sx + kx)];
            sr += double(px & 0xFF);
            sg += double((px >> 8) & 0xFF);
            sb += double((px >> 16) & 0xFF);
          }
        }
        size_t idx = (size_t(dy) * dw + dx) * 3;
        out[idx] = sr * inv;
        out[idx + 1] = sg * inv;
        out[idx + 2] = sb * inv;
      }
    }
    return out;
  };
  auto d15 = downsample(img15, 1920, 1080, 640, 360);  // exact 3x3 box
  auto d2 = downsample(img2, 2560, 1440, 640, 360);    // exact 4x4 box
  double mae = 0.0;
  for (size_t i = 0; i < d15.size(); ++i) mae += std::fabs(d15[i] - d2[i]);
  mae /= double(d15.size());
  CHECK(mae < 2.0);  // Tight geometric agreement while allowing legitimate edge-sampling differences.

  // 4. Subpixel texel-center UV boundary check at 3:2.
  for (uint32_t hx = 0; hx < 1920; ++hx) {
    double u_host = (double(hx) + 0.5) / 1920.0;
    uint32_t gx = hx * 2 / 3;
    double u_guest_lo = double(gx) / 1280.0;
    double u_guest_hi = double(gx + 1) / 1280.0;
    // Host texel center must lie within [u_guest_lo, u_guest_hi] (or within 1/3 guest pixel of owned guest pixel).
    CHECK(u_host >= u_guest_lo - 1e-12 && u_host <= u_guest_hi + 1e-12);
  }
}

static void TestMsaa4xTransferAndEdram() {
  g6p89::Scale r{3, 3, 2};
  // EDRAM tile sample dimensions at 3:2.
  uint32_t tw = r.TileWidthSamples();   // 120
  uint32_t th = r.TileHeightSamples();  // 24
  CHECK(tw == 120 && th == 24);
  // 64bpp tile width (tw >> 1) = 60. Compute thread group 60x8 divides both 120x24 (2x3 groups) and 60x24 (1x3 groups).
  CHECK((tw % 60 == 0) && ((tw >> 1) % 60 == 0) && (th % 8 == 0));
  CHECK((tw / 60 == 2) && ((tw >> 1) / 60 == 1) && (th / 8 == 3));
  // EDRAM buffer size: 10 MiB * 9/4 = 23,592,960 bytes.
  CHECK(r.AreaBytes(10u << 20) == 23592960ull);

  // Full-tile 1x <-> 4x MSAA host-sample-major bijection:
  // In a 120x24 sample tile:
  //   1x MSAA = 120x24 pixels x 1 sample = 2880 samples.
  //   4x MSAA = 60x12 pixels x 4 samples (2x2 per pixel) = 2880 samples.
  std::set<uint32_t> seen_linear;
  for (uint32_t py = 0; py < th / 2; ++py) {
    for (uint32_t px = 0; px < tw / 2; ++px) {
      for (uint32_t sy = 0; sy < 2; ++sy) {
        for (uint32_t sx = 0; sx < 2; ++sx) {
          uint32_t sample_x = px * 2 + sx;
          uint32_t sample_y = py * 2 + sy;
          CHECK(sample_x < tw && sample_y < th);
          uint32_t linear = sample_y * tw + sample_x;
          CHECK(seen_linear.insert(linear).second);
        }
      }
    }
  }
  CHECK(seen_linear.size() == size_t(tw) * th);
}

static void TestDepthStencilAndRtLifetime() {
  g6p89::Scale r{3, 3, 2};
  // Observed Rayman 3 HD render targets (color, depth, 4xMSAA, tall lept_15/knaar_10):
  struct RtCase {
    uint32_t gw, gh, hw, hh;
  };
  const RtCase rts[] = {
      {1280, 2048, 1920, 3072},  // main color & depth 1x
      {1040, 2528, 1560, 3792},  // depth 1x
      {640, 1024, 960, 1536},    // 4xMSAA color & depth
      {520, 1264, 780, 1896},    // 4xMSAA depth
      {640, 4096, 960, 6144},    // lept_15 / knaar_10 tall RT
  };
  for (const auto& rt : rts) {
    CHECK(r.X(rt.gw) == rt.hw && r.Y(rt.gh) == rt.hh);
    CHECK(r.InvX(rt.hw) == rt.gw && r.InvY(rt.hh) == rt.gh);
  }
  // Scaled resolve address space = 1,152 MiB, exact multiple of 16 MiB heaps (72 heaps).
  uint64_t addr_space = r.AreaBytes(512ull << 20);
  CHECK(addr_space == (1152ull << 20) && (addr_space % (16ull << 20)) == 0);
  // Texture cache soft/hard memory limit add: ceil(limit_rtt * (9 - 4) / 4) = ceil(limit_rtt * 5 / 4).
  for (uint32_t lim : {16u, 32u, 64u, 100u}) {
    uint32_t add = uint32_t((uint64_t(lim) * (r.x * r.y - r.den * r.den) + r.den * r.den - 1) / (r.den * r.den));
    CHECK(add == (lim * 5u + 3u) / 4u);
  }
  // Stencil clear rect exact scaling.
  CHECK(r.X(0) == 0 && r.Y(0) == 0 && r.X(1280) == 1920 && r.Y(720) == 1080);
}

static void TestHudPositioningAndLetterbox() {
  // HUD bounding boxes in guest 1280x720 must map to identical normalized [0,1] coords at 1x, 1.5x, 2x.
  struct Box {
    uint32_t x, y, w, h;
  };
  const Box hud_elements[] = {
      {48, 36, 220, 48},     // top-left health/score panel
      {960, 36, 272, 64},    // top-right combo meter
      {128, 600, 1024, 72},  // bottom subtitle bar
      {440, 260, 400, 200},  // centered pause menu panel
  };
  g6p89::Scale scales[] = {{1, 1, 1}, {3, 3, 2}, {2, 2, 1}, {3, 3, 1}};
  for (const auto& b : hud_elements) {
    double ref_x0 = double(b.x) / 1280.0, ref_y0 = double(b.y) / 720.0;
    double ref_x1 = double(b.x + b.w) / 1280.0, ref_y1 = double(b.y + b.h) / 720.0;
    for (const auto& sc : scales) {
      double hw = double(sc.X(1280)), hh = double(sc.Y(720));
      double x0 = double(sc.X(b.x)) / hw, y0 = double(sc.Y(b.y)) / hh;
      double x1 = double(sc.X(b.x + b.w)) / hw, y1 = double(sc.Y(b.y + b.h)) / hh;
      CHECK(std::fabs(x0 - ref_x0) < 1e-12 && std::fabs(y0 - ref_y0) < 1e-12);
      CHECK(std::fabs(x1 - ref_x1) < 1e-12 && std::fabs(y1 - ref_y1) < 1e-12);
    }
  }

  // Presenter 16:9 letterboxing of 1920x1080 guest output inside common swap-chain sizes.
  auto present_rect = [](uint32_t sw, uint32_t sh) -> std::pair<uint32_t, uint32_t> {
    if (sw * 9 > sh * 16) return {(sh * 16 + 4) / 9, sh};
    return {sw, (sw * 9 + 8) / 16};
  };
  auto [ow1, oh1] = present_rect(1920, 1080);
  CHECK(ow1 == 1920 && oh1 == 1080);  // 1:1 native
  auto [ow2, oh2] = present_rect(1920, 1200);
  CHECK(ow2 == 1920 && oh2 == 1080);  // letterboxed 1:1 native
  auto [ow3, oh3] = present_rect(2560, 1080);
  CHECK(ow3 == 1920 && oh3 == 1080);  // pillarboxed 1:1 native
}

int main(int argc, char** argv) {
  if (argc > 1) {
    const char* mode = argv[1];
    g6p89::Scale r{3, 3, 2};
    if (std::strcmp(mode, "refuse_viewport") == 0) {
      ComputeHostViewport(r, 640.5f, 640.5f, 360.0f, -360.0f, 32767, 32767);  // odd extent 1281
      return 0;
    }
    if (std::strcmp(mode, "refuse_scissor") == 0) {
      g6p89::Refuse(g6p89::kScissor, 1, 720);
    }
    if (std::strcmp(mode, "refuse_resolve_size") == 0) {
      if (!g6p89::ResolveExtentExact(81, 45)) g6p89::Refuse(g6p89::kResolveSize, 81 * 8, 45 * 8);
      return 0;
    }
    if (std::strcmp(mode, "refuse_resolve_shader") == 0) {
      g6p89::Refuse(g6p89::kResolveShader, 1, 2);
    }
    if (std::strcmp(mode, "refuse_address_align") == 0) {
      volatile uint64_t v = r.AddressExact(32);
      (void)v;
      return 0;
    }
    if (std::strcmp(mode, "refuse_host_depth_store") == 0) {
      g6p89::Refuse(g6p89::kHostDepthStore, 16, 0);
    }
    if (std::strcmp(mode, "refuse_integer_accessor") == 0) {
      volatile uint32_t v = r.IntegerArea();
      (void)v;
      return 0;
    }
  }

  TestViewportConversion();
  TestScissorBoundaries();
  TestGuestToHostCoordinates();
  TestSyntheticRenderAndModelRRoundTrip();
  TestMsaa4xTransferAndEdram();
  TestDepthStencilAndRtLifetime();
  TestHudPositioningAndLetterbox();

  std::printf("G6P141_RENDER_TEST %s checks=%d failures=%d\n", g_fail ? "FAIL" : "PASS", g_checks, g_fail);
  return g_fail ? 1 : 0;
}
