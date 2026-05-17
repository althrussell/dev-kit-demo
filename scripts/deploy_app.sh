#!/usr/bin/env bash
# Deploy GridLens to Databricks Apps.
#
# `databricks sync` is intended for source code and silently skips data files
# (.csv etc.), so we have to bulk-upload the synthetic CSVs manually via
# `databricks workspace import` before kicking off the deploy.
#
# Usage:
#   ./scripts/deploy_app.sh [--skip-build]
#
# Env:
#   DATABRICKS_CONFIG_PROFILE   defaults to "servco"
#   WORKSPACE_PATH              defaults to "/Workspace/Users/al.thrussell@databricks.com/gridlens-app"
#   APP_NAME                    defaults to "gridlens"

set -euo pipefail

PROFILE="${DATABRICKS_CONFIG_PROFILE:-servco}"
WORKSPACE_PATH="${WORKSPACE_PATH:-/Workspace/Users/al.thrussell@databricks.com/gridlens-app}"
APP_NAME="${APP_NAME:-gridlens}"
SKIP_BUILD=0

for arg in "$@"; do
  case "$arg" in
    --skip-build) SKIP_BUILD=1 ;;
    *) echo "unknown arg: $arg"; exit 2 ;;
  esac
done

cd "$(dirname "$0")/.."

if [ "$SKIP_BUILD" -eq 0 ]; then
  echo "==> [1/4] Building frontend..."
  (cd app/frontend && npm run build)
fi

echo "==> [2/4] Syncing source (.databricksignore controls excludes)..."
DATABRICKS_CONFIG_PROFILE="$PROFILE" databricks sync . "$WORKSPACE_PATH" --full \
  | tail -6

echo "==> [3/4] Uploading synthetic CSVs (databricks sync silently skips data files)..."
for f in data/synthetic/*.csv; do
  fname="$(basename "$f")"
  printf '    %s ... ' "$fname"
  DATABRICKS_CONFIG_PROFILE="$PROFILE" databricks workspace import \
    "$WORKSPACE_PATH/$f" --file "$f" --format AUTO --overwrite >/dev/null 2>&1
  printf 'ok\n'
done

echo "==> [4/4] Deploying app..."
DATABRICKS_CONFIG_PROFILE="$PROFILE" databricks apps deploy "$APP_NAME" \
  --source-code-path "$WORKSPACE_PATH" \
  | tail -10

echo
echo "Done. Tail logs with:"
echo "  DATABRICKS_CONFIG_PROFILE=$PROFILE databricks apps logs $APP_NAME --tail-lines 80"
