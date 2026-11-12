@echo off
call "C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\Auxiliary\Build\vcvars64.bat" >nul
if errorlevel 1 exit /b 1
cd /d "%~dp0llama.cpp"
cmake -S . -B build -G Ninja -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=89 -DCMAKE_CUDA_FLAGS=-allow-unsupported-compiler -DCMAKE_BUILD_TYPE=Release -DLLAMA_CURL=OFF
if errorlevel 1 exit /b 1
cmake --build build --config Release -j 8
