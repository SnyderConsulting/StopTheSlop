from __future__ import annotations

import json
from typing import Any

from .common import now_iso, read_json, read_text
from .config import (
    ANSWER_PARTITION_KEY,
    CLAIM_PARTITION_KEY,
    CONVERSATION_PARTITION_KEY,
    CRAWL_RUN_PARTITION_KEY,
    ENTITY_PARTITION_KEY,
    GUIDE_PARTITION_KEY,
    ONBOARDING_PARTITION_KEY,
    POST_PARTITION_KEY,
    QUESTION_PARTITION_KEY,
    SOURCE_PARTITION_KEY,
    USER_PARTITION_KEY,
    WEB_POST_PARTITION_KEY,
)


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


def post_record_to_table(post: dict[str, Any]) -> dict[str, Any]:
    return {
        "PartitionKey": POST_PARTITION_KEY,
        "RowKey": post["id"],
        "conversationId": post.get("conversationId", ""),
        "submitterId": post.get("submitterId", ""),
        "anonymousHandle": post.get("anonymousHandle", ""),
        "text": post.get("text", ""),
        "summary": post.get("summary", ""),
        "createdAt": post.get("createdAt", now_iso()),
        "updatedAt": post.get("updatedAt", now_iso()),
    }


def table_to_post_record(entity: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": entity["RowKey"],
        "conversationId": entity.get("conversationId", ""),
        "submitterId": entity.get("submitterId", ""),
        "anonymousHandle": entity.get("anonymousHandle", ""),
        "text": entity.get("text", ""),
        "summary": entity.get("summary", ""),
        "createdAt": entity.get("createdAt", now_iso()),
        "updatedAt": entity.get("updatedAt", now_iso()),
    }


def web_post_record_to_table(post: dict[str, Any]) -> dict[str, Any]:
    return {
        "PartitionKey": WEB_POST_PARTITION_KEY,
        "RowKey": post["id"],
        "title": post.get("title", ""),
        "summary": post.get("summary", ""),
        "body": post.get("body", ""),
        "angle": post.get("angle", ""),
        "query": post.get("query", ""),
        "sourceUrl": post.get("sourceUrl", ""),
        "sourceDomain": post.get("sourceDomain", ""),
        "sourceLabel": post.get("sourceLabel", ""),
        "sourceType": post.get("sourceType", "article"),
        "authorLabel": post.get("authorLabel", ""),
        "mediaKind": post.get("mediaKind", ""),
        "mediaCaption": post.get("mediaCaption", ""),
        "imageUrl": post.get("imageUrl", ""),
        "tagsJson": json.dumps(post.get("tags", [])),
        "createdAt": post.get("createdAt", now_iso()),
        "updatedAt": post.get("updatedAt", now_iso()),
    }


def table_to_web_post_record(entity: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": entity["RowKey"],
        "title": entity.get("title", ""),
        "summary": entity.get("summary", ""),
        "body": entity.get("body", ""),
        "angle": entity.get("angle", ""),
        "query": entity.get("query", ""),
        "sourceUrl": entity.get("sourceUrl", ""),
        "sourceDomain": entity.get("sourceDomain", ""),
        "sourceLabel": entity.get("sourceLabel", ""),
        "sourceType": entity.get("sourceType", "article"),
        "authorLabel": entity.get("authorLabel", ""),
        "mediaKind": entity.get("mediaKind", ""),
        "mediaCaption": entity.get("mediaCaption", ""),
        "imageUrl": entity.get("imageUrl", ""),
        "tags": read_json(entity.get("tagsJson", "[]"), []),
        "createdAt": entity.get("createdAt", now_iso()),
        "updatedAt": entity.get("updatedAt", now_iso()),
    }


def crawl_run_record_to_table(run: dict[str, Any]) -> dict[str, Any]:
    return {
        "PartitionKey": CRAWL_RUN_PARTITION_KEY,
        "RowKey": run["id"],
        "queryCount": int(run.get("queryCount", 0)),
        "discoveredCount": int(run.get("discoveredCount", 0)),
        "storedCount": int(run.get("storedCount", 0)),
        "notes": run.get("notes", ""),
        "createdAt": run.get("createdAt", now_iso()),
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
