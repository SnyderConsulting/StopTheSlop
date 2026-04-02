# Verbatim Product Requirements - 2026-04-02

This note preserves the user's exact wording from the product-pivot conversation on 2026-04-02.

Typos, punctuation, and phrasing are intentionally left unchanged.

## Pivot Request

```text
Let's rebuild it to focus on content curation in a sense. Users can post, but it's not structured like it is now with needing to choose a model and whatnot. Users just write freeform text, submit URLs, or upload image(s), with or without an account, and our system will ingest it and optionally take any of that information to append to the living graph/wiki. It's basically going to be "share something about AI" that is an open-ended conversation. Did something suck? Is this a guide? Do you have a question? Etc. Whatever you submit will give you a response grounded by the AI, effectively replacing the existing search functionality. What questions do you have?
```

## Homepage / Surface Direction

```text
1. Both. People should instantly see the "Share something about AI" with auto-suggestions in the hint like a URL, or some other tidbit, complaint, etc. Then we should be surfacing content from the community knowledge graph or "wiki" e.g., "People are saying Claude Code is the king" or "Chroma's new context model is incredible for agentic RAG", etc
```

## Operating Decisions

```text
1: Open an ongoing AI conversation, continuously feeding content to be ingested to the graph. 2: All of them together. 3: Everything should go into the graph, annotated by their sources. We could have a system to corroborate to strenghten the  sort of synapses, but whatever people put in should get stored as signals. 4: The AI system should just moderate the best it can. We'll never publish raw user submissions verbatim, instead the AI processes to the graph as it sees fit. 5: A mix, minus raw community posts. 6: Whatever we can aggregate via the AI system from the graph. The graph is basically the structured intake from all submissions. Anything for the UI would get derived from the latest graph state. So, we could do clustering to find hot subjects for example and emit those as posts/articles, etc. 7: There will no longer be dedicated search. You just type stuff, and the AI will respond accordingly whether it's a submission or a question. 8: Anything/everything, our intake will decide what do to and how/if/whether to process
```

## Delegated Judgment

```text
Use your best judgement.
```
