#!/usr/bin/env bash
# Deploy GridLens to Databricks Apps.
#
# `databricks sync` honors BOTH .gitignore and .databricksignore, and our
# .gitignore excludes app/frontend/dist/ and data/synthetic/*.csv (build /
# generated artefacts shouldn't be checked in). The FastAPI backend serves
# the built UI from app/frontend/dist/, so if we don't push it explicitly
# the app starts with no frontend and returns the dev-only JSON banner
# ("Frontend dist/ not built; run npm run build or use Vite dev server").
#
# This script therefore:
#   1. builds the frontend
#   2. syncs source via `databricks sync` (.databricks/.gitignore aware)
#   3. force-uploads app/frontend/dist/** and data/synthetic/*.csv via
#      `databricks workspace import` (bypasses gitignore)
#   4. kicks off `databricks apps deploy`
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
  echo "==> [1/5] Building frontend..."
  (cd app/frontend && npm run build)
fi

if [ ! -f app/frontend/dist/index.html ]; then
  echo "ERROR: app/frontend/dist/index.html missing — run 'npm run build' or drop --skip-build." >&2
  exit 1
fi

echo "==> [2/5] Syncing source (honours .gitignore + .databricksignore)..."
DATABRICKS_CONFIG_PROFILE="$PROFILE" databricks sync . "$WORKSPACE_PATH" --full \
  | tail -6

echo "==> [3/5] Force-uploading built frontend (dist/ is gitignored so sync skips it)..."
# `databricks workspace import-dir` recursively uploads and creates the
# parent directory tree (which plain `import` does not). Targets the
# directory layout the backend expects:
#   app/frontend/dist/index.html
#   app/frontend/dist/favicon.svg
#   app/frontend/dist/assets/*.{js,css,...}
DATABRICKS_CONFIG_PROFILE="$PROFILE" databricks workspace import-dir \
  app/frontend/dist "$WORKSPACE_PATH/app/frontend/dist" --overwrite \
  | tail -20

echo "==> [4/5] Uploading synthetic CSVs (databricks sync skips gitignored data files)..."
for f in data/synthetic/*.csv; do
  fname="$(basename "$f")"
  printf '    %s ... ' "$fname"
  DATABRICKS_CONFIG_PROFILE="$PROFILE" databricks workspace import \
    "$WORKSPACE_PATH/$f" --file "$f" --format AUTO --overwrite >/dev/null 2>&1
  printf 'ok\n'
done

echo "==> [5/5] Deploying app..."
DATABRICKS_CONFIG_PROFILE="$PROFILE" databricks apps deploy "$APP_NAME" \
  --source-code-path "$WORKSPACE_PATH" \
  | tail -10

echo
echo "Done. Tail logs with:"
echo "  DATABRICKS_CONFIG_PROFILE=$PROFILE databricks apps logs $APP_NAME --tail-lines 80"
