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
import time
import unicodedata
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urljoin, urlparse

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

from sts_backend.common import (
    build_anonymous_handle,
    build_row_key,
    dedupe_texts,
    filter_publishable_subject_names,
    has_ai_topic_signal,
    hash_token,
    is_blocked_entity_name,
    merge_unique,
    normalize_domain,
    normalize_for_match,
    normalize_question_text,
    now_iso,
    read_choice,
    read_json,
    read_text,
    safe_json_loads,
    should_keep_claim_text,
    should_keep_entity_candidate,
    should_keep_guide,
    should_keep_question_text,
    slugify,
    split_words,
    turn_looks_like_question,
    validate_public_import_url,
)
from sts_backend.config import (
    ANSWER_PARTITION_KEY,
    CLAIM_PARTITION_KEY,
    CLAIM_TYPE_OPTIONS,
    CONVERSATION_PARTITION_KEY,
    CRAWL_RUN_PARTITION_KEY,
    DEFAULT_LIVE_WEB_FEED_QUERIES,
    DEFAULT_WEB_CRAWL_QUERIES,
    ENTITY_PARTITION_KEY,
    ENTITY_TYPE_OPTIONS,
    GUIDE_PARTITION_KEY,
    INTAKE_SCHEMA,
    LEGACY_TICKET_PARTITION_KEY,
    LIVE_WEB_CACHE_TTL_SECONDS,
    MAX_EXTRACTED_TEXT_CHARS,
    MAX_FEED_ITEMS,
    META_PARTITION_KEY,
    MODERATION_ACTIONS,
    ONBOARDING_PARTITION_KEY,
    ONBOARDING_USE_CASE_OPTIONS,
    PERPLEXITY_SEARCH_ENDPOINT,
    POST_PARTITION_KEY,
    PUBLIC_ITEM_KINDS,
    PUBLIC_ENTITY_CREATION_TYPES,
    QUESTION_PARTITION_KEY,
    QUESTION_STATUS_OPTIONS,
    REACTION_PARTITION_PREFIX,
    REPLY_SCHEMA,
    ROOT_DIR,
    SESSION_SALT,
    SOURCE_PARTITION_KEY,
    SOURCE_BLOB_CONTAINER,
    STANCE_OPTIONS,
    TABLE_NAME,
    TOOL_FAMILY_METADATA,
    USER_PARTITION_KEY,
    WEB_IMPORT_USER_AGENT,
    WEB_POST_PARTITION_KEY,
    WEB_POST_SCHEMA,
)
from sts_backend.records import (
    answer_record_to_table,
    build_entity_description,
    build_entity_source_links,
    claim_record_to_table,
    conversation_record_to_table,
    crawl_run_record_to_table,
    entity_record_to_table,
    guide_record_to_table,
    message_partition_key,
    message_record_to_table,
    onboarding_record_to_table,
    post_record_to_table,
    question_record_to_table,
    reaction_record_to_table,
    source_record_to_table,
    table_to_claim_record,
    table_to_conversation_record,
    table_to_entity_record,
    table_to_guide_record,
    table_to_message_record,
    table_to_post_record,
    table_to_question_record,
    table_to_reaction_record,
    table_to_source_record,
    table_to_user_record,
    table_to_web_post_record,
    user_record_to_table,
    web_post_record_to_table,
)
from sts_backend.storage import (
    get_row,
    get_table_client,
    list_rows,
    upsert_row,
    upload_blob_bytes,
)
from sts_backend.web_sources import (
    build_web_post_id,
    extract_web_import_preview,
    extract_youtube_thumbnail,
    infer_web_source_type,
    present_import_source_label,
    read_query_list,
)

try:
    from openai import AzureOpenAI
except ImportError:  # pragma: no cover
    AzureOpenAI = None

try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover
    PdfReader = None



app = Flask(__name__)
app.config["JSON_SORT_KEYS"] = False

allowed_origins = [
    origin.strip()
    for origin in os.getenv("ALLOWED_ORIGINS", "").split(",")
    if origin.strip()
]
CORS(app, resources={r"/api/*": {"origins": allowed_origins or "*"}})

_openai_client = None
_openai_checked = False
_migration_checked = False
_live_web_feed_cache = {"expires_at": 0.0, "items": []}
_background_executor = ThreadPoolExecutor(
    max_workers=max(1, int(os.getenv("BACKGROUND_WORKERS", "2") or "2"))
)

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


def build_live_web_feed_items(force_refresh: bool = False) -> list[dict[str, Any]]:
    cache = _live_web_feed_cache
    if not force_refresh and cache["expires_at"] > time.time():
        return list(cache["items"])

    discovered: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for query in read_query_list("LIVE_WEB_FEED_QUERIES", DEFAULT_LIVE_WEB_FEED_QUERIES)[:6]:
        for result in search_live_web_results(query, max_results=2):
            source_url = read_text(result.get("url"), 500)
            if not source_url or source_url in seen_urls:
                continue
            seen_urls.add(source_url)
            discovered.append(
                {
                    "id": f"live-{build_web_post_id(source_url)}",
                    "kind": "live_web",
                    "title": read_text(result.get("title"), 120),
                    "summary": read_text(result.get("summary"), 220),
                    "body": read_text(result.get("summary"), 420),
                    "sourceUrl": source_url,
                    "sourceDomain": read_text(result.get("sourceDomain"), 120),
                    "sourceLabel": present_import_source_label(
                        read_text(result.get("sourceDomain"), 120),
                        "",
                        source_url,
                    ),
                    "sourceType": infer_web_source_type(source_url, read_text(result.get("sourceDomain"), 120)),
                    "mediaKind": infer_web_source_type(source_url, read_text(result.get("sourceDomain"), 120)),
                    "mediaCaption": "Live from the web",
                    "query": query,
                    "authorLabel": "",
                    "imageUrl": extract_youtube_thumbnail(source_url),
                    "createdAt": now_iso(),
                    "updatedAt": now_iso(),
                    "tags": dedupe_texts(split_words(query), limit=4),
                }
            )

    items = discovered[:8]
    cache["items"] = items
    cache["expires_at"] = time.time() + LIVE_WEB_CACHE_TTL_SECONDS
    return list(items)


def build_preview_from_search_result(result: dict[str, Any]) -> dict[str, Any]:
    source_url = read_text(result.get("url"), 1800)
    domain = normalize_domain(urlparse(source_url).hostname or "")
    preview = {
        "url": source_url,
        "domain": domain,
        "title": read_text(result.get("title"), 180),
        "description": read_text(result.get("summary"), 320),
        "excerpt": read_text(result.get("summary"), 1200),
        "siteName": present_import_source_label(domain, "", source_url),
        "sourceLabel": present_import_source_label(domain, "", source_url),
        "sourceType": infer_web_source_type(source_url, domain),
        "imageUrl": extract_youtube_thumbnail(source_url),
        "publishedAt": "",
        "authorName": "",
    }
    try:
        fetched = extract_web_import_preview(source_url)
    except Exception:
        return preview
    preview.update({key: value for key, value in fetched.items() if value})
    return preview


def crawl_web_feed(
    queries: list[str] | None = None,
    *,
    max_results_per_query: int | None = None,
    max_items: int | None = None,
) -> dict[str, Any]:
    active_queries = [read_text(item, 200) for item in (queries or read_query_list("WEB_CRAWL_QUERIES", DEFAULT_WEB_CRAWL_QUERIES))]
    active_queries = [item for item in active_queries if item]
    if not active_queries:
        return {"queryCount": 0, "discoveredCount": 0, "storedCount": 0, "items": []}

    per_query = max(1, min(int(max_results_per_query or os.getenv("WEB_CRAWL_MAX_RESULTS_PER_QUERY", "4") or 4), 6))
    item_limit = max(1, min(int(max_items or os.getenv("WEB_CRAWL_MAX_ITEMS", "16") or 16), 32))
    discovered: list[tuple[str, dict[str, Any]]] = []
    seen_urls: set[str] = set()

    for query in active_queries:
        results = search_live_web_results(query, max_results=per_query)
        for result in results:
            source_url = read_text(result.get("url"), 1800)
            if not source_url or source_url in seen_urls:
                continue
            seen_urls.add(source_url)
            discovered.append((query, result))
            if len(discovered) >= item_limit:
                break
        if len(discovered) >= item_limit:
            break

    stored_items: list[dict[str, Any]] = []
    for query, result in discovered:
        preview = build_preview_from_search_result(result)
        generated = compose_web_post(preview, query, read_text(result.get("summary"), 320))
        stored_items.append(upsert_web_post_record(preview, generated, query))

    persist_crawl_run(len(active_queries), len(discovered), len(stored_items), "Daily web crawl")
    return {
        "queryCount": len(active_queries),
        "discoveredCount": len(discovered),
        "storedCount": len(stored_items),
        "items": stored_items,
    }


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


def list_posts() -> list[dict[str, Any]]:
    posts = [table_to_post_record(row) for row in list_rows(POST_PARTITION_KEY)]
    return sorted(posts, key=lambda item: (item.get("createdAt", ""), item.get("id", "")), reverse=True)


def list_web_posts(limit: int | None = None) -> list[dict[str, Any]]:
    items = [table_to_web_post_record(row) for row in list_rows(WEB_POST_PARTITION_KEY)]
    items = sorted(items, key=lambda item: (item.get("updatedAt", ""), item.get("id", "")), reverse=True)
    return items[:limit] if limit else items


def build_reaction_partition_key(item_id: str) -> str:
    digest = hashlib.sha1(read_text(item_id, 240).encode("utf-8")).hexdigest()[:24]
    return f"{REACTION_PARTITION_PREFIX}-{digest}"


def normalize_reaction_emoji(value: Any) -> str:
    text = unicodedata.normalize("NFC", read_text(value, 24)).replace(" ", "")
    if not text or any(char in text for char in ("\n", "\r", "\t")):
        return ""
    if any("a" <= char.lower() <= "z" for char in text):
        return ""

    has_emoji_signal = False
    for char in text:
        codepoint = ord(char)
        category = unicodedata.category(char)
        if codepoint in {0x200D, 0xFE0E, 0xFE0F, 0x20E3}:
            has_emoji_signal = True
            continue
        if 0x1F1E6 <= codepoint <= 0x1F1FF:
            has_emoji_signal = True
            continue
        if 0x1F3FB <= codepoint <= 0x1F3FF:
            has_emoji_signal = True
            continue
        if category.startswith("S") and codepoint > 127:
            has_emoji_signal = True
            continue
        if category in {"Mn", "Cf"}:
            has_emoji_signal = True
            continue
        if category.startswith("N") and codepoint <= 127:
            continue
        if category.startswith("P") and char == "#":
            continue
        return ""

    return text if has_emoji_signal else ""


def find_reactable_item(item_id: str) -> dict[str, Any] | None:
    post = get_row(POST_PARTITION_KEY, item_id)
    if post:
        return {"id": item_id, "kind": "post"}

    web_post = get_row(WEB_POST_PARTITION_KEY, item_id)
    if web_post:
        return {"id": item_id, "kind": "web_post"}

    for item in build_live_web_feed_items():
        if item.get("id") == item_id:
            return {"id": item_id, "kind": "live_web"}
    return None


def list_reaction_records(item_id: str) -> list[dict[str, Any]]:
    partition_key = build_reaction_partition_key(item_id)
    rows = list_rows(partition_key)
    return [table_to_reaction_record(row) for row in rows if read_text(row.get("itemId"), 240) == item_id]


def build_reaction_summary(item_id: str, viewer_id: str = "") -> dict[str, Any]:
    viewer_hash = hash_token(viewer_id)[:48] if viewer_id else ""
    counts: dict[str, int] = defaultdict(int)
    viewer_emojis: list[str] = []

    for record in list_reaction_records(item_id):
        emojis = dedupe_texts(
            [normalize_reaction_emoji(item) for item in record.get("emojis", [])],
            limit=12,
        )
        if record.get("visitorHash") == viewer_hash:
            viewer_emojis = emojis
        for emoji in emojis:
            if emoji:
                counts[emoji] += 1

    items = [
        {
            "emoji": emoji,
            "count": count,
            "viewer": emoji in viewer_emojis,
        }
        for emoji, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]
    return {
        "items": items[:8],
        "viewerEmojis": viewer_emojis[:12],
        "totalCount": sum(counts.values()),
    }


def attach_reaction_summaries(items: list[dict[str, Any]], viewer_id: str = "") -> list[dict[str, Any]]:
    hydrated: list[dict[str, Any]] = []
    for item in items:
        item_id = read_text(item.get("id"), 240)
        enriched = dict(item)
        enriched["reactions"] = build_reaction_summary(item_id, viewer_id) if item_id else {
            "items": [],
            "viewerEmojis": [],
            "totalCount": 0,
        }
        hydrated.append(enriched)
    return hydrated


def toggle_reaction(item_id: str, item_kind: str, visitor_id: str, emoji: str) -> dict[str, Any]:
    normalized_item_id = read_text(item_id, 240)
    normalized_emoji = normalize_reaction_emoji(emoji)
    normalized_visitor_id = read_text(visitor_id, 120)
    if not normalized_item_id:
        raise ValueError("Missing item id.")
    if item_kind not in {"post", "web_post", "live_web"}:
        raise ValueError("Unsupported reaction target.")
    if not normalized_visitor_id:
        raise ValueError("Missing visitor id.")
    if not normalized_emoji:
        raise ValueError("Pick a real emoji.")

    partition_key = build_reaction_partition_key(normalized_item_id)
    visitor_hash = hash_token(normalized_visitor_id)[:48]
    existing = get_row(partition_key, visitor_hash)
    record = table_to_reaction_record(existing) if existing else {
        "partitionKey": partition_key,
        "visitorHash": visitor_hash,
        "itemId": normalized_item_id,
        "itemKind": item_kind,
        "emojis": [],
        "createdAt": now_iso(),
        "updatedAt": now_iso(),
    }

    current = dedupe_texts(
        [normalize_reaction_emoji(item) for item in record.get("emojis", [])],
        limit=12,
    )
    if normalized_emoji in current:
        current = [item for item in current if item != normalized_emoji]
    else:
        current = dedupe_texts([normalized_emoji, *current], limit=12)
    record["emojis"] = current
    record["updatedAt"] = now_iso()
    upsert_row(reaction_record_to_table(record))
    return build_reaction_summary(normalized_item_id, normalized_visitor_id)


def create_post_record(
    text: str,
    submitter_id: str,
    anonymous_handle: str,
    *,
    conversation_id: str = "",
) -> dict[str, Any]:
    body = read_text(text, 6000)
    if not body:
        raise ValueError("Type something before posting.")

    summary = read_text(" ".join(body.split()), 220)
    record = {
        "id": build_row_key("post"),
        "conversationId": conversation_id,
        "submitterId": submitter_id,
        "anonymousHandle": anonymous_handle,
        "text": body,
        "summary": summary,
        "createdAt": now_iso(),
        "updatedAt": now_iso(),
    }
    upsert_row(post_record_to_table(record))
    return record


def build_web_post_fallback(
    preview: dict[str, Any],
    query_text: str,
    search_summary: str = "",
) -> dict[str, Any]:
    source_type = read_text(preview.get("sourceType"), 40) or "article"
    title = read_text(preview.get("title"), 120)
    description = read_text(preview.get("description"), 320)
    excerpt = read_text(preview.get("excerpt"), 900)
    body = read_text(search_summary or excerpt or description, 560)
    tags = dedupe_texts(
        [
            source_type,
            preview.get("sourceLabel", ""),
            *split_words(query_text)[:3],
        ],
        limit=5,
    )
    return {
        "title": title or "Fresh AI slop source",
        "summary": read_text(description or search_summary or excerpt, 220) or title,
        "body": body or title,
        "angle": read_text(query_text, 120) or "Latest web signal",
        "source_type": source_type,
        "media_caption": read_text(preview.get("sourceLabel"), 80) or "Source preview",
        "tags": tags,
    }


def compose_web_post(
    preview: dict[str, Any],
    query_text: str,
    search_summary: str = "",
) -> dict[str, Any]:
    fallback = build_web_post_fallback(preview, query_text, search_summary)
    if not can_use_ai():
        return fallback

    messages = [
        {
            "role": "system",
            "content": (
                "You are writing a tight feed post for Stop The Slop, a public board about AI failures, spam, drift, hype, and messy real-world behavior. "
                "Turn the source into a bespoke post that feels native to the board. Stay factual and grounded in the supplied source only. "
                "Do not invent quotes, claims, dates, or details. Keep the title punchy, the summary scannable, and the body to one short paragraph. "
                "Treat blog posts, videos, complaints, and forum discussions as valid source types. Tags should be short and reusable."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "queryText": read_text(query_text, 180),
                    "preview": {
                        "url": read_text(preview.get("url"), 400),
                        "title": read_text(preview.get("title"), 180),
                        "description": read_text(preview.get("description"), 320),
                        "excerpt": read_text(preview.get("excerpt"), 1200),
                        "sourceLabel": read_text(preview.get("sourceLabel"), 120),
                        "sourceType": read_text(preview.get("sourceType"), 40),
                        "authorName": read_text(preview.get("authorName"), 120),
                    },
                    "searchSummary": read_text(search_summary, 320),
                },
                ensure_ascii=True,
            ),
        },
    ]
    data = call_ai_json(messages, WEB_POST_SCHEMA, max_tokens=800)
    if not data:
        return fallback
    return {
        "title": read_text(data.get("title"), 120) or fallback["title"],
        "summary": read_text(data.get("summary"), 220) or fallback["summary"],
        "body": read_text(data.get("body"), 560) or fallback["body"],
        "angle": read_text(data.get("angle"), 120) or fallback["angle"],
        "source_type": read_text(data.get("source_type"), 40) or fallback["source_type"],
        "media_caption": read_text(data.get("media_caption"), 80) or fallback["media_caption"],
        "tags": dedupe_texts(data.get("tags", []), limit=6) or fallback["tags"],
    }


def upsert_web_post_record(
    preview: dict[str, Any],
    generated: dict[str, Any],
    query_text: str,
) -> dict[str, Any]:
    source_url = read_text(preview.get("url"), 1800)
    if not source_url:
        raise ValueError("Web post is missing a source URL.")

    record_id = build_web_post_id(source_url)
    existing = get_row(WEB_POST_PARTITION_KEY, record_id)
    current = table_to_web_post_record(existing) if existing else {
        "id": record_id,
        "createdAt": now_iso(),
    }
    record = {
        **current,
        "id": record_id,
        "title": read_text(generated.get("title"), 120) or current.get("title", ""),
        "summary": read_text(generated.get("summary"), 220) or current.get("summary", ""),
        "body": read_text(generated.get("body"), 560) or current.get("body", ""),
        "angle": read_text(generated.get("angle"), 120) or current.get("angle", ""),
        "query": read_text(query_text, 180) or current.get("query", ""),
        "sourceUrl": source_url,
        "sourceDomain": read_text(preview.get("domain"), 120) or current.get("sourceDomain", ""),
        "sourceLabel": read_text(preview.get("sourceLabel"), 120) or current.get("sourceLabel", ""),
        "sourceType": read_text(generated.get("source_type"), 40)
        or read_text(preview.get("sourceType"), 40)
        or current.get("sourceType", "article"),
        "authorLabel": read_text(preview.get("authorName"), 120) or current.get("authorLabel", ""),
        "mediaKind": read_text(preview.get("sourceType"), 40) or current.get("mediaKind", ""),
        "mediaCaption": read_text(generated.get("media_caption"), 80) or current.get("mediaCaption", ""),
        "imageUrl": read_text(preview.get("imageUrl"), 1800) or current.get("imageUrl", ""),
        "tags": dedupe_texts([*(current.get("tags", []) or []), *(generated.get("tags", []) or [])], limit=8),
        "updatedAt": now_iso(),
    }
    upsert_row(web_post_record_to_table(record))
    return record


def persist_crawl_run(query_count: int, discovered_count: int, stored_count: int, notes: str = "") -> dict[str, Any]:
    record = {
        "id": build_row_key("crawl"),
        "queryCount": int(query_count or 0),
        "discoveredCount": int(discovered_count or 0),
        "storedCount": int(stored_count or 0),
        "notes": read_text(notes, 300),
        "createdAt": now_iso(),
    }
    upsert_row(crawl_run_record_to_table(record))
    return record


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


def build_home_feed_items(viewer_id: str = "") -> list[dict[str, Any]]:
    community_items = [
        {
            "id": post["id"],
            "kind": "post",
            "text": post.get("text", ""),
            "summary": post.get("summary", ""),
            "anonymousHandle": post.get("anonymousHandle", ""),
            "createdAt": post.get("createdAt", ""),
            "updatedAt": post.get("updatedAt", ""),
        }
        for post in list_posts()[:18]
    ]
    curated_web_items = [
        {
            "id": item["id"],
            "kind": "web_post",
            "title": item.get("title", ""),
            "summary": item.get("summary", ""),
            "body": item.get("body", ""),
            "angle": item.get("angle", ""),
            "sourceUrl": item.get("sourceUrl", ""),
            "sourceDomain": item.get("sourceDomain", ""),
            "sourceLabel": item.get("sourceLabel", ""),
            "sourceType": item.get("sourceType", "article"),
            "authorLabel": item.get("authorLabel", ""),
            "mediaKind": item.get("mediaKind", ""),
            "mediaCaption": item.get("mediaCaption", ""),
            "imageUrl": item.get("imageUrl", ""),
            "createdAt": item.get("createdAt", ""),
            "updatedAt": item.get("updatedAt", ""),
            "tags": item.get("tags", []),
        }
        for item in list_web_posts(limit=14)
    ]
    live_web_items = build_live_web_feed_items()[:6]

    mixed: list[dict[str, Any]] = []
    streams = {
        "community": community_items[:],
        "curated": curated_web_items[:],
        "live": live_web_items[:],
    }
    order = ("community", "curated", "community", "live", "curated")
    while len(mixed) < MAX_FEED_ITEMS and any(streams.values()):
        for key in order:
            if streams[key]:
                mixed.append(streams[key].pop(0))
            if len(mixed) >= MAX_FEED_ITEMS:
                break
    return attach_reaction_summaries(mixed[:MAX_FEED_ITEMS], viewer_id)


def build_feed(viewer_id: str = "") -> dict[str, Any]:
    posts = list_posts()
    web_posts = list_web_posts(limit=18)
    live_items = build_live_web_feed_items()
    items = build_home_feed_items(viewer_id)
    return {
        "metrics": {
            "postCount": len(posts),
            "webPostCount": len(web_posts),
            "liveResultCount": len(live_items),
            "sourceCount": len(posts) + len(web_posts),
            "entityCount": 0,
            "claimCount": 0,
            "guideCount": 0,
        },
        "items": items,
        "featuredEntities": [],
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
            "requiredOnboarding": False,
            "acceptedUploads": ["text"],
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


@app.post("/api/posts")
def submit_post():
    submitter_id, anonymous_handle, _user = build_actor_context()
    payload = request.get_json(silent=True) or {}
    text = read_text(payload.get("text"), 6000)
    post = create_post_record(text, submitter_id, anonymous_handle)
    return (
        jsonify(
            {
                "id": post["id"],
                "kind": "post",
                "text": post.get("text", ""),
                "summary": post.get("summary", ""),
                "anonymousHandle": post.get("anonymousHandle", ""),
                "createdAt": post.get("createdAt", ""),
                "updatedAt": post.get("updatedAt", ""),
                "reactions": {"items": [], "viewerEmojis": [], "totalCount": 0},
            }
        ),
        201,
    )


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
    visitor_id = read_text(request.args.get("visitorId"), 120)
    return jsonify(build_feed(visitor_id))


@app.post("/api/items/<item_id>/reactions")
def react_to_item(item_id: str):
    payload = request.get_json(silent=True) or {}
    item = find_reactable_item(item_id)
    if not item:
        return jsonify({"detail": "Feed item not found."}), 404

    user = get_authenticated_user()
    visitor_id = read_text(payload.get("visitorId"), 120) or read_text((user or {}).get("id"), 120)
    emoji = read_text(payload.get("emoji"), 24)
    reactions = toggle_reaction(item["id"], item["kind"], visitor_id, emoji)
    return jsonify({"itemId": item["id"], "kind": item["kind"], "reactions": reactions})


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
