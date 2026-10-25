"""Replay after M11 at the same pin: two host memory costs found by the M12 address-space breakdown (D-038).

1. Host thread stacks are reserved, not committed.

`Thread::Create` passed the requested stack size to `CreateThread` without `STACK_SIZE_PARAM_IS_A_RESERVATION`.
Windows then treats the size as the initial commit: every guest thread (16 MiB requested) and every runtime
thread (4 MiB default) committed its whole stack at creation. Measured in `intro_10`: 13 x 16 MiB + 24 x 4 MiB
= 304 MB of private commit with 4.6 MB resident. With the flag the same address range is reserved and the stack
grows through its guard page as on any Windows thread; the usable depth is unchanged.
`R3HD_STACK_COMMIT=1` restores the original call for comparison.

2. XMA decoder contexts allocate their codec state on first use.

`XmaDecoder::Setup` prepares 320 contexts and each `XmaContext::Setup` called `avcodec_alloc_context3`, which
allocates and zeroes the decoder's private state (about 460 KB each, 147 MB in total, all resident because it is
zero-filled). That state was never used for decoding: it only carried "sample rate 0, channels 0", and the first
`PrepareDecoder` of a stream frees it and allocates a new one because the format differs. A null context now
stands for the same "no format yet" state, and `ResetDecoderState` (context cleared or released by the title)
frees the codec state instead of zeroing its format, so memory follows the voices in use. The number and order of
codec opens per stream is unchanged. `R3HD_XMA_EAGER=1` restores the original allocation for comparison.

Both changes are host-only: no guest memory, no guest-visible value and no generated code changes.
"""
from m8_runtime_patch import patch_once

if __name__ == '__main__':
    patch_once('src/core/threading_win.cpp', [
        ('  HANDLE handle = CreateThread(NULL, params.stack_size, ThreadStartRoutine, start_data,\n'
         '                               params.create_suspended ? CREATE_SUSPENDED : 0, NULL);',
         '  // M12 (D-038): stack_size is the reserve. Without this flag Windows commits all of it at once.\n'
         '  static const DWORD m12_stack_flag =\n'
         '      std::getenv("R3HD_STACK_COMMIT") ? 0 : STACK_SIZE_PARAM_IS_A_RESERVATION;\n'
         '  HANDLE handle = CreateThread(NULL, params.stack_size, ThreadStartRoutine, start_data,\n'
         '                               (params.create_suspended ? CREATE_SUSPENDED : 0) | m12_stack_flag,\n'
         '                               NULL);'),
        ('#include <spdlog/spdlog.h>\n', '#include <spdlog/spdlog.h>\n#include <cstdlib>\n'),
    ])
    patch_once('src/audio/xma_context.cpp', [
        ('#include <algorithm>\n#include <cstring>\n', '#include <algorithm>\n#include <cstdlib>\n#include <cstring>\n'),
        ('  av_context_ = avcodec_alloc_context3(av_codec_);\n'
         '  if (!av_context_) {\n'
         '    REXAPU_ERROR("XmaContext {}: Couldn\'t allocate context", id);\n'
         '    return 1;\n'
         '  }\n'
         '\n'
         '  // Initialize these to 0. They\'ll actually be set later.\n'
         '  av_context_->channels = 0;\n'
         '  av_context_->sample_rate = 0;\n',
         '  // M12 (D-038): the codec state is allocated by PrepareDecoder on first use; a null context means\n'
         '  // "no format yet", which is all the context allocated here ever expressed.\n'
         '  static const bool m12_eager = std::getenv("R3HD_XMA_EAGER") != nullptr;\n'
         '  m12_lazy_ = !m12_eager;\n'
         '  if (m12_eager) {\n'
         '    av_context_ = avcodec_alloc_context3(av_codec_);\n'
         '    if (!av_context_) {\n'
         '      REXAPU_ERROR("XmaContext {}: Couldn\'t allocate context", id);\n'
         '      return 1;\n'
         '    }\n'
         '\n'
         '    // Initialize these to 0. They\'ll actually be set later.\n'
         '    av_context_->channels = 0;\n'
         '    av_context_->sample_rate = 0;\n'
         '  }\n'),
        ('  if (av_context_) {\n'
         '    av_context_->sample_rate = 0;\n'
         '    av_context_->channels = 0;\n'
         '  }\n',
         '  if (av_context_ && m12_lazy_) {\n'
         '    // M12 (D-038): the next PrepareDecoder allocates and opens a new codec state either way.\n'
         '    avcodec_free_context(&av_context_);\n'
         '  } else if (av_context_) {\n'
         '    av_context_->sample_rate = 0;\n'
         '    av_context_->channels = 0;\n'
         '  }\n'),
        ('  if (av_context_->sample_rate != sample_rate ||\n'
         '      av_context_->channels != static_cast<int>(channels)) {\n'
         '    REXAPU_NOISY_DEBUG("XmaContext {}: Codec reinit: rate {} -> {}, channels {} -> {}", id(),\n'
         '                       av_context_->sample_rate, sample_rate, av_context_->channels, channels);\n'
         '    avcodec_free_context(&av_context_);\n'
         '    av_context_ = avcodec_alloc_context3(av_codec_);\n',
         '  if (!av_context_ || av_context_->sample_rate != sample_rate ||\n'
         '      av_context_->channels != static_cast<int>(channels)) {\n'
         '    REXAPU_NOISY_DEBUG("XmaContext {}: Codec reinit: rate {} -> {}, channels {} -> {}", id(),\n'
         '                       av_context_ ? av_context_->sample_rate : 0, sample_rate,\n'
         '                       av_context_ ? av_context_->channels : 0, channels);\n'
         '    avcodec_free_context(&av_context_);\n'
         '    av_context_ = avcodec_alloc_context3(av_codec_);\n'
         '    if (!av_context_) {\n'
         '      REXAPU_ERROR("XmaContext {}: Couldn\'t allocate context", id());\n'
         '      return -1;\n'
         '    }\n'),
        ('    carry_valid_ = false;\n'
         '  }\n'
         '  PreparePacket(packet_info.current_frame_size_, padding_start);\n',
         '    carry_valid_ = false;\n'
         '  }\n'
         '  if (!av_context_) {\n'
         '    return;  // M12 (D-038): codec state could not be allocated (logged by PrepareDecoder)\n'
         '  }\n'
         '  PreparePacket(packet_info.current_frame_size_, padding_start);\n'),
    ])
    patch_once('include/rex/audio/xma/context.h', [
        ('  AVCodecContext* av_context_ = nullptr;\n',
         '  AVCodecContext* av_context_ = nullptr;\n'
         '  bool m12_lazy_ = true;  // M12 (D-038): codec state allocated on first use\n'),
    ])
