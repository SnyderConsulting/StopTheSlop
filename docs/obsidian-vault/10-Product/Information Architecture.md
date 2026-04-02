# Information Architecture

## Source Of Truth

- private source records and private conversation threads are the ingestion layer
- public surfaces are derived graph objects
- provenance links the two layers together

## Core Objects

### Source

The private record of what was submitted or fetched.

Suggested fields:

- `id`
- `conversation_id`
- `kind`
- `submitter_id` or `anonymous_key`
- `blob_location`
- `extracted_text`
- `extracted_metadata`
- `source_url`
- `moderation_status`
- `redaction_status`
- `submitted_at`
- `visibility`

### Conversation

The private running thread between the user and the system.

Suggested fields:

- `id`
- `user_id` or `anonymous_key`
- `message_ids`
- `source_ids`
- `latest_ai_reply`
- `grounded_source_ids`
- `created_at`
- `updated_at`

### Entity

The stable canonical object for a tool, model, vendor, framework, dataset, concept, or other tracked subject.

Suggested fields:

- `id`
- `canonical_name`
- `entity_type`
- `aliases`
- `vendor`
- `summary`
- `source_links`
- `related_entity_ids`
- `embedding`
- `latest_evidence_at`
- `support_stats`

### Claim

A source-annotated statement linked to one or more entities or topics.

Suggested fields:

- `id`
- `subject_entity_ids`
- `claim_text`
- `claim_type`
- `polarity`
- `source_ids`
- `support_count`
- `oppose_count`
- `freshness_score`
- `confidence`
- `status`

### Guide

A synthesized artifact derived from repeated evidence.

Suggested fields:

- `id`
- `title`
- `summary`
- `related_entity_ids`
- `source_ids`
- `step_list`
- `updated_at`

### Question

A normalized question extracted from a submission or conversation.

Suggested fields:

- `id`
- `question_text`
- `related_entity_ids`
- `source_ids`
- `status`
- `updated_at`

### Answer

A grounded answer tied to a conversation, question, or public artifact.

Suggested fields:

- `id`
- `conversation_id`
- `question_id`
- `answer_text`
- `grounded_source_ids`
- `grounded_entity_ids`
- `generated_at`

### Cluster

A grouped topic or hot subject derived from graph activity.

Suggested fields:

- `id`
- `label`
- `summary`
- `entity_ids`
- `claim_ids`
- `guide_ids`
- `question_ids`
- `hotness_score`
- `updated_at`

## Publication Model

Keep these private by default:

- `source`
- `conversation`

Publish graph-derived objects:

- `entity`
- `claim`
- `guide`
- `question`
- `answer`
- `cluster`

## Relationship Guidance

- `source` supports, disputes, or enriches `claim`
- `source` may mention many `entity` objects
- `conversation` can emit `question`, `claim`, `guide`, and `answer` objects
- `claim` attaches to one or more `entity` or topic nodes
- `guide` is synthesized from many sources and claims
- `cluster` groups related entities, claims, guides, and questions
- provenance should always survive graph compaction and synthesis

## Taxonomy Guidance

Keep the user-facing intake unstructured.

Stable first-class graph objects:

- source
- conversation
- entity
- claim
- guide
- question
- answer
- cluster

Derived AI structure:

- modality
- topic
- task
- sentiment
- contradiction
- corroboration
- freshness
- trust weighting

## Why This Matters

The site needs to answer:

- what are people saying right now
- what evidence supports it
- what is still disputed
- what should a newcomer read first
- which tools, topics, and guides are rising

That is enough to make the graph useful before adding deeper research or editorial structure.
