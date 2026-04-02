#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RESOURCE_GROUP="${RESOURCE_GROUP:-StopTheSlop}"
STORAGE_ACCOUNT="${STORAGE_ACCOUNT:-stoptheslopweb26032543}"

ACCOUNT_KEY="$(az storage account keys list --resource-group "${RESOURCE_GROUP}" --account-name "${STORAGE_ACCOUNT}" --query '[0].value' --output tsv)"

echo "Uploading static site files to ${STORAGE_ACCOUNT}..."

for file in index.html board.html wiki.html search.html feedback.html styles.css app.js api-config.js analytics-config.js analytics-bootstrap.js; do
  az storage blob upload \
    --account-name "${STORAGE_ACCOUNT}" \
    --account-key "${ACCOUNT_KEY}" \
    --container-name '$web' \
    --file "${ROOT_DIR}/${file}" \
    --name "${file}" \
    --overwrite true
done

for asset in StopTheSlopLogo.png StopTheSlopLogoHorizontal.png; do
  az storage blob upload \
    --account-name "${STORAGE_ACCOUNT}" \
    --account-key "${ACCOUNT_KEY}" \
    --container-name '$web' \
    --file "${ROOT_DIR}/src/${asset}" \
    --name "src/${asset}" \
    --overwrite true
done

az storage blob upload \
  --account-name "${STORAGE_ACCOUNT}" \
  --account-key "${ACCOUNT_KEY}" \
  --container-name '$web' \
  --file "${ROOT_DIR}/index.html" \
  --name 404.html \
  --overwrite true

ENDPOINT="$(az storage account show --resource-group "${RESOURCE_GROUP}" --name "${STORAGE_ACCOUNT}" --query 'primaryEndpoints.web' --output tsv)"

echo "Deployment complete."
echo "Static site endpoint: ${ENDPOINT}"
