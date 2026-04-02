# AI Enrichment Strategy

## Principle

AI should sit behind the product as an enrichment layer.

It should help make the archive:

- more searchable
- easier to browse
- easier to summarize
- better connected across similar issues

It should not become the main user experience.

## First-Pass Enrichment Jobs

### Structured tagging

On issue creation or major thread updates, run an LLM extraction step that returns strict JSON for:

- `failure_modes`
- `topics`
- `mentioned_models`
- `mentioned_tools`
- `canonical_tags`
- `workarounds`
- `sentiment`
- `is_duplicate_candidate`

### Embeddings

Generate embeddings for:

- issue title plus summary
- issue plus synced comments
- optional separate embeddings for comments if needed later

### Thread summaries

Create short rolling summaries that capture:

- what happened
- what others report
- practical advice that appeared
- disagreement or uncertainty

### External evidence ingestion

Pull structured outside data where it improves discoverability and context, especially for:

- benchmark results
- pricing and latency
- human preference leaderboards
- provider and modality metadata

See:

- [[20-AI/Public Enrichment Sources]]
- [[20-AI/Web Discovery and Ingestion Sources]]

## Product Rules

- raw user text is never overwritten
- AI output is stored separately from user content
- all answer experiences should cite underlying issues or comments
- low-confidence AI output should degrade gracefully rather than block posting

## User-Facing Features Enabled By Enrichment

- better filtering and tags
- similar issues panels
- cluster pages
- natural-language questions over the archive
- thread digest cards

## Order Of Operations

1. tagging
2. embeddings
3. related issues
4. ask-the-archive
5. cluster generation
