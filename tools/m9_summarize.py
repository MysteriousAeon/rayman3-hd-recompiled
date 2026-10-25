"""Metadata-only summary of M9 licence-mode runs: python tools/m9_summarize.py OUTPUT.json RUN [RUN ...]

Records the selected mode, the mask the guest received, read-only gate probes, content-API calls, levels opened,
focus results and the save files' sizes and hashes. No game data, frames or paths outside the repository.
"""
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def summarize(name: str) -> dict:
    run = ROOT / "private" / "work" / "m6_runs" / name
    meta = json.loads((run / "run.json").read_text(encoding="utf-8-sig"))
    lines = []
    for path in sorted(run.glob("runtime*.log")):
        lines += path.read_text(errors="replace").splitlines()
    imports = sorted({m[1] for line in lines if (m := re.search(r"import=__imp__(\w+)", line))})
    content = [m.groupdict() for line in lines
               if (m := re.search(r"M6 content api=(?P<api>\w+) caller=(?P<caller>\w+) arg3=\w+ arg4=\w+ arg5=\w+ arg6=(?P<arg6>\w+) result=(?P<result>\w+)", line))]
    opened = []
    for line in lines:
        m = re.search(r"vfs_open path=.*?([A-Za-z_0-9]+\.(?:lvl|bik)) result=00000000", line)
        if m and m[1] not in ("fix.lvl", "transit.lvl") and (not opened or opened[-1] != m[1]):
            opened.append(m[1])
    driver = run / "license_run.json"
    pilot = run / "pilot.json"
    user = Path(meta["user_root"]) if meta.get("user_root") else run / "user"
    return {
        "run": name,
        "license_mode": meta.get("license_mode"),
        "license_mask_selected": meta.get("license_mask"),
        "license_argument_passed": [a for a in meta["arguments"] if "license" in a],
        "host_mode_lines": sorted({m[0] for line in lines if (m := re.search(r"M9 license_mode=\w+ source=.*", line))}),
        "guest_license_masks": sorted({m[1] for line in lines if (m := re.search(r"M6 license .* mask=(\w{8})", line))}),
        "probes": [{"label": e["label"], **(e["state"] or {})} for e in json.loads(driver.read_text())["events"] if e["step"] == "probe"] if driver.is_file() else [],
        "opened_in_order": opened,
        "content_calls": content,
        "device_selector_calls": sum("import=__imp__XamShowDeviceSelectorUI" in line for line in lines),
        "imports_distinct": len(imports),
        "xam_content_imports": [i for i in imports if i.startswith(("XamContent", "XamEnumerate", "XamShowDeviceSelectorUI"))],
        "stub_imports": sum(" stub=true " in line for line in lines),
        "frames_saved": len(list(run.glob("m3_frame_*.bmp"))),
        "play_profile": meta.get("play_profile"),
        "executable_sha256": meta["executable_sha256"],
        "seconds": meta["seconds"],
        "exit_code": meta["exit_code"],
        "forced_termination": meta["forced_termination"],
        "runner_error": meta["error"],
        "driver_error": (json.loads(driver.read_text())["error"] if driver.is_file() else json.loads(pilot.read_text())["error"] if pilot.is_file() else None),
        "game_foreground_events": meta["game_foreground_events"],
        "game_foreground_samples": meta["game_foreground_samples"],
        "profile": user.name if meta.get("user_root") and "m9_profiles" in meta["user_root"] else "run-local",
        "profile_files_now": [{"path": p.relative_to(user).as_posix(), "size": p.stat().st_size,
                               "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(user.rglob("*")) if p.is_file()] if user.is_dir() else [],
    }


if __name__ == "__main__":
    output = Path(sys.argv[1])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps([summarize(name) for name in sys.argv[2:]], indent=1) + "\n", encoding="utf-8")
    print(f"wrote {output}")
