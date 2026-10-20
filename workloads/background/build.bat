@echo off
rem Usage: build.bat <src.cu> <out.exe>   -- always sm_89 (RTX 4070 Laptop), never a CPU fallback
call "C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\Auxiliary\Build\vcvars64.bat" >nul
if errorlevel 1 exit /b 1
nvcc -arch=sm_89 -O3 -lineinfo -allow-unsupported-compiler %3 %4 %5 "%~1" -o "%~2"
