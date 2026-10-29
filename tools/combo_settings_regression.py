#!/usr/bin/env python3
"""Focused Combo Meter Settings regression on synthetic installations and private desktops.

The default run exercises the real Settings window, saving and reopening it. --engine-only skips the native window.
All installation data and persisted test configurations are synthetic; this script never starts the game.
"""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))
import m30_launcher_regression as launcher  # noqa: E402
import r3hd_installer as engine  # noqa: E402
import r3hd_settings as settings  # noqa: E402
import r3hd_ui_locale as locale  # noqa: E402

KEY = "combo_close"
LANGUAGE = "game_language"
UNRELATED = "texture_orient"
SNAPSHOTS = ROOT / "private" / "work" / "combo_settings_cases"


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--engine-only", action="store_true", help="skip the built native Settings window")
    args = ap.parse_args()

    out = ROOT / "private" / "work" / "combo_settings_regression" / datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    out.mkdir(parents=True)
    checks = []

    def check(name, condition, detail=None):
        checks.append({"name": name, "pass": bool(condition), "detail": detail})

    reg = settings.load_registry()
    entry = reg["settings"][KEY]

    # Registry and resolver: current and legacy settings files share one source of truth.
    check("registry: visible preset-scoped Combo Meter Animation with the requested explanation",
          settings.scope(entry) == "preset" and entry["category"] == "enhancement"
          and entry.get("ui", "shown") == "shown" and entry["group"] == "corrections"
          and entry["label"] == "Combo Meter Animation"
          and entry["help"] == "Adds a smooth exit animation to the Combo Meter during the final second of a combo."
          and entry["values"] == ["original", "delayed"]
          and entry["value_labels"] == {"original": "Off (as on Xbox 360)", "delayed": "On"}
          and entry["vanilla"] == "original" and entry["hdplus"] == "delayed")

    vanilla = settings.resolve(reg, preset="vanilla")
    hdplus = settings.resolve(reg, preset="hdplus")
    check("fixed presets: Vanilla resolves original and HD+ resolves delayed",
          vanilla["values"][KEY] == "original" and hdplus["values"][KEY] == "delayed"
          and vanilla["sources"][KEY] == "vanilla" and hdplus["sources"][KEY] == "hdplus")

    for schema in (1, 2, 3, 4):
        for preset, expected in (("vanilla", "original"), ("hdplus", "delayed")):
            legacy = {"schema": schema, "preset": preset}
            if schema >= 2:
                legacy["preferences"] = {LANGUAGE: "fr"}
            resolved = settings.resolve(reg, settings=legacy)
            check(f"legacy schema {schema} {preset}: absent Combo choice keeps preset default and file unchanged",
                  resolved["values"][KEY] == expected and KEY not in legacy.get("overrides", {})
                  and KEY not in legacy.get("preferences", {}))

    old_custom = {"schema": 1, "preset": "custom", "base": "hdplus",
                  "overrides": {"layer_coords": "original", "game_language": "fr"}}
    old_custom_before = json.loads(json.dumps(old_custom))
    old_values = settings.resolve(reg, settings=old_custom)
    check("legacy Custom: missing option defaults to HD+ while existing correction and French language remain",
          old_values["values"][KEY] == "delayed" and old_values["values"]["layer_coords"] == "original"
          and old_values["values"][LANGUAGE] == "fr" and old_custom == old_custom_before)

    for base in ("vanilla", "hdplus"):
        base_doc = {"schema": 2, "preset": base, "preferences": {LANGUAGE: "fr", "render_scale": "2"}}
        base_values = settings.resolve(reg, settings=base_doc)["values"]
        for value in ("original", "delayed"):
            custom = settings.make_settings(reg, "custom", base,
                                            [f"{KEY}={value}", f"{LANGUAGE}=fr", "render_scale=2"],
                                            keep_preferences={LANGUAGE: "fr", "render_scale": "2"})
            resolved = settings.resolve(reg, settings=custom)
            check(f"Custom on {base}: {value} is independently selectable and saved as an override",
                  custom["preset"] == "custom" and custom["base"] == base
                  and custom["overrides"].get(KEY) == value and resolved["values"][KEY] == value
                  and resolved["sources"][KEY] == "custom" and resolved["values"][LANGUAGE] == "fr"
                  and resolved["values"]["render_scale"] == "2"
                  and all(resolved["values"][k] == base_values[k] for k in reg["settings"] if k not in (KEY, LANGUAGE, "render_scale")))

    for fn, code, label in (
            (lambda: settings.make_settings(reg, "vanilla", pairs=[f"{KEY}=delayed"]),
             "OVERRIDES_NEED_CUSTOM", "a fixed Vanilla file cannot hold a Custom override"),
            (lambda: settings.resolve(reg, settings={"schema": 3, "preset": "custom", "base": "hdplus",
                                                       "overrides": {KEY: "fade"}}),
             "INVALID_VALUE", "an unknown Combo value is refused"),
            (lambda: settings.resolve(reg, settings={"schema": 3, "preset": "custom", "base": "hdplus",
                                                       "overrides": {"unknown_setting": "on"}}),
             "UNKNOWN_SETTING", "an unknown setting is refused"),
            (lambda: settings.load_settings_file(out / "unsupported.json"),
             "SETTINGS_UNREADABLE", "an unreadable settings file is refused safely")):
        if label.startswith("an unreadable"):
            (out / "unsupported.json").write_text('{"schema":5,"preset":"custom"}', encoding="utf-8")
            fn = lambda: settings.load_settings_file(out / "unsupported.json")
            code = "SETTINGS_NEWER"
        try:
            fn()
            refused = False
        except settings.Refused as exc:
            refused = exc.code == code
        check(label, refused)

    if not args.engine_only:
        if not launcher.LAUNCHER.is_file():
            check("native Settings window: built launcher exists", False, str(launcher.LAUNCHER))
        else:
            check("native Settings regression uses the built launcher on a private desktop", True)
            saved_env = {k: os.environ.get(k) for k in engine.HOOKS}
            sys32 = out / "system32"
            sys32.mkdir()
            for name in engine.VC_RUNTIME:
                (sys32 / name).write_bytes(b"synthetic-runtime-presence")
            os.environ.update(R3HD_INSTALL_SYSTEM32=str(sys32), R3HD_INSTALL_FAKE_RUNNING="0",
                              R3HD_INSTALL_FAKE_LAUNCHER="0")
            snapshots = {}
            try:
                payload, tree, releases = engine.make_fixture(out)
                cases = (
                    ("vanilla", "vanilla", "vanilla", "original", None),
                    ("hdplus", "hdplus", "hdplus", "delayed", None),
                    ("custom_on", "vanilla", "vanilla", "delayed", "corrected"),
                    ("custom_off", "hdplus", "hdplus", "original", "original"),
                )
                for name, initial_preset, final_preset, choice, unrelated in cases:
                    home = out / ("home_" + name)
                    engine.install(home, payload, tree, initial_preset, releases=releases,
                                   ui_language="en", log=lambda *_: None)
                    engine.set_option(home, LANGUAGE, "fr")
                    before = settings.resolve(reg, settings=launcher.settings(home))["values"]
                    target_custom = name.startswith("custom_")
                    commands = ["page settings", "dump initial"]
                    if name == "hdplus":
                        commands.append("shot combo_row_en")
                    if name == "vanilla":
                        commands += ["profile custom", "profile vanilla"]
                    elif name == "hdplus":
                        commands += ["profile custom", "profile hdplus"]
                    else:
                        commands += ["profile custom", "dump custom", f"set {KEY} {choice}"]
                        if unrelated:
                            commands.append(f"set {UNRELATED} {unrelated}")
                    commands += ["dump changed", "click save", "dump saved", "click close"]
                    code, dumps, log, ui_out = launcher.ui(home, out, name, "\n".join(commands) + "\n")
                    initial = dumps.get("initial", {})
                    changed = dumps.get("changed", {})
                    changed_keys = {KEY} | ({UNRELATED} if unrelated else set())
                    before_value = "original" if initial_preset == "vanilla" else "delayed"
                    label = locale.load()[entry["label"]].get("en", entry["label"])
                    help_text = locale.load()[entry["help"]].get("en", entry["help"])
                    # Static labels share native control ID 0, so the helper's key/value parser collapses them;
                    # inspect the raw UI-test dump when verifying actual displayed copy.
                    visible = (ui_out / "initial.txt").read_text(encoding="utf-8")
                    check(f"UI {name}: visible label and explanation; fixed preset control has expected value and is disabled",
                          code == 0 and initial.get("setting." + KEY) == f"{before_value} enabled=0"
                          and label in visible and help_text in visible and launcher.layout_ok(initial), log[-400:])
                    if target_custom:
                        custom = dumps.get("custom", {})
                        check(f"UI {name}: selecting Custom preserves {initial_preset} base and enables only explicit choices",
                              custom.get("profile") == "custom" and custom.get("custom_base") == initial_preset
                              and custom.get("setting." + KEY) == f"{before_value} enabled=1"
                              and custom.get("dirty") == "1" and launcher.layout_ok(custom), log[-300:])
                        check(f"UI {name}: Combo and independent unrelated choice changed in Custom",
                              changed.get("profile") == "custom"
                              and changed.get("setting." + KEY) == f"{choice} enabled=1"
                              and (not unrelated or changed.get("setting." + UNRELATED) == f"{unrelated} enabled=1"))
                    else:
                        check(f"UI {name}: selecting the current fixed preset stores its unchanged Combo default",
                              changed.get("profile") == final_preset
                              and changed.get("setting." + KEY) == f"{before_value} enabled=0")

                    saved = launcher.settings(home)
                    resolved = settings.resolve(reg, settings=saved)
                    expected_preset = "custom" if target_custom else final_preset
                    check(f"UI {name}: save persists the intended profile, Combo choice and French Game language",
                          code == 0 and resolved["preset"] == expected_preset
                          and resolved["values"][KEY] == choice and resolved["values"][LANGUAGE] == "fr"
                          and saved.get("preferences", {}).get(LANGUAGE) == "fr"
                          and (not target_custom or saved.get("base") == initial_preset), json.dumps(saved))
                    check(f"UI {name}: changing Combo leaves every unrelated resolved setting unchanged",
                          all(resolved["values"][k] == before[k] for k in reg["settings"] if k not in changed_keys))
                    if target_custom:
                        expected_overrides = {KEY: choice}
                        if unrelated:
                            expected_overrides[UNRELATED] = unrelated
                        check(f"UI {name}: unrelated Custom override remains independently stored",
                              saved.get("overrides") == expected_overrides, json.dumps(saved.get("overrides")))
                    snapshots[name] = home / "settings.json"

                    # A separate launcher process on a separate private desktop proves save/close/reopen persistence.
                    code, reopened, reopen_log, _ = launcher.ui(home, out, name + "_reopened", "page settings\ndump reopened\nclick close\n")
                    state = reopened.get("reopened", {})
                    check(f"UI {name}: close and reopen restores the persisted profile, Combo value and layout",
                          code == 0 and state.get("profile") == expected_preset
                          and state.get("setting." + KEY) == f"{choice} enabled={0 if not target_custom else 1}"
                          and state.get("setting." + LANGUAGE) == "fr enabled=1"
                          and launcher.layout_ok(state), reopen_log[-300:])

                    if target_custom:
                        # Change only Combo in an already saved Custom file. This
                        # catches losing an existing unrelated override on save.
                        baseline = json.loads(json.dumps(saved))
                        baseline.get("overrides", {}).pop(KEY, None)
                        opposite = "original" if choice == "delayed" else "delayed"
                        for value in (opposite, choice):
                            code, _, log, _ = launcher.ui(home, out, name + "_only_" + value,
                                f"page settings\nset {KEY} {value}\nclick save\nclick close\n")
                            after = launcher.settings(home)
                            other_fields = json.loads(json.dumps(after))
                            other_fields.get("overrides", {}).pop(KEY, None)
                            check(f"UI {name}: changing only Combo to {value} preserves existing Custom fields",
                                  code == 0 and other_fields == baseline
                                  and settings.resolve(reg, settings=after)["values"][KEY] == value, log[-300:])
                            code, dumps, log, _ = launcher.ui(home, out, name + "_only_" + value + "_reopen",
                                "page settings\ndump reopened\nclick close\n")
                            check(f"UI {name}: independent {value} choice survives a new Settings process",
                                  code == 0 and dumps.get("reopened", {}).get("setting." + KEY) == f"{value} enabled=1"
                                  and dumps.get("reopened", {}).get("setting." + LANGUAGE) == "fr enabled=1", log[-300:])

                # EN/TR are the existing Settings interface languages; exercise the translated row in Turkish too.
                tr_home = out / "home_turkish"
                engine.install(tr_home, payload, tree, "hdplus", releases=releases,
                               ui_language="tr", log=lambda *_: None)
                engine.set_option(tr_home, LANGUAGE, "fr")
                code, dumps, log, ui_out = launcher.ui(tr_home, out, "turkish_visible",
                                                        "page settings\ndump visible\nshot combo_row_tr\nclick close\n")
                tr = dumps.get("visible", {})
                tr_visible = (ui_out / "visible.txt").read_text(encoding="utf-8")
                check("UI Turkish: translated Combo label and help are visible in Settings",
                      code == 0 and locale.load()[entry["label"]]["tr"] in tr_visible
                      and locale.load()[entry["help"]]["tr"] in tr_visible and launcher.layout_ok(tr), log[-300:])

                SNAPSHOTS.mkdir(parents=True, exist_ok=True)
                for name, source in snapshots.items():
                    dest = SNAPSHOTS / f"{name}.json"
                    shutil.copyfile(source, dest)
                    check(f"runtime fixture {name}: saved GUI configuration snapshot with French Game language",
                          settings.resolve(reg, settings=settings.load_settings_file(dest))["values"][LANGUAGE] == "fr"
                          and settings.resolve(reg, settings=settings.load_settings_file(dest))["values"][KEY]
                          == {"vanilla": "original", "hdplus": "delayed", "custom_on": "delayed", "custom_off": "original"}[name],
                          str(dest))
            finally:
                for key, value in saved_env.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

    failures = [item["name"] for item in checks if not item["pass"]]
    report = {"checks": checks, "passed": len(checks) - len(failures), "total": len(checks),
              "engine_only": args.engine_only, "ui_languages": ["en", "tr"] if not args.engine_only else [],
              "settings_snapshots": [str(SNAPSHOTS / f"{name}.json") for name in
                                     ("vanilla", "hdplus", "custom_on", "custom_off") if (SNAPSHOTS / f"{name}.json").is_file()]}
    (out / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("COMBO_SETTINGS_REGRESSION " + ("FAIL" if failures else "PASS") +
          f" {report['passed']}/{report['total']}")
    for failure in failures:
        print("FAIL " + failure)
    print("Detailed results: " + str(out / "result.json"))
    for path in report["settings_snapshots"]:
        print("GUI configuration fixture: " + path)
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
