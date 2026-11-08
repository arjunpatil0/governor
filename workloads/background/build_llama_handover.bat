@echo off
rem v2 sprint 2: builds llama_handover_bench.exe against the PATCHED llama.cpp build (third_party\llama.cpp_v2\build, made by build_llama_v2.bat). The v1 and sprint-1 drivers are not touched.
call "C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\Auxiliary\Build\vcvars64.bat" >nul
if errorlevel 1 exit /b 1
set L=%~dp0..\..\third_party\llama.cpp_v2
cl /nologo /O2 /EHsc /std:c++17 /I"%L%\include" /I"%L%\ggml\include" "%~dp0llama_handover_bench.cpp" /Fe:"%~dp0llama_handover_bench.exe" /Fo:"%~dp0llama_handover_bench.obj" /link /LIBPATH:"%L%\build\src" /LIBPATH:"%L%\build\ggml\src" llama.lib
