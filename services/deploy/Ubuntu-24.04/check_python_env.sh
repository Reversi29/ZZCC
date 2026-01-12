#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "[ERROR] Run as root (use sudo)." >&2
  exit 1
fi

# Check python3
if command -v python3 >/dev/null 2>&1; then
  echo "[INFO] python3 already installed"
else
  echo "[INFO] Installing python3"
  apt-get update -y
  apt-get install -y python3
fi

# Check PyYAML
if python3 -c 'import yaml' >/dev/null 2>&1; then
  echo "[OK] PyYAML already available"
else
  echo "[INFO] Installing python3-yaml"
  apt-get update -y
  apt-get install -y python3-yaml
  # Verify
  if python3 -c 'import yaml' >/dev/null 2>&1; then
    echo "[OK] PyYAML installed successfully"
  else
    echo "[ERROR] PyYAML installation failed" >&2
    exit 1
  fi
fi

echo "[OK] Python environment ready."
