# Open Questions

## Product

- When should private conversations become shareable by link, if at all?
- How much graph-update transparency should appear after each AI reply?
- What editorial controls should exist for featuring guides, answers, and clusters?

## AI

- How should trust weighting differ across anonymous users, authenticated users, imported web pages, and curated sources?
- When should contradictory claims be merged into a higher-level synthesis versus kept separate?
- What thresholds should promote signals into public guides, answers, or clusters?

## Platform

- Is Azure Table Storage still sufficient once multimodal source storage and graph relationships grow, or should the project move to a graph-oriented store?
- Should ingestion and regeneration move from in-process workers to queues and dedicated workers immediately or after proving volume?
- Where should blob storage, embeddings, and derivative caches live?

## Community

- What appeal or review workflow should exist for AI moderation errors?
- How should copyright-heavy uploads or long-form pasted text be handled?
- What rate limits and reputation boosts should anonymous versus authenticated users receive?
