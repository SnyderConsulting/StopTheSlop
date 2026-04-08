from __future__ import annotations

import hashlib
import ipaddress
import json
import re
import secrets
import socket
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from .config import (
    AI_TOPIC_KEYWORDS,
    BLOCKED_CLAIM_PHRASES,
    BLOCKED_ENTITY_EXACT_NAMES,
    BLOCKED_QUESTION_PHRASES,
    BLOCKED_QUESTION_PREFIXES,
    PUBLIC_ENTITY_CREATION_TYPES,
    QUESTION_OPENERS,
)

BLOCKED_ENTITY_NAME_PATTERNS = (
    re.compile(
        r"^(new )?(users?|viewers?|people|children|kids|parents?|musicians?|artists?|journalists?|creators?|researchers?|experts?|lawmakers?|groups?|communities|public figures?)$"
    ),
    re.compile(r"^(the )?(song|songs|video|videos|article|articles|study|studies|report|reports|headline|headlines|story|stories|chart|charts)$"),
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
        return text[:max_length]
    return text


def read_json(value: Any, fallback: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(read_text(value, 20_000))
    except Exception:
        return fallback


def safe_json_loads(value: str, fallback: Any = None) -> Any:
    try:
        return json.loads(value)
    except Exception:
        return fallback if fallback is not None else {}


def dedupe_texts(values: list[Any], limit: int = 12) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for item in values:
        text = read_text(item, 240)
        key = text.casefold()
        if not text or key in seen:
            continue
        seen.add(key)
        deduped.append(text)
        if len(deduped) >= limit:
            break
    return deduped


def normalize_for_match(value: Any) -> str:
    text = read_text(value, 400).lower()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def split_words(value: Any) -> list[str]:
    return [part for part in normalize_for_match(value).split() if part]


def has_ai_topic_signal(value: Any) -> bool:
    normalized = normalize_for_match(value)
    return any(keyword in normalized for keyword in AI_TOPIC_KEYWORDS)


def turn_looks_like_question(value: Any) -> bool:
    text = read_text(value, 400)
    normalized = text.lower().strip()
    return text.endswith("?") or normalized.startswith(QUESTION_OPENERS)


def is_blocked_entity_name(value: Any) -> bool:
    normalized = normalize_for_match(value)
    if not normalized:
        return True
    if normalized in BLOCKED_ENTITY_EXACT_NAMES:
        return True
    return any(pattern.match(normalized) for pattern in BLOCKED_ENTITY_NAME_PATTERNS)


def should_keep_entity_candidate(
    canonical_name: str,
    entity_type: str,
    official_url: str = "",
    source_blob: str = "",
    treat_as_existing: bool = False,
) -> bool:
    normalized = normalize_for_match(canonical_name)
    if not normalized or is_blocked_entity_name(canonical_name):
        return False
    words = split_words(canonical_name)
    if len(words) > 5:
        return False
    if entity_type in PUBLIC_ENTITY_CREATION_TYPES:
        return True
    if official_url:
        return True
    if treat_as_existing and (has_ai_topic_signal(canonical_name) or source_blob):
        return True
    return bool(has_ai_topic_signal(canonical_name) or has_ai_topic_signal(source_blob))


def filter_publishable_subject_names(subject_names: list[str]) -> list[str]:
    return [name for name in dedupe_texts(subject_names, limit=8) if not is_blocked_entity_name(name)]


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


def should_keep_question_text(question_text: str, user_turn_text: str, subject_names: list[str]) -> bool:
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

