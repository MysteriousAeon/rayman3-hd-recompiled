"""Build-time regression for D-038: host stacks are reserved, XMA codec state is allocated on first use.

Static check of the patched SDK sources (no game process). It guards two memory properties that the next SDK
patch or pin change could silently undo. The measured comparison is
    python tools/m12_measure.py RUN            (default)   against
    R3HD_STACK_COMMIT=1 R3HD_XMA_EAGER=1 python tools/m12_measure.py RUN2
and tools/m12_mem_compare.py RUN RUN2.
"""
import re
import sys

from m11_shutdown_regression import SDK, body


def main():
    checks = failures = 0

    def check(ok, what):
        nonlocal checks, failures
        checks += 1
        if not ok:
            failures += 1
            print('FAIL', what)

    thread = (SDK / 'src/core/threading_win.cpp').read_text()
    create = body(thread, 'std::unique_ptr<Thread> Thread::Create(CreationParameters params,')
    check(create.count('CreateThread(') == 1, 'one CreateThread call')
    call = create[create.index('CreateThread('):]
    call = call[:call.index(';')]
    check('params.stack_size' in call, 'the requested stack size is still passed')
    check('m12_stack_flag' in call and 'CREATE_SUSPENDED' in call, 'creation flags carry the reservation flag')
    check(re.search(r'm12_stack_flag\s*=\s*std::getenv\("R3HD_STACK_COMMIT"\)\s*\?\s*0\s*:\s*'
                    r'STACK_SIZE_PARAM_IS_A_RESERVATION;', create) is not None,
          'reservation is the default; R3HD_STACK_COMMIT restores the commit')

    xma = (SDK / 'src/audio/xma_context.cpp').read_text()
    setup = body(xma, 'int XmaContext::Setup(')
    eager = setup.find('if (m12_eager) {')
    alloc = setup.find('avcodec_alloc_context3(')
    check(setup.count('avcodec_alloc_context3(') == 1 and 0 <= eager < alloc, 'Setup allocates codec state only when eager')
    check('std::getenv("R3HD_XMA_EAGER") != nullptr' in setup and 'm12_lazy_ = !m12_eager;' in setup,
          'lazy is the default; R3HD_XMA_EAGER restores the allocation')
    check('av_frame_alloc()' in setup and 'av_packet_alloc()' in setup, 'frame and packet are still prepared')
    prepare = body(xma, 'int XmaContext::PrepareDecoder(')
    check('if (!av_context_ || av_context_->sample_rate != sample_rate ||' in prepare,
          'PrepareDecoder treats a null context as "format differs"')
    check(prepare.index('avcodec_alloc_context3(') < prepare.index('avcodec_open2('), 'allocate, then open')
    check(prepare.count('avcodec_open2(') == 1 and 'AV_CODEC_FLAG2_SKIP_MANUAL' in prepare, 'open path unchanged')
    opened = prepare[prepare.index('avcodec_alloc_context3('):prepare.index('avcodec_open2(')]
    check('if (!av_context_) {' in opened and 'return -1;' in opened, 'PrepareDecoder reports an allocation failure before touching the state')
    reset = body(xma, 'void XmaContext::ResetDecoderState()')
    check('if (av_context_ && m12_lazy_) {' in reset and 'avcodec_free_context(&av_context_);' in reset,
          'a reset frees the codec state in lazy mode')
    check('av_context_->sample_rate = 0;' in reset and 'carry_valid_ = false;' in reset, 'eager reset and stream state reset kept')
    decode = body(xma, 'void XmaContext::Decode(')
    check(0 <= decode.find('PrepareDecoder(') < decode.find('DecodePacket(av_context_'),
          'every decode prepares the codec before using it')
    guard = decode.find('if (!av_context_) {', decode.find('PrepareDecoder('))
    check(0 <= guard < decode.find('PreparePacket(') < decode.find('DecodePacket(av_context_'),
          'a failed allocation returns from Decode before the codec is used')
    header = (SDK / 'include/rex/audio/xma/context.h').read_text()
    check('AVCodecContext* av_context_ = nullptr;' in header and 'bool m12_lazy_ = true;' in header, 'header defaults')

    print(f'm12 memory regression: {checks} checks, {failures} failures: {"FAIL" if failures else "PASS"}')
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
