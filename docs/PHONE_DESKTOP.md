# Phone access to the hosted IBKR desktop

This optional proxy lets a personal phone reach an existing server desktop over HTTPS. It does not install IB Gateway, log in to IBKR or eliminate broker security checks. No software/key download is required on the company laptop; use the already-open Lightsail browser SSH terminal only as permitted by company policy.

Prerequisites: the US dashboard already works over HTTPS at a hostname verified against the new server IP. XFCE, TigerVNC, noVNC, websockify and dbus-x11 are installed on Ubuntu 24.04. A VNC password exists, and the desktop on 5901 and noVNC on 6080 listen only on 127.0.0.1/::1. Keep all VNC/noVNC/IBKR API ports closed in Lightsail. Existing manual desktop processes may need restarting after a server reboot.

In the server SSH terminal, as the regular Ubuntu user:

```bash
cd ~/Trading-app
git pull --ff-only
bash scripts/enable-phone-desktop.sh
```

The helper first rejects missing or non-loopback desktop listeners. It prompts twice for a separate 14–64-character ASCII website password (hidden input). Use a unique password, not a broker password or backend token. A bcrypt hash is saved privately in `~/compass-private/desktop.env` with mode 600; plaintext is never saved. Python 3.12/libcrypt on Ubuntu 24.04 is required. The helper validates the combined Compose/Caddy configuration and recreates only the HTTPS proxy, keeping the dashboard/backend intact.

On the personal phone, open (substitute the verified hostname):

```
https://YOUR_HOSTNAME/desktop/vnc.html?path=desktop/websockify&resize=scale
```

First sign in to the website as `operator` with the new website password. Then click Connect and use the previously created VNC desktop password. Basic authentication protects all `/desktop/*` HTTP and WebSocket paths. TLS protects both credentials in transit. IBKR login is entered only into the official Gateway application inside the desktop, not the website login or this chat. This is password-protected public HTTPS access, not a VPN; close the desktop route when finished.

To close browser desktop access while retaining the app:

```bash
sudo docker compose --env-file "$HOME/compass-private/us.env" -f deploy/compose.us.yaml up -d --no-deps https
```

While desktop access is needed, subsequent Compose operations must include both private env files and both compose files, in the same order used by the helper. Using only the base configuration removes the desktop proxy. Do not commit either private env file or share screenshots containing credentials. Before entering credentials, confirm valid HTTPS on your intended hostname. The Gateway installation and read-only API login are separate next steps; phone touch/keyboard behavior and an actual IBKR login have not been verified here.
