#!/bin/bash
# One-time migration shim: upgrades from bash-based to pip-based CAVE CLI.
# This file lives at the repo root so that a legacy `cave update` (git pull)
# replaces ~/.cave_cli/cave.sh with this script. The next time the user runs
# any `cave` command, migration runs automatically.

readonly CAVE_PATH="${HOME}/.cave_cli"
readonly BIN_DIR="/usr/local/bin"
readonly CHAR_LINE="============================="
readonly PIP_INSTALL_SPEC="cave_cli"

_info()  { printf "INFO: %s\n"  "$1"; }
_warn()  { printf "WARN: %s\n"  "$1"; }
_error() { printf "ERROR: %s\n" "$1"; }

printf "%s\n" "$CHAR_LINE"
_info "The CAVE CLI has migrated to a pip-based installation."
_info "Running one-time migration..."
printf "%s\n\n" "$CHAR_LINE"

# Find a usable pip
if python3 -m pip --version &>/dev/null 2>&1; then
    PIP="python3 -m pip"
elif command -v pip3 &>/dev/null; then
    PIP="pip3"
elif command -v pip &>/dev/null; then
    PIP="pip"
else
    _error "pip not found. Please install Python 3 with pip, then run:"
    _error "  pip install '${PIP_INSTALL_SPEC}'"
    _error "Then remove the old symlink:"
    _error "  sudo rm ${BIN_DIR}/cave"
    exit 1
fi

_info "Installing pip-based CAVE CLI..."
$PIP install "${PIP_INSTALL_SPEC}" --user
if [ $? -ne 0 ]; then
    _error "Installation failed. Please try manually:"
    _error "  $PIP install '${PIP_INSTALL_SPEC}'"
    exit 1
fi

_info "Removing old CLI symlink (${BIN_DIR}/cave)..."
if [ -L "${BIN_DIR}/cave" ]; then
    if ! rm "${BIN_DIR}/cave" 2>/dev/null; then
        _warn "Elevated privileges needed. Using sudo..."
        sudo rm "${BIN_DIR}/cave"
    fi
fi

_info "Cleaning up old CLI directory (${CAVE_PATH})..."
rm -rf "${CAVE_PATH}"

printf "\n%s\n" "$CHAR_LINE"
_info "Migration complete. CAVE CLI is now managed via pip."
_info "Open a new terminal and run 'cave --help' to get started."
printf "%s\n" "$CHAR_LINE"