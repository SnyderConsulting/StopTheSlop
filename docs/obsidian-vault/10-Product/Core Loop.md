# Core Loop

## Primary Loop

1. A user shares something about AI through the universal composer.
2. The system moderates the submission, stores the source privately, and extracts graph signals.
3. The user receives a grounded AI reply and stays in an ongoing conversation thread.
4. Entities, claims, guides, questions, answers, and clusters update from the latest evidence.
5. Public surfaces refresh from graph state instead of publishing the raw source.
6. Later submissions corroborate, contest, or deepen what the graph already believes.

## User Experience Goals

- the composer should be obvious and usable in seconds
- one entry point should handle submitting, asking, and exploring
- every submission should produce a useful grounded response
- the public product should feel active through synthesized graph artifacts
- every entity or cluster page should answer:
  - what are people saying
  - what evidence supports it
  - what is still contested or emerging

## Submission Design

The intake should start unstructured and let the system do the structuring later.

The composer should accept:

- freeform text
- URLs
- images
- PDFs
- audio
- video
- mixed submissions that combine any of the above

## Reading Experience

The public product should support three common behaviors:

- seeing what claims or topics are hot right now
- opening entity pages, guides, questions, and clusters derived from the graph
- asking follow-up questions in the same conversation surface instead of switching to dedicated search

## Publication Model

- raw user submissions stay private by default
- public surfaces are graph-derived
- provenance should remain available through citations, evidence cards, or support summaries
- disagreement should remain visible through competing claims and support signals

## Anti-Goals

- no mandatory structured ticket form
- no public raw-post feed as the main product
- no separate search product that competes with the composer
- no obligation to flatten conflicting evidence into one answer too early
