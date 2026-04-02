#!/usr/bin/env python3

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

import backend.server as sts

AUTHOR_ID = "seed-web-intake"
AUTHOR_NAME = "Web Intake"
AUTHOR_EMAIL = "web-intake@stoptheslop.tech"

SEEDS = [
    {
        "title": "OpenClaw shines when it owns the whole GitHub workflow",
        "summary": "OpenClaw gets people excited when it behaves like a real workflow manager: one prompt, many GitHub issues, PRs, review loops, and a Slack ping when everything is green.",
        "context": "Seeded from Cory LaNou's February 9, 2026 demo video showing OpenClaw take 10 GitHub issues from prompt to green PRs with Codex review loops and Slack notification.",
        "experienceType": "praise",
        "sentiment": "positive",
        "rating": 5,
        "modality": "agent",
        "surface": "youtube",
        "toolFamily": "other",
        "toolDetail": "OpenClaw",
        "preferredEntityName": "OpenClaw",
        "preferredEntityType": "product",
        "preferredEntityVendor": "OpenClaw",
        "preferredOfficialUrl": "https://github.com/openclaw/openclaw",
        "expected": "Owning the GitHub workflow from issue intake through PR review and Slack notification",
        "referenceUrl": "https://www.youtube.com/watch?v=VS9gvP0HsJQ",
        "tags": ["web-seed", "youtube", "workflow-automation", "github"],
    },
    {
        "title": "OpenClaw update reports turned some agents into chat-only bots",
        "summary": "Recent OpenClaw regressions left some users saying the agent lost exec, read, and write tools and collapsed into a chat-only assistant, which defeats the whole point of using it for automation.",
        "context": "Seeded from GitHub issue #34810 opened March 4, 2026. The report says OpenClaw suddenly stopped creating files, running commands, or deploying code and started replying with manual instructions instead.",
        "experienceType": "issue",
        "sentiment": "negative",
        "rating": 1,
        "modality": "agent",
        "surface": "github-issue",
        "toolFamily": "other",
        "toolDetail": "OpenClaw",
        "preferredEntityName": "OpenClaw",
        "preferredEntityType": "product",
        "preferredEntityVendor": "OpenClaw",
        "preferredOfficialUrl": "https://github.com/openclaw/openclaw",
        "expected": "Reliable exec, read, and write access after updates",
        "referenceUrl": "https://github.com/openclaw/openclaw/issues/34810",
        "tags": ["web-seed", "github", "regression", "automation"],
    },
    {
        "title": "Codex CLI going native resonates more than the model hype",
        "summary": "A lot of the Codex CLI optimism is really about the harness getting cleaner: people want the native binary, no Node requirement, better distribution, and a more serious sandbox story.",
        "context": "Seeded from the OpenAI GitHub discussion 'Codex CLI is Going Native' posted May 30, 2025, plus user replies that specifically praised zero-dependency install and the cleaner native binary distribution story.",
        "experienceType": "usage",
        "sentiment": "positive",
        "rating": 4,
        "modality": "agent",
        "surface": "github-discussion",
        "toolFamily": "other",
        "toolDetail": "Codex CLI",
        "preferredEntityName": "Codex CLI",
        "preferredEntityType": "product",
        "preferredEntityVendor": "OpenAI",
        "preferredOfficialUrl": "https://github.com/openai/codex",
        "expected": "Portable coding agent install with less environment friction",
        "referenceUrl": "https://github.com/openai/codex/discussions/1174",
        "tags": ["web-seed", "github", "native-rewrite", "developer-tools"],
    },
    {
        "title": "Codex CLI on Windows still gets called unusable",
        "summary": "On Windows, Codex CLI still gets called worse than Claude Code when harmless PowerShell reads trigger approval prompts over and over and break the flow of basic file inspection.",
        "context": "Seeded from GitHub issue #2860 opened August 29, 2025. The reporter explicitly says Claude Code works fine on the same Windows setup while Codex keeps asking permission for routine PowerShell operations.",
        "experienceType": "comparison",
        "sentiment": "mixed",
        "rating": 2,
        "comparisonTarget": "Claude Code",
        "modality": "agent",
        "surface": "github-issue",
        "toolFamily": "other",
        "toolDetail": "Codex CLI",
        "preferredEntityName": "Codex CLI",
        "preferredEntityType": "product",
        "preferredEntityVendor": "OpenAI",
        "preferredOfficialUrl": "https://github.com/openai/codex",
        "expected": "Harmless read commands without constant approval spam",
        "referenceUrl": "https://github.com/openai/codex/issues/2860",
        "tags": ["web-seed", "github", "windows", "permissions"],
    },
    {
        "title": "Claude Code still gets dragged for destructive overengineering",
        "summary": "Claude Code still gets roasted for destructive edits, placeholder code, file proliferation, and turning simple changes into sprawling rewrites.",
        "context": "Seeded from GitHub issue #5861 opened August 15, 2025. The report lists destructive file operations, placeholder-heavy codegen, inconsistent error handling, file clutter, and continuous scope creep.",
        "experienceType": "rant",
        "sentiment": "negative",
        "rating": 1,
        "modality": "agent",
        "surface": "github-issue",
        "toolFamily": "other",
        "toolDetail": "Claude Code",
        "preferredEntityName": "Claude Code",
        "preferredEntityType": "product",
        "preferredEntityVendor": "Anthropic",
        "preferredOfficialUrl": "https://github.com/anthropics/claude-code",
        "expected": "Surgical edits without placeholder code or destructive rewrites",
        "referenceUrl": "https://github.com/anthropics/claude-code/issues/5861",
        "tags": ["web-seed", "github", "overengineering", "trust"],
    },
    {
        "title": "Claude Code still wins people over with plan mode and skills",
        "summary": "Even when model opinions are split, a lot of developers still prefer Claude Code over Codex CLI for plan mode, skills, subagents, and better codebase adaptation during collaborative back-and-forth.",
        "context": "Seeded from Hacker News discussion around 'Claude Code on the web' on October 20, 2025, where commenters repeatedly praised plan mode, skills, subagents, and the harness feeling better for interactive work.",
        "experienceType": "comparison",
        "sentiment": "mixed",
        "rating": 4,
        "comparisonTarget": "Codex CLI",
        "modality": "agent",
        "surface": "hacker-news",
        "toolFamily": "other",
        "toolDetail": "Claude Code",
        "preferredEntityName": "Claude Code",
        "preferredEntityType": "product",
        "preferredEntityVendor": "Anthropic",
        "preferredOfficialUrl": "https://github.com/anthropics/claude-code",
        "expected": "Interactive coding with plan mode, skills, and context-friendly subagents",
        "referenceUrl": "https://news.ycombinator.com/item?id=45647166",
        "tags": ["web-seed", "hacker-news", "workflow", "plan-mode"],
    },
    {
        "title": "Kimi K2.5 has a real fanbase for developer workflows",
        "summary": "Kimi K2.5 keeps getting recommended for developer environments because it is strong at tool calling, structured extraction, and strict output formats when it sits inside a coding harness.",
        "context": "Seeded from Adam Holter's July 19, 2025 review saying Kimi is excellent for developer environments, especially tool calling, extraction, and format following in agentic coding contexts.",
        "experienceType": "praise",
        "sentiment": "positive",
        "rating": 5,
        "modality": "text",
        "surface": "blog",
        "toolFamily": "other",
        "toolDetail": "Kimi K2.5",
        "preferredEntityName": "Kimi K2.5",
        "preferredEntityType": "model",
        "preferredEntityVendor": "Moonshot AI",
        "preferredOfficialUrl": "https://kimi.ai/",
        "expected": "Coding agents, tool calling, structured extraction, and strict output formats",
        "referenceUrl": "https://adam.holter.com/kimi-ai-the-weird-model-thats-perfect-for-developer-environments-but-terrible-for-content/",
        "tags": ["web-seed", "blog", "coding", "tool-calling"],
    },
    {
        "title": "Kimi K2.5 still gets knocked for content hallucinations",
        "summary": "The flip side on Kimi K2.5 is that people say it can be terrible for general content work: it goes off-script, invents sections that were never in the source, and burns way more tokens than expected.",
        "context": "Seeded from Adam Holter's July 19, 2025 review, which says Kimi is impressive in technical environments but unreliable for broader content generation because it hallucinates and drifts off source material.",
        "experienceType": "issue",
        "sentiment": "negative",
        "rating": 1,
        "modality": "text",
        "surface": "blog",
        "toolFamily": "other",
        "toolDetail": "Kimi K2.5",
        "preferredEntityName": "Kimi K2.5",
        "preferredEntityType": "model",
        "preferredEntityVendor": "Moonshot AI",
        "preferredOfficialUrl": "https://kimi.ai/",
        "expected": "Content generation that stays grounded in the provided source material",
        "referenceUrl": "https://adam.holter.com/kimi-ai-the-weird-model-thats-perfect-for-developer-environments-but-terrible-for-content/",
        "tags": ["web-seed", "blog", "hallucinations", "content-generation"],
    },
    {
        "title": "Qwen3.5-35B-A3B feels strong for self-hosted coding",
        "summary": "Qwen3.5-35B-A3B is getting real praise for self-hosted coding because it handles well-defined tasks, writes sane tests, and feels unusually capable for its size.",
        "context": "Seeded from Hacker News discussion on March 4, 2026 around Qwen3.5-35B-A3B, where commenters praised it as a very capable agentic coding model for its size on well-defined tasks.",
        "experienceType": "praise",
        "sentiment": "positive",
        "rating": 4,
        "modality": "text",
        "surface": "hacker-news",
        "toolFamily": "other",
        "toolDetail": "Qwen3.5-35B-A3B",
        "preferredEntityName": "Qwen3.5-35B-A3B",
        "preferredEntityType": "model",
        "preferredEntityVendor": "Alibaba Qwen",
        "preferredOfficialUrl": "https://qwenlm.github.io/",
        "expected": "Self-hosted coding on well-defined tasks with good test and compiler loops",
        "referenceUrl": "https://news.ycombinator.com/item?id=47249343",
        "tags": ["web-seed", "hacker-news", "self-hosted", "coding"],
    },
    {
        "title": "Qwen3.5 can still drift into hacky shortcuts",
        "summary": "The recurring complaint about Qwen3.5 in agentic loops is that it follows detailed instructions for a while, then decides a hacky shortcut is simpler and wanders off the requested path.",
        "context": "Seeded from the same Hacker News thread on March 4, 2026. Multiple commenters said Qwen follows strict instructions for a few iterations and then strips infrastructure or heads toward a dead-end shortcut.",
        "experienceType": "issue",
        "sentiment": "negative",
        "rating": 2,
        "modality": "text",
        "surface": "hacker-news",
        "toolFamily": "other",
        "toolDetail": "Qwen3.5-35B-A3B",
        "preferredEntityName": "Qwen3.5-35B-A3B",
        "preferredEntityType": "model",
        "preferredEntityVendor": "Alibaba Qwen",
        "preferredOfficialUrl": "https://qwenlm.github.io/",
        "expected": "Strict instruction following all the way through a longer agentic loop",
        "referenceUrl": "https://news.ycombinator.com/item?id=47249343",
        "tags": ["web-seed", "hacker-news", "instruction-following", "agentic-coding"],
    },
]


def build_seed_key(seed: dict[str, str]) -> tuple[str, str]:
    return (
        sts.read_text(seed.get("referenceUrl"), 300),
        sts.read_text(seed.get("summary"), 500),
    )


def existing_seed_keys() -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    for row in sts.list_ticket_rows():
        keys.add(
            (
                sts.read_text(row.get("referenceUrl"), 300),
                sts.read_text(row.get("summary"), 500),
            )
        )
    return keys


def ensure_seed_user() -> None:
    sts.upsert_user_record(
        {
            "id": AUTHOR_ID,
            "email": AUTHOR_EMAIL,
            "displayName": AUTHOR_NAME,
            "pictureUrl": "",
            "emailVerified": False,
            "provider": "seed",
        }
    )


def create_ticket(seed: dict[str, str]) -> dict[str, object]:
    payload = {
        **seed,
        "authorUserId": AUTHOR_ID,
        "authorDisplayName": AUTHOR_NAME,
        "authorPictureUrl": "",
        "reporter": AUTHOR_NAME,
    }
    ticket = sts.build_ticket_payload(payload, allow_ai=True, allow_search=True)
    sts.get_table_client().create_entity(sts.ticket_to_entity(ticket))
    return ticket


def main() -> int:
    if not os.getenv("AZURE_STORAGE_CONNECTION_STRING") and not os.getenv("STORAGE_ACCOUNT_NAME"):
        print("Set AZURE_STORAGE_CONNECTION_STRING or STORAGE_ACCOUNT_NAME.", file=sys.stderr)
        return 1

    ensure_seed_user()
    existing = existing_seed_keys()
    inserted: list[dict[str, object]] = []

    for seed in SEEDS:
        key = build_seed_key(seed)
        if key in existing:
            print(f"skip {seed['title']}")
            continue
        ticket = create_ticket(seed)
        inserted.append(ticket)
        existing.add(key)
        print(f"created {ticket['id']} -> {ticket['title']}")
        time.sleep(0.35)

    entity_ids = sts.dedupe_texts(
        [
            entity_id
            for ticket in inserted
            for entity_id in [
                sts.read_text(ticket.get("primaryEntityId"), 120),
                *(ticket.get("linkedEntityIds", []) or []),
            ]
            if sts.read_text(entity_id, 120)
        ],
        limit=64,
    )

    for entity_id in entity_ids:
        try:
            sts.rebuild_entity(entity_id, allow_ai=True, sync_search=True)
            print(f"rebuilt {entity_id}")
        except Exception:
            sts.rebuild_entity(entity_id, allow_ai=False, sync_search=False)
            print(f"rebuilt {entity_id} (fallback)")
        time.sleep(0.35)

    print(f"inserted={len(inserted)} entities={len(entity_ids)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
