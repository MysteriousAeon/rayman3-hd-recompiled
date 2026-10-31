// DualSense controller speaker, device side (D-141). Installed into the SDK as <rex/r3hd_ds_speaker_sdl.h> by
// tools/r3hd_dualsense_patch.py and included by src/audio/sdl/sdl_audio_driver.cpp only (it defines Post()).
//
// One worker thread owns everything that can take time or reach a device: reading and decoding the clips from the
// person's game data (once, with the SDK's own xmaframes decoder), finding the DualSense audio endpoint, one SDL
// logical device on that endpoint with one stream per clip bound to it (opened at the first play, kept open, paused
// while idle; SDL mixes clips that overlap), playback, stop and shutdown. Callers (VdSwap, the XMA context's report of
// a mirrored sound start, the input driver's focus / close paths) only queue a request. The worker sleeps on a
// condition variable: no polling, nothing per frame.
//
// Output rules: only a playback endpoint whose name contains "DualSense" and only when exactly one exists (two
// controllers are ambiguous: no output); never the default device, so a missing controller never reaches the desktop
// speakers (SDL keeps a lost specific device silent rather than migrating it). The front channels carry the clips,
// the haptic pair stays silent (QuadFromMono). A hidden run (m23haptics::Suppressed) decodes and logs but makes no SDL
// audio call at all. Main game audio, its device and its mix are untouched.
//
// Route (E-332): the speaker sounds only while the controller's audio route says so (RouteBlock). The worker asks for
// it before the samples go out and waits, bounded, until the input driver's next poll of the USB DualSense wrote it
// (that driver owns the SDL_Gamepad); it asks for path 0 again once every clip drained or stopped, and the input
// driver's release paths (focus loss, close, title exit) write path 0 themselves. "output=submitted" only means SDL /
// Windows took the samples; whether anything was heard is a human check.
#pragma once

#include <SDL3/SDL.h>

#include <algorithm>
#include <chrono>
#include <cmath>
#include <condition_variable>
#include <deque>
#include <filesystem>
#include <fstream>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

extern "C" {
#include "libavcodec/avcodec.h"
#include "libavutil/frame.h"
}

#include <rex/logging.h>
#include <rex/m23_haptics.h>
#include <rex/r3hd_ds_speaker.h>
#include <rex/runtime.h>
#include <rex/system/kernel_state.h>

namespace r3hd_ds_speaker {
namespace detail {

inline uint64_t NowMs() { return static_cast<uint64_t>(SDL_GetTicks()); }

// Reads a clip from the game data root and decodes it (a stereo clip is mixed to mono first); reason names the first
// failure.
inline bool LoadClip(const Clip& clip, std::vector<float>& out, const char*& reason) {
  auto* kernel = REX_KERNEL_STATE();
  if (!kernel || !kernel->emulator()) return (reason = "no_runtime"), false;
  const std::filesystem::path path = kernel->emulator()->game_data_root() / clip.path;
  std::vector<uint8_t> raw(clip.size);
  std::ifstream in(path, std::ios::binary);
  if (!in) return (reason = "no_file"), false;
  in.seekg(clip.offset);
  in.read(reinterpret_cast<char*>(raw.data()), static_cast<std::streamsize>(raw.size()));
  if (!in || in.gcount() != static_cast<std::streamsize>(raw.size())) return (reason = "short_file"), false;
  if (Fnv1a64(raw.data(), raw.size()) != clip.fnv) return (reason = "data_differs"), false;

  const AVCodec* codec = avcodec_find_decoder(AV_CODEC_ID_XMAFRAMES);
  if (!codec) return (reason = "no_decoder"), false;
  AVCodecContext* ctx = avcodec_alloc_context3(codec);
  AVPacket* packet = av_packet_alloc();
  AVFrame* frame = av_frame_alloc();
  std::vector<float> mono;
  int frames = -1;
  if (ctx && packet && frame) {
    ctx->sample_rate = static_cast<int>(clip.rate);
    ctx->channels = clip.channels;
    ctx->flags2 |= AV_CODEC_FLAG2_SKIP_MANUAL;
    if (avcodec_open2(ctx, codec, nullptr) >= 0) {
      frames = SplitXma2(raw.data(), raw.size(), [&](const uint8_t* bytes, size_t size) {
        packet->data = const_cast<uint8_t*>(bytes);
        packet->size = static_cast<int>(size);
        if (avcodec_send_packet(ctx, packet) < 0 || avcodec_receive_frame(ctx, frame) < 0) return false;
        if (frame->format != AV_SAMPLE_FMT_FLTP || frame->nb_samples != static_cast<int>(kSamplesPerFrame) ||
            frame->channels != clip.channels)
          return false;
        const float* l = reinterpret_cast<const float*>(frame->data[0]);
        const float* r = reinterpret_cast<const float*>(frame->data[clip.channels - 1]);
        for (int i = 0; i < frame->nb_samples; ++i) mono.push_back(0.5f * (l[i] + r[i]));
        return true;
      });
    }
  }
  av_frame_free(&frame);
  av_packet_free(&packet);
  avcodec_free_context(&ctx);
  if (frames != static_cast<int>(clip.frames)) return (reason = "decode_failed"), false;
  out = QuadFromMono(mono);
  return !out.empty() || ((reason = "decode_empty"), false);
}

// The one playback endpoint named DualSense, or 0 (count = how many matched).
inline SDL_AudioDeviceID FindEndpoint(std::string& name, int& count) {
  count = 0;
  SDL_AudioDeviceID found = 0;
  int n = 0;
  if (SDL_AudioDeviceID* ids = SDL_GetAudioPlaybackDevices(&n)) {
    for (int i = 0; i < n; ++i) {
      const char* device_name = SDL_GetAudioDeviceName(ids[i]);
      if (device_name && std::strstr(device_name, "DualSense")) {
        ++count;
        found = ids[i];
        name = device_name;
      }
    }
    SDL_free(ids);
  }
  return count == 1 ? found : 0;
}

class Worker {
 public:
  void Post(Request r, int code) {
    {
      std::lock_guard<std::mutex> lock(m_);
      if (finished_) return;
      if (!started_) {   // started by VdSwap's kStart; focus before that is only remembered
        if (r == Request::kFocus || r == Request::kUnfocus) focused_ = r == Request::kFocus;
        if (r != Request::kStart && r != Request::kActivate && r != Request::kPickup && r != Request::kAlert &&
            r != Request::kPowerDown)
          return;
        started_ = true;
        thread_ = std::thread([this] { Run(); });
        thread_.detach();   // never joined: a hard exit may end the process while it sleeps
      }
      queue_.push_back({r, code, std::chrono::steady_clock::now()});
    }
    cv_.notify_one();
    if (r == Request::kShutdown) {   // the close paths: give the endpoint back before the process ends
      std::unique_lock<std::mutex> lock(m_);
      cv_done_.wait_for(lock, std::chrono::milliseconds(200), [this] { return finished_; });
    }
  }

 private:
  struct Item {
    Request request;
    int code;
    std::chrono::steady_clock::time_point at;
  };

  // One clip and its stream on the opened endpoint: the activation jingle, the can pickup, the expiry warning, the
  // expiry.
  struct Voice {
    const Clip* clip;
    std::vector<float> samples;   // the stream's source: four interleaved channels (QuadFromMono)
    bool ok = false;
    SDL_AudioStream* stream = nullptr;
    uint64_t last_play_ms = 0;
    uint32_t plays = 0;
  };
  enum : size_t { kJingle, kPickup, kWarning, kExpiry, kVoices };

  // Decodes a clip and returns its log fields: peak and RMS of the front-left channel in dBFS.
  static void Load(Voice& v, const char*& reason, double& peak_db, double& rms_db) {
    reason = "ok";
    v.ok = LoadClip(*v.clip, v.samples, reason);
    double peak = 0, energy = 0;
    for (size_t i = 0; i < v.samples.size(); i += 4) {
      peak = std::max(peak, static_cast<double>(std::fabs(v.samples[i])));
      energy += static_cast<double>(v.samples[i]) * v.samples[i];
    }
    const auto db = [](double x) { return x > 0 ? 20.0 * std::log10(x) : -999.0; };
    peak_db = db(peak);
    rms_db = db(v.samples.empty() ? 0 : std::sqrt(energy / (v.samples.size() / 4)));
  }

  void Run() {
    const Config c = Configured();
    const bool suppressed = m23haptics::Suppressed();
    const char* reason = "ok";
    double peak_db = 0, rms_db = 0;
    Load(voices_[kJingle], reason, peak_db, rms_db);
    REXLOG_INFO("R3HD ds_speaker on={} volume={} policy={} clip={} reason={} samples={} rate={} peak_db={:.2f} "
                "rms_db={:.2f}", c.on ? 1 : 0, c.volume, suppressed ? "suppressed" : "enabled", kPowerUp.name,
                reason, voices_[kJingle].samples.size() / 4, kPowerUp.rate, peak_db, rms_db);
    for (size_t i = kPickup; i < kVoices; ++i) {
      Voice& v = voices_[i];
      Load(v, reason, peak_db, rms_db);
      REXLOG_INFO("R3HD ds_speaker clip={} reason={} channels={} samples={} rate={} peak_db={:.2f} rms_db={:.2f}",
                  v.clip->name, reason, v.clip->channels, v.samples.size() / 4, v.clip->rate, peak_db, rms_db);
    }
    if (!suppressed) Endpoint(true);
    std::unique_lock<std::mutex> lock(m_);
    for (;;) {
      if (queue_.empty()) {
        if (playing_) {
          cv_.wait_for(lock, std::chrono::milliseconds(100));
        } else {
          cv_.wait(lock);
        }
      }
      if (queue_.empty()) {   // a timeout while playing: pause the device once every clip has drained
        if (playing_ && NowMs() >= play_end_ms_) {
          lock.unlock();
          if (device_ && Drained()) Idle();
          lock.lock();
        }
        continue;
      }
      const Item item = queue_.front();
      queue_.pop_front();
      lock.unlock();
      const bool stop = Handle(item, suppressed);
      lock.lock();
      if (stop) {
        finished_ = true;
        cv_done_.notify_all();
        return;
      }
    }
  }

  // Returns true at shutdown.
  bool Handle(const Item& item, bool suppressed) {
    switch (item.request) {
      case Request::kStart: return false;
      case Request::kFocus: focused_ = true; return false;
      case Request::kUnfocus: focused_ = false; Stop("focus"); return false;
      case Request::kStop: Stop("pause"); return false;
      case Request::kShutdown:
        Stop("shutdown");
        Close();
        REXLOG_INFO("R3HD ds_speaker release plays={} pickup_plays={} warning_plays={} expiry_plays={} refused={} "
                    "endpoint_opens={} route_unacked={}", plays_, voices_[kPickup].plays, voices_[kWarning].plays,
                    voices_[kExpiry].plays, refused_, opens_, route_unacked_);
        return true;
      case Request::kActivate: Play(voices_[kJingle], item, suppressed); return false;
      case Request::kPickup: Play(voices_[kPickup], item, suppressed); return false;
      case Request::kAlert: Play(voices_[kWarning], item, suppressed); return false;
      case Request::kPowerDown:
        // The game's macro 40C79B28 stops the warning right before it starts the expiry sound (E-335): a power lost
        // within the warning's 1.6 s (a hit) cuts it short on the TV, so here too.
        if (voices_[kWarning].stream) SDL_ClearAudioStream(voices_[kWarning].stream);
        Play(voices_[kExpiry], item, suppressed);
        return false;
    }
    return false;
  }

  // Event text of a log line: the activation names its power, the mirrored sounds have none.
  static std::string What(const Voice& v, const Item& item) {
    if (v.clip == &kCanPickup) return "event=pickup";
    if (v.clip == &kTimerAlert) return "event=expiry_warning";
    if (v.clip == &kPowerDown) return "event=expiry";
    return std::string("event=activate power=") +
           r3hd_ds::state::PowerName(r3hd_ds::state::PowerFromCode(item.code)) + " code=" + std::to_string(item.code);
  }

  // One clip, on its own stream: e.g. the jingle and a pickup sound together, as in the game's mix; the same clip again
  // restarts it (the game never repeats one within kRepeatMs; a second report of one start is refused).
  void Play(Voice& v, const Item& item, bool suppressed) {
    const char* why = nullptr;
    const uint64_t now = NowMs();
    if (!v.ok) why = "no_clip";
    else if (suppressed) why = "suppressed";
    else if (Configured().volume == 0) why = "volume_0";
    else if (!focused_) why = "unfocused";
    else if (v.last_play_ms && now - v.last_play_ms < kRepeatMs) why = "repeat";
    else if (!Endpoint(false)) why = "no_endpoint";
    if (why) {
      ++refused_;
      REXLOG_INFO("R3HD ds_speaker {} output={}", What(v, item), why);
      return;
    }
    const char* route = RouteTo(true);
    SDL_ClearAudioStream(v.stream);
    const bool put = SDL_PutAudioStreamData(v.stream, v.samples.data(),
                                            static_cast<int>(v.samples.size() * sizeof(float))) &&
                     SDL_FlushAudioStream(v.stream) && SDL_ResumeAudioDevice(device_);
    const auto latency = std::chrono::duration_cast<std::chrono::microseconds>(std::chrono::steady_clock::now() -
                                                                                 item.at).count();
    if (!put) {
      ++refused_;
      if (Drained()) Idle();
      REXLOG_WARN("R3HD ds_speaker {} output=failed error={}", What(v, item), SDL_GetError());
      return;
    }
    ++plays_;
    ++v.plays;
    playing_ = true;
    v.last_play_ms = now;
    // The device still holds up to one buffer once the streams are empty: pause no earlier than that after the end.
    play_end_ms_ = std::max(play_end_ms_, now + (v.samples.size() / 4) * 1000 / v.clip->rate +
                                              std::max<uint64_t>(200, buffer_ms_ * 2));
    REXLOG_INFO("R3HD ds_speaker {} output=submitted route={} plays={} queue_us={}", What(v, item), route, plays_,
                latency);
  }

  static constexpr uint64_t kRepeatMs = 500;

  bool Drained() const {
    for (const Voice& v : voices_) {
      if (v.stream && SDL_GetAudioStreamQueued(v.stream) > 0) return false;
    }
    return true;
  }

  // Asks the input driver for the speaker route or for path 0 (E-332). For the speaker it waits until a poll of the
  // pad wrote the route (at most kRouteWaitMs; the title polls every frame), then lets the controller settle as the
  // diagnostic did before its tones. Returns "written", "unacked" (no USB DualSense poll wrote it in time: the samples
  // still go out), "held" (already asked: a repeat activation while the jingle plays) or "default" (path 0 asked).
  const char* RouteTo(bool speaker) {
    if (speaker == routed_) return "held";
    routed_ = speaker;
    RouteState& r = Route();
    const uint32_t w = r.Want(speaker);
    if (!speaker) return "default";
    for (int waited = 0; waited < kRouteWaitMs; waited += 5) {
      if (r.written.load() == w) {
        SDL_Delay(kRouteSettleMs);
        return "written";
      }
      SDL_Delay(5);
    }
    ++route_unacked_;
    return "unacked";
  }

  static constexpr int kRouteWaitMs = 250, kRouteSettleMs = 100;

  // Keeps device_ (one logical device on the one DualSense endpoint, a stream per clip bound to it) open; reopens
  // after a change of device (unplug / replug), closes when there is none. Logs each change of what it found.
  bool Endpoint(bool startup) {
    if (!SDL_WasInit(SDL_INIT_AUDIO)) return Report(startup, "audio_not_ready", 0, ""), false;
    std::string name;
    int count = 0;
    const SDL_AudioDeviceID id = FindEndpoint(name, count);
    if (device_ && (id == 0 || id != physical_)) Close();
    if (id == 0) return Report(startup, count ? "ambiguous" : "none", count, ""), false;
    if (!device_ && !startup) {
      // Our own audio reference while the device is open: SDL_QuitAudio closes open devices and streams, so the SDK
      // driver's shutdown can never free them under the worker.
      if (!SDL_InitSubSystem(SDL_INIT_AUDIO)) return Report(startup, "audio_not_ready", 0, ""), false;
      const SDL_AudioDeviceID logical = SDL_OpenAudioDevice(id, nullptr);
      bool bound = logical != 0 && SDL_PauseAudioDevice(logical);   // a logical device opens unpaused
      for (Voice& v : voices_) {
        const SDL_AudioSpec source{SDL_AUDIO_F32, 4, static_cast<int>(v.clip->rate)};
        v.stream = bound ? SDL_CreateAudioStream(&source, &source) : nullptr;   // binding sets the device side
        bound = v.stream && SDL_BindAudioStream(logical, v.stream) &&
                SDL_SetAudioStreamGain(v.stream, Configured().volume / 100.0f);
      }
      if (!bound) {
        REXLOG_WARN("R3HD ds_speaker endpoint=open_failed name=\"{}\" error={}", name, SDL_GetError());
        for (Voice& v : voices_) {
          if (v.stream) SDL_DestroyAudioStream(v.stream);
          v.stream = nullptr;
        }
        if (logical) SDL_CloseAudioDevice(logical);
        SDL_QuitSubSystem(SDL_INIT_AUDIO);
        return false;
      }
      device_ = logical;
      physical_ = id;
      ++opens_;
      SDL_AudioSpec device_spec{};
      int frames = 0;
      SDL_GetAudioDeviceFormat(id, &device_spec, &frames);
      buffer_ms_ = device_spec.freq > 0 ? static_cast<uint64_t>(frames) * 1000 / device_spec.freq : 0;
      REXLOG_INFO("R3HD ds_speaker endpoint=opened name=\"{}\" device_channels={} device_rate={} buffer_frames={}",
                  name, device_spec.channels, device_spec.freq, frames);
    }
    return Report(startup, "found", count, name.c_str()), true;
  }

  void Report(bool startup, const char* what, int count, const char* name) {
    if (!startup && last_report_ == what) return;
    last_report_ = what;
    REXLOG_INFO("R3HD ds_speaker endpoint={} count={} name=\"{}\"", what, count, name);
  }

  void Stop(const char* reason) {
    if (!playing_ || !device_) return;
    for (Voice& v : voices_) SDL_ClearAudioStream(v.stream);
    SDL_PauseAudioDevice(device_);
    playing_ = false;
    RouteTo(false);
    REXLOG_INFO("R3HD ds_speaker stop reason={}", reason);
  }

  void Idle() {
    SDL_PauseAudioDevice(device_);
    playing_ = false;
    RouteTo(false);
  }

  void Close() {
    RouteTo(false);
    if (!device_) return;
    for (Voice& v : voices_) {
      SDL_DestroyAudioStream(v.stream);
      v.stream = nullptr;
    }
    SDL_CloseAudioDevice(device_);
    SDL_QuitSubSystem(SDL_INIT_AUDIO);   // the reference Endpoint() took for this device
    device_ = physical_ = 0;
    playing_ = false;
  }

  std::mutex m_;
  std::condition_variable cv_, cv_done_;
  std::deque<Item> queue_;
  std::thread thread_;
  bool started_ = false, finished_ = false;
  // Worker-owned.
  Voice voices_[kVoices] = {{&kPowerUp}, {&kCanPickup}, {&kTimerAlert}, {&kPowerDown}};
  bool focused_ = true, playing_ = false, routed_ = false;
  uint32_t route_unacked_ = 0;
  SDL_AudioDeviceID device_ = 0, physical_ = 0;   // the opened logical device, the endpoint it was opened on
  uint64_t play_end_ms_ = 0, buffer_ms_ = 0;
  uint32_t plays_ = 0, refused_ = 0, opens_ = 0;
  std::string last_report_;
};

inline Worker& Get() {
  static Worker* worker = new Worker;   // never destroyed: no join or SDL call from a static destructor
  return *worker;
}

}  // namespace detail

void Post(Request r, int power_code) {
  if (!Configured().on) return;
  detail::Get().Post(r, power_code);
}

}  // namespace r3hd_ds_speaker
