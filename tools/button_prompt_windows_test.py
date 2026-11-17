"""D-204: real Settings radio persistence/layout on its private test desktop. No game/capture."""
from datetime import datetime
import json
import os
from pathlib import Path
from unittest.mock import patch

import m30_launcher_regression as ui
import r3hd_installer as engine


def main():
    work = ui.ROOT / "private/work/button_prompt_windows" / datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    work.mkdir(parents=True)
    sys32 = work / "sys32"
    sys32.mkdir()
    for name in engine.VC_RUNTIME:
        (sys32 / name).write_bytes(b"fixture")
    checks = []
    with patch.dict(os.environ, {"R3HD_INSTALL_SYSTEM32": str(sys32), "R3HD_INSTALL_FAKE_RUNNING": "0",
                                 "R3HD_INSTALL_FAKE_LAUNCHER": "0"}):
        home = ui.make_home(work, "Home")
        script = "\n".join([
            "dump initial", "set controller_prompts auto", "click save", "reload", "dump auto", "set controller_prompts playstation", "click save", "reload", "dump ps",
            "profile hdplus", "dump hd", "profile custom", "dump custom", "language tr", "dump tr",
            "dpi 120", "dump tr120", "dpi 144", "dump tr144", "set controller_prompts xbox",
            "click save", "reload", "dump xbox", "language en", "dump en", "set controller_prompts auto", "click save", "reload", "dump restored_auto", "click close", ""])
        code, dumps, log, _ = ui.ui(home, work, "prompts", script)
        checks.append(("private desktop run", code == 0 and "initial" in dumps))
        for tag in ("initial", "auto", "ps", "hd", "custom", "tr", "tr120", "tr144", "xbox", "en", "restored_auto"):
            d = dumps.get(tag, {})
            ps = tag in ("ps", "hd", "custom", "tr", "tr120", "tr144")
            selected = "auto" if tag in ("initial", "auto", "restored_auto") else "playstation" if ps else "xbox"
            checks.append((tag + " radios", all(d.get("prompt_radio." + value) == str(int(value == selected))
                                               for value in ("auto", "xbox", "playstation"))))
            checks.append((tag + " left column beneath profile", d.get("prompt_below_profile") == "1"))
            checks.append((tag + " layout", ui.layout_ok(d) and d.get("text_clipped") == "0"))
        checks.append(("final persisted Auto", ui.rs.resolve(ui.rs.load_registry(), settings=ui.settings(home))["values"]["controller_prompts"] == "auto"))
        result = {"checks": [{"name": n, "pass": bool(ok)} for n, ok in checks], "game_started": False,
                  "captures": 0, "private_desktop_log": log}
        (work / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        bad = [n for n, ok in checks if not ok]
        print("BUTTON_PROMPT_WINDOWS", "FAIL" if bad else "PASS", f"checks={len(checks)}", str(work))
        for n in bad:
            print("FAIL", n)
        return int(bool(bad))


if __name__ == "__main__":
    raise SystemExit(main())
