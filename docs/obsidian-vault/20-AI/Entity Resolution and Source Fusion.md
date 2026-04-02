# Entity Resolution and Source Fusion

## Why This Exists

The Omni Wiki only works if the system can map messy user text onto canonical entities.

This is the key transition:

- from raw text mention
- to canonical entity
- to living Omni Page

## Entity Resolution Pipeline

### 1. Mention detection

Detect likely entities in free text such as:

- model names
- product names
- company names
- agent names
- APIs
- benchmarks

Examples:

- `Claude`
- `Claude 3.7 Sonnet`
- `ChatGPT`
- `OpenAI API`
- `GitHub Copilot`

### 2. Candidate generation

For each mention, generate likely matches from:

- existing Omni entities
- alias tables
- external reference sources
- web search candidates

### 3. Disambiguation

Pick the most likely entity using:

- text similarity
- alias match strength
- vendor match
- modality match
- surrounding context
- popularity priors

If confidence is too low:

- show multiple candidates
- or defer linking and queue review

### 4. Entity creation

If no candidate is good enough, create a draft Omni entity with:

- canonical label
- short generated description
- known aliases
- external URLs when found
- initial evidence bundle

## Source Fusion Model

An Omni Page should not be a single blob of generated text.

It should be assembled from multiple evidence channels:

- StopTheSlop issue reports
- synced Discord discussions
- official vendor pages
- external reference pages
- search-derived summaries
- public benchmark and market data sources

See also:

- [[20-AI/Public Enrichment Sources]]

## Data Model Recommendation

Treat the entity as a graph object with attached claims.

Suggested core entity fields:

- `entity_id`
- `entity_type`
- `canonical_name`
- `description`
- `aliases`
- `vendor`
- `official_url`
- `status`
- `created_at`
- `updated_at`

Suggested claim fields:

- `claim_id`
- `entity_id`
- `claim_type`
- `claim_text`
- `source_type`
- `source_url`
- `source_title`
- `evidence_excerpt`
- `observed_at`
- `confidence`

## Claim Types

Useful initial claim types:

- `good_for`
- `bad_for`
- `used_for`
- `complained_about_for`
- `integrates_with`
- `competes_with`
- `owned_by`
- `official_link`
- `community_link`

## Creation Strategy

Use a two-speed model.

### Fast path

On first mention:

- create a lightweight entity shell
- link the post immediately
- queue enrichment asynchronously

### Slow path

Background jobs then:

- gather candidate external references
- generate a short summary
- extract strengths and weaknesses
- compute embeddings
- find related entities
- update the public Omni Page

## Important Product Constraint

Never let the generated summary become the only truth.

The stable truth should be:

- the canonical entity record
- the underlying claims
- the links back to source material

The summary is a view over that data, not the primary asset.

## Matching Heuristics

Use these matching layers in order:

1. exact alias or canonical name
2. normalized string match
3. vendor plus product co-occurrence
4. embedding similarity against known entities
5. web-enriched candidate search

## Failure Modes To Expect

- `Claude` versus specific Claude model versions
- `Copilot` meaning GitHub Copilot versus Microsoft Copilot
- `Gemini` meaning model family versus app surface
- renamed products
- new unreleased models with weak web presence

## Recommendation

Start with narrow, high-confidence entity types:

- model
- product
- vendor
- API surface

Do not start by modeling every concept in the ecosystem.
