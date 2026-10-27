@echo off
setlocal

set "ROOT=%~dp0"
set "SIM_DIR=%ROOT%simulador"

cd /d "%ROOT%" || exit /b 1

where python >nul 2>nul
if errorlevel 1 (
    echo ERRO: Python nao foi encontrado no PATH.
    echo Instala o Python ou adiciona-o ao PATH e tenta novamente.
    pause
    exit /b 1
)

python -c "import websockets" >nul 2>nul
if errorlevel 1 (
    echo ERRO: A dependencia Python "websockets" nao esta instalada.
    echo Instala-a com: python -m pip install websockets
    pause
    exit /b 1
)

echo A compilar o simulador...
call "%SIM_DIR%\compilar.bat"
if errorlevel 1 (
    echo ERRO: A compilacao falhou. Verifica o GCC e a biblioteca JSON do MSYS2.
    pause
    exit /b 1
)

echo A iniciar a Ground Station numa nova janela...
start "CanSat Ground Station" /D "%ROOT%" cmd.exe /k "set PYTHONUTF8=1 && python -X utf8 groundstation_clean.py"

echo A aguardar que a Ground Station fique pronta...
powershell -NoProfile -Command "$deadline=(Get-Date).AddSeconds(30); while ((Get-Date) -lt $deadline) { $client=New-Object System.Net.Sockets.TcpClient; $ready=$false; try { $client.Connect('127.0.0.1',8050); $ready=$true } catch {} finally { $client.Dispose() }; if ($ready) { exit 0 }; Start-Sleep -Milliseconds 500 }; exit 1" >nul 2>nul
if errorlevel 1 (
    echo ERRO: A Ground Station nao respondeu na porta 8050 em 30 segundos.
    echo Verifica a janela da GS e confirma que a porta 8050 esta livre.
    pause
    exit /b 1
)

start "" "http://127.0.0.1:8050"
echo.
echo A Ground Station esta pronta.
echo Confirma no painel e prime qualquer tecla para iniciar o simulador.
pause >nul

echo A iniciar o simulador. Prime Ctrl+C nesta janela para o parar.
cd /d "%SIM_DIR%" || exit /b 1
"%SIM_DIR%\simulador.exe"
set "SIM_EXIT=%ERRORLEVEL%"

echo.
echo O simulador terminou. Para parar a Ground Station, prime Ctrl+C na janela dela.
pause
exit /b %SIM_EXIT%
