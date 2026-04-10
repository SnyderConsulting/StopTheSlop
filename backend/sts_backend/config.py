from __future__ import annotations

import os
from pathlib import Path


def load_dotenv_file(env_path: Path) -> None:
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        os.environ[key] = value.strip().strip("'").strip('"')


ROOT_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT_DIR.parent
WORKSPACE_ROOT = PROJECT_ROOT.parent

for candidate in (PROJECT_ROOT / ".env", WORKSPACE_ROOT / ".env"):
    load_dotenv_file(candidate)


TABLE_NAME = os.getenv("TABLE_NAME", "StopTheSlopTickets")
SOURCE_BLOB_CONTAINER = os.getenv("SOURCE_BLOB_CONTAINER", "source-ingestion")
WEB_IMPORT_USER_AGENT = "StopTheSlopBot/2.0 (+https://stoptheslop.tech)"
PERPLEXITY_SEARCH_ENDPOINT = str(
    os.getenv("PERPLEXITY_SEARCH_ENDPOINT", "https://api.perplexity.ai/search")
).strip() or "https://api.perplexity.ai/search"
SESSION_SALT = "stoptheslop-session-v2"
MAX_EXTRACTED_TEXT_CHARS = 18_000
MAX_FEED_ITEMS = 24
LIVE_WEB_CACHE_TTL_SECONDS = max(120, int(os.getenv("LIVE_WEB_CACHE_TTL_SECONDS", "900") or "900"))
DEFAULT_LIVE_WEB_FEED_QUERIES = [
    "AI slop",
    "AI hallucination complaint",
    "Claude Code issue",
    "Cursor AI complaint",
]
DEFAULT_WEB_CRAWL_QUERIES = [
    "AI slop",
    "AI-generated spam",
    "LLM hallucination complaint",
    "Claude Code issue",
    "Cursor AI complaint",
    "AI video slop",
]

PUBLIC_ENTITY_CREATION_TYPES = {
    "model",
    "product",
    "vendor",
    "service",
    "framework",
    "dataset",
    "concept",
    "company",
    "tool",
    "topic",
}

AI_TOPIC_KEYWORDS = {
    "ai",
    "artificial intelligence",
    "llm",
    "model",
    "models",
    "reasoning",
    "context",
    "prompt",
    "prompts",
    "agent",
    "agents",
    "agentic",
    "rag",
    "retrieval",
    "embedding",
    "embeddings",
    "vector",
    "search",
    "chatbot",
    "assistant",
    "copilot",
    "deepfake",
    "synthetic media",
    "slop",
    "benchmark",
    "dataset",
    "inference",
    "multimodal",
    "codegen",
    "coding",
}

QUESTION_OPENERS = (
    "how ",
    "what ",
    "why ",
    "can ",
    "should ",
    "is ",
    "are ",
    "does ",
    "do ",
    "which ",
    "could ",
)

BLOCKED_ENTITY_EXACT_NAMES = {
    "ai",
    "artificial intelligence",
    "ai content",
    "ai generated content",
    "generated content",
    "harmful ai content",
    "anti immigrant material",
    "advocacy groups",
    "human musicians",
    "public figures",
    "new users",
    "new youtube users",
}

BLOCKED_QUESTION_PREFIXES = (
    "why did ",
    "what happened to ",
    "when did ",
    "who is ",
    "who are ",
    "what actions are ",
)

BLOCKED_QUESTION_PHRASES = {
    "advocacy groups",
    "human musicians",
    "public figures",
    "new youtube users",
    "disappear from",
    "removed from",
}

BLOCKED_CLAIM_PHRASES = {
    "advocacy groups",
    "human musicians",
    "public figures",
    "new youtube users",
}

SOURCE_PARTITION_KEY = "SOURCE"
CONVERSATION_PARTITION_KEY = "CONVERSATION"
ANSWER_PARTITION_KEY = "ANSWER"
CLAIM_PARTITION_KEY = "CLAIM"
GUIDE_PARTITION_KEY = "GUIDE"
QUESTION_PARTITION_KEY = "QUESTION"
POST_PARTITION_KEY = "POST"
WEB_POST_PARTITION_KEY = "WEBPOST"
CRAWL_RUN_PARTITION_KEY = "CRAWLRUN"
ENTITY_PARTITION_KEY = "ENTITY"
USER_PARTITION_KEY = "USER"
META_PARTITION_KEY = "META"
LEGACY_TICKET_PARTITION_KEY = "TICKET"
ONBOARDING_PARTITION_KEY = "ONBOARDING"
REACTION_PARTITION_PREFIX = "REACTION"
COMMENT_PARTITION_PREFIX = "COMMENT"
THREAD_ITEM_PARTITION_KEY = "THREADITEM"

ENTITY_TYPE_OPTIONS = {
    "model",
    "product",
    "vendor",
    "service",
    "framework",
    "dataset",
    "concept",
    "company",
    "content",
    "tool",
    "topic",
    "other",
}
CLAIM_TYPE_OPTIONS = {
    "good_for",
    "bad_at",
    "used_for",
    "guide",
    "trend",
    "comparison",
    "observation",
    "question",
}
STANCE_OPTIONS = {"positive", "negative", "neutral", "mixed"}
MODERATION_ACTIONS = {"allow", "redact", "reject"}
QUESTION_STATUS_OPTIONS = {"open", "answered"}
PUBLIC_ITEM_KINDS = {"claim", "guide", "question", "cluster", "entity"}
ONBOARDING_USE_CASE_OPTIONS = {
    "coding",
    "research",
    "writing",
    "media",
    "ops",
    "other",
}

TOOL_FAMILY_METADATA = {
    "chatgpt": {
        "canonicalName": "ChatGPT",
        "entityType": "product",
        "vendor": "OpenAI",
        "officialUrl": "https://chatgpt.com/",
    },
    "claude": {
        "canonicalName": "Claude",
        "entityType": "product",
        "vendor": "Anthropic",
        "officialUrl": "https://claude.ai/",
    },
    "claude-code": {
        "canonicalName": "Claude Code",
        "entityType": "product",
        "vendor": "Anthropic",
        "officialUrl": "https://www.anthropic.com/claude-code",
    },
    "gemini": {
        "canonicalName": "Gemini",
        "entityType": "product",
        "vendor": "Google",
        "officialUrl": "https://gemini.google.com/",
    },
    "copilot": {
        "canonicalName": "GitHub Copilot",
        "entityType": "product",
        "vendor": "GitHub",
        "officialUrl": "https://github.com/features/copilot",
    },
    "cursor": {
        "canonicalName": "Cursor",
        "entityType": "product",
        "vendor": "Anysphere",
        "officialUrl": "https://www.cursor.com/",
    },
    "windsurf": {
        "canonicalName": "Windsurf",
        "entityType": "product",
        "vendor": "Codeium",
        "officialUrl": "https://windsurf.com/",
    },
    "perplexity": {
        "canonicalName": "Perplexity",
        "entityType": "product",
        "vendor": "Perplexity",
        "officialUrl": "https://www.perplexity.ai/",
    },
    "chroma": {
        "canonicalName": "Chroma",
        "entityType": "service",
        "vendor": "Chroma",
        "officialUrl": "https://www.trychroma.com/",
    },
}

INTAKE_SCHEMA = {
    "name": "sts_intake_extraction",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "moderation_action": {"type": "string"},
            "moderation_reason": {"type": "string"},
            "conversation_title": {"type": "string"},
            "query_text": {"type": "string"},
            "summary": {"type": "string"},
            "entities": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "canonical_name": {"type": "string"},
                        "entity_type": {"type": "string"},
                        "vendor": {"type": "string"},
                        "official_url": {"type": "string"},
                        "aliases": {"type": "array", "items": {"type": "string"}},
                        "summary": {"type": "string"},
                    },
                    "required": [
                        "canonical_name",
                        "entity_type",
                        "vendor",
                        "official_url",
                        "aliases",
                        "summary",
                    ],
                },
            },
            "claims": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "subject_names": {"type": "array", "items": {"type": "string"}},
                        "claim_text": {"type": "string"},
                        "claim_type": {"type": "string"},
                        "stance": {"type": "string"},
                        "tags": {"type": "array", "items": {"type": "string"}},
                        "confidence": {"type": "number"},
                    },
                    "required": [
                        "subject_names",
                        "claim_text",
                        "claim_type",
                        "stance",
                        "tags",
                        "confidence",
                    ],
                },
            },
            "guides": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "title": {"type": "string"},
                        "summary": {"type": "string"},
                        "steps": {"type": "array", "items": {"type": "string"}},
                        "subject_names": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["title", "summary", "steps", "subject_names"],
                },
            },
            "questions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "question_text": {"type": "string"},
                        "subject_names": {"type": "array", "items": {"type": "string"}},
                        "status": {"type": "string"},
                    },
                    "required": ["question_text", "subject_names", "status"],
                },
            },
        },
        "required": [
            "moderation_action",
            "moderation_reason",
            "conversation_title",
            "query_text",
            "summary",
            "entities",
            "claims",
            "guides",
            "questions",
        ],
    },
}

REPLY_SCHEMA = {
    "name": "sts_grounded_reply",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "reply": {"type": "string"},
            "followups": {"type": "array", "items": {"type": "string"}},
            "answer_title": {"type": "string"},
        },
        "required": ["reply", "followups", "answer_title"],
    },
}

WEB_POST_SCHEMA = {
    "name": "sts_web_post",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "title": {"type": "string"},
            "summary": {"type": "string"},
            "body": {"type": "string"},
            "angle": {"type": "string"},
            "source_type": {"type": "string"},
            "media_caption": {"type": "string"},
            "tags": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["title", "summary", "body", "angle", "source_type", "media_caption", "tags"],
    },
}
