#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  scripts/android_emulator_light.sh build [avd_name]
  scripts/android_emulator_light.sh start [avd_name]
  scripts/android_emulator_light.sh import <archive_or_avd_dir>
  scripts/android_emulator_light.sh list

Environment overrides:
  ANDROID_SDK_ROOT   Android SDK location (default: $HOME/Android/Sdk)
  AVD_NAME           Default AVD name (default: fonte-lite)
  API_LEVEL          Android API level for build (default: 24)
  ABI                ABI for build (default: x86_64)
  DEVICE_PROFILE     avdmanager device profile (default: pixel)

Examples:
  scripts/android_emulator_light.sh build
  scripts/android_emulator_light.sh start fonte-lite
  scripts/android_emulator_light.sh import ./backups/fonte-lite-avd.tar.gz
EOF
}

ANDROID_SDK_ROOT="${ANDROID_SDK_ROOT:-${ANDROID_HOME:-$HOME/Android/Sdk}}"
AVD_NAME="${AVD_NAME:-fonte-lite}"
API_LEVEL="${API_LEVEL:-24}"
ABI="${ABI:-x86_64}"
DEVICE_PROFILE="${DEVICE_PROFILE:-pixel}"
ANDROID_AVD_HOME="${ANDROID_AVD_HOME:-$HOME/.android/avd}"

SDKMANAGER_BIN="${ANDROID_SDK_ROOT}/cmdline-tools/latest/bin/sdkmanager"
AVDMANAGER_BIN="${ANDROID_SDK_ROOT}/cmdline-tools/latest/bin/avdmanager"
EMULATOR_BIN="${ANDROID_SDK_ROOT}/emulator/emulator"

require_file() {
  local path="$1"
  local label="$2"
  if [ ! -x "$path" ]; then
    echo "Missing ${label}: $path"
    echo "Install Android command-line tools first, then retry."
    exit 1
  fi
}

ensure_dirs() {
  mkdir -p "$ANDROID_AVD_HOME"
}

avd_config_path() {
  local name="$1"
  echo "$ANDROID_AVD_HOME/${name}.avd/config.ini"
}

apply_light_config() {
  local config_path="$1"
  touch "$config_path"

  upsert_cfg() {
    local key="$1"
    local value="$2"
    if grep -q "^${key}=" "$config_path"; then
      sed -i "s|^${key}=.*|${key}=${value}|" "$config_path"
    else
      echo "${key}=${value}" >>"$config_path"
    fi
  }

  upsert_cfg "hw.ramSize" "1024"
  upsert_cfg "vm.heapSize" "128"
  upsert_cfg "hw.cpu.ncore" "1"
  upsert_cfg "disk.dataPartition.size" "2048M"
  upsert_cfg "hw.lcd.density" "240"
  upsert_cfg "skin.name" "480x800"
  upsert_cfg "showDeviceFrame" "no"
  upsert_cfg "fastboot.forceColdBoot" "yes"
  upsert_cfg "fastboot.forceFastBoot" "no"
  upsert_cfg "hw.gpu.enabled" "yes"
  upsert_cfg "hw.gpu.mode" "swiftshader_indirect"
}

build_avd() {
  local name="${1:-$AVD_NAME}"
  local image="system-images;android-${API_LEVEL};default;${ABI}"

  require_file "$SDKMANAGER_BIN" "sdkmanager"
  require_file "$AVDMANAGER_BIN" "avdmanager"

  ensure_dirs
  yes | "$SDKMANAGER_BIN" --sdk_root="$ANDROID_SDK_ROOT" \
    "platform-tools" "emulator" "$image" >/dev/null

  if "$AVDMANAGER_BIN" list avd | grep -q "Name: ${name}$"; then
    echo "AVD '$name' already exists. Reusing it."
  else
    echo "no" | "$AVDMANAGER_BIN" --verbose create avd \
      --force \
      --name "$name" \
      --package "$image" \
      --device "$DEVICE_PROFILE" >/dev/null
  fi

  apply_light_config "$(avd_config_path "$name")"
  echo "Built lightweight emulator: $name"
}

start_avd() {
  local name="${1:-$AVD_NAME}"
  require_file "$EMULATOR_BIN" "emulator"
  "$EMULATOR_BIN" -avd "$name" \
    -no-snapshot \
    -no-boot-anim \
    -no-audio \
    -gpu swiftshader_indirect \
    -memory 1024
}

import_avd() {
  local src="${1:-}"
  if [ -z "$src" ]; then
    echo "Missing source path for import."
    usage
    exit 1
  fi

  ensure_dirs

  if [ -d "$src" ] && [[ "$src" == *.avd ]]; then
    local base
    base="$(basename "$src")"
    local name="${base%.avd}"
    cp -r "$src" "$ANDROID_AVD_HOME/$base"
    if [ -f "${src%.avd}.ini" ]; then
      cp "${src%.avd}.ini" "$ANDROID_AVD_HOME/${name}.ini"
    elif [ -f "$(dirname "$src")/${name}.ini" ]; then
      cp "$(dirname "$src")/${name}.ini" "$ANDROID_AVD_HOME/${name}.ini"
    else
      echo "Warning: ${name}.ini not found; emulator may not list this AVD."
    fi
    apply_light_config "$(avd_config_path "$name")"
    echo "Imported AVD directory: $name"
    return
  fi

  case "$src" in
    *.tar.gz|*.tgz)
      tar -xzf "$src" -C "$ANDROID_AVD_HOME"
      ;;
    *.zip)
      if command -v unzip >/dev/null 2>&1; then
        unzip -oq "$src" -d "$ANDROID_AVD_HOME"
      else
        echo "unzip is required to import zip archives."
        exit 1
      fi
      ;;
    *)
      echo "Unsupported import format: $src"
      echo "Use a .avd directory, .tar.gz/.tgz, or .zip archive."
      exit 1
      ;;
  esac

  local imported
  imported="$(find "$ANDROID_AVD_HOME" -maxdepth 1 -type d -name '*.avd' -printf '%f\n' | sed 's/\.avd$//' | tail -n 1 || true)"
  if [ -n "$imported" ]; then
    apply_light_config "$(avd_config_path "$imported")"
    echo "Imported AVD archive; detected emulator: $imported"
  else
    echo "Import completed, but no .avd directory was detected in $ANDROID_AVD_HOME."
  fi
}

list_avd() {
  require_file "$AVDMANAGER_BIN" "avdmanager"
  "$AVDMANAGER_BIN" list avd
}

main() {
  local cmd="${1:-}"
  case "$cmd" in
    build)
      build_avd "${2:-$AVD_NAME}"
      ;;
    start)
      start_avd "${2:-$AVD_NAME}"
      ;;
    import)
      import_avd "${2:-}"
      ;;
    list)
      list_avd
      ;;
    *)
      usage
      exit 1
      ;;
  esac
}

main "$@"
