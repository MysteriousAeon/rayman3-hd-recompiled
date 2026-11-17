"""E-458 (D-224): the gameplay-mod achievement gate against a genuine title-triggered unlock, hidden.

Route (reused from the release-candidate save/load runs rc2find_* / rc3_exactnames, E-2xx): title -> Start -> down ->
A x3 with a test profile that holds a save; loading it, the title itself calls XGIUserWriteAchievements for
achievement 3 (KernelState::UnlockAchievement). Nothing is forced: this tool never writes an unlock.

Each case starts from a fresh disposable profile under private/work/m9_profiles/<run>: a copy of the seed profile's
save folders only, without its `achievements/` (so the title's own call is the first unlock). The seed is read, never
written. Cases (tools/m9_license_run.py: hidden window, muted, no physical controller, scoped XAM input only):
  base  no mod plan: the runtime must store the unlock (log line + `[unlocked.3]` in the copy's toml)
  mod   the plan of a gameplay mod (`gameplay` record, D-224): the title's call must reach the gate (log
        `M33 achievement id=3 not_awarded`), and nothing is stored (no unlock line, no toml entry)
Both: M21 / M22 / M23-haptics judges. Outputs private (game-derived saves and logs).

usage: achievement_gate_ab.py TAG --plan PLAN.txt [--seed DIR] [--cases base,mod]
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TOOLS = ROOT / "tools"
RUNS = ROOT / "private" / "work" / "m6_runs"
PROFILES = ROOT / "private" / "work" / "m9_profiles"
STEPS = ROOT / "private" / "release_1.0.2" / "rc3" / "save_load.txt"
ACH_ID = 3

ap = argparse.ArgumentParser()
ap.add_argument("tag")
ap.add_argument("--plan", type=Path, required=True)
ap.add_argument("--seed", type=Path, default=PROFILES / "rc3_exactnames")
ap.add_argument("--cases", default="base,mod")
ap.add_argument("--seconds", type=int, default=110)
a = ap.parse_args()
if not re.fullmatch(r"[A-Za-z0-9_-]{1,24}", a.tag):
    ap.error("bad tag")
plan_text = a.plan.read_text(encoding="utf-8")
if not re.search(r"^gameplay \S+$", plan_text, re.M):
    raise SystemExit("the plan names no gameplay mod")
out = {}
for case in a.cases.split(","):
    run = f"e458_{a.tag}_{case}"
    prof = PROFILES / run
    if prof.exists() or (RUNS / run).exists():
        raise SystemExit(f"exists: {prof} or {RUNS / run}")
    shutil.copytree(a.seed, prof, ignore=lambda d, names: ["achievements"] if Path(d) == a.seed else [])
    env = dict(os.environ)
    env.pop("R3HD_MODS_PLAN", None)
    if case == "mod":
        env["R3HD_MODS_PLAN"] = str(a.plan.resolve())
    r = subprocess.run([sys.executable, str(TOOLS / "m9_license_run.py"), run, str(STEPS), "--license-mask", "1",
                        "--seconds", str(a.seconds), "--play", "--user-root", run], cwd=ROOT, env=env,
                       capture_output=True, text=True)
    log = "\n".join(p.read_text(errors="replace") for p in sorted((RUNS / run).glob("runtime*.log")))
    toml = prof / "achievements" / "5841123F.toml"
    stored = toml.read_text(encoding="utf-8") if toml.is_file() else ""
    judges = {t: subprocess.run([sys.executable, str(TOOLS / t), "--run", run], cwd=ROOT, capture_output=True).returncode
              for t in ("m21_regression.py", "m22_regression.py", "m23_haptics_regression.py")}
    out[case] = {
        "run": run, "runner_exit": r.returncode,
        "title_calls": len(re.findall(rf"XGIUserWriteAchievements: id={ACH_ID}\b", log)),
        "stored_line": f"Achievement unlocked: {ACH_ID:08X}" in log,
        "gate_lines": len(re.findall(rf"M33 achievement id={ACH_ID} not_awarded reason=gameplay_mods", log)),
        "gameplay_plan": "M33 mods gameplay mod=" in log, "mods_off": "M33 mods=off" in log,
        "toml_entry": f"[unlocked.{ACH_ID}]" in stored, "toml_entries": stored.count("[unlocked."),
        "haptics_policy": "M23 haptics policy=suppressed physical_pad_drivers=none" in log, "judges": judges}
b, m = out.get("base"), out.get("mod")
checks = {}
if b:
    checks["base: the title calls, the store records it (log + toml)"] = (
        b["title_calls"] >= 1 and b["stored_line"] and b["toml_entry"] and b["mods_off"] and b["gate_lines"] == 0)
if m:
    checks["mod: the title calls, the gate answers each call, nothing stored"] = (
        m["title_calls"] >= 1 and m["gate_lines"] == m["title_calls"] and not m["stored_line"]
        and not m["toml_entry"] and m["toml_entries"] == 0 and m["gameplay_plan"])
checks["all: runner exit 0, haptics line, M21 / M22 / M23 pass"] = all(
    c["runner_exit"] == 0 and c["haptics_policy"] and not any(c["judges"].values()) for c in out.values())
result = {"cases": out, "checks": checks, "pass": all(checks.values())}
(ROOT / "private" / "work" / f"e458_{a.tag}.json").write_text(json.dumps(result, indent=1) + "\n")
print(json.dumps(result, indent=1))
sys.exit(0 if result["pass"] else 1)
