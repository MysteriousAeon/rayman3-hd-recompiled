#!/usr/bin/env python3
"""Match a muted runtime capture to the target movie tracks (developer evidence only).

Needs NumPy and a local FFmpeg. Records the executable/version identity. Never downloads anything.
The M6 capture mixes callback clients in file order: align all 1,875 blocks to M22
peak/RMS/zero-count records first, then select a client. Refuse ambiguous alignment.
No acoustic-language recognition: track-language meaning also needs target-code evidence.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

import numpy as np

SAMPLE_RATE = 4000
FFMPEG_COMMIT = "e7a6bba51a"
FFMPEG_SHA256 = "5a6db9bfcf60f60427ee7c30198140d20d6b2d646ceeb3e4a15c34a53655f6fa"


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def match(x, y):
    best = {"correlation": -1}
    # Bounded rate fit, applied identically to every candidate. It accommodates
    # the title's resampling clock, without treating pitch/timing fidelity as tested.
    for scale in np.linspace(.998, 1.002, 81):
        xx = np.interp(np.arange(int(len(x) * scale)) / scale, np.arange(len(x)), x)
        xx -= xx.mean()
        n = len(xx)
        if n > len(y) or np.sum(xx * xx) < 1e-10:
            raise ValueError("silent or oversized capture")
        nf = 1 << (len(y) + n - 1).bit_length()
        cross = np.fft.irfft(np.fft.rfft(y, nf) * np.fft.rfft(xx[::-1], nf), nf)[n - 1:len(y)]
        sy, ss = np.r_[0, np.cumsum(y)], np.r_[0, np.cumsum(y * y)]
        energy = np.maximum(0, ss[n:] - ss[:-n] - (sy[n:] - sy[:-n]) ** 2 / n)
        den = np.sqrt(np.maximum(1e-30, energy * np.sum(xx * xx)))
        corr = np.where(den > 1e-5, cross / den, 0)
        k = int(np.argmax(corr))
        if float(corr[k]) > best["correlation"]:
            best = {"correlation": float(corr[k]), "rate_fit": float(scale), "offset_seconds": k / SAMPLE_RATE}
    return best


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("run", type=Path)
    ap.add_argument("movie", type=Path)
    ap.add_argument("--after", type=int, required=True)
    ap.add_argument("--client", required=True)
    ap.add_argument("--expected-track", type=int, required=True, help="1-based track in this movie")
    ap.add_argument("--ffmpeg", default="ffmpeg")
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    ff = Path(shutil.which(a.ffmpeg) or a.ffmpeg).resolve()
    version = subprocess.check_output([str(ff), "-version"], text=True).splitlines()[0]
    if FFMPEG_COMMIT not in version or sha(ff) != FFMPEG_SHA256:
        raise ValueError("FFmpeg differs from the Issue #2 evidence pin")
    cap = a.run / "audio.f32"
    frames = np.frombuffer(cap.read_bytes(), dtype="<f4").reshape(-1, 512)
    trace = a.run / "m22_audio.txt"
    rows = [line.split() for line in trace.read_text().splitlines() if line.startswith("out ")]
    fingerprints = [(f"{np.abs(b).max():.5f}", f"{np.sqrt(np.mean(b.astype(float) ** 2)):.5f}",
                     str(np.count_nonzero(b == 0))) for b in frames]

    def same(i, j):
        return tuple(rows[i][3:6]) == fingerprints[j]

    anchors = [i for i, r in enumerate(rows) if abs(int(r[1]) / 1e6 - a.after) < .1
               and i + len(frames) <= len(rows) and all(same(i + j, j) for j in range(min(20, len(frames))))]
    anchors = [i for i in anchors if all(same(i + j, j) for j in range(len(frames)))]
    if len(anchors) != 1:
        raise ValueError(f"need one complete callback alignment; got {len(anchors)}")
    start = anchors[0]
    selected = np.array([b for j, b in enumerate(frames) if rows[start + j][-1] == a.client], dtype="<f4")
    if not len(selected):
        raise ValueError("client has no captured frames")

    def pcm(args, data=None):
        r = subprocess.run([str(ff), "-v", "error", *args, "-f", "f32le", "-ac", "1", "-ar", str(SAMPLE_RATE), "pipe:1"],
                           input=data, capture_output=True, check=True)
        return np.frombuffer(r.stdout, dtype="<f4").astype("float64")

    x = pcm(["-f", "f32le", "-ar", "48000", "-ac", "2", "-i", "pipe:0"], selected.tobytes())
    with a.movie.open("rb") as f:
        header = f.read(1024)
    import struct
    n = struct.unpack_from("<I", header, 40)[0]
    if not 1 <= n <= 5:
        raise ValueError("expected the bounded target movie inventory")
    results = []
    for i in range(n):
        results.append({"track": i + 1, **match(x, pcm(["-i", str(a.movie), "-map", f"0:a:{i}"]))})
    ranked = sorted(results, key=lambda r: r["correlation"], reverse=True)
    ok = (ranked[0]["track"] == a.expected_track and ranked[0]["correlation"] >= .90
          and (len(ranked) == 1 or ranked[0]["correlation"] - ranked[1]["correlation"] >= .03))
    result = {"result": "PASS" if ok else "INCOMPLETE", "aligned_blocks": len(frames),
              "selected_blocks": len(selected), "client": a.client, "expected_track": a.expected_track,
              "capture_sha256": sha(cap), "trace_sha256": sha(trace), "movie_sha256": sha(a.movie),
              "comparison_sample_rate": SAMPLE_RATE,
              "ffmpeg_sha256": sha(ff), "ffmpeg_version": version, "numpy_version": np.__version__, "tracks": results}
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_bytes((json.dumps(result, indent=2) + "\n").encode())
    print(f"ISSUE2_MOVIE_PCM {result['result']} track={ranked[0]['track']} correlation={ranked[0]['correlation']:.6f}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
