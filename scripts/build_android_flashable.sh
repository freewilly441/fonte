#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="$ROOT_DIR/dist"
STAGE_DIR="$OUT_DIR/fonte-mobile"
ZIP_PATH="$OUT_DIR/fonte-mobile-flashable.zip"

rm -rf "$STAGE_DIR"
mkdir -p "$STAGE_DIR" "$OUT_DIR"

copy_file() {
  local src="$1"
  cp "$ROOT_DIR/$src" "$STAGE_DIR/$src"
}

mkdir -p "$STAGE_DIR/mobile" "$STAGE_DIR/data/user_docs" "$STAGE_DIR/data/sample_docs"

copy_file "fonte_mobile_parallel.py"
copy_file "kb.py"
copy_file "config.py"
copy_file "utils.py"
copy_file "requirements.txt"
copy_file "README.md"
copy_file "mobile/install_termux.sh"
copy_file "mobile/run_mobile.sh"

if [ -f "$ROOT_DIR/requirements-llm.txt" ]; then
  copy_file "requirements-llm.txt"
fi

(
  cd "$OUT_DIR"
  rm -f "$ZIP_PATH"
  if command -v zip >/dev/null 2>&1; then
    zip -rq "$(basename "$ZIP_PATH")" "$(basename "$STAGE_DIR")"
  else
    python3 -m zipfile -c "$(basename "$ZIP_PATH")" "$(basename "$STAGE_DIR")"
  fi
)

echo "Created $ZIP_PATH"
