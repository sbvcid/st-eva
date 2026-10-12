@echo off
setlocal EnableExtensions
chcp 65001 >nul

title ST-EVA Launcher

rem If this BAT is placed beside st_eva_runner.py, use that folder.
rem Otherwise use the known local checkout path.
set "REPO_DIR="
if exist "%~dp0st_eva_runner.py" set "REPO_DIR=%~dp0"
if not defined REPO_DIR set "REPO_DIR=C:\git\st-eva"

if not exist "%REPO_DIR%\st_eva_runner.py" (
  echo [ERROR] Cannot find ST-EVA at:
  echo         "%REPO_DIR%"
  echo.
  echo Move this BAT into the ST-EVA repository root, or edit REPO_DIR near
  echo the top of this file to match your local checkout path.
  echo.
  pause
  exit /b 1
)

cd /d "%REPO_DIR%"
set "URL=http://127.0.0.1:8000"

rem If ST-EVA is already healthy on the default port, reuse it.
call :CHECK_HEALTH
if not errorlevel 1 (
  echo ST-EVA is already running at %URL%
  start "" "%URL%"
  exit /b 0
)

rem Prefer a project virtual environment, then Python 3.12 via the Windows launcher,
rem then the Python executable available on PATH.
set "PYTHON_EXE="
set "PYTHON_ARGS="
if exist "%REPO_DIR%\.venv\Scripts\python.exe" set "PYTHON_EXE=%REPO_DIR%\.venv\Scripts\python.exe"
if not defined PYTHON_EXE if exist "%REPO_DIR%\venv\Scripts\python.exe" set "PYTHON_EXE=%REPO_DIR%\venv\Scripts\python.exe"

if not defined PYTHON_EXE (
  where py.exe >nul 2>&1
  if not errorlevel 1 (
    py -3.12 -c "import sys" >nul 2>&1
    if not errorlevel 1 (
      set "PYTHON_EXE=py"
      set "PYTHON_ARGS=-3.12"
    )
  )
)

if not defined PYTHON_EXE (
  for /f "delims=" %%P in ('where python.exe 2^>nul') do if not defined PYTHON_EXE set "PYTHON_EXE=%%P"
)

if not defined PYTHON_EXE (
  echo [ERROR] Python was not found. Install Python 3.12, or create a .venv in:
  echo         "%REPO_DIR%"
  pause
  exit /b 1
)

echo Using Python: %PYTHON_EXE% %PYTHON_ARGS%
"%PYTHON_EXE%" %PYTHON_ARGS% -c "import fastapi, uvicorn, tzdata" >nul 2>&1
if errorlevel 1 (
  echo Installing the ST-EVA web runtime dependencies...
  "%PYTHON_EXE%" %PYTHON_ARGS% -m pip install -r "%REPO_DIR%\requirements.txt" "fastapi>=0.110" "uvicorn>=0.27"
  if errorlevel 1 (
    echo.
    echo [ERROR] Dependency installation failed. Read the pip error above.
    pause
    exit /b 1
  )
)

rem The FastAPI app serves the built SPA. Build it only when its output is absent.
if not exist "%REPO_DIR%\web\frontend\dist\index.html" (
  where npm.cmd >nul 2>&1
  if errorlevel 1 (
    echo [ERROR] Frontend build is missing and npm was not found.
    echo Install Node.js LTS, then run this BAT again.
    pause
    exit /b 1
  )
  echo Frontend build not found. Preparing the web UI...
  pushd "%REPO_DIR%\web\frontend"
  if not exist "node_modules\vite\bin\vite.js" (
    call npm ci
    if errorlevel 1 (
      popd
      echo.
      echo [ERROR] npm ci failed. Read the npm error above.
      pause
      exit /b 1
    )
  )
  call npm run build
  if errorlevel 1 (
    popd
    echo.
    echo [ERROR] Frontend build failed. Read the build error above.
    pause
    exit /b 1
  )
  popd
)

echo Starting ST-EVA server at %URL% ...
start "ST-EVA Server" /D "%REPO_DIR%" cmd /k ""%PYTHON_EXE%" %PYTHON_ARGS% -m web.app --host 127.0.0.1 --port 8000"

echo Waiting for the server to become ready (up to 45 seconds)...
set "WAIT_COUNT=0"
:WAIT_FOR_SERVER
call :CHECK_HEALTH
if not errorlevel 1 goto SERVER_READY
set /a WAIT_COUNT+=1
if %WAIT_COUNT% GEQ 45 goto SERVER_TIMEOUT
timeout /t 1 /nobreak >nul
goto WAIT_FOR_SERVER

:SERVER_READY
echo.
echo ST-EVA is ready: %URL%
start "" "%URL%"
echo Keep the "ST-EVA Server" console window open while using the app.
echo To stop ST-EVA, close that server console window.
exit /b 0

:SERVER_TIMEOUT
echo.
echo [ERROR] ST-EVA did not become healthy within 45 seconds.
echo Check the separate "ST-EVA Server" window for startup errors.
echo If port 8000 is occupied by another application, stop that app or change
 echo the port in this BAT and the matching URL.
pause
exit /b 1

:CHECK_HEALTH
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r = Invoke-RestMethod -Uri '%URL%/api/health' -TimeoutSec 2; if ($r.status -eq 'ok') { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1
if errorlevel 1 exit /b 1
exit /b 0
