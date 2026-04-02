# StopTheSlop Vault

This vault is the working product and platform notebook for StopTheSlop.

## Current Product Thesis

StopTheSlop is a universal intake and curation system for `anything about AI`.

People can share a complaint, guide, question, benchmark, screenshot, URL, clip, or general observation. The system ingests the material, responds in an ongoing AI conversation, and updates a living graph that powers public knowledge surfaces.

The website is not a raw social feed, a support desk, or a vendor escalation workflow.

The core loop is:

1. Someone shares text, URLs, or files through the universal composer.
2. AI moderates the submission, stores the source privately, extracts graph signals, and updates provenance.
3. The user receives an ongoing grounded AI conversation.
4. Public surfaces refresh from the latest graph state.
5. Later submissions corroborate, contest, or deepen existing claims and clusters.

## Maps

- [[10-Product/Product Vision]]
- [[10-Product/Core Loop]]
- [[10-Product/Information Architecture]]
- [[10-Product/Universal Intake and Derived Publishing]]
- [[10-Product/Verbatim Product Requirements - 2026-04-02]]
- [[10-Product/Omni Wiki]]
- [[20-AI/AI Enrichment Strategy]]
- [[20-AI/Entity Resolution and Source Fusion]]
- [[20-AI/Public Enrichment Sources]]
- [[20-AI/Web Discovery and Ingestion Sources]]
- [[20-AI/Precedents - Smart Wikis and Entity Pages]]
- [[20-AI/Search, Retrieval, and Cluster View]]
- [[30-Platform/System Architecture]]
- [[30-Platform/Omni Wiki Architecture]]
- [[40-Roadmap/Roadmap]]
- [[40-Roadmap/Canny Feedback Intake]]
- [[40-Roadmap/Open Questions]]

## Current Design Decisions

- The universal composer is the primary product surface.
- Submission, asking, and discovery are unified into one AI conversation flow.
- Public content is derived from the graph, not from raw user posts.
- Raw sources and conversations are private by default.
- Every accepted submission becomes a source-annotated graph signal.
- The home feed is a mix of claims, guides, questions, answers, entities, and clusters.
- AI should ground on submitted material, internal graph state, and the live web together.
- Dedicated search is being removed.
- Existing tickets and entities should be migrated as seed evidence.

## Short-Term Documentation Backlog

- graph trust and corroboration model
- moderation and redaction policy
- source provenance and citation UI
- migration plan from tickets/entities to graph objects
- storage and indexing changes for multimodal sources
