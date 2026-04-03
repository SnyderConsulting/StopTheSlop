from __future__ import annotations

import base64
import hashlib
import ipaddress
import io
import json
import mimetypes
import os
import re
import secrets
import socket
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from azure.core.exceptions import ResourceExistsError, ResourceNotFoundError
from azure.data.tables import TableServiceClient, UpdateMode
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient, ContentSettings
from bs4 import BeautifulSoup
from flask import Flask, jsonify, request
from flask_cors import CORS
from google.auth.transport import requests as google_auth_requests
from google.oauth2 import id_token as google_id_token
from itsdangerous import BadSignature, BadTimeSignature, URLSafeTimedSerializer
from werkzeug.exceptions import HTTPException

try:
    from openai import AzureOpenAI
except ImportError:  # pragma: no cover
    AzureOpenAI = None

try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover
    PdfReader = None


ROOT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT_DIR.parent
WORKSPACE_ROOT = PROJECT_ROOT.parent


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
BLOCKED_ENTITY_NAME_PATTERNS = (
    re.compile(
        r"^(new )?(users?|viewers?|people|children|kids|parents?|musicians?|artists?|journalists?|creators?|researchers?|experts?|lawmakers?|groups?|communities|public figures?)$"
    ),
    re.compile(r"^(the )?(song|songs|video|videos|article|articles|study|studies|report|reports|headline|headlines|story|stories|chart|charts)$"),
)
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
ENTITY_PARTITION_KEY = "ENTITY"
USER_PARTITION_KEY = "USER"
META_PARTITION_KEY = "META"
LEGACY_TICKET_PARTITION_KEY = "TICKET"
ONBOARDING_PARTITION_KEY = "ONBOARDING"

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

app = Flask(__name__)
app.config["JSON_SORT_KEYS"] = False

allowed_origins = [
    origin.strip()
    for origin in os.getenv("ALLOWED_ORIGINS", "").split(",")
    if origin.strip()
]
CORS(app, resources={r"/api/*": {"origins": allowed_origins or "*"}})

_table_client = None
_blob_container_client = None
_openai_client = None
_openai_checked = False
_migration_checked = False
_background_executor = ThreadPoolExecutor(
    max_workers=max(1, int(os.getenv("BACKGROUND_WORKERS", "2") or "2"))
)


def now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def read_text(value: Any, max_length: int | None = None) -> str:
    text = str(value or "").strip()
    if max_length is not None:
        text = text[:max_length]
    return text


def read_json(value: Any, default: Any):
    try:
        return json.loads(value or "")
    except Exception:
        return default


def safe_json_loads(content: str) -> dict[str, Any]:
    try:
        parsed = json.loads(content or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def dedupe_texts(items, limit: int = 12) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items or []:
        text = read_text(item, 240)
        key = text.casefold()
        if not text or key in seen:
            continue
        seen.add(key)
        result.append(text)
        if len(result) >= limit:
            break
    return result


def normalize_for_match(value: Any) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", " ", read_text(value, 300).lower()).strip()
    return re.sub(r"\s+", " ", cleaned)


def split_words(value: Any) -> list[str]:
    return [word for word in normalize_for_match(value).split() if word]


def has_ai_topic_signal(value: Any) -> bool:
    normalized = normalize_for_match(value)
    if not normalized:
        return False
    return any(keyword in normalized for keyword in AI_TOPIC_KEYWORDS)


def turn_looks_like_question(value: Any) -> bool:
    text = read_text(value, 6000)
    normalized = normalize_for_match(text)
    return "?" in text or normalized.startswith(QUESTION_OPENERS)


def is_blocked_entity_name(name: str) -> bool:
    normalized = normalize_for_match(name)
    if not normalized:
        return True
    if normalized in BLOCKED_ENTITY_EXACT_NAMES:
        return True
    return any(pattern.match(normalized) for pattern in BLOCKED_ENTITY_NAME_PATTERNS)


def should_keep_entity_candidate(
    name: str,
    entity_type: str,
    official_url: str = "",
    source_blob: str = "",
    treat_as_existing: bool = False,
) -> bool:
    normalized = normalize_for_match(name)
    words = split_words(name)
    resolved_type = read_choice(entity_type, ENTITY_TYPE_OPTIONS, "other")
    source_match = normalized and normalized in normalize_for_match(source_blob)

    if not normalized or len(words) > 6 or len(normalized) < 3:
        return False
    if is_blocked_entity_name(normalized):
        return False
    if infer_tool_family_from_name(name):
        return True
    if resolved_type not in PUBLIC_ENTITY_CREATION_TYPES:
        return False
    if resolved_type in {"concept", "topic"}:
        return (treat_as_existing or source_match) and has_ai_topic_signal(name) and len(words) <= 4
    return treat_as_existing or source_match or bool(read_text(official_url, 240))


def infer_subject_names_from_text(
    curated_entities: list[dict[str, Any]],
    text: str,
) -> list[str]:
    normalized_text = normalize_for_match(text)
    inferred: list[str] = []
    if not normalized_text:
        return inferred
    for entity in curated_entities:
        name = read_text(entity.get("canonical_name") or entity.get("canonicalName"), 120)
        normalized_name = normalize_for_match(name)
        if normalized_name and normalized_name in normalized_text:
            inferred.append(name)
    return dedupe_texts(inferred, limit=6)


def canonicalize_subject_names(
    subject_names: list[str],
    curated_entities: list[dict[str, Any]],
    fallback_text: str = "",
) -> list[str]:
    curated_index = {
        normalize_for_match(item.get("canonical_name", "")): item.get("canonical_name", "")
        for item in curated_entities
        if normalize_for_match(item.get("canonical_name", ""))
    }
    canonical_subjects: list[str] = []
    for name in dedupe_texts(subject_names, limit=6):
        existing = find_existing_entity_by_name(name)
        if existing:
            canonical_subjects.append(read_text(existing.get("canonicalName"), 120))
            continue
        normalized = normalize_for_match(name)
        if normalized in curated_index:
            canonical_subjects.append(read_text(curated_index[normalized], 120))
    if not canonical_subjects and fallback_text:
        canonical_subjects.extend(infer_subject_names_from_text(curated_entities, fallback_text))
    return dedupe_texts(canonical_subjects, limit=6)


def filter_publishable_subject_names(subject_names: list[str]) -> list[str]:
    return [
        name
        for name in dedupe_texts(subject_names, limit=8)
        if not is_blocked_entity_name(name)
    ]


def should_keep_claim_text(claim_text: str) -> bool:
    normalized = normalize_for_match(claim_text)
    words = split_words(claim_text)
    if not normalized or len(words) < 3:
        return False
    if claim_text.strip().endswith("?"):
        return False
    if normalized.startswith(("according to ", "this article ", "the article ", "the report ")):
        return False
    if any(phrase in normalized for phrase in BLOCKED_CLAIM_PHRASES):
        return False
    if re.match(r"^\d", normalized) and any(token in normalized for token in ("views", "accounts", "videos")):
        return False
    return True


def should_keep_guide(title: str, summary: str, steps: list[str], subject_names: list[str]) -> bool:
    if not subject_names:
        return False
    if len(split_words(title)) < 3:
        return False
    return bool(read_text(summary, 320) or steps[:2])


def normalize_question_text(question_text: str) -> str:
    text = read_text(question_text, 220)
    if text and not text.endswith("?"):
        text = f"{text}?"
    return text


def should_keep_question_text(
    question_text: str,
    user_turn_text: str,
    subject_names: list[str],
) -> bool:
    text = normalize_question_text(question_text)
    normalized = normalize_for_match(text)
    words = split_words(text)

    if not turn_looks_like_question(user_turn_text):
        return False
    if not normalized or len(words) < 3 or len(words) > 20:
        return False
    if normalized.startswith(BLOCKED_QUESTION_PREFIXES):
        return False
    if any(phrase in normalized for phrase in BLOCKED_QUESTION_PHRASES):
        return False
    if re.search(r"[\"“”][^\"“”]{5,}[\"“”]", text):
        return False
    if re.search(r"\b(19|20)\d{2}\b", normalized):
        return False
    if subject_names and any(is_blocked_entity_name(name) for name in subject_names):
        return False
    return bool(subject_names or has_ai_topic_signal(text))


def curate_extraction_result(
    extraction: dict[str, Any],
    user_turn_text: str,
    ingested_text: str,
) -> dict[str, Any]:
    source_blob = "\n\n".join(part for part in [user_turn_text, ingested_text] if part)
    curated_entities: list[dict[str, Any]] = []
    seen_entity_names: set[str] = set()
    for item in extraction.get("entities", []):
        canonical_name = read_text(item.get("canonical_name"), 120)
        entity_type = read_choice(item.get("entity_type"), ENTITY_TYPE_OPTIONS, "other")
        official_url = read_text(item.get("official_url"), 240)
        normalized_name = normalize_for_match(canonical_name)
        if normalized_name in seen_entity_names:
            continue
        if not should_keep_entity_candidate(canonical_name, entity_type, official_url, source_blob):
            continue
        seen_entity_names.add(normalized_name)
        curated_entities.append(
            {
                "canonical_name": canonical_name,
                "entity_type": entity_type,
                "vendor": read_text(item.get("vendor"), 120),
                "official_url": official_url,
                "aliases": dedupe_texts(item.get("aliases", []), limit=10),
                "summary": read_text(item.get("summary"), 320),
            }
        )

    curated_claims: list[dict[str, Any]] = []
    for item in extraction.get("claims", []):
        claim_text = read_text(item.get("claim_text"), 280)
        subject_names = filter_publishable_subject_names(
            canonicalize_subject_names(
                item.get("subject_names", []),
                curated_entities,
                fallback_text=claim_text,
            )
        )
        if not subject_names or not should_keep_claim_text(claim_text):
            continue
        curated_claims.append(
            {
                "subject_names": subject_names,
                "claim_text": claim_text,
                "claim_type": read_choice(item.get("claim_type"), CLAIM_TYPE_OPTIONS, "observation"),
                "stance": read_choice(item.get("stance"), STANCE_OPTIONS, "neutral"),
                "tags": dedupe_texts(item.get("tags", []), limit=8),
                "confidence": float(item.get("confidence", 0.0) or 0.0),
            }
        )

    curated_guides: list[dict[str, Any]] = []
    for item in extraction.get("guides", []):
        title = read_text(item.get("title"), 160)
        summary = read_text(item.get("summary"), 320)
        steps = dedupe_texts(item.get("steps", []), limit=8)
        subject_names = canonicalize_subject_names(
            item.get("subject_names", []),
            curated_entities,
            fallback_text=" ".join([title, summary, " ".join(steps)]),
        )
        if not should_keep_guide(title, summary, steps, subject_names):
            continue
        curated_guides.append(
            {
                "title": title,
                "summary": summary,
                "steps": steps,
                "subject_names": subject_names,
            }
        )

    curated_questions: list[dict[str, Any]] = []
    for item in extraction.get("questions", []):
        question_text = normalize_question_text(item.get("question_text"))
        subject_names = canonicalize_subject_names(
            item.get("subject_names", []),
            curated_entities,
            fallback_text=question_text,
        )
        if not should_keep_question_text(question_text, user_turn_text, subject_names):
            continue
        curated_questions.append(
            {
                "question_text": question_text,
                "subject_names": subject_names,
                "status": read_choice(item.get("status"), QUESTION_STATUS_OPTIONS, "open"),
            }
        )

    if turn_looks_like_question(user_turn_text) and not curated_questions:
        fallback_question = normalize_question_text(user_turn_text)
        fallback_subjects = infer_subject_names_from_text(curated_entities, user_turn_text)
        if should_keep_question_text(fallback_question, user_turn_text, fallback_subjects):
            curated_questions.append(
                {
                    "question_text": fallback_question,
                    "subject_names": fallback_subjects,
                    "status": "open",
                }
            )

    return {
        "moderation_action": read_choice(extraction.get("moderation_action"), MODERATION_ACTIONS, "allow"),
        "moderation_reason": read_text(extraction.get("moderation_reason"), 220),
        "conversation_title": read_text(extraction.get("conversation_title"), 120)
        or build_conversation_title(user_turn_text or ingested_text),
        "query_text": read_text(extraction.get("query_text"), 180)
        or read_text(user_turn_text, 180)
        or read_text(ingested_text, 180),
        "summary": read_text(extraction.get("summary"), 500)
        or read_text(user_turn_text, 500)
        or read_text(ingested_text, 500),
        "entities": curated_entities[:8],
        "claims": curated_claims[:12],
        "guides": curated_guides[:6],
        "questions": curated_questions[:4],
    }


def is_publishable_question_record(question: dict[str, Any]) -> bool:
    return should_keep_question_text(
        question.get("questionText", ""),
        question.get("questionText", ""),
        question.get("subjectNames", []),
    )


def is_publishable_claim_record(claim: dict[str, Any]) -> bool:
    subject_names = filter_publishable_subject_names(claim.get("subjectNames", []))
    return should_keep_claim_text(claim.get("claimText", "")) and bool(
        subject_names or has_ai_topic_signal(claim.get("claimText", ""))
    )


def is_publishable_entity_record(entity: dict[str, Any]) -> bool:
    if should_keep_entity_candidate(
        entity.get("canonicalName", ""),
        entity.get("entityType", "other"),
        entity.get("officialUrl", ""),
        source_blob=entity.get("summary", "") or entity.get("description", ""),
        treat_as_existing=True,
    ):
        return True

    name = read_text(entity.get("canonicalName"), 120)
    words = split_words(name)
    stats = entity.get("stats", {}) or {}
    total_signal = sum(
        int(stats.get(key, 0) or 0)
        for key in ("sourceCount", "claimCount", "guideCount", "questionCount")
    )
    if is_blocked_entity_name(name) or not name or len(words) > 4:
        return False
    if total_signal < 2:
        return False
    return bool(
        read_text(entity.get("officialUrl"), 240)
        or read_text(entity.get("vendor"), 120)
        or has_ai_topic_signal(name)
        or any(character.isupper() for character in name)
    )


def slugify(value: Any) -> str:
    normalized = normalize_for_match(value)
    return normalized.replace(" ", "-") or secrets.token_hex(4)


def read_choice(value: Any, allowed: set[str], fallback: str) -> str:
    choice = read_text(value, 80).lower()
    return choice if choice in allowed else fallback


def hash_token(value: str) -> str:
    return hashlib.sha256(read_text(value, 500).encode("utf-8")).hexdigest()


def build_row_key(prefix: str) -> str:
    return f"{prefix}-{secrets.token_hex(8)}"


def build_anonymous_handle(seed: str) -> str:
    digest = hashlib.sha256(f"sts-anon::{read_text(seed, 240)}".encode("utf-8")).hexdigest()[:8]
    return f"anon-{digest}"


def merge_unique(existing: list[str], incoming: list[str], limit: int = 12) -> list[str]:
    return dedupe_texts([*(existing or []), *(incoming or [])], limit=limit)


def normalize_domain(hostname: str) -> str:
    host = read_text(hostname, 240).lower().strip(".")
    if host.startswith("www."):
        host = host[4:]
    return host


def validate_public_import_url(candidate_url: str) -> str:
    parsed = urlparse(read_text(candidate_url, 2000))
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Only http:// and https:// URLs are allowed.")

    hostname = normalize_domain(parsed.hostname or "")
    if not hostname:
        raise ValueError("Enter a valid URL.")
    if hostname in {"localhost", "0.0.0.0"} or hostname.endswith(".local"):
        raise ValueError("Local and private hosts cannot be fetched.")

    try:
        address_infos = socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as error:
        raise ValueError("That URL could not be resolved.") from error

    for address_info in address_infos:
        ip_value = address_info[4][0]
        ip_obj = ipaddress.ip_address(ip_value)
        if (
            ip_obj.is_private
            or ip_obj.is_loopback
            or ip_obj.is_link_local
            or ip_obj.is_multicast
            or ip_obj.is_reserved
            or ip_obj.is_unspecified
        ):
            raise ValueError("Private network targets cannot be fetched.")

    return parsed._replace(fragment="").geturl()[:1800]


def read_meta_content(soup: BeautifulSoup, *names: str) -> str:
    for name in names:
        tag = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
        content = read_text((tag or {}).get("content", ""), 500)
        if content:
            return content
    return ""


def titleize_domain_label(domain: str) -> str:
    cleaned = normalize_domain(domain)
    root = cleaned.split(".")[0]
    return root.replace("-", " ").replace("_", " ").title() if root else "Web"


def present_import_source_label(domain: str, site_name: str = "", source_url: str = "") -> str:
    normalized_domain = normalize_domain(domain)
    mapped = {
        "x.com": "X",
        "twitter.com": "X",
        "reddit.com": "Reddit",
        "medium.com": "Medium",
        "news.ycombinator.com": "Hacker News",
        "github.com": "GitHub",
        "youtube.com": "YouTube",
        "youtu.be": "YouTube",
        "substack.com": "Substack",
        "linkedin.com": "LinkedIn",
    }
    if normalized_domain in mapped:
        return mapped[normalized_domain]

    cleaned_site_name = read_text(site_name, 120)
    parsed_url = urlparse(read_text(source_url, 1800))
    if cleaned_site_name and cleaned_site_name.lower() not in {
        normalized_domain.lower(),
        (parsed_url.hostname or "").lower(),
    }:
        return cleaned_site_name

    return titleize_domain_label(normalized_domain)


def extract_web_import_preview(source_url: str) -> dict[str, Any]:
    current_url = validate_public_import_url(source_url)
    response = None

    for _redirect_count in range(5):
        validate_public_import_url(current_url)
        response = requests.get(
            current_url,
            allow_redirects=False,
            timeout=(3.5, 7.0),
            headers={
                "User-Agent": WEB_IMPORT_USER_AGENT,
                "Accept": "text/html,application/xhtml+xml",
            },
            stream=True,
        )
        if 300 <= response.status_code < 400 and response.headers.get("Location"):
            response.close()
            current_url = urljoin(current_url, response.headers["Location"])
            continue
        break

    if response is None:
        raise ValueError("Could not fetch that page.")
    if response.status_code >= 400:
        raise ValueError(f"The source page returned {response.status_code}.")

    content_type = read_text(response.headers.get("Content-Type"), 160).lower()
    if "html" not in content_type:
        raise ValueError("Only HTML pages can be fetched from a URL right now.")

    chunks: list[bytes] = []
    bytes_read = 0
    for chunk in response.iter_content(chunk_size=16_384):
        if not chunk:
            continue
        chunks.append(chunk)
        bytes_read += len(chunk)
        if bytes_read >= 350_000:
            break
    response.close()

    html = b"".join(chunks).decode(response.encoding or "utf-8", errors="ignore")
    final_url = validate_public_import_url(response.url or current_url)
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "iframe"]):
        tag.decompose()

    title = (
        read_meta_content(soup, "og:title", "twitter:title")
        or read_text((soup.title or {}).get_text(" ", strip=True), 180)
    )
    description = read_meta_content(soup, "description", "og:description", "twitter:description")
    parsed_final = urlparse(final_url)
    domain = normalize_domain(parsed_final.hostname or "")
    body_root = soup.find("article") or soup.find("main") or soup.body or soup
    paragraphs = [
        read_text(node.get_text(" ", strip=True), 320)
        for node in body_root.find_all(["p", "li"], limit=24)
    ]
    paragraphs = [paragraph for paragraph in paragraphs if len(paragraph) >= 40]
    excerpt = read_text(" ".join(paragraphs[:5]), 1200) or description
    site_name = read_text(read_meta_content(soup, "og:site_name"), 120) or domain

    return {
        "url": final_url,
        "domain": domain,
        "title": read_text(title or domain or "Imported page", 180),
        "description": read_text(description, 320),
        "excerpt": read_text(excerpt, 1200),
        "siteName": site_name,
        "sourceLabel": present_import_source_label(domain, site_name, final_url),
    }


def build_table_service_client() -> TableServiceClient:
    connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "").strip()
    if connection_string:
        return TableServiceClient.from_connection_string(connection_string)

    storage_account_name = os.getenv("STORAGE_ACCOUNT_NAME", "").strip()
    if not storage_account_name:
        raise RuntimeError("Set AZURE_STORAGE_CONNECTION_STRING or STORAGE_ACCOUNT_NAME.")

    endpoint = f"https://{storage_account_name}.table.core.windows.net"
    credential = DefaultAzureCredential(exclude_interactive_browser_credential=True)
    return TableServiceClient(endpoint=endpoint, credential=credential)


def get_table_client():
    global _table_client
    if _table_client is None:
        _table_client = build_table_service_client().create_table_if_not_exists(TABLE_NAME)
    return _table_client


def build_blob_service_client() -> BlobServiceClient:
    connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "").strip()
    if connection_string:
        return BlobServiceClient.from_connection_string(connection_string)

    storage_account_name = os.getenv("STORAGE_ACCOUNT_NAME", "").strip()
    if not storage_account_name:
        raise RuntimeError("Set AZURE_STORAGE_CONNECTION_STRING or STORAGE_ACCOUNT_NAME.")

    endpoint = f"https://{storage_account_name}.blob.core.windows.net"
    credential = DefaultAzureCredential(exclude_interactive_browser_credential=True)
    return BlobServiceClient(account_url=endpoint, credential=credential)


def get_blob_container_client():
    global _blob_container_client
    if _blob_container_client is None:
        service_client = build_blob_service_client()
        client = service_client.get_container_client(SOURCE_BLOB_CONTAINER)
        try:
            client.create_container()
        except ResourceExistsError:
            pass
        _blob_container_client = client
    return _blob_container_client


def get_openai_client():
    global _openai_client, _openai_checked
    if _openai_checked:
        return _openai_client

    _openai_checked = True
    endpoint = read_text(os.getenv("AZURE_OPENAI_ENDPOINT"), 200)
    api_key = read_text(os.getenv("AZURE_OPENAI_API_KEY"), 300)
    api_version = read_text(os.getenv("AZURE_OPENAI_API_VERSION"), 40) or "2024-10-21"
    if not endpoint or not api_key or AzureOpenAI is None:
        _openai_client = None
        return None

    _openai_client = AzureOpenAI(
        azure_endpoint=endpoint,
        api_key=api_key,
        api_version=api_version,
        max_retries=0,
        timeout=float(os.getenv("AZURE_OPENAI_TIMEOUT_SECONDS", "9.0") or 9.0),
    )
    return _openai_client


def can_use_ai() -> bool:
    return get_openai_client() is not None and bool(
        read_text(os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT"), 120)
    )


def can_use_perplexity_search() -> bool:
    return bool(read_text(os.getenv("PERPLEXITY_API_KEY"), 400))


def auth_is_enabled() -> bool:
    return bool(
        read_text(os.getenv("GOOGLE_CLIENT_ID"), 200)
        and read_text(os.getenv("AUTH_SESSION_SECRET"), 200)
    )


def get_google_client_id() -> str:
    return read_text(os.getenv("GOOGLE_CLIENT_ID"), 200)


def get_session_serializer() -> URLSafeTimedSerializer | None:
    secret = read_text(os.getenv("AUTH_SESSION_SECRET"), 200)
    if not secret:
        return None
    return URLSafeTimedSerializer(secret_key=secret, salt=SESSION_SALT)


def user_record_to_table(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "PartitionKey": USER_PARTITION_KEY,
        "RowKey": user["id"],
        "email": user.get("email", ""),
        "displayName": user.get("displayName", ""),
        "pictureUrl": user.get("pictureUrl", ""),
        "emailVerified": bool(user.get("emailVerified", False)),
        "provider": user.get("provider", "google"),
        "createdAt": user.get("createdAt", now_iso()),
        "updatedAt": user.get("updatedAt", now_iso()),
        "lastLoginAt": user.get("lastLoginAt", now_iso()),
    }


def table_to_user_record(entity: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": entity["RowKey"],
        "email": entity.get("email", ""),
        "displayName": entity.get("displayName", ""),
        "pictureUrl": entity.get("pictureUrl", ""),
        "emailVerified": bool(entity.get("emailVerified", False)),
        "provider": entity.get("provider", "google"),
        "createdAt": entity.get("createdAt", now_iso()),
        "updatedAt": entity.get("updatedAt", now_iso()),
        "lastLoginAt": entity.get("lastLoginAt", now_iso()),
    }


def get_user_record(user_id: str):
    try:
        entity = get_table_client().get_entity(partition_key=USER_PARTITION_KEY, row_key=user_id)
    except ResourceNotFoundError:
        return None
    return table_to_user_record(entity)


def build_public_user(user: dict[str, Any]) -> dict[str, Any]:
    user_id = read_text(user.get("id"), 120)
    public_handle = build_anonymous_handle(user_id) if user_id else "anon-user"
    return {
        "id": user_id,
        "displayName": public_handle,
        "publicHandle": public_handle,
        "pictureUrl": "",
    }


def verify_google_credential(credential: str) -> dict[str, Any]:
    client_id = get_google_client_id()
    if not client_id:
        raise ValueError("Google sign-in is not configured.")

    try:
        payload = google_id_token.verify_oauth2_token(
            credential,
            google_auth_requests.Request(),
            client_id,
        )
    except ValueError as error:
        raise ValueError("Google sign-in failed. Try again.") from error

    user_id = read_text(payload.get("sub"), 120)
    email = read_text(payload.get("email"), 200)
    display_name = read_text(payload.get("name"), 120) or email or "Google user"
    if not user_id or not email:
        raise ValueError("Google sign-in did not return a usable account.")

    existing = get_user_record(user_id)
    now = now_iso()
    record = {
        **(existing or {}),
        "id": user_id,
        "email": email,
        "displayName": display_name,
        "pictureUrl": read_text(payload.get("picture"), 300),
        "emailVerified": bool(payload.get("email_verified")),
        "provider": "google",
        "createdAt": (existing or {}).get("createdAt", now),
        "updatedAt": now,
        "lastLoginAt": now,
    }
    get_table_client().upsert_entity(mode=UpdateMode.REPLACE, entity=user_record_to_table(record))
    return record


def issue_session_token(user: dict[str, Any]) -> str:
    serializer = get_session_serializer()
    if serializer is None:
        raise RuntimeError("Authentication is not configured.")
    return serializer.dumps(build_public_user(user))


def decode_session_token(token: str, max_age_seconds: int = 60 * 60 * 24 * 30) -> dict[str, Any] | None:
    serializer = get_session_serializer()
    if serializer is None or not token:
        return None
    try:
        data = serializer.loads(token, max_age=max_age_seconds)
    except (BadSignature, BadTimeSignature):
        return None
    return get_user_record(read_text(data.get("id"), 120))


def read_bearer_token() -> str:
    header = read_text(request.headers.get("Authorization"), 500)
    if not header.startswith("Bearer "):
        return ""
    return read_text(header[7:], 500)


def get_authenticated_user() -> dict[str, Any] | None:
    return decode_session_token(read_bearer_token())


def list_rows(partition_key: str) -> list[dict[str, Any]]:
    query = f"PartitionKey eq '{partition_key}'"
    return list(get_table_client().query_entities(query_filter=query))


def get_row(partition_key: str, row_key: str) -> dict[str, Any] | None:
    try:
        return get_table_client().get_entity(partition_key=partition_key, row_key=row_key)
    except ResourceNotFoundError:
        return None


def upsert_row(entity: dict[str, Any]) -> None:
    get_table_client().upsert_entity(mode=UpdateMode.REPLACE, entity=entity)


def read_request_ip() -> str:
    for candidate in (
        request.headers.get("CF-Connecting-IP"),
        request.headers.get("X-Forwarded-For"),
        request.remote_addr,
    ):
        value = read_text(candidate, 160)
        if not value:
            continue
        return read_text(value.split(",", 1)[0], 120)
    return ""


def onboarding_record_to_table(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "PartitionKey": ONBOARDING_PARTITION_KEY,
        "RowKey": record["visitorId"],
        "surveyVersion": record.get("surveyVersion", "20260403a"),
        "aiUseCase": record.get("aiUseCase", ""),
        "slopMeaning": record.get("slopMeaning", ""),
        "desiredProduct": record.get("desiredProduct", ""),
        "entryPath": record.get("entryPath", ""),
        "referrer": record.get("referrer", ""),
        "userId": record.get("userId", ""),
        "clientIpHash": record.get("clientIpHash", ""),
        "userAgent": record.get("userAgent", ""),
        "createdAt": record.get("createdAt", now_iso()),
        "updatedAt": record.get("updatedAt", now_iso()),
    }


def persist_onboarding_response() -> dict[str, Any]:
    payload = request.get_json(silent=True) or {}
    visitor_id = read_text(payload.get("visitorId"), 120)
    ai_use_case = read_choice(payload.get("aiUseCase"), ONBOARDING_USE_CASE_OPTIONS, "")
    slop_meaning = read_text(payload.get("slopMeaning"), 2400)
    desired_product = read_text(payload.get("desiredProduct"), 2400)
    entry_path = read_text(payload.get("entryPath"), 200)
    referrer = read_text(payload.get("referrer"), 500)
    survey_version = read_text(payload.get("surveyVersion"), 40) or "20260403a"
    user = get_authenticated_user()
    client_ip = read_request_ip()

    if not visitor_id:
        raise ValueError("Missing visitor id.")
    if not ai_use_case:
        raise ValueError("Choose how you mostly use AI.")
    if len(slop_meaning) < 16:
        raise ValueError('Explain what "AI slop" means to you in a bit more detail.')
    if len(desired_product) < 16:
        raise ValueError("Explain what you would want from Stop The Slop in a bit more detail.")

    existing = get_row(ONBOARDING_PARTITION_KEY, visitor_id) or {}
    now = now_iso()
    record = {
        "visitorId": visitor_id,
        "surveyVersion": survey_version,
        "aiUseCase": ai_use_case,
        "slopMeaning": slop_meaning,
        "desiredProduct": desired_product,
        "entryPath": entry_path,
        "referrer": referrer,
        "userId": read_text((user or {}).get("id"), 120),
        "clientIpHash": hash_token(client_ip) if client_ip else "",
        "userAgent": read_text(request.headers.get("User-Agent"), 280),
        "createdAt": existing.get("createdAt", now),
        "updatedAt": now,
    }
    upsert_row(onboarding_record_to_table(record))
    return {
        "ok": True,
        "visitorId": visitor_id,
        "surveyVersion": survey_version,
        "completedAt": now,
    }


def build_entity_description(canonical_name: str, entity_type: str, vendor: str) -> str:
    subject = canonical_name or "This AI entity"
    if vendor:
        return f"{subject} is a tracked {entity_type} from {vendor}."
    return f"{subject} is a tracked AI {entity_type}."


def build_entity_source_links(entity: dict[str, Any]) -> dict[str, str]:
    canonical_name = entity.get("canonicalName", "")
    query = canonical_name or entity.get("vendor", "") or entity.get("id", "")
    return {
        "officialUrl": read_text(entity.get("officialUrl"), 200),
        "webSearchUrl": f"https://www.google.com/search?q={query.replace(' ', '+')}",
        "redditSearchUrl": f"https://www.reddit.com/search/?q={query.replace(' ', '%20')}",
    }


def entity_record_to_table(entity: dict[str, Any]) -> dict[str, Any]:
    return {
        "PartitionKey": ENTITY_PARTITION_KEY,
        "RowKey": entity["id"],
        "canonicalName": entity["canonicalName"],
        "entityType": entity.get("entityType", "other"),
        "toolFamily": entity.get("toolFamily", ""),
        "vendor": entity.get("vendor", ""),
        "description": entity.get("description", ""),
        "summary": entity.get("summary", ""),
        "aliasesJson": json.dumps(entity.get("aliases", [])),
        "goodForJson": json.dumps(entity.get("goodFor", [])),
        "badAtJson": json.dumps(entity.get("badAt", [])),
        "usedForJson": json.dumps(entity.get("usedFor", [])),
        "betterThanJson": json.dumps(entity.get("betterThan", [])),
        "worseThanJson": json.dumps(entity.get("worseThan", [])),
        "officialUrl": entity.get("officialUrl", ""),
        "sentiment": entity.get("sentiment", "mixed"),
        "ratingAverage": float(entity.get("ratingAverage", 0.0) or 0.0),
        "topTagsJson": json.dumps(entity.get("topTags", [])),
        "topModalitiesJson": json.dumps(entity.get("topModalities", [])),
        "topSurfacesJson": json.dumps(entity.get("topSurfaces", [])),
        "experienceMixJson": json.dumps(entity.get("experienceMix", {})),
        "latestTicketsJson": json.dumps(entity.get("latestTickets", [])),
        "statsJson": json.dumps(entity.get("stats", {})),
        "createdAt": entity.get("createdAt", now_iso()),
        "updatedAt": entity.get("updatedAt", now_iso()),
    }


def table_to_entity_record(entity: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": entity["RowKey"],
        "canonicalName": entity.get("canonicalName", ""),
        "entityType": entity.get("entityType", "other"),
        "toolFamily": entity.get("toolFamily", ""),
        "vendor": entity.get("vendor", ""),
        "description": entity.get("description", ""),
        "summary": entity.get("summary", ""),
        "aliases": read_json(entity.get("aliasesJson", "[]"), []),
        "goodFor": read_json(entity.get("goodForJson", "[]"), []),
        "badAt": read_json(entity.get("badAtJson", "[]"), []),
        "usedFor": read_json(entity.get("usedForJson", "[]"), []),
        "betterThan": read_json(entity.get("betterThanJson", "[]"), []),
        "worseThan": read_json(entity.get("worseThanJson", "[]"), []),
        "officialUrl": entity.get("officialUrl", ""),
        "sentiment": entity.get("sentiment", "mixed"),
        "ratingAverage": float(entity.get("ratingAverage", 0.0) or 0.0),
        "topTags": read_json(entity.get("topTagsJson", "[]"), []),
        "topModalities": read_json(entity.get("topModalitiesJson", "[]"), []),
        "topSurfaces": read_json(entity.get("topSurfacesJson", "[]"), []),
        "experienceMix": read_json(entity.get("experienceMixJson", "{}"), {}),
        "latestTickets": read_json(entity.get("latestTicketsJson", "[]"), []),
        "stats": read_json(entity.get("statsJson", "{}"), {}),
        "createdAt": entity.get("createdAt", now_iso()),
        "updatedAt": entity.get("updatedAt", now_iso()),
    }


def source_record_to_table(source: dict[str, Any]) -> dict[str, Any]:
    return {
        "PartitionKey": SOURCE_PARTITION_KEY,
        "RowKey": source["id"],
        "conversationId": source.get("conversationId", ""),
        "kind": source.get("kind", "text"),
        "submitterId": source.get("submitterId", ""),
        "anonymousHandle": source.get("anonymousHandle", ""),
        "blobPath": source.get("blobPath", ""),
        "sourceUrl": source.get("sourceUrl", ""),
        "filename": source.get("filename", ""),
        "contentType": source.get("contentType", ""),
        "extractedText": source.get("extractedText", ""),
        "summary": source.get("summary", ""),
        "moderationStatus": source.get("moderationStatus", "accepted"),
        "redactionNotesJson": json.dumps(source.get("redactionNotes", [])),
        "visibility": source.get("visibility", "private"),
        "createdAt": source.get("createdAt", now_iso()),
    }


def table_to_source_record(entity: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": entity["RowKey"],
        "conversationId": entity.get("conversationId", ""),
        "kind": entity.get("kind", "text"),
        "submitterId": entity.get("submitterId", ""),
        "anonymousHandle": entity.get("anonymousHandle", ""),
        "blobPath": entity.get("blobPath", ""),
        "sourceUrl": entity.get("sourceUrl", ""),
        "filename": entity.get("filename", ""),
        "contentType": entity.get("contentType", ""),
        "extractedText": entity.get("extractedText", ""),
        "summary": entity.get("summary", ""),
        "moderationStatus": entity.get("moderationStatus", "accepted"),
        "redactionNotes": read_json(entity.get("redactionNotesJson", "[]"), []),
        "visibility": entity.get("visibility", "private"),
        "createdAt": entity.get("createdAt", now_iso()),
    }


def conversation_record_to_table(conversation: dict[str, Any]) -> dict[str, Any]:
    return {
        "PartitionKey": CONVERSATION_PARTITION_KEY,
        "RowKey": conversation["id"],
        "title": conversation.get("title", ""),
        "submitterId": conversation.get("submitterId", ""),
        "anonymousHandle": conversation.get("anonymousHandle", ""),
        "manageTokenHash": conversation.get("manageTokenHash", ""),
        "sourceIdsJson": json.dumps(conversation.get("sourceIds", [])),
        "groundedEntityIdsJson": json.dumps(conversation.get("groundedEntityIds", [])),
        "latestReplySummary": conversation.get("latestReplySummary", ""),
        "createdAt": conversation.get("createdAt", now_iso()),
        "updatedAt": conversation.get("updatedAt", now_iso()),
    }


def table_to_conversation_record(entity: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": entity["RowKey"],
        "title": entity.get("title", ""),
        "submitterId": entity.get("submitterId", ""),
        "anonymousHandle": entity.get("anonymousHandle", ""),
        "manageTokenHash": entity.get("manageTokenHash", ""),
        "sourceIds": read_json(entity.get("sourceIdsJson", "[]"), []),
        "groundedEntityIds": read_json(entity.get("groundedEntityIdsJson", "[]"), []),
        "latestReplySummary": entity.get("latestReplySummary", ""),
        "createdAt": entity.get("createdAt", now_iso()),
        "updatedAt": entity.get("updatedAt", now_iso()),
    }


def message_partition_key(conversation_id: str) -> str:
    return f"MESSAGE-{conversation_id}"


def message_record_to_table(message: dict[str, Any]) -> dict[str, Any]:
    return {
        "PartitionKey": message_partition_key(message["conversationId"]),
        "RowKey": message["id"],
        "conversationId": message["conversationId"],
        "role": message.get("role", "assistant"),
        "text": message.get("text", ""),
        "sourceIdsJson": json.dumps(message.get("sourceIds", [])),
        "groundedEntityIdsJson": json.dumps(message.get("groundedEntityIds", [])),
        "citationsJson": json.dumps(message.get("citations", [])),
        "graphUpdatesJson": json.dumps(message.get("graphUpdates", [])),
        "createdAt": message.get("createdAt", now_iso()),
    }


def table_to_message_record(entity: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": entity["RowKey"],
        "conversationId": entity.get("conversationId", ""),
        "role": entity.get("role", "assistant"),
        "text": entity.get("text", ""),
        "sourceIds": read_json(entity.get("sourceIdsJson", "[]"), []),
        "groundedEntityIds": read_json(entity.get("groundedEntityIdsJson", "[]"), []),
        "citations": read_json(entity.get("citationsJson", "[]"), []),
        "graphUpdates": read_json(entity.get("graphUpdatesJson", "[]"), []),
        "createdAt": entity.get("createdAt", now_iso()),
    }


def claim_record_to_table(claim: dict[str, Any]) -> dict[str, Any]:
    return {
        "PartitionKey": CLAIM_PARTITION_KEY,
        "RowKey": claim["id"],
        "subjectEntityIdsJson": json.dumps(claim.get("subjectEntityIds", [])),
        "subjectNamesJson": json.dumps(claim.get("subjectNames", [])),
        "claimText": claim.get("claimText", ""),
        "claimType": claim.get("claimType", "observation"),
        "stance": claim.get("stance", "neutral"),
        "tagsJson": json.dumps(claim.get("tags", [])),
        "sourceIdsJson": json.dumps(claim.get("sourceIds", [])),
        "supportCount": int(claim.get("supportCount", 1)),
        "opposeCount": int(claim.get("opposeCount", 0)),
        "confidence": float(claim.get("confidence", 0.0) or 0.0),
        "createdAt": claim.get("createdAt", now_iso()),
        "updatedAt": claim.get("updatedAt", now_iso()),
    }


def table_to_claim_record(entity: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": entity["RowKey"],
        "subjectEntityIds": read_json(entity.get("subjectEntityIdsJson", "[]"), []),
        "subjectNames": read_json(entity.get("subjectNamesJson", "[]"), []),
        "claimText": entity.get("claimText", ""),
        "claimType": entity.get("claimType", "observation"),
        "stance": entity.get("stance", "neutral"),
        "tags": read_json(entity.get("tagsJson", "[]"), []),
        "sourceIds": read_json(entity.get("sourceIdsJson", "[]"), []),
        "supportCount": int(entity.get("supportCount", 1)),
        "opposeCount": int(entity.get("opposeCount", 0)),
        "confidence": float(entity.get("confidence", 0.0) or 0.0),
        "createdAt": entity.get("createdAt", now_iso()),
        "updatedAt": entity.get("updatedAt", now_iso()),
    }


def guide_record_to_table(guide: dict[str, Any]) -> dict[str, Any]:
    return {
        "PartitionKey": GUIDE_PARTITION_KEY,
        "RowKey": guide["id"],
        "title": guide.get("title", ""),
        "summary": guide.get("summary", ""),
        "stepsJson": json.dumps(guide.get("steps", [])),
        "subjectEntityIdsJson": json.dumps(guide.get("subjectEntityIds", [])),
        "subjectNamesJson": json.dumps(guide.get("subjectNames", [])),
        "sourceIdsJson": json.dumps(guide.get("sourceIds", [])),
        "createdAt": guide.get("createdAt", now_iso()),
        "updatedAt": guide.get("updatedAt", now_iso()),
    }


def table_to_guide_record(entity: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": entity["RowKey"],
        "title": entity.get("title", ""),
        "summary": entity.get("summary", ""),
        "steps": read_json(entity.get("stepsJson", "[]"), []),
        "subjectEntityIds": read_json(entity.get("subjectEntityIdsJson", "[]"), []),
        "subjectNames": read_json(entity.get("subjectNamesJson", "[]"), []),
        "sourceIds": read_json(entity.get("sourceIdsJson", "[]"), []),
        "createdAt": entity.get("createdAt", now_iso()),
        "updatedAt": entity.get("updatedAt", now_iso()),
    }


def question_record_to_table(question: dict[str, Any]) -> dict[str, Any]:
    return {
        "PartitionKey": QUESTION_PARTITION_KEY,
        "RowKey": question["id"],
        "questionText": question.get("questionText", ""),
        "subjectEntityIdsJson": json.dumps(question.get("subjectEntityIds", [])),
        "subjectNamesJson": json.dumps(question.get("subjectNames", [])),
        "sourceIdsJson": json.dumps(question.get("sourceIds", [])),
        "status": question.get("status", "open"),
        "createdAt": question.get("createdAt", now_iso()),
        "updatedAt": question.get("updatedAt", now_iso()),
    }


def table_to_question_record(entity: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": entity["RowKey"],
        "questionText": entity.get("questionText", ""),
        "subjectEntityIds": read_json(entity.get("subjectEntityIdsJson", "[]"), []),
        "subjectNames": read_json(entity.get("subjectNamesJson", "[]"), []),
        "sourceIds": read_json(entity.get("sourceIdsJson", "[]"), []),
        "status": entity.get("status", "open"),
        "createdAt": entity.get("createdAt", now_iso()),
        "updatedAt": entity.get("updatedAt", now_iso()),
    }


def answer_record_to_table(answer: dict[str, Any]) -> dict[str, Any]:
    return {
        "PartitionKey": ANSWER_PARTITION_KEY,
        "RowKey": answer["id"],
        "conversationId": answer.get("conversationId", ""),
        "title": answer.get("title", ""),
        "answerText": answer.get("answerText", ""),
        "questionId": answer.get("questionId", ""),
        "groundedSourceIdsJson": json.dumps(answer.get("groundedSourceIds", [])),
        "groundedEntityIdsJson": json.dumps(answer.get("groundedEntityIds", [])),
        "createdAt": answer.get("createdAt", now_iso()),
    }


def infer_tool_family_from_name(name: str) -> str:
    normalized = normalize_for_match(name)
    for tool_family, metadata in TOOL_FAMILY_METADATA.items():
        if normalize_for_match(metadata.get("canonicalName", "")) == normalized:
            return tool_family
        if normalized and normalized in normalize_for_match(metadata.get("canonicalName", "")):
            return tool_family
    return ""


def infer_entity_record_from_name(name: str, entity_type: str = "other", vendor: str = "") -> dict[str, Any]:
    canonical_name = read_text(name, 120)
    tool_family = infer_tool_family_from_name(canonical_name)
    metadata = TOOL_FAMILY_METADATA.get(tool_family, {})
    resolved_type = read_choice(
        entity_type,
        ENTITY_TYPE_OPTIONS,
        read_text(metadata.get("entityType"), 40) or "other",
    )
    resolved_vendor = read_text(vendor, 120) or read_text(metadata.get("vendor"), 120)
    official_url = read_text(metadata.get("officialUrl"), 240)
    return {
        "id": f"omni-{slugify(canonical_name)}",
        "canonicalName": read_text(metadata.get("canonicalName"), 120) or canonical_name,
        "entityType": resolved_type,
        "toolFamily": tool_family,
        "vendor": resolved_vendor,
        "description": build_entity_description(canonical_name, resolved_type, resolved_vendor),
        "summary": "",
        "aliases": dedupe_texts([canonical_name, metadata.get("canonicalName", "")], limit=12),
        "goodFor": [],
        "badAt": [],
        "usedFor": [],
        "betterThan": [],
        "worseThan": [],
        "officialUrl": official_url,
        "sentiment": "mixed",
        "ratingAverage": 0.0,
        "topTags": [],
        "topModalities": [],
        "topSurfaces": [],
        "experienceMix": {},
        "latestTickets": [],
        "stats": {"sourceCount": 0, "claimCount": 0, "guideCount": 0, "questionCount": 0},
        "createdAt": now_iso(),
        "updatedAt": now_iso(),
    }


def list_entity_rows() -> list[dict[str, Any]]:
    return list_rows(ENTITY_PARTITION_KEY)


def list_entities() -> list[dict[str, Any]]:
    entities = [table_to_entity_record(row) for row in list_entity_rows()]
    for entity in entities:
        entity["sourceLinks"] = build_entity_source_links(entity)
    return sorted(
        entities,
        key=lambda item: (
            -int((item.get("stats") or {}).get("sourceCount", 0)),
            item.get("canonicalName", "").lower(),
        ),
    )


def get_entity_record(entity_id: str):
    row = get_row(ENTITY_PARTITION_KEY, entity_id)
    if not row:
        return None
    entity = table_to_entity_record(row)
    entity["sourceLinks"] = build_entity_source_links(entity)
    return entity


def find_existing_entity_by_name(name: str) -> dict[str, Any] | None:
    normalized = normalize_for_match(name)
    if not normalized:
        return None
    for entity in list_entities():
        labels = [entity.get("canonicalName", ""), *(entity.get("aliases", []) or [])]
        if normalized in {normalize_for_match(label) for label in labels if normalize_for_match(label)}:
            return entity
    return None


def merge_entity_records(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    stats = existing.get("stats", {}) or {}
    incoming_stats = incoming.get("stats", {}) or {}
    return {
        **existing,
        **incoming,
        "id": existing["id"],
        "canonicalName": existing.get("canonicalName") or incoming.get("canonicalName", ""),
        "entityType": existing.get("entityType") or incoming.get("entityType", "other"),
        "toolFamily": existing.get("toolFamily") or incoming.get("toolFamily", ""),
        "vendor": existing.get("vendor") or incoming.get("vendor", ""),
        "description": existing.get("description") or incoming.get("description", ""),
        "summary": existing.get("summary") or incoming.get("summary", ""),
        "aliases": merge_unique(existing.get("aliases", []), incoming.get("aliases", []), limit=14),
        "goodFor": merge_unique(existing.get("goodFor", []), incoming.get("goodFor", []), limit=10),
        "badAt": merge_unique(existing.get("badAt", []), incoming.get("badAt", []), limit=10),
        "usedFor": merge_unique(existing.get("usedFor", []), incoming.get("usedFor", []), limit=10),
        "betterThan": merge_unique(existing.get("betterThan", []), incoming.get("betterThan", []), limit=8),
        "worseThan": merge_unique(existing.get("worseThan", []), incoming.get("worseThan", []), limit=8),
        "officialUrl": existing.get("officialUrl") or incoming.get("officialUrl", ""),
        "topTags": merge_unique(existing.get("topTags", []), incoming.get("topTags", []), limit=14),
        "topModalities": merge_unique(existing.get("topModalities", []), incoming.get("topModalities", []), limit=8),
        "topSurfaces": merge_unique(existing.get("topSurfaces", []), incoming.get("topSurfaces", []), limit=8),
        "stats": {
            "sourceCount": int(stats.get("sourceCount", 0)) + int(incoming_stats.get("sourceCount", 0)),
            "claimCount": int(stats.get("claimCount", 0)) + int(incoming_stats.get("claimCount", 0)),
            "guideCount": int(stats.get("guideCount", 0)) + int(incoming_stats.get("guideCount", 0)),
            "questionCount": int(stats.get("questionCount", 0)) + int(incoming_stats.get("questionCount", 0)),
        },
        "updatedAt": now_iso(),
    }


def upsert_entity_record(entity: dict[str, Any]) -> dict[str, Any]:
    existing = get_entity_record(entity["id"]) or find_existing_entity_by_name(entity.get("canonicalName", ""))
    merged = merge_entity_records(existing, entity) if existing else entity
    merged["updatedAt"] = now_iso()
    merged.setdefault("createdAt", now_iso())
    upsert_row(entity_record_to_table(merged))
    merged["sourceLinks"] = build_entity_source_links(merged)
    return merged


def parse_urls(raw_value: str) -> list[str]:
    urls: list[str] = []
    for match in re.finditer(r"https?://[^\s<>'\")]+", read_text(raw_value, 6000)):
        candidate = read_text(match.group(0), 1800).rstrip(".,;:!?])}")
        if candidate.startswith(("http://", "https://")):
            urls.append(candidate)
    return dedupe_texts(urls, limit=10)


def upload_blob_bytes(blob_path: str, payload: bytes, content_type: str) -> None:
    client = get_blob_container_client().get_blob_client(blob_path)
    client.upload_blob(
        payload,
        overwrite=True,
        content_settings=ContentSettings(content_type=content_type or "application/octet-stream"),
    )


def extract_pdf_text(payload: bytes) -> str:
    if PdfReader is None:
        return ""
    try:
        reader = PdfReader(io.BytesIO(payload))
        text_parts = []
        for page in reader.pages[:12]:
            page_text = read_text(page.extract_text(), 4000)
            if page_text:
                text_parts.append(page_text)
        return read_text("\n\n".join(text_parts), MAX_EXTRACTED_TEXT_CHARS)
    except Exception:
        return ""


def extract_image_text(filename: str, content_type: str, payload: bytes) -> str:
    if not can_use_ai():
        return ""
    client = get_openai_client()
    deployment = read_text(os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT"), 120)
    if client is None or not deployment:
        return ""

    data_url = f"data:{content_type};base64,{base64.b64encode(payload).decode('ascii')}"
    try:
        response = client.chat.completions.create(
            model=deployment,
            temperature=0.1,
            max_tokens=300,
            messages=[
                {
                    "role": "system",
                    "content": "Describe the uploaded image in plain English and extract any legible text. Keep it concise and factual.",
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": f"Filename: {filename}"},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                },
            ],
        )
        return read_text(
            response.choices[0].message.content if response.choices else "",
            2500,
        )
    except Exception:
        return ""


def extract_file_summary(filename: str, content_type: str, payload: bytes) -> tuple[str, str]:
    content_type = read_text(content_type, 120) or mimetypes.guess_type(filename)[0] or "application/octet-stream"
    summary = f"Uploaded file {filename} ({content_type})."

    if content_type.startswith("text/"):
        text = payload.decode("utf-8", errors="ignore")
        return read_text(text, MAX_EXTRACTED_TEXT_CHARS), summary
    if content_type == "application/pdf":
        extracted = extract_pdf_text(payload)
        return extracted, summary
    if content_type.startswith("image/"):
        extracted = extract_image_text(filename, content_type, payload)
        return extracted, summary
    return "", summary


def create_source_record(
    conversation_id: str,
    submitter_id: str,
    anonymous_handle: str,
    kind: str,
    extracted_text: str,
    summary: str,
    *,
    source_url: str = "",
    filename: str = "",
    content_type: str = "",
    blob_path: str = "",
    moderation_status: str = "accepted",
    created_at: str | None = None,
    source_id: str | None = None,
) -> dict[str, Any]:
    record = {
        "id": source_id or build_row_key("src"),
        "conversationId": conversation_id,
        "kind": kind,
        "submitterId": submitter_id,
        "anonymousHandle": anonymous_handle,
        "blobPath": blob_path,
        "sourceUrl": source_url,
        "filename": filename,
        "contentType": content_type,
        "extractedText": read_text(extracted_text, MAX_EXTRACTED_TEXT_CHARS),
        "summary": read_text(summary, 600),
        "moderationStatus": moderation_status,
        "redactionNotes": [],
        "visibility": "private",
        "createdAt": created_at or now_iso(),
    }
    upsert_row(source_record_to_table(record))
    return record


def build_actor_context() -> tuple[str, str, dict[str, Any] | None]:
    user = get_authenticated_user()
    if user:
        return read_text(user.get("id"), 120), build_public_user(user)["publicHandle"], user

    anonymous_seed = (
        read_text(request.headers.get("CF-Connecting-IP"), 120)
        or read_text(request.headers.get("X-Forwarded-For"), 120)
        or read_text(request.remote_addr, 120)
        or secrets.token_hex(6)
    )
    return "", build_anonymous_handle(anonymous_seed), None


def build_conversation_title(text: str) -> str:
    words = read_text(text, 140).split()
    if not words:
        return "AI conversation"
    return read_text(" ".join(words[:10]), 80)


def call_ai_json(messages: list[dict[str, Any]], schema: dict[str, Any], max_tokens: int = 800) -> dict[str, Any]:
    client = get_openai_client()
    deployment = read_text(os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT"), 120)
    if client is None or not deployment:
        return {}
    try:
        response = client.chat.completions.create(
            model=deployment,
            messages=messages,
            response_format={"type": "json_schema", "json_schema": schema},
            temperature=0.2,
            max_tokens=max_tokens,
        )
        content = response.choices[0].message.content if response.choices else "{}"
        return safe_json_loads(content or "{}")
    except Exception:
        app.logger.exception("AI JSON call failed")
        return {}


def extract_submission_signals(
    user_turn_text: str,
    ingested_text: str,
    source_previews: list[dict[str, Any]],
    recent_messages: list[dict[str, Any]],
) -> dict[str, Any]:
    normalized_preview = [
        {
            "kind": source.get("kind", ""),
            "summary": read_text(source.get("summary"), 400),
            "sourceUrl": read_text(source.get("sourceUrl"), 300),
            "filename": read_text(source.get("filename"), 160),
            "extractedText": read_text(source.get("extractedText"), 3000),
        }
        for source in source_previews[:8]
    ]

    fallback = {
        "moderation_action": "allow",
        "moderation_reason": "",
        "conversation_title": build_conversation_title(user_turn_text or ingested_text),
        "query_text": read_text(user_turn_text, 160) or read_text(ingested_text, 160),
        "summary": read_text(user_turn_text, 500) or read_text(ingested_text, 500),
        "entities": [],
        "claims": [],
        "guides": [],
        "questions": [],
    }

    if not can_use_ai():
        if turn_looks_like_question(user_turn_text):
            fallback["questions"] = [
                {
                    "question_text": normalize_question_text(user_turn_text),
                    "subject_names": [],
                    "status": "open",
                }
            ]
        elif user_turn_text or ingested_text:
            fallback["claims"] = [
                {
                    "subject_names": [],
                    "claim_text": read_text(user_turn_text or ingested_text, 260),
                    "claim_type": "observation",
                    "stance": "neutral",
                    "tags": [],
                    "confidence": 0.25,
                }
            ]
        return curate_extraction_result(fallback, user_turn_text, ingested_text)

    messages = [
        {
            "role": "system",
            "content": (
                "You are ingesting multimodal community submissions about AI tools, models, products, and workflows. "
                "Moderate the content first. The raw submission will remain private, but public graph artifacts may be derived from it. "
                "Reject doxxing, credentials, private documents, and clearly abusive or unsafe material. "
                "If the submission is acceptable but contains sensitive details, choose redact. "
                "Then extract only durable public knowledge grounded strictly in the supplied material. "
                "Prefer concise claims, reusable guides, and broad user questions over one-off article trivia. "
                "Only create entities for meaningful AI products, models, companies, tools, or durable AI topics. "
                "Do not create entities for generic actor groups, song titles, article subjects, or ephemeral people. "
                "Only return questions if the user is actually asking one and the question is reusable beyond this single source. "
                "When in doubt, return fewer entities and fewer questions."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "userTurnText": read_text(user_turn_text, 4000),
                    "ingestedText": read_text(ingested_text, 6000),
                    "sourcePreviews": normalized_preview,
                    "recentMessages": [
                        {"role": item.get("role", ""), "text": read_text(item.get("text"), 1000)}
                        for item in recent_messages[-6:]
                    ],
                },
                ensure_ascii=True,
            ),
        },
    ]
    data = call_ai_json(messages, INTAKE_SCHEMA, max_tokens=1400)
    if not data:
        return curate_extraction_result(fallback, user_turn_text, ingested_text)

    normalized = {
        "moderation_action": read_choice(data.get("moderation_action"), MODERATION_ACTIONS, "allow"),
        "moderation_reason": read_text(data.get("moderation_reason"), 220),
        "conversation_title": read_text(data.get("conversation_title"), 120) or fallback["conversation_title"],
        "query_text": read_text(data.get("query_text"), 180) or fallback["query_text"],
        "summary": read_text(data.get("summary"), 500) or fallback["summary"],
        "entities": [
            {
                "canonical_name": read_text(item.get("canonical_name"), 120),
                "entity_type": read_choice(item.get("entity_type"), ENTITY_TYPE_OPTIONS, "other"),
                "vendor": read_text(item.get("vendor"), 120),
                "official_url": read_text(item.get("official_url"), 240),
                "aliases": dedupe_texts(item.get("aliases", []), limit=10),
                "summary": read_text(item.get("summary"), 320),
            }
            for item in data.get("entities", [])[:8]
            if read_text(item.get("canonical_name"), 120)
        ],
        "claims": [
            {
                "subject_names": dedupe_texts(item.get("subject_names", []), limit=6),
                "claim_text": read_text(item.get("claim_text"), 280),
                "claim_type": read_choice(item.get("claim_type"), CLAIM_TYPE_OPTIONS, "observation"),
                "stance": read_choice(item.get("stance"), STANCE_OPTIONS, "neutral"),
                "tags": dedupe_texts(item.get("tags", []), limit=8),
                "confidence": float(item.get("confidence", 0.0) or 0.0),
            }
            for item in data.get("claims", [])[:12]
            if read_text(item.get("claim_text"), 280)
        ],
        "guides": [
            {
                "title": read_text(item.get("title"), 160),
                "summary": read_text(item.get("summary"), 320),
                "steps": dedupe_texts(item.get("steps", []), limit=8),
                "subject_names": dedupe_texts(item.get("subject_names", []), limit=6),
            }
            for item in data.get("guides", [])[:6]
            if read_text(item.get("title"), 160)
        ],
        "questions": [
            {
                "question_text": read_text(item.get("question_text"), 220),
                "subject_names": dedupe_texts(item.get("subject_names", []), limit=6),
                "status": read_choice(item.get("status"), QUESTION_STATUS_OPTIONS, "open"),
            }
            for item in data.get("questions", [])[:6]
            if read_text(item.get("question_text"), 220)
        ],
    }
    return curate_extraction_result(normalized, user_turn_text, ingested_text)


def search_live_web_results(query_text: str, max_results: int = 4) -> list[dict[str, Any]]:
    if not can_use_perplexity_search():
        return []

    api_key = read_text(os.getenv("PERPLEXITY_API_KEY"), 400)
    try:
        response = requests.post(
            PERPLEXITY_SEARCH_ENDPOINT,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "query": read_text(query_text, 240),
                "max_results": max(1, min(int(max_results or 4), 6)),
            },
            timeout=(3.5, 8.0),
        )
        response.raise_for_status()
        payload = response.json() if response.content else {}
    except Exception:
        app.logger.exception("Perplexity search failed", extra={"query": query_text})
        return []

    results = []
    for item in payload.get("results", []) or []:
        url = read_text(item.get("url"), 500)
        title = read_text(item.get("title"), 180)
        if not url or not title:
            continue
        results.append(
            {
                "kind": "web",
                "label": title,
                "title": title,
                "url": url,
                "summary": read_text(item.get("snippet"), 320),
                "sourceDomain": normalize_domain(urlparse(url).hostname or ""),
            }
        )
    return results[:max_results]


def score_text_match(blob: str, query: str) -> float:
    normalized_blob = normalize_for_match(blob)
    normalized_query = normalize_for_match(query)
    if not normalized_blob or not normalized_query:
        return 0.0
    score = 0.0
    if normalized_query in normalized_blob:
        score += 4.0
    for token in normalized_query.split():
        if token in normalized_blob:
            score += 1.1
    return score


def search_graph_context(query_text: str) -> dict[str, list[dict[str, Any]]]:
    entities = list_entities()
    claims = [
        table_to_claim_record(row)
        for row in list_rows(CLAIM_PARTITION_KEY)
        if is_publishable_claim_record(table_to_claim_record(row))
    ]
    guides = [table_to_guide_record(row) for row in list_rows(GUIDE_PARTITION_KEY)]
    questions = [
        table_to_question_record(row)
        for row in list_rows(QUESTION_PARTITION_KEY)
        if is_publishable_question_record(table_to_question_record(row))
    ]

    ranked_entities = sorted(
        entities,
        key=lambda item: -score_text_match(
            " ".join(
                [
                    item.get("canonicalName", ""),
                    item.get("summary", ""),
                    " ".join(item.get("aliases", [])),
                    " ".join(item.get("goodFor", [])),
                    " ".join(item.get("badAt", [])),
                    " ".join(item.get("usedFor", [])),
                ]
            ),
            query_text,
        ),
    )
    ranked_claims = sorted(
        claims,
        key=lambda item: -score_text_match(
            " ".join(
                [
                    item.get("claimText", ""),
                    " ".join(item.get("subjectNames", [])),
                    " ".join(item.get("tags", [])),
                ]
            ),
            query_text,
        ),
    )
    ranked_guides = sorted(
        guides,
        key=lambda item: -score_text_match(
            " ".join(
                [
                    item.get("title", ""),
                    item.get("summary", ""),
                    " ".join(item.get("steps", [])),
                    " ".join(item.get("subjectNames", [])),
                ]
            ),
            query_text,
        ),
    )
    ranked_questions = sorted(
        questions,
        key=lambda item: -score_text_match(
            " ".join([item.get("questionText", ""), " ".join(item.get("subjectNames", []))]),
            query_text,
        ),
    )
    return {
        "entities": [item for item in ranked_entities if score_text_match(item.get("canonicalName", "") + " " + item.get("summary", ""), query_text) > 0][:4],
        "claims": [item for item in ranked_claims if score_text_match(item.get("claimText", ""), query_text) > 0][:6],
        "guides": [item for item in ranked_guides if score_text_match(item.get("title", "") + " " + item.get("summary", ""), query_text) > 0][:4],
        "questions": [item for item in ranked_questions if score_text_match(item.get("questionText", ""), query_text) > 0][:4],
    }


def generate_grounded_reply(
    turn_text: str,
    extraction: dict[str, Any],
    graph_context: dict[str, list[dict[str, Any]]],
    web_results: list[dict[str, Any]],
    recent_messages: list[dict[str, Any]],
) -> dict[str, Any]:
    fallback_parts = []
    if extraction.get("summary"):
        fallback_parts.append(extraction["summary"])
    if graph_context.get("claims"):
        fallback_parts.append(
            "Relevant graph signals include "
            + ", ".join(
                read_text(item.get("claimText"), 140) for item in graph_context["claims"][:3]
            )
            + "."
        )
    if web_results:
        fallback_parts.append(
            "Live web references include "
            + ", ".join(read_text(item.get("title"), 120) for item in web_results[:3])
            + "."
        )
    fallback_reply = " ".join(part for part in fallback_parts if part).strip() or "I stored the signal and updated the graph where I could."

    if not can_use_ai():
        return {
            "reply": fallback_reply,
            "followups": [],
            "answer_title": extraction.get("conversation_title", "AI conversation"),
        }

    messages = [
        {
            "role": "system",
            "content": (
                "You are the conversational layer for StopTheSlop. "
                "Answer in a grounded way using the supplied submission context, internal graph context, and live web evidence. "
                "Be direct, concise, and explicit about uncertainty. "
                "Do not quote long passages. "
                "Treat the graph as community memory, not absolute truth."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "userTurn": read_text(turn_text, 4000),
                    "extraction": {
                        "summary": extraction.get("summary", ""),
                        "entities": extraction.get("entities", []),
                        "claims": extraction.get("claims", []),
                        "guides": extraction.get("guides", []),
                        "questions": extraction.get("questions", []),
                    },
                    "graphContext": {
                        "entities": [
                            {
                                "name": entity.get("canonicalName", ""),
                                "summary": entity.get("summary", ""),
                                "goodFor": entity.get("goodFor", []),
                                "badAt": entity.get("badAt", []),
                            }
                            for entity in graph_context.get("entities", [])[:4]
                        ],
                        "claims": [
                            {
                                "text": item.get("claimText", ""),
                                "subjects": item.get("subjectNames", []),
                                "supportCount": item.get("supportCount", 0),
                            }
                            for item in graph_context.get("claims", [])[:6]
                        ],
                        "guides": [
                            {
                                "title": item.get("title", ""),
                                "summary": item.get("summary", ""),
                            }
                            for item in graph_context.get("guides", [])[:4]
                        ],
                        "questions": [
                            {
                                "question": item.get("questionText", ""),
                                "status": item.get("status", "open"),
                            }
                            for item in graph_context.get("questions", [])[:4]
                        ],
                    },
                    "webResults": [
                        {
                            "title": item.get("title", ""),
                            "domain": item.get("sourceDomain", ""),
                            "summary": item.get("summary", ""),
                            "url": item.get("url", ""),
                        }
                        for item in web_results[:4]
                    ],
                    "recentMessages": [
                        {"role": item.get("role", ""), "text": read_text(item.get("text"), 900)}
                        for item in recent_messages[-6:]
                    ],
                },
                ensure_ascii=True,
            ),
        },
    ]
    data = call_ai_json(messages, REPLY_SCHEMA, max_tokens=850)
    if not data:
        return {
            "reply": fallback_reply,
            "followups": [],
            "answer_title": extraction.get("conversation_title", "AI conversation"),
        }
    return {
        "reply": read_text(data.get("reply"), 6000) or fallback_reply,
        "followups": dedupe_texts(data.get("followups", []), limit=4),
        "answer_title": read_text(data.get("answer_title"), 140)
        or extraction.get("conversation_title", "AI conversation"),
    }


def build_claim_id(subject_entity_ids: list[str], claim_text: str, claim_type: str, stance: str) -> str:
    digest = hashlib.sha1(
        f"{'|'.join(sorted(subject_entity_ids))}|{normalize_for_match(claim_text)}|{claim_type}|{stance}".encode("utf-8")
    ).hexdigest()[:16]
    return f"claim-{digest}"


def build_guide_id(title: str, subject_entity_ids: list[str]) -> str:
    digest = hashlib.sha1(
        f"{normalize_for_match(title)}|{'|'.join(sorted(subject_entity_ids))}".encode("utf-8")
    ).hexdigest()[:16]
    return f"guide-{digest}"


def build_question_id(question_text: str, subject_entity_ids: list[str]) -> str:
    digest = hashlib.sha1(
        f"{normalize_for_match(question_text)}|{'|'.join(sorted(subject_entity_ids))}".encode("utf-8")
    ).hexdigest()[:16]
    return f"question-{digest}"


def list_claims() -> list[dict[str, Any]]:
    return [table_to_claim_record(row) for row in list_rows(CLAIM_PARTITION_KEY)]


def list_guides() -> list[dict[str, Any]]:
    return [table_to_guide_record(row) for row in list_rows(GUIDE_PARTITION_KEY)]


def list_questions() -> list[dict[str, Any]]:
    return [table_to_question_record(row) for row in list_rows(QUESTION_PARTITION_KEY)]


def upsert_claim(
    claim_text: str,
    claim_type: str,
    stance: str,
    subject_entities: list[dict[str, Any]],
    source_ids: list[str],
    tags: list[str],
    confidence: float,
) -> dict[str, Any]:
    subject_entity_ids = [entity["id"] for entity in subject_entities]
    subject_names = [entity.get("canonicalName", "") for entity in subject_entities]
    claim_id = build_claim_id(subject_entity_ids, claim_text, claim_type, stance)
    existing = get_row(CLAIM_PARTITION_KEY, claim_id)
    record = table_to_claim_record(existing) if existing else {
        "id": claim_id,
        "subjectEntityIds": subject_entity_ids,
        "subjectNames": subject_names,
        "claimText": claim_text,
        "claimType": claim_type,
        "stance": stance,
        "tags": tags,
        "sourceIds": [],
        "supportCount": 0,
        "opposeCount": 0,
        "confidence": 0.0,
        "createdAt": now_iso(),
        "updatedAt": now_iso(),
    }
    record["subjectEntityIds"] = merge_unique(record.get("subjectEntityIds", []), subject_entity_ids, limit=8)
    record["subjectNames"] = merge_unique(record.get("subjectNames", []), subject_names, limit=8)
    record["tags"] = merge_unique(record.get("tags", []), tags, limit=10)
    record["sourceIds"] = merge_unique(record.get("sourceIds", []), source_ids, limit=30)
    record["supportCount"] = int(record.get("supportCount", 0)) + max(1, len(source_ids))
    record["confidence"] = max(float(record.get("confidence", 0.0) or 0.0), float(confidence or 0.0))
    record["updatedAt"] = now_iso()
    upsert_row(claim_record_to_table(record))
    return record


def upsert_guide(
    title: str,
    summary: str,
    steps: list[str],
    subject_entities: list[dict[str, Any]],
    source_ids: list[str],
) -> dict[str, Any]:
    subject_entity_ids = [entity["id"] for entity in subject_entities]
    subject_names = [entity.get("canonicalName", "") for entity in subject_entities]
    guide_id = build_guide_id(title, subject_entity_ids)
    existing = get_row(GUIDE_PARTITION_KEY, guide_id)
    record = table_to_guide_record(existing) if existing else {
        "id": guide_id,
        "title": title,
        "summary": summary,
        "steps": steps,
        "subjectEntityIds": subject_entity_ids,
        "subjectNames": subject_names,
        "sourceIds": [],
        "createdAt": now_iso(),
        "updatedAt": now_iso(),
    }
    record["summary"] = record.get("summary", "") or summary
    record["steps"] = merge_unique(record.get("steps", []), steps, limit=10)
    record["subjectEntityIds"] = merge_unique(record.get("subjectEntityIds", []), subject_entity_ids, limit=8)
    record["subjectNames"] = merge_unique(record.get("subjectNames", []), subject_names, limit=8)
    record["sourceIds"] = merge_unique(record.get("sourceIds", []), source_ids, limit=30)
    record["updatedAt"] = now_iso()
    upsert_row(guide_record_to_table(record))
    return record


def upsert_question(
    question_text: str,
    status: str,
    subject_entities: list[dict[str, Any]],
    source_ids: list[str],
) -> dict[str, Any]:
    subject_entity_ids = [entity["id"] for entity in subject_entities]
    subject_names = [entity.get("canonicalName", "") for entity in subject_entities]
    question_id = build_question_id(question_text, subject_entity_ids)
    existing = get_row(QUESTION_PARTITION_KEY, question_id)
    record = table_to_question_record(existing) if existing else {
        "id": question_id,
        "questionText": question_text,
        "subjectEntityIds": subject_entity_ids,
        "subjectNames": subject_names,
        "sourceIds": [],
        "status": "open",
        "createdAt": now_iso(),
        "updatedAt": now_iso(),
    }
    record["subjectEntityIds"] = merge_unique(record.get("subjectEntityIds", []), subject_entity_ids, limit=8)
    record["subjectNames"] = merge_unique(record.get("subjectNames", []), subject_names, limit=8)
    record["sourceIds"] = merge_unique(record.get("sourceIds", []), source_ids, limit=30)
    record["status"] = read_choice(status, QUESTION_STATUS_OPTIONS, record.get("status", "open"))
    record["updatedAt"] = now_iso()
    upsert_row(question_record_to_table(record))
    return record


def persist_answer(
    conversation_id: str,
    title: str,
    answer_text: str,
    grounded_source_ids: list[str],
    grounded_entity_ids: list[str],
    question_id: str = "",
) -> dict[str, Any]:
    record = {
        "id": build_row_key("ans"),
        "conversationId": conversation_id,
        "title": title,
        "answerText": answer_text,
        "questionId": question_id,
        "groundedSourceIds": grounded_source_ids,
        "groundedEntityIds": grounded_entity_ids,
        "createdAt": now_iso(),
    }
    upsert_row(answer_record_to_table(record))
    return record


def apply_claims_to_entities(
    subject_entities: list[dict[str, Any]],
    claim_type: str,
    claim_text: str,
    tags: list[str],
) -> None:
    for entity in subject_entities:
        entity["topTags"] = merge_unique(entity.get("topTags", []), tags, limit=14)
        if claim_type == "good_for":
            entity["goodFor"] = merge_unique(entity.get("goodFor", []), [claim_text], limit=10)
        elif claim_type == "bad_at":
            entity["badAt"] = merge_unique(entity.get("badAt", []), [claim_text], limit=10)
        elif claim_type == "used_for":
            entity["usedFor"] = merge_unique(entity.get("usedFor", []), [claim_text], limit=10)
        stats = entity.get("stats", {}) or {}
        stats["claimCount"] = int(stats.get("claimCount", 0)) + 1
        entity["stats"] = stats
        entity["updatedAt"] = now_iso()
        upsert_row(entity_record_to_table(entity))


def resolve_subject_entities(
    extraction_entities: list[dict[str, Any]],
    subject_names: list[str],
) -> list[dict[str, Any]]:
    resolved: list[dict[str, Any]] = []
    extraction_index = {
        normalize_for_match(item.get("canonical_name", "")): item
        for item in extraction_entities
        if normalize_for_match(item.get("canonical_name", ""))
    }
    for name in dedupe_texts(subject_names, limit=6):
        normalized = normalize_for_match(name)
        extraction_match = extraction_index.get(normalized)
        if extraction_match:
            candidate = infer_entity_record_from_name(
                extraction_match.get("canonical_name", name),
                extraction_match.get("entity_type", "other"),
                extraction_match.get("vendor", ""),
            )
            candidate["officialUrl"] = extraction_match.get("official_url", "")
            candidate["summary"] = extraction_match.get("summary", "")
            candidate["aliases"] = merge_unique(
                candidate.get("aliases", []),
                extraction_match.get("aliases", []),
                limit=12,
            )
            candidate["stats"] = {"sourceCount": 1, "claimCount": 0, "guideCount": 0, "questionCount": 0}
            resolved.append(upsert_entity_record(candidate))
            continue

        existing = find_existing_entity_by_name(name)
        if existing:
            resolved.append(existing)
            continue

        if not should_keep_entity_candidate(name, "other"):
            continue
        candidate = infer_entity_record_from_name(name)
        candidate["stats"] = {"sourceCount": 1, "claimCount": 0, "guideCount": 0, "questionCount": 0}
        resolved.append(upsert_entity_record(candidate))
    return resolved


def build_graph_updates(
    entities: list[dict[str, Any]],
    claims: list[dict[str, Any]],
    guides: list[dict[str, Any]],
    questions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    updates: list[dict[str, Any]] = []
    for entity in [item for item in entities if is_publishable_entity_record(item)][:4]:
        updates.append(
            {
                "kind": "entity",
                "title": entity.get("canonicalName", ""),
                "summary": entity.get("summary", "") or entity.get("description", ""),
            }
        )
    for claim in [item for item in claims if is_publishable_claim_record(item)][:4]:
        updates.append(
            {
                "kind": "claim",
                "title": claim.get("claimText", ""),
                "summary": ", ".join(filter_publishable_subject_names(claim.get("subjectNames", []))),
            }
        )
    for guide in guides[:3]:
        updates.append(
            {
                "kind": "guide",
                "title": guide.get("title", ""),
                "summary": guide.get("summary", ""),
            }
        )
    for question in [item for item in questions if is_publishable_question_record(item)][:3]:
        updates.append(
            {
                "kind": "question",
                "title": question.get("questionText", ""),
                "summary": ", ".join(question.get("subjectNames", [])),
            }
        )
    return updates[:10]


def build_citations(
    source_records: list[dict[str, Any]],
    graph_context: dict[str, list[dict[str, Any]]],
    web_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    citations: list[dict[str, Any]] = []
    for source in source_records[:3]:
        label = source.get("sourceUrl") or source.get("filename") or source.get("summary") or source.get("id")
        citations.append(
            {
                "kind": "source",
                "label": read_text(label, 120),
                "summary": read_text(source.get("summary"), 220),
                "url": read_text(source.get("sourceUrl"), 400),
            }
        )
    for claim in graph_context.get("claims", [])[:3]:
        citations.append(
            {
                "kind": "graph",
                "label": read_text(claim.get("claimText"), 120),
                "summary": read_text(", ".join(claim.get("subjectNames", [])), 220),
                "url": "",
            }
        )
    for result in web_results[:2]:
        citations.append(
            {
                "kind": "web",
                "label": read_text(result.get("title"), 120),
                "summary": read_text(result.get("summary"), 220),
                "url": read_text(result.get("url"), 400),
            }
        )
    return citations[:8]


def get_conversation_record(conversation_id: str) -> dict[str, Any] | None:
    row = get_row(CONVERSATION_PARTITION_KEY, conversation_id)
    return table_to_conversation_record(row) if row else None


def list_conversation_messages(conversation_id: str) -> list[dict[str, Any]]:
    partition = message_partition_key(conversation_id)
    messages = [table_to_message_record(row) for row in list_rows(partition)]
    return sorted(messages, key=lambda item: item.get("createdAt", ""))


def can_access_conversation(conversation: dict[str, Any], token: str = "") -> bool:
    user = get_authenticated_user()
    if user and read_text(conversation.get("submitterId"), 120) == read_text(user.get("id"), 120):
        return True
    if token and hash_token(token) == read_text(conversation.get("manageTokenHash"), 120):
        return True
    return False


def build_public_conversation(
    conversation: dict[str, Any],
    messages: list[dict[str, Any]],
    include_manage_token: str = "",
) -> dict[str, Any]:
    return {
        "id": conversation["id"],
        "title": conversation.get("title", "AI conversation"),
        "anonymousHandle": conversation.get("anonymousHandle", ""),
        "createdAt": conversation.get("createdAt", now_iso()),
        "updatedAt": conversation.get("updatedAt", now_iso()),
        "manageToken": include_manage_token,
        "messages": messages,
    }


def create_or_update_conversation(
    conversation_id: str,
    title: str,
    submitter_id: str,
    anonymous_handle: str,
    source_ids: list[str],
    grounded_entity_ids: list[str],
    latest_reply_summary: str,
    manage_token_hash: str = "",
) -> dict[str, Any]:
    existing = get_conversation_record(conversation_id)
    record = {
        **(existing or {}),
        "id": conversation_id,
        "title": read_text(title, 120) or (existing or {}).get("title", "AI conversation"),
        "submitterId": submitter_id or (existing or {}).get("submitterId", ""),
        "anonymousHandle": anonymous_handle or (existing or {}).get("anonymousHandle", ""),
        "manageTokenHash": manage_token_hash or (existing or {}).get("manageTokenHash", ""),
        "sourceIds": merge_unique((existing or {}).get("sourceIds", []), source_ids, limit=30),
        "groundedEntityIds": merge_unique(
            (existing or {}).get("groundedEntityIds", []),
            grounded_entity_ids,
            limit=20,
        ),
        "latestReplySummary": read_text(latest_reply_summary, 240),
        "createdAt": (existing or {}).get("createdAt", now_iso()),
        "updatedAt": now_iso(),
    }
    upsert_row(conversation_record_to_table(record))
    return record


def persist_message(
    conversation_id: str,
    role: str,
    text: str,
    source_ids: list[str],
    grounded_entity_ids: list[str],
    citations: list[dict[str, Any]],
    graph_updates: list[dict[str, Any]],
) -> dict[str, Any]:
    record = {
        "id": build_row_key("msg"),
        "conversationId": conversation_id,
        "role": role,
        "text": read_text(text, 6000),
        "sourceIds": source_ids,
        "groundedEntityIds": grounded_entity_ids,
        "citations": citations,
        "graphUpdates": graph_updates,
        "createdAt": now_iso(),
    }
    upsert_row(message_record_to_table(record))
    return record


def ingest_submission(
    conversation_id: str,
    text: str,
    urls: list[str],
    uploaded_files,
    submitter_id: str,
    anonymous_handle: str,
) -> tuple[list[dict[str, Any]], str]:
    source_records: list[dict[str, Any]] = []
    combined_text_parts: list[str] = []

    if text:
        source = create_source_record(
            conversation_id,
            submitter_id,
            anonymous_handle,
            "text",
            text,
            read_text(text, 400),
        )
        source_records.append(source)
        combined_text_parts.append(text)

    for url in urls:
        preview = extract_web_import_preview(url)
        extracted_text = " ".join(
            [
                preview.get("title", ""),
                preview.get("description", ""),
                preview.get("excerpt", ""),
            ]
        )
        source = create_source_record(
            conversation_id,
            submitter_id,
            anonymous_handle,
            "url",
            extracted_text,
            preview.get("title", "") or preview.get("sourceLabel", ""),
            source_url=preview.get("url", ""),
        )
        source_records.append(source)
        combined_text_parts.append(extracted_text)

    for uploaded in uploaded_files[:8]:
        filename = read_text(getattr(uploaded, "filename", ""), 180) or "upload.bin"
        content_type = read_text(getattr(uploaded, "content_type", ""), 120) or "application/octet-stream"
        payload = uploaded.read()
        extracted_text, summary = extract_file_summary(filename, content_type, payload)
        source_id = build_row_key("src")
        blob_path = f"{datetime.now(timezone.utc).strftime('%Y/%m/%d')}/{conversation_id}/{source_id}-{slugify(filename)}"
        upload_blob_bytes(blob_path, payload, content_type)
        source = create_source_record(
            conversation_id,
            submitter_id,
            anonymous_handle,
            "file",
            extracted_text,
            summary,
            filename=filename,
            content_type=content_type,
            blob_path=blob_path,
            source_id=source_id,
        )
        source_records.append(source)
        combined_text_parts.append(extracted_text or summary)

    combined_text = read_text("\n\n".join(part for part in combined_text_parts if part), MAX_EXTRACTED_TEXT_CHARS)
    return source_records, combined_text


def derive_cluster_items(claims: list[dict[str, Any]], entities_by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for claim in claims:
        entity_id = read_text((claim.get("subjectEntityIds") or [""])[0], 120)
        if entity_id:
            grouped[entity_id].append(claim)

    items = []
    for entity_id, entity_claims in grouped.items():
        entity = entities_by_id.get(entity_id)
        if not entity or not entity_claims:
            continue
        top_claims = sorted(entity_claims, key=lambda item: (-item.get("supportCount", 0), item.get("updatedAt", "")))[:3]
        support = sum(int(item.get("supportCount", 0)) for item in top_claims)
        items.append(
            {
                "id": f"cluster-{entity_id}",
                "kind": "cluster",
                "title": f"Hot subject: {entity.get('canonicalName', '')}",
                "summary": " / ".join(read_text(item.get("claimText"), 110) for item in top_claims),
                "entityId": entity_id,
                "supportCount": support,
                "updatedAt": max((item.get("updatedAt", "") for item in top_claims), default=""),
            }
        )
    return sorted(items, key=lambda item: (-item.get("supportCount", 0), item.get("updatedAt", "")))[:6]


def build_feed() -> dict[str, Any]:
    ensure_legacy_graph_migration()
    entities = [entity for entity in list_entities() if is_publishable_entity_record(entity)]
    claims = [claim for claim in list_claims() if is_publishable_claim_record(claim)]
    guides = list_guides()
    questions = [question for question in list_questions() if is_publishable_question_record(question)]
    entities_by_id = {entity["id"]: entity for entity in entities}

    claim_items = [
        {
            "id": claim["id"],
            "kind": "claim",
            "title": claim.get("claimText", ""),
            "summary": ", ".join(filter_publishable_subject_names(claim.get("subjectNames", []))),
            "entityId": read_text((claim.get("subjectEntityIds") or [""])[0], 120),
            "supportCount": int(claim.get("supportCount", 0)),
            "updatedAt": claim.get("updatedAt", ""),
            "tags": claim.get("tags", []),
        }
        for claim in sorted(
            claims,
            key=lambda item: (-int(item.get("supportCount", 0)), item.get("updatedAt", "")),
        )[:10]
    ]
    guide_items = [
        {
            "id": guide["id"],
            "kind": "guide",
            "title": guide.get("title", ""),
            "summary": guide.get("summary", ""),
            "entityId": read_text((guide.get("subjectEntityIds") or [""])[0], 120),
            "supportCount": len(guide.get("sourceIds", [])),
            "updatedAt": guide.get("updatedAt", ""),
        }
        for guide in sorted(guides, key=lambda item: item.get("updatedAt", ""), reverse=True)[:8]
    ]
    question_items = [
        {
            "id": question["id"],
            "kind": "question",
            "title": question.get("questionText", ""),
            "summary": ", ".join(question.get("subjectNames", [])) or question.get("status", "open"),
            "entityId": read_text((question.get("subjectEntityIds") or [""])[0], 120),
            "supportCount": len(question.get("sourceIds", [])),
            "updatedAt": question.get("updatedAt", ""),
        }
        for question in sorted(questions, key=lambda item: item.get("updatedAt", ""), reverse=True)[:8]
    ]
    entity_items = [
        {
            "id": entity["id"],
            "kind": "entity",
            "title": entity.get("canonicalName", ""),
            "summary": entity.get("summary", "") or entity.get("description", ""),
            "entityId": entity["id"],
            "supportCount": int((entity.get("stats") or {}).get("sourceCount", 0)),
            "updatedAt": entity.get("updatedAt", ""),
        }
        for entity in entities[:8]
    ]
    cluster_items = derive_cluster_items(claims, entities_by_id)

    buckets = [claim_items, guide_items, cluster_items, question_items, entity_items]
    mixed: list[dict[str, Any]] = []
    while any(buckets) and len(mixed) < MAX_FEED_ITEMS:
        for bucket in buckets:
            if bucket:
                mixed.append(bucket.pop(0))
                if len(mixed) >= MAX_FEED_ITEMS:
                    break

    return {
        "metrics": {
            "sourceCount": len(list_rows(SOURCE_PARTITION_KEY)),
            "entityCount": len(entities),
            "claimCount": len(claims),
            "guideCount": len(guides),
        },
        "items": mixed,
        "featuredEntities": entity_items[:6],
    }


def build_entity_detail(entity_id: str) -> dict[str, Any] | None:
    entity = get_entity_record(entity_id)
    if not entity:
        return None

    if not is_publishable_entity_record(entity):
        return None

    claims = [
        claim
        for claim in list_claims()
        if entity_id in claim.get("subjectEntityIds", [])
        and is_publishable_claim_record(claim)
    ]
    guides = [
        guide
        for guide in list_guides()
        if entity_id in guide.get("subjectEntityIds", [])
    ]
    questions = [
        question
        for question in list_questions()
        if entity_id in question.get("subjectEntityIds", [])
        and is_publishable_question_record(question)
    ]
    related_entity_ids: set[str] = set()
    for claim in claims[:12]:
        for related_id in claim.get("subjectEntityIds", []):
            if related_id and related_id != entity_id:
                related_entity_ids.add(related_id)
    related_entities = [get_entity_record(related_id) for related_id in sorted(related_entity_ids)]
    related_entities = [entity for entity in related_entities if entity and is_publishable_entity_record(entity)]

    return {
        **entity,
        "claims": sorted(claims, key=lambda item: (-item.get("supportCount", 0), item.get("updatedAt", "")))[:16],
        "guides": sorted(guides, key=lambda item: item.get("updatedAt", ""), reverse=True)[:10],
        "questions": sorted(questions, key=lambda item: item.get("updatedAt", ""), reverse=True)[:10],
        "relatedEntities": related_entities[:8],
        "sourceLinks": build_entity_source_links(entity),
    }


def search_entities(query_text: str) -> list[dict[str, Any]]:
    query = read_text(query_text, 180)
    entities = [entity for entity in list_entities() if is_publishable_entity_record(entity)]
    if not query:
        return entities
    scored = []
    for entity in entities:
        blob = " ".join(
            [
                entity.get("canonicalName", ""),
                entity.get("summary", ""),
                entity.get("vendor", ""),
                " ".join(entity.get("aliases", [])),
                " ".join(entity.get("goodFor", [])),
                " ".join(entity.get("badAt", [])),
                " ".join(entity.get("usedFor", [])),
            ]
        )
        score = score_text_match(blob, query)
        if score > 0:
            scored.append((score, entity))
    scored.sort(key=lambda item: (-item[0], item[1].get("canonicalName", "").lower()))
    return [entity for _score, entity in scored[:18]]


def legacy_entity_to_ticket(entity: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": entity["RowKey"],
        "title": entity.get("title", ""),
        "summary": entity.get("summary", ""),
        "context": entity.get("context", ""),
        "toolFamily": entity.get("toolFamily", ""),
        "toolDetail": entity.get("toolDetail", ""),
        "referenceUrl": entity.get("referenceUrl", ""),
        "sourceType": entity.get("sourceType", "signal"),
        "contentKind": entity.get("contentKind", "other"),
        "importDomain": entity.get("importDomain", ""),
        "importTitle": entity.get("importTitle", ""),
        "importExcerpt": entity.get("importExcerpt", ""),
        "createdAt": entity.get("createdAt", now_iso()),
        "primaryEntityId": entity.get("primaryEntityId", ""),
        "goodFor": read_json(entity.get("goodForJson", "[]"), []),
        "badAt": read_json(entity.get("badAtJson", "[]"), []),
        "usedFor": read_json(entity.get("usedForJson", "[]"), []),
        "tags": read_json(entity.get("tagsJson", "[]"), []),
        "aiSummary": entity.get("aiSummary", ""),
    }


def ensure_meta_flag(flag_name: str) -> bool:
    return get_row(META_PARTITION_KEY, flag_name) is not None


def set_meta_flag(flag_name: str, payload: dict[str, Any]) -> None:
    upsert_row(
        {
            "PartitionKey": META_PARTITION_KEY,
            "RowKey": flag_name,
            "payloadJson": json.dumps(payload),
            "createdAt": now_iso(),
        }
    )


def ensure_legacy_graph_migration() -> None:
    global _migration_checked
    if _migration_checked:
        return
    if ensure_meta_flag("legacy-graph-migration-v1"):
        _migration_checked = True
        return

    entity_rows = [table_to_entity_record(row) for row in list_entity_rows()]
    entity_index = {entity["id"]: entity for entity in entity_rows}
    for ticket_row in list_rows(LEGACY_TICKET_PARTITION_KEY):
        ticket = legacy_entity_to_ticket(ticket_row)
        source_id = f"legacy-src-{ticket['id']}"
        if get_row(SOURCE_PARTITION_KEY, source_id):
            continue

        entity = entity_index.get(ticket.get("primaryEntityId", ""))
        if not entity:
            entity = find_existing_entity_by_name(ticket.get("toolDetail", "")) or upsert_entity_record(
                infer_entity_record_from_name(ticket.get("toolDetail") or ticket.get("title") or ticket["id"])
            )

        source = create_source_record(
            conversation_id="",
            submitter_id="",
            anonymous_handle="legacy-import",
            kind="legacy_ticket",
            extracted_text=" ".join(
                [
                    ticket.get("title", ""),
                    ticket.get("summary", ""),
                    ticket.get("context", ""),
                    ticket.get("aiSummary", ""),
                ]
            ),
            summary=ticket.get("title", "") or ticket.get("summary", ""),
            source_url=ticket.get("referenceUrl", ""),
            moderation_status="accepted",
            created_at=ticket.get("createdAt", now_iso()),
            source_id=source_id,
        )
        entity["stats"] = entity.get("stats", {}) or {}
        entity["stats"]["sourceCount"] = int(entity["stats"].get("sourceCount", 0)) + 1
        upsert_row(entity_record_to_table(entity))

        created_claim = False
        for text in ticket.get("goodFor", [])[:4]:
            upsert_claim(text, "good_for", "positive", [entity], [source["id"]], ticket.get("tags", []), 0.7)
            created_claim = True
        for text in ticket.get("badAt", [])[:4]:
            upsert_claim(text, "bad_at", "negative", [entity], [source["id"]], ticket.get("tags", []), 0.7)
            created_claim = True
        for text in ticket.get("usedFor", [])[:4]:
            upsert_claim(text, "used_for", "neutral", [entity], [source["id"]], ticket.get("tags", []), 0.7)
            created_claim = True

        if ticket.get("contentKind") in {"guide", "tutorial", "docs"}:
            upsert_guide(
                ticket.get("importTitle") or ticket.get("title") or f"{entity['canonicalName']} guide",
                ticket.get("summary") or ticket.get("importExcerpt") or "",
                [],
                [entity],
                [source["id"]],
            )

        if not created_claim:
            fallback_claim = ticket.get("aiSummary") or ticket.get("summary") or ticket.get("title")
            if fallback_claim:
                upsert_claim(
                    read_text(fallback_claim, 260),
                    "observation",
                    "neutral",
                    [entity],
                    [source["id"]],
                    ticket.get("tags", []),
                    0.5,
                )

    set_meta_flag("legacy-graph-migration-v1", {"migratedAt": now_iso()})
    _migration_checked = True


def submit_turn(forced_conversation_id: str = "") -> tuple[dict[str, Any], int]:
    ensure_legacy_graph_migration()
    submitter_id, anonymous_handle, _user = build_actor_context()
    form = request.form if request.content_type and "multipart/form-data" in request.content_type else None
    payload = request.get_json(silent=True) or {}

    conversation_id = forced_conversation_id or read_text((form or payload).get("conversationId"), 120)
    text = read_text((form or payload).get("text"), 6000)
    field_urls = parse_urls((form or payload).get("urls", ""))
    inline_urls = parse_urls(text)
    urls = dedupe_texts([*inline_urls, *field_urls], limit=10)
    uploaded_files = request.files.getlist("files") if form is not None else []

    manage_token = read_text((form or payload).get("manageToken"), 240)
    existing_conversation = get_conversation_record(conversation_id) if conversation_id else None
    if existing_conversation:
        if not can_access_conversation(existing_conversation, manage_token):
            return {"detail": "Conversation not found or access token is invalid."}, 404
    else:
        conversation_id = build_row_key("conv")
        manage_token = secrets.token_urlsafe(24)
        existing_conversation = None

    if not text and not urls and not uploaded_files:
        return {"detail": "Share text, a URL, or a file."}, 400

    source_records, combined_text = ingest_submission(
        conversation_id,
        text,
        urls,
        uploaded_files,
        submitter_id,
        anonymous_handle,
    )
    source_ids = [source["id"] for source in source_records]
    recent_messages = list_conversation_messages(conversation_id)

    user_message_text = read_text(
        "\n\n".join(
            part
            for part in [
                text,
                "\n".join(field_urls),
                "\n".join(
                    f"Uploaded {source.get('filename') or source.get('summary')}"
                    for source in source_records
                    if source.get("kind") == "file"
                ),
            ]
            if part
        ),
        4000,
    ) or read_text(combined_text, 4000)
    persist_message(conversation_id, "user", user_message_text, source_ids, [], [], [])

    extraction = extract_submission_signals(
        text,
        combined_text or user_message_text,
        source_records,
        recent_messages,
    )
    if extraction["moderation_action"] == "reject":
        reply_text = extraction.get("moderation_reason") or "I stored the submission privately, but I cannot derive public knowledge from it."
        conversation = create_or_update_conversation(
            conversation_id,
            extraction.get("conversation_title", "AI conversation"),
            submitter_id,
            anonymous_handle,
            source_ids,
            [],
            reply_text,
            manage_token_hash=hash_token(manage_token) if not existing_conversation else "",
        )
        assistant_message = persist_message(conversation_id, "assistant", reply_text, source_ids, [], [], [])
        return (
            build_public_conversation(conversation, [*recent_messages, assistant_message], include_manage_token=manage_token),
            201,
        )

    extracted_entities = []
    for item in extraction.get("entities", []):
        candidate = infer_entity_record_from_name(
            item.get("canonical_name", ""),
            item.get("entity_type", "other"),
            item.get("vendor", ""),
        )
        candidate["officialUrl"] = item.get("official_url", "")
        candidate["summary"] = item.get("summary", "")
        candidate["aliases"] = merge_unique(candidate.get("aliases", []), item.get("aliases", []), limit=12)
        candidate["stats"] = {"sourceCount": 1, "claimCount": 0, "guideCount": 0, "questionCount": 0}
        extracted_entities.append(upsert_entity_record(candidate))

    claims_created: list[dict[str, Any]] = []
    guides_created: list[dict[str, Any]] = []
    questions_created: list[dict[str, Any]] = []

    for claim in extraction.get("claims", []):
        subjects = resolve_subject_entities(extraction.get("entities", []), claim.get("subject_names", []))
        if not subjects:
            continue
        created = upsert_claim(
            claim.get("claim_text", ""),
            claim.get("claim_type", "observation"),
            claim.get("stance", "neutral"),
            subjects,
            source_ids,
            claim.get("tags", []),
            float(claim.get("confidence", 0.0) or 0.0),
        )
        apply_claims_to_entities(subjects, created["claimType"], created["claimText"], created.get("tags", []))
        claims_created.append(created)

    for guide in extraction.get("guides", []):
        subjects = resolve_subject_entities(extraction.get("entities", []), guide.get("subject_names", []))
        if not subjects:
            continue
        created = upsert_guide(
            guide.get("title", ""),
            guide.get("summary", ""),
            guide.get("steps", []),
            subjects,
            source_ids,
        )
        for entity in subjects:
            stats = entity.get("stats", {}) or {}
            stats["guideCount"] = int(stats.get("guideCount", 0)) + 1
            entity["stats"] = stats
            upsert_row(entity_record_to_table(entity))
        guides_created.append(created)

    for question in extraction.get("questions", []):
        subjects = resolve_subject_entities(extraction.get("entities", []), question.get("subject_names", []))
        created = upsert_question(
            question.get("question_text", ""),
            question.get("status", "open"),
            subjects,
            source_ids,
        )
        for entity in subjects:
            stats = entity.get("stats", {}) or {}
            stats["questionCount"] = int(stats.get("questionCount", 0)) + 1
            entity["stats"] = stats
            upsert_row(entity_record_to_table(entity))
        questions_created.append(created)

    grounded_entity_ids = dedupe_texts(
        [entity["id"] for entity in extracted_entities]
        + [entity_id for claim in claims_created for entity_id in claim.get("subjectEntityIds", [])],
        limit=20,
    )
    graph_context = search_graph_context(extraction.get("query_text") or combined_text or user_message_text)
    web_results = search_live_web_results(extraction.get("query_text") or combined_text or user_message_text)
    reply_payload = generate_grounded_reply(
        user_message_text,
        extraction,
        graph_context,
        web_results,
        recent_messages + [{"role": "user", "text": user_message_text}],
    )
    graph_updates = build_graph_updates(extracted_entities, claims_created, guides_created, questions_created)
    citations = build_citations(source_records, graph_context, web_results)
    assistant_message = persist_message(
        conversation_id,
        "assistant",
        reply_payload.get("reply", ""),
        source_ids,
        grounded_entity_ids,
        citations,
        graph_updates,
    )
    persist_answer(
        conversation_id,
        reply_payload.get("answer_title", extraction.get("conversation_title", "AI conversation")),
        reply_payload.get("reply", ""),
        source_ids,
        grounded_entity_ids,
        questions_created[0]["id"] if questions_created else "",
    )

    conversation = create_or_update_conversation(
        conversation_id,
        extraction.get("conversation_title", "AI conversation"),
        submitter_id,
        anonymous_handle,
        source_ids,
        grounded_entity_ids,
        reply_payload.get("reply", ""),
        manage_token_hash=hash_token(manage_token) if not existing_conversation else "",
    )
    messages = list_conversation_messages(conversation_id)
    return (
        build_public_conversation(
            conversation,
            messages,
            include_manage_token=manage_token if not existing_conversation else "",
        ),
        201,
    )


@app.get("/")
def root():
    return jsonify({"service": "stoptheslop-api", "status": "ok"})


@app.get("/healthz")
def healthcheck():
    ensure_legacy_graph_migration()
    return jsonify({"ok": True, "aiConfigured": can_use_ai()})


@app.get("/api/config")
def get_config():
    ensure_legacy_graph_migration()
    return jsonify(
        {
            "aiConfigured": can_use_ai(),
            "authEnabled": auth_is_enabled(),
            "googleClientId": get_google_client_id(),
            "anonymousPosting": True,
            "requiredOnboarding": True,
            "acceptedUploads": ["text", "url", "image", "pdf", "audio", "video", "other"],
        }
    )


@app.get("/api/auth/session")
def get_auth_session():
    if not auth_is_enabled():
        return jsonify({"authenticated": False, "authEnabled": False, "user": None})

    user = get_authenticated_user()
    if not user:
        return jsonify({"authenticated": False, "authEnabled": True, "user": None})

    return jsonify({"authenticated": True, "authEnabled": True, "user": build_public_user(user)})


@app.post("/api/onboarding")
def submit_onboarding():
    return jsonify(persist_onboarding_response()), 201


@app.post("/api/auth/google")
def sign_in_with_google():
    if not auth_is_enabled():
        return jsonify({"detail": "Google sign-in is not configured."}), 503
    payload = request.get_json(silent=True) or {}
    credential = read_text(payload.get("credential"), 5000)
    if not credential:
        return jsonify({"detail": "Missing Google credential."}), 400
    user = verify_google_credential(credential)
    return jsonify({"token": issue_session_token(user), "user": build_public_user(user)})


@app.get("/api/feed")
def get_feed():
    return jsonify(build_feed())


@app.get("/api/entities")
def get_entities():
    ensure_legacy_graph_migration()
    query = read_text(request.args.get("q"), 180)
    return jsonify(search_entities(query))


@app.get("/api/entities/<entity_id>")
def get_entity(entity_id: str):
    ensure_legacy_graph_migration()
    entity = build_entity_detail(entity_id)
    if not entity:
        return jsonify({"detail": "Entity not found."}), 404
    return jsonify(entity)


@app.post("/api/conversations")
def create_conversation_turn():
    payload, status_code = submit_turn()
    return jsonify(payload), status_code


@app.post("/api/conversations/<conversation_id>/turns")
def continue_conversation_turn(conversation_id: str):
    payload, status_code = submit_turn(forced_conversation_id=conversation_id)
    return jsonify(payload), status_code


@app.get("/api/conversations/<conversation_id>")
def get_conversation(conversation_id: str):
    ensure_legacy_graph_migration()
    conversation = get_conversation_record(conversation_id)
    if not conversation:
        return jsonify({"detail": "Conversation not found."}), 404

    manage_token = read_text(
        request.args.get("token") or request.headers.get("X-Conversation-Token"),
        240,
    )
    if not can_access_conversation(conversation, manage_token):
        return jsonify({"detail": "Conversation not found or access token is invalid."}), 404

    return jsonify(build_public_conversation(conversation, list_conversation_messages(conversation_id)))


@app.get("/api/search")
def retired_search():
    return jsonify(
        {
            "detail": "Dedicated search has been retired. Use the universal composer to ask or submit something about AI."
        }
    ), 410


@app.get("/api/tickets")
def deprecated_tickets():
    return jsonify([])


@app.post("/api/tickets")
def deprecated_ticket_create():
    return jsonify(
        {
            "detail": "Structured ticket posting has been retired. Use /api/conversations instead."
        }
    ), 410


@app.errorhandler(ValueError)
def handle_value_error(error):
    return jsonify({"detail": str(error)}), 400


@app.errorhandler(PermissionError)
def handle_permission_error(error):
    return jsonify({"detail": str(error)}), 403


@app.errorhandler(HTTPException)
def handle_http_exception(error):
    return jsonify({"detail": error.description}), error.code


@app.errorhandler(Exception)
def handle_unexpected_error(error):
    app.logger.exception("Unexpected server error")
    return jsonify({"detail": "Unexpected server error."}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8000")), debug=True)
