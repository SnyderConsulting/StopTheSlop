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
APP_NAME="${APP_NAME:-stoptheslop-api}"
MIN_REPLICAS="${MIN_REPLICAS:-1}"
STORAGE_ACCOUNT="${STORAGE_ACCOUNT:-stoptheslopweb26032543}"
TABLE_NAME="${TABLE_NAME:-StopTheSlopTickets}"
SOURCE_BLOB_CONTAINER="${SOURCE_BLOB_CONTAINER:-source-ingestion}"
ENABLE_SEED_DATA="${ENABLE_SEED_DATA:-false}"
STATIC_ORIGIN="${STATIC_ORIGIN:-https://stoptheslopweb26032543.z19.web.core.windows.net}"
ALLOWED_ORIGINS="${ALLOWED_ORIGINS:-${STATIC_ORIGIN},https://stoptheslop.tech,https://www.stoptheslop.tech,http://127.0.0.1:8080,http://localhost:8080}"
OPENAI_ACCOUNT="${OPENAI_ACCOUNT:-stoptheslopopenai260325}"
OPENAI_CHAT_DEPLOYMENT="${OPENAI_CHAT_DEPLOYMENT:-gpt-4o-mini}"
OPENAI_EMBEDDING_DEPLOYMENT="${OPENAI_EMBEDDING_DEPLOYMENT:-text-embedding-3-small}"
OPENAI_API_VERSION="${OPENAI_API_VERSION:-2024-10-21}"
EXISTING_GOOGLE_CLIENT_ID="$(az containerapp show --name "${APP_NAME}" --resource-group "${RESOURCE_GROUP}" --query "properties.template.containers[0].env[?name=='GOOGLE_CLIENT_ID'].value | [0]" --output tsv 2>/dev/null || true)"
EXISTING_AUTH_SESSION_SECRET="$(az containerapp show --name "${APP_NAME}" --resource-group "${RESOURCE_GROUP}" --query "properties.template.containers[0].env[?name=='AUTH_SESSION_SECRET'].value | [0]" --output tsv 2>/dev/null || true)"
EXISTING_PERPLEXITY_API_KEY="$(az containerapp show --name "${APP_NAME}" --resource-group "${RESOURCE_GROUP}" --query "properties.template.containers[0].env[?name=='PERPLEXITY_API_KEY'].value | [0]" --output tsv 2>/dev/null || true)"
GOOGLE_CLIENT_ID="${GOOGLE_CLIENT_ID:-${EXISTING_GOOGLE_CLIENT_ID}}"
AUTH_SESSION_SECRET="${AUTH_SESSION_SECRET:-${EXISTING_AUTH_SESSION_SECRET}}"
PERPLEXITY_API_KEY="${PERPLEXITY_API_KEY:-${EXISTING_PERPLEXITY_API_KEY}}"
ACR_SCOPE="$(az acr list --resource-group "${RESOURCE_GROUP}" --query '[0].id' --output tsv 2>/dev/null || true)"

if [[ -z "${AUTH_SESSION_SECRET}" ]]; then
  AUTH_SESSION_SECRET="$(python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(48))
PY
)"
fi

ensure_role_assignment() {
  local principal_id="$1"
  local role_name="$2"
  local scope="$3"
  local existing_count

  [[ -z "${principal_id}" || -z "${scope}" ]] && return

  existing_count="$(az role assignment list --assignee-object-id "${principal_id}" --scope "${scope}" --query "[?roleDefinitionName=='${role_name}'] | length(@)" --output tsv)"
  if [[ "${existing_count}" == "0" ]]; then
    az role assignment create \
      --assignee-object-id "${principal_id}" \
      --assignee-principal-type ServicePrincipal \
      --role "${role_name}" \
      --scope "${scope}" >/dev/null
  fi
}

assign_runtime_roles() {
  local principal_id
  local storage_scope

  principal_id="$(az containerapp show --name "${APP_NAME}" --resource-group "${RESOURCE_GROUP}" --query 'identity.principalId' --output tsv 2>/dev/null || true)"
  storage_scope="$(az storage account show --name "${STORAGE_ACCOUNT}" --resource-group "${RESOURCE_GROUP}" --query 'id' --output tsv)"

  ensure_role_assignment "${principal_id}" "AcrPull" "${ACR_SCOPE}"
  ensure_role_assignment "${principal_id}" "Storage Table Data Contributor" "${storage_scope}"
  ensure_role_assignment "${principal_id}" "Storage Blob Data Contributor" "${storage_scope}"
}

ensure_blob_container() {
  local storage_key

  storage_key="$(az storage account keys list --resource-group "${RESOURCE_GROUP}" --account-name "${STORAGE_ACCOUNT}" --query '[0].value' --output tsv)"
  az storage container create \
    --account-name "${STORAGE_ACCOUNT}" \
    --account-key "${storage_key}" \
    --name "${SOURCE_BLOB_CONTAINER}" >/dev/null
}

deploy_container_app() {
  local openai_endpoint=""
  local openai_key=""

  openai_endpoint="$(az cognitiveservices account show --name "${OPENAI_ACCOUNT}" --resource-group "${RESOURCE_GROUP}" --query 'properties.endpoint' --output tsv 2>/dev/null || true)"
  openai_key="$(az cognitiveservices account keys list --name "${OPENAI_ACCOUNT}" --resource-group "${RESOURCE_GROUP}" --query 'key1' --output tsv 2>/dev/null || true)"

  az containerapp up \
    --name "${APP_NAME}" \
    --resource-group "${RESOURCE_GROUP}" \
    --environment "${ENVIRONMENT_NAME}" \
    --location "${LOCATION}" \
    --source "${ROOT_DIR}/backend" \
    --ingress external \
    --target-port 8000 \
    --system-assigned \
    --env-vars STORAGE_ACCOUNT_NAME="${STORAGE_ACCOUNT}" TABLE_NAME="${TABLE_NAME}" SOURCE_BLOB_CONTAINER="${SOURCE_BLOB_CONTAINER}" ENABLE_SEED_DATA="${ENABLE_SEED_DATA}" ALLOWED_ORIGINS="${ALLOWED_ORIGINS}" AZURE_OPENAI_ENDPOINT="${openai_endpoint}" AZURE_OPENAI_API_KEY="${openai_key}" AZURE_OPENAI_CHAT_DEPLOYMENT="${OPENAI_CHAT_DEPLOYMENT}" AZURE_OPENAI_EMBEDDING_DEPLOYMENT="${OPENAI_EMBEDDING_DEPLOYMENT}" AZURE_OPENAI_API_VERSION="${OPENAI_API_VERSION}" GOOGLE_CLIENT_ID="${GOOGLE_CLIENT_ID}" AUTH_SESSION_SECRET="${AUTH_SESSION_SECRET}" PERPLEXITY_API_KEY="${PERPLEXITY_API_KEY}"
}

echo "Deploying backend container app ${APP_NAME}..."
ensure_blob_container
if ! deploy_container_app; then
  assign_runtime_roles
  ensure_blob_container
  deploy_container_app
fi

assign_runtime_roles

az containerapp update \
  --name "${APP_NAME}" \
  --resource-group "${RESOURCE_GROUP}" \
  --min-replicas "${MIN_REPLICAS}" >/dev/null

API_FQDN="$(az containerapp show --name "${APP_NAME}" --resource-group "${RESOURCE_GROUP}" --query 'properties.configuration.ingress.fqdn' --output tsv)"

echo "Backend deployment complete."
echo "API base URL: https://${API_FQDN}"
