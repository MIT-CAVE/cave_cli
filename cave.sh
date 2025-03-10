#!/bin/bash
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
# Update environment
declare -xr CAVE_PATH="${HOME}/.cave_cli"
readonly CURRENT_ENV_VARIABLES=(
  "DATABASE_IMAGE"
  "DATABASE_PASSWORD"
  "DJANGO_ADMIN_EMAIL"
  "DJANGO_ADMIN_FIRST_NAME"
  "DJANGO_ADMIN_LAST_NAME"
  "DJANGO_ADMIN_PASSWORD"
  "DJANGO_ADMIN_USERNAME"
  "SECRET_KEY"
  "STATIC_APP_URL"
  "STATIC_APP_URL_PATH"
)
readonly RETIRED_ENV_VARIABLES=(
  "DATABASE_HOST"
  "DATABASE_PORT"
  "DATABASE_NAME"
  "DATABASE_USER"
)

printf_header() {
  printf "%s\n" "$CHAR_LINE" | pipe_log "INFO"
  printf "%s" "$@" | pipe_log "INFO"
  printf "%s\n" "$CHAR_LINE" | pipe_log "INFO"
}

validate_version() {
  local PROGRAM_NAME="$1"
  local EXIT_BOOL="$2"
  local ERROR_STRING="$3"
  local MIN_VERSION="$4"
  local CURRENT_VERSION="$5"
  if [ ! "$(printf '%s\n' "$MIN_VERSION" "$CURRENT_VERSION" | sort -V | head -n1)" = "$MIN_VERSION" ]; then
    printf "Your current %s version (%s) is too old. $ERROR_STRING" "$PROGRAM_NAME" "$CURRENT_VERSION" | pipe_log "ERROR"
    if [ "${EXIT_BOOL}" = "1" ]; then
      exit 1
    fi
  fi

}

check_docker() { # Validate docker is installed, running, and is correct version
  install_docker="\nPlease install docker version ${MIN_DOCKER_VERSION} or greater. \nFor more information see: 'https://docs.docker.com/get-docker/'"
  CURRENT_DOCKER_VERSION=$(docker --version | sed -e 's/Docker version //' -e 's/, build.*//')
  validate_version "docker" "1" "$install_docker" "$MIN_DOCKER_VERSION" "$CURRENT_DOCKER_VERSION"
  if ! docker info > /dev/null 2>&1 ; then
    log "Docker not running... Please start docker and try again!" "ERROR"
    exit 1
  fi
  printf "Docker Check Passed!\n" | pipe_log "DEBUG"
}

dockerfile_help() { # Add additional Dockerfile help if no Dockerfile is found
  if [ ! -f "Dockerfile" ]; then
    printf "No Dockerfile found in current directory.\nIf you are using a legacy cave app (v0.0.0-v1.4.0):" | pipe_log "ERROR"
    printf "    - You should run commands using legacy mode" | pipe_log "ERROR"
    printf "      - EG: 'cave run -legacy'" | pipe_log "ERROR"
    printf "      - Note: See 'cave help -legacy' for more information" | pipe_log "ERROR"
    printf "    - You should upgrade your app to the latest version" | pipe_log "ERROR"
    printf "      - EG: 'cave upgrade'" | pipe_log "ERROR"
  fi

}

get_app() {
  app_dir=$(find_app_dir)
  cd "$app_dir" || exit 1
  app_name=$(basename "$(readlink -f "$app_dir")")
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
  local failed=false
  if ! [[ -f manage.py && -d cave_core ]]; then
    failed=true
    return 1
  fi
  # Check the folders
  for folder in cave_api cave_app cave_core; do
    if ! [ -d ${folder} ] ; then
      printf "The folder '${folder}' is missing in the root project directory.\n" | pipe_log "ERROR" >&2
      failed=true
    fi
  done
  # Check the files
  for file in .env manage.py requirements.txt Dockerfile; do
      if ! [ -f ${file} ]; then
        printf "The file '${file}' is missing in the root project directory.\n" | pipe_log "ERROR" >&2
        failed=true
      fi
  done
  # check the .env file has appropriate variables
  source .env
  for var in "${CURRENT_ENV_VARIABLES[@]}"; do
    if [ -z "${!var+x}" ]; then
      printf "The env variable '%s' is missing from the '.env' file.\n" "$var" | pipe_log "ERROR" >&2
      failed=true
    fi
  done
  for var in "${RETIRED_ENV_VARIABLES[@]}"; do
    if [ -n "${!var+x}" ]; then
      printf "The env variable '%s' is retired and should be removed from the '.env' file.\n" "$var" | pipe_log "ERROR" >&2
      failed=true
    fi
  done
  dockerfile_help
  [ $failed = false ]
}

find_app_dir() { # Finds path to parent app folder if present
  path="${PWD}/"
  while ! valid_app_dir; do
    cd ../
    path="${path}../"
    if [ "${PWD}" = "/" ]; then
      echo "-1"
      exit 1
    fi
  done
  if [ "${path}" = "-1" ]; then
    printf "Ensure you are in a valid CAVE app directory\n" | pipe_log "ERROR"
    exit 1
  fi
  echo "${PWD}"
}

confirm_action() { # Checks user input for an action
  local confirm_text="$1"
    read -r -p "${confirm_text}. Would you like to continue? [y/N] " input
        case ${input} in
      [yY][eE][sS] | [yY])
        :
        ;;
      [nN][oO] | [nN] | "")
        printf "Operation canceled.\n" | pipe_log "ERROR"
        exit 1
        ;;
      *)
        printf "Invalid input: Operation canceled.\n" | pipe_log "ERROR"
        exit 1
        ;;
    esac
}

print_help() { # Prints the help text for cave_cli
  VERSION="$(cat "${CAVE_PATH}/VERSION")"
  HELP="$(cat "${CAVE_PATH}/help.txt")"
  printf_header "CAVE CLI ($VERSION)"
  printf "\n\n$HELP\n"
}

print_version(){
  printf "%s" "$(cat "${CAVE_PATH}/VERSION")" | pipe_log "INFO"
}

is_local_port_open() {
  local PORT=$1
  OPEN=$(nc -z 127.0.0.1 "$PORT"; echo $?)
  if [[ "$OPEN" = "1" ]]; then
    echo "true"
  else
    echo "false"
  fi
}

find_next_open_port() {
  local PORT=$1
  if [[ "$(is_local_port_open "$PORT")" = "true" ]]; then
    echo "$PORT"
  else
    find_next_open_port "$((PORT + 1))"
  fi
}

# Create a function to check if an input has `ERROR` in and exit if it does, otherwise pass the input on
check_error_and_return() {
  while read -r line || [ -n "$line" ]; do
    if [[ "$line" == *"ERROR"* ]]; then
      echo "true" > "$tmp_docker_error_file"
    fi
    printf "%s\n" "$line" 
  done
}

build_image() {
  remove_docker_containers
  printf "Getting Docker setup... (this may take a while)\n" | pipe_log "INFO"
  # Make a tmp file for this process to store the error state
  tmp_docker_error_file=$(mktemp)
  echo "false" > "$tmp_docker_error_file"
  # Pass has_docker_error to check_error_and_pipe_log to update the global variable
  docker build . --tag "cave-app:${app_name}" 2>&1 | check_error_and_return | pipe_log "DEBUG"

  # Check if there was an error during the build process
  has_docker_error=$(cat "$tmp_docker_error_file")
  rm "$tmp_docker_error_file"
  if [ "$has_docker_error" = true ]; then
    printf "An ERROR was returned during the Docker container build process." | pipe_log "ERROR"
    printf "The CAVE CLI command is exiting early due to this ERROR." | pipe_log "ERROR"
    printf "Consider running your command again in verbose mode to get more information." | pipe_log "ERROR"
    printf "EG: 'cave reset -verbose' or 'cave run -verbose'" | pipe_log "ERROR"
    exit 1
  fi
}

run_cave() { # Runs the cave app in the current directory
  build_image

  if [[ "$(has_flag -interactive "$@")" == "true" || "$(has_flag -it "$@")" == "true" ]]; then
    server_command=("bash")
    printf_header "CAVE App: (Interactive)"
  else
    entrypoint="$(get_flag "./utils/run_server.sh" "--entrypoint" "$@")"
    printf_header "CAVE App: ($entrypoint)"
    server_command=("$entrypoint" "$@")
  fi

  if [[ "$(has_flag --docker-args "$@")" == "true" ]]; then
    docker_args="$(get_flag "" "--docker-args" "$@")"
    echo "docker-args: $docker_args" | pipe_log "INFO"
  else
    docker_args=""
  fi

  # Use DATABASE_COMMAND "postgres -c listen_addresses=*" as the default command if not specified
  if [ -z "$DATABASE_COMMAND" ]; then
    DATABASE_COMMAND="postgres -c listen_addresses=*"
    printf "DATABASE_COMMAND not set in '.env' file. Using "postgres -c listen_addresses=*" as default." | pipe_log "DEBUG"
  fi

  docker network create cave-net:${app_name} 2>&1 | pipe_log "DEBUG"
  source .env
  docker run -d \
    ${docker_args} \
    --volume "${app_name}_pg_volume:/var/lib/postgresql/data" \
    --network cave-net:${app_name} \
    --name "${app_name}_db_host" \
    -e POSTGRES_PASSWORD="$DATABASE_PASSWORD" \
    -e POSTGRES_USER="${app_name}_user" \
    -e POSTGRES_DB="${app_name}_name"\
    "$DATABASE_IMAGE" $DATABASE_COMMAND 2>&1 | pipe_log "DEBUG"

  # Use redis:7 as the default image if not specified
  if [ -z "$CACHE_IMAGE" ]; then
    printf "CACHE_IMAGE not set in '.env' file. Using valkey/valkey:7 as default." | pipe_log "WARN"
    CACHE_IMAGE="valkey/valkey:7"
  fi

  docker run -d \
    ${docker_args} \
    --volume "${app_name}_redis_volume:/data" \
    --network cave-net:${app_name} \
    --name "${app_name}_redis_host" \
    "$CACHE_IMAGE" \
    --save 7200 1 2>&1 | pipe_log "DEBUG"

  if [[ "$1" != "" && "$1" =~ $IP_REGEX ]]; then
    export PORT IP
    IP=$(echo "$1" | perl -nle'print $& while m{([0-9]{1,3}\.)+([0-9]{1,3})}g')
    PORT=$(echo "$1" | perl -nle'print $& while m{(?<=:)\d\d\d[0-9]+}g')
    OPEN=$(nc -z 127.0.0.1 "$PORT"; echo $?)
    if [[ "$OPEN" = "1" ]]; then
      if [[ "${server_command}" == "./utils/run_server.sh" ]]; then
        printf "Your Cave App can be accessed from Chrome at:\nhttps://${IP}:${PORT}\n\n" | pipe_log "INFO"
      fi
      docker run -d \
        ${docker_args} \
        --restart unless-stopped \
        -p "$IP:$PORT:8000" \
        --network cave-net:${app_name} \
        --volume "$app_dir/utils/lan_hosting:/certs" \
        --name "${app_name}_nginx_host" \
        -e CAVE_HOST="${app_name}_django" \
        -e CAVE_PORT=$PORT \
        -e CAVE_IP=$IP \
        --volume "$app_dir/utils/nginx_ssl.conf.template:/etc/nginx/templates/default.conf.template:ro" \
        nginx 2>&1 | pipe_log "DEBUG"
      docker run -it \
        ${docker_args} \
        -p 8000 \
        --network cave-net:${app_name} \
        --volume "$app_dir:/app" \
        --volume "$CAVE_PATH:/cave_cli" \
        --name "${app_name}_django" \
        -e CSRF_TRUSTED_ORIGIN="$IP:$PORT" \
        -e DATABASE_HOST="${app_name}_db_host" \
        -e DATABASE_USER="${app_name}_user" \
        -e DATABASE_PASSWORD="$DATABASE_PASSWORD" \
        -e DATABASE_NAME="${app_name}_name"\
        -e DATABASE_PORT=5432 \
        -e REDIS_HOST="${app_name}_redis_host" \
        -e REDIS_PORT=6379 \
        "cave-app:${app_name}" "${server_command[@]}" 2>&1
    else
      printf "The specified port is in use. Please try another." | pipe_log "ERROR"
      exit 1
    fi
  else
    local PORT=$(find_next_open_port 8000)
    if [[ "${server_command}" == "./utils/run_server.sh" ]]; then
      printf "Your Cave App can be accessed from Chrome at:\nhttp://localhost:${PORT}\n\n" | pipe_log "INFO"
    fi
    docker run -it \
      ${docker_args} \
      -p ${PORT}:8000 \
      --network cave-net:${app_name} \
      --volume "$app_dir:/app" \
      --volume "$CAVE_PATH:/cave_cli" \
      --name "${app_name}_django" \
      -e DATABASE_HOST="${app_name}_db_host" \
      -e DATABASE_USER="${app_name}_user" \
      -e DATABASE_PASSWORD="$DATABASE_PASSWORD" \
      -e DATABASE_NAME="${app_name}_name"\
      -e DATABASE_PORT=5432 \
      -e REDIS_HOST="${app_name}_redis_host" \
      -e REDIS_PORT=6379 \
      "cave-app:${app_name}" "${server_command[@]}" 2>&1
  fi
  printf "Stopping Running Containers...\n" | pipe_log "DEBUG"
  remove_docker_containers
}

upgrade_env() {
  printf "Upgrading .env..." | pipe_log "INFO"
  export NEW_APP_URL_PATH
  NEW_APP_URL_PATH=$(grep "^STATIC_APP_URL_PATH=" "$1/example.env") \
    perl -pi -e 's/^STATIC_APP_URL_PATH=.*$/$ENV{NEW_APP_URL_PATH}/g' .env
  printf "Done\n" | pipe_log "INFO"
}

upgrade_cave() { # Upgrade cave_app while preserving .env and cave_api/
  if [[ "$(has_flag -y "$@")" != "true" ]]; then
    confirm_action "This will potentially update all files not in 'cave_api/' or '.env' and reset your database"
  fi
  printf_header "Upgrade:"
  printf "Upgrading CAVE App via a Sync operation...\n\n" | pipe_log "INFO"
  # shellcheck disable=SC2046 # need to expand the args
  sync_cave -y \
    --include "'cave_api/docs'" \
    --exclude "'.env' '.gitignore' 'cave_api/*'" \
    $( [[ "$(has_flag -skip-env-upgrade "$@")" != "true" ]] && printf %s '--post-sync upgrade_env' ) \
    --url "$(get_flag "$HTTPS_URL" "--url" "$@")" \
    --branch "$(get_flag "main" "--version" "$@")" \
    "$@"
  remove_licence_info "$app_dir"
  printf "Upgrade complete.\n" | pipe_log "INFO"
}

env_create() { # creates .env file for create_cave
  rm .env 2>&1 | pipe_log "DEBUG"
  cp example.env .env 2>&1 | pipe_log "DEBUG"
  local key line newenv
  build_image
  key=$(docker run --rm "cave-app:${app_name}" python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())")
  line=$(grep -n --colour=auto "SECRET_KEY" .env | cut -d: -f1)
  newenv=$(awk "NR==${line} {print \"SECRET_KEY='${key}'\"; next} {print}" .env)
  local key2=""
  if [ "${ADMIN_EMAIL}" = "" ]; then
    ADMIN_EMAIL="$1@example.com"
  fi
  printf_header "Set up your new app environment (.env) variables:"
  echo "$newenv" > .env
  printf "If you want to use a globe view or mapbox maps, you will need a valid Mapbox Token.\n" | pipe_log "INFO"
  printf "This is not required, but will allow you to use the full functionality of the app.\n" | pipe_log "INFO"
  printf "Mapbox tokens can be created by making an account on 'https://mapbox.com'\n" | pipe_log "INFO"
  read -r -p "Would you like to use Mapbox? [y/N] " input
  case ${input} in
  [yY][eE][sS] | [yY])
    SAVED_MAPBOX_TOKEN=$(cat "${CAVE_PATH}/MAPBOX_TOKEN" 2>/dev/null)
    read -r -p "Please input your Mapbox Public Token. Leave blank for last used token (*${SAVED_MAPBOX_TOKEN:(-4)}): " key
    if [ "${key}" = "" ]; then
      key="${SAVED_MAPBOX_TOKEN}"
    else
      # If a new token is inputted, save it
      printf "Saving mapbox token for future use...\n" | pipe_log "DEBUG"
      printf "%s" "$key" > "${CAVE_PATH}/MAPBOX_TOKEN"
    fi
    line=$(grep -n --colour=auto "MAPBOX_TOKEN" .env | cut -d: -f1)
    newenv=$(awk "NR==${line} {print \"MAPBOX_TOKEN='${key}'\"; next} {print}" .env)
    echo "$newenv" > .env
    ;;
  *)
    printf "Mapbox skipped\n" | pipe_log "INFO"
    ;;
  esac
  key=""
  printf "\n"
  read -r -p "Please input an admin email. Leave blank for default(${ADMIN_EMAIL}): " key
  if [ "${key}" = "" ]; then
    key="${ADMIN_EMAIL}"
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
  key=$(LC_ALL=C tr -dc A-Za-z0-9 </dev/urandom | head -c 16)
  # Code to choose or generate a password for the database
  # Commented out to auto-generate a password
  # key=""
  # key2=""
  # printf "\n"
  # while [ "${key2}" = "" ]; do
  #   printf "\n"
  #   read -r -s -p "Please input a database password. Leave blank to randomly generate one: " key
  #   if [ "${key}" = "" ]; then
  #     key=$(LC_ALL=C tr -dc A-Za-z0-9 </dev/urandom | head -c 16)
  #     key2="Placeholder"
  #   else
  #     printf "\n"
  #     read -r -s -p "Retype database password to confirm: " key2
  #     if [ "${key}" != "${key2}" ]; then
  #       printf "Passwords didn't match. Please try again\n"
  #       key2=""
  #     fi
  #   fi
  # done
  line=$(grep -n --colour=auto "DATABASE_PASSWORD" .env | cut -d: -f1)
  newenv=$(awk "NR==${line} {print \"DATABASE_PASSWORD='${key}'\"; next} {print}" .env)
  echo "$newenv" > .env
  key="$1_db"

  printf "\n"
}

create_cave() { # Create a cave app instance in folder $1
  local valid CLONE_URL
  valid=$(valid_app_name "$1")
  app_name=$1
  app_dir=$PWD/$1

  if [[ ! "${valid}" = "" ]]; then
    printf "%s\n" "$valid" | pipe_log "ERROR"
    exit 1
  fi
  if [[ -d "$1" ]]; then
    printf "Cannot create app '%s': This folder already exists in the current directory\n" "$1" | pipe_log "ERROR"
    exit 1
  fi
  
  CLONE_URL=$(get_flag "${HTTPS_URL}" "--url" "$@")
  printf_header "App Creation:"
  # Clone the repo
  printf "Downloading the app template..." | pipe_log "INFO"
  if [ "$(has_flag --version "$@")" = 'true' ]; then
    git clone -b "$(get_flag "main" "--version" "$@")" --single-branch "${CLONE_URL}" "$1" 2>&1 | pipe_log "DEBUG"
  else
    git clone --single-branch "${CLONE_URL}" "$1" 2>&1 | pipe_log "DEBUG"
  fi
  if [[ ! -d "$1" ]]; then
    printf "\nClone failed. Ensure you used a valid version.\n" | pipe_log "ERROR"
    printf "The version must be a tag (or branch) listed at ${CLONE_URL}.\n" | pipe_log "ERROR"
    exit 1
  fi
  printf "Done\n" | pipe_log "INFO"

  # cd into the created app
  cd "$1" || exit 1

  remove_licence_info "$app_dir"

  # Create a fake .env file to allow installation to proceed
  touch .env

  # Setup .env file
  env_create "$1"

  # Reset the db
  reset -y

  # Prep git repo
  printf_header "Version Control:" | pipe_log "INFO"
  printf "Configuring git repository..." | pipe_log "INFO"
  rm -rf .git
  git init 2>&1 | pipe_log "DEBUG"
  case "$(uname -s)" in
    Linux*)     sed -i 's/.env//g' .gitignore;;
    Darwin*)    sed -i '' 's/.env//g' .gitignore;;
    *)          printf "Error: OS not recognized." | pipe_log "ERROR"; exit 1;;
  esac
  git add . 2>&1 | pipe_log "DEBUG"
  # If media is not in the gitignore, add it and add it to the commit
  if ! grep -q "media" .gitignore; then
    echo "# Media" >> .gitignore
    echo "media" >> .gitignore
  fi
  git add .
  git commit -m "Initialize CAVE App" 2>&1 | pipe_log "DEBUG"
  git branch -M main 2>&1 | pipe_log "DEBUG"
  printf "Done.\n" | pipe_log "INFO"

  printf_header "App Creation Status:" | pipe_log "INFO"
  printf "App '%s' created successfully!\n" "$1" | pipe_log "INFO"
  printf "Created variables and additional configuration options are available in %s/.env\n" "$1" | pipe_log "INFO"
}

uninstall_cli() { # Remove the CAVE CLI from system
  read -r -p "Are you sure you want to uninstall CAVE CLI? [y/N] " input
  case ${input} in
  [yY][eE][sS] | [yY])
    printf "Removing installation...\n" | pipe_log "INFO"
    rm -rf "${CAVE_PATH}"
    if [ ! "$(rm "${BIN_DIR}/cave")" ]; then
      printf "Super User privileges required to terminate link! Using 'sudo'.\n" | pipe_log "WARN"
      sudo rm "${BIN_DIR}/cave"
    fi
    printf "Done.\n" | pipe_log "INFO"
    ;;
  *)
    printf "Uninstall canceled\n" | pipe_log "ERROR"
    ;;
  esac
}

sync_cave() { # Sync files from another repo to the selected cave app
  local app_dir
  app_dir=$(find_app_dir)
  cd "$app_dir" || exit 1
  if [[ "$(has_flag -y "$@")" != "true" ]]; then
    confirm_action "This will reset your docker containers and database. It will also potentially update your local files"
  fi
  printf_header "Sync:"

  local path CLONE_URL CLONE_BRANCH
  path=$(mktemp -d)
  CLONE_URL="$(get_flag "none" "--url" "$@")"
  CLONE_BRANCH="$(get_flag "none" "--branch" "$@")"

  printf "Syncing files with the following parameters:\n\n" | pipe_log "INFO"
  printf "App Location: $app_dir\n" | pipe_log "INFO"
  printf "Using Repo: $CLONE_URL\n" | pipe_log "INFO"
  printf "Using Branch: $CLONE_BRANCH\n\n" | pipe_log "INFO"
  printf "Downloading repo to sync..." | pipe_log "INFO"

  if [[ "${CLONE_BRANCH}" != 'none' ]]; then
    git clone -b "${CLONE_BRANCH}" --single-branch "${CLONE_URL}" "$path" 2>&1 | pipe_log "DEBUG"
  else
    git clone --single-branch "${CLONE_URL}" "$path" 2>&1 | pipe_log "DEBUG"
  fi
  if [[ "$(is_dir_empty "$path")" = 'true' ]]; then
    printf "Failed!\nEnsure you have access rights to the repository: %s\nEnsure you specified a valid branch: %s.\n" "$CLONE_URL" "$CLONE_BRANCH" | pipe_log "ERROR"
    rm -rf "${path}"
    exit 1
  fi
  printf "Done" | pipe_log "INFO"

  printf "Syncing files..." | pipe_log "INFO"
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
  eval "$RSYNC_COMMAND" 2>&1 | pipe_log "DEBUG"
  printf "Done\n" | pipe_log "INFO"

  post_sync="$(get_flag "" "--post-sync" "$@")"
  if [ -n "$path" ]; then
    $post_sync "$path"
  fi

  # clean up temp files
  rm -rf "${path}"

  # Setup docker and db again
  reset -y

  printf "Sync complete.\n" | pipe_log "INFO"
}

get_running_apps() {
  echo "$(docker ps -a --format "{{.Names}}" | grep -E ".*_django" | sed 's/_django//g' 2>&1)"
}

get_running_apps_and_ip_ports() {
  app_names=$(get_running_apps)
  # For each app in app_names, print the app name and the ip and port it is running on
  output=""
  for app_name in $app_names; do
    # If a NGINX Container is running, print the ip and port it is running on
    if docker ps -a --format "{{.Names}}" | grep -qE "${app_name}_nginx_host"; then
      # IP and Port are stored as environment variables as CAVE_PORT and CAVE_IP
      ip_port="$(docker inspect -f '{{.Config.Env}}' ${app_name}_nginx_host | grep -oE "CAVE_IP=[0-9.]*" | cut -d= -f2):$(docker inspect -f '{{.Config.Env}}' ${app_name}_nginx_host | grep -oE "CAVE_PORT=[0-9]*" | cut -d= -f2)"
      output="${output}${app_name} (https://${ip_port})\n"
    else
      # If no NGINX Container is running, print the port the Django Container is running on
      ip_port="$(docker inspect -f '{{(index (index .NetworkSettings.Ports "8000/tcp") 0).HostPort}}' ${app_name}_django)"
      output="${output}${app_name} (http://localhost:${ip_port})\n"
    fi
  done
  echo -e "$output"

}

list_versions() {
  # Get the provided pattern
  lv_pattern="$(get_flag "*" "--pattern" "$@")"
  # If lv pattern starts with a v, remove it
  lv_pattern="${lv_pattern#v}"
  # Get the repo
  lv_repo="$(get_flag "cave_app" "--repo" "$@")"
  if [ "$lv_repo" != "cave_app" ] && [ "$lv_repo" != "cave_static" ] && [ "$lv_repo" != "cave_cli" ] && [ "$lv_repo" != "cave_utils" ]; then
    printf "Error: Invalid repo provided. Must be one of 'cave_app', 'cave_static', 'cave_cli' or 'cave_utils'." | pipe_log "ERROR"
    exit 1
  fi
  GIT_URL="https://github.com/MIT-CAVE/${lv_repo}.git"

  stable_latest_version_branches="$( \
    git ls-remote --heads "$GIT_URL" | \
    grep -E "refs/heads/V[0-9]+$" | \
    grep -E "refs/heads/V${lv_pattern}" | \
    cut -d/ -f3 | \
    cut -d^ -f1 | \
    sort -V -r \
  )"

  stable_versions="$( \
    git ls-remote --tags "$GIT_URL" | \
    grep -E "refs/tags/v[0-9]+\.[0-9]+\.[0-9]+$" | \
    grep -E "refs/tags/v${lv_pattern}" | \
    cut -d/ -f3 | \
    cut -d^ -f1 | \
    sort -V -r \
  )"


  ordered_versions=$(echo -e "${stable_versions}\n${stable_latest_version_branches}" | sort -V)
  
  printf "CAVE Versions (repo: ${lv_repo}):\n"
  for version in $stable_versions; do
    major_version="$(echo "$version" | cut -d. -f1)"
    if [[ "$major_version" != "$last_major_version" ]]; then
      # Print the major version with out the v before
      major_version_no_v="${major_version#v}"
      printf "\n$CHAR_LINE\n"
      printf "Version ${major_version_no_v}:\n"
      printf "$CHAR_LINE\n"
      # If there is a branch for the major version, print it
      branch="V${major_version_no_v}"
      if echo "$stable_latest_version_branches" | grep -q "$branch"; then
        printf "  ${branch} (latest version of ${major_version})\n"
      fi
      last_major_version="$major_version"
    fi
    printf "  ${version}\n"
  done
}


list_cave() {
  if [ "$(has_flag -all "$@")" = "true" ]; then
    printf_header "CAVE App Containers (All):"
    docker ps -a --format "{{.Names}}" | grep -E ".*_django" 2>&1 | pipe_log "INFO"
    docker ps -a --format "{{.Names}}" | grep -E ".*_db_host" 2>&1 | pipe_log "INFO"
    docker ps -a --format "{{.Names}}" | grep -E ".*_redis_host" 2>&1 | pipe_log "INFO"
    docker ps -a --format "{{.Names}}" | grep -E ".*_nginx_host" 2>&1 | pipe_log "INFO"
  else
    printf_header "CAVE Apps (Running):"
    get_running_apps_and_ip_ports | pipe_log "INFO"
  fi
}

remove_docker_pg_volume() {
  printf "Removing Docker DB Volume for App (${app_name})..." 2>&1 | pipe_log "INFO"
  docker volume rm "${app_name}_pg_volume" 2>&1 | pipe_log "DEBUG"
}

kill_cave() {
  if [ "$(has_flag -all "$@")" = "true" ]; then
    for app_name in $(get_running_apps) ; do
      remove_docker_containers
      printf "Killed: ${app_name}\n" | pipe_log "INFO"
    done
  else
    get_app
    remove_docker_containers
    printf "Killed: ${app_name}\n" | pipe_log "INFO"
  fi
}

remove_licence_info() {
  # cd into the app
  cd "$1" || exit 1

  # Remove License and references
  rm LICENSE
  case "$(uname -s)" in
    Linux*)
      sed -i '/^## License Notice$/,$d' README.md
      sed -i '/^Licensed under.*/,$d' NOTICE.md
      if [ -f "cave_api/setup.py" ]; then
        sed -i '/^\s*license="MIT",$/d;/^\s*"License.*MIT License",$/d' cave_api/setup.py
      fi
    ;;
    Darwin*)
      sed -i '' '/^## License Notice$/,$d' README.md
      sed -i '' '/^Licensed under.*/,$d' NOTICE.md
      if [ -f "cave_api/setup.py" ]; then
        sed -i '' '/^\s*license="MIT",$/d;/^\s*"License.*MIT License",$/d' cave_api/setup.py
      fi
    ;;
    *)
      printf "Error: OS not recognized." | pipe_log "ERROR"; exit 1
    ;;
  esac
}

remove_docker_containers() {
  printf "Persisting Redis Data prior to Redis Container Termination..." 2>&1 | pipe_log "DEBUG"
  docker exec "${app_name}_redis_host" redis-cli save 2>&1 | pipe_log "DEBUG"
  printf "Killing Running App (${app_name})..." 2>&1 | pipe_log "DEBUG"
  docker rm --force "${app_name}_django" "${app_name}_nginx_host" "${app_name}_db_host" "${app_name}_redis_host" 2>&1 | pipe_log "DEBUG"
  docker network rm cave-net:${app_name} 2>&1 | pipe_log "DEBUG"
}

remove_docker_images() {
  printf "Removing Docker Images for App (${app_name})..." 2>&1 | pipe_log "INFO"
  docker rmi "cave-app:$app_name" | pipe_log "DEBUG"
}

reset() {
  if [[ "$(has_flag -y "$@")" != "true" ]]; then
    confirm_action "This will remove the Docker containers (deleted and recreated from scratch) for this app. All data in your database will be lost."
  fi
  remove_docker_containers
  remove_docker_pg_volume
  run_cave --entrypoint "./utils/reset_db.sh" "$@"
  printf "DB reset complete.\n" | pipe_log "INFO"
}

prettify_cave() { # Run api_prettify.sh and optionally prettify.sh
  printf "Prettifying cave_api...\n" | pipe_log "INFO"
  run_cave --entrypoint ./utils/prettify.sh "$@"
}

test_cave() { # Run given file found in /cave_api/tests/
  printf "Testing cave_api...\n" | pipe_log "INFO"
  run_cave --entrypoint ./utils/run_test.sh "$@"
}

purge_cave() { # Removes cave app in specified dir and db/db user
  local app_name=$1
  cd "${app_name}" || (printf "No directory %s\n" "$app_name" | pipe_log "ERROR" ; exit 1)
  if ! valid_app_dir; then
    printf "Ensure you specified a valid CAVE app directory\n" | pipe_log "ERROR"
    exit 1
  fi
  cd ../
  printf_header "Purging CAVE App ($app_name):"
  if [[ "$(has_flag -y "$@")" != "true" ]]; then
    confirm_action "This will permanently remove all data associated with your CAVE App (${app_name})"
  fi
  cd "$app_name" || exit 1

  remove_docker_containers
  remove_docker_pg_volume
  remove_docker_images

  cd ../
  source "${app_name}/.env"
  printf "Removing files..." | pipe_log "INFO"
  if sudo rm -rf "${app_name}" 2>&1 | pipe_log "WARN" ; then
    printf "Done\n" | pipe_log "INFO"
    printf "Purge complete.\n" | pipe_log "INFO"
  else
   printf "Couldn't remove files\n" | pipe_log "ERROR"
   exit 1
  fi
}

update_cave() { # Updates the cave cli
  printf "Updating CAVE CLI..." | pipe_log "INFO"
  # Change into the cave cli directory
  cd "${CAVE_PATH}" || exit 1
  git fetch 2>&1 | pipe_log "DEBUG"
  git checkout "$(get_flag "main" "--version" "$@")" 2>&1 | pipe_log "DEBUG"
  git pull 2>&1 | pipe_log "DEBUG"
  printf "Done.\n" | pipe_log "INFO"
  printf "CAVE CLI updated.\n" | pipe_log "INFO"
}

bailout_if_legacy() {
  # Bailout to legacy if -legacy or -l passed
  if [[ "$(has_flag -legacy "$@")" == "true" ]]; then
    "$CAVE_PATH/cave-1.4.0.sh" $(remove_flag "-legacy" "$@")
    exit 1
  fi
  if [[ "$(has_flag -l "$@")" == "true" ]]; then
    "$CAVE_PATH/cave-1.4.0.sh" $(remove_flag "-l" "$@")
    exit 1
  fi
}

main() {
  source "$CAVE_PATH/utils.sh"

  bailout_if_legacy "$@"

  # If no command is passed default to the help command
  if [[ $# -lt 1 ]]; then
    local MAIN_COMMAND="help"
  else
    local MAIN_COMMAND=$1
    shift
  fi
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
      check_docker
      create_cave "$@"
    ;;
    purge)
      # Requires being in parent of app_dir
      check_docker
      purge_cave "$@"
    ;;
    run | start)
      # Requires being inside app_dir
      check_docker
      get_app
      # Starts all required containers for the app
      run_cave "$@"
    ;;
    list)
      check_docker
      list_cave "$@"
    ;;
    kill)
      # Requires being inside app_dir or app_dir specified
      check_docker
      # Kills all containers for the app
      kill_cave "$@"
    ;;
    reset | reset-db)
      # Requires being inside app_dir
      check_docker
      get_app
      # Runs kill, then
      # Removes the volume for the db and app and recreates them
      reset "$@"
    ;;
    upgrade)
      # Requires being inside app_dir
      check_docker
      get_app
      upgrade_cave "$@"
    ;;
    sync)
      # Requires being inside app_dir
      check_docker
      get_app
      sync_cave "$@"
    ;;
    prettify)
      # Requires being inside app_dir
      check_docker
      get_app
      prettify_cave "$@"
    ;;
    list-versions | lv)
      list_versions "$@"
    ;;
    test)
      # Requires being inside app_dir
      check_docker
      get_app
      test_cave "$@"
    ;;
    *)
      printf "Unrecognized Command (%s) passed.\nUse cave --help for information on how to use the cave cli.\n" "$MAIN_COMMAND" | pipe_log "ERROR"
    ;;
  esac
}

main "$@"
