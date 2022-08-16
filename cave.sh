#!/bin/bash
#
# CAVE cli for unix based systems

# Constants
readonly VALID_NAME_PATTERN="^[abcdefghijklmnopqrstuvwxyz0-9_-]+$"
readonly INVALID_NAME_PATTERN_1="^[-_]+.*$"
readonly INVALID_NAME_PATTERN_2="^.*[-_]+$"
readonly INVALID_NAME_PATTERN_3="(-_)+"
readonly INVALID_NAME_PATTERN_4="(_-)+"
readonly BIN_DIR="/usr/local/bin"
readonly TMP_DIR="/tmp"
readonly CHAR_LINE="============================="
readonly SSH_URL="git@github.com:MIT-CAVE/cave_app.git"
# update environment
declare -xr CAVE_PATH="${HOME}/.cave_cli"

indexof() {
  search="$1"; shift
  i=0
  for arg; do
    [ "$search" = "$arg" ] && echo $i && exit
    ((i++))
  done
  echo -1 && exit
}

validate_version() {
  local PROGRAM_NAME="$1"
  local EXIT_BOOL="$2"
  local ERROR_STRING="$3"
  local MIN_VERSION="$4"
  local CURRENT_VERSION="$5"
  if [ ! "$(printf '%s\n' "$MIN_VERSION" "$CURRENT_VERSION" | sort -V | head -n1)" = "$MIN_VERSION" ]; then
    printf "Your current $PROGRAM_NAME version ($CURRENT_VERSION) is too old. ${ERROR_STRING}"
    if [ "${EXIT_BOOL}" = "1" ]; then
      exit 1
    fi
  fi

}

check_python() { # Validate python is installed and is correct version
  install_python="\nPlease install python version 3.9.0 or greater. \nFor more information see: 'https://www.python.org/downloads/'"
  CURRENT_PYTHON_VERSION=$($PYTHON3_BIN --version | sed 's/Python //')
  validate_version "python" "1" "$install_python" "$MIN_PYTHON_VERSION" "$CURRENT_PYTHON_VERSION"
  if [ ! "$(printf $PYTHON3_BIN -V | grep conda)" = "" ]; then
    printf "Please ensure that you are not using Anaconda. ${CAVE_CLI_SHORT_NAME} is not compatible with Anaconda"
    exit 1
  fi
}

valid_app_name() {
  local app_name=$1
  if [[ ${#app_name} -lt 2 || ${#app_name} -gt 255 ]]; then
    printf "The app name needs to be two to 255 characters"
  elif [[ ! ${app_name} =~ ${VALID_NAME_PATTERN} ]]; then
    printf "The app name can only contain lowercase letters, numbers, hyphens (-), and underscores (_)"
  elif [[ ${app_name} =~ ${INVALID_NAME_PATTERN_1} ]]; then
    printf "The app name cannot start with a hyphen (-) or an underscore (_)"
  elif [[ ${app_name} =~ ${INVALID_NAME_PATTERN_2} ]]; then
    printf "The app name cannot end with a hyphen (-) or an underscore (_)"
  elif [[ ${app_name} =~ ${INVALID_NAME_PATTERN_3} ]]; then
    printf "The app name cannot contain a hyphen (-) followed by an underscore (_)"
  elif [[ ${app_name} =~ ${INVALID_NAME_PATTERN_4} ]]; then
    printf "The app name cannot contain an underscore (_) followed by a hyphen (-)"
  fi
}

valid_app_dir() { # Checks if current directory is the an instance of the cave app
  [[
    -f manage.py && \
    -f requirements.txt && \
    -d cave_api && \
    -d cave_app && \
    -d cave_core
 ]]
}

print_help() { # Prints the help text for cave_cli
  cat 1>&2 <<EOF
    CAVE CLI
    ${CHAR_LINE}
    Core Commands:
      create <app-name> [--version v]         Creates a new CAVE app in the specified directory. If
                                                the version flag isn't specified the latest version is used.
      upgrade [--version v]                   Upgrades the CAVE app in the current dicrectory to the given
                                                version. If the version flag isn't specified the latest version
                                                is used.
      run [options]                           Runs the CAVE app in the current directory. Options are passed
                                                to manage.py
    Utility Commands:
      help                                    Prints this help text.

      version                                 Prints the version of the cli.

      sync <repo>                             Merges files from the given repo into the CAVE app in the
                                                current directory.
      update                                  Updates to the latest version of the CAVE CLI

      uninstall                               Removes the CAVE CLI

EOF
  exit 0
}

run_cave() { # Runs the cave app in the current directory
  if ! valid_app_dir; then
    printf "Ensure you are in a valid CAVE app directory\n"
    exit 1
  fi
  source venv/bin/activate &&
  python manage.py runserver "$@"
  exit 0
}

upgrade_cave() { # Upgrade cave_app while preserving .env and cave_api/
  if ! valid_app_dir; then
    printf "Ensure you are in a valid CAVE app directory\n"
    exit 1
  fi
  # copy kept files to temp directory
  printf "Backing up cave_api and .env..."
  local path=$(mktemp -d)
  cp .env "${path}/.env"
  cp -r cave_api "${path}/cave_api"
  cp -r .git "${path}/.git"
  printf "Done\n"

  # remove current files
  rm -rf *
  rm -rf .* >& /dev/null

  # Clone the repo
  local CLONE_URL="${SSH_URL}"
  local VERSION_IDX=$(indexof --version "$@")
  local offset=$(echo "${VERSION_IDX} + 2" | bc -l)
  if [ ! "${VERSION_IDX}" = "-1" ]; then
    git clone -b "${!offset}" --single-branch "${CLONE_URL}" .
  else
    git clone --single-branch "${CLONE_URL}" .
  fi
  if [[ ! -d "cave_core" ]]; then
    printf "Clone failed. Ensure you used your GitHub PAT and a valid version.\n"
    exit 1
  fi
  # remove cloned cave_api and git
  rm -rf cave_api
  rm -rf .git

  printf "Restoring backed up files..."
  cp "${path}/.env" .env
  cp -r "${path}/cave_api" cave_api
  cp -r "${path}/.git" .git
  printf "Done\n"

  # clean up temp files
  rm -rf "${path}"

  # Install virtualenv and create venv
  virtual=$($PYTHON3_BIN -m virtualenv --version | grep No)
  if [[ ! "${virtual}" = "" ]]; then
    $PYTHON3_BIN -m pip install virtualenv
  fi

  $PYTHON3_BIN -m virtualenv venv

  # Activate venv and install requirements

  source venv/bin/activate
  python-m pip install -r requirements.txt

  git add .
  git commit -m "Upgraded by CAVE CLI"

  ./utils/reset_db.sh

  printf "Done. Any cave_api specific requirements should be reinstalled.\n"
  exit 0
}

create_cave() { # Create a cave app instance in folder $1
  local valid=$(valid_app_name "$1")

  if [[ ! "${valid}" = "" ]]; then
    printf "${valid}\n"
    exit 1
  fi
  if [[ -d "$1" ]]; then
    printf "Cannot create app '$1': This folder already exists in the current directory\n"
    exit 1
  fi
  local CLONE_URL="${SSH_URL}"
  local VERSION_IDX=$(indexof --version "$@")
  local offset=$(echo "${VERSION_IDX} + 2" | bc -l)
  # Clone the repo
  if [ ! "${VERSION_IDX}" = "-1" ]; then
    git clone -b "${!offset}" --single-branch "${CLONE_URL}" "$1"
  else
    git clone --single-branch "${CLONE_URL}" "$1"
  fi
  if [[ ! -d "$1" ]]; then
    printf "Clone failed. Ensure you used a valid version.\n"
    exit 1
  fi
  # Install virtualenv and create venv
  virtual=$($PYTHON3_BIN -m virtualenv --version | grep No)
  if [[ ! "${virtual}" = "" ]]; then
    $PYTHON3_BIN -m pip install virtualenv
  fi
  cd "$1"
  git remote rm origin
  $PYTHON3_BIN -m virtualenv venv
  # Activate venv and install requirements
  source venv/bin/activate
  python -m pip install -r requirements.txt

  # Setup .env file
  cp example.env .env
  local key=$(python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())")
  local line=$(grep -n --colour=auto "SECRET_KEY" .env | sed 's/^\([0-9]\+\):.*$/\1/')
  sed -i "${line}s/^.*$/SECRET_KEY='${key}'/" .env
  read -r -p "Please input your Mapbox Token: " key
  line=$(grep -n --colour=auto "MAPBOX_TOKEN" .env | sed 's/^\([0-9]\+\):.*$/\1/')
  sed -i "${line}s/^.*$/MAPBOX_TOKEN='${key}'/" .env
  read -r -p "Please input an admin email: " key
  line=$(grep -n --colour=auto "DJANGO_ADMIN_EMAIL" .env | sed 's/^\([0-9]\+\):.*$/\1/')
  sed -i "${line}s/^.*$/DJANGO_ADMIN_EMAIL='${key}'/" .env
  read -r -s -p "Please input an admin password: " key
  line=$(grep -n --colour=auto "DJANGO_ADMIN_PASSWORD" .env | sed 's/^\([0-9]\+\):.*$/\1/')
  sed -i "${line}s/^.*$/DJANGO_ADMIN_PASSWORD='${key}'/" .env
  printf "\n"
  read -r -s -p "Please input a database password: " key
  line=$(grep -n --colour=auto "DATABASE_PASSWORD" .env | sed 's/^\([0-9]\+\):.*$/\1/')
  sed -i "${line}s/^.*$/DATABASE_PASSWORD='${key}'/" .env
  key="$1_server_db"
  line=$(grep -n --colour=auto "DATABASE_NAME" .env | sed 's/^\([0-9]\+\):.*$/\1/')
  sed -i "${line}s/^.*$/DATABASE_NAME='${key}'/" .env
  key="$1_db_user"
  line=$(grep -n --colour=auto "DATABASE_USER" .env | sed 's/^\([0-9]\+\):.*$/\1/')
  sed -i "${line}s/^.*$/DATABASE_USER='${key}'/" .env
  # Setup DB
  ./utils/reset_db.sh
  printf "\nDone. Addtional configuration options availible in $1/.env\n"
  exit 0
}

uninstall_cli() { # Remove the CAVE CLI from system
  read -r -p "Are you sure you want to uninstall CAVE CLI? [y/N] " input
  case ${input} in
  [yY][eE][sS] | [yY])
    printf "Removing installation...\n"
    rm -rf "${CAVE_PATH}"
    if [ ! $(rm "${BIN_DIR}/cave") ]; then
      printf "WARNING!: Super User privileges required to terminate link! Using 'sudo'.\n"
      sudo rm "${BIN_DIR}/cave"
    fi
    printf "done\n"
    exit 0
    ;;
  *)
    printf "Uninstall canceled\n"
    exit 0
    ;;
  esac
}

sync_cave() { # Sync files from another repo to the selected cave app
  if ! valid_app_dir; then
    printf "Ensure you are in a valid CAVE app directory\n"
    exit 1
  fi

  if [[ "$1" = "" ]]; then
    printf "Ensure you include a repository link when syncing\n"
    exit 1
  fi

  local path=$(mktemp -d)
  local VERSION_IDX=$(indexof --branch "$@")
  local offset=$(echo "${VERSION_IDX} + 2" | bc -l)
  # Clone the repo
  if [ ! "${VERSION_IDX}" = "-1" ]; then
    git clone -b "${!offset}" --single-branch "$1" "${path}"
  else
    git clone --single-branch "$1" "${path}"
  fi
  if [[ $(ls "${path}") = "" ]]; then
    printf "Clone failed. Ensure you included a valid repository link .\n"
    exit 1
  fi
  printf "Syncing files from provided repo..."
  rsync -a --exclude={'.git','.gitignore','README.md'} "${path}/" .
  printf "Done\n"

  printf "Cleaning up..."
  rm -rf ${path}
  printf "Done \n"
  printf "Sync complete\n"
  exit 0
}

main() {
  if [[ $# -lt 1 ]]; then
    print_help
  fi
  # Set the $PYTHON3_BIN var
  source "${CAVE_PATH}/CONFIG"
  case $1 in
    help | --help | -h)
      print_help
    ;;
    version | --version | -v)
      printf "$(cat "${CAVE_PATH}/VERSION")\n"
    ;;
    run)
      shift # pass all args except "run"
      run_cave "$@"
    ;;
    update)
      bash -c "$(curl https://raw.githubusercontent.com/MIT-CAVE/cave_cli/main/install.sh)"
    ;;
    uninstall)
      uninstall_cli
    ;;
    create)
      check_python
      shift
      create_cave "$@"
    ;;
    upgrade)
      check_python
      shift
      upgrade_cave "$@"
    ;;
    sync)
      shift
      sync_cave "$@"
    ;;
    --version | version)
      printf "$(cat "${CAVE_PATH}/VERSION")\n"
    ;;
  esac
}

main "$@"
