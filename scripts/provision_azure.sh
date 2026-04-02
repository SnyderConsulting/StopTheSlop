#!/usr/bin/env bash

set -euo pipefail

RESOURCE_GROUP="${RESOURCE_GROUP:-StopTheSlop}"
LOCATION="${LOCATION:-centralus}"
LOG_WORKSPACE="${LOG_WORKSPACE:-stoptheslop-logs}"
CONTAINER_ENV="${CONTAINER_ENV:-stoptheslop-env}"
KEY_VAULT="${KEY_VAULT:-stoptheslop-kv-26032543}"
STORAGE_ACCOUNT="${STORAGE_ACCOUNT:-stoptheslopweb26032543}"

echo "Creating storage account ${STORAGE_ACCOUNT} in ${RESOURCE_GROUP}..."
az storage account create \
  --resource-group "${RESOURCE_GROUP}" \
  --name "${STORAGE_ACCOUNT}" \
  --location "${LOCATION}" \
  --sku Standard_LRS \
  --kind StorageV2

az storage account update \
  --resource-group "${RESOURCE_GROUP}" \
  --name "${STORAGE_ACCOUNT}" \
  --min-tls-version TLS1_2 >/dev/null

echo "Enabling static website hosting..."
ACCOUNT_KEY="$(az storage account keys list --resource-group "${RESOURCE_GROUP}" --account-name "${STORAGE_ACCOUNT}" --query '[0].value' --output tsv)"

az storage blob service-properties update \
  --account-name "${STORAGE_ACCOUNT}" \
  --account-key "${ACCOUNT_KEY}" \
  --static-website \
  --index-document index.html \
  --404-document index.html

echo "Creating Log Analytics workspace ${LOG_WORKSPACE}..."
az monitor log-analytics workspace create \
  --resource-group "${RESOURCE_GROUP}" \
  --workspace-name "${LOG_WORKSPACE}" \
  --location "${LOCATION}"

echo "Creating Container Apps environment ${CONTAINER_ENV}..."
WORKSPACE_ID="$(az monitor log-analytics workspace show --resource-group "${RESOURCE_GROUP}" --workspace-name "${LOG_WORKSPACE}" --query customerId --output tsv)"
WORKSPACE_KEY="$(az monitor log-analytics workspace get-shared-keys --resource-group "${RESOURCE_GROUP}" --workspace-name "${LOG_WORKSPACE}" --query primarySharedKey --output tsv)"

az containerapp env create \
  --resource-group "${RESOURCE_GROUP}" \
  --name "${CONTAINER_ENV}" \
  --location "${LOCATION}" \
  --logs-workspace-id "${WORKSPACE_ID}" \
  --logs-workspace-key "${WORKSPACE_KEY}"

echo "Creating Key Vault ${KEY_VAULT}..."
az keyvault create \
  --resource-group "${RESOURCE_GROUP}" \
  --name "${KEY_VAULT}" \
  --location "${LOCATION}" \
  --sku standard

echo "Provisioning complete."
echo "Storage account: ${STORAGE_ACCOUNT}"
echo "Container Apps environment: ${CONTAINER_ENV}"
echo "Key Vault: ${KEY_VAULT}"
