# Search, Retrieval, and Cluster View

## Search Strategy

Use hybrid retrieval rather than pure vector search.

Reason:

- keyword search is better for exact tool, model, or vendor names
- vector search is better for semantically similar complaints
- both are needed for this archive

## Search Inputs

Search should be able to rank across:

- issue title
- issue summary
- synced Discord comments
- AI-generated tags
- tool and modality metadata

## Related Issues

Every issue page should have a related issues module driven by embeddings.

The initial user value is simple:

- "people who hit this also hit these"

This is the smallest useful AI feature and should come before a full cluster map.

## Cluster View

The cluster view is a higher-level archive browser.

Each cluster should show:

- cluster label
- short cluster summary
- top tools and models mentioned
- top modalities
- example issues
- recent activity
- discussion volume over time

## How Clusters Should Be Generated

Short term:

- nearest-neighbor similarity only

Medium term:

- periodic clustering over issue embeddings
- LLM-generated labels for each cluster
- merge or split logic when clusters become too broad

## Ask-The-Archive

This should be a retrieval-first feature, not a freeform chatbot.

Example questions:

- what coding agents are people most frustrated with
- what workarounds are users sharing for context loss
- what repeated complaints exist for website chatbots

The answer should:

- retrieve relevant issues and comments
- synthesize a short response
- link back to the source issues

## UI Notes

- search should remain visible from the board
- related issues belongs on the issue detail view
- cluster pages should feel like browsable categories, not latent-space art projects
- citations matter more than eloquence
