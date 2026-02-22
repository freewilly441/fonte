#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

ROOT_DIR="${1:-$HOME/fonte}"
PYTHON_BIN="${PYTHON_BIN:-python}"

echo "Installing Fonte mobile package into: $ROOT_DIR"
mkdir -p "$ROOT_DIR"
cp -r . "$ROOT_DIR/"
cd "$ROOT_DIR"

if command -v pkg >/dev/null 2>&1; then
  pkg update -y
  pkg install -y python clang cmake make
fi

"$PYTHON_BIN" -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo "Install complete."
echo "Run with: cd $ROOT_DIR && source .venv/bin/activate && python fonte_mobile_parallel.py init"
