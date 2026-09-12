#!/usr/bin/env bash
# The real-core suite. Builds a Python 3.14 venv with the core version
# hacs.json claims support for, plus the custom-component test harness,
# then runs tests/e2e from inside that directory (its pytest.ini governs).
# Idempotent: the venv is reused when it already exists.
set -euo pipefail
cd "$(dirname "$0")/.."
REPO="$PWD"
FLOOR="$(python3 -c 'import json;print(json.load(open("hacs.json"))["homeassistant"])')"
VENV="${E2E_VENV:-.venv-e2e}"
if [ ! -x "$VENV/bin/python" ]; then
  uv venv -q --python 3.14 "$VENV"
  uv pip install -q --python "$VENV/bin/python" "homeassistant==$FLOOR" pytest-homeassistant-custom-component
fi
cd tests/e2e
exec "$REPO/$VENV/bin/python" -m pytest -p no:cacheprovider "$@"
