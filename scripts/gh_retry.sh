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
      *"API rate limit exceeded for installation"*)
        # Installation limits reset outside these short-lived planning jobs.
        # Exponential retries only consume the job timeout and then prevent the
        # fail-closed no-data plan from being written.
        printf 'GitHub installation rate limit is not retryable in this job\n' >&2
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

# Build a newline-delimited set of workflow-run IDs that currently own at
# least one non-expired repository artifact. Artifact assemblers otherwise
# issue one `gh run download` request for every candidate run, including the
# many plan-first runs that intentionally publish no artifact. One paginated
# repository index is substantially cheaper than hundreds of known-empty
# download probes.
gh_build_artifact_run_index() {
  local output_path=$1
  local since=$2
  local repository=${GITHUB_REPOSITORY:-}
  local unsorted

  : >"$output_path"
  if [ -z "$repository" ]; then
    return 1
  fi

  unsorted="${output_path}.unsorted"
  if ! gh_retry api --paginate \
    "repos/${repository}/actions/artifacts?per_page=100" \
    --jq ".artifacts[] | select(.expired == false and .created_at > \"$since\") | .workflow_run.id" \
    >"$unsorted"; then
    rm -f "$unsorted"
    return 1
  fi
  sort -u "$unsorted" >"$output_path"
  rm -f "$unsorted"
}

gh_run_has_indexed_artifact() {
  local index_path=$1
  local run_id=$2
  grep -Fqx "$run_id" "$index_path"
}
