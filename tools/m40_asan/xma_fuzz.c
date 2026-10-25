// M40 (E-201): AddressSanitizer harness for the SDK's FFmpeg xmaframes decoder, driven the way XmaContext drives it:
// a codec state allocated and opened per stream with the context's rate and channel count (D-038), packet data
// pointing at a 1 + 4096 byte frame buffer (XmaContext::xma_frame_, no FFmpeg input padding), avcodec_send_packet /
// avcodec_receive_frame, 512 samples read per channel (ConvertFrame), the state freed on a reset (sometimes in the
// middle of a stream). Frames come from the game's own packets (m40_xma_frames.py, private corpus); a share of them
// is mutated. Exit 0 and one XMA_FUZZ line when no ASan report stopped the process.
// Usage: xma_fuzz CORPUS ITERATIONS SEED [MUTATE_PERCENT [control]]  (control: one byte written past the frame
// buffer, which ASan must report)
#include <libavcodec/avcodec.h>
#include <libavutil/log.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct {
  uint32_t n;
  uint8_t** f;
  uint16_t* sz;
} Stream;

static uint64_t rs;
static uint32_t rnd(void) {
  rs ^= rs << 13;
  rs ^= rs >> 7;
  rs ^= rs << 17;
  return (uint32_t)(rs >> 11);
}

static void mutate_frame(uint8_t* xma, uint32_t* size) {
  uint32_t s = *size;
  switch (rnd() % 5) {
    case 0:  // a few bit flips in the frame
      for (int b = 1 + rnd() % 8; b; b--) xma[1 + rnd() % (s > 1 ? s - 1 : 1)] ^= (uint8_t)(1 << (rnd() & 7));
      break;
    case 1:  // random body, same length
      for (uint32_t b = 1; b < s; b++) xma[b] = (uint8_t)rnd();
      break;
    case 2:  // random padding byte
      xma[0] = (uint8_t)rnd();
      break;
    case 3:  // random size and bytes (mostly refused by the size check)
      s = 3 + rnd() % 4095;
      for (uint32_t b = 0; b < s; b++) xma[b] = (uint8_t)rnd();
      break;
    default: {  // random body whose 15-bit length is consistent, so it passes the size check
      uint32_t bits = 16 + rnd() % (4095 * 8 - 16), nb = (bits + 7) / 8;
      for (uint32_t b = 1; b <= nb; b++) xma[b] = (uint8_t)rnd();
      xma[0] = (uint8_t)(((nb * 8 - bits) & 7) << 2);
      xma[1] = (uint8_t)(bits >> 7);
      xma[2] = (uint8_t)((xma[2] & 1) | ((bits & 0x7F) << 1));
      s = 1 + nb;
    }
  }
  *size = s;
}

int main(int argc, char** argv) {
  if (argc < 4) return 2;
  FILE* fp = fopen(argv[1], "rb");
  if (!fp) return 2;
  fseek(fp, 0, SEEK_END);
  long len = ftell(fp);
  fseek(fp, 0, SEEK_SET);
  uint8_t* all = malloc(len);
  if (fread(all, 1, len, fp) != (size_t)len) return 2;
  fclose(fp);
  uint32_t cap = 1024, ns = 0;
  Stream* st = malloc(sizeof(Stream) * cap);
  for (long p = 0; p + 4 <= len;) {
    uint32_t n;
    memcpy(&n, all + p, 4);
    p += 4;
    if (ns == cap) st = realloc(st, sizeof(Stream) * (cap *= 2));
    Stream* s = &st[ns++];
    s->n = n;
    s->f = malloc(sizeof(uint8_t*) * n);
    s->sz = malloc(2 * (size_t)n);
    for (uint32_t i = 0; i < n; i++) {
      memcpy(&s->sz[i], all + p, 2);
      p += 2;
      s->f[i] = all + p;
      p += s->sz[i];
    }
  }
  if (!ns) return 2;
  long iters = atol(argv[2]);
  rs = 0x9E3779B97F4A7C15ull ^ (uint64_t)atoll(argv[3]);
  int mutate = argc > 4 ? atoi(argv[4]) : 20;
  av_log_set_level(AV_LOG_QUIET);
  const AVCodec* codec = avcodec_find_decoder(AV_CODEC_ID_XMAFRAMES);
  if (!codec) return 3;
  static const int rates[4] = {24000, 32000, 44100, 48000};
  AVPacket* pkt = av_packet_alloc();  // as XmaContext::Setup: a buffer of its own, data pointed elsewhere
  pkt->buf = av_buffer_alloc(128 * 1024);
  AVFrame* frame = av_frame_alloc();
  uint8_t* xma = malloc(1 + 4096);
  if (argc > 5 && strcmp(argv[5], "control") == 0) {
    volatile uint8_t* past = xma + 1 + 4096;  // positive control: ASan must report this heap overflow
    *past = 1;
  }
  uint64_t frames = 0, decoded = 0, errors = 0, opens = 0, mutated = 0;
  double sink = 0;
  for (long it = 0; it < iters; it++) {
    Stream* s = &st[rnd() % ns];
    uint32_t start = rnd() % s->n, count = 1 + rnd() % 400;
    int ch = 1 + (rnd() & 1), rate = rates[rnd() & 3];
    AVCodecContext* ctx = NULL;
    for (uint32_t i = start; i < s->n && i < start + count; i++) {
      if (!ctx) {
        ctx = avcodec_alloc_context3(codec);
        ctx->sample_rate = rate;
        ctx->channels = ch;
        ctx->flags2 |= AV_CODEC_FLAG2_SKIP_MANUAL;
        if (avcodec_open2(ctx, codec, NULL) < 0) return 3;
        opens++;
      }
      uint32_t size = s->sz[i] > 4097 ? 4097 : s->sz[i];
      memset(xma, 0, 1 + 4096);
      memcpy(xma, s->f[i], size);
      if ((int)(rnd() % 100) < mutate) {
        mutate_frame(xma, &size);
        mutated++;
      }
      pkt->data = xma;
      pkt->size = (int)size;
      frames++;
      int ret = avcodec_send_packet(ctx, pkt);
      if (ret >= 0) ret = avcodec_receive_frame(ctx, frame);
      if (ret >= 0) {
        decoded++;
        const float* c0 = (const float*)frame->data[0];
        const float* c1 = ch == 2 ? (const float*)frame->data[1] : NULL;
        for (int j = 0; j < 512; j++) sink += c0[j] + (c1 ? c1[j] : 0.0f);
      } else {
        errors++;
      }
      if (rnd() % 97 == 0) avcodec_free_context(&ctx);  // ResetDecoderState in the middle of a stream
    }
    avcodec_free_context(&ctx);
  }
  av_frame_free(&frame);
  av_packet_free(&pkt);
  free(xma);
  printf("XMA_FUZZ iterations=%ld frames=%llu decoded=%llu errors=%llu opens=%llu mutated=%llu streams=%u "
         "signal=%d\n", iters, (unsigned long long)frames, (unsigned long long)decoded, (unsigned long long)errors,
         (unsigned long long)opens, (unsigned long long)mutated, ns, sink != 0);
  return 0;
}
