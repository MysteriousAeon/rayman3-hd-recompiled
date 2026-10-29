#!/usr/bin/env python3
"""Source and run-log regression for the private Combo Meter close experiment.

    python tools/combo_close_regression.py
    python tools/combo_close_regression.py --generated
    python tools/combo_close_regression.py --pair CONTROL_RUN TIMED_RUN

The paired run check reads private logs and exact event-swap M17 snapshots. It expects a control made
with R3HD_TEST_COMBO_CLOSE=observe and a prototype run made with =timed, both
using the same hidden knaar_69 fixture and the same requested M22 captures.
"""
import argparse
import json
import re
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOK_CONFIG = ROOT / "config/rexglue/r3hd_compat.toml"
HOST_SOURCE = ROOT / "tools/m2_host/m2_trace.cpp"
PLAY_SOURCE = ROOT / "tools/play.ps1"
REGISTRY = ROOT / "config/settings/registry.json"
RUNS = ROOT / "private/work/m6_runs"
GENERATED = ROOT / "private/work/rex/generated/default"

checks = failures = 0


def check(condition: bool, label: str) -> None:
    global checks, failures
    checks += 1
    if not condition:
        failures += 1
        print(f"FAIL {label}")


def section(text: str, begin: str, end: str) -> str:
    start = text.find(begin)
    if start < 0:
        return ""
    finish = text.find(end, start + len(begin))
    return text[start:] if finish < 0 else text[start:finish]


def run_log(name: str) -> str:
    run = RUNS / name
    return "\n".join(p.read_text(encoding="utf-8-sig", errors="replace")
                     for p in sorted(run.glob("runtime*.log")))


def combo_events(name: str) -> list[dict]:
    path = RUNS / name / "frame_events.json"
    if not path.is_file():
        raise ValueError(f"{name}: missing frame_events.json; run combo_close_test.py analyze")
    events = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(events, list) or not events:
        raise ValueError(f"{name}: frame_events.json is empty or malformed")
    return events


def natural_cashout(events: list[dict], name: str) -> tuple[dict, dict, tuple[int, float, int]]:
    """Return (positive-bonus state, cash-out state, (score, bonus, paid score))."""
    for before, paid in zip(events, events[1:]):
        bonus = float(before["bonus"])
        if bonus > 0 and float(paid["bonus"]) == 0 and int(paid["score"]) > int(before["score"]):
            score, paid_score = int(before["score"]), int(paid["score"])
            if abs((paid_score - score) - bonus) > 0.001:
                continue
            return before, paid, (score, bonus, paid_score)
    raise ValueError(f"{name}: no natural nonzero bonus cash-out in frame events")


def check_pair(control_name: str, timed_name: str, control_events: list[dict], timed_events: list[dict]) -> None:
    try:
        cbefore, cpaid, ctuple = natural_cashout(control_events, control_name)
        tbefore, tpaid, ttuple = natural_cashout(timed_events, timed_name)
        check(ctuple == ttuple,
              f"pair: nonzero cash-out tuple matches (control={ctuple}, timed={ttuple})")
        check(cpaid["bonus"] == 0 and tpaid["bonus"] == 0,
              "pair: unpaid bonus clears at cash-out")

        def expiry_timing(before: dict, paid: dict, name: str) -> float:
            lifetime = int(paid["engine"]) - int(paid["start_ms"])
            expected = int(paid["expiry_ms"])
            check(abs(lifetime - expected) <= 34,
                  f"{name}: natural expiry at configured lifetime ({lifetime} vs {expected} ms)")
            return float(lifetime)

        control_lifetime = expiry_timing(cbefore, cpaid, control_name)
        timed_lifetime = expiry_timing(tbefore, tpaid, timed_name)
        check(int(cpaid["expiry_ms"]) == int(tpaid["expiry_ms"]) and
              abs(control_lifetime - timed_lifetime) <= 34,
              "pair: combo lifetime matches within one sampled-frame tolerance")
        print(f"COMBO_CLOSE_CHECKPOINT control_engine={cpaid['engine']} timed_engine={tpaid['engine']} "
              f"lifetime_control_ms={control_lifetime:g} lifetime_timed_ms={timed_lifetime:g}")

        check(int(tpaid["hud_state"]) == 3 and tpaid["visible"] == [1, 1] and
              abs(float(tpaid["duration"]) - 6.0) < 0.001,
              f"{timed_name}: cash-out frame records timed close state, visibility and duration")
        # Evidence correction to this new test's erroneous expectation: E-303's
        # unchanged run combo_cashout_k69_d swap658 already records [1,0], as
        # does E-304 control swap688. This pair is [main score, Combo], so the
        # main score must remain visible. Retain the initial failed log and all
        # numeric timing limits; require the exact established baseline value.
        check(int(cpaid["hud_state"]) == 0 and cpaid["visible"] == [1, 0],
              f"{control_name}: control cash-out frame records immediate close")

        def reentry(events: list[dict], paid: dict, name: str) -> tuple[int, dict]:
            paid_index = events.index(paid)
            for index in range(paid_index + 1, len(events)):
                event = events[index]
                if int(event["score"]) > int(paid["score"]) and int(event["pending"]) == 1:
                    check(int(event["hud_state"]) == 2 and event["visible"] == [1, 1],
                          f"{name}: new combo is open and visible on re-entry")
                    check(event["digits"] == [0, 0, 0, 0, 0],
                          f"{name}: re-entry clears all stored combo digits")
                    check(event["handles"] == paid["handles"] and all(event["handles"]),
                          f"{name}: re-entry keeps the pre-expiry HUD handles")
                    for prior in events[paid_index + 1:index]:
                        check(float(prior["bonus"]) == 0 and int(prior["score"]) <= int(paid["score"]),
                              f"{name}: no second positive score jump or old bonus payment before re-entry")
                    return index, event
            raise ValueError(f"{name}: no later score event with pending flag and HUD re-entry")

        ci, creentry = reentry(control_events, cpaid, control_name)
        ti, treentry = reentry(timed_events, tpaid, timed_name)
        check(cbefore["handles"] == cpaid["handles"] and tbefore["handles"] == tpaid["handles"],
              "pair: HUD handles persist from before expiration through cash-out")
        check(cbefore["handles"] == tbefore["handles"] == creentry["handles"] == treentry["handles"],
              "pair: control and timed run use the same persistent HUD handles")
        elapsed = int(treentry["engine"]) - int(tpaid["engine"])
        check(0 < elapsed < 6000,
              f"{timed_name}: re-entry interrupts the timed close before six seconds ({elapsed} ms)")
        print(f"COMBO_CLOSE_REENTRY control_engine={creentry['engine']} timed_engine={treentry['engine']} "
              f"timed_close_elapsed_ms={elapsed}")

        def snapshot(name: str, event: dict) -> dict:
            # Engine time is constant during a guest frame. A live poll with
            # the same tick can precede its score/open command. Require the
            # exact event swap, with no nearest-time fallback or tolerance.
            import m17_frame_trace as ft
            trace = ROOT / 'private/work' / (name + '.trace')
            for swap, _, _, ranges in ft.frames(trace):
                if swap == event['swap']:
                    return dict(objects=list(struct.unpack('>56I', ranges[0x828A3E28])),
                                hud=list(struct.unpack('>80I', ranges[0x8288D528])))
            raise ValueError(f"{name}: no exact event-swap object snapshot")

        cwatch, twatch = snapshot(control_name, creentry), snapshot(timed_name, treentry)
        cobject, tobject = cwatch["objects"][28:51], twatch["objects"][28:51]
        check(len(cobject) == len(tobject) == 23 and cobject[0] == tobject[0] == 0x8200FE2C and
              cobject[6] == tobject[6] == 0x40CB14F4 and cobject[22] == tobject[22] == 1,
              "pair: re-entry retains the original Combo object class, material and selector")
        # +4 and +40 are time-dependent words. Require every other sampled
        # object word, including position and presentation fields, byte-exact.
        check(all(cobject[i] == tobject[i] for i in range(23) if i not in (1, 10)),
              "pair: re-entry object fields equal control except the two time words")
        check(cwatch["hud"][5] == twatch["hud"][5],
              "pair: the title's vertical interpolant is restored to the control's open position")
        # Target update order, verified in both opt-in runs: reset/open sets
        # state2 and restores position in swap797 / 802; the cached elapsed word
        # is cleared by virtual 8219F2C0's state2 arm in swap798 / 803. Require
        # that exact next-swap reset, alongside the immediate state2/position
        # assertions above. The initial same-swap-zero expectation was false;
        # its failed logs are retained. This is no longer an active close.
        check(float(creentry["next_elapsed"]) == float(treentry["next_elapsed"]) == 0,
              "pair: inactive closing elapsed word is zero on exactly the next swap")
    except (KeyError, TypeError, ValueError, IndexError) as exc:
        check(False, f"pair: incomplete or malformed gameplay evidence: {exc}")


def main() -> int:
    global checks, failures
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generated", action="store_true",
                        help="also check the generated hook call when codegen output exists")
    parser.add_argument("--pair", nargs=2, metavar=("CONTROL", "TIMED"),
                        help="check observe-control and timed-prototype private run logs")
    args = parser.parse_args()

    config = HOOK_CONFIG.read_text(encoding="utf-8")
    source = HOST_SOURCE.read_text(encoding="utf-8")
    play = PLAY_SOURCE.read_text(encoding="utf-8")
    registry = REGISTRY.read_text(encoding="utf-8")

    hooks = re.findall(r"(?ms)^\[\[midasm_hook\]\]\s*\n(?:(?!^\[\[).)*?^address\s*=\s*0x8219E9D4\s*\n"
                       r"(?:(?!^\[\[).)*?^name\s*=\s*\"ComboTimedCloseTest\"\s*\n"
                       r"(?:(?!^\[\[).)*?^registers\s*=\s*\[\"r31\",\s*\"r27\",\s*\"f13\",\s*\"f30\"\]",
                       config)
    check(len(hooks) == 1, "one E9D4 hook with object/command/duration/scalar registers")

    hook = section(source, "void ComboTimedCloseTest(", "\n}\n")
    check(bool(hook), "ComboTimedCloseTest implementation exists")
    if hook:
        for needle, label in (
            ('std::getenv("R3HD_NONINTRUSIVE")', "hidden-only gate"),
            ('std::getenv("R3HD_TEST_COMBO_CLOSE")', "explicit private option"),
            ('std::strcmp(v, "timed")', "timed opt-in"),
            ('std::strcmp(v, "observe")', "observe-only control mode"),
            ('"knaar_69\\0"', "fixture-only level guard"),
            ('selector == 1', "Combo selector guard"),
            ('action == 0x40000000', "close action guard"),
            ('old_duration == -1.0', "original immediate-close guard"),
            ('scalar.f64 == 0.0', "zero score delta guard"),
            ('M18Base()[0x40CDD6FE] == 1', "normal expiry pending guard"),
            ('duration.f64 = 6.0', "existing six-second transition operand"),
            ('"ComboTest command', "private command/state diagnostic"),
        ):
            check(needle in hook, f"hook: {label}")
        check("M18Store(" not in hook and "std::memcpy(" not in hook,
              "hook does not write guest memory through helper stores or copies")
        mutations = re.findall(r"\b(object|command|duration|scalar)\.(f64|u64|u32)\s*=(?!=)", hook)
        check(mutations == [("duration", "f64")],
              "duration operand is the only PPC register mutation in the hook")

    test_only = section(play, "$testOnly =", "\n$saved = @{}")
    check("R3HD_TEST_COMBO_CLOSE" in test_only and
          "foreach ($name in $testOnly)" in section(play, "$saved = @{}", "$env:R3HD_PLAY ="),
          "visible Play launcher clears the private test option")
    spec = json.loads(registry)["settings"]["combo_close"]
    check(spec["vanilla"] == "original" and spec["hdplus"] == "delayed"
          and spec.get("ui") != "hidden" and spec["launcher"] == "ComboClose",
          "visible production Combo option uses the existing preset resolver")

    if args.generated:
        if GENERATED.is_dir():
            generated = "\n".join(p.read_text(encoding="utf-8", errors="replace")
                                    for p in GENERATED.glob("r3hd_recomp.*.cpp"))
            check("ComboTimedCloseTest" in generated, "generated dispatch calls the configured hook")
        else:
            check(False, "generated directory is absent")

    if args.pair:
        control_name, timed_name = args.pair
        control, timed = run_log(control_name), run_log(timed_name)
        check(bool(control) and "ComboTest command" in control,
              f"{control_name}: observe-control logged scoped HUD commands")
        check(bool(timed) and "ComboTest command" in timed,
              f"{timed_name}: timed run logged scoped HUD commands")
        check("selected=true" not in control,
              f"{control_name}: observe control did not select the transition")
        check("selected=true" in timed,
              f"{timed_name}: opt-in selected the six-second close")
        try:
            control_events, timed_events = combo_events(control_name), combo_events(timed_name)
            check_pair(control_name, timed_name, control_events, timed_events)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            check(False, f"pair: missing or unreadable analyzed gameplay evidence: {exc}")

    print(f"COMBO_CLOSE_REGRESSION {'PASS' if not failures else 'FAIL'} checks={checks} failures={failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
