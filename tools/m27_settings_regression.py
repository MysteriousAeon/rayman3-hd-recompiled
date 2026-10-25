"""M27 (D-060): presets regression. Starts no game process.

1. Resolver: defaults, each preset, custom overrides, precedence, and every refusal rule.
2. Consistency: play.ps1's parameter defaults are the vanilla column of config/settings/registry.json and its
   ValidateSets are the registry's value lists (the launcher without -Preset stays exactly vanilla).
3. play.ps1 -DryRun (prints, starts nothing; skipped when the executable has not been built): legacy launch,
   presets, explicit parameter over preset, a settings file, refusals.

usage: m27_settings_regression.py
"""
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import r3hd_settings as rs  # noqa: E402

PLAY = ROOT / "tools" / "play.ps1"
EXE = ROOT / "private" / "work" / "rex" / "out" / "build" / "win-amd64-release" / "r3hd.exe"
checks = failures = skipped = 0


def check(cond, label):
    global checks, failures
    checks += 1
    if not cond:
        failures += 1
        print("FAIL", label)


def refused(fn, code):
    try:
        fn()
    except rs.Refused as e:
        return e.code == code
    return False


reg = rs.load_registry()
S = reg["settings"]

# --- 1. resolver ----------------------------------------------------------------------------------------------
v = rs.resolve(reg)
check(v["preset"] == "vanilla" and all(v["values"][k] == S[k]["vanilla"] for k in S), "no preset = vanilla")
check(all(src == "vanilla" for src in v["sources"].values()) and not v["warnings"], "vanilla: every source vanilla, no note")
h = rs.resolve(reg, "hdplus")
check(h["values"]["layer_coords"] == "separate" and h["sources"]["layer_coords"] == "hdplus", "hdplus: layer_coords separate")
check(h["values"]["texture_orient"] == "corrected" and any("texture_orient" in w and "provisional" in w for w in h["warnings"]),
      "hdplus: texture_orient corrected, provisionally (M43, D-080), with a note")
check(all(h["values"][k] == S[k]["vanilla"] for k in S if S[k]["category"] in ("mandatory", "platform")),
      "hdplus: mandatory and platform settings equal vanilla")
check(rs.resolve(reg, "vanilla")["values"]["layer_coords"] == "original", "vanilla: layer_coords original")
for key, s in S.items():
    if s["category"] == "mandatory":
        check(s["vanilla"] == s["hdplus"] and s.get("diagnostic_values"), f"{key}: mandatory, same everywhere, diagnostics listed")
check(S["revisit"]["vanilla"] == "fixed" and S["pacing"]["vanilla"] == "precise", "M18 / M17 policies preserved (D-047, D-046)")
c = rs.resolve(reg, settings={"schema": 1, "preset": "custom", "base": "hdplus", "overrides": {"texture_orient": "corrected"}})
check(c["values"]["texture_orient"] == "corrected" and c["sources"]["texture_orient"] == "custom"
      and c["values"]["layer_coords"] == "separate", "custom on hdplus: override plus base")
c2 = rs.resolve(reg, settings={"schema": 1, "preset": "custom", "overrides": {"render_scale": "1", "cursor": "visible"}})
check(c2["base"] == "vanilla" and c2["values"]["render_scale"] == "1" and c2["values"]["cursor"] == "visible", "custom default base vanilla")
e = rs.resolve(reg, "hdplus", explicit={"layer_coords": "original"})
check(e["values"]["layer_coords"] == "original" and e["sources"]["layer_coords"] == "explicit" and e["label"] == "hdplus+explicit",
      "explicit parameter wins over the preset and is labelled")
e2 = rs.resolve(reg, settings={"schema": 1, "preset": "custom", "overrides": {"layer_coords": "separate"}},
                explicit={"layer_coords": "original"})
check(e2["values"]["layer_coords"] == "original", "explicit wins over a settings file")
d = rs.resolve(reg, "vanilla", explicit={"revisit": "original"})
check(d["values"]["revisit"] == "original" and d["diagnostic"] == ["revisit"] and d["warnings"], "explicit mandatory value = diagnostic, warned")
same = rs.resolve(reg, "hdplus", explicit={"layer_coords": "separate"})
check(same["label"] == "hdplus" and same["sources"]["layer_coords"] == "hdplus", "explicit equal to the preset changes nothing")
check(rs.parse_pairs(["LayerCoords=separate"], reg, "t") == {"layer_coords": "separate"}, "launcher parameter names accepted")
cases = [
    (lambda: rs.resolve(reg, "ultra"), "UNKNOWN_PRESET"),
    (lambda: rs.resolve(reg, settings={"schema": 1, "preset": "custom", "base": "custom"}), "UNKNOWN_PRESET"),
    (lambda: rs.resolve(reg, settings={"schema": 1, "preset": "hdplus", "overrides": {"cursor": "visible"}}), "OVERRIDES_NEED_CUSTOM"),
    (lambda: rs.resolve(reg, settings={"schema": 1, "preset": "vanilla", "base": "hdplus"}), "OVERRIDES_NEED_CUSTOM"),
    (lambda: rs.resolve(reg, settings={"schema": 1, "preset": "custom", "overrides": {"revisit": "original"}}), "MANDATORY_SETTING"),
    (lambda: rs.resolve(reg, settings={"schema": 1, "preset": "custom", "overrides": {"pacing": "pinned"}}), "MANDATORY_SETTING"),
    (lambda: rs.resolve(reg, settings={"schema": 1, "preset": "custom", "overrides": {"bloom": "on"}}), "UNKNOWN_SETTING"),
    (lambda: rs.resolve(reg, settings={"schema": 1, "preset": "custom", "overrides": {"render_scale": "4"}}), "INVALID_VALUE"),
    (lambda: rs.resolve(reg, settings={"schema": 1, "preset": "custom", "overrides": ["x"]}), "SETTINGS_INVALID"),
    (lambda: rs.resolve(reg, "vanilla", settings={"schema": 1, "preset": "hdplus"}), "PRESET_CONFLICT"),
    (lambda: rs.resolve(reg, explicit={"texture_orient": "upside"}), "INVALID_VALUE"),
    (lambda: rs.parse_pairs(["layer_coords"], reg, "t"), "INVALID_PAIR"),
    (lambda: rs.make_settings(reg, "hdplus", pairs=["texture_orient=corrected"]), "OVERRIDES_NEED_CUSTOM"),  # M30: cursor is a preference
    (lambda: rs.make_settings(reg, "custom", pairs=["revisit=original"]), "MANDATORY_SETTING"),
]
for i, (fn, code) in enumerate(cases):
    check(refused(fn, code), f"refusal {i}: {code}")
# Experimental rule, exercised on a registry copy with one synthetic experimental setting.
exp = json.loads(json.dumps(reg))
exp["settings"]["x_test"] = {"category": "experimental", "values": ["off", "on"], "vanilla": "off", "hdplus": "off", "why": "test"}
check(refused(lambda: rs.resolve(exp, settings={"schema": 1, "preset": "custom", "overrides": {"x_test": "on"}}),
              "EXPERIMENTAL_NOT_ALLOWED"), "experimental value needs allow_experimental")
check(refused(lambda: rs.resolve(exp, settings={"schema": 1, "preset": "custom", "allow_experimental": "false",
                                              "overrides": {"x_test": "on"}}), "EXPERIMENTAL_NOT_ALLOWED"),
      "allow_experimental must be JSON true, not a truthy string")
check(rs.resolve(exp, settings={"schema": 1, "preset": "custom", "allow_experimental": True, "overrides": {"x_test": "on"}})
      ["values"]["x_test"] == "on", "experimental value with allow_experimental")
with tempfile.TemporaryDirectory() as tmp:
    t = Path(tmp)
    bad_reg = json.loads((ROOT / "config/settings/registry.json").read_text(encoding="utf-8"))
    bad_reg["settings"]["revisit"]["hdplus"] = "original"
    (t / "r.json").write_text(json.dumps(bad_reg), encoding="utf-8")
    check(refused(lambda: rs.load_registry(t / "r.json"), "REGISTRY_INVALID"), "registry: a mandatory setting differing by preset is refused")
    bad_reg["settings"]["revisit"]["hdplus"] = "fixed"
    bad_reg["schema"] = 2
    (t / "r.json").write_text(json.dumps(bad_reg), encoding="utf-8")
    check(refused(lambda: rs.load_registry(t / "r.json"), "REGISTRY_SCHEMA"), "registry: unknown schema refused")
    for name, body, code in (("newer.json", {"schema": 4, "preset": "vanilla"}, "SETTINGS_NEWER"),  # M32 reads 1, 2 and 3
                             ("noschema.json", {"preset": "vanilla"}, "SETTINGS_INVALID"),
                             ("field.json", {"schema": 1, "preset": "vanilla", "colour": 1}, "SETTINGS_INVALID")):
        (t / name).write_text(json.dumps(body), encoding="utf-8")
        check(refused(lambda: rs.load_settings_file(t / name), code), f"settings file {name}: {code}")
    (t / "broken.json").write_text("{", encoding="utf-8")
    check(refused(lambda: rs.load_settings_file(t / "broken.json"), "SETTINGS_UNREADABLE"), "settings file: broken JSON")
    # write -> read round trip through the CLI, and a refused write leaves the file as it was.
    f = t / "settings.json"
    run = lambda *a: subprocess.run([sys.executable, str(ROOT / "tools/r3hd_settings.py"), *a], capture_output=True, text=True)
    check(run("write", str(f), "--preset", "custom", "--base", "hdplus", "--set", "TextureOrient=corrected").returncode == 0,
          "CLI write custom")
    r = run("resolve", "--settings", str(f))
    out = json.loads(r.stdout)
    check(r.returncode == 0 and out["values"]["texture_orient"] == "corrected" and out["values"]["layer_coords"] == "separate",
          "CLI resolve of the written file")
    before = f.read_bytes()
    check(run("write", str(f), "--preset", "custom", "--set", "revisit=original").returncode == 2 and f.read_bytes() == before,
          "CLI refused write leaves the file unchanged")
    r = run("resolve", "--preset", "ultra")
    check(r.returncode == 2 and json.loads(r.stdout)["code"] == "UNKNOWN_PRESET", "CLI refusal exit code 2")

# --- 2. play.ps1 consistency ----------------------------------------------------------------------------------
play = PLAY.read_text(encoding="utf-8-sig")
for key, s in S.items():
    if not s.get("launcher"):
        check(s.get("ui") == "hidden" and rs.scope(s) == "preference",
              f"{key}: Settings-only preference has no game-launch parameter")
        continue
    if "range" in s:  # D-108: an integer preference is an [int] parameter over the same range
        m = re.search(r"\[ValidateRange\((\d+), (\d+)\)\]\[int\]\$" + s["launcher"] + r" = (\d+)", play)
        check(m is not None and [int(m.group(1)), int(m.group(2))] == [s["range"]["min"], s["range"]["max"]]
              and m.group(3) == s["vanilla"], f"play.ps1: -{s['launcher']} declared over the registry range, default vanilla")
        continue
    m = re.search(r"\[ValidateSet\(([^)]*)\)\]\[string\]\$" + s["launcher"] + r" = '([^']*)'", play)
    check(m is not None, f"play.ps1: -{s['launcher']} declared")
    if m:
        values = re.findall(r"'([^']*)'", m.group(1))
        check(m.group(2) == s["vanilla"], f"play.ps1: -{s['launcher']} default {m.group(2)!r} = vanilla {s['vanilla']!r}")
        check(sorted(values) == sorted(s["values"]),f"play.ps1: -{s['launcher']} values {values} = registry {s['values']}")
check("[ValidateSet('', 'vanilla', 'hdplus', 'custom')][string]$Preset = ''," in play, "play.ps1: -Preset, default none (= vanilla)")
block = play[play.index("# --- presets (M27"):play.index("# --- preflight")]
mapping = dict(re.findall(r"(\w+) = '(\w+)'", block[block.index("$settingParams"):block.index("$resolverArgs")]))
check(mapping == {s["launcher"]: k for k, s in S.items() if s.get("launcher")},
      "play.ps1: the parameter map covers exactly the runtime settings")
check("$PSBoundParameters.ContainsKey($_)" in block and "'r3hd_settings.py'" in block and block.count("Set-Variable") == 1,
      "play.ps1: explicit parameters are passed on; the resolver sets the rest")
check("preset = $presetLabel" in play and play.count("preset = $presetLabel") == 2, "play.ps1: the preset is recorded with the session")
check("python" not in play[:play.index("# --- presets (M27")].split("param(")[1], "play.ps1: no Python before a preset is asked for")

# --- 3. play.ps1 -DryRun -------------------------------------------------------------------------------------
def dry(*args):
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(PLAY), "-DryRun", *args],
                       capture_output=True, text=True, cwd=ROOT)
    lines = dict(re.findall(r"^(\w[\w ]*?)\s*: (.*)$", r.stdout, re.M))
    return r.returncode, lines, r.stdout + r.stderr


if EXE.exists() and "--skip-runtime-dry-run" not in sys.argv[1:]:
    with tempfile.TemporaryDirectory() as tmp:
        code, out, _ = dry()
        check(code == 0 and out.get("preset") == "vanilla (launcher defaults)" and out.get("layer coord") == "original"
              and out.get("texture ori") == "original" and out.get("revisit") == "fixed", "dry run: legacy launch = vanilla")
        code, out, _ = dry("-Preset", "hdplus")
        check(code == 0 and out.get("preset") == "hdplus" and out.get("layer coord") == "separate"
              and out.get("texture ori") == "corrected" and out.get("preset note", "").startswith("texture_orient"), "dry run: hdplus")
        code, out, _ = dry("-Preset", "hdplus", "-TextureOrient", "original")
        check(code == 0 and out.get("texture ori") == "original" and out.get("preset") == "hdplus+explicit",
              "dry run: the provisional HD+ correction is turned off by its parameter (M43)")
        code, out, _ = dry("-Preset", "hdplus", "-LayerCoords", "original")
        check(code == 0 and out.get("layer coord") == "original" and out.get("preset") == "hdplus+explicit", "dry run: explicit over preset")
        code, out, _ = dry("-Preset", "hdplus", "-WaterLayers", "original")
        check(code == 0 and out.get("layer coord") == "original", "dry run: the old alias still counts as explicit")
        f = Path(tmp) / "s.json"
        f.write_text(json.dumps({"schema": 1, "preset": "custom", "base": "hdplus", "overrides": {"texture_orient": "corrected"}}),
                     encoding="utf-8")
        code, out, _ = dry("-SettingsFile", str(f))
        check(code == 0 and out.get("preset") == "custom" and out.get("texture ori") == "corrected"
              and out.get("layer coord") == "separate", "dry run: settings file")
        code, out, _ = dry("-Preset", "vanilla", "-Revisit", "original")
        check(code == 0 and out.get("revisit") == "original" and "diagnostic" in out.get("preset note", ""), "dry run: diagnostic noted")
        f.write_text(json.dumps({"schema": 1, "preset": "custom", "overrides": {"pacing": "pinned"}}), encoding="utf-8")
        code, out, text = dry("-SettingsFile", str(f))
        check(code != 0 and "MANDATORY_SETTING" in text and "DRY RUN" not in text, "dry run: a refused settings file stops the launch")
        code, out, text = dry("-Preset", "ultra")
        check(code != 0, "dry run: unknown preset refused by the parameter set")
else:
    skipped += 9
    print("SKIP runtime dry runs: explicit skip or missing build")

print(f"M27_SETTINGS_REGRESSION {'PASS' if not failures else 'FAIL'} checks={checks} failures={failures} skipped={skipped}")
sys.exit(1 if failures else 0)
