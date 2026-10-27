#!/usr/bin/env bash
set -u

# ST-EVA Launcher (macOS)
# Mirrors start-st-eva.bat for Windows.

# If this script is placed beside st_eva_runner.py, use that folder.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$SCRIPT_DIR"
if [ ! -f "$REPO_DIR/st_eva_runner.py" ]; then
  REPO_DIR="/Users/xuxiuwei/git/st-eva"
fi

if [ ! -f "$REPO_DIR/st_eva_runner.py" ]; then
  echo "[ERROR] Cannot find ST-EVA at:"
  echo "        $REPO_DIR"
  echo
  echo "Move this script into the ST-EVA repository root, or edit REPO_DIR near"
  echo "the top of this file to match your local checkout path."
  echo
  read -r -p "Press Enter to exit..."
  exit 1
fi

cd "$REPO_DIR"
URL="http://127.0.0.1:8000"

check_health() {
  curl -sf "$URL/api/health" >/dev/null 2>&1
}

# Reuse an already healthy ST-EVA instance.
if check_health; then
  echo "ST-EVA is already running at $URL"
  open "$URL"
  exit 0
fi

# Prefer a project virtualenv, then python3 on PATH.
PYTHON_EXE=""
if [ -x "$REPO_DIR/.venv/bin/python" ]; then
  PYTHON_EXE="$REPO_DIR/.venv/bin/python"
elif [ -x "$REPO_DIR/venv/bin/python" ]; then
  PYTHON_EXE="$REPO_DIR/venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_EXE="python3"
fi

if [ -z "$PYTHON_EXE" ]; then
  echo "[ERROR] Python was not found. Install Python 3.12, or create a .venv in:"
  echo "        $REPO_DIR"
  read -r -p "Press Enter to exit..."
  exit 1
fi

echo "Using Python: $PYTHON_EXE"

"$PYTHON_EXE" -c "import fastapi, uvicorn, tzdata" >/dev/null 2>&1
if [ $? -ne 0 ]; then
  echo "Installing the ST-EVA web runtime dependencies..."
  "$PYTHON_EXE" -m pip install -r "$REPO_DIR/requirements.txt" "fastapi>=0.110" "uvicorn>=0.27"
  if [ $? -ne 0 ]; then
    echo
    echo "[ERROR] Dependency installation failed. Read the pip error above."
    read -r -p "Press Enter to exit..."
    exit 1
  fi
fi

# Build the frontend SPA when its output is absent.
if [ ! -f "$REPO_DIR/web/frontend/dist/index.html" ]; then
  if ! command -v npm >/dev/null 2>&1; then
    echo "[ERROR] Frontend build is missing and npm was not found."
    echo "Install Node.js LTS, then run this script again."
    read -r -p "Press Enter to exit..."
    exit 1
  fi
  echo "Frontend build not found. Preparing the web UI..."
  pushd "$REPO_DIR/web/frontend" >/dev/null
  if [ ! -f "node_modules/.bin/vite" ]; then
    npm ci
    if [ $? -ne 0 ]; then
      popd >/dev/null
      echo
      echo "[ERROR] npm ci failed. Read the npm error above."
      read -r -p "Press Enter to exit..."
      exit 1
    fi
  fi
  npm run build
  if [ $? -ne 0 ]; then
    popd >/dev/null
    echo
    echo "[ERROR] Frontend build failed. Read the build error above."
    read -r -p "Press Enter to exit..."
    exit 1
  fi
  popd >/dev/null
fi

echo "Starting ST-EVA server at $URL ..."

# Open a dedicated Terminal window running the server (mirrors the .bat's separate console).
osascript - <<EOF >/dev/null 2>&1
tell application "Terminal"
  activate
  do script "cd \"$REPO_DIR\" && \"$PYTHON_EXE\" -m web.app --host 127.0.0.1 --port 8000"
end tell
EOF

echo "Waiting for the server to become ready (up to 45 seconds)..."
WAIT_COUNT=0
while [ $WAIT_COUNT -lt 45 ]; do
  if check_health; then
    break
  fi
  WAIT_COUNT=$((WAIT_COUNT + 1))
  sleep 1
done

if check_health; then
  echo
  echo "ST-EVA is ready: $URL"
  open "$URL"
  echo "Keep the ST-EVA Server terminal window open while using the app."
  echo "To stop ST-EVA, close that server terminal window."
  exit 0
else
  echo
  echo "[ERROR] ST-EVA did not become healthy within 45 seconds."
  echo "Check the ST-EVA Server terminal window for startup errors."
  echo "If port 8000 is occupied by another application, stop that app or change"
  echo "the port in this script and the matching URL."
  read -r -p "Press Enter to exit..."
  exit 1
fi
