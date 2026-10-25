#!/usr/bin/env python3
"""M27 (D-060): resolve the Vanilla / HD+ / Custom presets from config/settings/registry.json.

Precedence, lowest first: the vanilla column -> the preset (or a custom file's base preset) -> a settings
file's overrides (custom only) -> the file's preferences (any preset; M30) -> explicit launcher parameters
(backwards compatibility with play.ps1). Every rule refuses rather than guesses: an unknown preset, key or value,
a newer schema, overrides on a fixed preset, an override of a mandatory setting from a file, a preference that is
not one, or an experimental value without allow_experimental.

M30 (D-067): a setting with "scope": "preference" (display mode, rendering resolution, cursor, save clock) is a
per-installation choice that is the same in every preset. It is stored under "preferences" and kept when the
preset changes. Settings files are written with schema 2; schema 1 files (M27 / M29) stay valid, and a preference
found among a schema 1 file's custom overrides is read as a preference.

M31 (D-068): a preference may carry install_default (written into a brand-new installation's first settings file
only), ui "hidden" (resolved and kept, not shown by the launcher) and requires {other: value} (shown disabled
unless the other setting has that value; the stored value is kept either way).

M32 (D-069): the keyboard map (config/controls/keymap.json) is a preference of its own, outside the visual presets:
a settings file (schema 3) may hold "keyboard": {"layout": L, "keys": {input: [key, key]}} with only the inputs a
person changed. Precedence, highest first: an explicit layout (play.ps1 -KeyLayout; keybind_* in -ExtraArgs win over
everything, in play.ps1) -> the saved keys -> the saved layout -> the keymap's default layout. A saved section that
does not validate never stops a launch or touches the other settings: its layout's (or the default) keys are used and
a warning says why. A new section is refused unless every key is known, not reserved, used once, and every required
input (menu movement, A, B, Start) has a key.

M43 (D-080): "provisional": true marks an HD+ correction the person chose to include before its in-game look (only an
hd_correction whose HD+ value differs from Vanilla); resolving HD+ (or a Custom file on it) then warns that it is
provisional and how to turn it off (-TextureOrient original, or Custom). Vanilla never carries it.

M49 (D-088): the keymap's keyboard-only input "walk" (hold to move slowly) is passed like the pad inputs, with
--mnk_walk_magnitude from the keymap. An input marked "yields" gives its layout keys away to a key a saved section
put on another input (that section was written before the input existed), so an older saved map stays valid.

D-108: "range": {"min": A, "max": B} makes an integer preference (the DualSense trigger strength, a slider in
Settings); load_registry gives it the values "A" ... "B", so files, explicit pairs and play.ps1 carry decimal strings.

usage:
  r3hd_settings.py resolve [--preset P] [--settings FILE] [--explicit KEY=VALUE ...] [--key-layout L]
  r3hd_settings.py write FILE --preset P [--base B] [--set KEY=VALUE ...] [--keep-preferences]
                         [--keyboard LAYOUT [--key INPUT=KEY[,KEY] ...]]
  r3hd_settings.py describe
Exit codes: 0 resolved / written, 2 refused (reason printed), 1 usage error.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "config" / "settings" / "registry.json"
SCHEMA = 1  # the registry's schema
SETTINGS_SCHEMA = 3  # settings files written now (M32: "keyboard"; M30: "preferences"); schema 1 / 2 still read
SETTINGS_READ = (1, 2, 3)
SETTINGS_FIELDS = {1: {"schema", "preset", "base", "overrides", "allow_experimental", "comment"}}
SETTINGS_FIELDS[2] = SETTINGS_FIELDS[1] | {"preferences"}
SETTINGS_FIELDS[3] = SETTINGS_FIELDS[2] | {"keyboard"}
KEYMAP = ROOT / "config" / "controls" / "keymap.json"
KEYMAP_SCHEMA = 1
KEYBOARD_FIELDS = {"layout", "keys"}
SCOPES = ("preset", "preference")
UI_MODES = ("shown", "hidden")
FIXED_PRESETS = ("vanilla", "hdplus")
CATEGORIES = ("mandatory", "platform", "hd_correction", "enhancement", "experimental")


class Refused(Exception):
    def __init__(self, code: str, detail: str):
        super().__init__(f"{code}: {detail}")
        self.code, self.detail = code, detail


def scope(s: dict) -> str:
    return s.get("scope", "preset")


def load_registry(path: Path = REGISTRY) -> dict:
    raw = path.read_bytes()
    reg = json.loads(raw)
    if reg.get("schema") != SCHEMA:
        raise Refused("REGISTRY_SCHEMA", f"registry schema {reg.get('schema')!r}, this resolver reads {SCHEMA}")
    for key, s in reg["settings"].items():
        # D-108: "range" {min, max} = an integer preference (a slider); its values are the decimal strings min..max,
        # so it is stored, validated and passed like any other setting.
        if "range" in s:
            r = s["range"]
            if "values" in s or "value_labels" in s or not all(isinstance(r.get(k), int) and not isinstance(r.get(k), bool)
                                                               for k in ("min", "max")) or r["min"] >= r["max"]:
                raise Refused("REGISTRY_INVALID", f"{key}: a range has integer min < max and no values list")
            s["values"] = [str(v) for v in range(r["min"], r["max"] + 1)]
        if s["category"] not in CATEGORIES:
            raise Refused("REGISTRY_INVALID", f"{key}: category {s['category']!r}")
        for preset in FIXED_PRESETS:
            if s[preset] not in s["values"]:
                raise Refused("REGISTRY_INVALID", f"{key}: {preset} value {s[preset]!r} not among {s['values']}")
        if s["category"] == "mandatory" and s["vanilla"] != s["hdplus"]:
            raise Refused("REGISTRY_INVALID", f"{key}: a mandatory setting is the same in every preset")
        if s["category"] == "experimental" and (s["vanilla"] != s["values"][0] or s["hdplus"] != s["values"][0]):
            raise Refused("REGISTRY_INVALID", f"{key}: an experimental setting is off in both fixed presets")
        if scope(s) not in SCOPES:
            raise Refused("REGISTRY_INVALID", f"{key}: scope {scope(s)!r}")
        if scope(s) == "preference" and (s["category"] in ("mandatory", "experimental") or s["vanilla"] != s["hdplus"]
                                         or s.get("hdplus_candidate")):
            raise Refused("REGISTRY_INVALID", f"{key}: a preference is adjustable and the same in every preset")
        if s.get("provisional") is not None and (s["provisional"] is not True or s["category"] != "hd_correction"
                                                 or s["hdplus"] == s["vanilla"] or s.get("hdplus_candidate")):
            raise Refused("REGISTRY_INVALID", f"{key}: provisional marks an HD+ correction that differs from vanilla")
        labels = s.get("value_labels")
        if labels is not None and sorted(labels) != sorted(s["values"]):
            raise Refused("REGISTRY_INVALID", f"{key}: value_labels must name every value exactly")
        # M31 (D-068)
        if "install_default" in s and (scope(s) != "preference" or s["install_default"] not in s["values"]):
            raise Refused("REGISTRY_INVALID", f"{key}: install_default must be one of a preference's values")
        if "preserve_default" in s and (s["preserve_default"] is not True or scope(s) != "preference"):
            raise Refused("REGISTRY_INVALID", f"{key}: preserve_default is true for a preference only")
        if s.get("ui", "shown") not in UI_MODES:
            raise Refused("REGISTRY_INVALID", f"{key}: ui {s.get('ui')!r}")
        for other, value in (s.get("requires") or {}).items():
            o = reg["settings"].get(other)
            if o is None or value not in o["values"] or other == key:
                raise Refused("REGISTRY_INVALID", f"{key}: requires {other}={value!r}")
    reg["_sha256"] = hashlib.sha256(raw).hexdigest()
    return reg


def by_launcher(reg: dict) -> dict:
    return {s["launcher"]: k for k, s in reg["settings"].items() if s.get("launcher")}


def parse_pairs(pairs, reg: dict, origin: str) -> dict:
    out = {}
    names = by_launcher(reg)
    for pair in pairs or []:
        if "=" not in pair:
            raise Refused("INVALID_PAIR", f"{origin}: {pair!r} is not KEY=VALUE")
        key, value = pair.split("=", 1)
        key = names.get(key, key)  # launcher parameter names are accepted too
        out[key] = value
    return out


def load_settings_file(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise Refused("SETTINGS_UNREADABLE", f"{path}: {e}")
    if not isinstance(data, dict):
        raise Refused("SETTINGS_INVALID", f"{path}: not a JSON object")
    schema = data.get("schema")
    if schema not in SETTINGS_READ or isinstance(schema, bool):
        code = "SETTINGS_NEWER" if isinstance(schema, int) and schema > max(SETTINGS_READ) else "SETTINGS_INVALID"
        raise Refused(code, f"{path}: schema {schema!r}, this resolver reads {', '.join(map(str, SETTINGS_READ))}")
    unknown = set(data) - SETTINGS_FIELDS[schema]
    if unknown:
        raise Refused("SETTINGS_INVALID", f"{path}: unknown fields {sorted(unknown)}")
    return data


def check_value(reg: dict, key: str, value: str, origin: str) -> dict:
    s = reg["settings"].get(key)
    if s is None:
        raise Refused("UNKNOWN_SETTING", f"{origin}: no setting {key!r} (known: {', '.join(sorted(reg['settings']))})")
    if value not in s["values"]:
        raise Refused("INVALID_VALUE", f"{origin}: {key}={value!r}, allowed {s['values']}")
    return s


def resolve(reg: dict, preset: str = None, settings: dict = None, explicit: dict = None,
            key_layout: str = None, keymap: dict = None) -> dict:
    out = resolve_presets(reg, preset, settings, explicit)
    km = keymap or load_keymap()
    out["keyboard"] = resolve_keyboard(km, (settings or {}).get("keyboard"), key_layout)
    out["warnings"] += [f"keyboard: {w}" for w in out["keyboard"]["warnings"]]
    return out


def resolve_presets(reg: dict, preset: str = None, settings: dict = None, explicit: dict = None) -> dict:
    settings = settings or {}
    explicit = explicit or {}
    file_preset = settings.get("preset")
    if preset and file_preset and preset != file_preset:
        raise Refused("PRESET_CONFLICT", f"--preset {preset} but the settings file says {file_preset}")
    name = preset or file_preset or "vanilla"
    if name not in FIXED_PRESETS + ("custom",):
        raise Refused("UNKNOWN_PRESET", f"{name!r}: vanilla, hdplus or custom")
    overrides = settings.get("overrides") or {}
    if not isinstance(overrides, dict):
        raise Refused("SETTINGS_INVALID", "overrides must be an object")
    preferences = settings.get("preferences") or {}
    if not isinstance(preferences, dict):
        raise Refused("SETTINGS_INVALID", "preferences must be an object")
    base = settings.get("base")
    if name in FIXED_PRESETS:
        if overrides or base:
            raise Refused("OVERRIDES_NEED_CUSTOM", f"preset {name} is fixed; use preset custom with base {name}")
        base = name
    else:
        base = base or "vanilla"
        if base not in FIXED_PRESETS:
            raise Refused("UNKNOWN_PRESET", f"custom base {base!r}: vanilla or hdplus")
    allow_exp = settings.get("allow_experimental") is True

    values, sources = {}, {}
    for key, s in reg["settings"].items():
        values[key], sources[key] = s["vanilla"], "vanilla"
        if s[base] != s["vanilla"]:
            values[key], sources[key] = s[base], base
    for key, value in overrides.items():
        s = check_value(reg, key, value, "settings file")
        if s["category"] == "mandatory":
            raise Refused("MANDATORY_SETTING", f"settings file: {key} is not a preference ({s['why']})")
        if s["category"] == "experimental" and value != s["values"][0] and not allow_exp:
            raise Refused("EXPERIMENTAL_NOT_ALLOWED", f"settings file: {key}={value} needs allow_experimental")
        # A schema 1 (M27 / M29) custom file keeps its preferences here; they are read as preferences.
        values[key], sources[key] = value, "preference" if scope(s) == "preference" else "custom"
    for key, value in preferences.items():
        s = check_value(reg, key, value, "settings file preferences")
        if scope(s) != "preference":
            raise Refused("NOT_A_PREFERENCE", f"settings file: {key} belongs to the preset (choose it in Custom)")
        values[key], sources[key] = value, "preference"
    warnings, diagnostic = [], []
    for key, value in explicit.items():
        s = check_value(reg, key, value, "launcher")
        if value != values[key]:
            values[key], sources[key] = value, "explicit"
        if value in s.get("diagnostic_values", []):
            diagnostic.append(key)
            warnings.append(f"{key}={value} is a diagnostic launch, not a preset choice ({s['why']})")
    for key, s in reg["settings"].items():
        if s.get("hdplus_candidate") and base == "hdplus" and values[key] == s["hdplus"]:
            warnings.append(f"{key}: HD+ keeps {s['hdplus']} until its validation passes ({s.get('validation', '')})")
        if s.get("provisional") and base == "hdplus" and values[key] == s["hdplus"]:
            warnings.append(f"{key}: {s['hdplus']} in HD+ is provisional, not yet checked in the game; "
                            f"-{s['launcher']} {s['vanilla']} (or Custom) turns it off")
    if name == "custom" and "custom" not in sources.values():
        # D-090: a Custom file whose overrides are only preferences (e.g. the M48-P gameplay subtitles written as a
        # Custom override on HD+) chooses nothing of its own: it is its base preset.
        name = base
    label = name
    if name in FIXED_PRESETS and any(sources[k] == "explicit" and values[k] != reg["settings"][k][name]
                                     and scope(reg["settings"][k]) == "preset" for k in values):
        label = f"{name}+explicit"
    return {"preset": name, "base": base, "label": label, "values": values, "sources": sources,
            "diagnostic": diagnostic, "warnings": warnings, "registry_sha256": reg["_sha256"], "schema": SCHEMA}


# --- keyboard map (M32, D-069) -------------------------------------------------------------------------------------

def load_keymap(path: Path = KEYMAP) -> dict:
    """config/controls/keymap.json, checked as strictly as the registry: every layout must itself be a valid map."""
    raw = path.read_bytes()
    km = json.loads(raw)
    if km.get("schema") != KEYMAP_SCHEMA:
        raise Refused("KEYMAP_SCHEMA", f"keymap schema {km.get('schema')!r}, this resolver reads {KEYMAP_SCHEMA}")
    groups = [g["key"] for g in km["groups"]]
    ids = [i["id"] for i in km["inputs"]]
    if len(set(ids)) != len(ids) or any(i["group"] not in groups for i in km["inputs"]):
        raise Refused("KEYMAP_INVALID", "inputs: duplicate id or unknown group")
    names, scans = [k["name"] for k in km["keys"]], [s for k in km["keys"] for s in k["scan"]]
    if len(set(names)) != len(names) or len(set(scans)) != len(scans):
        raise Refused("KEYMAP_INVALID", "keys: duplicate name or scan code")
    for s in scans:
        if not (len(s) in (2, 4) and int(s, 16) >= 0 and (len(s) == 2 or s.startswith("E0"))):
            raise Refused("KEYMAP_INVALID", f"keys: scan code {s!r}")
    if not set(km["reserved"]) <= set(names) or not set(km["required"]) <= set(ids):
        raise Refused("KEYMAP_INVALID", "reserved keys and required inputs must be known")
    for key, target in km["fallbacks"].items():
        if key not in names or key in km["reserved"] or target not in ids:
            raise Refused("KEYMAP_INVALID", f"fallback {key} -> {target}")
    if km["default_layout"] not in km["layouts"]:
        raise Refused("KEYMAP_INVALID", f"default layout {km['default_layout']!r}")
    walk = km.get("walk_magnitude", 0.5)
    if not isinstance(walk, (int, float)) or isinstance(walk, bool) or not 0.1 <= walk <= 1.0:
        raise Refused("KEYMAP_INVALID", f"walk_magnitude {walk!r}: a number from 0.1 to 1.0")
    if any(i.get("yields") and i["id"] in km["required"] for i in km["inputs"]):
        raise Refused("KEYMAP_INVALID", "a required input cannot yield its keys")
    km["_names"] = names
    km["_labels"] = {k["name"]: k.get("label", k["name"]) for k in km["keys"]}
    km["_ids"] = ids
    for name, layout in km["layouts"].items():
        if set(layout["keys"]) != set(ids):
            raise Refused("KEYMAP_INVALID", f"layout {name}: it must name every input exactly")
        try:
            check_map(km, {i: slots(km, v, f"layout {name}") for i, v in layout["keys"].items()})
        except Refused as e:
            raise Refused("KEYMAP_INVALID", f"layout {name}: {e.code}: {e.detail}")
    km["_sha256"] = hashlib.sha256(raw).hexdigest()
    return km


def slots(km: dict, value, origin: str) -> list:
    """One input's keys as exactly km['slots'] entries ('' = empty), empties last. Refuses an unknown or reserved
    name, a key named twice for the same input and more keys than slots."""
    if isinstance(value, str):
        value = value.split(",")
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise Refused("KEY_INVALID", f"{origin}: a list of key names is needed, not {value!r}")
    keys = [v.strip() for v in value if v.strip()]
    for k in keys:
        if k not in km["_names"]:
            raise Refused("KEY_UNKNOWN", f"{origin}: {k!r} is not a key the game can read")
        if k in km["reserved"]:
            raise Refused("KEY_RESERVED", f"{origin}: {k} cannot be used ({km['reserved'][k]})")
    if len(set(keys)) != len(keys):
        raise Refused("KEY_REPEATED", f"{origin}: {', '.join(keys)} names a key twice")
    if len(keys) > km["slots"]:
        raise Refused("KEY_TOO_MANY", f"{origin}: at most {km['slots']} keys per input")
    return keys + [""] * (km["slots"] - len(keys))


def input_label(km: dict, input_id: str) -> str:
    i = next(x for x in km["inputs"] if x["id"] == input_id)
    return f"{i['pad']} ({i['action'].split(';')[0].split('.')[0]})"


def check_map(km: dict, keys: dict):
    """A complete map: no key on two inputs (KEY_CONFLICT), a key for every required input (KEY_REQUIRED)."""
    owner = {}
    for input_id in km["_ids"]:
        for k in keys.get(input_id, []):
            if not k:
                continue
            if k in owner:
                raise Refused("KEY_CONFLICT", f"{km['_labels'][k]} is used by both {input_label(km, owner[k])} and "
                                              f"{input_label(km, input_id)}")
            owner[k] = input_id
    for input_id in km["required"]:
        if not any(keys.get(input_id, [])):
            raise Refused("KEY_REQUIRED", f"{input_label(km, input_id)} needs a key: {km['required_why']}")


def layout_keys(km: dict, layout: str) -> dict:
    return {i: slots(km, v, f"layout {layout}") for i, v in km["layouts"][layout]["keys"].items()}


def changed_keys(km: dict, layout: str, changes=None) -> dict:
    """A layout's keys with a person's changes (INPUT -> keys) applied; an input marked "yields" that the changes do
    not name loses a layout key that a changed input now uses (M49). Not checked: see keyboard_section."""
    if layout not in km["layouts"]:
        raise Refused("KEY_LAYOUT_UNKNOWN", f"{layout!r}: one of {', '.join(km['layouts'])}")
    keys = layout_keys(km, layout)
    for input_id, value in (changes or {}).items():
        if input_id not in keys:
            raise Refused("KEY_INPUT_UNKNOWN", f"{input_id!r} is not an input ({', '.join(km['_ids'])})")
        keys[input_id] = slots(km, value, input_label(km, input_id))
    taken = {k for i in (changes or {}) for k in keys[i] if k}
    for i in km["inputs"]:
        if i.get("yields") and i["id"] not in (changes or {}) and taken & set(keys[i["id"]]):
            left = [k for k in keys[i["id"]] if k and k not in taken]
            keys[i["id"]] = left + [""] * (km["slots"] - len(left))
    return keys


def keyboard_section(km: dict, layout: str, changes=None) -> dict:
    """The settings file's keyboard section for a layout and the inputs a person set (INPUT -> keys). Only inputs that
    differ from the layout are stored, so the layout's later corrections still reach unchanged inputs; an input that
    only yielded its key (M49) is not stored either. Refuses an unknown layout or input and any map check_map
    refuses."""
    keys = changed_keys(km, layout, changes)
    check_map(km, keys)
    base = layout_keys(km, layout)
    return {"layout": layout, "keys": {i: [k for k in v if k] for i, v in keys.items()
                                       if i in (changes or {}) and v != base[i]}}


def check_keyboard_section(km: dict, section) -> dict:
    """A stored section as keyboard_section would have written it, or Refused."""
    if not isinstance(section, dict) or not set(section) <= KEYBOARD_FIELDS:
        raise Refused("KEYBOARD_INVALID", f"keyboard must be an object with {sorted(KEYBOARD_FIELDS)}")
    changes = section.get("keys") or {}
    if not isinstance(changes, dict):
        raise Refused("KEYBOARD_INVALID", "keyboard.keys must be an object")
    layout = section.get("layout", km["default_layout"])
    if not isinstance(layout, str):  # M32 review: a hand-edited list / object must be refused, not crash
        raise Refused("KEYBOARD_INVALID", f"keyboard.layout must be a layout name, not {layout!r}")
    return keyboard_section(km, layout, changes)


def keyboard_of(km: dict, settings) -> dict:
    """The valid keyboard section of a settings file, or None (absent or not valid)."""
    if not settings or "keyboard" not in settings:
        return None
    try:
        return check_keyboard_section(km, settings["keyboard"])
    except Refused:
        return None


def resolve_keyboard(km: dict, section=None, explicit_layout: str = None) -> dict:
    """The effective map and the runtime's keybind_* arguments. Never refuses a stored section (see the module
    note); an unknown explicit layout is refused."""
    warnings, state = [], "default"
    if explicit_layout is not None and explicit_layout not in km["layouts"]:
        raise Refused("KEY_LAYOUT_UNKNOWN", f"{explicit_layout!r}: one of {', '.join(km['layouts'])}")
    layout, changes = km["default_layout"], {}
    if section is not None:
        try:
            ok = check_keyboard_section(km, section)
            layout, changes, state = ok["layout"], ok["keys"], "saved"
        except Refused as e:
            state = "invalid"
            if isinstance(section, dict) and isinstance(section.get("layout"), str) and section["layout"] in km["layouts"]:
                layout = section["layout"]
            warnings.append(f"saved keys not used ({e.code}: {e.detail}); the {km['layouts'][layout]['name']} "
                            "keys apply")
    if explicit_layout is not None:
        if explicit_layout != layout or changes:
            warnings.append(f"keyboard layout {explicit_layout} chosen for this launch; the saved keys are not used")
        layout, changes, state = explicit_layout, {}, "explicit"
    keys, sources = changed_keys(km, layout, changes), {i: "layout" for i in km["_ids"]}
    for input_id in changes:
        sources[input_id] = "saved"
    used = {k for v in keys.values() for k in v if k}
    effective = {i: [k for k in v if k] for i, v in keys.items()}
    added = []
    for key, target in km["fallbacks"].items():
        if key not in used:
            effective[target].append(key)
            added.append(f"{key}={target}")
    # Every input is named, so no SDK default key survives; an unbound one gets "None", a name the runtime never
    # matches (ParseVirtualKey -> kNone), rather than an empty value.
    args = [f"--keybind_{i}={','.join(effective[i]) or 'None'}" for i in km["_ids"]] + ["--mnk_modifier_keys=true"]
    args.append(f"--mnk_walk_magnitude={km.get('walk_magnitude', 0.5)}")  # M49 (D-088)
    return {"state": state, "layout": layout, "layout_name": km["layouts"][layout]["name"], "keys": keys,
            "sources": sources, "effective": effective, "fallbacks_added": added, "warnings": warnings, "args": args,
            "keymap_sha256": km["_sha256"]}


def parse_key_pairs(pairs) -> dict:
    out = {}
    for pair in pairs or []:
        if "=" not in pair:
            raise Refused("INVALID_PAIR", f"{pair!r} is not INPUT=KEY[,KEY]")
        input_id, value = pair.split("=", 1)
        out[input_id] = value
    return out


def install_defaults(reg: dict) -> dict:
    """M31 (D-068): the preferences a brand-new installation stores (display=fullscreen). Only the engine's first
    settings file of a new home uses them; an existing settings.json, an upgrade or a repair never does."""
    return {k: s["install_default"] for k, s in reg["settings"].items() if "install_default" in s}


def preferences_of(reg: dict, settings: dict) -> dict:
    """The preferences a settings file holds, schema 1 custom overrides included (M30)."""
    out = {}
    if not settings:
        return out
    for key, value in list((settings.get("overrides") or {}).items()) + list((settings.get("preferences") or {}).items()):
        s = reg["settings"].get(key)
        if s is not None and scope(s) == "preference" and value in s["values"]:
            out[key] = value
    return out


def make_settings(reg: dict, preset: str, base: str = None, pairs=None, allow_experimental=False,
                  keep_preferences=None, keyboard=None) -> dict:
    """A settings file for a preset (M30, D-067). Preference pairs go to "preferences" in every preset, the other
    pairs to the custom overrides; keep_preferences (the current file's) are carried over unless a pair names them;
    a preference equal to its default is not stored unless preserve_default records an explicit choice.
    M32: keyboard is a section
    from keyboard_section (or a kept one); the default layout without changes is not stored."""
    pairs = parse_pairs(pairs, reg, "write")
    prefs = dict(keep_preferences or {})
    overrides = {}
    for key, value in pairs.items():
        s = reg["settings"].get(key)
        if s is not None and scope(s) == "preference":
            prefs[key] = value
        else:
            overrides[key] = value
    for key in list(prefs):
        check_value(reg, key, prefs[key], "write")
        if prefs[key] == reg["settings"][key]["vanilla"] and not reg["settings"][key].get("preserve_default"):
            del prefs[key]
    data = {"schema": SETTINGS_SCHEMA, "preset": preset}
    if preset == "custom":
        data["base"] = base or "vanilla"
        data["overrides"] = overrides
        if allow_experimental:
            data["allow_experimental"] = True
    elif base or overrides:
        raise Refused("OVERRIDES_NEED_CUSTOM", f"preset {preset} is fixed; use preset custom")
    data["preferences"] = dict(sorted(prefs.items()))
    km = load_keymap()
    if keyboard is not None:
        keyboard = check_keyboard_section(km, keyboard)
        if keyboard["layout"] != km["default_layout"] or keyboard["keys"]:
            data["keyboard"] = keyboard
    resolve(reg, settings=data, keymap=km)  # never persist a file that would not resolve
    return data


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("resolve")
    r.add_argument("--preset")
    r.add_argument("--settings", type=Path)
    r.add_argument("--explicit", nargs="*", default=[])
    r.add_argument("--key-layout", help="M32: a keyboard layout for this launch (the saved keys are not used)")
    w = sub.add_parser("write")
    w.add_argument("file", type=Path)
    w.add_argument("--preset", required=True)
    w.add_argument("--base")
    w.add_argument("--set", nargs="*", default=[])
    w.add_argument("--allow-experimental", action="store_true")
    w.add_argument("--keep-preferences", action="store_true", help="carry the existing file's preferences over")
    w.add_argument("--keyboard", help="M32: keyboard layout; with --key the inputs changed from it")
    w.add_argument("--key", nargs="*", default=[], help="INPUT=KEY[,KEY]; an empty value unbinds")
    sub.add_parser("describe")
    a = ap.parse_args()
    try:
        reg = load_registry()
        if a.cmd == "describe":
            for key, s in reg["settings"].items():
                print(f"{key:14} {s['category']:13} {scope(s):10} vanilla={s['vanilla']:9} hdplus={s['hdplus']:9} "
                      f"values={'/'.join(s['values'])} ({s['decision']})")
            return 0
        if a.cmd == "write":
            old = load_settings_file(a.file) if a.file.exists() else None  # replace only a file this resolver reads
            km = load_keymap()
            if a.keyboard:
                keyboard = keyboard_section(km, a.keyboard, parse_key_pairs(a.key))
            elif a.key:
                raise Refused("KEY_LAYOUT_REQUIRED", "--key needs --keyboard LAYOUT")
            else:
                keyboard = keyboard_of(km, old) if a.keep_preferences else None
            data = make_settings(reg, a.preset, a.base, a.set, a.allow_experimental,
                                 preferences_of(reg, old) if a.keep_preferences else None, keyboard)
            tmp = a.file.with_name(a.file.name + ".tmp")
            tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
            tmp.replace(a.file)
            print(f"R3HD_SETTINGS WRITTEN {a.file} preset={data['preset']}", file=sys.stderr)
            return 0
        settings = load_settings_file(a.settings) if a.settings else None
        out = resolve(reg, a.preset, settings, parse_pairs(a.explicit, reg, "launcher"), a.key_layout)
    except Refused as e:
        print(json.dumps({"result": "refused", "code": e.code, "detail": e.detail}))
        print(f"R3HD_SETTINGS REFUSED {e.code}: {e.detail}", file=sys.stderr)
        return 2
    print(json.dumps(dict(result="resolved", **out), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
