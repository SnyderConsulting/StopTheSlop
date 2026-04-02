#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

for ENV_FILE in "${ROOT_DIR}/.env" "${ROOT_DIR}/../.env"; do
  if [[ -f "${ENV_FILE}" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "${ENV_FILE}"
    set +a
  fi
done

RESOURCE_GROUP="${RESOURCE_GROUP:-StopTheSlop}"
ENVIRONMENT_NAME="${ENVIRONMENT_NAME:-stoptheslop-env}"
LOCATION="${LOCATION:-centralus}"
APP_NAME="${MCP_APP_NAME:-stoptheslop-mcp}"
MIN_REPLICAS="${MCP_MIN_REPLICAS:-1}"
STATIC_ORIGIN="${STATIC_ORIGIN:-https://stoptheslopweb26032543.z19.web.core.windows.net}"
MCP_ALLOWED_ORIGINS="${MCP_ALLOWED_ORIGINS:-*,${STATIC_ORIGIN},https://stoptheslop.tech,https://www.stoptheslop.tech,http://127.0.0.1:8080,http://localhost:8080}"
SITE_URL="${SITE_URL:-${STATIC_ORIGIN}}"
API_APP_NAME="${API_APP_NAME:-stoptheslop-api}"

API_FQDN="$(az containerapp show --name "${API_APP_NAME}" --resource-group "${RESOURCE_GROUP}" --query 'properties.configuration.ingress.fqdn' --output tsv)"
SITE_API_BASE_URL="${STS_API_BASE_URL:-https://${API_FQDN}}"

deploy_container_app() {
  az containerapp up \
    --name "${APP_NAME}" \
    --resource-group "${RESOURCE_GROUP}" \
    --environment "${ENVIRONMENT_NAME}" \
    --location "${LOCATION}" \
    --source "${ROOT_DIR}/mcp_server" \
    --ingress external \
    --target-port 8000 \
    --env-vars STS_API_BASE_URL="${SITE_API_BASE_URL}" STS_SITE_URL="${SITE_URL}" STS_MCP_ALLOWED_ORIGINS="${MCP_ALLOWED_ORIGINS}"
}

echo "Deploying MCP container app ${APP_NAME}..."
deploy_container_app

az containerapp update \
  --name "${APP_NAME}" \
  --resource-group "${RESOURCE_GROUP}" \
  --min-replicas "${MIN_REPLICAS}" >/dev/null

MCP_FQDN="$(az containerapp show --name "${APP_NAME}" --resource-group "${RESOURCE_GROUP}" --query 'properties.configuration.ingress.fqdn' --output tsv)"
MCP_BASE_URL="https://${MCP_FQDN}"

az containerapp update \
  --name "${APP_NAME}" \
  --resource-group "${RESOURCE_GROUP}" \
  --set-env-vars STS_MCP_PUBLIC_BASE_URL="${MCP_BASE_URL}" >/dev/null

echo "MCP deployment complete."
echo "MCP base URL: ${MCP_BASE_URL}"
echo "MCP endpoint: ${MCP_BASE_URL}/mcp"
