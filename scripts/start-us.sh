#!/usr/bin/env bash
# Short mobile-safe entry point; never changes broker mode or private credentials.
set -euo pipefail
cd "$(dirname "$0")/.."
args=(--env-file "$HOME/compass-private/us.env")
if [[ ${1:-} == --desktop ]]; then
    if [[ $# -ne 1 ]]; then echo 'Usage: bash scripts/start-us.sh [--desktop]' >&2; exit 2; fi
    args+=(--env-file "$HOME/compass-private/desktop.env" -f deploy/compose.us.yaml -f deploy/compose.desktop.yaml)
elif [[ $# -eq 0 ]]; then
    # Require an explicit choice to avoid accidentally removing phone access.
    if [[ -f "$HOME/compass-private/desktop.env" ]]; then
        echo 'Phone desktop settings found. Use: bash scripts/start-us.sh --desktop' >&2; exit 2
    fi
    args+=(-f deploy/compose.us.yaml)
else
    echo 'Usage: bash scripts/start-us.sh [--desktop]' >&2; exit 2
fi
sudo docker compose "${args[@]}" config --quiet
sudo docker compose "${args[@]}" up -d --build
sudo docker compose "${args[@]}" ps
