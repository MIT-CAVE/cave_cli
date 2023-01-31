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
readonly HTTPS_URL="https://github.com/MIT-CAVE/cave_app.git"
readonly IP_REGEX="([0-9]{1,3}\.)+([0-9]{1,3}):[0-9][0-9][0-9][0-9]+"
# update environment
declare -xr CAVE_PATH="${HOME}/.cave_cli"

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
  # Check to see if this is a cave app folder with manage.py and cave_core
  if ! [[ -f manage.py && -d cave_core ]]; then
    return 1
  fi
  # Check the folders
  for folder in cave_api cave_app cave_core; do
    if ! [ -d ${folder} ] ; then
      printf "The folder '${folder}' is missing in the root project directory.\n" >&2
    fi
  done
  # Check the files
  for file in .env manage.py requirements.txt; do
      if ! [ -f ${file} ]; then
        printf "The file '${file}' is missing in the root project directory.\n" >&2
      fi
  done
  [[  -f .env && \
      -f manage.py && \
      -f requirements.txt && \
      -d cave_api && \
      -d cave_app && \
      -d cave_core ]]
}

find_app_dir() { # Finds path to parent app folder if present
  path="./"
  while ! valid_app_dir; do
    cd ../
    path="${path}../"
    if [ "${PWD}" = "/" ]; then
      echo "-1"
      exit 1
    fi
  done
  echo "${path}"
}

find_open_port() { # Finds an open port above the specified one
  port="$1"
  open=$(nc -z 127.0.0.1 ${port}; echo $?)
  while [ "$open" != "1" ]; do
    port=$(echo "${port} + 1" | bc -l)
    open=$(nc -z 127.0.0.1 ${port}; echo $?)
    if [ "${port}" = "65535" ]; then
      echo "-1"
      exit 1
    fi
  done
  echo "${port}"
}

start_postgres() {
  case "$(uname -s)" in
    Linux*)     sudo service postgresql start &> /dev/null;;
    Darwin*)    brew services start postgresql@14 &> /dev/null;;
    *)          printf "Error: OS not recognized."; exit 1;;
  esac
}

is_postgres_running() {
  case "$(pg_isready)" in
    *"accepting"*)    printf "Postgres Is Running!\n" &> /dev/null;;
    *)                return 1;;
  esac
}

ensure_postgres_running() {
  if ! is_postgres_running; then
    printf "Postgres is not currently running. Attempting to start it..."
    start_postgres
    sleep 1
    if ! is_postgres_running; then
      printf "Failed!\n"
      printf "Ensure you have postgresql installed and running.\nSee the docs at: https://github.com/MIT-CAVE/cave_cli for setup information.\nExiting\n"
      exit 1
    else
      printf "Done.\n"
    fi
  fi
}

purge_mac_db() { # Removes db and db user on mac
  psql postgres -c "DROP DATABASE IF EXISTS ${DATABASE_NAME}"
  psql postgres -c "DROP USER IF EXISTS ${DATABASE_USER}"
}

purge_linux_db(){ # Removes db and db user on linux
  sudo -u postgres psql -c "DROP DATABASE IF EXISTS ${DATABASE_NAME}"
  sudo -u postgres psql -c "DROP USER IF EXISTS ${DATABASE_USER}"
}

confirm_action() { # Checks user input for an action
  local confirm_text="$1"
    read -r -p "${confirm_text}. Would you like to continue? [y/N] " input
        case ${input} in
      [yY][eE][sS] | [yY])
        :
        ;;
      [nN][oO] | [nN] | "")
        printf "Operation canceled.\n"
        exit 1
        ;;
      *)
        printf "Invalid input: Operation canceled.\n"
        exit 1
        ;;
    esac
}

print_help() { # Prints the help text for cave_cli
  VERSION="$(cat ${CAVE_PATH}/VERSION)"
  HELP="$(cat ${CAVE_PATH}/help.txt))"
  cat 1>&2 <<EOF
CAVE CLI ($VERSION)
${CHAR_LINE}

${HELP}

EOF
  exit 0
}

force_venv_setup() {
  if ! [[ -d venv ]]; then
    confirm_action "Your app python virtual environment has not been set up. You must set it up and reset your database before proceeding"
    install_cave
    reset_cave -y
  fi
}


run_cave() { # Runs the cave app in the current directory
  local app_dir=$(find_app_dir)
  if [ "${app_dir}" = "-1" ]; then
    printf "Ensure you are in a valid CAVE app directory\n"
    exit 1
  else
    cd "${app_dir}"
  fi

  force_venv_setup

  source venv/bin/activate
  if [[ "$1" != "" && "$1" =~ $IP_REGEX ]]; then
    local ip=$(echo "$1" | perl -nle'print $& while m{([0-9]{1,3}\.)+([0-9]{1,3})}g')
    local port=$(echo "$1" | perl -nle'print $& while m{(?<=:)\d\d\d[0-9]+}g')
    local offset_port=$(echo "${port} + 1" | bc -l)
    local open=$(nc -z 127.0.0.1 ${port}; echo $?)
    local offset_open=$(find_open_port ${offset_port})
    if [[ "${open}" = "1" && "${offset_open}" != "-1" ]]; then
      python manage.py collectstatic
      daphne -e ssl:$port:privateKey=utils/lan_hosting/LAN.key:certKey=utils/lan_hosting/LAN.crt cave_app.asgi:application -p $offset_open -b $ip
    else
      printf "The specified port is in use. Please try another."
      exit 1
    fi
  else
    python manage.py runserver "$@"
  fi
  exit 0
}

upgrade_cave() { # Upgrade cave_app while preserving .env and cave_api/
  local app_dir=$(find_app_dir)
  if [ "${app_dir}" = "-1" ]; then
    printf "Ensure you are in a valid CAVE app directory\n"
    exit 1
  else
    cd "${app_dir}"
  fi

  if [[ "$(has_flag -y "$@")" != "true" ]]; then
    confirm_action "This will potentially update all files not in 'cave_api/' or '.env' and reset your database"
  fi

  sync_cave -y --exclude "'.git' '.env' '.gitignore' 'cave_api/'" --url "$(get_flag "$HTTPS_URL" "--url" "$@")" --branch "$(get_flag "" "--version" "$@")" "$@"
  printf "Upgrade complete.\n"
  exit 0
}

env_create() { # creates .env file for create_cave
  local save_inputs=$2
  rm .env &> /dev/null
  cp example.env .env &> /dev/null
  local key=$(source venv/bin/activate && python3 -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())")
  local line=$(grep -n --colour=auto "SECRET_KEY" .env | cut -d: -f1)
  local newenv=$(awk "NR==${line} {print \"SECRET_KEY='${key}'\"; next} {print}" .env)
  local key2=""
  if [ "${ADMIN_EMAIL}" = "" ]; then
    ADMIN_EMAIL="$1@example.com"
  fi
  printf "Set up your new app environment (.env) variables:\n"
  echo "$newenv" > .env
  printf "Mapbox tokens can be created by making an account on 'https://mapbox.com'\n"
  if [ "${MAPBOX_TOKEN}" = "" ]; then
    read -r -p "Please input your Mapbox Public Token: " key
  else
    read -r -p "Please input your Mapbox Public Token. Leave blank to use default: " key
  fi
  if [ "${key}" = "" ]; then
    key="${MAPBOX_TOKEN}"
  elif [ "${save_inputs}" = "true" ]; then
    MAPBOX_TOKEN="${key}"
  fi
  line=$(grep -n --colour=auto "MAPBOX_TOKEN" .env | cut -d: -f1)
  newenv=$(awk "NR==${line} {print \"MAPBOX_TOKEN='${key}'\"; next} {print}" .env)
  echo "$newenv" > .env
  key=""
  printf "\n"
  read -r -p "Please input an admin email. Leave blank for default(${ADMIN_EMAIL}): " key
  if [ "${key}" = "" ]; then
    key="${ADMIN_EMAIL}"
  elif [ "${save_inputs}" = "true" ]; then
    ADMIN_EMAIL="${key}"
  fi
  line=$(grep -n --colour=auto "DJANGO_ADMIN_EMAIL" .env | cut -d: -f1)
  newenv=$(awk "NR==${line} {print \"DJANGO_ADMIN_EMAIL='${key}'\"; next} {print}" .env)
  echo "$newenv" > .env
  key=""
  while [ "${key2}" = "" ]; do
    printf "\n"
    read -r -s -p "Please input an admin password. Leave blank to randomly generate one: " key
    if [ "${key}" = "" ]; then
      key=$(LC_ALL=C tr -dc A-Za-z0-9 </dev/urandom | head -c 16)
      key2="Placeholder"
    else
      printf "\n"
      read -r -s -p "Retype admin password to confirm: " key2
      if [ "${key}" != "${key2}" ]; then
        printf "Passwords didn't match. Please try again\n"
        key2=""
      fi
    fi
  done
  line=$(grep -n --colour=auto "DJANGO_ADMIN_PASSWORD" .env | cut -d: -f1)
  newenv=$(awk "NR==${line} {print \"DJANGO_ADMIN_PASSWORD='${key}'\"; next} {print}" .env)
  echo "$newenv" > .env
  key=""
  key2=""
  printf "\n"
  while [ "${key2}" = "" ]; do
    printf "\n"
    read -r -s -p "Please input a database password. Leave blank to randomly generate one: " key
    if [ "${key}" = "" ]; then
      key=$(LC_ALL=C tr -dc A-Za-z0-9 </dev/urandom | head -c 16)
      key2="Placeholder"
    else
      printf "\n"
      read -r -s -p "Retype database password to confirm: " key2
      if [ "${key}" != "${key2}" ]; then
        printf "Passwords didn't match. Please try again\n"
        key2=""
      fi
    fi
  done
  line=$(grep -n --colour=auto "DATABASE_PASSWORD" .env | cut -d: -f1)
  newenv=$(awk "NR==${line} {print \"DATABASE_PASSWORD='${key}'\"; next} {print}" .env)
  echo "$newenv" > .env
  key="$1_db"
  line=$(grep -n --colour=auto "DATABASE_NAME" .env | cut -d: -f1)
  newenv=$(awk "NR==${line} {print \"DATABASE_NAME='${key}'\"; next} {print}" .env)
  echo "$newenv" > .env
  key="$1_db_user"
  line=$(grep -n --colour=auto "DATABASE_USER" .env | cut -d: -f1)
  newenv=$(awk "NR==${line} {print \"DATABASE_USER='${key}'\"; next} {print}" .env)
  echo "$newenv" > .env

  # Save inputs
  if [ "${save_inputs}" = "true" ]; then
    # Write MAPBOX_TOKEN to config line 2 and ADMIN_EMAIL to config line 3
    local inputs="MAPBOX_TOKEN='${MAPBOX_TOKEN}'\nADMIN_EMAIL='${ADMIN_EMAIL}'\n"
    local newConfig=$(awk "NR==2 {print \"${inputs}\"; next} NR==3 {next} {print}" "${CAVE_PATH}/CONFIG")
    echo "$newConfig" > "${CAVE_PATH}/CONFIG"
  fi
  printf "\n"
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
  
  local CLONE_URL=$(get_flag "${HTTPS_URL}" --url "$@")

  # Clone the repo
  printf "${CHAR_LINE}\n"
  printf "Downloading the app template..."
  if [ "$(has_flag --version "$@")" = 'true' ]; then
    git clone -b "$(get_flag main --version "$@")" --single-branch "${CLONE_URL}" "$1" &> /dev/null
  else
    git clone --single-branch "${CLONE_URL}" "$1" &> /dev/null
  fi
  if [[ ! -d "$1" ]]; then
    printf "\nClone failed. Ensure you used a valid version.\n"
    exit 1
  fi
  printf "Done\n"

  # cd into the created app
  cd "$1"
  # Create a fake .env file to allow installation to proceed
  touch .env

  # Setup python virtual environment
  install_cave

  # Setup .env file
  env_create "$1" "$(has_flag -save-inputs "$@")"

  # Set up the app database
  reset_cave -y

  # Prep git repo
  printf "Version Control:\n"
  printf "Configuring git repository..."
  if [ "${DEV_IDX}" = "-1" ]; then
    rm -rf .git        
    git init  &> /dev/null
    case "$(uname -s)" in
      Linux*)     sed -i 's/.env//g' .gitignore;;
      Darwin*)    sed -i '' 's/.env//g' .gitignore;;
      *)          printf "Error: OS not recognized."; exit 1;;
    esac
    git add .  &> /dev/null
    git commit -m "Initialize CAVE App" &> /dev/null
    git branch -M main &> /dev/null
  fi
  printf "Done.\n"
  printf "${CHAR_LINE}\n"
  printf "App Creation completed!\nNote: Created variables and addtional configuration options are availible in $1/.env\n"
  printf "${CHAR_LINE}\n"
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
  local app_dir=$(find_app_dir)
  if [ "${app_dir}" = "-1" ]; then
    printf "Ensure you are in a valid CAVE app directory\n"
    exit 1
  else
    cd "${app_dir}"
  fi

  if [[ "$(has_flag -y "$@")" != "true" ]]; then
    confirm_action "This will reset your virtual environment and database. It will also potentially update your files"
  fi

  printf "Downloading repo to sync..."
  local path=$(mktemp -d)
  local CLONE_URL="$(get_flag "none" --url "$@")"
  local CLONE_BRANCH="$(get_flag "none" --branch "$@")"
  if [[ "${CLONE_BRANCH}" != 'none' ]]; then
    git clone -b "$(get_flag '' --branch "$@")" --single-branch "${CLONE_URL}" "$path" &> /dev/null
  else
    git clone --single-branch "${CLONE_URL}" "$path" &> /dev/null
  fi
  if [[ "$(is_dir_empty "$path")" = 'true' ]]; then
    printf "Failed!\nEnsure you have access rights to the repository: ${CLONE_URL}\nEnsure you specified a valid branch: ${CLONE_BRANCH}.\n"
    rm -rf "${path}"
    exit 1
  fi
  printf "Done.\n"

  printf "Syncing files..."
  RSYNC_EXCLUDE=$(get_flag "" "--exclude" "$@")
  RSYNC_COMMAND="rsync -a --exclude='.git'"
  for EXCLUDE in $RSYNC_EXCLUDE; do
      RSYNC_COMMAND="$RSYNC_COMMAND --exclude=${EXCLUDE}"
  done
  RSYNC_COMMAND="$RSYNC_COMMAND "${path}/" ."
  eval $RSYNC_COMMAND &> /dev/null
  printf "Done\n"

  # clean up temp files
  rm -rf "${path}"

  # Setup venv and db again
  install_cave
  reset_cave -y

  printf "Sync complete.\n"
  exit 0
}

kill_cave() { # Kill given tcp port (default 8000)
  local port="$(get_flag "8000" "--port" "$@")"
  case "$(uname -s)" in
    Linux*)     fuser -k "${port}/tcp";;
    Darwin*)    lsof -P | grep ":${port}" | awk '{print $2}' | xargs kill -9;;
    *)          printf "Error: OS not recognized."; exit 1;;
  esac
  printf "Activity on port ${port} ended.\n"
  exit 0
}

reset_cave() { # Run reset_db.sh
  local app_dir=$(find_app_dir)
  if [ "${app_dir}" = "-1" ]; then
    printf "Ensure you are in a valid CAVE app directory\n"
    exit 1
  else
    cd "${app_dir}"
  fi
  printf "${CHAR_LINE}\n"
  printf "Setup/Reset your app database:\n"
  if [[ "$(has_flag -y "$@")" != "true" ]]; then
    confirm_action "This will permanently remove all data stored in the app database"
  fi
  source venv/bin/activate
  printf "Configuring your app database (sudo required)..."
  ./utils/reset_db.sh &> /dev/null
  printf "Done.\n"
  printf "${CHAR_LINE}\n"
}

prettify_cave() { # Run api_prettify.sh and optionally prefftify.sh
  local app_dir=$(find_app_dir)
  if [ "${app_dir}" = "-1" ]; then
    printf "Ensure you are in a valid CAVE app directory\n"
    exit 1
  else
    cd "${app_dir}"
  fi
  source venv/bin/activate
  printf "Prettifying cave_api..."
  ./utils/api_prettify.sh &> /dev/null
  printf "Done\n"
  if [ "$(has_flag -all "$@")" = "true" ]; then
    printf "Prettifying everything else..."
    ./utils/prettify.sh &> /dev/null
    printf "Done\n"
  fi
  exit 0
}

test_cave() { # Run given file found in /cave_api/tests/
  # Check directory and files
  local app_dir=$(find_app_dir)
  if [ "${app_dir}" = "-1" ]; then
    printf "Ensure you are in a valid CAVE app directory\n"
    exit 1
  else
    cd "${app_dir}"
  fi
  ALL_FLAG=$(has_flag -all "$@")
  if [[ ! -f "cave_api/tests/$1" && "${ALL_FLAG}" != "true" ]]; then
    printf "Test $1 not found. Ensure you entered a valid test name.\n"
    printf "Tests available in 'cave_api/tests/' include \n $(ls cave_api/tests/)\n"
    exit 1
  fi
  # Activate venv and run given test
  source venv/bin/activate
  if [ "${ALL_FLAG}" != "true" ]; then
    python3 "cave_api/tests/$1"
  else
    for f in cave_api/tests/*.py; do python3 "$f"; done
  fi
  exit 0
}

install_cave() { # (re)installs all python requirements for cave app
  local app_dir=$(find_app_dir)
  if [ "${app_dir}" = "-1" ]; then
    printf "Ensure you are in a valid CAVE app directory\n"
    exit 1
  else
    cd "${app_dir}"
  fi
  printf "${CHAR_LINE}\n"
  printf "Setting up your python virtual environment:\n"
  printf "Removing old virtual enviornment if it exists..."
  rm -rf venv/ &> /dev/null
  printf "Done\n"
  # Install virtualenv and create venv
  local virtual=$($PYTHON3_BIN -m pip list | grep -F virtualenv)
  if [ "$virtual" = "" ]; then
    printf "Virtualenv not installed. Installing it for you..."
    $PYTHON3_BIN -m pip install virtualenv &> /dev/null
    printf "Done\n"
  fi
  printf "Creating a new virtual envrionment..."
  $PYTHON3_BIN -m virtualenv venv &> /dev/null
  printf "Done\n"

  # Activate venv and install requirements
  source venv/bin/activate
  # Since the virtualenv has been activated we use python3 instead of the bin location
  printf "Installing all python requirements in your new virtual environment..."
  python3 -m pip install --require-virtualenv -r requirements.txt  &> /dev/null
  printf "Done\n"
  printf "Package install completed.\n"
  printf "${CHAR_LINE}\n"
}

purge_cave() { # Removes cave app in specified dir and db/db user
  local app_name=$1
  cd "${app_name}"
  if ! valid_app_dir; then
    printf "Ensure you specified a valid CAVE app directory\n"
    exit 1
  fi
  cd ../
  printf "${CHAR_LINE}\n"
  printf "Purging CAVE App (${app_name}):\n"
  if [[ "$(has_flag -y "$@")" != "true" ]]; then
    confirm_action "This will permanently remove all data associated with your CAVE App (${app_name})"
  fi
  source "${app_name}/.env"
  printf "Removing files..."
  rm -rf "${app_name}"
  printf "Done\n"
  printf "Removing DB (sudo required)..."
  case "$(uname -s)" in
    Linux*)     purge_linux_db &> /dev/null;;
    Darwin*)    purge_mac_db &> /dev/null;;
    *)          printf "Error: OS not recognized."; exit 1;;
  esac
  printf "Done\n"
  printf "Purge complete.\n"
  printf "${CHAR_LINE}\n"
  exit 0
}

update_cave() { # Updates the cave cli 
  printf "${CHAR_LINE}\n"
  printf "Updating CAVE CLI...\n"
  # Change into the cave cli directory
  cd "${CAVE_PATH}"
  git fetch  &> /dev/null
  git checkout "$(get_flag main --version "$@")"  &> /dev/null
  git pull &> /dev/null
  printf "CAVE CLI updated.\n"
  printf "${CHAR_LINE}\n"
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
      ensure_postgres_running
      run_cave "$@"
    ;;
    update)
      update_cave "$@"
    ;;
    uninstall)
      uninstall_cli
    ;;
    create)
      check_python
      ensure_postgres_running
      shift
      create_cave "$@"
    ;;
    upgrade)
      check_python
      ensure_postgres_running
      shift
      upgrade_cave "$@"
    ;;
    sync)
      shift
      sync_cave "$@"
    ;;
    kill)
      shift
      kill_cave "$@"
    ;;
    reset)
      ensure_postgres_running
      reset_cave "$@"
      exit 0
    ;;
    prettify)
      shift
      prettify_cave "$@"
    ;;
    test)
      shift
      test_cave "$@"
    ;;
    reinstall-pkgs)
      install_cave
    ;;
    setup)
      ensure_postgres_running
      install_cave
      reset_cave "$@"
    ;;
    purge)
      shift
      ensure_postgres_running
      purge_cave "$@"
    ;;
    *)
      printf "Unrecognized Command ($1) passed.\nUse cave --help for information on how to use the cave cli.\n"
    ;;
  esac
}

main "$@"
