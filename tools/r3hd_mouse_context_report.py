#!/usr/bin/env python3
"""Summarize read-only XAM context traces; never authorizes a mouse feature.

Usage: r3hd_mouse_context_report.py TRACE.csv [--watch WATCH.jsonl --clock CLOCK.json]
Actor correlation uses a QPC/UTC calibration and discards 250 ms at each boundary.
Traces and actor watches are private game-derived inputs. Output is statistics only.
"""
import argparse
import csv
import itertools
import json
from pathlib import Path


FIELDS = ("engine", "menu_mode", "menu_state", "page", "loaded", "pause_word", "cinematic", "pad_selector")


def candidate(row):
    """Unvalidated hypothesis, deliberately reported rather than used for input."""
    return (row["engine"] == "9" and row["pause_word"] == "0" and row.get("cinematic") == "0"
            and row.get("pad_selector") == "0" and bool(row["current"])
            and row["current"].lower() != "menumap")


def report(rows, watch=None, clock=None):
    if not rows:
        raise ValueError("empty trace")
    missing = [k for k in (*FIELDS, "freeze") if k not in rows[0]]
    rows = [r | {k: "" for k in missing} for r in rows]
    for row in rows:
        for name in (*FIELDS, "qpc", "frame"):
            if name not in missing:
                int(row[name])
    intervals = []
    for key, group in itertools.groupby(rows, lambda r: tuple(r[k] for k in (*FIELDS, "current", "next"))):
        span = list(group)
        intervals.append(dict(zip((*FIELDS, "current", "next"), key)) | {
            "first_frame": int(span[0]["frame"]), "last_frame": int(span[-1]["frame"]), "polls": len(span),
        })
    result = {
        "polls": len(rows), "context_intervals": intervals,
        "unobserved_fields": missing,
        "same_frame_adjacent_polls": sum(a["frame"] == b["frame"] for a, b in zip(rows, rows[1:])),
        "frame_resets": sum(int(b["frame"]) < int(a["frame"]) for a, b in zip(rows, rows[1:])),
        "candidate_allow_polls": sum(candidate(r) for r in rows),
        "gate_verified": False,
        "candidate_allow_with_freeze_clear_polls": sum(candidate(r) and r.get("freeze") == "0" for r in rows),
    }
    if watch is not None:
        if not clock or clock["frequency"] <= 0:
            raise ValueError("actor correlation requires QPC/UTC clock calibration")
        # Only observed transitions bound intervals. Do not infer an open interval's end.
        start = next(r["utc"] for r in watch if "watch" in r)
        def changes(model):
            # Actor records also repeat the same behavior when health/bits change.
            # Those records must not split one semantic interval into short pieces.
            out = []
            for row in watch:
                if row.get("model") == model and "comport" in row:
                    if not out or (row.get("perso"), row["comport"]) != (out[-1].get("perso"), out[-1]["comport"]):
                        out.append(row)
            return out
        actor = changes("ODA_Director")
        observations = []
        for a, b in zip(actor, actor[1:]):
            if "PersoHelp" not in (a.get("comport") or ""):
                continue
            low, high = start + a["t"] + .25, start + b["t"] - .25
            if high <= low:
                continue
            matched = [r for r in rows if low < clock["utc"] + (int(r["qpc"]) - clock["qpc"]) / clock["frequency"] < high]
            observations.append({"duration_s": round(high - low, 3), "interior_polls": len(matched),
                                 "candidate_allow_polls": sum(candidate(r) for r in matched),
                                 "candidate_allow_with_freeze_clear_polls": sum(candidate(r) and r.get("freeze") == "0" for r in matched)})
        result["photo_help_interiors"] = observations
        result["candidate_rejected_by_photo"] = any(o["candidate_allow_polls"] for o in observations)
        player = changes("YLT_RaymanModel")
        death = []
        for a, b in zip(player, player[1:]):
            if "PafMort" not in (a.get("comport") or ""):
                continue
            low, high = start + a["t"] + .25, start + b["t"] - .25
            if high <= low:
                continue
            matched = [r for r in rows if low < clock["utc"] + (int(r["qpc"]) - clock["qpc"]) / clock["frequency"] < high]
            death.append({"duration_s": round(high - low, 3), "interior_polls": len(matched),
                          "candidate_allow_with_freeze_clear_polls": sum(candidate(r) and r.get("freeze") == "0" for r in matched)})
        result["death_interiors"] = death
        result["freeze_candidate_rejected_by_death"] = any(o["candidate_allow_with_freeze_clear_polls"] for o in death)
    return result


def selftest():
    # Metadata fixtures from E-293's observed contexts, not game bytes or scripts.
    base = dict(zip(FIELDS, ("9", "0", "3", "0", "0", "0", "0", "0")))
    base.update(qpc="1000", frame="10", current="wood_10", next="", freeze="0")
    checks = []
    def check(label, ok):
        checks.append(bool(ok))
        print(f"{'PASS' if ok else 'FAIL'} context analysis: {label}")
    check("scene matches the unvalidated candidate", candidate(base))
    for key, value in (("engine", "5"), ("pause_word", "1"), ("cinematic", "1"),
                       ("cinematic", "4294967295"), ("pad_selector", "1"), ("current", "menumap")):
        check(f"candidate excludes {key}={value}", not candidate(base | {key: value}))
    sample = [base, base | {"qpc": "1100"}, base | {"frame": "1", "qpc": "1200"}]
    r = report(sample)
    check("counts repeated frame polls and frame reset independently", r["same_frame_adjacent_polls"] == 1 and r["frame_resets"] == 1)
    check("never calls an observed candidate a verified gate", not r["gate_verified"])
    watch = [{"watch": [], "utc": 100}, {"model": "ODA_Director", "comport": "ODA_rul_Director_PersoHelp", "t": 0},
             {"model": "ODA_Director", "comport": "ODA_rul_Director_MainBehaviour", "t": 2}]
    clock = {"qpc": 1000, "utc": 100, "frequency": 1000}
    sample = [base | {"qpc": str(q), "freeze": "1"} for q in (1100, 1500, 2900)]
    r = report(sample, watch, clock)
    check("photo counterexample uses interior polls only", r["photo_help_interiors"][0]["interior_polls"] == 1 and r["candidate_rejected_by_photo"])
    check("missing freeze evidence never counts as clear", report([base | {"freeze": ""}])["candidate_allow_with_freeze_clear_polls"] == 0)
    check("freeze byte would reject the observed frozen photo interior", r["photo_help_interiors"][0]["candidate_allow_with_freeze_clear_polls"] == 0)
    try:
        report([])
        empty_refused = False
    except ValueError:
        empty_refused = True
    check("empty evidence refused", empty_refused)
    check("open actor interval is not silently extended", not report(sample, watch[:2], clock)["photo_help_interiors"])
    death_watch = [{"watch": [], "utc": 100},
                   {"model": "YLT_RaymanModel", "comport": "YAM_C_PafMortDebut", "t": 0},
                   {"model": "YLT_RaymanModel", "comport": "YAM_C_PafMortDebut", "t": .3},
                   {"model": "YLT_RaymanModel", "comport": "YAM_C_Init", "t": 2}]
    r = report([base | {"qpc": "1500"}], death_watch, clock)
    check("unfrozen death observation rejects stronger candidate", r["freeze_candidate_rejected_by_death"])
    check("same behavior snapshots do not split death interval", len(r["death_interiors"]) == 1 and r["death_interiors"][0]["duration_s"] == 1.5)
    legacy = {k: v for k, v in base.items() if k not in ("cinematic", "pad_selector", "freeze")}
    r = report([legacy])
    check("older trace schema is explicit and cannot authorize candidate", len(r["unobserved_fields"]) == 3 and r["candidate_allow_polls"] == 0)
    return len(checks), sum(not ok for ok in checks)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("trace", type=Path, nargs="?")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--watch", type=Path)
    ap.add_argument("--clock", type=Path)
    args = ap.parse_args()
    if args.selftest:
        n, bad = selftest()
        print(f"MOUSE_CONTEXT_SELFTEST {'FAIL' if bad else 'PASS'} checks={n} failures={bad}")
        return int(bool(bad))
    if args.trace is None:
        ap.error("TRACE or --selftest required")
    rows = list(csv.DictReader(args.trace.open(encoding="ascii")))
    watch = [json.loads(line) for line in args.watch.read_text().splitlines()] if args.watch else None
    clock = json.loads(args.clock.read_text()) if args.clock else None
    print(json.dumps(report(rows, watch, clock), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
