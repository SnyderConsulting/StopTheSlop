# Omni Wiki Architecture

## Goal

Support on-demand creation and enrichment of canonical AI entity pages.

## Core Components

### Entity store

Stores canonical Omni entities, aliases, and claims.

Likely options:

- Azure Cosmos DB for flexible entity and claim documents
- PostgreSQL if relational control is preferred

### Search index

Supports:

- entity lookup
- alias lookup
- hybrid search
- similarity search
- auto-suggest

Azure AI Search is the natural fit for this layer.

### Enrichment workers

Background jobs for:

- mention extraction
- entity candidate generation
- external source lookups
- summarization
- embeddings
- related-entity computation

### Source registry

Tracks known external sources for an entity:

- official site
- docs site
- Wikipedia
- subreddit
- StopTheSlop board
- Discord thread set

## Write Path

1. User submits a post or usage statement.
2. Mention detector finds candidate entities in the text.
3. Existing entities are linked where confidence is high.
4. Missing entities are created as shells.
5. Background enrichment jobs fill in the Omni Page.

## Read Path

1. User opens an Omni Page.
2. API loads canonical entity data.
3. API loads claims, related issues, related entities, and summaries.
4. Page renders both structured facts and evidence-backed narrative.

## Serving Model

The page should mix:

- canonical facts
- recent community evidence
- AI-generated synthesis
- outbound links

This should feel like a knowledge card crossed with a wiki page and an issue archive.

## Practical MVP

The first deployable Omni Wiki can be much smaller than the end-state vision.

Start with:

- entity records
- alias matching
- issue-to-entity linking
- one generated summary
- official URL and Wikipedia URL fields
- related issues
- simple `good for` and `bad for` claim extraction

## Key Operational Rules

- entity linking must be idempotent
- entity summaries must be refreshable
- source freshness should be tracked
- deleted or merged entities need redirects
- ambiguous mentions should not silently auto-resolve at low confidence
