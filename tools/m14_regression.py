#!/usr/bin/env python3
"""Gameplay-mechanics regression over isolated test-only level runs (M14, D-040, D-041).

    python tools/m14_regression.py TAG [NAME ...]        (no NAME = all, about nine minutes)
    python tools/m14_regression.py --list

Each scenario is one hidden run of tools/m14_scenario.py (scoped input from a config/m14 step file, read-only
actor watch) and passes when the run meets the mechanical criteria of the M13 sweep and every listed
observation occurred. The observations are what was seen on the M14 build; they are isolated test-only
evidence, not progression. Rows: private/work/m14/regression_<TAG>.json. Prints M14_REGRESSION PASS n/n.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "private" / "work" / "m14"
HOODLUM = "YAM_M_CagouSnipeBase"
BOSS = "LAU_mRefluxPremier"

# name: (level, step file, seconds, settle, watched models, expected observations)
SCENARIOS = {
    # enemy approach, ranged attack on the player, ten hits, death, respawn inside the level
    "damage_death": ("knaar_69", "idle60.txt", 70, 6, HOODLUM,
                     f"actor:{HOODLUM}:1Detecte,actor:{HOODLUM}:1VaVersObjectif,actor:{HOODLUM}:6SautMontee,"
                     f"actor:{HOODLUM}:3SnipeTir,player:PafSol,player:PafMortDebut,player:TransitionSynchro2"),
    # straight fists: the enemy's parry behaviour runs (a fist that arrives before the parry can still land)
    "straight_parried": ("knaar_69", "k69_straight.txt", 62, 6, HOODLUM, f"actor:{HOODLUM}:3SnipeCogne"),
    # lock-on, strafing and curved fists: hit reaction, hit points down, death
    "curve_defeat": ("knaar_69", "k69_curve.txt", 62, 6, HOODLUM,
                     f"player:StrafeMode,actor:{HOODLUM}:4Paf,actor:{HOODLUM}:5Mort,hp:{HOODLUM}"),
    # charged fists get through the parry
    "charged_defeat": ("knaar_69", "k69_charged.txt", 70, 6, HOODLUM,
                       f"actor:{HOODLUM}:4Paf,actor:{HOODLUM}:5Mort,hp:{HOODLUM}"),
    # photo mode freezes the world and returns
    "photo_mode": ("knaar_69", "k69_photo.txt", 55, 6, f"{HOODLUM},ODA_Director",
                   "actor:ODA_Director:PersoHelp,player:PafSol"),
    # death that restarts by loading the level again. Most shots strike the platform edge below the player, so
    # the tenth hit comes 2 .. 4 minutes in with the constant 16 ms step (M17, D-046; 36 .. 60 s with the pinned
    # polling timing, whose irregular step moved the hoodlums' firing positions, RE_NOTES "M17").
    "death_reload": ("menu_10", "idle290.txt", 300, 4, HOODLUM, "player:PafMortDebut,reloads:2"),
    # first Reflux fight: cinematic, three attack phases, the exhausted phase, player death, restart
    "boss_phases": ("knaar_60", "idle170.txt", 180, 4, f"{BOSS},Levelknaar_60",
                    f"actor:{BOSS}:Cine_Intro,actor:{BOSS}:Tornade_Poursuite,actor:{BOSS}:Serpents_GenereSeries,"
                    f"actor:{BOSS}:Central_GereHorloge,actor:{BOSS}:Central_Epuisement,player:PafSol,player:Ejecte,"
                    "player:PafMortDebut,actor:Levelknaar_60:YLT_InitLevel"),
    # final fight, flying phase: shield cycle, the player's craft is destroyed, the level re-initialises
    "final_flight": ("lept_15", "idle110.txt", 120, 4,
                     "NIN_m_RefluxLept15,NIN_m_RefLept15_Shield,NIN_m_SpaceFight,Levellept_15",
                     "actor:NIN_m_RefluxLept15:CreateShield,actor:NIN_m_RefluxLept15:FlyingAttack,"
                     "actor:NIN_m_RefLept15_Shield:Shield_On,actor:NIN_m_SpaceFight:Space_Death,"
                     "actor:Levellept_15:YLT_InitLevel"),
    # bonus minigame start menu -> help page -> game
    "bonus_start": ("raz_map", "raz_start.txt", 52, 4, "ZHT_BonusInterface,NIN_m_RazoffTraining",
                    "actor:ZHT_BonusInterface:HelpMenu,actor:ZHT_BonusInterface:WaitTillEnd,"
                    "actor:NIN_m_RazoffTraining:Mouvement"),
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("tag", nargs="?")
    ap.add_argument("names", nargs="*")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    if a.list:
        for name, (level, steps, seconds, _, _, expect) in SCENARIOS.items():
            print(f"{name}: {level}, config/m14/{steps}, {seconds} s, {len(expect.split(','))} observations")
        return 0
    if not a.tag or not re.fullmatch(r"[A-Za-z0-9]+", a.tag):
        ap.error("TAG required (letters and digits)")
    names = a.names or list(SCENARIOS)
    unknown = [n for n in names if n not in SCENARIOS]
    if unknown:
        ap.error(f"unknown scenario: {unknown}")
    WORK.mkdir(parents=True, exist_ok=True)
    rows, passed = [], 0
    for name in names:
        level, steps, seconds, settle, watch, expect = SCENARIOS[name]
        run = f"m14_{a.tag}_{name}"
        done = subprocess.run([sys.executable, str(ROOT / "tools" / "m14_scenario.py"), run, level,
                               str(ROOT / "config" / "m14" / steps), "--seconds", str(seconds), "--settle", str(settle),
                               "--watch", watch, "--expect", expect], cwd=ROOT, capture_output=True, text=True)
        line = next((l for l in done.stdout.splitlines() if l.startswith("M14_SCENARIO")), "M14_SCENARIO FAIL (no result)")
        result_path = WORK / f"scenario_{run}.json"
        result = json.loads(result_path.read_text(encoding="utf-8")) if result_path.is_file() else {}
        ok = done.returncode == 0 and result.get("pass") is True
        passed += ok
        rows.append({"scenario": name, "run": run, "level": level, "steps": steps, "pass": ok,
                     "expect": result.get("expect"), "reasons": result.get("reasons"),
                     "executable_sha256": (result.get("sweep_row") or {}).get("executable_sha256")})
        (WORK / f"regression_{a.tag}.json").write_text(json.dumps(rows, indent=1) + "\n", encoding="utf-8")
        print(f"{name}: {line}", flush=True)
    print(f"M14_REGRESSION {'PASS' if passed == len(names) else 'FAIL'} {passed}/{len(names)}")
    return 0 if passed == len(names) else 1


if __name__ == "__main__":
    raise SystemExit(main())
