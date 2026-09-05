#!/bin/bash
# Pull every CloudERPs source repo on this machine and (optionally)
# propagate the same pulls to the Apps server.
#
# Usage:
#   sudo -u clouderps bash /home/clouderps/custom-addons/git-pull.sh         # main only
#   sudo -u clouderps bash /home/clouderps/custom-addons/git-pull.sh --all   # main + Apps
#   sudo -u clouderps bash /home/clouderps/custom-addons/git-pull.sh --apps  # Apps only
#
# Apps-server propagation runs the same git pulls under
# /opt/ghaima_source_code/18.0/ via the bk.server SSH key
# (root@10.0.128.20). Tenant containers bind-mount the source so changes
# go live without a container rebuild — call _reload_odoo_entity_registry
# on each tenant after pulling code that affects the registry.

set -e

BASE_DIR="/home/clouderps/custom-addons"
ODOO_DIR="/home/clouderps/odoo"
GIT_ORG="git@github.com:clouderps"
BRANCH="main"
APPS_HOST="root@10.0.128.20"
APPS_BASE="/opt/ghaima_source_code/18.0"

# Custom-addon repos (live under custom-addons/ on main, under
# /opt/ghaima_source_code/18.0/ on Apps).
REPOS=(
    "saas-erp"
    "saas-accounting"
    "ghaima-api"
    "payment-gateway"
    "saas-ai"
    "saas-approval"
    "saas-branches"
    "saas-client"
    "saas-dashboard"
    # "saas-enterprise"  # repo lives on GitHub, not pulled to this server (Enterprise-only, not in addons_path)
    "saas-hr"
    "saas-mail"
    "saas-pos"
    "saas-server"
    "saas-share"
    "saas-theme"
)

# --- args --------------------------------------------------------------
PULL_MAIN=true
PULL_APPS=false
case "${1:-}" in
    --all)  PULL_APPS=true ;;
    --apps) PULL_MAIN=false; PULL_APPS=true ;;
    "")     ;;
    *)      echo "unknown flag: $1"; exit 2 ;;
esac

# --- main server -------------------------------------------------------
if $PULL_MAIN; then
    echo "=== Main server: pull Odoo source + custom-addons ==="

    # Odoo source — lives outside custom-addons/. Tracks clouderps/odoo-18 main.
    if [ -d "$ODOO_DIR/.git" ]; then
        echo "[PULL] odoo-18"
        git -C "$ODOO_DIR" pull origin "$BRANCH" 2>&1 | sed 's/^/  /'
    elif [ -d "$ODOO_DIR" ]; then
        echo "[SKIP] odoo-18 — $ODOO_DIR exists but is not a git repo"
    else
        echo "[CLONE] odoo-18"
        git clone --depth 1 --branch "$BRANCH" "$GIT_ORG/odoo-18.git" "$ODOO_DIR" 2>&1 | sed 's/^/  /'
    fi
    echo ""

    for REPO in "${REPOS[@]}"; do
        REPO_DIR="$BASE_DIR/$REPO"
        if [ -d "$REPO_DIR/.git" ]; then
            echo "[PULL] $REPO"
            # Clear .pyc / __pycache__ before pull. Tenant containers
            # bind-mount these dirs and regenerate bytecode, which can
            # collide with files still tracked from before .gitignore
            # was added (and aborts the pull).
            find "$REPO_DIR" -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
            find "$REPO_DIR" -type f -name '*.pyc' -delete 2>/dev/null || true
            git -C "$REPO_DIR" pull origin "$BRANCH" 2>&1 | sed 's/^/  /'
        elif [ -d "$REPO_DIR" ]; then
            echo "[SKIP] $REPO — directory exists but not a git repo"
        else
            echo "[CLONE] $REPO"
            git clone "$GIT_ORG/$REPO.git" "$REPO_DIR" 2>&1 | sed 's/^/  /'
        fi
        echo ""
    done
fi

# --- apps server -------------------------------------------------------
if $PULL_APPS; then
    echo "=== Apps server (10.0.128.20): same pulls under $APPS_BASE ==="

    # Build one remote command so we don't open 15 SSH sessions.
    # Helper to keep the remote command short: clean .pyc, then pull.
    REMOTE_CLEAN='find . -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true; find . -type f -name "*.pyc" -delete 2>/dev/null || true'

    REMOTE_CMD="set -e; mkdir -p $APPS_BASE; cd $APPS_BASE; "
    REMOTE_CMD+="echo '[PULL] odoo-18'; "
    REMOTE_CMD+="if [ -d odoo/.git ]; then (cd odoo && $REMOTE_CLEAN); git -C odoo pull origin $BRANCH 2>&1 | sed 's/^/  /'; "
    REMOTE_CMD+="else git clone --depth 1 --branch $BRANCH $GIT_ORG/odoo-18.git odoo 2>&1 | sed 's/^/  /'; fi; echo; "
    for REPO in "${REPOS[@]}"; do
        REMOTE_CMD+="echo '[PULL] $REPO'; "
        REMOTE_CMD+="if [ -d $REPO/.git ]; then (cd $REPO && $REMOTE_CLEAN); git -C $REPO pull origin $BRANCH 2>&1 | sed 's/^/  /'; "
        REMOTE_CMD+="elif [ -d $REPO ]; then echo '  [SKIP] not a git repo'; "
        REMOTE_CMD+="else git clone $GIT_ORG/$REPO.git $REPO 2>&1 | sed 's/^/  /'; fi; echo; "
    done
    ssh -o StrictHostKeyChecking=no "$APPS_HOST" "$REMOTE_CMD"

    # Bind mounts are tied to the host inode at container start. A regular
    # `git pull` updates files in place (inode preserved) — fine. But a
    # full re-clone (rm -rf + git clone) creates a new inode and orphans
    # the mount: container sees an empty dir → asset bundles serve as 0
    # bytes → broken CSS. Detect and auto-restart any affected container.
    echo ""
    echo "=== Apps: check for stale bind mounts ==="
    STALE_CHECK='for c in $(docker ps --format "{{.Names}}"); do
        for src in $(docker inspect "$c" --format "{{range .Mounts}}{{if eq .Type \"bind\"}}{{.Source}}|{{.Destination}}{{println}}{{end}}{{end}}"); do
            host="${src%|*}"; cont="${src#*|}"
            [ -z "$host" ] && continue
            host_count=$(find "$host" -maxdepth 1 2>/dev/null | wc -l)
            cont_count=$(docker exec "$c" find "$cont" -maxdepth 1 2>/dev/null | wc -l)
            if [ "$host_count" -gt 5 ] && [ "$cont_count" -le 1 ]; then
                echo "  STALE: $c  $cont (host=$host_count container=$cont_count)"
                echo "$c" >> /tmp/stale_containers
            fi
        done
    done
    if [ -s /tmp/stale_containers ]; then
        for c in $(sort -u /tmp/stale_containers); do
            echo "  [RESTART] $c"
            docker restart "$c" >/dev/null
        done
        rm -f /tmp/stale_containers
    else
        echo "  OK — all bind mounts live"
    fi'
    ssh -o StrictHostKeyChecking=no "$APPS_HOST" "rm -f /tmp/stale_containers; $STALE_CHECK"

    # Refresh DBCLOUD `current_commit_str` for every addon path so the UI
    # shows actual HEAD (otherwise "Current Commit" goes stale silently).
    echo ""
    echo "=== Refresh DBCLOUD addon-path commit metadata ==="
    # Already clouderps (the documented way to run this script)? Don't nest
    # sudo — clouderps is not a sudoer and the step would fail.
    AS_CLOUDERPS=""
    [ "$(id -un)" != "clouderps" ] && AS_CLOUDERPS="sudo -u clouderps"
    $AS_CLOUDERPS /home/clouderps/venv/bin/python3 - << 'PYEOF'
import sys; sys.path.insert(0, '/home/clouderps/odoo')
import odoo
odoo.tools.config.parse_config(['-c', '/home/clouderps/clouderps-odoo.conf', '-d', 'DBCLOUD'])
odoo.service.server.load_server_wide_modules()
reg = odoo.registry('DBCLOUD')
with reg.cursor() as cr:
    env = odoo.api.Environment(cr, 2, {})
    apps = env['bk.server'].search([('name','=','Apps')], limit=1)
    if not apps:
        print("Apps server record not found — skip refresh")
        sys.exit(0)
    refreshed = 0
    for tbl in ('odoo_image_addon_path', 'odoo_container_addon_path'):
        cr.execute(f"SELECT id, name, path FROM {tbl}")
        for rid, name, path in cr.fetchall():
            if not path:
                continue
            try:
                out = apps._execute_command(
                    f"cd {path} 2>/dev/null && "
                    f"echo R=$(git remote get-url origin 2>/dev/null) && "
                    f"echo B=$(git rev-parse --abbrev-ref HEAD 2>/dev/null) && "
                    f"echo C=$(git log --oneline -1 2>/dev/null) || true"
                )
                r = b = c = ''
                for line in out.split('\n'):
                    if line.startswith('R='): r = line[2:].strip().replace('git@github.com:', 'https://github.com/')
                    elif line.startswith('B='): b = line[2:].strip()
                    elif line.startswith('C='): c = line[2:].strip()
                if c:
                    cr.execute(f"UPDATE {tbl} SET git_remote_link=%s, git_branch_name=%s, current_commit_str=%s WHERE id=%s",
                               (r, b, c, rid))
                    refreshed += 1
            except Exception:
                pass
        cr.commit()
    print(f"Refreshed {refreshed} addon-path commit-str rows")
PYEOF
fi

echo "=== Done ==="
