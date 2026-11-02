#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
if [ -f .env ]; then
  set -a
  source .env
  set +a
fi
: "${H3_COMFY_URL:?Set H3_COMFY_URL in .env}"
export H3_COMFY_URL
export H3_HOST="${H3_HOST:-0.0.0.0}"
: "${H3_PORT:?Set H3_PORT in .env}"
export H3_PORT
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
fi
.venv/bin/python -m pip install -r requirements-macos.txt
(cd web && npm ci && npm run build)
export H3_WEB_DIST="$PWD/web/dist"
exec .venv/bin/python server/app.py
