# Web Discovery and Ingestion Sources

Last reviewed: 2026-03-26

## Why This Note Exists

StopTheSlop should eventually ingest outside reports and conversations from the web, not just wait for direct user submissions.

This note tracks which web sources are realistic first-class inputs for that system.

The emphasis here is not benchmark metadata.

The emphasis is:

- real complaints
- praise
- comparisons
- usage notes
- discussions about AI tools, models, services, and generated content

## Core Recommendation

Do not start with a generic crawler.

Start with source-specific adapters that ingest from official APIs or feed-like endpoints, then normalize the results into a shared candidate format.

Recommended order:

1. GitHub Issues, Issue Comments, and Discussions
2. Reddit
3. Hacker News
4. Bluesky
5. Stack Exchange
6. Mastodon
7. YouTube

## First-Wave Sources

### GitHub

Why it is strong:

- high-signal reports from engineers
- issues are often concrete and reproducible
- excellent fit for AI coding tools, SDKs, agents, frameworks, and browser extensions

Best use cases:

- product failures
- regressions
- tool comparisons
- workaround discovery
- long-running reliability complaints

What to ingest:

- issues
- issue comments
- Discussions where available

Why it should be first:

- high quality
- official APIs
- strong attribution
- lower noise than open social feeds

References:

- https://docs.github.com/en/rest/issues
- https://docs.github.com/en/rest/issues/comments
- https://docs.github.com/en/graphql/guides/using-the-graphql-api-for-discussions
- https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api

### Reddit

Why it is strong:

- huge volume of exactly the kind of “this model sucks lately” and “I use X for Y” conversation StopTheSlop wants to capture
- subreddit structure makes topic targeting easy

Best use cases:

- public sentiment
- recurring pain points
- comparison chatter
- organic praise and complaints

Constraint:

- policy and rate-limit posture matters more here than with some other sources
- use the official API, not brittle HTML scraping

Important notes from the official materials reviewed:

- Reddit documents official API access
- Reddit states free OAuth access is 100 queries per minute
- Reddit also notes commercial or excess usage may require a separate agreement

References:

- https://www.reddit.com/dev/api/
- https://redditinc.com/news/apifacts
- https://redditinc.com/policies/data-api-terms

### Hacker News

Why it is strong:

- high-signal product discussion
- launch backlash
- benchmark skepticism
- thoughtful comparison threads

Best use cases:

- AI product launches
- reliability backlash
- developer reactions
- “Ask HN” style usage and comparison prompts

Why it is attractive:

- official public API
- simple data model
- relatively low integration friction

Reference:

- https://github.com/HackerNews/API

### Bluesky

Why it is strong:

- fast-moving model chatter
- useful for emerging releases and sentiment shifts
- good fit for casual comparisons and reactions

Best use cases:

- new-model buzz
- short-form praise or complaints
- what people are saying right now

Reference:

- https://docs.bsky.app/
- https://docs.bsky.app/docs/api/app-bsky-feed-search-posts

## Second-Wave Sources

### Stack Exchange / Stack Overflow

Why it is useful:

- strong fit for technical failures and practical usage questions
- better for engineering evidence than emotional venting

Best use cases:

- reproducible implementation problems
- API misuse confusion
- prompt/system design problems

Constraint:

- less culturally aligned with the rant or praise side of StopTheSlop
- still very useful for technical signal

Reference:

- https://api.stackexchange.com/docs

### Mastodon

Why it is useful:

- federated public posts
- can surface discussion outside the main commercial social networks

Why it is second-wave:

- search quality varies by instance
- full-text search is not uniformly available

Reference:

- https://docs.joinmastodon.org/methods/search/
- https://docs.joinmastodon.org/api/rate-limits/

### YouTube

Why it is useful:

- reviews
- reaction videos
- benchmark and launch commentary

Why it is later:

- search quota is relatively expensive
- harder to extract precise atomic claims from long video content

Reference:

- https://developers.google.com/youtube/v3/docs/search/list

## What To Avoid At First

- generic web crawling across arbitrary domains
- scraping sites that already have official APIs
- ingesting raw full-text content when excerpt plus attribution is enough
- auto-publishing crawled content straight to the public board

## Recommended System Shape

Build source adapters, not one giant crawler.

Examples:

- `github-adapter`
- `reddit-adapter`
- `hn-adapter`
- `bluesky-adapter`

Each adapter should output a normalized candidate record with fields like:

- `source`
- `source_item_id`
- `url`
- `title`
- `body_excerpt`
- `author_name`
- `published_at`
- `engagement_counts`
- `entity_hints`
- `crawl_confidence`

## Processing Pipeline

1. Discover candidate items from a source adapter.
2. Deduplicate on source ID, canonical URL, and content hash.
3. Run relevance classification.
4. Run entity linking and claim extraction.
5. Decide whether to stage, auto-publish, or discard.
6. Feed approved results into the existing import and enrichment pipeline.

## Product Rule

Crawled content should enter the system as sourced evidence, not as silent truth.

Good default posture:

- retain source attribution
- keep canonical links
- store excerpts instead of copying full pages when possible
- prefer moderation or staging for lower-confidence imports

## Practical Next Step

The first implementation should not be “crawl the web.”

It should be:

1. GitHub adapter
2. Reddit adapter
3. Hacker News adapter
4. staging queue
5. AI relevance and entity-linking pass

That gets StopTheSlop useful outside signal quickly without overbuilding a crawler.
