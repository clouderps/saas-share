#!/usr/bin/env bash
# Ghaima Printer Bridge Agent — Linux installer.
#
# Run on a PC / mini-PC / Raspberry Pi inside the customer's LAN, with
# sudo. Idempotent — re-running upgrades the agent in place.
#
# Usage:
#   sudo AGENT_URL=https://fayia.ghaima.sa \
#        AGENT_TOKEN=<paste-from-Odoo> \
#        AGENT_NAME="Main Office PC" \
#        bash install_agent.sh
set -euo pipefail

: "${AGENT_URL:?AGENT_URL required (e.g. https://fayia.ghaima.sa)}"
: "${AGENT_TOKEN:?AGENT_TOKEN required (paste from Odoo Agent form)}"
AGENT_NAME="${AGENT_NAME:-$(hostname)}"

INSTALL_DIR="/opt/ghaima-printer-agent"
LOG_DIR="/var/log/ghaima-printer-agent"
SERVICE="/etc/systemd/system/ghaima-printer-agent.service"
USER_NAME="ghaima-agent"

echo "==> Installing Ghaima Printer Agent"
echo "    server : $AGENT_URL"
echo "    name   : $AGENT_NAME"

# 1. Dependencies
if ! command -v python3 >/dev/null 2>&1; then
    echo "Installing python3…"
    if   command -v apt-get >/dev/null;  then apt-get update -y && apt-get install -y python3 python3-pip
    elif command -v dnf     >/dev/null;  then dnf install -y python3 python3-pip
    elif command -v yum     >/dev/null;  then yum install -y python3 python3-pip
    else echo "Unknown package manager — install python3 manually." >&2; exit 1
    fi
fi
python3 -m pip install --quiet --upgrade requests || pip3 install --quiet --upgrade requests

# 2. User
if ! id -u "$USER_NAME" >/dev/null 2>&1; then
    useradd --system --no-create-home --shell /usr/sbin/nologin "$USER_NAME"
fi

# 3. Files
mkdir -p "$INSTALL_DIR" "$LOG_DIR"
chown "$USER_NAME:$USER_NAME" "$LOG_DIR"

SCRIPT_SRC="$(dirname "$(readlink -f "$0")")/ab_printer_agent.py"
if [[ ! -f "$SCRIPT_SRC" ]]; then
    # Allow running the installer without colocating the script — pull from
    # the configured server's public download path.
    echo "ab_printer_agent.py not next to installer — fetching from $AGENT_URL"
    curl -fsSL "$AGENT_URL/ab_printer/agent/download" -o "$INSTALL_DIR/ab_printer_agent.py"
else
    install -m 0755 "$SCRIPT_SRC" "$INSTALL_DIR/ab_printer_agent.py"
fi
chown -R "$USER_NAME:$USER_NAME" "$INSTALL_DIR"

# 4. systemd unit
cat > "$SERVICE" <<UNIT
[Unit]
Description=Ghaima Printer Bridge Agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
Environment=AGENT_URL=$AGENT_URL
Environment=AGENT_TOKEN=$AGENT_TOKEN
Environment=AGENT_NAME=$AGENT_NAME
ExecStart=/usr/bin/python3 $INSTALL_DIR/ab_printer_agent.py
Restart=on-failure
RestartSec=5
User=$USER_NAME
Group=$USER_NAME
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
ReadWritePaths=$LOG_DIR

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable ghaima-printer-agent.service
systemctl restart ghaima-printer-agent.service

echo
echo "==> Done."
echo "    service : ghaima-printer-agent"
echo "    status  : systemctl status ghaima-printer-agent"
echo "    logs    : journalctl -u ghaima-printer-agent -f"
