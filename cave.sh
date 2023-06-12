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
readonly CHAR_LINE="============================="
readonly HTTPS_URL="https://github.com/MIT-CAVE/cave_app.git"
readonly IP_REGEX="([0-9]{1,3}\.)+([0-9]{1,3}):[0-9][0-9][0-9][0-9]+"
readonly MIN_DOCKER_VERSION="23.0.6"
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

printf_header() {
  printf "\n%s\n" $CHAR_LINE
  printf "%s\n" "$@"
  printf "%s\n" $CHAR_LINE
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
    printf "Your current %s version (%s) is too old. %s" "$PROGRAM_NAME" "$CURRENT_VERSION" "$ERROR_STRING"
    if [ "${EXIT_BOOL}" = "1" ]; then
      exit 1
    fi
  fi

}

check_docker() { # Validate docker is installed, running, and is correct version
  install_docker="\nPlease install docker version ${MIN_DOCKER_VERSION} or greater. \nFor more information see: 'https://docs.docker.com/get-docker/'"
  CURRENT_DOCKER_VERSION=$(docker --version | sed -e 's/Docker version //' -e 's/, build.*//')
  validate_version "docker" "1" "$install_docker" "$MIN_DOCKER_VERSION" "$CURRENT_DOCKER_VERSION"
  printf "Docker Check Passed!\n"  2>&1 | print_if_verbose "$@"
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
      printf "The folder '%s' is missing in the root project directory.\n" "$folder" >&2
    fi
  done
  # Check the files
  for file in .env manage.py requirements.txt; do
      if ! [ -f ${file} ]; then
        printf "The file '%s' is missing in the root project directory.\n" "$file" >&2
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
  VERSION="$(cat "${CAVE_PATH}/VERSION")"
  HELP="$(cat "${CAVE_PATH}/help.txt")"
  cat 1>&2 <<EOF
${CHAR_LINE}
CAVE CLI ($VERSION)
${CHAR_LINE}

${HELP}

EOF
}

print_version(){
  printf "%s" "$(cat "${CAVE_PATH}/VERSION")\n"
}

run_cave() { # Runs the cave app in the current directory
  local app_dir app_name
  app_dir=$(readlink -f "$(find_app_dir)")
  app_name=$(basename "$app_dir")
  if [ "${app_dir}" = "-1" ]; then
    printf "Ensure you are in a valid CAVE app directory\n"
    exit 1
  else
    cd "${app_dir}" || exit 1
  fi

  kill_cave
  docker build . --tag cave-app

  printf_header "Starting CAVE App:"

  source .env
  docker run --volume "${app_name}_pg_volume:/var/lib/postgresql/data" --network cave-net --name "${app_name}_postgres" -e POSTGRES_PASSWORD="$DATABASE_PASSWORD" -e POSTGRES_USER="$DATABASE_USER" -e POSTGRES_DB="$DATABASE_NAME" -d postgres:15.3-alpine3.18

  if [[ "$1" != "" && "$1" =~ $IP_REGEX ]]; then
    export PORT OFFSET_OPEN IP
    IP=$(echo "$1" | perl -nle'print $& while m{([0-9]{1,3}\.)+([0-9]{1,3})}g')
    PORT=$(echo "$1" | perl -nle'print $& while m{(?<=:)\d\d\d[0-9]+}g')
    OPEN=$(nc -z 127.0.0.1 "$PORT"; echo $?)
    if [[ "$OPEN" = "1" ]]; then
      docker run -d --restart unless-stopped -p "$IP:$PORT:8000" --network cave-net --volume "$app_dir/utils/lan_hosting:/certs" --name "${app_name}_nginx" -e CAVE_HOST="${app_name}_django" --volume "$CAVE_PATH/nginx_ssl.conf.template:/etc/nginx/templates/default.conf.template:ro" nginx || return
      docker run -it -p 8000 --network cave-net --volume "$app_dir:/app" --name "${app_name}_django" cave-app /app/utils/run_dev_server.sh
      docker rm --force "${app_name}_nginx"
    else
      printf "The specified port is in use. Please try another."
      exit 1
    fi
  else
    docker run -it -p 8000:8000 --network cave-net --volume "$app_dir:/app" --name "${app_name}_django" cave-app /app/utils/run_dev_server.sh
  fi

  docker rm --force "${app_name}_postgres"
}

upgrade_cave() { # Upgrade cave_app while preserving .env and cave_api/
  local app_dir
  app_dir=$(find_app_dir)
  if [ "${app_dir}" = "-1" ]; then
    printf "Ensure you are in a valid CAVE app directory\n"
    exit 1
  else
    cd "${app_dir}" || exit 1
  fi

  if [[ "$(has_flag -y "$@")" != "true" ]]; then
    confirm_action "This will potentially update all files not in 'cave_api/' or '.env' and reset your database"
  fi
  if [ "$(has_flag --version "$@")" = "true" ]; then
    local BRANCH_STRING
    BRANCH_STRING="--branch $(get_flag "" "--version" "$@")"
  else
    local BRANCH_STRING=""
  fi
  sync_cave -y --include "'cave_api/docs'" --exclude "'.env' '.gitignore' 'cave_api/*'" --url "$(get_flag "$HTTPS_URL" "--url" "$@")" "$BRANCH_STRING" "$@"
  printf "Upgrade complete.\n"
}

env_create() { # creates .env file for create_cave
  local save_inputs=$2
  rm .env 2>&1 | print_if_verbose
  cp example.env .env 2>&1 | print_if_verbose
  local key line newenv
  key=$(docker run cave-app python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())")
  line=$(grep -n --colour=auto "SECRET_KEY" .env | cut -d: -f1)
  newenv=$(awk "NR==${line} {print \"SECRET_KEY='${key}'\"; next} {print}" .env)
  local key2=""
  if [ "${ADMIN_EMAIL}" = "" ]; then
    ADMIN_EMAIL="$1@example.com"
  fi
  printf_header "Set up your new app environment (.env) variables:"
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
  key="$1_postgres"
  line=$(grep -n --colour=auto "DATABASE_HOST" .env | cut -d: -f1)
  newenv=$(awk "NR==${line} {print \"DATABASE_HOST='${key}'\"; next} {print}" .env)
  echo "$newenv" > .env

  # Save inputs
  if [ "${save_inputs}" = "true" ]; then
    # Write MAPBOX_TOKEN to config line 2 and ADMIN_EMAIL to config line 3
    local inputs="MAPBOX_TOKEN='${MAPBOX_TOKEN}'\nADMIN_EMAIL='${ADMIN_EMAIL}'\n"
    local newConfig
    newConfig=$(awk "NR==2 {print \"${inputs}\"; next} NR==3 {next} {print}" "${CAVE_PATH}/CONFIG")
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
  printf "\n${CHAR_LINE}\n"
  printf "App Creation:\n"
  printf "${CHAR_LINE}\n"
  # Clone the repo
  printf "Downloading the app template..."
  if [ "$(has_flag --version "$@")" = 'true' ]; then
    git clone -b "$(get_flag main --version "$@")" --single-branch "${CLONE_URL}" "$1" 2>&1 | print_if_verbose
  else
    git clone --single-branch "${CLONE_URL}" "$1" 2>&1 | print_if_verbose
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

  # Setup .env file
  env_create "$1" "$(has_flag -save-inputs "$@")"

  # Prep git repo
  printf "\n${CHAR_LINE}\n"
  printf "Version Control:\n"
  printf "${CHAR_LINE}\n"
  printf "Configuring git repository..."
  rm -rf .git
  git init 2>&1 | print_if_verbose
  case "$(uname -s)" in
    Linux*)     sed -i 's/.env//g' .gitignore;;
    Darwin*)    sed -i '' 's/.env//g' .gitignore;;
    *)          printf "Error: OS not recognized."; exit 1;;
  esac
  git add . 2>&1 | print_if_verbose
  git commit -m "Initialize CAVE App" 2>&1 | print_if_verbose
  git branch -M main 2>&1 | print_if_verbose
  printf "Done.\n"
  printf "\n${CHAR_LINE}\n"
  printf "App Creation Status:\n"
  printf "${CHAR_LINE}\n"
  printf "App '$1' created successfully!\n"
  printf "Note: Created variables and addtional configuration options are availible in $1/.env\n"
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
    printf "Done.\n"
    ;;
  *)
    printf "Uninstall canceled\n"
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
  printf "\n${CHAR_LINE}\n"
  printf "Sync:\n"
  printf "${CHAR_LINE}\n"

  printf "Downloading repo to sync..."
  local path=$(mktemp -d)
  local CLONE_URL="$(get_flag "none" --url "$@")"
  local CLONE_BRANCH="$(get_flag "none" --branch "$@")"
  if [[ "${CLONE_BRANCH}" != 'none' ]]; then
    git clone -b "$(get_flag '' --branch "$@")" --single-branch "${CLONE_URL}" "$path" 2>&1 | print_if_verbose
  else
    git clone --single-branch "${CLONE_URL}" "$path" 2>&1 | print_if_verbose
  fi
  if [[ "$(is_dir_empty "$path")" = 'true' ]]; then
    printf "Failed!\nEnsure you have access rights to the repository: ${CLONE_URL}\nEnsure you specified a valid branch: ${CLONE_BRANCH}.\n"
    rm -rf "${path}"
    exit 1
  fi
  printf "Done.\n"

  printf "Syncing files..."
  RSYNC_INCLUDE=$(get_flag "" "--include" "$@")
  RSYNC_EXCLUDE=$(get_flag "" "--exclude" "$@")
  RSYNC_COMMAND="rsync -a --exclude='.git'"
  for INCLUDE in $RSYNC_INCLUDE; do
      RSYNC_COMMAND="$RSYNC_COMMAND --include=${INCLUDE}"
  done
  for EXCLUDE in $RSYNC_EXCLUDE; do
      RSYNC_COMMAND="$RSYNC_COMMAND --exclude=${EXCLUDE}"
  done
  RSYNC_COMMAND="$RSYNC_COMMAND "${path}/" ."
  eval $RSYNC_COMMAND 2>&1 | print_if_verbose
  printf "Done\n"

  # clean up temp files
  rm -rf "${path}"

  # Setup docker and db again
  reset_db -y

  printf "Sync complete.\n"
  exit 0
}

kill_cave() { # Kill given tcp port (default 8000)
  local app_dir app_name
  app_dir=$(readlink -f "$(find_app_dir)")
  app_name=$(basename "$app_dir")
  if [ "${app_dir}" = "-1" ]; then
    printf "Ensure you are in a valid CAVE app directory\n"
    exit 1
  else
    cd "${app_dir}" || exit
  fi
  docker rm --force "${app_name}_django" "${app_name}_nginx" "${app_name}_postgres"
  printf "Killed cave app\n"
}

reset_db() {
  local app_dir app_name
  app_dir=$(readlink -f "$(find_app_dir)")
  app_name=$(basename "$app_dir")
  if [ "${app_dir}" = "-1" ]; then
    printf "Ensure you are in a valid CAVE app directory\n"
    exit 1
  else
    cd "${app_dir}" || exit
  fi
  kill_cave
  docker volume rm "${app_name}_pg_volume"
}

prettify_cave() { # Run api_prettify.sh and optionally prefftify.sh
  local app_dir=$(find_app_dir)
  if [ "${app_dir}" = "-1" ]; then
    printf "Ensure you are in a valid CAVE app directory\n"
    exit 1
  else
    cd "${app_dir}"
  fi

  printf "Prettifying cave_api..."
  docker run --volume "$app_dir/cave_api:/app/cave_api" cave-app /app/utils/api_prettify.sh 2>&1 | print_if_verbose
  printf "Done\n"
  if [ "$(has_flag -all "$@")" = "true" ]; then
    printf "Prettifying everything else..."
    docker run --volume "$app_dir:/app" cave-app /app/utils/prettify.sh 2>&1 | print_if_verbose
    printf "Done\n"
  fi
}

test_cave() { # Run given file found in /cave_api/tests/
  # Check directory and files
  local app_dir
  app_dir=$(find_app_dir)
  if [ "$app_dir" = "-1" ]; then
    printf "Ensure you are in a valid CAVE app directory\n"
    exit 1
  else
    cd "$app_dir" || exit 1
  fi
  ALL_FLAG=$(has_flag -all "$@")
  if [[ ! -f "cave_api/tests/$1" && "${ALL_FLAG}" != "true" ]]; then
    printf "Test %1 not found. Ensure you entered a valid test name.\n" "$1"
    printf "Tests available in 'cave_api/tests/' include \n %s\n" "$(ls cave_api/tests/)"
    exit 1
  fi
  # Run given test in docker
  if [ "${ALL_FLAG}" != "true" ]; then
    docker run --volume "$app_dir:/app" cave-app python "/app/cave_app/cave_api/tests/$1"
  else
    for f in cave_api/tests/*.py; do
      docker run --volume "$app_dir:/app" cave-app python "/app/cave_app/$f"
    done
  fi
}

purge_cave() { # Removes cave app in specified dir and db/db user
  local app_name=$1
  cd "${app_name}" || printf "No directory %s\n" "$app_name"
  if ! valid_app_dir; then
    printf "Ensure you specified a valid CAVE app directory\n"
    exit 1
  fi
  cd ../
  printf "\n%s\n" $CHAR_LINE
  printf "Purging CAVE App (%s):\n" "$app_name"
  printf "%s\n" $CHAR_LINE
  if [[ "$(has_flag -y "$@")" != "true" ]]; then
    confirm_action "This will permanently remove all data associated with your CAVE App (${app_name})"
  fi
  cd "$app_name" || exit
  reset_db
  cd ../
  source "${app_name}/.env"
  printf "Removing files..."
  sudo rm -rf "${app_name}"
  printf "Done\n"
  printf "Purge complete.\n"
}

update_cave() { # Updates the cave cli
  printf "Updating CAVE CLI..."
  # Change into the cave cli directory
  cd "${CAVE_PATH}" || exit 1
  git fetch 2>&1 | print_if_verbose
  git checkout "$(get_flag main --version "$@")" 2>&1 | print_if_verbose
  git pull 2>&1 | print_if_verbose
  printf "Done.\n"
  printf "CAVE CLI updated.\n"
}

print_if_verbose () {
  if [ -n "${1}" ]; then 
      IN="${1}"
      if [ "$VERBOSE" = 'true' ]; then
        printf "${IN}\n"
      fi
  else
      while read IN; do
          if [ "$VERBOSE" = 'true' ]; then
            printf "${IN}\n"
          fi
      done
  fi
}


main() {
  # Source the the CONFIG file
  source "${CAVE_PATH}/CONFIG"
  # If no command is passed default to the help command
  if [[ $# -lt 1 ]]; then
    local MAIN_COMMAND="help"
  else
    local MAIN_COMMAND=$1
    shift
  fi
  VERBOSE=$(has_flag -v "$@")
  case $MAIN_COMMAND in
    help | --help | -h)
      # Independent CLI Command
      print_help
    ;;
    version | --version | -v)
      # Independent CLI Command
      print_version
    ;;
    update)
      # Independent CLI Command
      update_cave "$@"
    ;;
    uninstall)
      # Independent CLI Command
      uninstall_cli
    ;;
    create)
      # Does NOT require being inside app_dir
      check_docker "$@"
      create_cave "$@"
    ;;
    purge)
      # Requires being in parent of app_dir
      check_docker "$@"
      purge_cave "$@"
    ;;
    run | start)
      # Requires being inside app_dir
      check_docker "$@"
      # Starts all required containers for the app
      run_cave "$@"
    ;;
    kill)
      # Requires being inside app_dir
      check_docker "$@"
      # Kills all containers for the app
      kill_cave "$@"
    ;;
    reset-db)
      # Requires being inside app_dir
      check_docker "$@"
      # Runs kill, then
      # Removes the volume for the db
      reset_db "$@"
    ;;
    upgrade)
      # Requires being inside app_dir
      check_docker "$@"
      upgrade_cave "$@"
    ;;
    sync)
      # Requires being inside app_dir
      check_docker "$@"
      sync_cave "$@"
    ;;
    prettify)
      # Requires being inside app_dir
      check_docker "$@"
      prettify_cave "$@"
    ;;
    test)
      # Requires being inside app_dir
      check_docker "$@"
      test_cave "$@"
    ;;
    *)
      printf "Unrecognized Command (%s) passed.\nUse cave --help for information on how to use the cave cli.\n" "$MAIN_COMMAND"
    ;;
  esac
}

main "$@"
