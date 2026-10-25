"""Bounded camera-relative intro_15 route pilot using normal XAM input only.

The route file is a JSON array of objects with label, x, y, and radius fields.
Rayman/camera reads are observational; movement is appended to the controlled
XAM schedule (never sent through desktop input and never written to guest state).

Usage: python tools/m6_route_probe.py PID BASE_HEX RUN_DIR --targets route.json
       [--seconds 300] [--output route.jsonl] [--jump-every 0] [--jump-hold 0.2]
"""
import argparse
import json
import math
import sys
import time
from pathlib import Path

from m5_live import Actor, Process


FORWARD_POSITIVE = 26  # W
FORWARD_NEGATIVE = 22  # S
RIGHT_POSITIVE = 7  # D
RIGHT_NEGATIVE = 4  # A
MOVEMENT_KEYS = (RIGHT_NEGATIVE, RIGHT_POSITIVE, FORWARD_NEGATIVE, FORWARD_POSITIVE)
COLLECTIBLE_MODELS = {"LAU_mLums", "NIK_mPickup"}
COLLECTIBLE_NEAR_RADIUS = 5.0
JUMP_SCANCODE = 44


def read_targets(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list) or not data:
        raise ValueError("targets must be a non-empty JSON list")
    targets = []
    for index, item in enumerate(data):
        if not isinstance(item, dict):
            raise ValueError(f"target {index} must be an object")
        label = item.get("label")
        if not isinstance(label, str) or not label:
            raise ValueError(f"target {index} needs a non-empty label")
        values = [item.get("x"), item.get("y"), item.get("radius")]
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) for value in values):
            raise ValueError(f"target {label!r} needs finite numeric x, y, and radius")
        x, y, radius = map(float, values)
        if radius < 0:
            raise ValueError(f"target {label!r} radius cannot be negative")
        target = {"label": label, "x": x, "y": y, "radius": radius}
        if "z_min" in item:
            z_min = item["z_min"]
            if isinstance(z_min, bool) or not isinstance(z_min, (int, float)) or not math.isfinite(z_min):
                raise ValueError(f"target {label!r} needs finite numeric z_min")
            target["z_min"] = float(z_min)
        targets.append(target)
    return targets


def axis_key(score: float, held: set[int], positive: int, negative: int) -> int | None:
    """Select one axis key with a 0.30 entry and 0.15 release threshold."""
    if positive in held:
        if score >= 0.15:
            return positive
        if score <= -0.30:
            return negative
        return None
    if negative in held:
        if score <= -0.15:
            return negative
        if score >= 0.30:
            return positive
        return None
    if score >= 0.30:
        return positive
    if score <= -0.30:
        return negative
    return None


def desired_movement_keys(forward_score: float, right_score: float, held: set[int]) -> set[int]:
    current_forward = FORWARD_POSITIVE if FORWARD_POSITIVE in held else FORWARD_NEGATIVE if FORWARD_NEGATIVE in held else None
    current_right = RIGHT_POSITIVE if RIGHT_POSITIVE in held else RIGHT_NEGATIVE if RIGHT_NEGATIVE in held else None
    forward_key = axis_key(
        forward_score,
        {current_forward} if current_forward is not None else set(),
        FORWARD_POSITIVE,
        FORWARD_NEGATIVE,
    )
    right_key = axis_key(
        right_score,
        {current_right} if current_right is not None else set(),
        RIGHT_POSITIVE,
        RIGHT_NEGATIVE,
    )
    return {key for key in (forward_key, right_key) if key is not None}


def distance_xy(position: tuple[float, ...], target: dict) -> float:
    return math.hypot(target["x"] - position[0], target["y"] - position[1])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pid", type=int)
    parser.add_argument("base", type=lambda value: int(value, 16))
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--seconds", type=int, default=300)
    parser.add_argument("--targets", type=Path, required=True)
    parser.add_argument("--output", default="route.jsonl")
    parser.add_argument("--jump-every", type=float, default=0.0)
    parser.add_argument("--jump-hold", type=float, default=0.2)
    args = parser.parse_args()
    if args.pid <= 0:
        parser.error("PID must be positive")
    if not 1 <= args.seconds <= 500:
        parser.error("seconds must be between 1 and 500")
    if not math.isfinite(args.jump_every) or (args.jump_every != 0 and args.jump_every < 1):
        parser.error("jump-every must be 0 (disabled) or a finite value of at least 1 second")
    if not math.isfinite(args.jump_hold) or args.jump_hold <= 0:
        parser.error("jump-hold must be a finite positive number")
    if args.jump_every > 0 and args.jump_hold >= args.jump_every:
        parser.error("jump-hold must be less than jump-every when jumping is enabled")

    run_dir = args.run_dir.resolve()
    targets_path = args.targets.resolve()
    output = Path(args.output)
    if not output.is_absolute():
        output = run_dir / output
    schedule_path = run_dir / "schedule.txt"
    actors_path = run_dir / "actors_intro_15.json"
    if not run_dir.is_dir():
        parser.error(f"run directory does not exist: {run_dir}")
    if not targets_path.is_file():
        parser.error(f"target file does not exist: {targets_path}")
    if not schedule_path.is_file():
        parser.error(f"input schedule does not exist: {schedule_path}")
    if not actors_path.is_file():
        parser.error(f"intro_15 actor discovery file does not exist: {actors_path}")

    output.parent.mkdir(parents=True, exist_ok=True)
    log = output.open("a", encoding="utf-8", buffering=1)
    start = time.monotonic()
    deadline = start + args.seconds
    held: set[int] = set()
    jump_release_at = None
    next_jump_at = None
    result = "error"
    reached = 0
    error = None

    def emit(**data) -> None:
        log.write(json.dumps({"t": round(time.time(), 3), **data}, separators=(",", ":")) + "\n")
        log.flush()

    def set_keys(desired: set[int]) -> None:
        nonlocal held
        releases = sorted(held - desired)
        presses = sorted(desired - held)
        if not releases and not presses:
            return
        with schedule_path.open("a", encoding="ascii", newline="") as schedule:
            for scan in releases:
                schedule.write(f"0 {scan} 0\n")
                held.discard(scan)
                emit(event="key_edge", scancode=scan, down=False)
            for scan in presses:
                schedule.write(f"0 {scan} 1\n")
                held.add(scan)
                emit(event="key_edge", scancode=scan, down=True)
            schedule.flush()

    def reset_jump() -> None:
        nonlocal jump_release_at, next_jump_at
        jump_release_at = None
        next_jump_at = None

    def add_jump_pulse(desired: set[int], now: float) -> set[int]:
        nonlocal jump_release_at, next_jump_at
        keys = set(desired)
        if args.jump_every == 0:
            return keys
        if jump_release_at is not None and now >= jump_release_at:
            jump_release_at = None
        if jump_release_at is None and (next_jump_at is None or now >= next_jump_at):
            jump_release_at = now + args.jump_hold
            next_jump_at = now + args.jump_every
        if jump_release_at is not None:
            keys.add(JUMP_SCANCODE)
        return keys

    try:
        targets = read_targets(targets_path)
        process = Process(args.pid, args.base)
        actor_data = json.loads(actors_path.read_text(encoding="utf-8"))["actors"]
        actors = []
        for record in actor_data:
            try:
                actor = Actor(process, int(record["so"], 16))
                if actor.model:
                    actors.append(actor)
            except (KeyError, TypeError, ValueError, IndexError, OSError):
                continue

        rayman = next((actor for actor in actors if actor.model == "YLT_RaymanModel"), None)
        camera = next((actor for actor in actors if actor.model == "StdCam"), None)
        if rayman is None or camera is None:
            raise RuntimeError("intro_15 actor discovery lacks Rayman or StdCam")
        collectibles = [actor for actor in actors if actor.model in COLLECTIBLE_MODELS]
        collectible_state = {}
        for actor in collectibles:
            position = actor.position()
            collectible_state[actor.so] = {
                "model": actor.model,
                "alive": actor.alive(),
                "bits": actor.custom_bits(),
                "position": position,
                "near_logged": False,
            }

        emit(
            event="start",
            pid=args.pid,
            base=f"{args.base:08X}",
            seconds=args.seconds,
            targets=targets,
            rayman=f"{rayman.so:08X}",
            camera=f"{camera.so:08X}",
            collectible_models={name: sum(actor.model == name for actor in collectibles) for name in sorted(COLLECTIBLE_MODELS)},
            stall_seconds=15,
            stall_improvement_units=1.0,
            alignment_enter=0.30,
            alignment_release=0.15,
            collectible_near_radius=COLLECTIBLE_NEAR_RADIUS,
            jump_enabled=args.jump_every > 0,
            jump_every=args.jump_every,
            jump_hold=args.jump_hold,
            jump_scancode=JUMP_SCANCODE,
        )

        # Establish neutral state through the same schedule path. Preserve the
        # old directional-only baseline unless optional jumping is enabled.
        with schedule_path.open("a", encoding="ascii", newline="") as schedule:
            neutral_keys = (*MOVEMENT_KEYS, JUMP_SCANCODE) if args.jump_every > 0 else MOVEMENT_KEYS
            for scan in neutral_keys:
                schedule.write(f"0 {scan} 0\n")
                emit(event="key_edge", scancode=scan, down=False, reason="route_start_neutral")
            schedule.flush()

        target_index = 0
        best_distance = None
        last_improvement = time.monotonic()
        last_sample = 0.0
        previous_sample_position = None
        while time.monotonic() < deadline:
            now = time.monotonic()
            if not process.running() or not rayman.alive():
                result = "actor_gone"
                emit(event="actor_gone", process_running=process.running(), rayman_alive=rayman.alive())
                break

            rayman_position = rayman.position()
            camera_position = camera.position()
            if rayman_position is None or camera_position is None or not all(math.isfinite(x) for x in (*rayman_position, *camera_position)):
                emit(event="position_unavailable", rayman=rayman_position, camera=camera_position)
                reset_jump()
                set_keys(set())
                time.sleep(min(0.2, max(0.0, deadline - time.monotonic())))
                continue

            target = targets[target_index]
            distance = distance_xy(rayman_position, target)
            if distance <= target["radius"] and rayman_position[2] >= target.get("z_min", -math.inf):
                set_keys(set())
                reset_jump()
                emit(event="target_reached", target=target["label"], distance=round(distance, 3), position=list(rayman_position))
                reached += 1
                target_index += 1
                if target_index >= len(targets):
                    result = "reached_all"
                    break
                best_distance = None
                last_improvement = time.monotonic()
                continue

            if best_distance is None or best_distance - distance >= 1.0:
                best_distance = distance
                last_improvement = now

            forward_x = rayman_position[0] - camera_position[0]
            forward_y = rayman_position[1] - camera_position[1]
            forward_length = math.hypot(forward_x, forward_y)
            if forward_length <= 1e-5:
                emit(event="camera_forward_unavailable", target=target["label"], distance=round(distance, 3))
                reset_jump()
                set_keys(set())
            else:
                forward = (forward_x / forward_length, forward_y / forward_length)
                right = (forward[1], -forward[0])
                delta = (target["x"] - rayman_position[0], target["y"] - rayman_position[1])
                unit_delta = (delta[0] / distance, delta[1] / distance) if distance else (0.0, 0.0)
                forward_score = unit_delta[0] * forward[0] + unit_delta[1] * forward[1]
                right_score = unit_delta[0] * right[0] + unit_delta[1] * right[1]
                desired = desired_movement_keys(forward_score, right_score, held)
                set_keys(add_jump_pulse(desired, now))

            if now - last_sample >= 0.2:
                last_sample = now
                displacement = None
                if previous_sample_position is not None:
                    displacement = math.dist(rayman_position, previous_sample_position)
                previous_sample_position = rayman_position
                emit(
                    event="sample",
                    target=target["label"],
                    distance=round(distance, 3),
                    radius=target["radius"],
                    rayman=[round(x, 3) for x in rayman_position],
                    camera=[round(x, 3) for x in camera_position],
                    displacement_since_previous_sample=round(displacement, 4) if displacement is not None else None,
                    comport=rayman.comport(),
                    reflex_comport=rayman.comport(reflex=True),
                    held=sorted(held),
                    best_distance=round(best_distance, 3) if best_distance is not None else None,
                    seconds_without_improvement=round(now - last_improvement, 3),
                )

                for actor in collectibles:
                    before = collectible_state[actor.so]
                    current_alive = actor.alive()
                    current_bits = actor.custom_bits() if current_alive else before["bits"]
                    current_position = actor.position() if current_alive else before["position"]
                    candidate_position = current_position or before["position"]
                    nearby = None
                    if candidate_position is not None:
                        nearby = min(
                            ((distance_xy(candidate_position, item), item) for item in targets),
                            key=lambda entry: entry[0],
                        )
                    near_limit = max(COLLECTIBLE_NEAR_RADIUS, nearby[1]["radius"] * 3) if nearby else 0.0
                    is_near = nearby is not None and nearby[0] <= near_limit
                    if is_near:
                        before["near_logged"] = True
                    changed = current_alive != before["alive"] or current_bits != before["bits"]
                    if changed and (before["near_logged"] or is_near):
                        emit(
                            event="collectible_change",
                            model=before["model"],
                            actor=f"{actor.so:08X}",
                            alive_before=before["alive"],
                            alive_after=current_alive,
                            bits_before=f"{before['bits']:08X}",
                            bits_after=f"{current_bits:08X}",
                            nearest_target=nearby[1]["label"] if nearby else None,
                            distance_to_target=round(nearby[0], 3) if nearby else None,
                        )
                    before["alive"] = current_alive
                    before["bits"] = current_bits
                    if current_position is not None:
                        before["position"] = current_position

            stalled_for = now - last_improvement
            if stalled_for >= 15.0:
                result = "stalled"
                emit(
                    event="stalled",
                    target=target["label"],
                    distance=round(distance, 3),
                    best_distance=round(best_distance, 3) if best_distance is not None else None,
                    seconds_without_improvement=round(stalled_for, 3),
                )
                break
            time.sleep(min(0.2, max(0.0, deadline - time.monotonic())))
        else:
            result = "time_limit"

    except BaseException as exc:
        error = {"type": type(exc).__name__, "message": str(exc)}
        emit(event="error", **error)
    finally:
        try:
            set_keys(set())
        except Exception as release_error:
            if error is None:
                error = {"type": type(release_error).__name__, "message": str(release_error)}
            emit(event="release_error", **error)
        emit(
            event="end",
            result=result if error is None else "error",
            reached_targets=reached,
            target_count=len(targets) if "targets" in locals() else None,
            elapsed_seconds=round(time.monotonic() - start, 3),
            error=error,
        )
        log.close()

    if error is not None:
        print(json.dumps({"result": "error", "output": str(output), "error": error}), file=sys.stderr)
        return 1
    summary = {"result": result, "reached_targets": reached, "target_count": len(targets), "output": str(output)}
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
