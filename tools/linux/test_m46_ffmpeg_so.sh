#!/bin/sh
# LX-5 (E-375, B3): the libffmpeg.so link mechanism of tools/m46_runtime_patch.py on a toy pair of archives.
# Two static archives (an "avutil" and an "avcodec"; one member defined in both, like FFmpeg's file_open.c) are
# linked into one shared library exactly as the Linux branch does: m46_ffmpeg_so.cmake writes the EXTERN list,
# the version script keeps av* global. Checks: every av* symbol of both archives is exported, nothing else is,
# the duplicate member links once, and a program links and runs against the library. Needs cc, ar, nm, cmake.
#   sh tools/linux/test_m46_ffmpeg_so.sh [cc]
set -eu
CC=${1:-cc}
HERE=$(cd "$(dirname "$0")" && pwd)
T=$(mktemp -d)
trap 'rm -rf "$T"' EXIT
cd "$T"
cat > util.c <<'EOF'
int ff_util_internal(int x) { return x + 1; }
int av_util_add(int x) { return ff_util_internal(x); }
const int av_util_table[2] = {7, 8};
EOF
cat > open.c <<'EOF'
int avpriv_open(int x) { return x * 3; }
EOF
cat > codec.c <<'EOF'
int ff_util_internal(int x);
int av_util_add(int x);
int av_codec_decode(int x) { return av_util_add(x) * 2; }
int ff_codec_private(void) { return 5; }
EOF
cat > unused.c <<'EOF'
int av_codec_unreferenced(void) { return 11; }
EOF
cat > main.c <<'EOF'
int av_codec_decode(int); int av_codec_unreferenced(void); int avpriv_open(int); extern const int av_util_table[2];
int main(void) { return !(av_codec_decode(1) == 4 && av_codec_unreferenced() == 11 && avpriv_open(2) == 6
                         && av_util_table[1] == 8); }
EOF
for f in util open codec unused; do "$CC" -fPIC -fvisibility=default -O2 -c $f.c -o $f.o; done
cp open.o open2.o
ar rcs libavutil.a util.o open.o
ar rcs libavcodec.a codec.o unused.o open2.o
if command -v cmake >/dev/null; then
  if cmake -DNM=nm -DAVUTIL=libavutil.a -DAVCODEC=libavcodec.a -DOUT=exports.ld -P "$HERE/../m46_ffmpeg_so.cmake" \
       2>&1 | grep -q "only 5 av\* symbols"; then
    echo "ok   m46_ffmpeg_so.cmake reads the archives and refuses a toy set (< 100 symbols)"
  else
    echo "FAIL m46_ffmpeg_so.cmake"; exit 1
  fi
else
  echo "skip m46_ffmpeg_so.cmake (no cmake here; the native SDK build runs it)"
fi
# The size floor is for the real archives; write the toy list with the same rule to exercise the link.
{ echo "EXTERN("; nm --defined-only --extern-only libavutil.a libavcodec.a | sed -n 's/^[0-9a-fA-F]* [A-Z] \(av[A-Za-z0-9_]*\)$/  \1/p' | sort -u; echo ")"; } > exports.ld
printf '{\n  global: av*;\n  local: *;\n};\n' > ffmpeg.ver
echo 'typedef int m46_ffmpeg_dll_has_no_code_of_its_own;' > dummy.c
"$CC" -fPIC -c dummy.c -o dummy.o
"$CC" -shared -o libffmpeg.so dummy.o exports.ld libavcodec.a libavutil.a -Wl,--version-script=ffmpeg.ver \
  -Wl,-Bsymbolic -Wl,--no-undefined
exported=$(nm -D --defined-only libffmpeg.so | awk '{print $3}' | sort | tr '\n' ' ')
want="av_codec_decode av_codec_unreferenced av_util_add av_util_table avpriv_open "
[ "$exported" = "$want" ] && echo "ok   exports exactly the av* symbols: $exported" || { echo "FAIL exports: $exported"; exit 1; }
"$CC" main.c -L. -lffmpeg -Wl,-rpath,'$ORIGIN' -o main && ./main && echo "ok   a program links and runs against libffmpeg.so"
echo "R3HD_M46_FFMPEG_SO PASS"
