@echo off
rem G6-P39 (D-295): build the 3D editor's narrow OpenGL bridge, tools\scene_gl\r3hd_scene_gl.cpp ->
rem OUT\_r3hd_scene_gl.pyd (default private\work\scene_gl). Same toolchain as the launcher (build_launcher.bat): the
rem pinned LLVM clang-cl / lld-link with the MSVC libraries of config\build\toolchain.json; static C runtime (the only
rem imports are python311.dll and Windows' opengl32 / gdi32 / user32 / kernel32), no PDB, /Brepro, Control Flow
rem Guard. Headers and import library come from the pinned CPython 3.11.4 installation (R3HD_PYTHON_DIR, default:
rem the running python's base prefix), whose python311.dll must equal the payload pin. Alone:
rem   cmd /c tools\scene_gl\build_scene_gl.bat [OUT]
rem Ends with SCENE_GL_BUILD_OK.
setlocal
cd /d "%~dp0..\.."
set "OUT=%~1"
if "%OUT%"=="" set "OUT=private\work\scene_gl"
if not defined R3HD_VCVARS set "R3HD_VCVARS=C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
if not defined R3HD_LLVM_BIN set "R3HD_LLVM_BIN=C:\Program Files\LLVM\bin"
if not exist "%R3HD_LLVM_BIN%\clang-cl.exe" echo SCENE_GL_BUILD_FAIL clang-cl.exe not found; set R3HD_LLVM_BIN & exit /b 1
if not defined R3HD_PYTHON_DIR for /f "delims=" %%P in ('python -c "import sys; print(sys.base_prefix)"') do set "R3HD_PYTHON_DIR=%%P"
python tools\scene_gl\check_python.py "%R3HD_PYTHON_DIR%" || (echo SCENE_GL_BUILD_FAIL the Python headers are not the pinned CPython & exit /b 1)
if not defined VCToolsInstallDir (
  if not exist "%R3HD_VCVARS%" echo SCENE_GL_BUILD_FAIL vcvars64.bat not found; set R3HD_VCVARS & exit /b 1
  call "%R3HD_VCVARS%" >nul 2>&1
)
if not exist "%OUT%" mkdir "%OUT%" || exit /b 1
"%R3HD_LLVM_BIN%\clang-cl.exe" /nologo /std:c++17 /O2 /MT /W4 -Wno-missing-field-initializers /EHsc /GS /guard:cf /DNDEBUG /Brepro ^
  /I "%R3HD_PYTHON_DIR%\include" /Fo"%OUT%\r3hd_scene_gl.obj" /Fe"%OUT%\_r3hd_scene_gl.pyd" /LD ^
  tools\scene_gl\r3hd_scene_gl.cpp -fuse-ld=lld /link /DLL /DEBUG:NONE /INCREMENTAL:NO /Brepro /OPT:REF /OPT:ICF ^
  /GUARD:CF /DYNAMICBASE /HIGHENTROPYVA /NXCOMPAT /LIBPATH:"%R3HD_PYTHON_DIR%\libs" ^
  opengl32.lib gdi32.lib user32.lib || exit /b 1
echo SCENE_GL_BUILD_OK %OUT%\_r3hd_scene_gl.pyd
exit /b 0
