# Precedents - Smart Wikis and Entity Pages

## Why These Matter

The Omni Wiki should borrow proven patterns instead of inventing a totally novel knowledge system.

## Semantic MediaWiki

Relevant idea:

- a wiki can also function as a collaborative database with semantic annotations and queryable data

Takeaway for StopTheSlop:

- pages should carry structured data, not just prose
- form-based contribution and faceted browsing matter

Reference:

- https://www.semantic-mediawiki.org/wiki/Main_Page
- https://www.semantic-mediawiki.org/wiki/Help:Introduction_to_Semantic_MediaWiki

## Wikibase and Wikidata

Relevant idea:

- entities should be represented as structured items with labels, aliases, statements, qualifiers, and references

Takeaway for StopTheSlop:

- the Omni Page should be a view over an entity-and-claims model
- aliases and references are first-class
- statements are more durable than generated summaries

Reference:

- https://www.mediawiki.org/wiki/Extension:Wikibase
- https://www.wikidata.org/wiki/Wikidata:Data_model

## Google Knowledge Graph

Relevant idea:

- entity lookup, autocomplete, and content annotation are core primitives

Takeaway for StopTheSlop:

- typeahead and auto-linking should be built into posting flows
- canonical entities should be searchable by aliases and ranked candidates

Constraint:

- external entity APIs should not be the production-critical dependency for the product

Reference:

- https://developers.google.com/knowledge-graph

## Perplexity Pages

Relevant idea:

- search and research can be transformed into shareable generated pages

Takeaway for StopTheSlop:

- generated page views can be useful
- generated pages should sit on top of source retrieval and citations
- generation alone is not a durable knowledge model

Reference:

- https://www.perplexity.ai/help-center/en/articles/10352968-perplexity-pages
- https://www.perplexity.ai/es/hub/blog/perplexity-pages

## Open Research Knowledge Graph

Relevant idea:

- move from document blobs to machine-readable claims and comparisons

Takeaway for StopTheSlop:

- comparisons between tools should be structured
- `good for`, `bad for`, and `used for` claims should be queryable

Reference:

- https://eosc.eu/use-case/open-research-knowledge-graph

## Synthesis

The best design direction is:

- Wikibase-style entity and claim model
- Semantic MediaWiki-style structured contribution and querying
- Google Knowledge Graph-style entity lookup and autocomplete
- Perplexity-style generated page view
- ORKG-style comparative claims

This combination is much stronger than building a plain wiki with an LLM bolted on top.
