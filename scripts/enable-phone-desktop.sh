#!/usr/bin/env bash
# Opt-in HTTPS proxy for an existing loopback-only VNC/noVNC desktop.
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ $EUID -eq 0 ]]; then echo 'Run as your normal Ubuntu user, without sudo.' >&2; exit 1; fi
if [[ ! -f "$HOME/compass-private/us.env" ]]; then echo 'Configure the US backend first.' >&2; exit 1; fi
python3 - <<'PY'
import subprocess
found=set()
for line in subprocess.check_output(['ss','-H','-ltn'],text=True).splitlines():
    fields=line.split()
    if len(fields)<4:continue
    address=fields[3]
    host,_,port=address.rpartition(':')
    if port not in ('5901','6080'):continue
    if host not in ('127.0.0.1','[::1]','::1'):
        raise SystemExit('Desktop listener is not loopback-only. Stop it and bind to 127.0.0.1 before proceeding.')
    found.add(port)
if found!={'5901','6080'}:
    raise SystemExit('Start the loopback VNC desktop on 5901 and noVNC proxy on 6080 first.')
PY
python3 scripts/configure-desktop.py
args=(--env-file "$HOME/compass-private/us.env" --env-file "$HOME/compass-private/desktop.env" -f deploy/compose.us.yaml -f deploy/compose.desktop.yaml)
sudo docker compose "${args[@]}" config --quiet
sudo docker compose "${args[@]}" run --rm --no-deps https caddy validate --config /etc/caddy/Caddyfile
sudo docker compose "${args[@]}" up -d --no-deps https
echo 'Phone desktop HTTPS proxy enabled. Website username: operator.'
echo 'Keep 5900/5901/6080 and IBKR API ports closed in Lightsail. No broker login has been performed.'
