// Host test for tools/r3hd_ds_speaker.h (D-141): settings, the XMA2 frame splitter, the quad layout, the activation
// rule, the pickup mirror (E-334) and the trace predicates. No SDL, no FFmpeg, no device, no game. With a game data
// root as the first argument it also checks the person's own clips (size, FNV-1a 64, 63 / 130 frames) and the pickup
// mirror on the real pickup clip; without one that part is skipped and said so.
// Ends with R3HD_DS_SPEAKER_TEST PASS n/n.
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <string>
#include <vector>

#include "r3hd_ds_speaker.h"

using namespace r3hd_ds_speaker;
using r3hd_ds::state::Guest;

namespace {

int g_pass = 0, g_fail = 0;
void Check(const char* what, bool ok) {
  if (ok) {
    ++g_pass;
  } else {
    ++g_fail;
    std::printf("FAIL %s\n", what);
  }
}

// Builds a single-stream XMA2 clip from frame lengths (bits): frames are bit-contiguous across 2 KiB packets, each
// packet header says how many frames begin in it, first frame offset 0 for packet 0, metadata 1, skip 0. Frame bodies
// are a deterministic pattern so the splitter's copies can be compared. The tail is filled with 1 bits (0x7FFF).
struct Built {
  std::vector<uint8_t> data;
  std::vector<std::vector<uint8_t>> frames;   // expected payload bits of each frame, as bytes from bit 0
};

// A length of 0 pads the rest of the current packet with 1 bits (the next frame begins at the next packet), as the
// encoder does when a frame would not fit.
Built Build(const std::vector<uint32_t>& lengths, size_t packets) {
  const size_t payload = kPacketBytes - 4;
  std::vector<uint8_t> bits(packets * payload * 8, 1);
  Built b;
  size_t pos = 0;
  std::vector<int> begins(packets, 0);
  std::vector<size_t> first(packets, 0);
  uint32_t seed = 12345;
  for (uint32_t len : lengths) {
    if (len == 0) {
      pos = (pos / (payload * 8) + 1) * payload * 8;
      continue;
    }
    if (begins[pos / (payload * 8)]++ == 0) first[pos / (payload * 8)] = pos % (payload * 8);
    std::vector<uint8_t> expect((len + 7) / 8, 0);
    for (uint32_t i = 0; i < len; ++i) {
      uint32_t v;
      if (i < 15) {
        v = (len >> (14 - i)) & 1;
      } else {
        seed = seed * 1103515245u + 12345u;
        v = (seed >> 16) & 1;
      }
      bits[pos + i] = static_cast<uint8_t>(v);
      if (v) expect[i >> 3] |= static_cast<uint8_t>(0x80u >> (i & 7));
    }
    b.frames.push_back(expect);
    pos += len;
  }
  b.data.assign(packets * kPacketBytes, 0);
  for (size_t p = 0; p < packets; ++p) {
    uint8_t* h = b.data.data() + p * kPacketBytes;
    h[0] = static_cast<uint8_t>((begins[p] << 2) | (first[p] >> 13));
    h[1] = static_cast<uint8_t>(first[p] >> 5);
    h[2] = static_cast<uint8_t>(((first[p] & 0x1F) << 3) | 1);   // metadata 1 = XMA2
    h[3] = 0;
    for (size_t i = 0; i < payload * 8; ++i) {
      if (bits[p * payload * 8 + i]) h[4 + (i >> 3)] |= static_cast<uint8_t>(0x80u >> (i & 7));
    }
  }
  return b;
}

struct Captured {
  std::vector<std::vector<uint8_t>> frames;
  bool layout_ok = true;
};

int Split(const std::vector<uint8_t>& data, Captured& c) {
  return SplitXma2(data.data(), data.size(), [&](const uint8_t* bytes, size_t size) {
    // bytes[0]: padding start 0 (bits 7..5), padding end (bits 4..2) = unused bits of the last byte.
    if ((bytes[0] & 0xE3) != 0) c.layout_ok = false;
    c.frames.emplace_back(bytes + 1, bytes + size);
    return true;
  });
}

Guest G(bool gameplay, int code) {
  Guest g;
  g.gameplay = gameplay;
  g.world = gameplay ? 2 : 0;
  g.power_code = gameplay ? code : r3hd_ds::state::kPowerCodeUnread;
  return g;
}

}  // namespace

// The device side is not part of this test: Post only counts what OnXmaBuffer reports.
int g_pickups = 0, g_alerts = 0, g_downs = 0;
void r3hd_ds_speaker::Post(Request r, int) {
  g_pickups += r == Request::kPickup;
  g_alerts += r == Request::kAlert;
  g_downs += r == Request::kPowerDown;
}

int main(int argc, char** argv) {
  // Settings: read once, default off / 50.
  {
    _putenv("R3HD_DS_SPEAKER=on");
    _putenv("R3HD_DS_SPEAKER_VOLUME=35");
    const Config c = Configured();
    Check("settings: on and volume read from the environment", c.on && c.volume == 35 && !c.trace);
    _putenv("R3HD_DS_SPEAKER=off");
    Check("settings: read once per process", Configured().on);
    Config d;
    Check("settings: defaults off / 50", !d.on && d.volume == 50);
    Check("settings: volume percent parsed", r3hd_ds::state::Percent("R3HD_DS_SPEAKER_VOLUME", 50) == 35);
    _putenv("R3HD_DS_SPEAKER_VOLUME=150");
    Check("settings: volume above 100 falls back", r3hd_ds::state::Percent("R3HD_DS_SPEAKER_VOLUME", 50) == 50);
  }

  // FNV-1a 64 reference values.
  Check("fnv: empty", Fnv1a64(nullptr, 0) == 0xCBF29CE484222325ull);
  Check("fnv: 'a'", Fnv1a64(reinterpret_cast<const uint8_t*>("a"), 1) == 0xAF63DC4C8601EC8Cull);
  Check("clip: identity", kPowerUp.offset == 0x759800 && kPowerUp.size == 10240 && kPowerUp.rate == 22084 &&
                              kPowerUp.frames == 63 && kPowerUp.size % kPacketBytes == 0 && kPowerUp.channels == 1);
  Check("clip: can pickup identity (E-334)", kCanPickup.offset == 0x27000 && kCanPickup.size == 38912 &&
                                                 kCanPickup.rate == 22054 && kCanPickup.frames == 130 &&
                                                 kCanPickup.channels == 2 && kCanPickup.size % kPacketBytes == 0 &&
                                                 !std::strcmp(kCanPickup.path, "GAMEDATAbin/WORLD/SOUND/Static.hsx"));
  Check("clip: expiry warning identity (E-335)", kTimerAlert.offset == 0x1F6000 && kTimerAlert.size == 8192 &&
                                                     kTimerAlert.rate == 11025 && kTimerAlert.frames == 36 &&
                                                     kTimerAlert.channels == 1 &&
                                                     !std::strcmp(kTimerAlert.path, kCanPickup.path));
  Check("clip: expiry identity (E-335)", kPowerDown.offset == 0x2C6000 && kPowerDown.size == 4096 &&
                                             kPowerDown.rate == 10997 && kPowerDown.frames == 19 &&
                                             kPowerDown.channels == 1 && !std::strcmp(kPowerDown.path, kCanPickup.path));
  Check("clip: the mirrored clips' sizes differ (one hash per buffer at most)",
        kCanPickup.size != kTimerAlert.size && kCanPickup.size != kPowerDown.size && kTimerAlert.size != kPowerDown.size);

  // Splitter: frames within a packet, across packet boundaries, after a padded packet tail.
  {
    std::vector<uint32_t> lengths;
    for (int i = 0; i < 40; ++i) lengths.push_back(600 + (i * 977) % 2600);   // some cross a 16,320-bit packet payload
    size_t total = 0;
    for (uint32_t len : lengths) total += len;
    const Built b = Build(lengths, total / ((kPacketBytes - 4) * 8) + 1);
    Check("split: the synthetic clip spans several packets", b.data.size() >= 4 * kPacketBytes);
    Captured c;
    const int n = Split(b.data, c);
    Check("split: every frame found", n == static_cast<int>(lengths.size()));
    bool same = c.frames.size() == b.frames.size();
    for (size_t i = 0; same && i < c.frames.size(); ++i) same = c.frames[i] == b.frames[i];
    Check("split: each frame's bits copied exactly, also across packets", same);
    Check("split: padding byte layout of XmaContext::PreparePacket", c.layout_ok);
  }
  {
    // The real clip's shape: whole frames, the packet tail padded, the next frame at the next packet's start.
    const std::vector<uint32_t> lengths{3000, 3100, 2900, 3000, 0, 2500, 2600, 0, 1200};
    const Built b = Build(lengths, 3);
    Captured c;
    bool same = Split(b.data, c) == 7 && c.frames.size() == b.frames.size();
    for (size_t i = 0; same && i < c.frames.size(); ++i) same = c.frames[i] == b.frames[i];
    Check("split: a padded packet tail is skipped, the next packet's frames follow", same);
  }
  {
    Built b = Build({1000, 2000}, 1);
    Captured c;
    Check("split: frames counted by the packet headers", Split(b.data, c) == 2);
    std::vector<uint8_t> bad = b.data;
    bad[0] = 3 << 2;
    Check("split: a header promising a frame over padding refused", Split(bad, c) == -1);
    bad = b.data;
    bad[3] = 1;
    Check("split: packet skip != 0 refused", Split(bad, c) == -1);
    bad = b.data;
    bad[2] = 2;
    Check("split: metadata != 1 (not XMA2) refused", Split(bad, c) == -1);
    bad = b.data;
    bad[1] = 1;   // first frame offset 32 bits in
    Check("split: first frame not at the start refused", Split(bad, c) == -1);
    bad.resize(1000);
    Check("split: partial packet refused", Split(bad, c) == -1);
    Check("split: empty refused", SplitXma2(nullptr, 0, [](const uint8_t*, size_t) { return true; }) == -1);
    int calls = 0;
    Check("split: a frame the decoder refuses ends the split",
          SplitXma2(b.data.data(), b.data.size(), [&](const uint8_t*, size_t) { return ++calls < 1; }) == -1 &&
              calls == 1);
  }

  // Quad layout.
  {
    std::vector<float> mono(kDecoderStartPadding + 3, 0.0f);
    mono[kDecoderStartPadding] = 0.5f;
    mono[kDecoderStartPadding + 1] = 1.5f;
    mono[kDecoderStartPadding + 2] = -2.0f;
    const auto q = QuadFromMono(mono);
    Check("quad: start padding dropped, four channels", q.size() == 12);
    Check("quad: jingle on both front channels", q[0] == 0.5f && q[1] == 0.5f);
    Check("quad: haptic (back) channels silent", q[2] == 0 && q[3] == 0 && q[6] == 0 && q[7] == 0 && q[10] == 0 &&
                                                     q[11] == 0);
    Check("quad: clamped to [-1, 1]", q[4] == 1.0f && q[8] == -1.0f);
    Check("quad: too short gives nothing", QuadFromMono(std::vector<float>(kDecoderStartPadding)).empty());
  }

  // Activation rule.
  {
    Tracker t;
    int code = -1;
    const uint32_t a = 111, b = 222;
    // snipe_00 (E-322): the level start writes 5, its script 3 about 0.6 s later; the game plays no jingle.
    bool quiet = true;
    for (uint32_t i = 0; i < 36; ++i) quiet &= t.Step(G(true, 5), b) == Event::kNone;
    for (uint32_t i = 0; i < 200; ++i) quiet &= t.Step(G(true, 3), b) == Event::kNone;
    Check("rule: a power set by the level script while the level settles is no pickup", quiet);
    Check("rule: first read of a level is a baseline (level starts with no power)", t.Step(G(true, 5), a) == Event::kNone);
    Check("rule: a change while the level settles only moves the baseline",
          t.Step(G(true, 3), a) == Event::kNone && t.Step(G(true, 5), a) == Event::kNone);
    for (uint32_t i = 3; i < Tracker::kSettleFrames; ++i) quiet &= t.Step(G(true, 5), a) == Event::kNone;
    Check("rule: every further frame without a change gives nothing", quiet && t.Step(G(true, 5), a) == Event::kNone);
    Check("rule: none -> Shock Rocket activates", t.Step(G(true, 3), a, &code) == Event::kActivate && code == 3);
    Check("rule: the power held on the next frames gives nothing", t.Step(G(true, 3), a) == Event::kNone &&
                                                                       t.Step(G(true, 3), a) == Event::kNone);
    Check("rule: pause stops a playing jingle once", t.Step(G(false, 3), a) == Event::kStop &&
                                                         t.Step(G(false, 3), a) == Event::kNone);
    Check("rule: resume with the same power gives nothing", t.Step(G(true, 3), a) == Event::kNone);
    Check("rule: an unreadable frame keeps the baseline", t.Step(G(true, 15), a) == Event::kNone &&
                                                              t.Step(G(true, 3), a) == Event::kNone);
    Check("rule: another power while one is active activates", t.Step(G(true, 4), a, &code) == Event::kActivate &&
                                                                   code == 4);
    Check("rule: expiry / hit / death (-> 5) gives nothing", t.Step(G(true, 5), a) == Event::kNone);
    // A same-level reload whose script sets the power again (snipe_00's pattern after a death): no pickup.
    quiet = true;
    for (uint32_t i = 0; i < 36; ++i) quiet &= t.Step(G(true, 5), a) == Event::kNone;
    for (uint32_t i = 0; i < 200; ++i) quiet &= t.Step(G(true, 4), a) == Event::kNone;
    Check("rule: a power set again right after a reload is no pickup", quiet);
    quiet = t.Step(G(true, 5), a) == Event::kNone;
    for (uint32_t i = 1; i < Tracker::kSettleFrames; ++i) quiet &= t.Step(G(true, 5), a) == Event::kNone;
    Check("rule: a new pickup after expiry and the settle activates",
          quiet && t.Step(G(true, 0), a, &code) == Event::kActivate && code == 0);
    Check("rule: front end stops", t.Step(G(false, 0), a) == Event::kStop);
    Check("rule: a level that starts with a power is no pickup", t.Step(G(true, 3), b) == Event::kNone);
    for (uint32_t i = 1; i < Tracker::kSettleFrames; ++i) t.Step(G(true, 3), b);
    for (uint32_t i = 0; i < Tracker::kSettleFrames; ++i) t.Step(G(true, 5), b);
    Check("rule: ... and its later pickup still counts", t.Step(G(true, 2), b, &code) == Event::kActivate && code == 2);
    Check("rule: level change with the same code is a baseline", t.Step(G(true, 2), a) == Event::kNone);
    for (uint32_t i = 1; i < Tracker::kSettleFrames; ++i) t.Step(G(true, 2), a);
    for (uint32_t i = 0; i < Tracker::kSettleFrames; ++i) t.Step(G(true, 5), a);
    Check("rule: Throttle Copter (1) activates", t.Step(G(true, 1), a, &code) == Event::kActivate && code == 1);
    Check("rule: out-of-range code ignored", t.Step(G(true, 9), a) == Event::kNone && t.last == 1);
  }

  // Trace predicates.
  Check("trace: file name case-insensitive", IsClipFile("STREAM.H00") && IsClipFile("Stream.h00") &&
                                                 !IsClipFile("Stream.h01") && !IsClipFile("Stream.h0"));
  Check("trace: overlap", ReadOverlapsClip(0x759800, 1) && ReadOverlapsClip(0x758000, 0x2000) &&
                              ReadOverlapsClip(0x75BFFF, 1) && !ReadOverlapsClip(0x75C000, 0x800) &&
                              !ReadOverlapsClip(0x750000, 0x9800));

  // The game's own pickup, warning and expiry sounds (E-334, E-335): a buffer counts when a context reaches it or
  // starts it again, not while it is read; only a clip's exact size and hash are that clip.
  {
    XmaWatch w;
    const bool first = FreshBuffer(w, 0x1862E000, 32);
    const bool reading = FreshBuffer(w, 0x1862E000, 4000) || FreshBuffer(w, 0x1862E000, 4000);
    const bool restart = FreshBuffer(w, 0x1862E000, 32);
    const bool other = FreshBuffer(w, 0x1DB5C000, 32);
    const bool back = FreshBuffer(w, 0x1862E000, 32);
    Check("xma: first start, restart and another buffer count; reading on does not",
          first && !reading && restart && other && back);
    std::vector<uint8_t> zeros(kCanPickup.size, 0);
    Check("xma: only a clip's size and hash are that clip",
          !MirroredClip(nullptr, kCanPickup.size) && !MirroredClip(zeros.data(), kCanPickup.size) &&
              !MirroredClip(zeros.data(), kTimerAlert.size) && !MirroredClip(zeros.data(), kPowerDown.size) &&
              !MirroredClip(zeros.data(), 2048));
    g_pickups = g_alerts = g_downs = 0;
    OnXmaBuffer(7, 0x1862E000, zeros.data(), kCanPickup.size, 32);
    OnXmaBuffer(8, 0x1DCBB000, zeros.data(), kTimerAlert.size, 32);
    OnXmaBuffer(9, 0x1DB5F000, zeros.data(), kPowerDown.size, 32);
    Check("xma: other sounds of the same sizes post nothing", g_pickups + g_alerts + g_downs == 0);
  }

  // Audio route (E-332): exactly the bytes of the diagnostic's step C (path 2, volume 0x50, pre-gain 2) and of its
  // restore (path 0 alone); nothing outside the audio fields, so light bar, triggers and rumble are not touched.
  {
    uint8_t on[kRouteBlockBytes], off[kRouteBlockBytes];
    std::memset(on, 0xAA, sizeof on);
    std::memset(off, 0xAA, sizeof off);
    RouteBlock(true, on);
    RouteBlock(false, off);
    Check("route: block is SDL's 47-byte DS5EffectsState_t", kRouteBlockBytes == 47);
    Check("route: speaker enables audio control, speaker volume, audio control 2", on[0] == 0xA0 && on[1] == 0x80);
    Check("route: speaker volume 0x50, path 2 (L_L_R), pre-gain 2", on[5] == 0x50 && on[7] == 0x20 && on[37] == 2);
    bool rest = true;
    for (size_t i = 0; i < kRouteBlockBytes; ++i)
      if (i != 0 && i != 1 && i != 5 && i != 7 && i != 37) rest &= on[i] == 0;
    Check("route: speaker block leaves every other byte zero (no rumble, light, trigger, mute bits)", rest);
    bool zero = true;
    for (size_t i = 1; i < kRouteBlockBytes; ++i) zero &= off[i] == 0;
    Check("route: default = audio control valid with path 0 only", off[0] == 0x80 && zero);
    RouteState r;
    const uint32_t a = r.Want(true), b = r.Want(false), c = r.Want(true);
    Check("route: wants are distinct, carry the speaker bit, never 0", a != b && b != c && a != c && (a & 1) &&
                                                                          !(b & 1) && (c & 1) && a && b && c);
    Check("route: nothing written until the input driver acknowledges", r.written.load() == 0 && r.wanted == c);
  }

  // The person's own clip, when a game data root is given.
  if (argc > 1) {
    const std::string path = std::string(argv[1]) + "/" + kPowerUp.path;
    std::ifstream in(path, std::ios::binary);
    std::vector<uint8_t> raw(kPowerUp.size);
    in.seekg(kPowerUp.offset);
    in.read(reinterpret_cast<char*>(raw.data()), static_cast<std::streamsize>(raw.size()));
    const bool read = in && in.gcount() == static_cast<std::streamsize>(raw.size());
    Check("data: clip readable from the game data root", read);
    Check("data: FNV-1a 64 matches", read && Fnv1a64(raw.data(), raw.size()) == kPowerUp.fnv);
    Captured c;
    Check("data: the clip splits into 63 XMA2 frames", read && Split(raw, c) == static_cast<int>(kPowerUp.frames) &&
                                                           c.layout_ok);

    std::ifstream can_in(std::string(argv[1]) + "/" + kCanPickup.path, std::ios::binary);
    std::vector<uint8_t> can(kCanPickup.size);
    can_in.seekg(kCanPickup.offset);
    can_in.read(reinterpret_cast<char*>(can.data()), static_cast<std::streamsize>(can.size()));
    const bool can_read = can_in && can_in.gcount() == static_cast<std::streamsize>(can.size());
    Check("data: pickup clip readable, FNV-1a 64 matches", can_read && Fnv1a64(can.data(), can.size()) == kCanPickup.fnv);
    Captured cc;
    Check("data: the pickup clip splits into 130 XMA2 frames",
          can_read && Split(can, cc) == static_cast<int>(kCanPickup.frames) && cc.layout_ok);
    // As the game played it three times in one menu_20 run (E-334): the whole clip as one buffer from bit 32, on any
    // context; a context reading on in it posts nothing more.
    g_pickups = 0;
    OnXmaBuffer(4, 0x1862E000, can.data(), kCanPickup.size, 32);
    OnXmaBuffer(4, 0x1862E000, can.data(), kCanPickup.size, 9000);
    OnXmaBuffer(6, 0x1862E000, can.data(), kCanPickup.size, 32);
    OnXmaBuffer(5, 0x1862E000, can.data(), kCanPickup.size, 32);
    OnXmaBuffer(kXmaContexts, 0x1862E000, can.data(), kCanPickup.size, 32);
    Check("data: each pickup start posts one pickup (3), reading on and an out-of-range context post none",
          can_read && g_pickups == 3);

    // E-335: the expiry warning and the expiry, as one menu_20 Shock Rocket expiry started them (2.000 s apart, each
    // whole clip as one buffer from bit 32; the warning context read on, then a later one restarted the clip).
    const auto load = [&](const Clip& clip, std::vector<uint8_t>& out) {
      std::ifstream f(std::string(argv[1]) + "/" + clip.path, std::ios::binary);
      out.assign(clip.size, 0);
      f.seekg(clip.offset);
      f.read(reinterpret_cast<char*>(out.data()), static_cast<std::streamsize>(out.size()));
      return f && f.gcount() == static_cast<std::streamsize>(out.size()) && Fnv1a64(out.data(), out.size()) == clip.fnv;
    };
    std::vector<uint8_t> alert, down;
    const bool alert_read = load(kTimerAlert, alert), down_read = load(kPowerDown, down);
    Check("data: warning and expiry clips readable, FNV-1a 64 matches", alert_read && down_read);
    Captured ac, dc;
    Check("data: warning 36 / expiry 19 XMA2 frames",
          alert_read && down_read && Split(alert, ac) == static_cast<int>(kTimerAlert.frames) && ac.layout_ok &&
              Split(down, dc) == static_cast<int>(kPowerDown.frames) && dc.layout_ok);
    g_pickups = g_alerts = g_downs = 0;
    OnXmaBuffer(5, 0x1DCBB000, alert.data(), kTimerAlert.size, 32);
    OnXmaBuffer(5, 0x1DCBB000, alert.data(), kTimerAlert.size, 20000);
    OnXmaBuffer(8, 0x1DB5F000, down.data(), kPowerDown.size, 32);
    OnXmaBuffer(8, 0x1DB5F000, down.data(), kPowerDown.size, 9000);
    OnXmaBuffer(5, 0x1DCBB000, alert.data(), kTimerAlert.size, 32);
    Check("data: each warning / expiry start posts its own request once, nothing else",
          alert_read && down_read && g_alerts == 2 && g_downs == 1 && g_pickups == 0);
  } else {
    std::printf("data checks skipped (no game data root given)\n");
  }

  std::printf("R3HD_DS_SPEAKER_TEST %s %d/%d\n", g_fail ? "FAIL" : "PASS", g_pass, g_pass + g_fail);
  return g_fail ? 1 : 0;
}
