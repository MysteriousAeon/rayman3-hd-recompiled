#!/usr/bin/env python3
"""Linux launcher for r3hd: the Linux counterpart of tools/play.ps1 (LX-2, E-374).

The Windows features (HD+ preset, combo meter close, gameplay subtitles, DualSense light bar / triggers, mods,
keyboard and controller maps, pacing, ...) are implemented in the runtime and the game host and are switched on by
the launcher through runtime arguments and R3HD_* variables. play.ps1 is that launcher on Windows; without it every
feature stays at its off default, which is what the first native Linux runs showed (`R3HD dualsense light=off`).

This script reuses the same sources of truth, it does not reimplement them:
  * tools/r3hd_settings.py resolve: presets, settings.json, explicit values, the keyboard and controller maps;
  * tools/r3hd_mods.py plan: the verified mod plan (R3HD_MODS_PLAN);
  * the argument and variable mapping of play.ps1 (kept equal by tools/linux/test_r3hd_play.py, which parses it).
Windows-only parts are left out and reported: the work-area window fitting and display-scale conversion, the
installer repair hints, Discord IPC.

LX-4 (E-375): the home layout is play.ps1's (M28): HOME/bin, HOME/data/content, HOME/settings.json, profiles, cache,
sessions and mods; --bin / --game override it. A home prepared by app/tools/r3hd_portable.py (the Linux package, the
same portable layout as the Windows ZIP) is an installed home: the in-game PC Settings panel (F4) then saves through
the same engine (r3hd_installer.py set-preferences), exactly when play.ps1 lets it (D-139), and the 10 newest
sessions are kept (M31). The desktop identity (SDL_APP_ID) matches the desktop entry that --desktop-entry writes.

  python3 tools/linux/r3hd_play.py [--home DIR] [--bin DIR] [--game CONTENT] [--preset hdplus] [--set key=value ...]
  python3 tools/linux/r3hd_play.py ... --dry-run          (prints the plan as JSON; starts nothing)
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
XEX_SHA256 = "77a4df54340aebcc79eb0f0053938c03b8efd2efdd3ffee26c00fdfef3c6e8ca"  # play.ps1 $xexSha256
# play.ps1 $settingParams: launcher parameter -> registry key (the parameter names are the play.ps1 variables).
SETTING_PARAMS = {
    "Revisit": "revisit", "Pacing": "pacing", "Display": "display", "Cursor": "cursor", "SaveClock": "save_clock",
    "GameLanguage": "game_language", "RenderScale": "render_scale", "LayerCoords": "layer_coords",
    "TextureOrient": "texture_orient", "RedCorrection": "red_correction", "SkyClear": "sky_clear",
    "LitUvScroll": "lit_uv_scroll", "PowerSwirl": "power_swirl", "BeamColor": "beam_color", "LockonColor": "lockon_far_color", "VSync": "display_vsync", "WindowSize": "window_size", "ComboClose": "combo_close",
    "Diagnostics": "diagnostics", "GameplaySubtitles": "gameplay_subtitles", "DiscordPresence": "discord_presence",
    "DualSenseLight": "dualsense_light", "DualSenseTrigger": "dualsense_trigger",
    "DualSenseTriggerStrength": "dualsense_trigger_strength", "DualSenseSpeaker": "dualsense_speaker",
    "DualSenseSpeakerVolume": "dualsense_speaker_volume", "MouseCamera": "mouse_camera",
    "MouseSensitivity": "mouse_sensitivity", "MouseButtons": "mouse_buttons", "ButtonPrompts": "controller_prompts",
}
# play.ps1: `$env:R3HD_X = $Param` for a setting passed through unchanged.
# D-220: R3HD_DISPLAY_VSYNC is mapped for parity only; it is Windows-only (D3D12 presenter) and the Vulkan
# presenter used here does not read it, so the preference has no effect on Linux.
ENV_FROM_PARAM = {
    "R3HD_DISCORD": "DiscordPresence", "R3HD_DS_LIGHT": "DualSenseLight", "R3HD_DS_TRIGGER": "DualSenseTrigger",
    "R3HD_DS_TRIGGER_STRENGTH": "DualSenseTriggerStrength", "R3HD_DS_SPEAKER": "DualSenseSpeaker",
    "R3HD_DS_SPEAKER_VOLUME": "DualSenseSpeakerVolume", "R3HD_REVISIT": "Revisit", "R3HD_LAYER_COORDS": "LayerCoords",
    "R3HD_TEXTURE_ORIENT": "TextureOrient", "R3HD_RED_CORRECTION": "RedCorrection", "R3HD_SKY_CLEAR": "SkyClear",
    "R3HD_LIT_UV_SCROLL": "LitUvScroll", "R3HD_POWER_SWIRL": "PowerSwirl", "R3HD_BEAM_COLOR": "BeamColor", "R3HD_LOCKON_COLOR": "LockonColor", "R3HD_DISPLAY_VSYNC": "VSync", "R3HD_COMBO_CLOSE": "ComboClose",
    "R3HD_GAMEPLAY_SUBTITLES": "GameplaySubtitles",
    "R3HD_BUTTON_PROMPTS": "ButtonPrompts",
}
GAME_LANGUAGE_ID = {"en": 1, "fr": 4, "es": 5, "it": 6, "de": 3}  # play.ps1 $gameLanguageId
# play.ps1 $testOnly: never inherited from the calling environment into a play session.
TEST_ONLY = ("R3HD_NONINTRUSIVE", "R3HD_TEST_SECONDS", "R3HD_INPUT_SCHEDULE", "R3HD_INPUT_FOLLOW", "R3HD_M5_CAPTURE",
             "R3HD_FRAME_REQUEST", "R3HD_AUDIO_CAPTURE", "R3HD_AUDIO_AFTER", "R3HD_M5_VB_RESIDENCY_CACHE", "R3HD_PLAY",
             "R3HD_TRIAL", "R3HD_FRAME_TRACE", "R3HD_VBLANK_SPIN_US", "R3HD_TEST_WORLD_END", "R3HD_TEST_COMBO_CLOSE",
             "R3HD_TEST_COMBO_PLAYTEST", "R3HD_TEST_COMBO_CAPTURE", "R3HD_TEST_SKY_CLEAR", "R3HD_SAVE_FAULT",
             "R3HD_SAVE_COMMIT", "R3HD_CURSOR", "R3HD_TIMEZONE", "R3HD_M22_DRAW_TRACE", "R3HD_M22_AUDIO",
             "R3HD_AUDIO_AUDIBLE", "R3HD_M24_EVENTS", "R3HD_DIAGNOSTICS", "R3HD_KEYMAP_TEST", "R3HD_PADMAP_TEST",
             "R3HD_PAD_MAP", "R3HD_DISCORD", "R3HD_DS_LIGHT", "R3HD_DS_TRIGGER", "R3HD_DS_TRIGGER_STRENGTH",
             "R3HD_DS_SPEAKER", "R3HD_DS_SPEAKER_VOLUME", "R3HD_ACH_TEXT", "R3HD_PCSET_TEST", "R3HD_PCSET_HOME",
             "R3HD_PCSET_PYTHON", "R3HD_PCSET_TOOLS", "R3HD_PCSET_SESSION", "R3HD_PCSET_SETTINGS_APP", "R3HD_BUTTON_PROMPTS", "R3HD_BUTTON_PROMPTS_PLAN", "R3HD_BUTTON_PROMPTS_TEST", "R3HD_BUTTON_PROMPTS_EFFECTIVE")
FORBIDDEN_EXTRA = ("--license_mask=", "--user_language=", "--cl=", "--bind_settings=", "--bind_debug_overlay=")
SESSION_LIMIT = 10  # play.ps1 $sessionLimit (M31): an installed home keeps its 10 newest sessions
APP_ID = "rayman3hd-recompiled"  # SDL_APP_ID: the Wayland app_id / X11 WM_CLASS that the desktop entry names


class Refused(Exception):
    pass


def resolve_settings(preset, settings_file, explicit, key_layout):
    cmd = [sys.executable, "-B", str(TOOLS / "r3hd_settings.py"), "resolve"]
    if preset:
        cmd += ["--preset", preset]
    if settings_file:
        cmd += ["--settings", str(settings_file)]
    if explicit:
        cmd += ["--explicit", *explicit]
    if key_layout:
        cmd += ["--key-layout", key_layout]
    r = subprocess.run(cmd, capture_output=True, text=True)
    try:
        out = json.loads(r.stdout)
    except ValueError:
        raise Refused(f"settings resolver failed (exit {r.returncode}): {r.stderr.strip()[-300:]}")
    if r.returncode or out.get("result") != "resolved":
        raise Refused(f"settings refused: {out.get('code')}: {out.get('detail')}")
    return out


def primary_mode(xrandr_text):
    """The primary monitor's mode from `xrandr --current`, as play.ps1 takes the primary display mode (E-377).

    Not the "current W x H" screen size: with several monitors that is their combined desktop (LX2B: 4480x1440 for a
    2560x1440 and a 1920x1080 monitor side by side). The output marked primary wins; else the one at +0+0; else the
    first connected output with a mode. None when no connected output has a mode."""
    outputs = [(bool(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4)), int(m.group(5)))
               for m in re.finditer(r"^\S+ connected (primary )?(\d+)x(\d+)\+(\d+)\+(\d+)", xrandr_text, re.M)]
    if not outputs:
        return None
    pick = next((o for o in outputs if o[0]), None) or next((o for o in outputs if o[3:] == (0, 0)), outputs[0])
    return pick[1], pick[2]


def display_mode():
    """The primary monitor's mode (physical pixels) when xrandr can tell (X11 or XWayland); None otherwise."""
    if not shutil.which("xrandr"):
        return None
    try:
        out = subprocess.run(["xrandr", "--current"], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    return primary_mode(out)


def render_scale(setting, target):
    if setting != "auto":
        return int(setting)
    import math
    scale = max(math.ceil(target[0] / 1280.0), math.ceil(target[1] / 720.0))
    return int(min(3, max(1, scale)))


def mouse_scale(sensitivity):
    return format(round(2 ** ((int(sensitivity) - 50) / 25), 4), "g")


def mods_plan(home, cache, game, enabled):
    root = home / "mods"
    if not enabled:
        return "", "", "off (--mods off)", []
    if not (root / "state.json").is_file():
        return "", "", "none installed", []
    cmd = [sys.executable, "-B", str(TOOLS / "r3hd_mods.py"), "plan", "--json", "--mods-root", str(root),
           "--cache", str(cache / "mods"), "--game-dir", str(game), "--home", str(home)]
    try:
        out = json.loads(subprocess.run(cmd, capture_output=True, text=True).stdout)
    except ValueError:
        out = None
    if not out or out.get("result") != "ok":
        detail = f"{out.get('code')}: {out.get('detail')}" if out else "no result"
        return "", "", "none applied", [f"the mod list could not be used ({detail}); the game's own data is used"]
    notes = [f"{m['id']} is not applied: {m.get('code')} {m.get('detail')}" for m in out.get("mods", [])
             if m.get("enabled") and m.get("state") != "active"]
    active = out.get("active") or []
    plan = out.get("plan", "") if active else ""
    ach = out.get("achievement_text", "") if active else ""
    text = f"{', '.join(active)} ({out.get('ranges')} ranges)" if active else "none enabled"
    return plan, ach, text, notes


def sessions_to_prune(root, keep):
    """play.ps1 Get-SessionsToPrune: session folders (timestamp names only) beyond the keep newest; nothing else."""
    if not root.is_dir():
        return []
    names = sorted(p.name for p in root.iterdir() if p.is_dir() and not p.is_symlink()
                   and re.fullmatch(r"\d{8}-\d{6}", p.name))
    return names[:len(names) - keep] if len(names) > keep else []


def build_plan(a, now=None):
    home = Path(a.home).expanduser().resolve()
    bin_dir = Path(a.bin).expanduser().resolve() if a.bin else home / "bin"
    game = Path(a.game).expanduser().resolve() if a.game else home / "data" / "content"
    installed = (home / "installer.json").is_file()  # play.ps1 $installed
    exe = bin_dir / "r3hd"
    for extra in a.extra:
        if not re.match(r"^--[a-z0-9_]+=", extra):
            raise Refused(f"extra arguments look like --name=value: {extra}")
        if extra.startswith(FORBIDDEN_EXTRA):
            raise Refused(f"{extra.split('=')[0]} is chosen by a launcher option or setting, not through --extra")
    settings_file = Path(a.settings).expanduser() if a.settings else None
    if not settings_file and not a.preset and (home / "settings.json").is_file():
        settings_file = home / "settings.json"
    resolved = resolve_settings(a.preset, settings_file, a.set, a.key_layout)
    v = {param: str(resolved["values"][key]) for param, key in SETTING_PARAMS.items()}

    problems = []
    if not a.dry_run or a.check:
        if not os.access(exe, os.X_OK):
            problems.append(f"executable missing: {exe}")
        xex = game / "Default.xex"
        if not xex.is_file():
            problems.append(f"extracted game content missing: {xex}")
        elif hashlib.sha256(xex.read_bytes()).hexdigest() != XEX_SHA256:
            problems.append("Default.xex does not match the hash this build was translated from")
    if problems:
        raise Refused("; ".join(problems))

    stamp = (now or datetime.datetime.now()).strftime("%Y%m%d-%H%M%S")
    session = home / "sessions" / stamp
    user = home / "profiles" / a.profile / "user"
    cache = home / "cache"
    fullscreen = v["Display"] == "fullscreen"
    args = [f"--game_data_root={game}", f"--user_data_root={user}", f"--cache_root={cache}", "--gpu_plugin=xenos",
            f"--log_level={a.log_level}", "--log_flush_interval=1", f"--log_file={session / 'runtime.log'}",
            f"--mnk_mode={'false' if a.no_keyboard else 'true'}", f"--fullscreen={'true' if fullscreen else 'false'}"]
    if v["MouseCamera"] == "on":
        args += ["--mnk_mouse=true", f"--mnk_sensitivity={mouse_scale(v['MouseSensitivity'])}"]
    if v["MouseButtons"] == "on":
        args.append("--mnk_mouse_buttons=true")
    if not a.dev_overlay:
        args += ["--bind_settings=None", "--bind_debug_overlay=None"]
    if v["Diagnostics"] == "standard":
        args.append("--log_max_files=2")
    notes = []
    target, target_source = (1280, 720), "default window"
    if fullscreen:
        mode = display_mode()
        if mode:
            target, target_source = mode, "primary display mode (xrandr)"
        else:
            target_source = "display mode unavailable, assumed 1280x720"
    elif v["WindowSize"] != "auto":
        w, h = (int(x) for x in v["WindowSize"].split("x"))
        args += [f"--window_width={w}", f"--window_height={h}"]
        target, target_source = (w, h), "window"
        notes.append("window size is passed as is (no work-area fitting or display scaling on Linux)")
    scale = render_scale(v["RenderScale"], target)
    args.append(f"--resolution_scale={scale}")
    keyboard = resolved.get("keyboard") or {}
    controller = resolved.get("controller") or {}
    if not a.no_keyboard:
        named = {e.split("=", 1)[0] for e in a.extra if e.startswith("--keybind_")}
        key_args = [k for k in keyboard.get("args", []) if k.split("=", 1)[0] not in named]
        if any(re.match(r"^--keybind_[a-z_]+=.*\+", e) for e in a.extra) or any(e.startswith("--mnk_modifier_keys=") for e in a.extra):
            key_args = [k for k in key_args if not k.startswith("--mnk_modifier_keys=")]
        args += key_args
    args.append(f"--user_language={GAME_LANGUAGE_ID[v['GameLanguage']]}")
    args += a.extra

    plan, ach_text, mods_text, mod_notes = mods_plan(home, cache, game, a.mods == "on")
    notes += mod_notes
    env = {k: v[p] for k, p in ENV_FROM_PARAM.items()}
    env.update({
        "R3HD_PLAY": "1",
        "R3HD_PAD_MAP": str(controller.get("env") or ""),
        "R3HD_PCSET_SESSION": ";".join(f"{SETTING_PARAMS[p]}={v[p]}" for p in SETTING_PARAMS),
        "R3HD_VBLANK": "deadline" if v["Pacing"] == "precise" else "poll",
        "R3HD_WATER_LAYERS": "",
        "R3HD_MODS_PLAN": plan,
    })
    if ach_text:
        env["R3HD_ACH_TEXT"] = ach_text
    if v["Cursor"] == "visible":
        env["R3HD_CURSOR"] = "visible"
    if v["SaveClock"] == "utc":
        env["R3HD_TIMEZONE"] = "utc"
    if v["Diagnostics"] == "detailed":
        env["R3HD_DIAGNOSTICS"] = "detailed"
    if a.license == "trial":
        env["R3HD_TRIAL"] = "1"
    # D-139 (play.ps1): F4 saves through the engine of this home only when the launch uses the home's own
    # settings.json (no --preset / other --settings); otherwise it is session-only. No Settings app on Linux yet.
    home_settings = home / "settings.json"
    pcset_home = installed and settings_file is not None and settings_file.resolve() == home_settings.resolve()
    if pcset_home:
        env.update({"R3HD_PCSET_HOME": str(home), "R3HD_PCSET_PYTHON": sys.executable, "R3HD_PCSET_TOOLS": str(TOOLS)})
    pcset_text = f"F4; saves to {home}" if pcset_home else "F4; this session only (no installation settings)"
    env["SDL_APP_ID"] = APP_ID
    prune = sessions_to_prune(home / "sessions", SESSION_LIMIT - 1) if installed else []
    notes.append("the Windows save keeper (play_savekeeper.ps1 save history) is not part of the Linux launcher")
    return {
        "executable": str(exe), "session": str(session), "arguments": args, "env": env,
        "installed": installed, "pc_settings": pcset_text, "prune_sessions": prune,
        "settings": {"label": resolved.get("label"), "file": str(settings_file) if settings_file else "",
                     "values": resolved["values"], "warnings": resolved.get("warnings", [])},
        "render": f"{1280 * scale}x{720 * scale} internal (scale {scale}), target {target[0]}x{target[1]} ({target_source})",
        "keyboard": f"{keyboard.get('layout_name')} ({keyboard.get('state')})" if not a.no_keyboard else "none",
        "controller": f"{controller.get('state')}{': ' + controller['env'] if controller.get('env') else ''}",
        "mods": mods_text, "notes": notes,
    }


SETTINGS_ID = APP_ID + "-settings"
FALLBACK_ICONS = {APP_ID: "app/icons/rayman3hd-recompiled.png", SETTINGS_ID: "app/icons/rayman3hd-recompiled-settings.png"}


def png_size(png):
    """(width, height) of a PNG, or None."""
    if png[:8] != b"\x89PNG\r\n\x1a\n" or png[12:16] != b"IHDR" or len(png) < 24:
        return None
    return int.from_bytes(png[16:20], "big"), int.from_bytes(png[20:24], "big")


def ico_png(data):
    """The PNG of a one-image ICO with a PNG entry (r3hd_installer.play_icon_bytes), or None."""
    if len(data) > 22 and data[:4] == b"\0\0\1\0":
        size, offset = int.from_bytes(data[14:18], "little"), int.from_bytes(data[18:22], "little")
        png = data[offset:offset + size]
        if png_size(png):
            return png
    return None


def game_icon(home, package=None):
    """E-379: the game's own icon, as Windows uses it: data/play_icon.ico, written by the engine from the person's
    package (r3hd_installer.write_play_icon; game-derived, local, never shipped). With `package` (the person's own
    package file) it is made from that package's header, after the engine checks that it is the package the data
    came from. Returns (png, "package") or (None, reason)."""
    ico = home / "data" / "play_icon.ico"
    if package is not None:
        sys.path.insert(0, str(TOOLS))
        import r3hd_installer as engine
        try:  # the package the data came from, else the supported release's own package identity
            content_id = engine.read_json(home / "data" / "intake.json").get("source", {}).get("content_id")
        except (OSError, ValueError, AttributeError):
            content_id = None
        content_id = content_id or engine.load_releases()[0]["package"]["content_id"]
        data = engine.play_icon_bytes(Path(package), content_id)
        if data is None:
            return None, "the package has no usable thumbnail or is not the package the data came from"
        if not ico.is_file() or ico.read_bytes() != data:
            ico.write_bytes(data)
    if ico.is_file():
        png = ico_png(ico.read_bytes())
        if png:
            return png, "package"
    return None, "no data/play_icon.ico (game data supplied as an extracted folder)"


def desktop_escape(value):
    """A quoted Exec argument (freedesktop Desktop Entry spec: \\ " ` $ escaped inside double quotes)."""
    return '"' + re.sub(r'([\\"`$])', r"\\\1", str(value)) + '"'


def refresh_desktop_cache(base, run=subprocess.run):
    """Best effort: let the menu notice a new or removed entry at once (absent tools are skipped)."""
    for argv in (["update-desktop-database", str(base / "applications")], ["kbuildsycoca6"], ["kbuildsycoca5"]):
        if shutil.which(argv[0]):
            try:
                run(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60, check=False)
            except (OSError, subprocess.SubprocessError):
                pass
            if argv[0].startswith("kbuildsycoca"):
                break


def desktop_entry(home, data_home=None, package=None, refresh=True):
    """Per-user desktop entries (freedesktop) for this home: the game (Play.sh) and Settings (Settings.sh), with the
    icons Windows uses: the game's own thumbnail from the person's package when it is available (see game_icon),
    else the application's neutral fallback icon (the same Fluent artwork as r3hd.exe's icon resource, shipped in
    app/icons). The game entry's file name and StartupWMClass equal SDL_APP_ID, the Wayland app_id / X11 WM_CLASS
    the launcher gives the window, so KDE matches the window and taskbar button to it. Icon= names the installed
    file by absolute path (no icon-theme cache to refresh). Returns {"written": [...], "icon": source}."""
    home = Path(home).expanduser().resolve()
    base = Path(data_home or os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share").expanduser()
    png, why = game_icon(home, package)
    source = "package"
    if png is None:
        fallback = home / FALLBACK_ICONS[APP_ID]
        png, source = (fallback.read_bytes(), "fallback") if fallback.is_file() else (None, "none")
    written, removed = [], remove_icons(base)
    entries = {APP_ID: ("Rayman 3 HD Recompiled", "Play (experimental Linux build; uses your own game data)",
                        "Play.sh", png, "Game;"),
               SETTINGS_ID: ("Rayman 3 HD Recompiled Settings", "Preset, display, controls and other settings",
                             "Settings.sh", (home / FALLBACK_ICONS[SETTINGS_ID]).read_bytes()
                             if (home / FALLBACK_ICONS[SETTINGS_ID]).is_file() else None, "Game;Settings;")}
    for app_id, (name, comment, script, icon_png, categories) in entries.items():
        icon_line = ""
        size = png_size(icon_png or b"")
        if size:
            icon = base / f"icons/hicolor/{size[0]}x{size[1]}/apps" / f"{app_id}.png"
            icon.parent.mkdir(parents=True, exist_ok=True)
            icon.write_bytes(icon_png)
            written.append(str(icon))
            icon_line = f"Icon={icon}\n"
        entry = base / "applications" / f"{app_id}.desktop"
        entry.parent.mkdir(parents=True, exist_ok=True)
        entry.write_text("[Desktop Entry]\nType=Application\nVersion=1.5\n"
                         f"Name={name}\nComment={comment}\nExec={desktop_escape(home / script)}\nPath={home}\n"
                         f"{icon_line}Terminal=false\nCategories={categories}\nStartupNotify=true\n"
                         f"StartupWMClass={app_id}\nX-R3HD-Home={home}\n", encoding="utf-8")
        written.append(str(entry))
    if refresh:
        refresh_desktop_cache(base)
    return {"written": written, "icon": source, "icon_note": None if source == "package" else why,
            "replaced_icons": [str(r) for r in removed if str(r) not in written]}


def remove_icons(base):
    """Our installed icons in every size (an icon of another size must not shadow the new one)."""
    removed = []
    for app_id in (APP_ID, SETTINGS_ID):
        for icon in sorted((base / "icons/hicolor").glob(f"*/apps/{app_id}.png")):
            icon.unlink()
            removed.append(icon)
    return removed


def entry_home(entry):
    m = re.search(r"^X-R3HD-Home=(.*)$", entry.read_text(encoding="utf-8", errors="replace"), re.M) \
        if entry.is_file() else None
    return m.group(1) if m else None


def remove_desktop_entry(home, data_home=None, refresh=True):
    """Remove the entries and icons desktop_entry wrote for THIS home (an entry of another home is kept)."""
    home = Path(home).expanduser().resolve()
    base = Path(data_home or os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share").expanduser()
    entries = [base / "applications" / f"{i}.desktop" for i in (APP_ID, SETTINGS_ID)]
    if any(entry_home(e) not in (None, str(home)) for e in entries):
        return {"removed": [], "kept": "the entries belong to another home: " + str(entry_home(entries[0]))}
    removed = [str(e) for e in entries if e.is_file()]
    for e in entries:
        if e.is_file():
            e.unlink()
    removed += [str(i) for i in remove_icons(base)]
    if refresh:
        refresh_desktop_cache(base)
    return {"removed": removed}


def update_desktop_entry_if_present(home, data_home=None):
    """Keep an existing entry of this home current (icon, paths) at each start; never creates one."""
    base = Path(data_home or os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share").expanduser()
    if entry_home(base / "applications" / f"{APP_ID}.desktop") == str(Path(home).expanduser().resolve()):
        try:
            return desktop_entry(home, data_home)
        except OSError:
            return None
    return None


def prepare_button_prompt_plan(plan, run=None):
    """Generate local artwork only for a real launch; failures retain Xbox artwork."""
    plan["env"]["R3HD_BUTTON_PROMPTS_PLAN"] = ""
    if plan["env"].get("R3HD_BUTTON_PROMPTS", "auto") == "xbox":
        return
    run = run or subprocess.run
    try:
        paths = dict(arg[2:].split("=", 1) for arg in plan["arguments"] if "=" in arg)
        argv = [sys.executable, str(TOOLS / "r3hd_button_prompts.py"), "--game-dir", paths["game_data_root"],
                "--cache", str(Path(paths["cache_root"]) / "button_prompts")]
        if plan["env"].get("R3HD_MODS_PLAN"):
            argv += ["--mods-plan", plan["env"]["R3HD_MODS_PLAN"]]
        result = run(argv, capture_output=True, text=True, check=False)
        data = json.loads(result.stdout)
        if not isinstance(data, dict):
            raise ValueError("invalid artwork result")
        if result.returncode == 0 and data.get("result") == "ok" and data.get("plan"):
            plan["env"]["R3HD_BUTTON_PROMPTS_PLAN"] = data["plan"]
            return
        reason = data.get("reason", "artwork plan unavailable")
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        reason = "artwork plan unavailable"
    note = f"Button prompts: existing artwork retained ({reason})."
    plan.setdefault("notes", []).append(note)
    print(note, file=sys.stderr)


def launch(plan, bin_dir):
    prepare_button_prompt_plan(plan)
    session = Path(plan["session"])
    for name in plan.get("prune_sessions", []):  # M31: only timestamp-named session folders of an installed home
        shutil.rmtree(session.parent / name, ignore_errors=True)
    session.mkdir(parents=True, exist_ok=True)
    (session / "session.json").write_text(json.dumps(plan, indent=1) + "\n", encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k not in TEST_ONLY}
    for k, v in plan["env"].items():
        if v:
            env[k] = v
        else:
            env.pop(k, None)  # empty: the variable stays unset, as in play.ps1
    env["LD_LIBRARY_PATH"] = os.pathsep.join(p for p in (str(bin_dir), os.environ.get("LD_LIBRARY_PATH", "")) if p)
    return subprocess.call([plan["executable"], *plan["arguments"]], env=env, cwd=session)  # play.ps1: -WorkingDirectory $session


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--bin", help="directory with r3hd, librexruntime.so and the GPU plugin (default: HOME/bin)")
    ap.add_argument("--game", help="the extracted game content, holding Default.xex (default: HOME/data/content)")
    ap.add_argument("--home", default=os.path.join(os.environ.get("XDG_DATA_HOME", "~/.local/share"), "r3hd"),
                    help="profiles, cache, sessions, mods and settings.json (default: $XDG_DATA_HOME/r3hd)")
    ap.add_argument("--profile", default="default")
    ap.add_argument("--preset", choices=("vanilla", "hdplus", "custom"))
    ap.add_argument("--settings", help="a settings.json (default: HOME/settings.json when it exists and no --preset)")
    ap.add_argument("--set", action="append", default=[], metavar="KEY=VALUE", help="an explicit setting (wins)")
    ap.add_argument("--key-layout")
    ap.add_argument("--mods", choices=("on", "off"), default="on")
    ap.add_argument("--license", choices=("full", "trial"), default="full")
    ap.add_argument("--no-keyboard", action="store_true")
    ap.add_argument("--dev-overlay", action="store_true")
    ap.add_argument("--log-level", choices=("info", "debug", "warn"), default="info")
    ap.add_argument("--extra", action="append", default=[], help="an extra runtime argument --name=value")
    ap.add_argument("--dry-run", action="store_true", help="print the plan as JSON and start nothing")
    ap.add_argument("--check", action="store_true", help="with --dry-run: also run the preflight checks")
    ap.add_argument("--desktop-entry", action="store_true",
                    help="write the per-user desktop entries (game, Settings) and icons for HOME, then exit")
    ap.add_argument("--remove-desktop-entry", action="store_true",
                    help="remove the desktop entries and icons this home wrote, then exit")
    ap.add_argument("--package", help="with --desktop-entry: your own package file, for the game's icon")
    a = ap.parse_args(argv)
    if a.desktop_entry or a.remove_desktop_entry:
        r = remove_desktop_entry(a.home) if a.remove_desktop_entry else desktop_entry(a.home, package=a.package)
        print("R3HD_PLAY_DESKTOP " + json.dumps(r, sort_keys=True))
        return 0
    try:
        plan = build_plan(a)
    except Refused as e:
        print(f"R3HD_PLAY REFUSED: {e}", file=sys.stderr)
        return 2
    if a.dry_run:
        print(json.dumps(plan, indent=1))
        return 0
    for w in plan["settings"]["warnings"] + plan["notes"]:
        print(f"note: {w}")
    print(f"R3HD_PLAY session={plan['session']} preset={plan['settings']['label']} render={plan['render']} mods={plan['mods']}")
    print(f"In-game PC Settings: {plan['pc_settings']}")
    if plan.get("installed"):
        update_desktop_entry_if_present(a.home)  # E-379: an existing entry follows this home (icon, paths)
    return launch(plan, Path(plan["executable"]).parent)


if __name__ == "__main__":
    sys.exit(main())
