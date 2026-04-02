# Public Enrichment Sources

Last reviewed: 2026-03-25

## Why This Note Exists

The wiki should be enriched with outside data where it adds signal, but not every AI leaderboard or tooling product exposes usable public data.

This note tracks which sources are realistic inputs for StopTheSlop entity pages.

For community discussions, issue trackers, and crawlable web sources, see:

- [[20-AI/Web Discovery and Ingestion Sources]]

## Recommendation Summary

Best current sources to build adapters for:

1. Artificial Analysis
2. Hugging Face Open LLM Leaderboard
3. LM Arena
4. Scale Labs leaderboards and public datasets
5. Vellum survey and public benchmark material

Sources that are not good public wiki feeds:

- LangSmith
- Helicone
- Phoenix
- Braintrust
- Martian
- Berri

## Strong Public Sources

### Artificial Analysis

Why it is useful:

- structured benchmark data
- pricing data
- latency and throughput data
- multimodal coverage beyond text models

Why it is strong:

- has an official API
- is oriented around model comparison, not private customer traces

Good fit for wiki fields:

- benchmark metrics
- price and speed metadata
- modality support
- model release tracking

References:

- https://artificialanalysis.ai/api-reference
- https://artificialanalysis.ai/documentation

### Hugging Face Open LLM Leaderboard

Why it is useful:

- public benchmark result datasets
- per-model details
- strong fit for open and open-weight model pages

Why it is strong:

- leaderboard data is published through Hugging Face datasets
- easy to treat as structured benchmark evidence

Good fit for wiki fields:

- benchmark scores
- model family lineage
- open model metadata
- benchmark history snapshots

References:

- https://huggingface.co/open-llm-leaderboard/datasets
- https://huggingface.co/docs/leaderboards/en/open_llm_leaderboard/archive

### LM Arena

Why it is useful:

- human preference data
- in-the-wild prompts and votes
- closer to real usage than static academic benchmarks

Why it is strong:

- official dataset releases exist
- Search Arena also has an open dataset and analysis code

Good fit for wiki fields:

- preference leaderboard evidence
- task clusters from real prompts
- model-versus-model comparisons
- examples of where people preferred one system over another

Constraint:

- this is preference data, not reliability truth

References:

- https://arena.ai/how-it-works
- https://lmarena.ai/blog/dataset/
- https://lmarena.ai/blog/two-year-celebration/
- https://lmarena.ai/blog/search-arena/

## Partial Sources

### Scale Labs and SEAL-style leaderboards

Why it is useful:

- strong benchmark methodology
- public leaderboard pages
- some public datasets, such as Humanity's Last Exam

Why it is only partial:

- public pages are useful, but a stable public leaderboard ingestion API was not found in this review
- likely better as selective benchmark enrichment than a core syncing feed

Good fit for wiki fields:

- benchmark citations
- calibration and accuracy notes
- notable public leaderboard positions

References:

- https://labs.scale.com/leaderboard/humanitys_last_exam
- https://labs.scale.com/leaderboard/tool_use_enterprise
- https://scale.com/blog/showdown

### Vellum

Why it is useful:

- public survey material about what builders are using
- public benchmark and model comparison content

Why it is only partial:

- a stable public leaderboard export or API was not found in this review
- best treated as market context, not canonical model telemetry

Good fit for wiki fields:

- usage trend notes
- provider popularity context
- workflow and tooling adoption summaries

References:

- https://www.vellum.ai/open-llm-leaderboard
- https://www.vellum.ai/state-of-ai-2025

## Poor Fits For Public Wiki Enrichment

### LangSmith, Helicone, Phoenix, and Braintrust

Why they do not fit:

- these tools are primarily built around private customer traces, logs, eval datasets, and internal observability
- they are useful for a company's own telemetry, not as shared public evidence across the market

Implication:

- they are good design references for analytics, tracing, topic clustering, and evaluation workflows
- they are not good default sources for enriching public entity pages

References:

- https://docs.langchain.com/langsmith/trace-with-opentelemetry
- https://docs.helicone.ai/features/hql
- https://arize.com/docs/phoenix/self-hosting/security/privacy
- https://www.braintrust.dev/docs/observe
- https://www.braintrust.dev/docs/api-reference/datasets/list-datasets

### Martian and Berri

Why they do not fit well:

- they are more about routing, gateway, or product-layer optimization than public benchmark publishing
- this review did not find strong public data feeds suitable for wiki ingestion

Implication:

- useful as product precedents
- weak as direct external evidence feeds

References:

- https://docs.withmartian.com/martian-model-router/getting-started/hello-world
- https://www.withmartian.com/model-router
- https://docs.berri.ai/introduction

## Product Rule

External source data should be stored as evidence, not truth.

Suggested external evidence fields:

- `source`
- `source_type`
- `source_url`
- `metric_name`
- `metric_value`
- `task`
- `modality`
- `captured_at`
- `license_or_terms_note`

## Implementation Guidance

Use external sources to enrich wiki pages with:

- benchmark snapshots
- pricing and latency metadata
- preference leaderboard evidence
- provider and modality context

Do not let external scores overwrite what the community is saying on StopTheSlop.

The durable product asset is still:

- the entity
- the linked community signals
- the extracted claims
- the source-backed evidence bundle
