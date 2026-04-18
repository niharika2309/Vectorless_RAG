#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_HOST="127.0.0.1"
BACKEND_PORT="8000"
FRONTEND_HOST="127.0.0.1"
FRONTEND_PORT="8501"
PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
# Resolve streamlit using the *system* python3 (not the venv) so we find the
# user-installed binary regardless of whether the venv is currently activated.
_SYS_PY3="/usr/bin/python3"
STREAMLIT_BIN="$($_SYS_PY3 -m site --user-base 2>/dev/null)/bin/streamlit"
if [[ ! -x "$STREAMLIT_BIN" ]]; then
  STREAMLIT_BIN="$_SYS_PY3 -m streamlit"
fi
BACKEND_LOG="$ROOT_DIR/.run_backend.log"
FRONTEND_LOG="$ROOT_DIR/.run_streamlit.log"
ONCE_MODE=0

if [[ "${1:-}" == "--once" ]]; then
  ONCE_MODE=1
fi

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "[error] Missing Python virtualenv at $PYTHON_BIN"
  echo "        Create it first, e.g. python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
  exit 1
fi

BACKEND_PID=""
STREAMLIT_PID=""
STARTED_BACKEND=0
STARTED_FRONTEND=0

cleanup() {
  set +e
  if [[ "$STARTED_BACKEND" -eq 1 ]] && [[ -n "$BACKEND_PID" ]] && kill -0 "$BACKEND_PID" 2>/dev/null; then
    kill "$BACKEND_PID" 2>/dev/null
  fi
  if [[ "$STARTED_FRONTEND" -eq 1 ]] && [[ -n "$STREAMLIT_PID" ]] && kill -0 "$STREAMLIT_PID" 2>/dev/null; then
    kill "$STREAMLIT_PID" 2>/dev/null
  fi
}

trap cleanup EXIT INT TERM

wait_for_http() {
  local url="$1"
  local label="$2"
  local timeout_seconds="${3:-60}"

  echo "[wait] $label -> $url"
  for ((i=1; i<=timeout_seconds; i++)); do
    if "$PYTHON_BIN" -c 'import sys, urllib.request; req = urllib.request.Request(sys.argv[1], method="GET"); resp = urllib.request.urlopen(req, timeout=3); raise SystemExit(0 if 200 <= resp.status < 500 else 1)' "$url" >/dev/null 2>&1
    then
      echo "[ok] $label is reachable"
      return 0
    fi
    sleep 1
  done

  echo "[error] Timed out waiting for $label"
  if [[ "$label" == "backend" ]] && [[ -f "$BACKEND_LOG" ]]; then
    echo "[error] Last backend log lines:"
    tail -n 20 "$BACKEND_LOG" || true
  fi
  if [[ "$label" == "frontend" ]] && [[ -f "$FRONTEND_LOG" ]]; then
    echo "[error] Last Streamlit log lines:"
    tail -n 20 "$FRONTEND_LOG" || true
  fi
  return 1
}

run_smoke_tests() {
  echo "[test] Running smoke checks"
  "$PYTHON_BIN" -c 'import sys, urllib.request
backend_host, backend_port, frontend_host, frontend_port = sys.argv[1:5]
checks = [
    (f"http://{backend_host}:{backend_port}/docs", "backend /docs"),
    (f"http://{frontend_host}:{frontend_port}", "streamlit /"),
]
for url, label in checks:
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=10) as resp:
        if not (200 <= resp.status < 400):
            raise SystemExit(f"[fail] {label} returned status {resp.status}")
        print(f"[pass] {label} status={resp.status}")
print("[pass] Smoke checks completed")' "$BACKEND_HOST" "$BACKEND_PORT" "$FRONTEND_HOST" "$FRONTEND_PORT"
}

is_reachable() {
  local url="$1"
  "$PYTHON_BIN" -c 'import sys, urllib.request; req = urllib.request.Request(sys.argv[1], method="GET"); urllib.request.urlopen(req, timeout=1)' "$url" >/dev/null 2>&1
}

if is_reachable "http://$BACKEND_HOST:$BACKEND_PORT/docs"; then
  echo "[reuse] Backend already running on $BACKEND_HOST:$BACKEND_PORT"
else
  echo "[start] Backend server"
  cd "$ROOT_DIR"
  "$PYTHON_BIN" -m uvicorn main:app --host "$BACKEND_HOST" --port "$BACKEND_PORT" >"$BACKEND_LOG" 2>&1 &
  BACKEND_PID=$!
  STARTED_BACKEND=1
fi

if is_reachable "http://$FRONTEND_HOST:$FRONTEND_PORT"; then
  echo "[reuse] Streamlit already running on $FRONTEND_HOST:$FRONTEND_PORT"
else
  echo "[start] Streamlit UI"
  cd "$ROOT_DIR"
  $STREAMLIT_BIN run streamlit_app.py \
    --server.address "$FRONTEND_HOST" \
    --server.port "$FRONTEND_PORT" \
    --server.headless true \
    >"$FRONTEND_LOG" 2>&1 &
  STREAMLIT_PID=$!
  STARTED_FRONTEND=1
fi

cd "$ROOT_DIR"

wait_for_http "http://$BACKEND_HOST:$BACKEND_PORT/docs" "backend" 45
wait_for_http "http://$FRONTEND_HOST:$FRONTEND_PORT" "frontend" 75
run_smoke_tests

echo "[done] Backend log:   $BACKEND_LOG"
echo "[done] Streamlit log: $FRONTEND_LOG"

if [[ "$ONCE_MODE" -eq 1 ]]; then
  echo "[done] --once mode enabled. Stopping services."
  exit 0
fi

echo "[serve] Services are running. Press Ctrl+C to stop both."
wait
