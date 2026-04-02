# Omni Wiki

## Concept

The Omni Wiki is a living entity layer for the AI ecosystem.

Instead of treating every mention of a model, tool, agent, service, framework, or company as plain text, the system should try to resolve that mention into a canonical entity page.

Examples:

- `Claude`
- `ChatGPT`
- `Gemini 2.5 Pro`
- `GitHub Copilot`
- `Cursor`
- `Replit Agent`
- `OpenAI API`

Each Omni Page should act as a living amalgamation of:

- official product links
- source-derived signals from StopTheSlop
- external reference links
- machine-generated summaries
- structured strengths and weaknesses
- usage claims, guides, questions, and answers synthesized from real submissions

## Product Thesis

Users should be able to say things like:

- `I use Claude for debugging Python services`
- `Gemini is good at long context but bad at reliable code edits`
- `Copilot is fine for autocomplete and bad for repo-wide changes`

The product should detect likely entities in those statements and:

1. link them to an existing Omni Page if the entity is already known
2. propose candidate matches if the mention is ambiguous
3. create a new Omni Page when the entity does not yet exist

## What Makes This Different From A Normal Wiki

This is not a manually curated encyclopedia first.

It is an entity resolution and knowledge synthesis system with wiki-like pages.

That means:

- pages can be created on demand
- pages can improve over time as new evidence arrives
- pages can aggregate many source types
- structured claims matter more than prose alone
- provenance matters more than polish

## Page Anatomy

Every Omni Page should contain:

### Canonical identity

- canonical name
- short description
- aliases
- entity type
- vendor or parent organization
- official URL

### External references

- Wikipedia
- product website
- documentation
- subreddit
- Discord or community links
- search links
- other known identifiers

### Community layer

- claims and guides derived from StopTheSlop submissions
- user statements like `I use this for X`
- claimed strengths
- claimed weaknesses
- common workarounds

### Machine layer

- generated summary
- extracted tags
- related entities
- similar tools
- embeddings
- cluster membership

### Evidence layer

- sourced claims
- timestamps
- freshness markers
- confidence or support signals

## Core User Flows

### During composer submission

When someone submits something through the universal composer, the system should:

- detect likely entities from text, URLs, images, or other inputs
- link them to existing Omni Pages when the match is clear
- create new pages when the graph does not yet know the entity
- attach source provenance to each extracted relationship

### During browsing

Users should be able to click from a claim, guide, answer, or cluster into:

- the Omni Page for the referenced tool
- related models from the same family
- competing tools used for the same task

### During exploration

Users should be able to ask:

- what do people use Claude for
- what is Cursor good at
- what is Copilot bad at lately
- which coding agents are complained about most

## Design Principle

The Omni Page should be a stable public object.

Private source records, AI extraction, and external references should all point into that object instead of producing disconnected text fragments everywhere.

## Non-Goal

Do not try to pre-curate the entire AI ecosystem.

The system should be capable of discovering and instantiating new entities on demand.
