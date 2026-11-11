@echo off
call "C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\Auxiliary\Build\vcvars64.bat" >nul
if errorlevel 1 exit /b 11
cd /d C:\Users\arjun\governor\third_party\llama.cpp
cmake -S . -B build_vk -G Ninja -DGGML_VULKAN=ON -DCMAKE_BUILD_TYPE=Release -DLLAMA_CURL=OFF -DGGML_NATIVE=OFF -DGGML_AVX2=ON -DGGML_FMA=ON -DGGML_F16C=ON
if errorlevel 1 exit /b 12
cmake --build build_vk --config Release -j 8
exit /b %errorlevel%
