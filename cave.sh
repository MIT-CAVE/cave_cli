#!/bin/bash
# One-time migration shim: upgrades from pipx-based to uv-based CAVE CLI.
# This file lives at the repo root so that a legacy `cave update` (git pull)
# replaces ~/.cave_cli/cave.sh with this script. The next time the user runs
# any `cave` command, migration runs automatically.

readonly CAVE_PATH="${HOME}/.cave_cli"
readonly BIN_DIR="/usr/local/bin"
readonly CHAR_LINE="============================="
readonly UV_INSTALL_SPEC="cave_cli"
readonly UV_DOCS_URL="https://docs.astral.sh/uv/"
readonly UV_INSTALLER_URL="https://astral.sh/uv/install.sh"

_info()  { printf "INFO: %s\n"  "$1"; }
_warn()  { printf "WARN: %s\n"  "$1"; }
_error() { printf "ERROR: %s\n" "$1"; }

_ask() {
    # Returns 0 if user answers yes, 1 otherwise.
    local response
    printf "%s [y/N] " "$1"
    read -r response
    case "$response" in
        [yY]|[yY][eE][sS]) return 0 ;;
        *) return 1 ;;
    esac
}

printf "%s\n" "$CHAR_LINE"
_info "The CAVE CLI has migrated to a uv-based installation."
_info "Running one-time migration..."
printf "%s\n\n" "$CHAR_LINE"

# ── Step 1: ensure uv is available ──────────────────────────────────────────
UV_INSTALLED=0
if command -v uv &>/dev/null; then
    UV_INSTALLED=1
else
    _warn "uv is not installed."
    OS="$(uname -s)"

    if [ "$OS" = "Darwin" ]; then
        # macOS ── try Homebrew first
        if command -v brew &>/dev/null; then
            if _ask "Install uv via Homebrew? (brew install uv)"; then
                brew install uv && UV_INSTALLED=1
            fi
        else
            _info "Homebrew not found. Skipping brew-based install."
        fi

        # macOS fallback ── official installer
        if [ $UV_INSTALLED -eq 0 ]; then
            if command -v curl &>/dev/null; then
                if _ask "Install uv via the official installer? (curl -LsSf ${UV_INSTALLER_URL} | sh)"; then
                    curl -LsSf "${UV_INSTALLER_URL}" | sh && UV_INSTALLED=1
                fi
            fi
        fi
    else
        # Linux / other ── official installer
        if command -v curl &>/dev/null; then
            if _ask "Install uv via the official installer? (curl -LsSf ${UV_INSTALLER_URL} | sh)"; then
                curl -LsSf "${UV_INSTALLER_URL}" | sh && UV_INSTALLED=1
            fi
        fi
    fi

    if [ $UV_INSTALLED -eq 0 ]; then
        _error "Could not install uv automatically."
        _error "Please install uv manually, then run:"
        _error "  uv tool install ${UV_INSTALL_SPEC}"
        _error "  sudo rm ${BIN_DIR}/cave   # remove the old symlink"
        _error "uv installation guide: ${UV_DOCS_URL}"
        exit 1
    fi

    # Make sure uv's bin dir is on PATH for this session
    export PATH="${HOME}/.local/bin:${PATH}"
    if ! command -v uv &>/dev/null; then
        _error "uv was installed but cannot be found on PATH."
        _error "Add ~/.local/bin to your PATH, then run: uv tool install ${UV_INSTALL_SPEC}"
        _error "uv installation guide: ${UV_DOCS_URL}"
        exit 1
    fi
fi

# ── Step 2: install cave_cli via uv ─────────────────────────────────────────
_info "Installing CAVE CLI via uv..."
if ! uv tool install "${UV_INSTALL_SPEC}"; then
    _error "Failed to install CAVE CLI via uv."
    _error "Please try manually: uv tool install ${UV_INSTALL_SPEC}"
    _error "uv installation guide: ${UV_DOCS_URL}"
    exit 1
fi

# ── Step 3: clean up old bash-based installation ─────────────────────────────
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
_info "Migration complete. CAVE CLI is now managed via uv."
_info "Open a new terminal and run 'cave --help' to get started."
printf "%s\n" "$CHAR_LINE"
