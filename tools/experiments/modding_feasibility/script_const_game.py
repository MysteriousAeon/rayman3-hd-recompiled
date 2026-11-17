"""D-223 / E-455: one hidden run showing a script-constant mod in the running game. Isolated test-only level
entry (`-level:intro_10`, D-040) through tools/m9_license_run.py (hidden window, muted, no physical controller,
isolated test profile, no input, no captures). A private test mod, made here from the person's own files, moves
one real constant of the flight generator's NIN_C_FlyMvt script 0 to the next float32 (one unit in the last
place: the smallest change that is still bit-exact to detect). After the level opens, the existing read-only
probes (m5_memory_probe.py actor discovery, m5_script_probe.py script decode) read the live script. Nothing is
written to guest memory; no input is sent.

PASS needs: the runtime reports the plan active and serves the range from intro_10.lvl at the node's offset; the
live node has the mod's bits; every other int / real node of every live behaviour of the level equals the file
(only the edited node differs); M21 / M22 / M23-haptics judges pass. Outputs stay under private/work/d223/.

usage: python tools/experiments/modding_feasibility/script_const_game.py TAG [--settle 15] [--seconds 120]
"""
import argparse
import json
import os
import re
import struct
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))
import r3hd_mods as rm  # noqa: E402

GAME = ROOT / "private" / "extracted" / "5841123F"
RUNS = ROOT / "private" / "work" / "m6_runs"
LEVEL, NEEDLE = "intro_10", "NIN_C_FlyMvt"

ap = argparse.ArgumentParser()
ap.add_argument("tag")
ap.add_argument("--settle", type=int, default=15)
ap.add_argument("--seconds", type=int, default=120)
a = ap.parse_args()
if not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", a.tag):
    ap.error("bad tag")
work = ROOT / "private" / "work" / "d223" / a.tag
run = f"d223_{a.tag}"
if work.exists() or (RUNS / run).exists():
    raise SystemExit(f"exists: {work} or {RUNS / run}")
work.mkdir(parents=True)

# 1. the private test mod, from the person's own level file
ix = rm.read_script_index(GAME, LEVEL)
name = next(n for n in ix["behaviours"] if n.endswith(":" + NEEDLE))
na, nodes = ix["behaviours"][name][0]
k = next(i for i, (p, _, kind) in enumerate(nodes) if kind == rm.SCRIPT_KINDS["real"]
         and 1e-30 < abs(struct.unpack(">f", struct.pack(">I", p))[0]) < 1e30)
old_bits = nodes[k][0]
new_bits = old_bits + 1
new_value = struct.unpack(">f", struct.pack(">I", new_bits))[0]
offset = na + 8 * k
src = work / "mod_src"
src.mkdir()
(src / "mod.json").write_text(json.dumps({
    "format": 1, "id": "d223.flymvt-ulp", "name": "D-223 test", "version": "1.0.0",
    "target": {"title_id": rm.TITLE_ID, "releases": rm.release_ids({"home": None}), "min_port_version": "0.0.1"},
    "overrides": [{"type": "script-constant", "level": LEVEL, "behavior": name, "script": 0, "node": k,
                   "script_sha256": rm.script_hash(ix, na, nodes), "kind": "real", "value": new_value}]}),
    encoding="utf-8")
common = ["--mods-root", str(work / "mods"), "--cache", str(work / "cache"), "--game-dir", str(GAME), "--json"]


def mods(*args):
    r = subprocess.run([sys.executable, "-I", str(TOOLS / "r3hd_mods.py"), *args, *common], capture_output=True,
                       text=True, cwd=ROOT)
    out = json.loads(r.stdout)
    if out.get("result") != "ok":
        raise SystemExit(f"r3hd_mods {args}: {out}")
    return out


mods("import", str(src), "--enable")
plan = mods("plan")["plan"]
row = {"run": run, "level": LEVEL, "node": k, "offset": offset, "old_bits": f"{old_bits:08X}",
       "new_bits": f"{new_bits:08X}", "plan_ranges": sum(1 for ln in Path(plan).read_text().splitlines()
                                                        if ln.startswith("range "))}

# 2. the hidden run (as tools/m14_script_scan.py), with the plan
steps = work / "steps.txt"
steps.write_text(f"wait {a.seconds - 8}\n", encoding="ascii")
env = dict(os.environ)
env["R3HD_MODS_PLAN"] = plan
probe_out = work / "live"
with (work / "driver.log").open("w") as log:
    game = subprocess.Popen([sys.executable, str(TOOLS / "m9_license_run.py"), run, str(steps), "--license-mask", "1",
                             "--seconds", str(a.seconds), "--play", "--test-level", LEVEL, "--user-root", run],
                            cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
    needle = re.compile(rf"[\\/]{LEVEL}\.lvl result=00000000", re.IGNORECASE)
    opened, base, end = None, None, time.monotonic() + 90
    while time.monotonic() < end and game.poll() is None and opened is None:
        time.sleep(1)
        lp = RUNS / run / "runtime.log"
        if lp.is_file():
            text = lp.read_text(errors="replace")
            opened = time.monotonic() if needle.search(text) else None
            m = re.search(r"virtual base 0x0*([0-9A-Fa-f]+),", text)
            base = m.group(1) if m else base
    if opened is None or base is None:
        row["error"] = "level did not open"
    else:
        time.sleep(a.settle)
        pid = json.loads((RUNS / run / "process.json").read_text(encoding="utf-8-sig"))["pid"]
        probe_out.mkdir()
        p1 = subprocess.run([sys.executable, str(TOOLS / "m5_memory_probe.py"), str(pid), base,
                             str(probe_out / "discovery.json"), "--regions"], cwd=ROOT, capture_output=True, text=True,
                            timeout=180)
        p2 = subprocess.run([sys.executable, str(TOOLS / "m5_script_probe.py"), str(pid), base,
                             str(probe_out / "discovery.json"), str(probe_out / "scripts")], cwd=ROOT,
                            capture_output=True, text=True, timeout=600) if p1.returncode == 0 else p1
        if p2.returncode != 0:
            row["error"] = "probe failed: " + p2.stderr.strip()[-200:]
    game.wait(timeout=a.seconds + 240)
    row["runner_exit"] = game.returncode

# 3. judge
log_text = "\n".join(p.read_text(errors="replace") for p in sorted((RUNS / run).glob("runtime*.log")))
row["plan_active"] = "M33 mods state=active" in log_text
row["served"] = sorted(set(re.findall(r"M33 mods served mod=(\S+) file=(\S+) offset=(\d+)", log_text)))
live, other_equal, other_diff = None, 0, 0
fix_ix = rm.read_script_index(GAME, "fix")
for dump in (probe_out / "scripts").glob("*.txt") if (probe_out / "scripts").is_dir() else ():
    beh, cur, scripts = None, None, {}
    for line in dump.read_text(errors="replace").splitlines():
        if line.startswith(("## normal ", "## reflex ")):
            beh = line.split(" ", 3)[3]
            scripts[beh] = []
        elif line.startswith("## macro"):
            beh = None
        elif line.startswith("# script") and beh:
            cur = []
            scripts[beh].append(cur)
        else:
            m = re.match(r"^( *)k([0-9A-F]{2}):([0-9A-F]{8})", line)
            if m and beh and cur is not None:
                cur.append((int(m.group(3), 16), int(m.group(2), 16)))
    for b, ls in scripts.items():
        fs = ix["behaviours"][b] if b in ix["behaviours"] else fix_ix["behaviours"].get(b)
        if not fs or len(fs) != len(ls):
            continue
        for j, ((fna, fn), ln) in enumerate(zip(fs, ls)):
            for i, ((fp, _, fk), (lp, lk)) in enumerate(zip(fn or (), ln)):
                if fk != lk or fk not in rm.SCRIPT_KINDS.values():
                    continue
                if b == name and j == 0 and i == k:
                    live = f"{lp:08X}"
                elif fp == lp:
                    other_equal += 1
                else:
                    other_diff += 1
row.update(live_bits=live, other_constants_equal=other_equal, other_constants_differ=other_diff)
judges = {}
for tool in ("m21_regression.py", "m22_regression.py", "m23_haptics_regression.py"):
    r = subprocess.run([sys.executable, str(TOOLS / tool), "--run", run], cwd=ROOT, capture_output=True, text=True)
    judges[tool] = r.returncode
    (work / f"{tool}.log").write_text(r.stdout + r.stderr)
row["judges"] = judges
row["pass"] = (row["plan_active"] and any(f.lower() == f"{LEVEL}.lvl" and int(o) == offset for _, f, o in row["served"])
               and live == row["new_bits"] and other_diff == 0 and other_equal > 0 and not any(judges.values())
               and "error" not in row)
(work / "result.json").write_text(json.dumps(row, indent=1) + "\n")
print(json.dumps({x: row[x] for x in row if x != "served"} | {"served": len(row["served"])}))
sys.exit(0 if row["pass"] else 1)
