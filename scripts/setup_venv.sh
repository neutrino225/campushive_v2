#!/usr/bin/env bash
# Setup script to create and populate a Python venv for this project.
# Usage:
#   ./scripts/setup_venv.sh [--venv-dir .venv] [--python python3] [--pin-chromadb 0.5.2] [--freeze]
#
# Examples:
#   ./scripts/setup_venv.sh --venv-dir .venv
#   ./scripts/setup_venv.sh --pin-chromadb 0.5.2 --freeze

set -euo pipefail

VENV_DIR=".venv"
PYTHON="python3"
PIN_CHROMADB=""
FREEZE="false"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --venv-dir)
      VENV_DIR="$2"; shift 2;;
    --python)
      PYTHON="$2"; shift 2;;
    --pin-chromadb)
      PIN_CHROMADB="$2"; shift 2;;
    --freeze)
      FREEZE="true"; shift 1;;
    -h|--help)
      echo "Usage: $0 [--venv-dir .venv] [--python python3] [--pin-chromadb <version>] [--freeze]"; exit 0;;
    *)
      echo "Unknown arg: $1"; exit 1;;
  esac
done

echo "Creating venv at $VENV_DIR using $PYTHON"
$PYTHON -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"

echo "Upgrading pip, setuptools, wheel"
python -m pip install --upgrade pip setuptools wheel

echo "Installing requirements from requirements.txt"
pip install -r requirements.txt

if [[ -n "$PIN_CHROMADB" ]]; then
  echo "Pinning chromadb to $PIN_CHROMADB"
  pip install --force-reinstall "chromadb==${PIN_CHROMADB}"
fi

if [[ "$FREEZE" == "true" ]]; then
  echo "Generating requirements-locked.txt"
  pip freeze > requirements-locked.txt
  echo "Wrote requirements-locked.txt"
fi

echo "Done. Activate your venv with: source $VENV_DIR/bin/activate"
