// DualSense controller speaker (D-141): the title's own power-up jingle through the speaker of a USB DualSense when
// Rayman gains a power. Installed into the SDK as <rex/r3hd_ds_speaker.h> by tools/r3hd_dualsense_patch.py. This
// header is the pure part (settings, the clip's identity, the XMA2 frame splitter, the activation rule), tested by
// tools/r3hd_ds_speaker_test.cpp; the device side is <rex/r3hd_ds_speaker_sdl.h> (one translation unit: the SDL audio
// driver). Nothing here writes guest memory, and the game's own sound is never changed or routed.
//
// Clip (RE_NOTES "DualSense speaker", local data): fixe.hxx event Play_MJ_Rm_01PowerUp (cuuid 1:003B0028) -> wave
// resource MJ_Rm_02PowerUp01 (3:003B004C) -> CXBoxStreamHWWaveFileIdObj 575E80A3:2E304F1F = STREAM.H00 offset 0x759800,
// 10,240 bytes: five 2 KiB XMA2 packets, 63 frames, mono, 22,084 Hz, 32,256 encoded samples. It is read from the
// person's own game data at run time and checked by size and FNV-1a 64 before it is decoded; nothing is shipped.
//
// Can pickup (E-334): every power-up can plays one shared asset, OI_WheelFistCan = Static.hsx 0x27000, 38,912 bytes,
// stereo, 22,054 Hz (the bank's five per-power events Play_OI_{ForceFist,Grapnel,MissileFist,SuperHelico,WheelFist}Can
// all lead to it). The game plays it at every pickup, also of a can taken again while its power is still active, when
// the jingle does not play: so it is not inferred from the power code but mirrored from the game's own sound: the XMA
// context reports each input buffer it starts (OnXmaBuffer), and one equal in size and hash to the clip is a pickup.
//
// Expiry warning and expiry (E-335): the player's common power-up code (YLT_RaymanModel, identical in all 61 scanned
// levels) sends fixe.hxx Play_RSb_TimerOffAlert01 once when under 2 s of any power's timer remain (macro 40C79BC0) and
// Play_MJ_Rm_01PowerDown whenever the power code becomes 5 (macro 40C79B28; also a hit that ends the power). Each
// event leads to one asset: RSb_TimerOffAlert01 = Static.hsx 0x1F6000, 8,192 bytes, mono 11,025 Hz, 36 frames;
// MJ_Rm_02PoweDown01 = Static.hsx 0x2C6000, 4,096 bytes, mono 10,997 Hz, 19 frames. Both are mirrored from the game's
// own XMA buffer start like the pickup: no timer or threshold is computed here.
//
// Settings: R3HD_DS_SPEAKER = on | off (default off), R3HD_DS_SPEAKER_VOLUME = 0..100 percent (default 50), read once
// (a change applies at the next game start). R3HD_DS_SPEAKER_TRACE=1 (hidden tools) logs the guest's reads of the
// clip's range. A hidden run (R3HD_NONINTRUSIVE) never opens an audio device for this (D-053).
#pragma once

#include <atomic>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <vector>

#if __has_include(<rex/r3hd_ds_state.h>)
#include <rex/r3hd_ds_state.h>
#else
#include "r3hd_ds_state.h"   // the standalone test
#endif

namespace r3hd_ds_speaker {

struct Config {
  bool on = false;
  uint8_t volume = 50;   // percent: the stream gain of this effect only
  bool trace = false;
};

inline Config Configured() {
  static const Config c = [] {
    Config x;
    x.on = r3hd_ds::state::On("R3HD_DS_SPEAKER");
    x.volume = r3hd_ds::state::Percent("R3HD_DS_SPEAKER_VOLUME", x.volume);
    const char* t = std::getenv("R3HD_DS_SPEAKER_TRACE");
    x.trace = t && !std::strcmp(t, "1");
    return x;
  }();
  return c;
}

struct Clip {
  const char* name;
  const char* path;        // relative to the game data root
  uint32_t offset, size;   // bytes in that file
  uint32_t rate;           // Hz
  uint32_t frames;         // XMA frames
  uint64_t fnv;            // FNV-1a 64 of the raw bytes
  uint8_t channels;        // 1 or 2 (one XMA2 stream either way)
};

inline constexpr Clip kPowerUp{"MJ_Rm_02PowerUp01", "GAMEDATAbin/WORLD/SOUND/Stream.h00", 0x759800, 0x2800, 22084, 63,
                               0x2539548C17FD455Dull, 1};
inline constexpr Clip kCanPickup{"OI_WheelFistCan", "GAMEDATAbin/WORLD/SOUND/Static.hsx", 0x27000, 0x9800, 22054, 130,
                                 0xA0EC8EFBB8920117ull, 2};
inline constexpr Clip kTimerAlert{"RSb_TimerOffAlert01", "GAMEDATAbin/WORLD/SOUND/Static.hsx", 0x1F6000, 0x2000, 11025,
                                  36, 0x89E14B998AE79070ull, 1};
inline constexpr Clip kPowerDown{"MJ_Rm_02PoweDown01", "GAMEDATAbin/WORLD/SOUND/Static.hsx", 0x2C6000, 0x1000, 10997, 19,
                                 0xBE40B703286E972Full, 1};

inline uint64_t Fnv1a64(const uint8_t* p, size_t n) {
  uint64_t h = 0xCBF29CE484222325ull;
  for (size_t i = 0; i < n; ++i) h = (h ^ p[i]) * 0x100000001B3ull;
  return h;
}

// XMA2 as the clip stores it: 2048-byte packets with a 32-bit header (count of frames that begin in the packet 6 bits,
// bit offset of the first of them after the header 15 bits, metadata 3 bits = 1 for XMA2, packet skip 8 bits). Each
// frame starts with its 15-bit length in bits and may run on into the next packet's payload (the payloads are
// bit-contiguous once the headers are taken out); a packet's unused tail is padding of 1 bits. Only a single-stream
// clip is accepted: every packet's skip is 0 and the first frame starts right after the first header. For each frame,
// frame(bytes, size) gets the frame's bits copied to bytes[1..] from bit 0 with bytes[0] = the xmaframes decoder's
// padding byte (the SDK's XmaContext::PreparePacket layout). Returns the number of frames, or -1 when the clip is not
// of that shape or frame() refused one.
inline constexpr uint32_t kPacketBytes = 2048;
inline constexpr uint32_t kHeaderBits = 32;
inline constexpr uint32_t kSamplesPerFrame = 512;
inline constexpr uint32_t kDecoderStartPadding = 192;   // the xmaframes decoder's delay (SDK XmaContext)

template <typename Frame>
int SplitXma2(const uint8_t* data, size_t size, Frame&& frame) {
  if (!data || size == 0 || size % kPacketBytes) return -1;
  const size_t packets = size / kPacketBytes;
  const size_t payload_bits = (kPacketBytes - kHeaderBits / 8) * 8;
  std::vector<uint8_t> payload;
  payload.reserve(packets * payload_bits / 8);
  for (size_t p = 0; p < packets; ++p) {
    const uint8_t* h = data + p * kPacketBytes;
    const uint32_t first = ((h[0] & 3u) << 13) | (h[1] << 5) | (h[2] >> 3);
    if ((h[2] & 7) != 1 || h[3] != 0 || (p == 0 && first != 0)) return -1;
    payload.insert(payload.end(), h + kHeaderBits / 8, h + kPacketBytes);
  }
  const size_t total_bits = payload.size() * 8;
  auto bit = [&](size_t i) { return (payload[i >> 3] >> (7 - (i & 7))) & 1u; };
  std::vector<uint8_t> buf;
  int count = 0;
  for (size_t p = 0; p < packets; ++p) {
    const uint8_t* h = data + p * kPacketBytes;
    const uint32_t begins = h[0] >> 2;
    size_t pos = p * payload_bits + (((h[0] & 3u) << 13) | (h[1] << 5) | (h[2] >> 3));
    for (uint32_t f = 0; f < begins; ++f) {
      if (pos + 15 > total_bits) return -1;
      uint32_t length = 0;
      for (int i = 0; i < 15; ++i) length = (length << 1) | bit(pos + i);
      if (length == 0x7FFF || length < 15 || pos + length > total_bits) return -1;
      const size_t bytes = 1 + (length + 7) / 8;
      buf.assign(bytes, 0);
      for (uint32_t i = 0; i < length; ++i) {
        if (bit(pos + i)) buf[1 + (i >> 3)] |= static_cast<uint8_t>(0x80u >> (i & 7));
      }
      const uint32_t padding_end = static_cast<uint32_t>(bytes * 8 - (8 + length));
      buf[0] = static_cast<uint8_t>((padding_end & 7) << 2);
      if (!frame(buf.data(), bytes)) return -1;
      pos += length;
      ++count;
    }
  }
  return count;
}

// Mono decoder output (concatenated 512-sample blocks) -> the stream's source: four interleaved float channels in the
// order of a DualSense USB endpoint (front left, front right, back left, back right = KSAUDIO_SPEAKER_QUAD, channel
// mask 0x33: VERIFIED as Windows stored it on this PC). The jingle goes to both front channels: the headset pair, of
// which the speaker plays the right one once the route below is sent (E-332); the back pair (the haptic actuators: SUPPORTED by community documentation, not observed
// here) stays silent. The decoder's start padding is dropped.
inline std::vector<float> QuadFromMono(const std::vector<float>& mono) {
  std::vector<float> out;
  if (mono.size() <= kDecoderStartPadding) return out;
  out.reserve((mono.size() - kDecoderStartPadding) * 4);
  for (size_t i = kDecoderStartPadding; i < mono.size(); ++i) {
    float s = mono[i];
    s = s > 1.0f ? 1.0f : (s < -1.0f ? -1.0f : s);
    out.push_back(s);
    out.push_back(s);
    out.push_back(0.0f);
    out.push_back(0.0f);
  }
  return out;
}

// The activation rule, fed once per guest frame from VdSwap with the published guest state and the level name.
// A power becomes active when, in gameplay of one level, the global actor's code moves from 5 (none) or from another
// power to a power 0..4. The codes of a level's first kSettleFrames gameplay frames, and of the kSettleFrames after a
// power is lost, are only a baseline: a level that
// starts with a power is not a pickup, and its script sets it a little after the level start writes 5 (snipe_00:
// 5 then 3 after 0.6 s, and the game plays no jingle there; E-322). Pauses, the front end and unreadable frames leave
// the baseline alone, so resuming a pause, a death reload (power -> 5) and every other frame give nothing. Out of
// gameplay a playing jingle is stopped.
enum class Event : uint8_t { kNone, kActivate, kStop };

struct Tracker {
  static constexpr int kUnknown = -1;
  static constexpr uint32_t kSettleFrames = 120;   // 2 s of 60 Hz guest frames; no can is reachable that early
  int last = kUnknown;          // last power code read in gameplay of this level, or kUnknown
  uint32_t level = 0;           // FNV of the level name of that read
  uint32_t frames = 0;          // gameplay frames of this level so far (saturating)
  bool gameplay = false;

  Event Step(const r3hd_ds::state::Guest& g, uint32_t level_hash, int* power_code = nullptr) {
    const bool was_gameplay = gameplay;
    gameplay = g.gameplay;
    if (!g.gameplay) return was_gameplay ? Event::kStop : Event::kNone;
    if (level_hash != level) {
      level = level_hash;
      last = kUnknown;
      frames = 0;
    }
    if (frames < kSettleFrames) ++frames;
    const int code = g.power_code;
    if (code < 0 || code > r3hd_ds::state::kPowerCodeNone) return Event::kNone;   // unread: keep the baseline
    const int prev = last;
    last = code;
    // Losing a power (expiry, hit, death and its same-level reload) settles again: a level script that sets a power
    // after a reload (snipe_00's pattern) must not count as a pickup either.
    if (code == r3hd_ds::state::kPowerCodeNone && prev != kUnknown && prev != code) frames = 1;
    if (prev == kUnknown || frames < kSettleFrames || code == prev || code == r3hd_ds::state::kPowerCodeNone)
      return Event::kNone;
    if (power_code) *power_code = code;
    return Event::kActivate;
  }
};

inline uint32_t LevelHash(const uint8_t* membase) {
  char level[16] = {};
  std::memcpy(level, membase + r3hd_ds::state::kLevelName, 15);
  uint32_t h = 2166136261u;
  for (int i = 0; i < 15 && level[i]; ++i) h = (h ^ static_cast<uint8_t>(level[i] | 0x20)) * 16777619u;
  return h;
}

// The controller's audio route (E-332). A USB DualSense plays its built-in speaker only after the host sends the audio
// fields of its HID output report; at power-on the route is headset stereo (path 0) and the speaker plays nothing
// (E-331: the jingle reached Windows three times and stayed silent). Human diagnostic E-332: with no route, none of
// the four endpoint channels was heard from the speaker; with output path 2 (L_L_R: headset = left, speaker = right)
// or 3 (X_X_R), speaker volume 0x50 and pre-gain 2, the front right channel played from the speaker and the front left
// did not. The jingle uses path 2, the one that leaves a headset in the jack hearing it (the left channel) as path 0
// did, and only while it plays: the worker asks for the route before the samples go out and for path 0 once they
// drained or stopped. The block is SDL's DS5EffectsState_t (the 47 bytes after the report id, SDL_SendGamepadEffect)
// with only audio enable bits set, so light bar, triggers and rumble keep what was last sent. Byte meanings SUPPORTED
// by Linux hid-playstation / community documentation; the effect VERIFIED only by the E-332 human result.
constexpr uint8_t kRoutePathSpeaker = 2;   // L_L_R
constexpr uint8_t kSpeakerVolume = 0x50;
constexpr uint8_t kSpeakerPreGain = 2;
constexpr size_t kRouteBlockBytes = 47;

// speaker: path 2 with speaker volume and pre-gain; otherwise path 0 alone (the power-on route; the speaker volume is
// left as it is, path 0 does not use it).
inline void RouteBlock(bool speaker, uint8_t block[kRouteBlockBytes]) {
  std::memset(block, 0, kRouteBlockBytes);
  block[0] = 0x80;   // enable bits 1: audio control valid
  if (speaker) {
    block[0] |= 0x20;   // speaker volume valid
    block[1] = 0x80;    // enable bits 2: audio control 2 valid
    block[5] = kSpeakerVolume;
    block[7] = static_cast<uint8_t>(kRoutePathSpeaker << 4);   // audio control: output path in bits 4..5
    block[37] = kSpeakerPreGain;                                // audio control 2: speaker pre-gain in bits 0..2
  }
}

// Worker -> input driver: the worker asks (Want), the input driver's next poll of a USB DualSense writes the block and
// acknowledges with the same value (written). Value = generation << 1 | speaker; 0 = nothing asked yet (path 0). Only
// the worker writes `wanted`.
struct RouteState {
  std::atomic<uint32_t> wanted{0}, written{0};
  uint32_t Want(bool speaker) {
    const uint32_t w = (((wanted.load() >> 1) + 1) << 1) | (speaker ? 1u : 0u);
    wanted.store(w);
    return w;
  }
};

inline RouteState& Route() {
  static RouteState state;
  return state;
}

// Device side (defined in <rex/r3hd_ds_speaker_sdl.h>): queue a request for the speaker worker; never blocks the
// caller beyond a mutex (shutdown waits at most 200 ms for the endpoint to be given back). Kinds: start (the first
// guest frame: the worker decodes the clips and reports the endpoint), activation of a power code 0..4, a can pickup
// (the game started its pickup sound), the expiry warning and the expiry (the game started those sounds), stop (pause,
// front end, focus loss), window focus, shutdown. Nothing happens unless the option is on.
enum class Request : uint8_t { kStart, kActivate, kStop, kShutdown, kFocus, kUnfocus, kPickup, kAlert, kPowerDown };
void Post(Request r, int power_code = -1);

// VdSwap: one step per guest frame while the option is on. Cheap: a 15-byte read, a hash and a few comparisons.
inline void OnSwap(const uint8_t* membase) {
  if (!membase) return;
  static Tracker tracker;
  static bool started = (Post(Request::kStart), true);
  (void)started;
  int code = -1;
  switch (tracker.Step(r3hd_ds::state::Read(), LevelHash(membase), &code)) {
    case Event::kActivate: Post(Request::kActivate, code); break;
    case Event::kStop: Post(Request::kStop); break;
    case Event::kNone: break;
  }
}

// The game's own pickup, expiry warning and expiry sounds (E-334, E-335). The XMA context calls OnXmaBuffer from its
// decode step with the input buffer it is about to read from: a buffer counts once when the context reaches it
// (another address than its last one) or starts it again (the read position went back), never again while it is being
// read. Every traced start of these static assets (pickups in knaar_60 and menu_20, three in a row; two menu_20
// Shock Rocket expiries) was the clip's whole range as one buffer at bit 32, on any of the contexts; the size test
// keeps the hash off every other buffer (the three sizes differ). Per-context state is touched only under that
// context's lock.
struct XmaWatch {
  uint32_t phys = 0, bits = 0;
};

inline bool FreshBuffer(XmaWatch& w, uint32_t phys, uint32_t read_bits) {
  const bool fresh = phys != w.phys || read_bits < w.bits;
  w.phys = phys;
  w.bits = read_bits;
  return fresh;
}

struct Mirrored {
  const Clip* clip;
  Request request;
};
inline constexpr Mirrored kMirrored[] = {
    {&kCanPickup, Request::kPickup}, {&kTimerAlert, Request::kAlert}, {&kPowerDown, Request::kPowerDown}};

// The mirrored clip a buffer is, or nullptr.
inline const Mirrored* MirroredClip(const uint8_t* data, uint32_t bytes) {
  if (!data) return nullptr;
  for (const Mirrored& m : kMirrored) {
    if (bytes == m.clip->size && Fnv1a64(data, bytes) == m.clip->fnv) return &m;
  }
  return nullptr;
}

inline constexpr uint32_t kXmaContexts = 320;   // XmaDecoder::kContextCount at the pin

inline void OnXmaBuffer(uint32_t context, uint32_t phys, const uint8_t* data, uint32_t bytes, uint32_t read_bits) {
  if (!Configured().on || context >= kXmaContexts) return;
  static XmaWatch watch[kXmaContexts];
  if (!FreshBuffer(watch[context], phys, read_bits)) return;
  if (const Mirrored* m = MirroredClip(data, bytes)) Post(m->request);
}

// Guest reads of the clip's file (trace only): the file name, case-insensitively, and whether [offset, offset + bytes)
// overlaps the clip.
inline bool IsClipFile(const char* file_name) {
  const char* want = "stream.h00";
  for (size_t i = 0;; ++i) {
    const char c = file_name[i];
    if ((c >= 'A' && c <= 'Z' ? c | 0x20 : c) != want[i]) return false;
    if (!c) return true;
  }
}

inline bool ReadOverlapsClip(uint64_t offset, uint64_t bytes) {
  return offset < uint64_t(kPowerUp.offset) + kPowerUp.size && offset + bytes > kPowerUp.offset;
}

}  // namespace r3hd_ds_speaker
