"""G6-P76: source pins of the multi-controller policy in the replayed SDK (read-only).

The behaviour is tested by g6p76_multipad_input_test.cpp (real InputSystem) and g6p76_multipad_sdl_test.cpp (pinned
SDL). This script pins the wiring those tests cannot see: the product input system installs SlotAssignment, the SDL
driver neither deduplicates devices nor uses SDL's player index for guest users, and a removed pad is closed and
erased. A change to any of these is a policy change that needs a decision (G6-P76 report, D-325).

  python tools/g6p76_multipad_regression.py            check the replayed SDK tree
  python tools/g6p76_multipad_regression.py --selftest  mutations of the rules must be rejected
Prints G6P76_MULTIPAD_REGRESSION PASS n/n.
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SDK = ROOT / "external" / "rexglue-sdk"
FILES = {
    "input_system": SDK / "src" / "input" / "input_system.cpp",
    "assignment": SDK / "src" / "input" / "device_assignment.cpp",
    "sdl": SDK / "src" / "input" / "sdl" / "sdl_input_driver.cpp",
    "xam": SDK / "src" / "kernel" / "xam" / "xam_input.cpp",
}


def rules():
    return [
        ("product input system installs SlotAssignment",
         "input_system", lambda s: "input->SetDeviceAssignment(std::make_unique<SlotAssignment>());" in s
         and "make_unique<SharedAssignment>" not in s),
        ("ordinals carried forward, lowest free slot for a new device",
         "input_system", lambda s: "seen[i].ordinal = existing->ordinal;" in s and "while (taken(ordinal))" in s),
        ("merge only within one guest user's devices",
         "input_system", lambda s: s.count("assignment_->DevicesForUser(user_index, ids);") == 4
         and "MergeInto(merged, state);" in s),
        ("vibration goes to the requested user's devices only",
         "input_system", lambda s: re.search(r"SetState\(uint32_t user_index.*?DevicesForUser\(user_index, ids\).*?"
                                             r"SetDeviceVibration\(id, vibration\)", s, re.S) is not None),
        ("host close reaches every driver",
         "input_system", lambda s: re.search(r"OnHostClosing\(\) \{\s*for \(auto& driver : drivers_\) \{\s*"
                                             r"driver->OnHostClosing\(\);", s) is not None),
        ("slot policy: ordinal N feeds user N, synthetic devices user 0",
         "assignment", lambda s: "users_[0].push_back(device.id);" in s
         and "users_[device.ordinal].push_back(device.id);" in s),
        ("SDL driver: every opened gamepad is reported (no deduplication)",
         "sdl", lambda s: re.search(r"for \(const auto& controller : controllers_\) \{\s*DeviceInfo info;", s)
         is not None and "dedup" not in s.lower()),
        ("SDL driver: SDL's player index is not used for guest users",
         "sdl", lambda s: "SDL_GetGamepadPlayerIndex is deliberately ignored" in s
         and "SDL_GetGamepadPlayerIndex(" not in s.replace("SDL_GetGamepadPlayerIndex is", "")),
        ("SDL driver: a removed pad is closed and erased",
         "sdl", lambda s: re.search(r"SDL_CloseGamepad\(controllers_\.at\(\*idx\)\.sdl\);\s*"
                                    r"controllers_\.erase", s) is not None),
        ("SDL driver: a new connection gets a never-reused device id",
         "sdl", lambda s: "state.id = AllocateDeviceId();" in s and "next_device_id_++" in s),
        ("XAM: users 1-3 are answered by the input system (not pinned to user 0)",
         "xam", lambda s: "auto m16_result = is->GetState(actual_user_index, input_state);" in s),
    ]


MUTATIONS = [
    ("input_system", "input->SetDeviceAssignment(std::make_unique<SlotAssignment>());",
     "input->SetDeviceAssignment(std::make_unique<SharedAssignment>());"),
    ("input_system", "seen[i].ordinal = existing->ordinal;", "seen[i].ordinal = 0;"),
    ("assignment", "users_[device.ordinal].push_back(device.id);", "users_[0].push_back(device.id);"),
    ("sdl", "state.id = AllocateDeviceId();", "state.id = static_cast<DeviceId>(1);"),
    ("sdl", "controllers_.erase(controllers_.begin()", "// controllers_.erase(controllers_.begin()"),
    ("xam", "auto m16_result = is->GetState(actual_user_index, input_state);",
     "auto m16_result = is->GetState(0, input_state);"),
]


def evaluate(texts):
    results = []
    for name, key, rule in rules():
        try:
            ok = bool(rule(texts[key]))
        except Exception:  # noqa: BLE001 - a rule that cannot evaluate fails
            ok = False
        results.append((name, ok))
    return results


def main():
    texts = {k: p.read_text(encoding="utf-8", errors="replace") for k, p in FILES.items()}
    results = evaluate(texts)
    for name, ok in results:
        print(("PASS " if ok else "FAIL ") + name)
    passed = sum(ok for _, ok in results)
    rc = 0 if passed == len(results) else 1
    if "--selftest" in sys.argv[1:]:
        rejected = 0
        for key, old, new in MUTATIONS:
            if old not in texts[key]:
                print(f"FAIL mutation anchor missing in {key}: {old[:50]}")
                rc = 1
                continue
            mutated = dict(texts)
            mutated[key] = texts[key].replace(old, new)
            if not all(ok for _, ok in evaluate(mutated)):
                rejected += 1
            else:
                print(f"FAIL mutation accepted: {key}: {new[:50]}")
        print(f"mutations rejected {rejected}/{len(MUTATIONS)}")
        if rejected != len(MUTATIONS):
            rc = 1
    print(f"G6P76_MULTIPAD_REGRESSION {'PASS' if rc == 0 else 'FAIL'} {passed}/{len(results)}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
