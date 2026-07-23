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
    # `gh run download` uses a non-zero exit when a run has not uploaded an
    # artifact. That state is terminal for this run, not a transient API
    # failure. Retrying it for the full exponential schedule can consume more
    # than five minutes per run and starve compaction/monitor jobs that scan
    # several expected no-artifact executions.
    case "$output" in
      *"no valid artifacts found to download"* | *"no artifacts found to download"*)
        printf 'gh error is not retryable; skipping this run\n' >&2
        return "$status"
        ;;
    esac
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
