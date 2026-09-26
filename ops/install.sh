#!/usr/bin/env bash
# Install vigia systemd units (user mode)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SYSTEMD_USER_DIR="${HOME}/.config/systemd/user"
ENABLE_FLAG=false

# Parse args
while [[ $# -gt 0 ]]; do
    case $1 in
        --enable)
            ENABLE_FLAG=true
            shift
            ;;
        *)
            echo "Unknown option: $1" >&2
            echo "Usage: $0 [--enable]" >&2
            exit 1
            ;;
    esac
done

# Create systemd user directory
mkdir -p "${SYSTEMD_USER_DIR}"

# Copy units
cp "${SCRIPT_DIR}/vigia-run.service" "${SYSTEMD_USER_DIR}/"
cp "${SCRIPT_DIR}/vigia-run.timer" "${SYSTEMD_USER_DIR}/"
cp "${SCRIPT_DIR}/vigia-digest.service" "${SYSTEMD_USER_DIR}/"
cp "${SCRIPT_DIR}/vigia-digest.timer" "${SYSTEMD_USER_DIR}/"

echo "Units installed to ${SYSTEMD_USER_DIR}"

# Reload daemon
systemctl --user daemon-reload
echo "Daemon reloaded"

# Enable if requested
if [[ "${ENABLE_FLAG}" == "true" ]]; then
    systemctl --user enable vigia-run.timer
    systemctl --user enable vigia-digest.timer
    echo "Timers enabled"
    echo "Start with: systemctl --user start vigia-run.timer vigia-digest.timer"
else
    echo "Units installed but not enabled. Use --enable to enable timers."
fi

echo "Check status with: systemctl --user list-timers"
