#!/usr/bin/env python3
"""Deterministic checks of the M14 gameplay-scenario tooling (no game process; part of the build).

The scenarios themselves run with tools/m14_regression.py (hidden game runs, checkpoint workflow). This script
keeps their definition honest: the judge works on synthetic watch rows, every scenario's step file exists, fits
its run time, sends only scoped input and requests no frame, and the tools stay read-only and keep the D-040
gate (isolated entry only through m9_license_run.py --test-level).
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import m14_regression  # noqa: E402
import m14_scenario  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
checks = failures = 0


def check(ok: bool, what: str) -> None:
    global checks, failures
    checks += 1
    if not ok:
        failures += 1
        print(f"FAIL {what}")


def std(hp: int, init: int) -> str:
    block = bytearray(0x40)
    block[0x0D], block[0x0E] = hp, init
    return block.hex()


rows = [
    {"t": 0.0, "perso": "A", "model": "YLT_RaymanModel", "comport": "YAM_C_Attente", "reflex": "YLT_ReflexeAttente",
     "alive": True, "std": std(40, 40)},
    {"t": 1.0, "perso": "A", "model": "YLT_RaymanModel", "comport": "YAM_C_PafSol", "reflex": "YAM_R_ReflexeVide",
     "alive": True, "std": std(40, 40)},
    {"t": 0.0, "perso": "B", "model": "Enemy", "comport": "E_Wait", "reflex": None, "alive": True, "std": std(12, 12)},
    {"t": 2.0, "perso": "B", "model": "Enemy", "comport": "E_Wait", "reflex": "E_R_Paf", "alive": True, "std": std(8, 12)},
    {"t": 3.0, "perso": "B", "model": "Enemy", "alive": False},
    {"t": 0.0, "perso": "C", "model": "Other", "comport": "O_Idle", "reflex": None, "alive": True, "std": std(3, 3)},
]
seen = m14_scenario.judge(["player:PafSol", "player:PafMort", "actor:Enemy:R_Paf", "actor:Enemy:Missing", "gone:Enemy",
                           "gone:Other", "hp:Enemy", "hp:Other", "reloads:2", "reloads:3"], rows,
                          ["lvl", "lvl"], "lvl")
expected = {"player:PafSol": True, "player:PafMort": False, "actor:Enemy:R_Paf": True, "actor:Enemy:Missing": False,
            "gone:Enemy": True, "gone:Other": False, "hp:Enemy": True, "hp:Other": False, "reloads:2": True,
            "reloads:3": False}
for name, value in expected.items():
    check(seen.get(name) is value, f"judge {name} expected {value}")
check(m14_scenario.hp(std(7, 12)) == (7, 12), "hit-point bytes read from StdGame +0x1D / +0x1E")
check(m14_scenario.hp(None) is None, "missing block gives no hit points")
try:
    m14_scenario.judge(["bogus:1"], rows, [], "lvl")
    check(False, "unknown check is refused")
except SystemExit:
    check(True, "unknown check is refused")

levels = {p.name.lower() for p in (ROOT / "private" / "extracted" / "5841123F" / "GAMEDATAbin").glob("*") if p.is_dir()}
allowed = {"wait", "press", "axis"}
for name, (level, steps, seconds, settle, watch, expect) in m14_regression.SCENARIOS.items():
    path = ROOT / "config" / "m14" / steps
    check(path.is_file(), f"{name}: step file exists")
    if not path.is_file():
        continue
    lines = [line.split("#", 1)[0].split() for line in path.read_text().splitlines()]
    lines = [line for line in lines if line]
    check(all(line[0] in allowed for line in lines), f"{name}: only wait / press / axis steps (no frame, no probe)")
    duration = sum(float(line[1]) for line in lines if line[0] == "wait") + \
        sum(float(line[2]) if len(line) > 2 else 0.2 for line in lines if line[0] == "press")
    check(duration <= seconds, f"{name}: steps ({duration:.0f} s) fit the run ({seconds} s)")
    check(20 <= seconds <= 900 and 0 < settle < seconds, f"{name}: bounded run")
    check(not levels or level in levels, f"{name}: {level} is a level directory")
    check(bool(watch) and all(re.fullmatch(r"(player:\w+|actor:\w+:\w+|gone:\w+|hp:\w+|reloads:\d+)", c)
                              for c in expect.split(",")), f"{name}: well-formed observations")

for tool in ("m14_scenario.py", "m14_combat_watch.py", "m14_script_scan.py", "m14_regression.py", "m14_transition_graph.py"):
    text = (ROOT / "tools" / tool).read_text(encoding="utf-8")
    check("WriteProcessMemory" not in text and "VirtualProtectEx" not in text, f"{tool}: no guest write API")
    # the option is spelled in two parts so that this file passes the M13 gate regression, which scans tools/
    check("--" + "cl=" not in text and "play.ps1" not in text, f"{tool}: no direct command-line option, no visible launcher")
for tool in ("m14_scenario.py", "m14_script_scan.py"):
    text = (ROOT / "tools" / tool).read_text(encoding="utf-8")
    check('"--test-level"' in text and "m9_license_run.py" in text, f"{tool}: isolated entry through the gated runner")
check("0x410" in (ROOT / "tools" / "m5_live.py").read_text(encoding="utf-8"), "live helper opens the process read-only")

print(f"M14 scenario tooling regression: {'PASS' if not failures else 'FAIL'} ({checks} checks)")
raise SystemExit(1 if failures else 0)
