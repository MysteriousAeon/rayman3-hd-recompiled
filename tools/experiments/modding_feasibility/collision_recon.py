"""E-462 reconnaissance (exploratory, not judged): one hidden intro_15 start without mods, recording where Rayman is
and how he moves (position, behaviour, every 0.2 s) and the positions of the NIK_mSpoPont bridges, to find whether
an unattended contact between Rayman and a collision-bearing actor exists. Read-only (m5_live); outputs under
private/work/e462/recon_<TAG>/.

usage: collision_recon.py TAG [--seconds 200] [--level intro_15]
"""
import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))
RUNS = ROOT / "private" / "work" / "m6_runs"

ap = argparse.ArgumentParser()
ap.add_argument("tag")
ap.add_argument("--seconds", type=int, default=200)
ap.add_argument("--level", default="intro_15")
a = ap.parse_args()
from m5_live import Actor, Process  # noqa: E402

run = f"e462_recon_{a.tag}"
work = ROOT / "private" / "work" / "e462" / f"recon_{a.tag}"
if work.exists() or (RUNS / run).exists():
    raise SystemExit("exists")
work.mkdir(parents=True)
(work / "steps.txt").write_text(f"wait {a.seconds - 8}\n", encoding="ascii")
samples, row = [], {"run": run}
with (work / "driver.log").open("w") as log:
    game = subprocess.Popen([sys.executable, str(TOOLS / "m9_license_run.py"), run, str(work / "steps.txt"),
                             "--license-mask", "1", "--seconds", str(a.seconds), "--play", "--test-level", a.level,
                             "--user-root", run], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
    needle = re.compile(rf"[\\/]{a.level}\.lvl result=00000000", re.IGNORECASE)
    opened, base, end = None, None, time.monotonic() + 90
    while time.monotonic() < end and game.poll() is None and opened is None:
        time.sleep(0.5)
        lp = RUNS / run / "runtime.log"
        if lp.is_file():
            text = lp.read_text(errors="replace")
            opened = time.monotonic() if needle.search(text) else None
            m = re.search(r"virtual base 0x0*([0-9A-Fa-f]+),", text)
            base = m.group(1) if m else base
    if opened and base:
        pid = json.loads((RUNS / run / "process.json").read_text(encoding="utf-8-sig"))["pid"]
        disc = work / "discovery.json"
        subprocess.run([sys.executable, str(TOOLS / "m5_memory_probe.py"), str(pid), base, str(disc), "--regions"],
                       cwd=ROOT, capture_output=True, text=True, timeout=180)
        process = Process(pid, int(base, 16))
        ray, bridges = None, []
        for x in json.loads(disc.read_text(encoding="utf-8"))["actors"]:
            try:
                act = Actor(process, int(x["so"], 16))
            except Exception:
                continue
            if act.model == "YLT_RaymanModel" and ray is None:
                ray = act
            elif act.model == "NIK_mSpoPont":
                bridges.append(act)
        row["bridges"] = [list(b.position()) for b in bridges]
        t_end = time.monotonic() + a.seconds - 40
        while ray and time.monotonic() < t_end and process.running():
            try:
                samples.append({"t": round(time.monotonic() - opened, 2), "pos": ray.position(), "beh": ray.comport()})
            except Exception:
                break
            time.sleep(0.2)
    game.wait(timeout=a.seconds + 240)
(work / "samples.json").write_text(json.dumps(samples) + "\n")
(work / "row.json").write_text(json.dumps(row, indent=1) + "\n")
print(json.dumps({"samples": len(samples), "bridges": row.get("bridges")}))
