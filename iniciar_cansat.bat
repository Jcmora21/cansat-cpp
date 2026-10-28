@echo off
setlocal
cd /d "%~dp0"

if exist "C:\msys64\ucrt64\bin\g++.exe" set "PATH=C:\msys64\ucrt64\bin;%PATH%"

set "PYTHON_EXE="
if defined VIRTUAL_ENV if exist "%VIRTUAL_ENV%\Scripts\python.exe" set "PYTHON_EXE=%VIRTUAL_ENV%\Scripts\python.exe"
if not defined PYTHON_EXE if exist "%~dp0.venv\Scripts\python.exe" set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"

if defined PYTHON_EXE (
    "%PYTHON_EXE%" -c "import websockets" >nul 2>nul
) else (
    where py >nul 2>nul
    if errorlevel 1 (
        echo ERRO: Python Launcher (py) nao encontrado. Instala Python 3 e ativa "Add Python to PATH".
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

call "%~dp0simulador\compilar.bat"
if errorlevel 1 (
    pause
    exit /b 1
)

echo A iniciar a Ground Station multicansat...
if defined PYTHON_EXE (
    start "CanSat Ground Station" "%PYTHON_EXE%" "%~dp0groundstation.py"
) else (
    start "CanSat Ground Station" py -3 "%~dp0groundstation.py"
)
timeout /t 2 /nobreak >nul
start "" "http://127.0.0.1:8050"

echo.
echo Confirma no terminal da Ground Station que os servidores iniciaram.
choice /C SN /N /M "Iniciar agora o simulador multicansat? [S/N] "
if errorlevel 2 goto :end

echo A iniciar os 5 CanSats simulados...
start "Simulador CanSat" "%~dp0simulador\simulador.exe"

:end
echo.
echo A Ground Station continua aberta. Se escolheste N, podes iniciar o simulador mais tarde em:
echo "%~dp0simulador\iniciar_simulador.bat"
pause
exit /b 0
