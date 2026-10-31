#!/usr/bin/env python3
"""High-refresh study (E-321): per-frame timing and motion of a tools/m24_resume_state.py run (statistics only).

    python tools/hr_motion.py TAG [--json OUT]

Reads private/work/m24/m24_TAG.r3ft (+ .layout.json) of a run with config/high_refresh/swamp60_motion.txt. The
window is 6 s before to 12 s after the player's first walk: guest frames per second, engine frames per swap, step /
measured ms, simulated / wall, trace interval; camera yaw around the player while the right stick is held; run speed
per simulated second; jumps (apex, frames, step-summed ms). Works at any vblank rate. Traces are game-derived and
stay under private/; this prints numbers only.
"""
import json
import math
import struct
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import m17_frame_trace as m17  # noqa: E402
import m24_pause_resume as m24  # noqa: E402

TRANSLATION = 0x34


def load(tag):
    trace = m24.WORK / f"m24_{tag}.r3ft"
    layout = json.loads(Path(str(trace) + ".layout.json").read_text(encoding="utf-8"))
    actors = layout["actors"]
    pi = next(i for i, a in enumerate(actors) if a["model"] == "YLT_RaymanModel")
    ci = next(i for i, a in enumerate(actors) if a["model"] == "StdCam")
    rows = []
    for swap, host, guest, ranges in m17.frames(trace):
        t = m17.timer_fields(ranges)
        if not t:
            continue
        def pos(i):
            b = ranges.get(actors[i]["matrix"], b"")
            return struct.unpack_from(">3f", b, TRANSLATION) if len(b) == 0x40 else None
        rows.append(dict(swap=swap, host=host, frame=t["frame"], step=t["useful_ms"], meas=t["delta_ms"],
                         total=t["total_ms"], flen=t["frame_length"], p=pos(pi), c=pos(ci)))
    return rows, len(actors)


def pct(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(len(xs) * q))] if xs else None


def analyze(rows):
    out = {}
    # steady stretch: last 40 s of the trace (the level is in play and the steps run there)
    pr = [r for r in rows if r["p"]]
    t_walk = None
    for a, b in zip(pr, pr[60:]):
        if math.hypot(b["p"][0] - a["p"][0], b["p"][1] - a["p"][1]) > 0.05:
            t_walk = b["host"]
            break
    out["t_walk_rel_s"] = round(t_walk - rows[0]["host"], 2)
    s = [r for r in rows if t_walk - 6.0 <= r["host"] <= t_walk + 12.0]
    pairs = list(zip(s, s[1:]))
    one = [(a, b) for a, b in pairs if b["frame"] == a["frame"] + 1 and b["swap"] == a["swap"] + 1]
    wall = (s[-1]["host"] - s[0]["host"]) * 1000.0
    sim = sum(b["step"] for a, b in one)
    iv = [(b["host"] - a["host"]) * 1000.0 for a, b in one]
    out["timing"] = dict(frames=len(s), wall_s=round(wall / 1000, 2), guest_frames_per_s=round(len(s) / (wall / 1000), 2),
                         one_engine_frame_per_swap=f"{len(one)}/{len(pairs)}",
                         step_ms=dict(Counter(b["step"] for a, b in one).most_common(5)),
                         measured_ms=dict(Counter(b["meas"] for a, b in one).most_common(5)),
                         nominal_frame_s=s[-1]["flen"], simulated_per_wall=round(sim / wall, 4),
                         trace_interval_ms=dict(p5=round(pct(iv, .05), 2), p50=round(pct(iv, .5), 2),
                                                p95=round(pct(iv, .95), 2), p99=round(pct(iv, .99), 2)))
    # motion, per engine frame, in the steady stretch
    dist = lambda p, q: math.dist(p[:3], q[:3])  # noqa: E731
    h = lambda p, q: math.hypot(p[0] - q[0], p[1] - q[1])  # noqa: E731
    # camera yaw around the player (horizontal plane = x, y; z up in this engine)
    def yaw(r):
        return math.degrees(math.atan2(r["c"][1] - r["p"][1], r["c"][0] - r["p"][0]))
    cam = []
    for a, b in one:
        if a["c"] and b["c"] and a["p"] and b["p"] and t_walk - 6.0 <= a["host"] <= t_walk - 2.0:
            d = (yaw(b) - yaw(a) + 180) % 360 - 180
            cam.append((a, b, d, dist(a["c"], b["c"])))
    turning = [x for x in cam if abs(x[2]) > 0.05]
    if turning:
        rate = [abs(x[2]) / (x[1]["step"] / 1000.0) for x in turning]
        out["camera"] = dict(turning_frames=len(turning), deg_per_frame_p50=round(pct([abs(x[2]) for x in turning], .5), 3),
                             deg_per_frame_p95=round(pct([abs(x[2]) for x in turning], .95), 3),
                             deg_per_sim_s_p50=round(pct(rate, .5), 1), deg_per_sim_s_p90=round(pct(rate, .9), 1),
                             camera_static_while_turning_share=round(sum(1 for x in turning if x[3] == 0) / len(turning), 4),
                             total_deg=round(sum(abs(x[2]) for x in turning), 1))
    # walking: horizontal player speed, frames moving with feet on the base height
    walk = [(a, b, h(a["p"], b["p"])) for a, b in one if a["p"] and b["p"] and t_walk - 0.5 <= a["host"] <= t_walk + 3.0]
    moving = [w for w in walk if w[2] > 1e-3 and abs(w[1]["p"][2] - w[0]["p"][2]) < 1e-3]
    if moving:
        sp_sim = [w[2] / (w[1]["step"] / 1000.0) for w in moving]
        sp_wall = [w[2] / (w[1]["host"] - w[0]["host"]) for w in moving]
        out["walk"] = dict(frames=len(moving), units_per_sim_s_p50=round(pct(sp_sim, .5), 3),
                           units_per_sim_s_max=round(max(sp_sim), 3), units_per_frame_p50=round(pct([w[2] for w in moving], .5), 4),
                           units_per_wall_s_p50=round(pct(sp_wall, .5), 3), total_distance=round(sum(w[2] for w in moving), 3))
    # jumps: rise of z from a resting height
    zs = [(r, r["p"][2]) for r in s if r["p"]]
    jumps, k = [], 1
    while k < len(zs):
        r0, z0 = zs[k - 1]
        if zs[k][1] - z0 > 0.02:
            base, start, apex, ai = z0, k - 1, z0, k
            j = k
            while j < len(zs) and zs[j][1] > base + 0.005:
                if zs[j][1] > apex:
                    apex, ai = zs[j][1], j
                j += 1
            if j < len(zs) and j - start > 5:
                a, top, e = zs[start][0], zs[ai][0], zs[j][0]
                jumps.append(dict(apex_height=round(apex - base, 3), air_frames=j - start, rise_frames=ai - start,
                                  air_sim_ms=sum(z[0]["step"] for z in zs[start + 1:j + 1]), rise_sim_ms=sum(z[0]["step"] for z in zs[start + 1:ai + 1]),
                                  air_wall_ms=round((e["host"] - a["host"]) * 1000, 1)))
            k = j + 1
        else:
            k += 1
    out["jumps"] = jumps
    return out


if __name__ == "__main__":
    rows, n = load(sys.argv[1])
    res = analyze(rows)
    res["actors_watched"] = n
    print(json.dumps(res, indent=1))
    if len(sys.argv) > 3 and sys.argv[2] == "--json":
        Path(sys.argv[3]).write_text(json.dumps(res, indent=1))
