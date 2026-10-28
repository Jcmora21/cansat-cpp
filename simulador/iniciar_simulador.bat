@echo off
setlocal
cd /d "%~dp0"

if exist "C:\msys64\ucrt64\bin\g++.exe" set "PATH=C:\msys64\ucrt64\bin;%PATH%"
if not exist "simulador.exe" (
    call compilar.bat
    if errorlevel 1 exit /b 1
)

simulador.exe %*
