@echo off
rem Milestone 8 build: replay M2 through M8 at the pinned SDK revision.
rem Retains exception, callback, nonlocal-flow, input and capture regressions; adds the crash-report regression
rem and the M10 keyboard confirm / cancel regression (Escape = pad B); M11 adds the shutdown-order patch and
rem its regression (D-034); M12 adds the host memory patch and its regression (D-038);
rem M13 adds the test-level gate regression (D-040); M15 adds the resolution-chain instrumentation patch and
rem the rendering-resolution regression (D-042); M16 adds the vblank-delivery / achievements-entry patch, the
rem input-gate test and the M16 regression (D-043, D-044, D-045).
rem M17 adds the read-only frame-trace patch and the M17 regression (D-046).
rem M20 adds the staged save-replacement patch, its fault-injection test and the M20 regression (D-049).
rem M21 adds the cursor-rule / time-zone patch, its host test and the M21 regression (D-050).
rem M32 adds the keyboard-map patch (modifier keys, hidden key source), its driver test and the M32 regression (D-069).
rem M31 adds the window-size / video-mode and bounded-diagnostics patch, the r3hd.exe icon and the M31 regression (D-068).
rem M44 adds the optional gameplay voice-subtitle patch (experimental, off by default) and the M44 regression (D-081).
rem M49 adds the keyboard Walk key (m49_runtime_patch.py) and its regression m49_regression.py (D-088).
rem M50 removes the kernel key 0x19 this title cannot use (m50_runtime_patch.py, last in the chain, D-089).
rem M46 builds FFmpeg and libmspack as their own DLLs (m46_runtime_patch.py) and checks them (m46_lgpl.py, D-084).
rem M45 replaces AMD's DXBC checksum by the DXC-derived container hash (m45_runtime_patch.py) and its regression (D-083).
rem M36 adds the grown-VS.sub patch (m36_runtime_patch.py; tests in m33_mod_overlay_test) and the M36 regression (D-073).
rem D-101 / D-102 add r3hd_dualsense_patch.py (last: DualSense light bar / R2, achievement display text and glyphs)
rem and build_r3hd_release_tests.bat (mock-pad policy and display-text tests).
rem D-115 adds r3hd_padmap_patch.py (after it: the controller button map), its host test and r3hd_padmap_regression.py.
rem M23 adds the optional two-layer surface correction patch (off by default), its test and regression (D-052),
rem and the hidden-run haptics safeguard with its test and regression (D-053).
setlocal
cd /d "%~dp0.."
rem Set the toolchain environment once. Calling tools\devenv.bat per step re-runs vcvars,
rem grows PATH each time and makes the fifth call abort silently (E-22).
rem M27: R3HD_VCVARS / R3HD_LLVM_BIN override the pinned install paths (config\build\toolchain.json); a missing
rem toolchain stops the build here instead of failing later without a message.
if not defined R3HD_VCVARS set "R3HD_VCVARS=C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
if not defined R3HD_LLVM_BIN set "R3HD_LLVM_BIN=C:\Program Files\LLVM\bin"
if not exist "%R3HD_VCVARS%" echo M8_BUILD_FAIL vcvars64.bat not found; set R3HD_VCVARS or see tools\r3hd_build_doctor.py & exit /b 1
if not exist "%R3HD_LLVM_BIN%\clang++.exe" echo M8_BUILD_FAIL clang++.exe not found; set R3HD_LLVM_BIN or see tools\r3hd_build_doctor.py & exit /b 1
call "%R3HD_VCVARS%" >nul 2>&1
rem M28 (D-062): R3HD_GAME_DIR = the extracted game data root (default: the developer layout); R3HD_JOBS = parallel
rem compile jobs for every step (default 4 for the SDK and tests, 6 for the game); R3HD_BUILD_MODE=user skips the
rem developer target audit (decrypted-image input) and requires the pinned generated-code digest instead.
if not defined R3HD_GAME_DIR set "R3HD_GAME_DIR=%CD%\private\extracted\5841123F"
set "R3HD_J4=4"
set "R3HD_J6=6"
if defined R3HD_JOBS set "R3HD_J4=%R3HD_JOBS%"
if defined R3HD_JOBS set "R3HD_J6=%R3HD_JOBS%"
set "PATH=%R3HD_LLVM_BIN%;%PATH%"
python tools\m2_runtime_patch.py || exit /b 1
python tools\m3_runtime_patch.py || exit /b 1
python tools\m4_runtime_patch.py || exit /b 1
python tools\m5_runtime_patch.py || exit /b 1
python tools\m6_runtime_patch.py || exit /b 1
python tools\m8_runtime_patch.py || exit /b 1
python tools\m10_runtime_patch.py || exit /b 1
python tools\m11_runtime_patch.py || exit /b 1
python tools\m11_repaint_patch.py || exit /b 1
python tools\m12_runtime_patch.py || exit /b 1
python tools\m15_runtime_patch.py || exit /b 1
python tools\m16_runtime_patch.py || exit /b 1
python tools\m17_runtime_patch.py || exit /b 1
python tools\m20_runtime_patch.py || exit /b 1
python tools\m21_runtime_patch.py || exit /b 1
python tools\m22_runtime_patch.py || exit /b 1
python tools\m23_runtime_patch.py || exit /b 1
python tools\m23_haptics_patch.py || exit /b 1
python tools\m24_runtime_patch.py || exit /b 1
python tools\m26_runtime_patch.py || exit /b 1
python tools\m31_runtime_patch.py || exit /b 1
python tools\m32_runtime_patch.py || exit /b 1
python tools\m33_runtime_patch.py || exit /b 1
python tools\m36_runtime_patch.py || exit /b 1
python tools\m44_runtime_patch.py || exit /b 1
python tools\m45_runtime_patch.py || exit /b 1
python tools\m46_runtime_patch.py || exit /b 1
python tools\m49_runtime_patch.py || exit /b 1
python tools\m50_runtime_patch.py || exit /b 1
python tools\r3hd_dualsense_patch.py || exit /b 1
python tools\r3hd_padmap_patch.py || exit /b 1
rem M29 (D-066): the binaries carry no absolute path of the build machine. Source paths (__FILE__, debug info) are
rem written relative to the repository and the PDB reference is the file name only. A repository path with a space
rem cannot be one compiler argument inside CMAKE_*_FLAGS, so there the map is left out (the binaries then keep it).
set "R3HD_PATHMAP=-ffile-prefix-map=%CD:\=/%=. -ffile-prefix-map=%CD%=."
if not "%CD: =%"=="%CD%" set "R3HD_PATHMAP="
if not defined R3HD_PATHMAP echo M29 note: the repository path contains a space; binaries keep absolute source paths
cmake -S external/rexglue-sdk -B external/rexglue-sdk/out/build/win-amd64 "-DCMAKE_C_FLAGS=-march=x86-64-v2 %R3HD_PATHMAP%" "-DCMAKE_CXX_FLAGS=-march=x86-64-v2 %R3HD_PATHMAP%" "-DCMAKE_SHARED_LINKER_FLAGS=-Wl,/pdbaltpath:%%_PDB%%" "-DCMAKE_EXE_LINKER_FLAGS=-Wl,/pdbaltpath:%%_PDB%%" >nul
if errorlevel 1 exit /b 1
cmake --build external/rexglue-sdk/out/build/win-amd64 --config Release --target rexglue rexgpu-xenos SDL3_test -j %R3HD_J4%
if errorlevel 1 exit /b 1
cmake --install external/rexglue-sdk/out/build/win-amd64 --config Release
if errorlevel 1 exit /b 1
python tools\m2_prepare.py prepare || exit /b 1
python tools\m3_prepare.py || exit /b 1
python tools\m4_prepare.py || exit /b 1
python tools\m5_prepare.py || exit /b 1
python tools\m6_prepare.py || exit /b 1
python tools\m8_prepare.py || exit /b 1
python tools\m10_prepare.py || exit /b 1
python tools\m11_prepare.py || exit /b 1
python tools\m16_prepare.py || exit /b 1
python tools\m18_prepare.py || exit /b 1
python tools\m20_prepare.py || exit /b 1
python tools\m21_prepare.py || exit /b 1
python tools\m23_prepare.py || exit /b 1
python tools\m26_prepare.py || exit /b 1
python tools\m31_prepare.py || exit /b 1
python tools\m32_prepare.py || exit /b 1
python tools\m33_prepare.py || exit /b 1
external\rexglue-sdk\out\win-amd64\Release\rexglue.exe --log-level debug codegen --ignore-stamp private/work/rex/r3hd_manifest.toml
if errorlevel 1 exit /b 1
python tools\m4_validate_emission.py || exit /b 1
python tools\r3hd_build_step.py audit || exit /b 1
cmake -S private/work/rex -B private/work/rex/out/build/win-amd64-release -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_CXX_COMPILER=clang++ "-DCMAKE_PREFIX_PATH=%CD%/external/rexglue-sdk/out/install/win-amd64" "-DCMAKE_CXX_FLAGS=%R3HD_PATHMAP%" "-DCMAKE_EXE_LINKER_FLAGS=-Wl,/pdbaltpath:%%_PDB%%"
if errorlevel 1 exit /b 1
cmake --build private/work/rex/out/build/win-amd64-release --target r3hd -j %R3HD_J6%
if errorlevel 1 exit /b 1
copy /y external\rexglue-sdk\out\install\win-amd64\bin\*.dll private\work\rex\out\build\win-amd64-release\ >nul
cmake --build private/work/rex/out/build/win-amd64-release --target m26_texture_orient_test m23_haptics_test m23_water_test m21_host_test m20_save_commit_test m18_revisit_test m16_sysui_test m10_input_test m8_crash_test m6_input_test m2_nonlocal_test m3_exception_test m4_exception_test m4_generated_test m4_input_test m32_keymap_test m33_mod_overlay_test -j %R3HD_J4%
if errorlevel 1 exit /b 1
private\work\rex\out\build\win-amd64-release\m2_nonlocal_test.exe || exit /b 1
private\work\rex\out\build\win-amd64-release\m3_exception_test.exe || exit /b 1
private\work\rex\out\build\win-amd64-release\m4_exception_test.exe || exit /b 1
private\work\rex\out\build\win-amd64-release\m4_generated_test.exe || exit /b 1
private\work\rex\out\build\win-amd64-release\m4_input_test.exe || exit /b 1
private\work\rex\out\build\win-amd64-release\m6_input_test.exe || exit /b 1
private\work\rex\out\build\win-amd64-release\m10_input_test.exe || exit /b 1
private\work\rex\out\build\win-amd64-release\m16_sysui_test.exe || exit /b 1
private\work\rex\out\build\win-amd64-release\m18_revisit_test.exe || exit /b 1
private\work\rex\out\build\win-amd64-release\m20_save_commit_test.exe || exit /b 1
private\work\rex\out\build\win-amd64-release\m21_host_test.exe || exit /b 1
private\work\rex\out\build\win-amd64-release\m23_water_test.exe || exit /b 1
private\work\rex\out\build\win-amd64-release\m23_haptics_test.exe || exit /b 1
private\work\rex\out\build\win-amd64-release\m26_texture_orient_test.exe || exit /b 1
private\work\rex\out\build\win-amd64-release\m33_mod_overlay_test.exe || exit /b 1
if exist "%R3HD_GAME_DIR%\GAMEDATAbin\fact_55\fact_55_2.btf" private\work\rex\out\build\win-amd64-release\m26_texture_orient_test.exe "%R3HD_GAME_DIR%\GAMEDATAbin\fact_55\fact_55_2.btf" || exit /b 1
rem M30 (D-067): the Settings launcher (tools\launcher; static runtime, no PDB), staged into the installer payload.
call tools\launcher\build_launcher.bat || exit /b 1
python tools\m6_capture_regression.py || exit /b 1
python tools\m8_crash_regression.py || exit /b 1
python tools\m9_license_regression.py || exit /b 1
python tools\m11_shutdown_regression.py || exit /b 1
python tools\m12_memory_regression.py || exit /b 1
python tools\m13_testlevel_regression.py || exit /b 1
python tools\m14_scenario_regression.py || exit /b 1
python tools\m15_resolution_regression.py || exit /b 1
python tools\m16_regression.py || exit /b 1
python tools\m17_regression.py || exit /b 1
python tools\m18_regression.py || exit /b 1
python tools\m20_regression.py || exit /b 1
python tools\m21_regression.py || exit /b 1
python tools\m22_regression.py || exit /b 1
python tools\m23_regression.py || exit /b 1
python tools\m23_haptics_regression.py --binaries || exit /b 1
python tools\m24_regression.py || exit /b 1
python tools\m26_regression.py || exit /b 1
python tools\r3hd_intake.py selftest || exit /b 1
python tools\m27_settings_regression.py || exit /b 1
python tools\r3hd_bootstrap.py selftest || exit /b 1
python tools\r3hd_build_step.py selftest || exit /b 1
python tools\r3hd_release_audit.py selftest || exit /b 1
python tools\m28_portable_regression.py || exit /b 1
python tools\m29_installer_regression.py || exit /b 1
python tools\m30_launcher_regression.py || exit /b 1
python tools\m31_regression.py || exit /b 1
python tools\m32_regression.py || exit /b 1
python tools\r3hd_mods.py selftest || exit /b 1
python tools\m33_regression.py || exit /b 1
python tools\m34_regression.py || exit /b 1
python tools\m35_regression.py || exit /b 1
python tools\m36_regression.py || exit /b 1
python tools\m37_regression.py || exit /b 1
python tools\m38_regression.py || exit /b 1
python tools\m39_regression.py || exit /b 1
python tools\m47_regression.py || exit /b 1
python tools\m43_regression.py || exit /b 1
python tools\m44_regression.py || exit /b 1
python tools\m45_regression.py --build-tree || exit /b 1
python tools\m46_lgpl.py check --build-tree || exit /b 1
python tools\m49_regression.py || exit /b 1
python tools\r3hd_modkit.py selftest || exit /b 1
python tools\r3hd_bundled_mods.py selftest || exit /b 1
call tools\build_discord_test.bat || exit /b 1
call tools\build_release_ux_tests.bat || exit /b 1
call tools\build_r3hd_release_tests.bat || exit /b 1
python tools\release_discord_settings_test.py || exit /b 1
python tools\release_dualsense_settings_test.py || exit /b 1
python tools\r3hd_padmap_regression.py || exit /b 1
echo M8_BUILD_OK
exit /b 0
