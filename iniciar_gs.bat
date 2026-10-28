@echo off
setlocal
cd /d "%~dp0"

set "PYTHON_EXE="
if defined VIRTUAL_ENV if exist "%VIRTUAL_ENV%\Scripts\python.exe" set "PYTHON_EXE=%VIRTUAL_ENV%\Scripts\python.exe"
if not defined PYTHON_EXE if exist "%~dp0.venv\Scripts\python.exe" set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"

if defined PYTHON_EXE (
    "%PYTHON_EXE%" -c "import websockets" >nul 2>nul
) else (
    where py >nul 2>nul
    if errorlevel 1 (
        echo ERRO: Python Launcher ^(py^) nao encontrado. Instala Python 3 e ativa "Add Python to PATH".
        pause
        exit /b 1
    )
    py -3 -c "import websockets" >nul 2>nul
)
if errorlevel 1 (
    echo ERRO: falta a dependencia Python websockets.
    if defined PYTHON_EXE (
        echo Instala-a com: "%PYTHON_EXE%" -m pip install websockets
    ) else (
        echo Instala-a com: py -3 -m pip install websockets
    )
    pause
    exit /b 1
)

echo A iniciar a Ground Station multicansat...
if defined PYTHON_EXE (
    start "CanSat Ground Station" "%PYTHON_EXE%" "%~dp0groundstation.py"
) else (
    start "CanSat Ground Station" py -3 "%~dp0groundstation.py"
)

echo A aguardar que os servidores Web iniciem...
ping -n 3 127.0.0.1 >nul
start "" "http://127.0.0.1:8050"
echo.
echo Confirma que a pagina da Ground Station abriu. Depois executa:
echo "%~dp0simulador\iniciar_simulador.bat"
exit /b 0
