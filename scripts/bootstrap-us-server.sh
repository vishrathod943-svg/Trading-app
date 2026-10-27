#!/usr/bin/env bash
# Run on a NEW Ubuntu 24.04 x86_64 server after confirming hosting credit eligibility.
set -euo pipefail
if [[ $# -ne 1 ]]; then
    echo "Usage: bash scripts/bootstrap-us-server.sh YOUR_NEW_HOSTNAME" >&2
    exit 2
fi
cd "$(dirname "$0")/.."
if [[ $(uname -m) != x86_64 ]]; then echo 'Use an x86_64 server for the documented IB Gateway workflow.' >&2; exit 1; fi
. /etc/os-release
if [[ ${ID:-} != ubuntu || ${VERSION_ID:-} != 24.04 ]]; then echo 'This helper supports Ubuntu 24.04 only.' >&2; exit 1; fi
# Configuration validation happens before installing packages or starting any service.
python3 scripts/configure-us.py --domain "$1"
sudo apt-get update
sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y git docker.io docker-compose-v2 python3-venv
sudo systemctl enable --now docker
sudo docker compose --env-file "$HOME/compass-private/us.env" -f deploy/compose.us.yaml config --quiet
sudo docker compose --env-file "$HOME/compass-private/us.env" -f deploy/compose.us.yaml up -d --build
sudo docker compose --env-file "$HOME/compass-private/us.env" -f deploy/compose.us.yaml ps
echo 'Synthetic demo services started. This does not install/log into IB Gateway or verify broker data.'
echo "After HTTPS is ready, open https://$1/app on your iPhone. Use your private backend token."
echo 'Keep IBKR ports 4001/4002/7496/7497 and backend port 8000 closed to the public Internet.'
