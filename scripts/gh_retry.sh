#!/bin/bash
# Bounded exponential retry for GitHub API calls made by artifact assemblers.
# shellcheck shell=bash

gh_retry() {
  local attempt=1
  local max_attempts=${GH_RETRY_MAX_ATTEMPTS:-6}
  local delay=${GH_RETRY_INITIAL_SECONDS:-10}
  local max_delay=${GH_RETRY_MAX_SECONDS:-240}
  local output
  local status

  while true; do
    if output=$(gh "$@" 2>&1); then
      printf '%s\n' "$output"
      return 0
    else
      status=$?
    fi
    printf 'gh attempt %d/%d failed: %s\n' "$attempt" "$max_attempts" "$output" >&2
    if [ "$attempt" -ge "$max_attempts" ]; then
      return "$status"
    fi
    sleep "$delay"
    attempt=$((attempt + 1))
    delay=$((delay * 2))
    if [ "$delay" -gt "$max_delay" ]; then
      delay=$max_delay
    fi
  done
}
