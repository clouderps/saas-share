#!/bin/sh
# Run the ePOS-Print smoke against any tenant container.
#
# Usage:
#   ./run_epos_smoke.sh <container_name> <database>
#
# Example (fayia):
#   ./run_epos_smoke.sh fayia_7m2mg92 fayia_74756778
#
# Assumes the container ships our ab_printer_driver bundle, the conf
# is at /opt/ghaima/odoo.conf, and the venv is at /venv3.12/. Adjust
# the four PATH_* variables if your container layout differs.
set -eu

if [ "${1:-}" = "" ] || [ "${2:-}" = "" ]; then
    echo "usage: $0 <container_name> <database>" >&2
    exit 2
fi

CONTAINER="$1"
DATABASE="$2"
SMOKE_DIR="$(cd "$(dirname "$0")" && pwd)"

PATH_PY=/venv3.12/bin/python3.12
PATH_ODOO_BIN=/opt/ghaima/odoo_source_code/odoo/odoo-bin
PATH_ODOO_CONF=/opt/ghaima/odoo.conf
PATH_WORK=/tmp/ab_printer_smoke

echo "==> copy scripts into $CONTAINER:$PATH_WORK"
docker exec "$CONTAINER" mkdir -p "$PATH_WORK"
docker cp "$SMOKE_DIR/mock_epos_server.py" "$CONTAINER:$PATH_WORK/mock_epos_server.py"
docker cp "$SMOKE_DIR/epos_smoke.py"       "$CONTAINER:$PATH_WORK/epos_smoke.py"

echo "==> stop any leftover mock printer"
docker exec "$CONTAINER" sh -c "pkill -f mock_epos_server.py 2>/dev/null || true"

echo "==> start mock printer in background"
docker exec -d "$CONTAINER" "$PATH_PY" "$PATH_WORK/mock_epos_server.py"
sleep 1

echo "==> health-probe mock"
docker exec "$CONTAINER" sh -c "curl -s --max-time 2 http://127.0.0.1:18043/ ; echo"

echo "==> run smoke script through odoo-bin shell (this can take 20-40s)"
docker exec "$CONTAINER" sh -c "
  $PATH_PY $PATH_ODOO_BIN shell -c $PATH_ODOO_CONF -d $DATABASE --no-http \
    < $PATH_WORK/epos_smoke.py > $PATH_WORK/smoke.out 2>&1
  echo EXIT=\$?
"

echo "==> smoke output"
docker exec "$CONTAINER" cat "$PATH_WORK/smoke.out"

echo "==> mock printer log"
docker exec "$CONTAINER" cat /tmp/mock_epos.log 2>/dev/null || true

echo "==> stop mock printer"
docker exec "$CONTAINER" sh -c "pkill -f mock_epos_server.py 2>/dev/null || true"

echo "==> done"
