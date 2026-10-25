"""M22: summarise m22_audio.txt (written by tools/m22_audio_probe.h with R3HD_M22_AUDIO=1; statistics only).

Reports, for the mixed output: callback pacing, frames with nothing queued after the first mixed frame (host
underruns), runs of silent frames between audible ones (gaps), level drops inside an audible stretch (dips) and
the largest sample steps (clicks). For XMA contexts: lifetimes, long-lived streams, starvation and decode
refusals. A gap in the mix is not by itself a defect (a level can be quiet); read it with the stream table.

usage: m22_audio_report.py RUN_DIR [--client N] [--from S] [--to S] [--json OUT]
"""
import argparse
import json
import statistics
from pathlib import Path

FRAME_S = 256 / 48000


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("run", type=Path)
    ap.add_argument("--from", dest="t0", type=float, default=0.0)
    ap.add_argument("--to", dest="t1", type=float, default=1e9)
    ap.add_argument("--client", type=int, default=0, help="render client tag (0 = first opened)")
    ap.add_argument("--json", type=Path)
    a = ap.parse_args()
    out, xma = [], []
    for line in (a.run / "m22_audio.txt").read_text().splitlines():
        p = line.split()
        if len(p) < 3:
            continue
        t = int(p[1]) / 1e6
        if p[0] == "out" and len(p) == 8 and int(p[7]) == a.client:
            out.append((t, int(p[2]), float(p[3]), float(p[4]), int(p[5]), float(p[6])))
        elif p[0] == "xma":
            xma.append((t, int(p[2]), p[3], [int(x) for x in p[4:]]))
    first_mixed = next((i for i, o in enumerate(out) if o[1] and o[3] > 0), len(out))
    sel = [o for o in out[first_mixed:] if a.t0 <= o[0] <= a.t1]
    res = dict(callback_frames=len(out), analysed_frames=len(sel), analysed_seconds=round(len(sel) * FRAME_S, 1))
    if sel:
        span = sel[-1][0] - sel[0][0]
        res["delivered_over_wall"] = round(len(sel) * FRAME_S / span, 4) if span else None
        res["not_queued_frames"] = sum(1 for o in sel if not o[1])
        # Underrun episodes: consecutive not-queued frames.
        episodes, run = [], 0
        for o in sel:
            if not o[1]:
                run += 1
            elif run:
                episodes.append((round(o[0], 2), run))
                run = 0
        res["underrun_episodes"] = len(episodes)
        res["underrun_longest_ms"] = round(max((n for _, n in episodes), default=0) * FRAME_S * 1000, 1)
        res["underrun_first"] = episodes[:12]
        # Silent gaps: queued frames with rms == 0 between audible frames.
        gaps, run, start = [], 0, 0.0
        for o in sel:
            if o[1] and o[3] == 0.0:
                if not run:
                    start = o[0]
                run += 1
            elif run:
                gaps.append((round(start, 2), round(run * FRAME_S * 1000, 1)))
                run = 0
        res["silent_gaps"] = len(gaps)
        res["silent_gaps_over_20ms"] = [g for g in gaps if g[1] >= 20][:40]
        # Dips: rms below a tenth of the median of the surrounding second, for 10..500 ms, in an audible stretch.
        rms = [o[3] for o in sel]
        window = int(0.5 / FRAME_S)
        dips, i = [], window
        while i < len(rms) - window:
            around = statistics.median(rms[i - window:i] + rms[i + 1:i + 1 + window])
            if around > 0.003 and rms[i] < around * 0.1:
                j = i
                while j < len(rms) - window and rms[j] < around * 0.1:
                    j += 1
                if 2 <= j - i <= int(0.5 / FRAME_S):
                    dips.append((round(sel[i][0], 2), round((j - i) * FRAME_S * 1000, 1), round(around, 4)))
                i = j + 1
            else:
                i += 1
        res["dips"] = dips[:40]
        res["dip_count"] = len(dips)
        steps = sorted(((o[5], round(o[0], 2), round(o[2], 3)) for o in sel), reverse=True)[:8]
        res["largest_steps"] = [dict(step=round(s, 3), t=t, peak=p) for s, t, p in steps]
        res["peak"] = max(o[2] for o in sel)
    ends = [(t, c, v) for t, c, k, v in xma if k == "end"]
    starts = [(t, c) for t, c, k, v in xma if k == "start"]
    res["xma"] = dict(
        starts=len(starts), ends=len(ends), contexts=len({c for _, c in starts}),
        starve=[dict(t=round(t, 2), ctx=c, ms=v[0]) for t, c, k, v in xma if k == "starve"][:60],
        starve_count=sum(1 for x in xma if x[2] == "starve"),
        errors=sum(1 for x in xma if x[2] == "error"),
        error_first=[dict(t=round(t, 2), ctx=c) for t, c, k, v in xma if k == "error"][:20],
        long_streams=[dict(end_t=round(t, 2), ctx=c, frames=v[0], ms=v[1]) for t, c, v in ends if v[1] >= 5000][:60])
    open_ctx, last_end = {}, {}
    for t, c in starts:
        open_ctx[c] = t
    for t, c, v in ends:
        last_end[c] = t
    res["xma"]["open_at_end"] = [dict(ctx=c, start_t=round(t, 2)) for c, t in sorted(open_ctx.items())
                                 if last_end.get(c, -1) < t]
    text = json.dumps(res, indent=1)
    print(text)
    if a.json:
        a.json.write_text(text + "\n")


if __name__ == "__main__":
    main()
