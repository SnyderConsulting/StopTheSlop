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
APP_NAME="${APP_NAME:-stoptheslop-api}"

read_container_env() {
  local env_name="$1"
  az containerapp show \
    --name "${APP_NAME}" \
    --resource-group "${RESOURCE_GROUP}" \
    --query "properties.template.containers[0].env[?name=='${env_name}'].value | [0]" \
    --output tsv 2>/dev/null || true
}

export STORAGE_ACCOUNT_NAME="${STORAGE_ACCOUNT_NAME:-$(read_container_env STORAGE_ACCOUNT_NAME)}"
export TABLE_NAME="${TABLE_NAME:-$(read_container_env TABLE_NAME)}"
export AZURE_OPENAI_ENDPOINT="${AZURE_OPENAI_ENDPOINT:-$(read_container_env AZURE_OPENAI_ENDPOINT)}"
export AZURE_OPENAI_API_KEY="${AZURE_OPENAI_API_KEY:-$(read_container_env AZURE_OPENAI_API_KEY)}"
export AZURE_OPENAI_CHAT_DEPLOYMENT="${AZURE_OPENAI_CHAT_DEPLOYMENT:-$(read_container_env AZURE_OPENAI_CHAT_DEPLOYMENT)}"
export AZURE_OPENAI_API_VERSION="${AZURE_OPENAI_API_VERSION:-$(read_container_env AZURE_OPENAI_API_VERSION)}"

cd "${ROOT_DIR}/backend"
PYTHONPATH="${ROOT_DIR}/backend" "${ROOT_DIR}/.venv/bin/python" run_public_graph_rebuild.py "$@"
