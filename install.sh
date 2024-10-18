#!/bin/bash
#
# Install the cave_cli on unix based systems

# Constants
readonly CHARS_LINE="============================"
readonly CAVE_CLI_PATH="${HOME}/.cave_cli"
readonly CAVE_CLI_SHORT_NAME="CAVE CLI"
readonly CAVE_CLI_COMMAND="cave"
readonly CAVE_CLI_VERSION="v3.0.2"
readonly BIN_DIR="/usr/local/bin"
readonly HTTPS_CLONE_URL="-b ${CAVE_CLI_VERSION} https://github.com/MIT-CAVE/cave_cli.git"
readonly SSH_CLONE_URL="-b ${CAVE_CLI_VERSION} git@github.com:MIT-CAVE/cave_cli.git"
readonly MIN_DOCKER_VERSION="23.0.6"

VERBOSE='false'

get_flag() {
    local default=$1
    shift
    local flag=$1
    shift
    while [ $# -gt 0 ]; do
        if [ "$1" = "$flag" ]; then
            echo "$2"
            return
        fi
        shift
    done
    echo "$default"
}

has_flag() {
    local flag=$1
    shift
    while [ $# -gt 0 ]; do
        if [ "$1" = "$flag" ]; then
            echo "true"
            return
        fi
        shift
    done
    echo "false"
}

is_dir_empty() {
    local dir=$1
    if [ "$(ls -A $dir)" ]; then
        echo "false"
    else
        echo "true"
    fi
}

print_if_verbose () {
  while read IN; do
    if [ "$VERBOSE" = 'true' ]; then
      printf "%s\n" "$IN"
    fi
  done
}

err() { # Display an error message
  printf "$0: $1\n" >&2
}

validate_install() {
  local PROGRAM_NAME="$1"
  local EXIT_BOOL="$2"
  local ERROR_STRING="$3"
  if [ "$($PROGRAM_NAME --version)" = "" ]; then
    err "${PROGRAM_NAME} is not installed. ${ERROR_STRING}"
    if [ "${EXIT_BOOL}" = "1" ]; then
      exit 1
    fi
  fi
}

validate_version() {
  local PROGRAM_NAME="$1"
  local EXIT_BOOL="$2"
  local ERROR_STRING="$3"
  local MIN_VERSION="$4"
  local CURRENT_VERSION="$5"
  if [ ! "$(printf '%s\n' "$MIN_VERSION" "$CURRENT_VERSION" | sort -V | head -n1)" = "$MIN_VERSION" ]; then
    echo "Your current $PROGRAM_NAME version ($CURRENT_VERSION) is too old. ${ERROR_STRING}"
    if [ "${EXIT_BOOL}" = "1" ]; then
      exit 1
    fi
  fi
}

check_os() { # Validate that the current OS
  case "$(uname -s)" in
      Linux*)     machine="Linux";;
      Darwin*)    machine="Mac";;
      *)          machine="UNKNOWN"
  esac
  if [ $machine = "UNKNOWN" ]; then
    printf "Error: Unknown operating system.\n"
    printf "Please run this command on one of the following:\n"
    printf "- MacOS\n- Linux\n- Windows (Using Ubuntu 20.04 on Windows Subsystem for Linux 2 - WSL2)"
    exit 1
  fi
}

check_git() { # Validate git is installed
  local install_git="\nPlease install git. \nFor more information see: 'https://git-scm.com'"
  validate_install "git" "1" "$install_git"
}

check_docker() { # Validate docker is installed, running, and is correct version
  install_docker="\nPlease install docker version ${MIN_DOCKER_VERSION} or greater. \nFor more information see: 'https://docs.docker.com/get-docker/'"
  CURRENT_DOCKER_VERSION=$(docker --version | sed -e 's/Docker version //' -e 's/, build.*//')
  validate_version "docker" "1" "$install_docker" "$MIN_DOCKER_VERSION" "$CURRENT_DOCKER_VERSION"
  printf "Docker is correctly installed\n"
}

check_previous_installation() { # Check to make sure previous installations are removed before continuing
  if [ -d "${CAVE_CLI_PATH}" ]; then
    local LOCAL_CLI_VERSION=$(cat ${CAVE_CLI_PATH}/VERSION)
    printf "${CHARS_LINE}\n"
    printf "An existing installation of ${CAVE_CLI_SHORT_NAME} ($LOCAL_CLI_VERSION) was found.\n"
    read -r -p "Would you like to uninstall it and then install ${CAVE_CLI_SHORT_NAME} ($CAVE_CLI_VERSION)? [y/N] " input
    case ${input} in
      [yY][eE][sS] | [yY])
        printf "Uninstalling old installation..."
        rm -rf "${CAVE_CLI_PATH}" 2>&1 | print_if_verbose
        printf "Done\n"
        ;;
      [nN][oO] | [nN] | "")
        err "Installation canceled."
        exit 1
        ;;
      *)
        err "Invalid input: Installation canceled."
        exit 1
        ;;
    esac
  fi
}

install_new() { # Copy the needed files locally
  check_previous_installation "$@"
  printf "Creating application folder at '${CAVE_CLI_PATH}'..."
  mkdir -p "${CAVE_CLI_PATH}" 2>&1 | print_if_verbose
  printf "Done\n"
  printf "Cloning ${CAVE_CLI_SHORT_NAME} from GitHub..."
  if [[ "$(has_flag "-dev" "$@")" = "true" ]]; then
    CLONE_URL="$SSH_CLONE_URL"
  else
    CLONE_URL="$HTTPS_CLONE_URL"
  fi
  git clone --progress $CLONE_URL "${CAVE_CLI_PATH}" 2>&1 | print_if_verbose
  if [[ "$(is_dir_empty "${CAVE_CLI_PATH}")" = 'true' ]]; then
    printf "Failed!\nEnsure you have access rights to the repository: ${CLONE_URL}.\n"
    rm -rf "${CAVE_CLI_PATH}" 2>&1 | print_if_verbose
    exit 1
  fi
  printf "Done\n"
}

add_to_path() { # Add the cli to a globally accessable path
  printf "Making '${CAVE_CLI_COMMAND}' globally accessable: \nCreating link from '${CAVE_CLI_PATH}/${CAVE_CLI_COMMAND}.sh' as '${BIN_DIR}/${CAVE_CLI_COMMAND}' (sudo required)..."
  sudo ln -sf "${CAVE_CLI_PATH}/${CAVE_CLI_COMMAND}.sh" "${BIN_DIR}/${CAVE_CLI_COMMAND}" 2>&1 | print_if_verbose
  printf "Done\n"
}

main() {
  check_os
  VERBOSE=$(has_flag "-v" "$@")
  check_git
  check_docker
  install_new "$@"
  add_to_path "$@"
  printf "${CHARS_LINE}\n"
  printf "Installation Complete.\n"
  printf "To get started, run:\n\n${CAVE_CLI_COMMAND} --help\n\n"
}

main "$@"
