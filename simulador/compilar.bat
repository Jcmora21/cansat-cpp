@echo off
setlocal
cd /d "%~dp0"

where g++ >nul 2>nul
if errorlevel 1 (
    if exist "C:\msys64\ucrt64\bin\g++.exe" (
        set "PATH=C:\msys64\ucrt64\bin;%PATH%"
    ) else (
        echo g++ nao encontrado. Instale o MSYS2 e o pacote UCRT64 do GCC.
        exit /b 1
    )
)

g++ -std=c++17 -Wall -Wextra simulador.cpp -o simulador.exe -lws2_32
if errorlevel 1 exit /b %ERRORLEVEL%

echo Compilacao concluida: simulador.exe
endlocal
