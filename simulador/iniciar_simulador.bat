@echo off
setlocal
cd /d "%~dp0"

if exist "C:\msys64\ucrt64\bin\g++.exe" set "PATH=C:\msys64\ucrt64\bin;%PATH%"

where g++ >nul 2>nul
if errorlevel 1 (
    echo ERRO: g++ nao encontrado. Instala o MSYS2 UCRT64 com g++ e nlohmann-json.
    echo Se o MSYS2 estiver noutra pasta, adiciona ucrt64\bin ao PATH.
    pause
    exit /b 1
)

echo A compilar o simulador multicansat...
g++ -std=c++17 -O2 -Wall -Wextra simulador.cpp -o simulador.exe -lws2_32
if errorlevel 1 (
    echo ERRO: compilacao falhou.
    pause
    exit /b 1
)

echo Compilacao concluida. A iniciar os cinco CanSats...
echo Para terminar a simulacao, prime Ctrl+C.
simulador.exe %*
