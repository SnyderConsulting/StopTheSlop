#!/usr/bin/env bash

set -euo pipefail

RESOURCE_GROUP="${RESOURCE_GROUP:-StopTheSlop}"
LOCATION="${LOCATION:-centralus}"
OPENAI_ACCOUNT="${OPENAI_ACCOUNT:-stoptheslopopenai260325}"
OPENAI_CHAT_DEPLOYMENT="${OPENAI_CHAT_DEPLOYMENT:-gpt-4o-mini}"
OPENAI_CHAT_MODEL="${OPENAI_CHAT_MODEL:-gpt-4o-mini}"
OPENAI_CHAT_VERSION="${OPENAI_CHAT_VERSION:-2024-07-18}"
OPENAI_EMBEDDING_DEPLOYMENT="${OPENAI_EMBEDDING_DEPLOYMENT:-text-embedding-3-small}"
OPENAI_EMBEDDING_MODEL="${OPENAI_EMBEDDING_MODEL:-text-embedding-3-small}"
OPENAI_EMBEDDING_VERSION="${OPENAI_EMBEDDING_VERSION:-1}"
SEARCH_SERVICE="${SEARCH_SERVICE:-stoptheslopsearch260325}"

ensure_openai_account() {
  if az cognitiveservices account show -g "${RESOURCE_GROUP}" -n "${OPENAI_ACCOUNT}" >/dev/null 2>&1; then
    return
  fi

  az cognitiveservices account create \
    -g "${RESOURCE_GROUP}" \
    -n "${OPENAI_ACCOUNT}" \
    -l "${LOCATION}" \
    --kind OpenAI \
    --sku S0 \
    --custom-domain "${OPENAI_ACCOUNT}" \
    --yes >/dev/null
}

ensure_openai_deployment() {
  local deployment_name="$1"
  local model_name="$2"
  local model_version="$3"

  if az cognitiveservices account deployment show \
    -g "${RESOURCE_GROUP}" \
    -n "${OPENAI_ACCOUNT}" \
    --deployment-name "${deployment_name}" >/dev/null 2>&1; then
    return
  fi

  az cognitiveservices account deployment create \
    -g "${RESOURCE_GROUP}" \
    -n "${OPENAI_ACCOUNT}" \
    --deployment-name "${deployment_name}" \
    --model-name "${model_name}" \
    --model-version "${model_version}" \
    --model-format OpenAI \
    --sku-name GlobalStandard \
    --sku-capacity 1 >/dev/null
}

ensure_search_service() {
  if az search service show -g "${RESOURCE_GROUP}" -n "${SEARCH_SERVICE}" >/dev/null 2>&1; then
    return
  fi

  az search service create \
    -g "${RESOURCE_GROUP}" \
    -n "${SEARCH_SERVICE}" \
    --sku basic \
    -l "${LOCATION}" \
    --semantic-search free >/dev/null
}

echo "Provisioning Azure AI services..."
ensure_openai_account
ensure_openai_deployment "${OPENAI_CHAT_DEPLOYMENT}" "${OPENAI_CHAT_MODEL}" "${OPENAI_CHAT_VERSION}"
ensure_openai_deployment "${OPENAI_EMBEDDING_DEPLOYMENT}" "${OPENAI_EMBEDDING_MODEL}" "${OPENAI_EMBEDDING_VERSION}"
ensure_search_service

echo "Azure OpenAI endpoint: $(az cognitiveservices account show -g "${RESOURCE_GROUP}" -n "${OPENAI_ACCOUNT}" --query 'properties.endpoint' -o tsv)"
echo "Azure AI Search endpoint: $(az search service show -g "${RESOURCE_GROUP}" -n "${SEARCH_SERVICE}" --query 'endpoint' -o tsv)"
