"""D-199: replay after the existing patch chain; texture-read overlay only."""
from m16_runtime_patch import install
from m8_runtime_patch import patch_once

if __name__ == "__main__":
    install("r3hd_button_prompt_policy.h")
    install("r3hd_button_prompts.h")
    install("r3hd_button_prompts_sdl.h")
    patch_once("src/filesystem/devices/host_path_file.cpp", [
        ("#include <rex/m33_mod_overlay.h>\n",
         "#include <rex/m33_mod_overlay.h>\n#include <rex/r3hd_button_prompts.h>\n"),
    ])
    patch_once("src/filesystem/devices/host_path_file.cpp", [
        ("                         out_bytes_read ? *out_bytes_read : buffer.size());\n"
         "    }\n    return X_STATUS_SUCCESS;\n",
         "                         out_bytes_read ? *out_bytes_read : buffer.size());\n"
         "    }\n"
         "    // D-199: sparse prompt blocks, separate from presets and community mods.\n"
         "    r3hd_prompts::AfterRead(static_cast<HostPathEntry*>(entry())->host_path(), byte_offset,\n"
         "                            buffer.data(), out_bytes_read ? *out_bytes_read : buffer.size(), &M33Log);\n"
         "    return X_STATUS_SUCCESS;\n"),
    ])
    # G6-P43 (D-299): evaluate Auto in the module whose SDL the input driver initialized.
    # rexruntime exports it (WINDOWS_EXPORT_ALL_SYMBOLS); the host's own static SDL copy is never initialized.
    patch_once("src/input/sdl/sdl_input_driver.cpp", [
        ("#include <rex/input/sdl/sdl_input_driver.h>\n",
         "#include <rex/input/sdl/sdl_input_driver.h>\n#include <rex/r3hd_button_prompts_sdl.h>\n"),
        ("}  // namespace rex::input::sdl\n",
         "}  // namespace rex::input::sdl\n"
         "\n"
         "// G6-P43 (D-299): the prompt Auto snapshot must use this module's SDL instance.\n"
         "r3hd_prompts::Style r3hd_prompts::RuntimeLaunchStyle() {\n"
         "  Snapshot seen;\n"
         "  const Style style = LaunchStyle(&seen);\n"
         "  if (seen.queried) {\n"
         "    REXLOG_INFO(\"R3HD prompts auto_identity module=rexruntime sdl_gamepad={} pads={} playstation={} xbox={}\",\n"
         "                seen.initialized ? 1 : 0, seen.pads, seen.playstation, seen.xbox);\n"
         "  }\n"
         "  return style;\n"
         "}\n"),
    ])
