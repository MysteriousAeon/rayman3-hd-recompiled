#!/usr/bin/env python3
"""M24 follow-up: what the game state does across a pause (read-only), on a working copy of a genuine save entry.

    python tools/m24_resume_state.py run TAG [--entry swamp_60_human] [--level swamp_60] [--scale 2]
                                             [--steps config/m24/resume_state_swamp60.txt] [--seconds 230]
    python tools/m24_resume_state.py analyze TAG [--json OUT] [--detail N] [--expect title]
    python tools/m24_resume_state.py selftest

`run` is tools/m24_pause_resume.py's hidden run (event trace + M17 frame trace, hidden window, scoped input, muted,
no physical controller, no captures). Beside it, once the level is in play, the actors are discovered
(tools/m5_memory_probe.py) and the 0x40-byte matrix of every actor is added to the frame trace's watch list, so
every guest frame records the engine timer and where every actor is. Nothing is written to the guest.

`analyze` answers, for every pause of the run, the four questions of the follow-up:
  time      the engine clock before and after (how far it is put back), the measured frame time and the
            simulation step of the first frames after the exit (a long step or a catch-up would show here);
  frames    guest frames per presented frame around the exit, swap and present intervals, GPU fence waits;
  state     for the player, the camera and every other actor: the distance moved from the last scene frame
            before the menu to the first scene frame after it, in units of the actor's own per-frame movement
            around the pause ("frames of movement"; 1 = an ordinary frame), and the movement inside the menu;
  input     the pad buttons from the exit key to the first scene frames.
`--expect title` passes (M24_RESUME_CHECK) when every pause looks as the title makes it (RE_NOTES "M24"): no
step over 20 ms, the clock not ahead of where it stood at the pause, exactly one guest frame per presented frame
after the exit, and the player and the median moving actor at most MAX_FRAMES of their own movement further
(the title simulates one step under the menu's last frame, so a moving actor is two frames further, not one),
at most one step under the menu, and the camera actor standing at most MAX_CAMERA_HOLD scene frames after the exit.

Everything printed is times, counts and distances. Traces are game-derived and stay under private/.
"""
import argparse
import bisect
import json
import math
import struct
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import m12_save_entry as m12  # noqa: E402
import m17_frame_trace as m17  # noqa: E402
import m24_pause_resume as m24  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
WORK = m24.WORK
TOOLS = ROOT / "tools"
PLAYER, CAMERA = "YLT_RaymanModel", "StdCam"
MATRIX_BYTES, TRANSLATION = 0x40, 0x34      # tools/m5_live.py: SuperObject +0x20 -> matrix, translation at +0x34
MAX_ACTORS = 240                            # the frame trace takes 256 ranges
AROUND = 12                                 # scene frames on each side of a pause that give an actor's own movement
MOVING = 1e-4                               # units per frame below which an actor counts as standing
MAX_FRAMES = 2.5                            # movement across a pause, in frames of the actor's own movement
MAX_STEP_MS = 20
MAX_CAMERA_HOLD = 10                        # scene frames; the title holds its camera 5 .. 6 (RE_NOTES "M24")


def beside(level: str, settle: float):
    """The work beside a run: actor discovery, then the watch list."""
    def work(run_dir: Path, trace: Path, game: subprocess.Popen, log) -> None:
        import m19_campaign_check as m19
        from m5_live import Actor, Process
        layout = {"level": level, "actors": [], "watch_written": False}
        try:
            if not m19.wait_for_log(run_dir, f"{level}\\{level}.lvl result=00000000", game, 150):
                return
            time.sleep(settle)
            pid, base = m19.attach(run_dir)
            listing = run_dir / f"actors_{level}.json"
            subprocess.run([sys.executable, str(TOOLS / "m5_memory_probe.py"), str(pid), base, str(listing), "--regions"],
                           cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=180)
            process = Process(pid, int(base, 16))
            ranges = list(m17.TIMER_WATCH)
            for record in json.loads(listing.read_text(encoding="utf-8"))["actors"]:
                try:
                    actor = Actor(process, int(record["so"], 16))
                except (TypeError, ValueError, IndexError, OSError):
                    continue
                if not actor.alive() or not actor.matrix or len(layout["actors"]) >= MAX_ACTORS:
                    continue
                layout["actors"].append({"so": actor.so, "matrix": actor.matrix, "model": actor.model})
                ranges.append((actor.matrix, MATRIX_BYTES))
            m17.write_watch(trace, ranges)
            layout["watch_written"] = True
        finally:
            Path(str(trace) + ".layout.json").write_text(json.dumps(layout, indent=1) + "\n", encoding="utf-8")
    return work


def cmd_run(a) -> int:
    a.beside = beside(a.level, a.settle)
    a.layer_coords, a.audio, a.gpu, a.env = "separate", False, a.gpu, []
    code = m24.cmd_run(a)
    layout = WORK / f"m24_{a.tag}.r3ft.layout.json"
    written = layout.is_file() and json.loads(layout.read_text(encoding="utf-8"))["watch_written"]
    print(f"M24_RESUME_RUN m24_{a.tag} driver_exit={code} actors_watched={written}")
    return code if written else 1


# ---------------------------------------------------------------------------------------------------------------

def distance(p, q) -> float:
    return math.dist(p, q)


def median(values):
    values = sorted(values)
    return values[len(values) // 2] if values else 0.0


def pause_state(positions: list, before: int, after: int) -> dict:
    """One actor across one pause. positions[k] = translation in guest frame k (None when not recorded);
    `before` = the last scene frame ahead of the menu, `after` = the first scene frame behind it."""
    def steps(lo, hi):
        return [distance(positions[k], positions[k - 1]) for k in range(lo, hi)
                if 0 < k < len(positions) and positions[k] and positions[k - 1]]
    if not (positions[before] and positions[after]):
        return {}
    own_before, own_after = steps(before - AROUND + 1, before + 1), steps(after + 1, after + AROUND + 1)
    own = max(median(own_before), median(own_after))
    across = distance(positions[before], positions[after])
    in_menu = sum(steps(before + 1, after))  # movement between consecutive menu frames
    return {"own_before": median(own_before), "own_after": median(own_after), "across": across, "in_menu": in_menu,
            "frames": across / own if own > MOVING else (0.0 if across <= MOVING else float("inf")),
            "rise": positions[after][2] - positions[before][2]}


def analyze_run(events: Path, trace: Path, layout: dict, detail: int = 0) -> dict:
    data = events.read_bytes()
    counters = [struct.unpack_from("<IIqII", data, o) for o in range(0, len(data) - 23, 24)]
    frequency = next(((b << 32) | a for kind, _, _, a, b in counters if kind == 0), 0)
    first = min(c[2] for c in counters) / frequency
    ev = m24.read_events(events)
    pauses = m24.analyze_events(events)["pauses"]
    swaps = ev["cpswap"]
    swap_times = [t for t, _, _ in swaps]
    rows = [(host - first, m17.timer_fields(ranges), ranges) for _, host, _, ranges in m17.frames(trace)]
    times = [r[0] for r in rows]

    def swap_offset(k: int):
        """In play the command processor swaps a guest frame at the vblank after its VdSwap (its vblank wait
        starts within a millisecond of the call, RE_NOTES "M24"): the swap that shows guest frame k is the
        first one 5 ms or more after it. Returns that swap's index minus k."""
        s = bisect.bisect_left(swap_times, times[k] + 0.005)
        return s - k if s < len(swaps) and swap_times[s] - times[k] < 0.020 else None

    actors = layout.get("actors", [])
    tracks = [[struct.unpack_from(">3f", r[2][a["matrix"]], TRANSLATION)
               if len(r[2].get(a["matrix"], b"")) == MATRIX_BYTES else None for r in rows] for a in actors]
    for track in tracks:  # a matrix that is not finite is not a position
        for k, p in enumerate(track):
            if p and not all(math.isfinite(x) and abs(x) < 1e6 for x in p):
                track[k] = None
    player = next((i for i, a in enumerate(actors) if a["model"] == PLAYER), None)
    out, skipped = [], []
    for p in pauses:
        lo, hi = bisect.bisect_left(swap_times, p["entered_s"] - 0.002), bisect.bisect_left(swap_times, p["left_s"] - 0.002)  # rounded to 1 ms
        # Frames are shown in the order they are made, so one offset between guest frame and swap holds through
        # the pause when it is the same in the play on both sides of it (the menu only makes the queue longer).
        near = bisect.bisect_left(times, swap_times[lo] - 0.5)
        sides = []
        for start in (near, bisect.bisect_left(times, swap_times[hi] + 0.5)):
            seen = [swap_offset(k) for k in range(start, min(start + 30, len(rows) - 2))]
            mode = max(set(seen), key=seen.count) if seen else None
            sides.append(mode if mode is not None and seen.count(mode) >= 24 else None)
        if sides[0] is None or sides[0] != sides[1]:
            skipped.append(round(p["menu_s"], 2))
            continue
        offset = sides[0]
        shown = lambda k: k + offset  # noqa: E731
        before, after = lo - 1 - offset, hi - offset
        if not (0 < before < after < len(rows)) or not rows[before][1] or not rows[after][1]:
            continue
        timer = lambda k: rows[k][1]  # noqa: E731
        window = [k for k in range(after, min(after + 20, len(rows))) if timer(k)]
        menu = [k for k in range(before + 1, after) if timer(k)]
        per_swap = [sum(1 for k in range(after, min(after + 40, len(rows))) if shown(k) == s) for s in range(hi, min(hi + 20, len(swaps) - 1))]
        fact = {
            "menu_s": p["menu_s"], "exit_key": p["exit_key"], "verdict": p["verdict"],
            "clock_before_ms": timer(before)["total_ms"], "clock_after_ms": timer(after)["total_ms"],
            "clock_end_of_menu_ms": timer(menu[-2])["total_ms"] if len(menu) > 1 else None,
            "clock_step_across_ms": timer(after)["total_ms"] - timer(before)["total_ms"],
            "engine_frames_in_menu": timer(after)["frame"] - timer(before)["frame"] - 1,
            "measured_ms_after": [timer(k)["delta_ms"] for k in window],
            "step_ms_after": [timer(k)["useful_ms"] for k in window],
            "step_ms_in_menu_max": max((timer(k)["useful_ms"] for k in menu), default=None),
            "guest_frames_per_swap_after": per_swap,
            "swap_ms_after": [round((swap_times[s] - swap_times[s - 1]) * 1000, 1) for s in range(hi, min(hi + 20, len(swaps)))],
            "buttons": [(round((t - p["left_s"]) * 1000), m24.BUTTON_NAMES.get(a, f"{a:04X}") if a else "none")
                        for t, a, _ in ev["buttons"] if p["left_s"] - 0.6 <= t <= p["left_s"] + 0.6],
            "actors": {},
        }
        states = [(i, pause_state(track, before, after)) for i, track in enumerate(tracks)]
        states = [(i, s) for i, s in states if s]
        moving = [(i, s) for i, s in states if max(s["own_before"], s["own_after"]) > MOVING]
        fact["actors"] = {
            "recorded": len(states), "moving_around_the_pause": len(moving),
            "moved_in_menu": sum(1 for _, s in states if s["in_menu"] > MOVING),
            "moved_across_only": sum(1 for _, s in states if s["frames"] == float("inf")),
            "frames_of_movement_max": round(max((s["frames"] for _, s in moving if math.isfinite(s["frames"])), default=0.0), 2),
            "frames_of_movement_median": round(median([s["frames"] for _, s in moving if math.isfinite(s["frames"])]), 2),
            "over_limit": sorted(({"model": actors[i]["model"], "frames": round(s["frames"], 2), "across": round(s["across"], 4),
                                   "in_menu": round(s["in_menu"], 4)}
                                  for i, s in states if s["frames"] > MAX_FRAMES or s["in_menu"] > MOVING),
                                 key=lambda r: -r["across"])[:8],
        }
        camera = next((i for i, a in enumerate(actors) if a["model"] == CAMERA), None)
        if camera is not None and tracks[camera][before] and tracks[camera][after]:
            fact["camera"] = {k: round(v, 5) if math.isfinite(v) else None
                              for k, v in pause_state(tracks[camera], before, after).items()}
            # scene frames after the exit in which the camera actor still stands although it moved before the pause
            held = next((n for n, k in enumerate(range(after, min(after + 60, len(rows))))
                         if tracks[camera][k] and tracks[camera][k - 1] and distance(tracks[camera][k], tracks[camera][k - 1]) > MOVING), None)
            fact["camera_hold_frames"] = held if fact["camera"]["own_before"] > MOVING else None
        if player is not None and tracks[player][before] and tracks[player][after]:
            s = pause_state(tracks[player], before, after)
            # guest frames drawn as the menu in which the player nevertheless moved (simulated, never shown as a scene)
            fact["hidden_steps"] = sum(1 for k in range(before + 1, after) if tracks[player][k] and tracks[player][k - 1]
                                       and distance(tracks[player][k], tracks[player][k - 1]) > MOVING)
            fact["frozen_scene_frames_at_entry"] = next((n for n, k in enumerate(range(before, before - 10, -1))
                                                         if tracks[player][k] and tracks[player][k - 1]
                                                         and distance(tracks[player][k], tracks[player][k - 1]) > MOVING), None)                 if s["own_before"] > MOVING else None
            fact["player"] = {k: round(v, 5) if math.isfinite(v) else None for k, v in s.items()}
            if detail:
                fact["player_steps"] = [round(distance(tracks[player][k], tracks[player][k - 1]), 4)
                                        if tracks[player][k] and tracks[player][k - 1] else None
                                        for k in list(range(before - detail + 1, before + 1)) + list(range(after, after + detail))]
                fact["player_height"] = [round(tracks[player][k][2], 3) if tracks[player][k] else None
                                         for k in list(range(before - 2, before + 1)) + list(range(after, after + detail, 3))]
        out.append(fact)
    return {"pauses": out, "pauses_in_trace": len(pauses), "pauses_not_paired": skipped, "actors_watched": len(actors), "player_found": player is not None,
            "models": sorted({a["model"] for a in actors if a["model"]})}


def judge(result: dict) -> list:
    reasons = [] if len(result["pauses"]) >= 2 else [f"only {len(result['pauses'])} pause(s) with state"]
    for i, p in enumerate(result["pauses"], 1):
        if max(p["step_ms_after"], default=0) > MAX_STEP_MS:
            reasons.append(f"pause {i}: simulation step {max(p['step_ms_after'])} ms after the exit")
        if p["clock_step_across_ms"] > 2 * MAX_STEP_MS:
            reasons.append(f"pause {i}: engine clock {p['clock_step_across_ms']} ms ahead of the pause")
        if any(n != 1 for n in p["guest_frames_per_swap_after"]):
            reasons.append(f"pause {i}: guest frames per presented frame {p['guest_frames_per_swap_after']}")
        a = p["actors"]
        if a["frames_of_movement_median"] > MAX_FRAMES or p.get("player", {}).get("frames") is None or p["player"]["frames"] > MAX_FRAMES:
            reasons.append(f"pause {i}: movement across the pause: player {p.get('player', {}).get('frames')} frames, "
                           f"actors median {a['frames_of_movement_median']}")
        if p.get("hidden_steps", 0) > 1:
            reasons.append(f"pause {i}: {p['hidden_steps']} simulation steps under the menu")
        if (p.get("camera_hold_frames") or 0) > MAX_CAMERA_HOLD:
            reasons.append(f"pause {i}: camera stood for {p['camera_hold_frames']} frames after the exit")
    return reasons


def cmd_analyze(a) -> int:
    name = a.run if a.run.startswith("m24_") else f"m24_{a.run}"
    trace = WORK / f"{name}.r3ft"
    layout = json.loads(Path(str(trace) + ".layout.json").read_text(encoding="utf-8"))
    result = analyze_run(WORK / f"{name}.r3ev", trace, layout, a.detail)
    result["run"] = name
    if a.json:
        a.json.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    print(f"{name}: {result['actors_watched']} actors watched, player found: {result['player_found']}; pauses {result['pauses_in_trace']}, "
          f"not paired with frames {result['pauses_not_paired']}")
    for i, p in enumerate(result["pauses"], 1):
        s, act = p.get("player", {}), p["actors"]
        print(f"  pause {i}: {p['menu_s']:5.2f} s, {p['verdict']}; clock {p['clock_before_ms']} -> menu end "
              f"{p['clock_end_of_menu_ms']} -> {p['clock_after_ms']} ({p['clock_step_across_ms']:+d} ms across, "
              f"{p['engine_frames_in_menu']} engine frames in the menu); after the exit: measured {min(p['measured_ms_after'])}.."
              f"{max(p['measured_ms_after'])} ms, step {min(p['step_ms_after'])}..{max(p['step_ms_after'])} ms, guest frames per "
              f"swap {sorted(set(p['guest_frames_per_swap_after']))}, swap {min(p['swap_ms_after'])}..{max(p['swap_ms_after'])} ms")
        print(f"           player: own movement {s.get('own_before')} / {s.get('own_after')} per frame, across the pause "
              f"{s.get('across')} = {s.get('frames')} frames, in the menu {s.get('in_menu')}, height {s.get('rise')}; camera "
              f"{p.get('camera', {}).get('own_before')} / {p.get('camera', {}).get('own_after')}, across {p.get('camera', {}).get('across')} = "
              f"{p.get('camera', {}).get('frames')} frames, stands {p.get('camera_hold_frames')} scene frames after the exit; "
              f"steps under the menu {p.get('hidden_steps')}, frozen scene frames at the entry {p.get('frozen_scene_frames_at_entry')}; actors: "
              f"{act['moving_around_the_pause']} of {act['recorded']} moving, across the pause median {act['frames_of_movement_median']} "
              f"/ max {act['frames_of_movement_max']} frames, moved in the menu {act['moved_in_menu']}, moved only across "
              f"{act['moved_across_only']}; buttons {p['buttons']}")
        if a.detail:
            print(f"           player steps {p.get('player_steps')}")
            print(f"           player height {p.get('player_height')}")
    if not a.expect:
        return 0
    reasons = judge(result)
    print(f"M24_RESUME_CHECK {'FAIL' if reasons else 'PASS'} expect={a.expect} pauses={len(result['pauses'])} reasons={reasons}")
    return 1 if reasons else 0


# ---------------------------------------------------------------------------------------------------------------
# selftest: synthetic traces (no game, no private data)

def synthetic(folder: Path, name: str, jump_frames: int, long_step: bool) -> tuple:
    """Play 6 s, menu 3 s, play 4 s, twice; one actor walking 0.1 units per scene frame (and `jump_frames` more
    at each exit), one standing. Returns (events, trace, layout)."""
    frequency, tick = 10_000_000, 166_667
    records = [(0, 1, 0, frequency & 0xFFFFFFFF, frequency >> 32)]
    trace = bytearray(struct.pack("<IIQ", 0x54463352, 1, frequency))
    walker, stander, now, x, clock, frame = 0x40001000, 0x40002000, tick, 0.0, 1000, 0
    for kind, frames in (("play", 360), ("menu", 180), ("play", 240), ("menu", 180), ("play", 240)):
        saved = clock
        for i in range(frames):
            now += tick
            frame += 1
            step = 16
            if kind == "play":
                first = i == 0 and frame > 1
                x += 0.1 * (1 + (jump_frames if first else 0))
                step = 40 if first and long_step else 16
            clock += step
            block = bytearray(0x70)
            struct.pack_into(">IIII", block, 0, frame, 0, clock, 17)
            struct.pack_into(">I", block, 0x50, step)
            struct.pack_into(">I", block, 0x6C, 50000)
            ranges = [(m17.ENGINE + 0x64, bytes(block))]
            for address, value in ((walker, x), (stander, 5.0)):
                matrix = bytearray(MATRIX_BYTES)
                struct.pack_into(">3f", matrix, TRANSLATION, value, 2.0, 3.0)
                ranges.append((address, bytes(matrix)))
            trace += struct.pack("<IIIqQ", 0x4D415246, frame, len(ranges), now - tick * 9 // 10, 0)
            for address, payload in ranges:
                trace += struct.pack("<II", address, len(payload)) + payload
            records.append((1, 3, now - tick * 9 // 10, 5400, 0))
            records.append((2, 2, now, 122 if kind == "play" else 270, (7 << 16 | 1) if kind == "play" else (1 << 16)))
            records.append((3, 4, now + 100, 200, 0))
            if kind == "menu" and i == frames - 3:
                records.append((4, 1, now, 0x1000, 0))
        if kind == "menu":
            clock = saved
    events, trace_path = folder / f"{name}.r3ev", folder / f"{name}.r3ft"
    events.write_bytes(b"".join(struct.pack("<IIqII", *r) for r in records))
    trace_path.write_bytes(bytes(trace))
    return events, trace_path, {"actors": [{"so": 1, "matrix": walker, "model": PLAYER}, {"so": 2, "matrix": stander, "model": "other"}]}


def cmd_selftest(_a) -> int:
    failures = []

    def check(condition: bool, label: str) -> None:
        if not condition:
            failures.append(label)

    with tempfile.TemporaryDirectory() as folder:
        for name, jump, long_step, fails in (("continuous", 0, False, False), ("title", 1, False, False), ("jump", 6, False, True),
                                             ("step", 0, True, True)):
            result = analyze_run(*synthetic(Path(folder), name, jump, long_step))
            check(len(result["pauses"]) == 2, f"{name}: two pauses with state ({len(result['pauses'])})")
            check(bool(judge(result)) == fails, f"{name}: judged {'discontinuous' if fails else 'continuous'}")
            for p in result["pauses"]:
                check(abs(p["player"]["frames"] - (1 + jump)) < 0.05, f"{name}: player moved {1 + jump} frames across the pause")
                check(p["actors"]["moving_around_the_pause"] == 1 and p["actors"]["recorded"] == 2, f"{name}: one of two actors moving")
                check(p["engine_frames_in_menu"] == 180, f"{name}: engine frames in the menu")
                check(p["clock_step_across_ms"] == (40 if long_step else 16), f"{name}: clock across the pause")
                check(set(p["guest_frames_per_swap_after"]) == {1}, f"{name}: one guest frame per swap")
                check(p["hidden_steps"] == 0 and p["frozen_scene_frames_at_entry"] == 0, f"{name}: no step under the menu")
    for label in failures:
        print("FAIL", label)
    print(f"M24_RESUME_SELFTEST {'FAIL' if failures else 'PASS'} failures={len(failures)}")
    return 1 if failures else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="command", required=True)
    r = sub.add_parser("run")
    r.add_argument("tag")
    r.add_argument("--entry", default="swamp_60_human")
    r.add_argument("--level", default="swamp_60")
    r.add_argument("--steps", type=Path, default=ROOT / "config" / "m24" / "resume_state_swamp60.txt")
    r.add_argument("--seconds", type=int, default=230)
    r.add_argument("--scale", type=int, choices=(1, 2), default=2)
    r.add_argument("--settle", type=float, default=8.0, help="seconds after the level file opened before the actors are listed")
    r.add_argument("--gpu", action="store_true")
    an = sub.add_parser("analyze")
    an.add_argument("run")
    an.add_argument("--json", type=Path)
    an.add_argument("--detail", type=int, default=0, help="player steps of N frames on each side of every pause")
    an.add_argument("--expect", choices=("title",))
    sub.add_parser("selftest")
    a = ap.parse_args()
    return {"run": cmd_run, "analyze": cmd_analyze, "selftest": cmd_selftest}[a.command](a)


if __name__ == "__main__":
    sys.exit(main())
