@echo off
setlocal
cd /d "%~dp0"

where g++ >nul 2>nul
if errorlevel 1 if exist "C:\msys64\ucrt64\bin\g++.exe" set "PATH=C:\msys64\ucrt64\bin;%PATH%"
where g++ >nul 2>nul
if errorlevel 1 (
    echo ERRO: g++ nao encontrado.
    echo Instala o MSYS2 UCRT64 com g++ e nlohmann-json e adiciona ucrt64\bin ao PATH.
    exit /b 1
)

echo A compilar o simulador multicansat...
g++ -std=c++17 -O2 -Wall -Wextra simulador.cpp -o simulador.exe -lws2_32
if errorlevel 1 (
    echo ERRO: compilacao falhou.
    exit /b 1
)

echo Compilacao concluida: simulador.exe
exit /b 0
