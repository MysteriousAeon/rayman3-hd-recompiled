#!/usr/bin/env python3
"""M16: frame-pacing statistics from a CapFrameX capture (JSON), without printing the raw arrays.

usage: m16_capframex.py CAPTURE.json... [--json OUT] [--bucket SECONDS]

Reads the PresentMon columns CapFrameX stores per frame and reports, per capture:
application present cadence (MsBetweenPresents), displayed cadence (MsBetweenDisplayChange), the present
mode / sync interval / tearing flags, outliers and where they cluster, the frame-to-frame pattern (lag-1
autocorrelation, alternation share) and per-bucket jitter. Captures are private; the output is statistics only.
"""
import argparse
import datetime
import json
import math
import os
import sys

PRESENT_MODES = {
    0: "Unknown", 1: "Hardware: Legacy Flip", 2: "Hardware: Legacy Copy to front buffer",
    3: "Hardware: Independent Flip", 4: "Composed: Flip", 5: "Composed: Copy with GPU GDI",
    6: "Composed: Copy with CPU GDI", 7: "Composed: Composition Atlas",
    8: "Hardware Composed: Independent Flip",
}


def pct(sorted_values, q):
    if not sorted_values:
        return float("nan")
    i = min(len(sorted_values) - 1, max(0, int(round(q * (len(sorted_values) - 1)))))
    return sorted_values[i]


def series_stats(values, nominal):
    v = [x for x in values if x is not None and x > 0]
    s = sorted(v)
    n = len(v)
    if n == 0:
        return {"n": 0}
    mean = sum(v) / n
    sd = math.sqrt(sum((x - mean) ** 2 for x in v) / n)
    core = [x for x in v if abs(x - nominal) <= nominal * 0.25]
    cmean = sum(core) / len(core) if core else float("nan")
    csd = math.sqrt(sum((x - cmean) ** 2 for x in core) / len(core)) if core else float("nan")
    d = [core[i + 1] - core[i] for i in range(len(core) - 1)]
    lag1 = float("nan")
    if len(core) > 2 and csd > 0:
        lag1 = sum((core[i] - cmean) * (core[i + 1] - cmean) for i in range(len(core) - 1)) / ((len(core) - 1) * csd * csd)
    # share of consecutive deviations with opposite sign (0.5 = independent, 1.0 = strict long/short alternation)
    alt = [1 for i in range(len(core) - 1) if (core[i] - cmean) * (core[i + 1] - cmean) < 0]
    return {
        "n": n, "mean": round(mean, 3), "sd": round(sd, 3),
        "p0.1": round(pct(s, 0.001), 3), "p1": round(pct(s, 0.01), 3), "p5": round(pct(s, 0.05), 3),
        "p50": round(pct(s, 0.5), 3), "p95": round(pct(s, 0.95), 3), "p99": round(pct(s, 0.99), 3),
        "p99.9": round(pct(s, 0.999), 3), "max": round(s[-1], 3),
        "within_0.5ms": round(sum(1 for x in v if abs(x - nominal) <= 0.5) / n, 4),
        "within_1ms": round(sum(1 for x in v if abs(x - nominal) <= 1.0) / n, 4),
        "over_20ms": sum(1 for x in v if x > 20), "over_25ms": sum(1 for x in v if x > 25),
        "over_33ms": sum(1 for x in v if x > 33.4), "over_50ms": sum(1 for x in v if x > 50),
        "over_100ms": sum(1 for x in v if x > 100),
        "core_sd": round(csd, 3), "core_lag1_autocorr": round(lag1, 3),
        "core_alternation_share": round(len(alt) / max(1, len(core) - 1), 3),
        "core_mean_abs_step": round(sum(abs(x) for x in d) / max(1, len(d)), 3),
    }


def counts(values):
    out = {}
    for x in values:
        out[str(x)] = out.get(str(x), 0) + 1
    return out


def analyse(path, bucket):
    doc = json.load(open(path, encoding="utf-8-sig"))
    info = doc.get("Info", {})
    run = doc["Runs"][0]
    cd = run["CaptureData"]
    t = cd["TimeInSeconds"]
    mbp = cd["MsBetweenPresents"]
    mbd = cd.get("MsBetweenDisplayChange") or []
    n = len(t)
    duration = t[-1] - t[0] if n else 0.0
    created = info.get("CreationDate")
    end_utc = None
    if created:
        end_utc = datetime.datetime.fromisoformat(created[:26].rstrip("Z")).replace(tzinfo=datetime.timezone.utc)
    med = sorted(mbp)[n // 2] if n else 16.667
    nominal = 1000.0 / 60 if abs(med - 16.667) < 2 else (1000.0 / 30 if abs(med - 33.333) < 3 else med)
    res = {
        "file": os.path.basename(path), "frames": n, "duration_s": round(duration, 2),
        "creation_utc": created, "average_fps": round((n - 1) / duration, 3) if duration else None,
        "nominal_ms": round(nominal, 3),
        "info": {k: info.get(k) for k in ("AppVersion", "Processor", "GPU", "GPUDriverVersion", "ApiInfo",
                                           "PresentationMode", "ResolutionInfo", "WinGameMode", "HAGS")},
        "present_mode": {PRESENT_MODES.get(int(k), k): v for k, v in counts(cd.get("PresentMode", [])).items()},
        "sync_interval": counts(cd.get("SyncInterval", [])),
        "allows_tearing": counts(cd.get("AllowsTearing", [])),
        "dropped": counts(cd.get("Dropped", [])),
        "frame_type": counts(cd.get("FrameType", [])),
        "between_presents": series_stats(mbp, nominal),
        "between_display_change": series_stats(mbd, nominal) if mbd else None,
    }
    for name in ("MsInPresentAPI", "MsUntilDisplayed", "GpuActive", "CpuActive", "AnimationError"):
        col = cd.get(name)
        if col:
            s = sorted(col)
            res[name] = {"p1": round(pct(s, 0.01), 3), "p50": round(pct(s, 0.5), 3), "p99": round(pct(s, 0.99), 3),
                         "min": round(s[0], 3), "max": round(s[-1], 3),
                         "mean_abs": round(sum(abs(x) for x in col) / len(col), 3)}
    # displayed interval relative to refresh periods of common fixed rates: a fixed-refresh display without
    # tearing quantises to multiples of the period; a variable-refresh or tearing presentation does not.
    if mbd:
        for hz in (239.97, 144.0, 120.0, 60.0):
            period = 1000.0 / hz
            near = sum(1 for x in mbd if x > 0 and abs(x / period - round(x / period)) < 0.06)
            res.setdefault("display_quantisation_share", {})[str(hz)] = round(near / max(1, len(mbd)), 4)
    # outliers and clusters
    stalls = [(t[i], mbp[i]) for i in range(n) if mbp[i] > 25.0 and nominal < 20]
    clusters = []
    for ts, ms in stalls:
        if clusters and ts - clusters[-1]["end_s"] <= 2.0:
            c = clusters[-1]
            c["end_s"] = ts
            c["count"] += 1
            c["max_ms"] = max(c["max_ms"], ms)
        else:
            clusters.append({"start_s": ts, "end_s": ts, "count": 1, "max_ms": ms})
    for c in clusters:
        if end_utc is not None:
            wall = end_utc - datetime.timedelta(seconds=duration - c["start_s"])
            c["start_local_estimate"] = wall.astimezone().strftime("%H:%M:%S")
        c["start_s"] = round(c["start_s"], 2)
        c["end_s"] = round(c["end_s"], 2)
        c["max_ms"] = round(c["max_ms"], 2)
    res["stall_clusters_over_25ms"] = clusters
    if end_utc is not None:
        res["capture_local_estimate"] = [
            (end_utc - datetime.timedelta(seconds=duration)).astimezone().strftime("%H:%M:%S"),
            end_utc.astimezone().strftime("%H:%M:%S")]
    # buckets
    rows = []
    i = 0
    while i < n:
        j = i
        b0 = t[i]
        while j < n and t[j] - b0 < bucket:
            j += 1
        seg = mbp[i:j]
        segd = mbd[i:j] if mbd else []
        if len(seg) >= 30:
            st = series_stats(seg, nominal)
            sd_ = series_stats(segd, nominal) if segd else {}
            rows.append({"t": round(b0, 1), "n": len(seg), "p50": st["p50"], "core_sd": st["core_sd"],
                         "alt": st["core_alternation_share"], "lag1": st["core_lag1_autocorr"],
                         "o25": st["over_25ms"], "disp_core_sd": sd_.get("core_sd"),
                         "disp_within_1ms": sd_.get("within_1ms")})
        i = j
    res["buckets"] = rows
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("captures", nargs="+")
    ap.add_argument("--json")
    ap.add_argument("--bucket", type=float, default=60.0)
    ap.add_argument("--buckets", action="store_true", help="print the per-bucket rows")
    a = ap.parse_args()
    out = [analyse(p, a.bucket) for p in a.captures]
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=1)
    for r in out:
        b = r.pop("buckets")
        print(json.dumps(r, indent=1))
        if a.buckets:
            for row in b:
                print("  bucket", " ".join(f"{k}={v}" for k, v in row.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
