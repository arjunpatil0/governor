@echo off
rem Builds the governed llama.cpp decode driver (pacing + shared-memory control) against the pinned source build (third_party\llama.cpp\build). MSVC C++ only; the GPU work is in llama.cpp's CUDA backend.
call "C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\Auxiliary\Build\vcvars64.bat" >nul
set L=%~dp0..\..\third_party\llama.cpp
cl /nologo /O2 /EHsc /std:c++17 /I"%L%\include" /I"%L%\ggml\include" /I"%~dp0." "%~dp0llama_governed_bench.cpp" /Fe:"%~dp0llama_governed_bench.exe" /Fo:"%~dp0llama_governed_bench.obj" /link /LIBPATH:"%L%\build\src" /LIBPATH:"%L%\build\ggml\src" llama.lib
