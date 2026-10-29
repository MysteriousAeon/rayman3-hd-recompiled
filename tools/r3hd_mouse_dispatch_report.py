"""Summarize optional dispatcher/XAM observations without authorizing mouse input.

Usage: r3hd_mouse_dispatch_report.py DISPATCH.csv XAM.csv [--watch WATCH.jsonl --clock CLOCK.json]
Raw traces and actor records remain private. Output contains counts/addresses only.
"""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path

import r3hd_mouse_context_report as context

READERS = {"82297C80": "8227D02C", "82297C58": "8227D058",
           "82297CD0": "8227D084", "82297CA8": "8227D0B0"}
OPCODES = dict(zip(READERS, ("45", "46", "47", "48")))


def report(dispatch, polls, watch=None, clock=None):
    if not dispatch or not polls:
        raise ValueError("both dispatcher and XAM observations required")
    if watch is not None and (not clock or clock.get("frequency", 0) <= 0):
        raise ValueError("actor correlation requires a valid QPC/UTC calibration")
    events = sorted([(int(r["qpc"]), "dispatch", r) for r in dispatch] +
                    [(int(r["qpc"]), "poll", r) for r in polls], key=lambda e: e[0])
    counts = Counter(r["pc"] for r in dispatch)
    sources, positive, enabled = Counter(), Counter(), Counter()
    starts = posts = poll = None
    contexts = {}
    ordered = mismatched = unattributed = 0
    attributed = []
    for qpc, kind, row in events:
        if kind == "poll":
            poll = row
            continue
        pc = row["pc"]
        if pc == "82297ED0":
            starts, posts = row, None
        elif pc == "82297638":
            posts = row
        elif pc == "8227CFD0":
            if row.get("tid"):
                contexts[row["tid"]] = row
        elif pc in READERS and row["lr"] == READERS[pc]:
            owner = contexts.get(row.get("tid"))
            if (owner is None or owner["frame"] != row["frame"] or
                    owner.get("opcode") != OPCODES[pc] or owner.get("argument") != row["r3"] or
                    owner["context0"] != "00000002"):
                unattributed += 1
                continue
            # Actor identity is retained as an address, not inferred from a behavior name.
            key = f"{owner['r3']}:{owner['context4']}:{row['r3']}:{pc}"
            sources[key] += 1
            value = int(row["counter"])
            signed = value - (1 << 32) if value >= 1 << 31 else value
            positive[key] += signed > 0
            enabled[key] += row["entry_enable"] == "1"
            attributed.append((qpc, key, row))
            if (starts and poll and posts and
                    starts["frame"] == poll["frame"] == posts["frame"] == row["frame"] and
                    int(starts["qpc"]) < int(poll["qpc"]) < int(posts["qpc"]) < qpc):
                ordered += 1
            else:
                mismatched += 1
    result = {"gate_verified": False, "delivery_implemented": False,
              "dispatch_rows": len(dispatch), "polls": len(polls), "functions": dict(counts),
              "reader_sources": [{"superobject:perso:entry:reader": k, "reads": n,
                                  "positive_counter": positive[k], "entry_enabled": enabled[k]}
                                 for k, n in sources.items()],
              "attributed_reads_after_same_frame_poll_and_action_update": ordered,
              "reads_without_that_order": mismatched, "unattributed_script_reads": unattributed}
    if watch is not None:
        # Reuse established interval/counterexample rules. Add the last observed
        # generic input-enable value before each poll, with no claim it is current eligibility.
        observed, last, index = [], None, 0
        ordered_dispatch = sorted(dispatch, key=lambda r: int(r["qpc"]))
        for row in sorted(polls, key=lambda r: int(r["qpc"])):
            while index < len(ordered_dispatch) and int(ordered_dispatch[index]["qpc"]) < int(row["qpc"]):
                last = ordered_dispatch[index]
                index += 1
            if last and last["global_enable"] == "1":
                observed.append(row)
        if observed:
            matched = context.report(observed, watch, clock)
            result["global_enable_observed_before_polls"] = len(observed)
            result["photo_interiors_with_generic_enable"] = matched.get("photo_help_interiors", [])
            result["death_interiors_with_generic_enable"] = matched.get("death_interiors", [])
        else:
            result["global_enable_observed_before_polls"] = 0
        origin = next(r["utc"] for r in watch if "watch" in r)
        result["actor_interiors"] = []
        for model, name in (("ODA_Director", "PersoHelp"), ("YLT_RaymanModel", "PafMort")):
            changes = []
            for row in watch:
                if row.get("model") == model and "comport" in row:
                    if not changes or (row.get("perso"), row["comport"]) != (changes[-1].get("perso"), changes[-1]["comport"]):
                        changes.append(row)
            for a, b in zip(changes, changes[1:]):
                if name not in (a["comport"] or ""):
                    continue
                low, high = origin + a["t"] + .25, origin + b["t"] - .25
                if low >= high:
                    continue
                matched = [(key, row) for qpc, key, row in attributed if
                           low < clock["utc"] + (qpc - clock["qpc"]) / clock["frequency"] < high]
                result["actor_interiors"].append({"model": model, "behavior": a["comport"],
                    "duration_s": round(high - low, 3), "reader_sources": dict(Counter(k for k, r in matched)),
                    "enabled_reader_sources": dict(Counter(k for k, r in matched if r["entry_enable"] == "1"))})
    return result


def selftest():
    checks = []
    def check(ok):
        checks.append(bool(ok))
    base = dict(qpc="10", frame="1", pc="82297ED0", lr="0", r3="0", r4="0", r5="0",
                global_enable="1", count="238", list="1000", counter="4294967295", entry_enable="1",
                context0="00000002", context4="actor", context8="0", tid="7", opcode="45", argument="entry")
    ds = [base, base | dict(qpc="30", pc="82297638"),
          base | dict(qpc="40", pc="8227CFD0", r3="player"),
          base | dict(qpc="50", pc="82297C80", lr="8227D02C", r3="entry", counter="1")]
    ps = [dict(qpc="20", frame="1")]
    r = report(ds, ps)
    check(r["attributed_reads_after_same_frame_poll_and_action_update"] == 1)
    check(r["reader_sources"][0]["positive_counter"] == 1)
    check(not r["gate_verified"] and not r["delivery_implemented"])
    for value in ("0", "4294967295", "4294967294"):
        check(report(ds[:-1] + [ds[-1] | {"counter": value}], ps)["reader_sources"][0]["positive_counter"] == 0)
    check(report([x | {"entry_enable": "0"} for x in ds], ps)["reader_sources"][0]["entry_enabled"] == 0)
    check(report([x | {"tid": ""} for x in ds], ps)["unattributed_script_reads"] == 1)
    check(report(ds[:-1] + [ds[-1] | {"tid": "8"}], ps)["unattributed_script_reads"] == 1)
    check(report(ds[:-1] + [ds[-1] | {"frame": "2"}], ps)["unattributed_script_reads"] == 1)
    check(report([ds[0], ds[2], ds[3]], ps)["reads_without_that_order"] == 1)
    check(report(ds, [ps[0] | {"qpc": "60"}])["reads_without_that_order"] == 1)
    check(report(ds[:-1] + [ds[-1] | {"lr": "82298020"}], ps)["reader_sources"] == [])
    for field, value in (("opcode", "46"), ("argument", "other"), ("context0", "00000000")):
        altered = [x | {field: value} if x["pc"] == "8227CFD0" else x for x in ds]
        check(report(altered, ps)["unattributed_script_reads"] == 1)
    try:
        report([], ps)
        check(False)
    except ValueError:
        check(True)
    for clock in (None, {"frequency": 0}):
        try:
            report(ds, ps, [], clock)
            check(False)
        except ValueError:
            check(True)
    # Preserve the observed distinction: generic input can remain enabled while
    # the player is in death. This fixture judges the analyzer, never eligibility.
    poll = dict(zip(context.FIELDS, ("9", "0", "3", "0", "0", "0", "0", "0")))
    poll.update(qpc="500", frame="1", current="knaar_69", next="", freeze="0")
    watch = [{"watch": [], "utc": 100},
             {"model": "YLT_RaymanModel", "perso": "actor", "comport": "YAM_C_PafMortDebut", "t": 0},
             {"model": "YLT_RaymanModel", "perso": "actor", "comport": "YAM_C_Init", "t": 1}]
    clock = {"frequency": 1000, "qpc": 0, "utc": 100}
    r = report(ds, [poll], watch, clock)
    check(r["death_interiors_with_generic_enable"][0]["interior_polls"] == 1)
    check(r["death_interiors_with_generic_enable"][0]["candidate_allow_with_freeze_clear_polls"] == 1)
    check(not r["gate_verified"])
    check(report([r | {"global_enable": "0"} for r in ds], [poll], watch, clock)["global_enable_observed_before_polls"] == 0)
    print(f"MOUSE_DISPATCH_SELFTEST {'FAIL' if not all(checks) else 'PASS'} checks={len(checks)} failures={checks.count(False)}")
    return len(checks), checks.count(False)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("dispatch", type=Path, nargs="?")
    ap.add_argument("xam", type=Path, nargs="?")
    ap.add_argument("--watch", type=Path)
    ap.add_argument("--clock", type=Path)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        raise SystemExit(bool(selftest()[1]))
    if not a.dispatch or not a.xam:
        ap.error("two CSV traces required")
    ds, ps = [list(csv.DictReader(p.open(encoding="ascii"))) for p in (a.dispatch, a.xam)]
    watch = [json.loads(line) for line in a.watch.read_text().splitlines()] if a.watch else None
    clock = json.loads(a.clock.read_text()) if a.clock else None
    print(json.dumps(report(ds, ps, watch, clock), indent=2))
