@echo off
rem Sets up MSVC libs/SDK + LLVM clang + ninja for building the pinned external tools.
call "C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\Auxiliary\Build\vcvars64.bat" >nul 2>&1
set "PATH=C:\Program Files\LLVM\bin;%PATH%"
%*
