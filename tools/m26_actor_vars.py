#!/usr/bin/env python3
"""M26: designer variables and hit points of every live actor of one model, in an isolated test-only level run.

    python tools/m26_actor_vars.py RUN LEVEL MODEL [--vars 4,5] [--seconds 60] [--frames S S ...]

One hidden run (D-040 entry, muted, no controller, no input): after the level opens the actors are discovered
(`m5_memory_probe.py`), and for each live actor of MODEL the tool reads, without writing anything: position,
behaviour, hit points and their maximum (StdGame +0x1D / +0x1E, RE_NOTES "M14"), and the named designer
variables as raw bytes with their type word (the rank switches of a Hoodlum are variables 4 and 5, RE_NOTES
"M25"). --frames asks for private traced frames that many seconds after the read (`R3HD_M22_DRAW_TRACE=1`, at
most 8), so the skin a rank selects can be read from the draw trace of the same run.
Output: private/work/m26/actors_<RUN>.json and one line per actor. An isolated run is never progression.
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import m12_save_entry as m12  # noqa: E402
import m19_campaign_check as m19  # noqa: E402
from m5_live import Actor  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
WORK = ROOT / "private" / "work" / "m26"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("level")
    ap.add_argument("model")
    ap.add_argument("--vars", default="4,5")
    ap.add_argument("--seconds", type=int, default=60)
    ap.add_argument("--frames", type=float, nargs="*", default=[])
    ap.add_argument("--material", help="guest address (hex) of a visual material named by SkinMaterial in the "
                                       "model's script: its texture list and current entry are read as well")
    a = ap.parse_args()
    wanted = [int(x) for x in a.vars.split(",")]
    rows, material = [], {}

    def beside(run_dir: Path, game, log) -> list:
        if not m19.wait_for_log(run_dir, f"{a.level}\\{a.level}.lvl result=00000000", game, 90):
            return [f"{a.level} did not open"]
        time.sleep(6)
        pid, base = m19.attach(run_dir)
        actors = run_dir / f"actors_{a.level}.json"
        subprocess.run([sys.executable, str(TOOLS / "m5_memory_probe.py"), str(pid), base, str(actors), "--regions"],
                       cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=180)
        process = m19.Process(pid, int(base, 16))
        for record in json.loads(actors.read_text(encoding="utf-8"))["actors"]:
            try:
                actor = Actor(process, int(record["so"], 16))
                if not actor.alive() or actor.model != a.model:
                    continue
                dsg = actor.dsg()
                mem = process.words(actor.mind[3], 3)
                var = process.words(process.words(mem[0], 1)[0], 4)
                types = [process.words(var[1] + i * 16, 2)[1] for i in range(var[3] >> 24)]
                std = process.read(actor.std + 0x1D, 2)
                values = {}
                for n in wanted:
                    if n < len(dsg):
                        buf, off = dsg[n]
                        end = min([o for _, o in dsg if o > off] + [len(buf)])
                        values[str(n)] = dict(type=types[n], bytes=buf[off:end].hex())
                rows.append(dict(so=record["so"], perso=record.get("perso"), position=[round(x, 1) for x in actor.position()],
                                 comport=actor.comport(), reflex=actor.comport(True), hit_points=std[0], hit_points_max=std[1], variables=values))
            except (TypeError, ValueError, IndexError, OSError, AttributeError) as exc:
                rows.append(dict(so=record.get("so"), error=f"{type(exc).__name__}: {exc}"))
        if a.material:                                   # texture list head +0x48, current +0x4C (RE_NOTES "M25")
            vm = int(a.material, 16)
            name = lambda t: process.cstr(t + 0x4A) if t else None
            head, current = process.words(vm + 0x48, 2)
            nodes, node = [], head
            while node and len(nodes) < 8:
                tex, _, nxt = process.words(node, 3)
                nodes.append(dict(node=f"{node:08X}", texture=name(tex)))
                node = nxt if nxt != head else 0
            cur = process.words(current, 1)[0] if current else 0
            layer0 = process.words(vm + 0x68, 1)[0]
            material.update(address=a.material.upper(), list=nodes, current_node=f"{current:08X}",
                            current_texture=name(cur), layer0_texture=name(layer0))
        for request, pause in enumerate(a.frames, 1):
            time.sleep(pause)
            before = len(list(run_dir.glob("m22_draws_*.bin")))
            (run_dir / "frame.request").write_text(f"{request}\n", encoding="ascii")
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline and len(list(run_dir.glob("m22_draws_*.bin"))) == before:
                time.sleep(0.1)
        return []

    steps = ROOT / "config" / "m14" / "idle60.txt"
    reasons = m19.hidden_run(a.run, steps, max(a.seconds, 75), test_level=a.level,
                             env={"R3HD_M22_DRAW_TRACE": "1"} if a.frames else None, beside=beside)
    WORK.mkdir(parents=True, exist_ok=True)
    out = WORK / f"actors_{a.run}.json"
    out.write_text(json.dumps(dict(run=a.run, level=a.level, model=a.model, actors=rows, material=material, reasons=reasons), indent=1) + "\n")
    for r in rows:
        print(json.dumps(r))
    if material:
        print(json.dumps(material))
    print("M26_ACTOR_VARS", json.dumps(dict(run=a.run, actors=len(rows), reasons=reasons, out=str(out.relative_to(ROOT)))))
    return 1 if reasons else 0


if __name__ == "__main__":
    sys.exit(main())
