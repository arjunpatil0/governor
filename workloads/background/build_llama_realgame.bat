@echo off
rem Builds the sprint-R1 decode driver against STOCK llama.cpp. Optional argument "vulkan" links the separate Vulkan build dir third_party\llama.cpp\build_vk; default is third_party\llama.cpp\build (CUDA).
rem Output: llama_realgame_bench.exe (cuda) or llama_realgame_bench_vk.exe (vulkan). Creates no build dir: a missing build_vk is an error.
call "C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\Auxiliary\Build\vcvars64.bat" >nul
if errorlevel 1 exit /b 1
set L=%~dp0..\..\third_party\llama.cpp
set B=build
set EXE=llama_realgame_bench.exe
if /i "%~1"=="vulkan" (
  set B=build_vk
  set EXE=llama_realgame_bench_vk.exe
)
if not exist "%L%\%B%\src\llama.lib" (
  echo ERROR: %L%\%B%\src\llama.lib not found. The %B% build dir does not exist or is not built; this script does not create it.
  exit /b 1
)
cl /nologo /O2 /EHsc /std:c++17 /I"%L%\include" /I"%L%\ggml\include" "%~dp0llama_realgame_bench.cpp" /Fe:"%~dp0%EXE%" /Fo:"%~dp0llama_realgame_bench.obj" /link /LIBPATH:"%L%\%B%\src" /LIBPATH:"%L%\%B%\ggml\src" llama.lib ggml.lib ggml-base.lib
