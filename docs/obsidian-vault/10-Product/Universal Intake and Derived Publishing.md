# Universal Intake and Derived Publishing

## Decision Summary

See also: [[Verbatim Product Requirements - 2026-04-02]]

- StopTheSlop is no longer organized around structured issue tickets or model-first intake.
- The primary interface is a universal multimodal composer with the prompt `Share something about AI`.
- Users can submit freeform text, URLs, images, PDFs, audio, video, or any combination of those inputs.
- Every submission opens or continues an AI conversation.
- The assistant grounds on submitted material, the internal graph/wiki, and the live web together.
- Raw user submissions are not published verbatim.
- Public surfaces are derived from graph state.
- All accepted submissions are stored as source-annotated signals in the graph immediately.
- Corroboration and opposition strengthen or weaken relationships over time, but disagreement is preserved instead of collapsed away early.
- Dedicated search is removed. Asking, submitting, and exploring all happen through the composer.

## Product Statement

StopTheSlop becomes an AI-native curation and synthesis system for `anything about AI`.

People can share what sucked, what worked, a guide, a question, a benchmark, a screenshot, a thread, a clip, or a useful link. The system ingests that material, responds in context, and updates a living graph that powers every public surface.

## Public And Private Boundary

- `source` and `conversation` objects are private by default.
- Public surfaces are derived artifacts such as claims, guides, entity pages, question summaries, answers, and clusters.
- The site publishes the latest graph state, not a raw feed of community posts.
- Provenance remains attached internally and should be exposed through citations or evidence summaries where useful.

## Interaction Model

- The home page opens with the universal composer.
- Submission and Q&A use the same entry point.
- After submit, the user lands in an ongoing AI conversation thread.
- The reply should explain what it found, answer the user, and optionally note what was added or updated in the graph.
- The old dedicated search page is retired. Search intent is handled through the conversation experience.

## Graph Write Policy

- Everything accepted by moderation becomes a stored signal.
- Signals write into the graph immediately with source annotations.
- The graph preserves competing claims when sources disagree.
- Corroboration strengthens relationships over time through support counts, freshness, confidence, and trust weighting.
- Live web evidence may enter the graph, but it should carry different trust defaults than first-party submissions.

## V1 Graph Objects

- `source`
- `conversation`
- `entity`
- `claim`
- `guide`
- `question`
- `answer`
- `cluster`

## Moderation And Safety Defaults

- Anonymous submission is allowed.
- AI moderation should block or heavily redact doxxing, credentials, private documents, explicit abuse content, and clearly unsafe material.
- Raw source artifacts may be retained privately for audit, provenance, and regeneration, with redaction when needed.
- Public output should only contain sanitized derived content.

## Accounts And Identity

- Anonymous users can submit immediately behind rate limits, CAPTCHA, and AI moderation.
- Anonymous users receive a signed manage link.
- Accounts unlock saved history, edit/delete rights, higher limits, subscriptions, and moderation trust.

## Feed Composition

- The main feed is a derived mix of hot claims, rising entities, fresh guides, unanswered questions, grounded answers, and emerging clusters.
- The UI should not default to raw user posts.
- Home and wiki surfaces should be generated from the latest graph state.

## Migration Decision

- Existing tickets and entities should be migrated into the new graph as seed evidence rather than discarded.

## Non-Goals

- no mandatory structured ticket form
- no dedicated search page
- no public raw-post feed as the main product
- no collapsing disagreement into a single claim too early
