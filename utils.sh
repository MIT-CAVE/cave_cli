#!/bin/bash
# Shell utils shared by cave projects

setup_log() {
    if [[ "$(has_flag -v "$@")" == "true" || "$(has_flag -verbose "$@")" == "true" ]]; then
      script_logging_level="DEBUG"
    else
      if [[ "$(has_flag --loglevel "$@")" == "true" ]]; then
        script_logging_level="$(get_flag "INFO" --loglevel "$@")"
      else
        script_logging_level="$(get_flag "INFO" --ll "$@")"
      fi
    fi
    # Levels are DEBUG, INFO, WARN, ERROR
    # Set the levels that will be logged
    case "$script_logging_level" in
      "DEBUG")
        script_logging_levels=("DEBUG" "INFO" "WARN" "ERROR")
        ;;
      "INFO")
        script_logging_levels=("INFO" "WARN" "ERROR")
        ;;
      "WARN")
        script_logging_levels=("WARN" "ERROR")
        ;;
      "ERROR")
        script_logging_levels=("ERROR")
        ;;
      "SILENT")
        script_logging_levels=()
        ;;
      *)
        script_logging_levels=("ERROR")
        printf "Invalid log level $script_logging_level" | pipe_log "ERROR"
        exit 1
        ;;
    esac
}

log() {
    local log_message=$1
    local log_priority=$2
    
    if [[ " ${script_logging_levels[@]} " =~ " ${log_priority} " ]]; then
      printf "$log_priority: $log_message\n" >&2
    fi
}

pipe_log() {
  IFS=''
  while read -r line || [ -n "$line" ]; do
    log "$line" "$1"
  done
}
