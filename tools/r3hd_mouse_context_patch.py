"""Hidden-only read-only XAM context trace, after existing runtime patches.

No enabled mouse input, device output, guest write or generated-code change.
"""
from m16_runtime_patch import install
from m8_runtime_patch import patch_once

if __name__ == "__main__":
    install("r3hd_mouse_context_trace.h")
    patch_once("src/kernel/xam/xam_input.cpp", [
        ("#include <rex/input/input.h>\n", "#include <rex/input/input.h>\n#include <rex/r3hd_mouse_context_trace.h>\n"),
        ("  auto* is = input_system();\n  if (m6input::Enabled()) {\n",
         "  r3hd_mouse_trace::Poll(REX_KERNEL_MEMORY()->virtual_membase(), actual_user_index, bool(input_state));\n"
         "  auto* is = input_system();\n  if (m6input::Enabled()) {\n"),
    ])
