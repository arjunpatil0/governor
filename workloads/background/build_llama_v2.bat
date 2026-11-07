@echo off
rem v2 sprint 1: builds the PATCHED copy of the pinned llama.cpp (third_party\llama.cpp_v2, made by third_party\apply_pause_patch.py) into its own build directory.
rem Same flags as third_party\build_llama.bat. The pinned build (third_party\llama.cpp\build) and the v1 driver exe are not touched.
call "C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\Auxiliary\Build\vcvars64.bat" >nul
if errorlevel 1 exit /b 1
cd /d %~dp0..\..\third_party\llama.cpp_v2
cmake -S . -B build -G Ninja -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=89 -DCMAKE_CUDA_FLAGS=-allow-unsupported-compiler -DCMAKE_BUILD_TYPE=Release -DLLAMA_CURL=OFF
if errorlevel 1 exit /b 1
cmake --build build --config Release -j 8
