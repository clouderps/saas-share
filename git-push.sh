#!/bin/bash
# Push all CloudERPs GitHub repos from custom-addons/
# Usage: sudo -u clouderps bash /home/clouderps/custom-addons/git-push.sh
# Usage: sudo -u clouderps bash /home/clouderps/custom-addons/git-push.sh "commit message"

set -e

BASE_DIR="/home/clouderps/custom-addons"
BRANCH="main"
COMMIT_MSG="${1:-update from server $(date '+%Y-%m-%d %H:%M')}"

REPOS=(
    "saas-erp"
    "saas-accounting"
    "ghaima-api"
    "saas-ai"
    "saas-approval"
    "saas-branches"
    "saas-client"
    "saas-dashboard"
    "saas-enterprise"
    "saas-hr"
    "saas-pos"
    "saas-server"
    "saas-share"
    "saas-theme"
)

echo "=== CloudERPs Git Push ==="
echo "Commit message: $COMMIT_MSG"
echo ""

for REPO in "${REPOS[@]}"; do
    REPO_DIR="$BASE_DIR/$REPO"

    if [ ! -d "$REPO_DIR/.git" ]; then
        echo "[SKIP] $REPO — not a git repo"
        echo ""
        continue
    fi

    cd "$REPO_DIR"

    # Check for changes
    if [ -z "$(git status --porcelain)" ]; then
        echo "[CLEAN] $REPO — nothing to push"
    else
        echo "[PUSH] $REPO"
        git add -A 2>&1 | sed 's/^/  /'
        git commit -m "$COMMIT_MSG" 2>&1 | sed 's/^/  /'
        git push origin "$BRANCH" 2>&1 | sed 's/^/  /'
    fi
    echo ""
done

echo "=== Done ==="
