# StopTheSlop

Product and platform notes live in the Obsidian vault at [docs/obsidian-vault](/Users/andrewsnyder/AI-Projects/StopTheSlop/docs/obsidian-vault).

Backend-backed web app for `stoptheslop.tech`.

## What it does

- Branded landing page around the AI reliability thesis
- Structured public intake form for AI failures
- Backend API for tickets and reactions
- Azure Table Storage persistence
- Explicit capture of:
  - primary AI modality
  - failed product or tool
  - specific model, version, or chatbot name
  - access surface such as website chatbot, API, IDE, phone agent, or robot
- Public board with filterable tickets and local reactions
- Public board with filterable tickets and persisted reactions

## Local preview

From this directory, run the backend and frontend separately:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r backend/requirements.txt
export AZURE_STORAGE_CONNECTION_STRING="$(az storage account show-connection-string --resource-group StopTheSlop --name stoptheslopweb26032543 --query connectionString --output tsv)"
export TABLE_NAME=StopTheSlopTicketsDev
python backend/server.py
```

In a second shell:

```bash
python3 -m http.server 8080
```

Then open `http://127.0.0.1:8080`.

## Azure deployment

The CLI helpers in `scripts/provision_azure.sh` and
`scripts/deploy_static_site.sh` provision a static website.

`scripts/deploy_backend.sh` deploys the Python API to Azure Container Apps.
storage account and upload the current site files.

They assume:

- resource group: `StopTheSlop`
- region: `centralus`
- Azure CLI is already logged into the correct subscription

## Next pass

- add Discord fan-out and ticket-thread synchronization
- add moderation and admin controls
- expose a benchmark export pipeline
- map the custom domain to both frontend and API
