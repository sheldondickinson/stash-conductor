#!/usr/bin/env bash
# Build before replacing the running service; record the actual outcome if configured.
set -euo pipefail
repo_dir=$(cd "$(dirname "$0")/.." && pwd)
compose_file="${1:-$repo_dir/compose.yaml}"
if [ "$#" -gt 1 ] || [ ! -f "$compose_file" ]; then
  printf '%s\n' 'Usage: scripts/deploy.sh [compose-file]' >&2
  exit 2
fi
compose_file=$(cd "$(dirname "$compose_file")" && pwd)/$(basename "$compose_file")
compose=(docker compose --project-directory "$(dirname "$compose_file")" -f "$compose_file")
"${compose[@]}" config --quiet
container=$("${compose[@]}" ps -a -q stash | head -n 1)
if [ -n "${DOCS_DEPLOY_HOOK:-}" ]; then
  test -r "$DOCS_DEPLOY_HOOK" || { printf '%s\n' 'Configured documentation hook is unavailable; no deployment started.' >&2; exit 2; }
  test -n "${DOCS_SERVICE_ID:-}" || { printf '%s\n' 'DOCS_SERVICE_ID is required with a documentation hook.' >&2; exit 2; }
  # This is trusted operator configuration, never browser or document input.
  source "$DOCS_DEPLOY_HOOK"
  documentation_capture_on_exit "$DOCS_SERVICE_ID" "${container:-stash-container-unavailable}" "$compose_file"
else
  printf '%s\n' 'Documentation capture is not configured for this deployment.' >&2
fi
"${compose[@]}" build stash
"${compose[@]}" up -d --no-deps stash
container=$("${compose[@]}" ps -q stash)
test -n "$container"
# The shared hook reads this again at EXIT, after the new container exists.
DC_DEPLOY_CONTAINER="$container"
for attempt in $(seq 1 30); do
  status=$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container")
  if [ "$status" = healthy ]; then
    if "${compose[@]}" config --services | grep -qx print-worker; then
      "${compose[@]}" up -d --no-deps print-worker
    fi
    printf '%s\n' 'Stash deployment health check passed.'
    exit 0
  fi
  if [ "$status" = unhealthy ] || [ "$status" = exited ] || [ "$status" = dead ]; then break; fi
  sleep 2
done
printf '%s\n' 'Stash did not reach healthy status. Inspect the deployment before proceeding.' >&2
exit 1
