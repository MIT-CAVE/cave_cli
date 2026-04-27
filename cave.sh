#!/bin/bash
# One-time migration shim: upgrades from bash-based to pipx-based CAVE CLI.
# This file lives at the repo root so that a legacy `cave update` (git pull)
# replaces ~/.cave_cli/cave.sh with this script. The next time the user runs
# any `cave` command, migration runs automatically.

readonly CAVE_PATH="${HOME}/.cave_cli"
readonly BIN_DIR="/usr/local/bin"
readonly CHAR_LINE="============================="
readonly PIPX_INSTALL_SPEC="cave_cli"
readonly PIPX_DOCS_URL="https://pipx.pypa.io/stable"

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
_info "The CAVE CLI has migrated to a pipx-based installation."
_info "Running one-time migration..."
printf "%s\n\n" "$CHAR_LINE"

# ── Step 1: ensure pipx is available ────────────────────────────────────────
PIPX_INSTALLED=0
if command -v pipx &>/dev/null; then
    PIPX_INSTALLED=1
else
    _warn "pipx is not installed."
    OS="$(uname -s)"

    if [ "$OS" = "Darwin" ]; then
        # macOS ── try Homebrew first
        if command -v brew &>/dev/null; then
            if _ask "Install pipx via Homebrew? (brew install pipx)"; then
                brew install pipx && PIPX_INSTALLED=1
            fi
        else
            _info "Homebrew not found. Skipping brew-based install."
        fi

        # macOS fallback ── pip
        if [ $PIPX_INSTALLED -eq 0 ]; then
            if command -v pip3 &>/dev/null; then
                if _ask "Install pipx via pip3? (pip3 install --user pipx)"; then
                    pip3 install --user pipx && PIPX_INSTALLED=1
                fi
            elif command -v pip &>/dev/null; then
                if _ask "Install pipx via pip? (pip install --user pipx)"; then
                    pip install --user pipx && PIPX_INSTALLED=1
                fi
            fi
        fi
    else
        # Linux / other ── pip
        if python3 -m pip --version &>/dev/null 2>&1; then
            if _ask "Install pipx via pip? (python3 -m pip install --user pipx)"; then
                python3 -m pip install --user pipx && PIPX_INSTALLED=1
            fi
        elif command -v pip3 &>/dev/null; then
            if _ask "Install pipx via pip3? (pip3 install --user pipx)"; then
                pip3 install --user pipx && PIPX_INSTALLED=1
            fi
        elif command -v pip &>/dev/null; then
            if _ask "Install pipx via pip? (pip install --user pipx)"; then
                pip install --user pipx && PIPX_INSTALLED=1
            fi
        fi
    fi

    if [ $PIPX_INSTALLED -eq 0 ]; then
        _error "Could not install pipx automatically."
        _error "Please install pipx manually, then run:"
        _error "  pipx install ${PIPX_INSTALL_SPEC}"
        _error "  sudo rm ${BIN_DIR}/cave   # remove the old symlink"
        _error "pipx installation guide: ${PIPX_DOCS_URL}"
        exit 1
    fi

    # Make sure pipx's bin dir is on PATH for this session
    export PATH="${HOME}/.local/bin:${PATH}"
    if ! command -v pipx &>/dev/null; then
        _error "pipx was installed but cannot be found on PATH."
        _error "Add ~/.local/bin to your PATH, then run: pipx install ${PIPX_INSTALL_SPEC}"
        _error "pipx installation guide: ${PIPX_DOCS_URL}"
        exit 1
    fi

    _info "Ensuring pipx's bin directory is on PATH..."
    pipx ensurepath
fi

# ── Step 2: install cave_cli via pipx ───────────────────────────────────────
_info "Installing CAVE CLI via pipx..."
if ! pipx install "${PIPX_INSTALL_SPEC}"; then
    _error "Failed to install CAVE CLI via pipx."
    _error "Please try manually: pipx install ${PIPX_INSTALL_SPEC}"
    _error "pipx installation guide: ${PIPX_DOCS_URL}"
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
_info "Migration complete. CAVE CLI is now managed via pipx."
_info "Open a new terminal and run 'cave --help' to get started."
printf "%s\n" "$CHAR_LINE"
