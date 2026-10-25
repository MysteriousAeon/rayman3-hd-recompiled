"""Closed-loop path pilot for a hidden run: plan on decoded collision, follow with normal input.

Reads Rayman and the camera from the live process (QUERY_INFORMATION|VM_READ only), plans a
walk/jump/glide/drop route on the offline collision decode (m7_route_plan.py) and follows it by
appending controller events to the run's scoped XAM schedule: analog left stick (scancodes
300/301) and A (44). Nothing is written to the guest and no desktop input is produced. When a
move fails (missed jump, fall, stall) the failed move is excluded and the route is replanned
from the observed position. Reaching the goal position proves traversal only, not any game
interaction.

Usage: python tools/m7_path_pilot.py RUN_DIR SNAPSHOT_DIR --goal X Y Z [--seconds 500]
       [--level intro_15] [--output path_pilot.jsonl] [--platforms extra.json]
       [--goal-radius 2.5] [--no-glide] [--stop-comport NAME]
"""
import argparse
import json
import math
import pickle
import re
import sys
import time
from pathlib import Path

import m7_collision_map as cm
import m7_route_plan as rp
from m5_live import Actor, Process

A_BUTTON, X_BUTTON, AXIS_X, AXIS_Y = 44, 15, 300, 301
GROUND = ("YAM_C_Attente", "YAM_C_Course")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run", type=Path)
    parser.add_argument("snapshot")
    parser.add_argument("--goal", nargs=3, type=float)
    parser.add_argument("--follow", default="", help="follow the live actor with this model name instead of a fixed goal")
    parser.add_argument("--follow-distance", type=float, default=5.0)
    parser.add_argument("--attack-comport", default="", help="while the followed actor's behaviour contains this text, close in and tap X")
    parser.add_argument("--stop-dsg", default="", help="N=V: stop successfully when Rayman's one-byte designer variable N reads V")
    parser.add_argument("--goal-radius", type=float, default=2.5)
    parser.add_argument("--seconds", type=float, default=500)
    parser.add_argument("--level", default="intro_15")
    parser.add_argument("--output", default="path_pilot.jsonl")
    parser.add_argument("--platforms")
    parser.add_argument("--no-glide", action="store_true")
    parser.add_argument("--stop-comport", default="", help="stop successfully when Rayman enters a behaviour containing this text")
    args = parser.parse_args()

    if (args.goal is None) == (not args.follow):
        parser.error("give exactly one of --goal and --follow")
    run = args.run.resolve()
    pid = int(json.loads((run / "process.json").read_text(encoding="utf-8-sig"))["pid"])
    base = None
    for path in sorted(run.glob("runtime*.log")):
        with path.open(errors="replace") as stream:
            for line in stream:
                match = re.search(r"virtual base 0x0*([0-9A-Fa-f]+),", line)
                if match:
                    base = int(match.group(1), 16)
                    break
        if base is not None:
            break
    if base is None:
        raise SystemExit("guest virtual base not found in runtime logs")
    schedule_path = run / "schedule.txt"
    log = (run / args.output).open("a", encoding="utf-8", buffering=1)

    def emit(**data) -> None:
        log.write(json.dumps({"t": round(time.time(), 3), **data}, separators=(",", ":")) + "\n")

    sent = {AXIS_X: 0, AXIS_Y: 0, A_BUTTON: 0, X_BUTTON: 0}

    def send(values: dict) -> None:
        lines = []
        for code, value in values.items():
            if code in (A_BUTTON, X_BUTTON):
                changed = sent[code] != value
            else:
                changed = abs(sent[code] - value) >= 1500 or (value == 0 and sent[code] != 0)
            if changed:
                lines.append(f"0 {code} {value}\n")
                sent[code] = value
                if code in (A_BUTTON, X_BUTTON):
                    emit(event="button", scancode=code, down=bool(value))
        if lines:
            with schedule_path.open("a", encoding="ascii", newline="") as schedule:
                schedule.write("".join(lines))

    def neutral() -> None:
        send({AXIS_X: 0, AXIS_Y: 0, A_BUTTON: 0, X_BUTTON: 0})

    result, error = "error", None
    stats = {"replans": 0, "jumps": 0, "glides": 0, "failed_moves": 0}
    start_time = time.monotonic()
    try:
        platforms = json.load(open(args.platforms)) if args.platforms else []
        levels = rp.build(cm.load(args.snapshot), -1e9, platforms)
        process = Process(pid, base)
        actors = []
        for record in json.loads((run / f"actors_{args.level}.json").read_text(encoding="utf-8"))["actors"]:
            try:
                actors.append(Actor(process, int(record["so"], 16)))
            except (TypeError, ValueError, IndexError, OSError):
                continue
        rayman = next(actor for actor in actors if actor.model == "YLT_RaymanModel")
        camera = next(actor for actor in actors if actor.model == "StdCam")
        followed = next((actor for actor in actors if actor.model == args.follow), None) if args.follow else None
        if args.follow and followed is None:
            raise RuntimeError(f"no live actor with model {args.follow}")
        goal = list(args.goal) if args.goal else list(followed.position())
        goal_radius = args.goal_radius if args.goal else args.follow_distance
        goal_node = rp.nearest(levels, *goal)
        stop_dsg = tuple(int(part) for part in args.stop_dsg.split("=")) if args.stop_dsg else None
        followed_comport, attack_since, hits = None, 0.0, 0
        # Spring platforms keep Rayman bouncing (never grounded); route around them when possible.
        springs = set()
        for actor in actors:
            if actor.model == "NIK_mSpoWobblerSimple" and actor.alive():
                sx, sy, sz = actor.position()
                for i in range(math.floor((sx - 2.2) / rp.CELL), math.floor((sx + 2.2) / rp.CELL) + 1):
                    for j in range(math.floor((sy - 2.2) / rp.CELL), math.floor((sy + 2.2) / rp.CELL) + 1):
                        if math.hypot((i + 0.5) * rp.CELL - sx, (j + 0.5) * rp.CELL - sy) <= 2.2:
                            for kk, lz in enumerate(levels.get((i, j), [])):
                                if abs(lz - sz) <= 3.0:
                                    springs.add((i, j, kk))
        blocked_edges, blocked_nodes = set(), set()
        edge_failures = {}
        blocked_landings, landing_failures = set(), {}
        plan_time = 0.0
        # Jump/glide candidates are expensive to enumerate; keep them between runs.
        cache_path = Path(args.snapshot) / "jump_cache.pkl"
        cache_key = (rp.MODEL, rp.CELL, rp.JUMP_UP, rp.JUMP_RANGE, rp.GLIDE_RANGE, rp.STAND_NZ, bool(platforms))
        plan_cache = {}
        if cache_path.is_file():
            try:
                stored = pickle.loads(cache_path.read_bytes())
                if stored.get("key") == cache_key:
                    plan_cache = stored["cache"]
            except (OSError, pickle.PickleError, EOFError, AttributeError):
                plan_cache = {}
        cache_saved = len(plan_cache)
        emit(event="start", pid=pid, goal=goal, follow=args.follow or None, goal_node=list(goal_node), seconds=args.seconds,
             input="XAM schedule analog 300/301 + A 44", rayman=f"{rayman.so:08X}")

        def grounded() -> bool:
            comport = rayman.comport() or ""
            return comport.startswith(GROUND)

        def replan(position, reason):
            stats["replans"] += 1
            try:
                start = rp.nearest(levels, *position)
            except SystemExit:
                emit(event="replan_failed", reason=reason, position=[round(v, 3) for v in position], cause="no surface near position")
                return None
            path = None
            for avoid in (springs - {start, goal_node}, set()):
                path, _ = rp.plan(levels, start, goal_node, allow_glide=not args.no_glide,
                                  blocked_edges=blocked_edges, blocked_nodes=blocked_nodes | avoid, cache=plan_cache,
                                  blocked_landings=blocked_landings | avoid)
                if path is not None:
                    break
            nonlocal cache_saved
            if len(plan_cache) > cache_saved:
                try:
                    cache_path.write_bytes(pickle.dumps({"key": cache_key, "cache": plan_cache}))
                    cache_saved = len(plan_cache)
                except OSError:
                    pass
            if path is None:
                emit(event="replan_failed", reason=reason, position=[round(v, 3) for v in position], cause="goal unreachable")
                return None
            route = rp.to_route(levels, path, 3.0)
            emit(event="plan", reason=reason, position=[round(v, 3) for v in position], waypoints=len(route),
                 moves={kind: sum(1 for item in route if item["move"] == kind) for kind in ("jump", "glide", "drop")},
                 specials=[[item["label"], item["x"], item["y"], item["z"]] for item in route if item["move"] != "walk"])
            return route

        def steer(position, target, scale=1.0) -> None:
            cam = camera.position()
            fx, fy = position[0] - cam[0], position[1] - cam[1]
            length = math.hypot(fx, fy)
            dx, dy = target["x"] - position[0], target["y"] - position[1]
            distance = math.hypot(dx, dy)
            if length < 1e-4 or distance < 1e-4:
                return
            fx, fy, dx, dy = fx / length, fy / length, dx / distance, dy / distance
            forward, right = dx * fx + dy * fy, dx * fy - dy * fx
            send({AXIS_X: int(round(right * 32767 * scale)), AXIS_Y: int(round(forward * 32767 * scale))})

        neutral()
        route = None
        index = 0
        deadline = start_time + args.seconds
        last_sample = 0.0
        phase, phase_since, attempts = "walk", time.monotonic(), 0
        best, best_time = None, time.monotonic()
        previous_z, previous_t, apex_seen = None, None, False
        recent = []
        hang_since = 0.0
        while time.monotonic() < deadline:
            now = time.monotonic()
            if not process.running() or not rayman.alive():
                result = "actor_gone"
                emit(event="actor_gone", running=process.running())
                break
            position = rayman.position()
            if position is None or not all(math.isfinite(v) for v in position):
                neutral()
                time.sleep(0.1)
                continue
            comport = rayman.comport() or ""
            if "Accroche" in comport:
                # Hanging from a ledge (observed once hands are back): A climbs up; do not press
                # again while the climb animation (AccrocheRemonte) runs.
                if now - hang_since > 0.9 and comport.endswith("AccrocheAuBord"):
                    hang_since = now
                    send({A_BUTTON: 1})
                    emit(event="ledge_climb", comport=comport, position=[round(v, 3) for v in position])
                elif now - hang_since > 0.2 and sent[A_BUTTON]:
                    send({A_BUTTON: 0})
                phase_since = now
                time.sleep(0.03)
                continue
            if args.stop_comport and args.stop_comport in comport:
                result = "stop_comport"
                emit(event="stop_comport", comport=comport, position=[round(v, 3) for v in position])
                break
            if stop_dsg:
                variables = rayman.dsg()
                buffer, offset = variables[stop_dsg[0]]
                if buffer[offset] == stop_dsg[1]:
                    result = "stop_dsg"
                    emit(event="stop_dsg", variable=stop_dsg[0], value=stop_dsg[1], position=[round(v, 3) for v in position], comport=comport)
                    break
            attacking = False
            if followed is not None:
                if not followed.alive():
                    result = "follow_target_gone"
                    emit(event="follow_target_gone", position=[round(v, 3) for v in position])
                    break
                their = followed.position()
                their_comport = followed.comport() or ""
                if their_comport != followed_comport:
                    followed_comport = their_comport
                    emit(event="followed_comport", comport=their_comport, bits=f"{followed.custom_bits():08X}",
                         their=[round(v, 3) for v in their], position=[round(v, 3) for v in position])
                attacking = bool(args.attack_comport) and args.attack_comport in their_comport
                goal_radius = 1.6 if attacking else args.follow_distance
                if math.dist(their, goal) > 2.0:
                    goal = list(their)
                    try:
                        moved = rp.nearest(levels, *goal)
                    except SystemExit:
                        moved = goal_node
                    if moved != goal_node:
                        goal_node = moved
                        if route is not None and phase in ("walk", "hop"):
                            route = None  # replan toward the new position
                            phase_since = now
            at_goal = math.dist(position[:2], goal[:2]) <= goal_radius and abs(position[2] - goal[2]) <= 2.5
            if attacking and math.dist(position[:2], goal[:2]) <= 2.6 and abs(position[2] - goal[2]) <= 2.5:
                # Face the target and tap X (ordinary attack input); the game decides whether it connects.
                steer(position, {"x": goal[0], "y": goal[1]}, 0.35)
                cycle = (now - attack_since) % 0.5
                if now - attack_since > 0.5 and sent[X_BUTTON] == 0:
                    attack_since, hits = now, hits + 1
                    send({X_BUTTON: 1})
                elif sent[X_BUTTON] == 1 and now - attack_since > 0.15:
                    send({X_BUTTON: 0})
                route = None
                phase_since = now
                time.sleep(0.03)
                continue
            if sent[X_BUTTON]:
                send({X_BUTTON: 0})
            if at_goal:
                if followed is None:
                    result = "goal_reached"
                    emit(event="goal_reached", position=[round(v, 3) for v in position])
                    break
                send({AXIS_X: 0, AXIS_Y: 0})
                route = None
                phase_since = now
                time.sleep(0.03)
                continue
            recent = [(t, z) for t, z in recent if now - t <= 1.2] + [(now, position[2])]
            low_z = min(z for _, z in recent)
            if route is None:
                bouncing = not grounded() and now - phase_since > 2.5
                if not grounded() and not bouncing:
                    send({A_BUTTON: 0})
                    time.sleep(0.05)
                    continue
                # Bouncing on a spring never grounds: plan from the surface under the bounce.
                origin = (position[0], position[1], low_z) if bouncing else position
                route = replan(origin, ("initial" if stats["replans"] == 0 else "recover") + ("_airborne" if bouncing else ""))
                if route is None:
                    result = "no_route"
                    break
                if len(route) <= 1:
                    # Already in the goal cell (the stated goal height can differ from the surface).
                    if followed is None:
                        result = "goal_reached"
                        emit(event="goal_reached", note="start and goal share a cell", position=[round(v, 3) for v in position])
                        break
                    route = None
                    send({AXIS_X: 0, AXIS_Y: 0})
                    time.sleep(0.2)
                    continue
                index, phase, phase_since, attempts = 1, "walk", now, 0
                plan_time = time.monotonic()
                best, best_time = None, now
                continue
            target = route[index]
            move = target["move"]
            distance = math.dist(position[:2], (target["x"], target["y"]))
            vz = None
            if previous_z is not None and now > previous_t:
                vz = (position[2] - previous_z) / (now - previous_t)
            previous_z, previous_t = position[2], now

            # low_z (lowest height in the last 1.2 s) lets a bounce over the waypoint count.
            reached = distance <= target["radius"] and low_z >= target["z_min"] and low_z <= target["z"] + 2.0
            if move == "drop":
                reached = distance <= 2.0 and abs(position[2] - target["z"]) <= 1.2 and grounded()
            elif move in ("jump", "glide"):
                reached = distance <= 2.0 and target["z_min"] <= position[2] <= target["z"] + 2.0 and grounded()
            if reached:
                send({A_BUTTON: 0})
                emit(event="reached", label=target["label"], move=move, position=[round(v, 3) for v in position])
                index += 1
                phase, phase_since, attempts = "walk", now, 0
                best, best_time = None, now
                if index >= len(route):
                    route = None
                continue

            if move == "walk" or move == "drop":
                # In the air (spring bounce, hop) approach proportionally so the landing is not overshot.
                steer(position, target, 1.0 if grounded() else max(0.3, min(1.0, distance / 4.0)))
                if best is None or best - distance >= 0.5:
                    best, best_time = distance, now
                # Not right after a plan: the start can be a moving platform absent from static collision.
                fell = move == "walk" and grounded() and position[2] < target["z"] - 2.5 and now - plan_time > 3.0
                if fell or now - best_time > 6.0:
                    stats["failed_moves"] += 1
                    emit(event="walk_failed", label=target["label"], cause="fell" if fell else "stalled",
                         position=[round(v, 3) for v in position])
                    if not fell:
                        ti, tj, _ = target["node"]
                        for di in (-1, 0, 1):
                            for dj in (-1, 0, 1):
                                for kk, lz in enumerate(levels.get((ti + di, tj + dj), [])):
                                    if abs(lz - target["z"]) <= 1.5:
                                        blocked_nodes.add((ti + di, tj + dj, kk))
                    neutral()
                    route = None
                    phase_since = now
                elif now - best_time > 2.5 and grounded() and phase != "hop":
                    phase, phase_since = "hop", now
                    send({A_BUTTON: 1})
                elif phase == "hop" and now - phase_since > 0.25:
                    send({A_BUTTON: 0})
                    if now - phase_since > 1.5:
                        phase = "walk"
            else:  # jump or glide from the previous waypoint
                steer(position, target)
                if phase == "walk":
                    if grounded():
                        phase, phase_since, apex_seen = "air_press", now, False
                        attempts += 1
                        stats["jumps" if move == "jump" else "glides"] += 1
                        send({A_BUTTON: 1})
                        emit(event="takeoff", label=target["label"], move=move, attempt=attempts,
                             position=[round(v, 3) for v in position])
                elif phase == "air_press":
                    if now - phase_since >= 0.3:
                        send({A_BUTTON: 0})
                        phase = "air"
                elif phase == "air":
                    if vz is not None and vz < 0.5 and now - phase_since > 0.45:
                        apex_seen = True
                    over_target = distance <= 0.8
                    if move == "glide" and apex_seen and not over_target and position[2] > target["z"] + 0.4 and now - phase_since > 0.5:
                        send({A_BUTTON: 1})
                        phase = "glide_hold"
                    elif grounded() and now - phase_since > 0.6:
                        phase = "landed"
                elif phase == "glide_hold":
                    if distance <= 0.8 or position[2] <= target["z"] + 0.3 or (grounded() and now - phase_since > 1.0):
                        send({A_BUTTON: 0})
                        phase = "air"
                        apex_seen = False if distance <= 0.8 else apex_seen
                        if distance <= 0.8:
                            move = "jump"  # fall straight down from here
                on_target = distance <= 2.0 and target["z_min"] <= position[2] <= target["z"] + 2.0
                if phase == "landed" and on_target:
                    continue  # the reached test at the top of the loop accepts it
                if phase == "landed" or now - phase_since > 12.0:
                    # Landed somewhere other than the target.
                    send({A_BUTTON: 0})
                    stats["failed_moves"] += 1
                    emit(event="move_failed", label=target["label"], move=target["move"], attempt=attempts,
                         position=[round(v, 3) for v in position])
                    if target.get("from_node"):
                        # Attempts are counted per move across replans.
                        edge = (tuple(target["from_node"]), tuple(target["node"]))
                        edge_failures[edge] = edge_failures.get(edge, 0) + 1
                        # The same landing missed from several take-offs is not a usable landing.
                        landing = tuple(target["node"])
                        landing_failures[landing] = landing_failures.get(landing, 0) + 1
                        if landing_failures[landing] >= 3:
                            li, lj, _ = landing
                            for di in (-1, 0, 1):
                                for dj in (-1, 0, 1):
                                    for kk, lz in enumerate(levels.get((li + di, lj + dj), [])):
                                        if abs(lz - target["z"]) <= 1.0:
                                            blocked_landings.add((li + di, lj + dj, kk))
                        if edge_failures[edge] >= 2:
                            blocked_edges.add(edge)
                            emit(event="move_blocked", label=target["label"], move=target["move"])
                    neutral()
                    route = None
                    phase, phase_since = "walk", now

            if now - last_sample >= 0.25:
                last_sample = now
                emit(event="sample", rayman=[round(v, 3) for v in position], comport=comport[6:], target=target["label"],
                     distance=round(distance, 2), phase=phase, stick=[sent[AXIS_X], sent[AXIS_Y]], a=sent[A_BUTTON])
            time.sleep(0.03)
        else:
            result = "time_limit"
    except BaseException as exc:  # release input on every exit path
        error = {"type": type(exc).__name__, "message": str(exc)}
        emit(event="error", **error)
    finally:
        try:
            neutral()
        except OSError as release_error:
            error = error or {"type": type(release_error).__name__, "message": str(release_error)}
        emit(event="end", result=result if error is None else "error", elapsed_seconds=round(time.monotonic() - start_time, 3), **stats, error=error)
        log.close()
    print(json.dumps({"result": result if error is None else "error", **stats, "error": error}))
    return 0 if error is None else 1


if __name__ == "__main__":
    raise SystemExit(main())
