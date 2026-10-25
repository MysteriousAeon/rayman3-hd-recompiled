"""Offline route planner over the decoded static collision (tools/m7_collision_map.py output).

Builds a multi-level grid of walkable surfaces and searches walk / jump / drop moves between two
world positions. The result is a planning aid for the hidden route pilot, not a physics model:
moving platforms and actors are absent from static collision unless given with --platforms, the
jump envelope is a conservative guess from observed jumps, and every plan must be confirmed by
running it through normal input.

Usage:
  python tools/m7_route_plan.py SNAPSHOT_DIR --start X Y Z --goal X Y Z [--out route.json]
         [--platforms extra.json] [--avoid-below Z] [--png plan.png]
extra.json: [{"x":..,"y":..,"z":..,"radius":..}] additional standable discs (dynamic platforms).
Output route: [{"label","x","y","z","radius","z_min","move"}], move in walk|jump|glide|drop for
the move that ARRIVES at that waypoint.
"""
import argparse
import heapq
import json
import math

import m7_collision_map as cm

CELL = 1.0
STEP_UP, STEP_DOWN = 0.7, 1.3      # walkable height change between adjacent cells
JUMP_UP = 4.3                      # observed tap jumps rise 4.2 to 4.9
JUMP_RANGE = 6.0                   # horizontal reach of a running jump at equal height
GLIDE_RANGE = 18.0                 # cap on a jump followed by a helicopter glide
HEAD = 1.5
MODEL = 4                          # bump when move costs or envelopes change (invalidates caches)
STAND_NZ = 0.75                    # steeper faces (e.g. nz 0.675 near 60.5,100.5) did not hold a landing
WATER_FLOOR = -9.984               # intro_15: shallow floor under water material 16384 (z -9.675)


def build(tris, avoid_below, platforms):
    grid = {}
    for p, n, mid, mt in tris:
        if cm.unit_nz(n) < STAND_NZ or mid == 16384:
            continue
        xs, ys = [q[0] for q in p], [q[1] for q in p]
        for i in range(math.floor(min(xs) / CELL), math.floor(max(xs) / CELL) + 1):
            for j in range(math.floor(min(ys) / CELL), math.floor(max(ys) / CELL) + 1):
                z = cm.tri_z_at(p, (i + 0.5) * CELL, (j + 0.5) * CELL)
                if z is not None and z >= avoid_below:
                    grid.setdefault((i, j), []).append(z)
    for item in platforms:
        r = item.get("radius", 1.5)
        for i in range(math.floor((item["x"] - r) / CELL), math.floor((item["x"] + r) / CELL) + 1):
            for j in range(math.floor((item["y"] - r) / CELL), math.floor((item["y"] + r) / CELL) + 1):
                if math.hypot((i + 0.5) * CELL - item["x"], (j + 0.5) * CELL - item["y"]) <= r:
                    grid.setdefault((i, j), []).append(item["z"])
    ceilings = {}
    for p, n, mid, mt in tris:
        if cm.unit_nz(n) > -0.3:
            continue
        xs, ys = [q[0] for q in p], [q[1] for q in p]
        for i in range(math.floor(min(xs) / CELL), math.floor(max(xs) / CELL) + 1):
            for j in range(math.floor(min(ys) / CELL), math.floor(max(ys) / CELL) + 1):
                z = cm.tri_z_at(p, (i + 0.5) * CELL, (j + 0.5) * CELL)
                if z is not None:
                    ceilings.setdefault((i, j), []).append(z)
    levels = {}
    for cell, zs in grid.items():
        merged = []
        for z in sorted(zs):
            if not merged or z - merged[-1] > 0.6:
                merged.append(z)
            else:
                merged[-1] = z
        # A level needs head room below the next ceiling above it.
        keep = []
        for z in merged:
            above = [c for c in ceilings.get(cell, []) if c > z + 0.05]
            if not above or min(above) - z >= HEAD:
                keep.append(z)
        if keep:
            levels[cell] = keep
    return levels


def is_edge(levels, node):
    """True where plain walking cannot continue in one of the four axis directions."""
    i, j, k = node
    z = levels[(i, j)][k]
    for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        if not any(-STEP_DOWN <= lz - z <= STEP_UP for lz in levels.get((i + di, j + dj), [])):
            return True
    return False


def nearest(levels, x, y, z):
    best = None
    ci, cj = math.floor(x / CELL), math.floor(y / CELL)
    for i in range(ci - 3, ci + 4):
        for j in range(cj - 3, cj + 4):
            for k, lz in enumerate(levels.get((i, j), [])):
                d = math.hypot((i + 0.5) * CELL - x, (j + 0.5) * CELL - y) + 2 * abs(lz - z)
                if best is None or d < best[0]:
                    best = (d, (i, j, k))
    if best is None:
        raise SystemExit(f"no walkable surface near {x},{y},{z}")
    return best[1]


def plan(levels, start, goal, allow_glide=True, blocked_edges=(), blocked_nodes=(), cache=None, blocked_landings=()):
    """A* (straight-line heuristic); blocked_edges holds (from, to) moves that failed live.

    cache (a dict kept by the caller) memoises the expensive jump/glide candidates per node."""
    goal_xy = ((goal[0] + 0.5) * CELL, (goal[1] + 0.5) * CELL)

    def estimate(node):
        return math.hypot((node[0] + 0.5) * CELL - goal_xy[0], (node[1] + 0.5) * CELL - goal_xy[1])

    def z_of(node):
        return levels[(node[0], node[1])][node[2]]

    def walk_neighbours(node):
        i, j, _ = node
        z = z_of(node)
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                if di or dj:
                    for k, lz in enumerate(levels.get((i + di, j + dj), [])):
                        other = (i + di, j + dj, k)
                        if -STEP_DOWN <= lz - z <= STEP_UP and other not in blocked_nodes:
                            # Keep walking lines off ledges: rims cost more than interiors.
                            # Wading (observed: Rayman stands at z -10.0 under the water surface) is a last resort.
                            wade = 3.0 if abs(lz - WATER_FLOOR) < 0.05 else 0.0
                            yield other, math.hypot(di, dj) * CELL * (1.0 + 2.0 * edge(other) + wade), "walk"

    edge_memo = cache.setdefault("edge", {}) if cache is not None else {}

    def edge(node):
        if node not in edge_memo:
            edge_memo[node] = 1.0 if is_edge(levels, node) else 0.4 if any(
                is_edge(levels, (node[0] + di, node[1] + dj, kk))
                for di in (-1, 0, 1) for dj in (-1, 0, 1)
                for kk, lz in enumerate(levels.get((node[0] + di, node[1] + dj), []))
                if abs(lz - z_of(node)) <= STEP_DOWN) else 0.0
        return edge_memo[node]

    def clear(a, b, za, zb, top):
        steps = int(max(abs(b[0] - a[0]), abs(b[1] - a[1])) * 2)
        for s in range(1, steps):
            t = s / steps
            cell = (round(a[0] + (b[0] - a[0]) * t), round(a[1] + (b[1] - a[1]) * t))
            if cell in ((a[0], a[1]), (b[0], b[1])):
                continue
            arc = za + (zb - za) * t + (top - max(za, zb)) * 4 * t * (1 - t) + (max(za, zb) - (za + (zb - za) * t))
            for lz in levels.get(cell, []):
                if za - 0.3 < lz < za + 9 and lz > arc + 0.3 and lz > min(za, zb) + 0.3:
                    if lz > max(za, zb) + 0.3:
                        return False
        return True

    def jump_neighbours(node):
        if cache is not None and (node, allow_glide) in cache:
            found = cache[(node, allow_glide)]
        else:
            found = list(jump_candidates(node))
            if cache is not None:
                cache[(node, allow_glide)] = found
        for other, cost, kind in found:
            if (node, other) not in blocked_edges and other not in blocked_nodes and other not in blocked_landings:
                yield other, cost, kind

    def jump_candidates(node):
        i, j, _ = node
        z = z_of(node)
        # Only take off where plain walking cannot continue in some direction.
        if not is_edge(levels, node):
            return
        reach = int(GLIDE_RANGE / CELL) if allow_glide else int(JUMP_RANGE / CELL)
        for di in range(-reach, reach + 1):
            for dj in range(-reach, reach + 1):
                d = math.hypot(di, dj) * CELL
                if d < 1.5 or d > GLIDE_RANGE:
                    continue
                for k, lz in enumerate(levels.get((i + di, j + dj), [])):
                    dz = lz - z
                    if dz > JUMP_UP:
                        continue
                    if d <= 2.5 and dz < -STEP_DOWN:
                        kind, limit, cost = "drop", 2.5, d + 3 + 0.05 * -dz
                    elif dz >= -1.0:
                        kind, limit, cost = "jump", JUMP_RANGE - max(0.0, dz) * 0.6, d + 12 + max(0.0, dz) + 8 * max(0.0, dz - 3.4)
                    else:
                        kind, limit, cost = "glide", 0.0, d + 20
                    if kind != "drop" and dz <= 2.0 and d > limit:
                        # Jump apex about 4 above take-off, then helicopter descent at roughly 2:1.
                        kind, limit, cost = "glide", min(GLIDE_RANGE, 2.0 + 2.0 * (4.0 - dz)), d + 20
                    if kind == "glide" and not allow_glide:
                        continue
                    if d > limit:
                        continue
                    if clear((i, j), (i + di, j + dj), z, lz, max(z, lz) + (4.0 if kind != "drop" else 0.0)):
                        yield (i + di, j + dj, k), cost, kind

    distance = {start: 0.0}
    previous = {}
    queue = [(estimate(start), 0.0, start)]
    while queue:
        _, cost, node = heapq.heappop(queue)
        if node == goal:
            break
        if cost > distance.get(node, math.inf):
            continue
        for moves in (walk_neighbours(node), jump_neighbours(node)):
            for other, step, kind in moves:
                total = cost + step
                if total < distance.get(other, math.inf):
                    distance[other] = total
                    previous[other] = (node, kind)
                    heapq.heappush(queue, (total + estimate(other), total, other))
    if goal not in distance:
        return None, distance
    path = [(goal, None)]
    while path[-1][0] != start:
        node, kind = previous[path[-1][0]]
        path[-1] = (path[-1][0], kind)
        path.append((node, None))
    path[-1] = (start, "walk")
    return list(reversed(path)), distance


def world(levels, node):
    return ((node[0] + 0.5) * CELL, (node[1] + 0.5) * CELL, levels[(node[0], node[1])][node[2]])


def to_route(levels, path, spacing=4.0):
    """Waypoints from a node path; each records its nodes so a failed move can be blocked."""
    route = []
    since = 0.0
    for index, (node, kind) in enumerate(path):
        x, y, z = world(levels, node)
        last = index == len(path) - 1
        special = kind != "walk" or (not last and path[index + 1][1] != "walk")
        if index:
            since += math.dist(world(levels, path[index - 1][0])[:2], (x, y))
        if special or last or since >= spacing:
            since = 0.0
            takeoff = not last and path[index + 1][1] != "walk"
            route.append({"label": f"n{len(route)}_{kind}" + ("_takeoff" if takeoff else ""), "x": round(x, 2), "y": round(y, 2),
                          "z": round(z, 2), "radius": 1.2 if special or is_edge(levels, node) else 2.0, "z_min": round(z - 0.8, 2),
                          "move": kind, "next": path[index + 1][1] if not last else None,
                          "node": list(node), "from_node": list(path[index - 1][0]) if index else None})
    return route


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("snapshot")
    parser.add_argument("--start", nargs=3, type=float, required=True)
    parser.add_argument("--goal", nargs=3, type=float, required=True)
    parser.add_argument("--out")
    parser.add_argument("--platforms")
    parser.add_argument("--avoid-below", type=float, default=-1e9)
    parser.add_argument("--no-glide", action="store_true")
    parser.add_argument("--spacing", type=float, default=4.0)
    args = parser.parse_args()

    platforms = json.load(open(args.platforms)) if args.platforms else []
    levels = build(cm.load(args.snapshot), args.avoid_below, platforms)
    start, goal = nearest(levels, *args.start), nearest(levels, *args.goal)
    path, distance = plan(levels, start, goal, allow_glide=not args.no_glide)

    def world_of(node):
        return world(levels, node)

    if path is None:
        # Report the reachable node closest to the goal so the missing link can be examined.
        gx, gy, gz = world_of(goal)
        best = min(distance, key=lambda node: math.dist(world_of(node), (gx, gy, gz)))
        print(json.dumps({"result": "unreachable", "reachable_nodes": len(distance),
                          "closest_reachable": [round(v, 2) for v in world_of(best)],
                          "distance_to_goal": round(math.dist(world_of(best), (gx, gy, gz)), 2)}))
        return 1
    route = to_route(levels, path, args.spacing)
    summary = {"result": "ok", "nodes": len(path), "waypoints": len(route),
               "moves": {kind: sum(1 for item in route if item["move"] == kind) for kind in ("walk", "jump", "glide", "drop")}}
    print(json.dumps(summary))
    for item in route:
        if item["move"] != "walk" or item["next"] not in ("walk", None):
            print(json.dumps(item))
    if args.out:
        with open(args.out, "w", encoding="utf-8") as stream:
            stream.write("[\n" + ",\n".join("  " + json.dumps(item) for item in route) + "\n]\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
