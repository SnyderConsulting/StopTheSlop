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
APP_NAME="${APP_NAME:-stoptheslop-api}"
JOB_NAME="${JOB_NAME:-stoptheslop-webcrawl}"
WEB_CRAWL_CRON_EXPRESSION="${WEB_CRAWL_CRON_EXPRESSION:-0 13 * * *}"
WEB_CRAWL_MAX_RESULTS_PER_QUERY="${WEB_CRAWL_MAX_RESULTS_PER_QUERY:-4}"
WEB_CRAWL_MAX_ITEMS="${WEB_CRAWL_MAX_ITEMS:-16}"

query_app_env() {
  local env_name="$1"
  az containerapp show \
    --name "${APP_NAME}" \
    --resource-group "${RESOURCE_GROUP}" \
    --query "properties.template.containers[0].env[?name=='${env_name}'].value | [0]" \
    --output tsv 2>/dev/null || true
}

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

IMAGE="$(az containerapp show --name "${APP_NAME}" --resource-group "${RESOURCE_GROUP}" --query 'properties.template.containers[0].image' --output tsv)"
if [[ -z "${IMAGE}" ]]; then
  echo "Could not resolve the backend image from ${APP_NAME}." >&2
  exit 1
fi

REGISTRY_SERVER="${IMAGE%%/*}"
ACR_NAME="$(az acr list --resource-group "${RESOURCE_GROUP}" --query "[?loginServer=='${REGISTRY_SERVER}'].name | [0]" --output tsv)"
ACR_USERNAME="$(az acr credential show --name "${ACR_NAME}" --query 'username' --output tsv)"
ACR_PASSWORD="$(az acr credential show --name "${ACR_NAME}" --query 'passwords[0].value' --output tsv)"
STORAGE_ACCOUNT_NAME="$(query_app_env STORAGE_ACCOUNT_NAME)"
TABLE_NAME="$(query_app_env TABLE_NAME)"
SOURCE_BLOB_CONTAINER="$(query_app_env SOURCE_BLOB_CONTAINER)"
AZURE_OPENAI_ENDPOINT="$(query_app_env AZURE_OPENAI_ENDPOINT)"
AZURE_OPENAI_API_KEY="$(query_app_env AZURE_OPENAI_API_KEY)"
AZURE_OPENAI_CHAT_DEPLOYMENT="$(query_app_env AZURE_OPENAI_CHAT_DEPLOYMENT)"
AZURE_OPENAI_API_VERSION="$(query_app_env AZURE_OPENAI_API_VERSION)"
PERPLEXITY_API_KEY="$(query_app_env PERPLEXITY_API_KEY)"

ENV_VARS=(
  "PYTHONUNBUFFERED=1"
  "STORAGE_ACCOUNT_NAME=${STORAGE_ACCOUNT_NAME}"
  "TABLE_NAME=${TABLE_NAME}"
  "SOURCE_BLOB_CONTAINER=${SOURCE_BLOB_CONTAINER}"
  "AZURE_OPENAI_ENDPOINT=${AZURE_OPENAI_ENDPOINT}"
  "AZURE_OPENAI_API_KEY=${AZURE_OPENAI_API_KEY}"
  "AZURE_OPENAI_CHAT_DEPLOYMENT=${AZURE_OPENAI_CHAT_DEPLOYMENT}"
  "AZURE_OPENAI_API_VERSION=${AZURE_OPENAI_API_VERSION}"
  "PERPLEXITY_API_KEY=${PERPLEXITY_API_KEY}"
  "WEB_CRAWL_MAX_RESULTS_PER_QUERY=${WEB_CRAWL_MAX_RESULTS_PER_QUERY}"
  "WEB_CRAWL_MAX_ITEMS=${WEB_CRAWL_MAX_ITEMS}"
)

if az containerapp job show --name "${JOB_NAME}" --resource-group "${RESOURCE_GROUP}" >/dev/null 2>&1; then
  echo "Updating crawler job ${JOB_NAME}..."
  az containerapp job update \
    --name "${JOB_NAME}" \
    --resource-group "${RESOURCE_GROUP}" \
    --image "${IMAGE}" \
    --cpu 0.5 \
    --memory 1.0Gi \
    --replica-timeout 1800 \
    --replica-retry-limit 1 \
    --replica-completion-count 1 \
    --parallelism 1 \
    --cron-expression "${WEB_CRAWL_CRON_EXPRESSION}" \
    --command python \
    --args run_web_crawl.py \
    --replace-env-vars "${ENV_VARS[@]}" >/dev/null
else
  echo "Creating crawler job ${JOB_NAME}..."
  az containerapp job create \
    --name "${JOB_NAME}" \
    --resource-group "${RESOURCE_GROUP}" \
    --environment "${ENVIRONMENT_NAME}" \
    --trigger-type Schedule \
    --cron-expression "${WEB_CRAWL_CRON_EXPRESSION}" \
    --image "${IMAGE}" \
    --registry-server "${REGISTRY_SERVER}" \
    --registry-username "${ACR_USERNAME}" \
    --registry-password "${ACR_PASSWORD}" \
    --mi-system-assigned \
    --cpu 0.5 \
    --memory 1.0Gi \
    --replica-timeout 1800 \
    --replica-retry-limit 1 \
    --replica-completion-count 1 \
    --parallelism 1 \
    --command python \
    --args run_web_crawl.py \
    --env-vars "${ENV_VARS[@]}" >/dev/null
fi

JOB_PRINCIPAL_ID="$(az containerapp job show --name "${JOB_NAME}" --resource-group "${RESOURCE_GROUP}" --query 'identity.principalId' --output tsv)"
STORAGE_SCOPE="$(az storage account show --name "${STORAGE_ACCOUNT_NAME}" --resource-group "${RESOURCE_GROUP}" --query 'id' --output tsv)"

ensure_role_assignment "${JOB_PRINCIPAL_ID}" "Storage Table Data Contributor" "${STORAGE_SCOPE}"
ensure_role_assignment "${JOB_PRINCIPAL_ID}" "Storage Blob Data Contributor" "${STORAGE_SCOPE}"

echo "Crawler job deployed."
echo "Job name: ${JOB_NAME}"
echo "Schedule (UTC): ${WEB_CRAWL_CRON_EXPRESSION}"
