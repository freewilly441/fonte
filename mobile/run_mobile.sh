#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$APP_DIR"

if [ ! -d .venv ]; then
  echo ".venv not found. Run mobile/install_termux.sh first."
  exit 1
fi

# shellcheck disable=SC1091
source .venv/bin/activate
exec python fonte_mobile_parallel.py "$@"
