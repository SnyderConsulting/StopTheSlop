# System Architecture

## Current Shape

- static website frontend
- backend API in Azure Container Apps
- private source storage for submitted and fetched artifacts
- derived graph objects powering public surfaces
- AI grounding across submission context, graph state, and the live web

## Target Shape

### Write Path

1. User submits text, URLs, files, or mixed content through the universal composer.
2. API stores private source records and moderation metadata as the source of truth.
3. Extraction and graph-write jobs create or update entities, claims, guides, questions, answers, and clusters.
4. API returns a grounded AI reply and continues the conversation thread.
5. Derived public surfaces refresh from graph state.

### Sync Path

1. New user turns append to the private conversation.
2. New sources and conversation turns trigger re-extraction and regeneration.
3. Corroboration and contradiction scores update as related evidence accumulates.
4. Search, retrieval, and feed indexes update as derived read models.

### Read Path

1. Home loads graph-derived claims, guides, questions, answers, entities, and clusters.
2. Entity and cluster pages load synthesized public artifacts plus supporting evidence summaries.
3. Conversation views load the private thread plus grounded citations.

## Likely Azure Services

- Azure Container Apps for API and ingestion workers
- Blob Storage for uploaded and fetched source artifacts
- Azure Table Storage, Cosmos DB, or another graph-capable store for core records
- Azure Queue Storage or Service Bus for async ingestion and regeneration
- Azure OpenAI for extraction, grounding, summaries, and embeddings
- Azure AI Search for retrieval, vector similarity, and derived read indexes
- Key Vault for secrets
- Application Insights for tracing and failures

## Separation Of Concerns

- transactional source of truth lives in private source storage plus core graph records
- public publishing is derived from graph state
- grounding can read from source artifacts, graph state, and live web search
- retrieval and feed indexes are derived read models
- moderation and redaction happen before anything becomes publicly visible

## Operational Concerns

- rate limiting, CAPTCHA, and anonymous abuse control
- redaction and private source retention policy
- retry-safe ingestion and regeneration jobs
- replay path for rebuilding graph-derived artifacts and indexes
- provenance retention across graph compaction and synthesis
- deciding when the current storage model should move to a more graph-native system
