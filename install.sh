#!/bin/bash
#
# Install the cave_cli on unix based systems

# Constants
readonly CHARS_LINE="============================"
readonly CAVE_CLI_PATH="${HOME}/.cave_cli"
readonly CAVE_CLI_SHORT_NAME="CAVE CLI"
readonly CAVE_CLI_COMMAND="cave"
readonly CAVE_CLI_VERSION="0.3.0"
readonly BIN_DIR="/usr/local/bin"
readonly DATA_DIR="data"
readonly HTTPS_CLONE_URL="-b ${CAVE_CLI_VERSION} https://github.com/MIT-CAVE/cave_cli.git"
readonly SSH_CLONE_URL="-b ${CAVE_CLI_VERSION} git@github.com:MIT-CAVE/cave_cli.git"
readonly MIN_PYTHON_VERSION="3.9.0"

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
  install_git="\nPlease install git. \nFor more information see: 'https://git-scm.com'"
  validate_install "git" "1" "$install_git"
}

check_postgress() { # Validate postgress is installed
  local install_post="\nPlease install postgreSQL. \nFor more information see: 'https://www.postgresql.org/download/'"
  validate_install "psql" "1" "$install_post"
}

check_python() { # Validate python is installed and is correct version
  install_python="\nPlease install python version 3.9.0 or greater. \nFor more information see: 'https://www.python.org/downloads/'\n"
  CURRENT_PYTHON_VERSION=$($1 --version | sed 's/Python //')
  echo $(validate_version "python" "0" "$install_python" "$MIN_PYTHON_VERSION" "$CURRENT_PYTHON_VERSION")
  if [ ! "$(printf $1 -V | grep conda)" = "" ]; then
    printf "Please ensure that you are not using Anaconda. ${CAVE_CLI_SHORT_NAME} is not compatible with Anaconda\n"
  fi
}

check_previous_installation() { # Check to make sure previous installations are removed before continuing
  local config_path="$1"
  if [ -d "${CAVE_CLI_PATH}" ]; then
    LOCAL_CLI_VERSION=$(cat ${CAVE_CLI_PATH}/VERSION)
    printf "An existing installation of ${CAVE_CLI_SHORT_NAME} ($LOCAL_CLI_VERSION) was found\n"
    if [ "$LOCAL_CLI_VERSION" = "$CAVE_CLI_VERSION" ] ; then
      read -r -p "Would you like to reinstall ${CAVE_CLI_SHORT_NAME} ($CAVE_CLI_VERSION)? [y/N] " input
    else
      read -r -p "Would you like to update to ${CAVE_CLI_SHORT_NAME} ($CAVE_CLI_VERSION)? [y/N] " input
    fi
    case ${input} in
      [yY][eE][sS] | [yY])
        printf "Removing old installation... "
        cp "${CAVE_CLI_PATH}/CONFIG" "${config_path}"
        rm -rf "${CAVE_CLI_PATH}"
        printf "done\n"
        ;;
      [nN][oO] | [nN] | "")
        err "Installation canceled"
        exit 1
        ;;
      *)
        err "Invalid input: Installation canceled."
        exit 1
        ;;
    esac
  fi
}

choose_python() { # Choose a python bin and check that it is valid
  local path=""
  local default=$(which python)
  local check="Placeholder"
  #Ask for python path until valid version is given
  while [[ ! "${check}" = "" ]]; do
    read -r -p "Please enter the path to your python binary. Leave blank to use the default(${default}): " path
    if [[ "${path}" = "" ]]; then
      check=$(check_python ${default})
    else
      check=$(check_python ${path})
    fi
    printf "${check}"
  done
  if [[ "${path}" = "" ]]; then
    printf "PYTHON3_BIN=\"${default}\"\n\n\n" > "${CAVE_CLI_PATH}/CONFIG"
  else
    printf "PYTHON3_BIN=\"${path}\"\n\n\n" > "${CAVE_CLI_PATH}/CONFIG"
  fi
}

install_new() { # Copy the needed files locally
  local config_path=$(mktemp)
  check_previous_installation "${config_path}"
  printf "Creating application folder at '${CAVE_CLI_PATH}'..."
  mkdir -p "${CAVE_CLI_PATH}"
  printf "done\n"
  printf "${CHARS_LINE}\n"
  CLONE_URL="$HTTPS_CLONE_URL"
  git clone $CLONE_URL \
    ${clone_opts} \
    "${CAVE_CLI_PATH}" > /dev/null
  if [ ! -d "${CAVE_CLI_PATH}" ]; then
    err "Git Clone Failed. Installation Canceled"
    exit 1
  fi

  local config_info=$(cat ${config_path})
  if [ "${config_info}" != "" ]; then
    cp "${config_path}" "${CAVE_CLI_PATH}/CONFIG"
  else
    printf "${CHARS_LINE}\n"
    choose_python
  fi
}

add_to_path() { # Add the cli to a globally accessable path
  printf "${CHARS_LINE}\n"
  printf "Making '${CAVE_CLI_COMMAND}' globally accessable: \nCreating link from '${CAVE_CLI_PATH}/${CAVE_CLI_COMMAND}.sh' as '${BIN_DIR}/${CAVE_CLI_COMMAND}':\n"
  if [ $(readlink "${BIN_DIR}/${CAVE_CLI_COMMAND}") = "${CAVE_CLI_PATH}/${CAVE_CLI_COMMAND}.sh" ]; then
    printf "Link already present... skipping. \n"
  else
    if [ ! $(ln -sf "${CAVE_CLI_PATH}/${CAVE_CLI_COMMAND}.sh" "${BIN_DIR}/${CAVE_CLI_COMMAND}") ]; then
      printf "WARNING!: Super User priviledges required to complete link! Using 'sudo'.\n"
      sudo ln -sf "${CAVE_CLI_PATH}/${CAVE_CLI_COMMAND}.sh" "${BIN_DIR}/${CAVE_CLI_COMMAND}"
    fi
  fi
  printf "Done\n"
}

main() {
  check_os
  check_git
  check_postgress
  install_new
  add_to_path
  printf "${CHARS_LINE}\n"
  printf "Install completed.\n"
  exit 0
}

main "$@"
