@echo off
setlocal
if not exist private\work\button_prompts mkdir private\work\button_prompts
clang++ -std=c++20 -O2 -DNOMINMAX -Iexternal\rexglue-sdk\out\install\win-amd64\include tools\button_prompt_test.cpp -o private\work\button_prompts\policy_test.exe || exit /b 1
private\work\button_prompts\policy_test.exe %*
exit /b %ERRORLEVEL%
