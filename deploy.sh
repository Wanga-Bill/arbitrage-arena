#!/usr/bin/env bash
# deploy.sh - Script to configure Coolify application FQDN and trigger restart

# Load .env file from the current directory
if [ -f .env ]; then
  export $(grep -v '^#' .env | xargs)
fi

DRY_RUN=false
if [[ "$1" == "--dry-run" ]]; then
  DRY_RUN=true
fi

# Configuration check
errors=()
if [ -z "$VPS_IP" ] || [[ "$VPS_IP" == *"your_"* ]] || [[ "$VPS_IP" == *"placeholder"* ]]; then
  errors+=("VPS_IP is missing or set to a placeholder.")
fi

if [ -z "$APP_UUID" ] || [[ "$APP_UUID" == *"your_"* ]] || [[ "$APP_UUID" == *"placeholder"* ]]; then
  errors+=("APP_UUID is missing or set to a placeholder.")
fi

if [ -z "$COOLIFY_API_TOKEN" ] || [[ "$COOLIFY_API_TOKEN" == *"your_"* ]] || [[ "$COOLIFY_API_TOKEN" == *"placeholder"* ]]; then
  errors+=("COOLIFY_API_TOKEN is missing or set to a placeholder.")
fi

DOMAIN_URL=${DOMAIN_URL:-"https://arbitragearena.io"}

if [ ${#errors[@]} -ne 0 ]; then
  echo "Error: Configuration validation failed:"
  for err in "${errors[@]}"; do
    echo "  - $err"
  done
  exit 1
fi

COOLIFY_URL="http://${VPS_IP}:8000"
CLI_PATH="C:/Users/HP/AppData/Local/Coolify/coolify.exe"

# If running on Linux/macOS, check if coolify is in PATH
if [ ! -f "$CLI_PATH" ]; then
  CLI_PATH="coolify"
fi

if [ "$DRY_RUN" = true ]; then
  echo "=== COOLIFY DEPLOYMENT DRY RUN ==="
  echo "URL: $COOLIFY_URL"
  echo "APP UUID: $APP_UUID"
  echo "DOMAIN URL: $DOMAIN_URL"
  echo ""
  echo "[Dry Run] Would configure Coolify context 'my-server' using URL: $COOLIFY_URL"
  echo "[Dry Run] Would verify context connection."
  echo "[Dry Run] Would run: coolify app env create $APP_UUID --key COOLIFY_FQDN --value \"$DOMAIN_URL\""
  echo "[Dry Run] Would run: coolify app update $APP_UUID --domains \"$DOMAIN_URL\""
  echo "[Dry Run] Would run: coolify app restart $APP_UUID"
  echo "=================================="
  exit 0
fi

echo "=== COOLIFY DEPLOYMENT ==="
echo "Configuring context..."
"$CLI_PATH" context add my-server "$COOLIFY_URL" "$COOLIFY_API_TOKEN" --default --force

echo "Verifying context..."
"$CLI_PATH" context verify

echo "Setting COOLIFY_FQDN environment variable..."
"$CLI_PATH" app env create "$APP_UUID" --key COOLIFY_FQDN --value "$DOMAIN_URL"

echo "Updating application domains configuration..."
"$CLI_PATH" app update "$APP_UUID" --domains "$DOMAIN_URL"

echo "Restarting application to apply changes..."
"$CLI_PATH" app restart "$APP_UUID"
echo "Deployment triggered successfully!"
