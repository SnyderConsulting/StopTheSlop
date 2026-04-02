from __future__ import annotations

import contextlib
import json
import os
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route


SERVER_NAME = "Stop The Slop MCP"
DEFAULT_SITE_API_BASE = "https://stoptheslop-api.ashymoss-163410b1.centralus.azurecontainerapps.io"
DEFAULT_SITE_URL = "https://stoptheslopweb26032543.z19.web.core.windows.net"
DEFAULT_TIMEOUT_SECONDS = float(os.getenv("STS_API_TIMEOUT_SECONDS", "20") or 20)


TOOL_CATALOG = [
    {
        "name": "get_site_status",
        "access": "read",
        "description": "Check Stop The Slop health, AI readiness, and high-level ingestion metrics.",
    },
    {
        "name": "get_public_feed",
        "access": "read",
        "description": "Read recent public takeaways, guides, hot topics, questions, and tracked entities.",
    },
    {
        "name": "search_topics",
        "access": "read",
        "description": "Search public topic pages by product, model, vendor, workflow, or claim language.",
    },
    {
        "name": "get_topic",
        "access": "read",
        "description": "Read a topic page with claims, guides, questions, and related subjects.",
    },
    {
        "name": "submit_signal",
        "access": "write",
        "description": "Submit a new AI question, complaint, guide, or observation into the site ingestion pipeline.",
    },
    {
        "name": "continue_conversation",
        "access": "write",
        "description": "Append a follow-up turn to a private conversation by using its manage token.",
    },
    {
        "name": "get_conversation",
        "access": "private-read",
        "description": "Read a private conversation thread by using its conversation id and manage token.",
    },
]

RESOURCE_CATALOG = [
    {
        "uri": "sts://server",
        "description": "Server metadata, connection details, and tool catalog.",
    },
    {
        "uri": "sts://feed",
        "description": "A recent snapshot of the public takeaway feed.",
    },
    {
        "uri": "sts://topic/{entity_id}",
        "description": "A topic page snapshot for a specific Stop The Slop entity id.",
    },
]


def read_text(value: Any, limit: int = 4000) -> str:
    return str(value or "").strip()[:limit]


def read_api_base_url() -> str:
    return read_text(os.getenv("STS_API_BASE_URL"), 300).rstrip("/") or DEFAULT_SITE_API_BASE


def read_site_url() -> str:
    return read_text(os.getenv("STS_SITE_URL"), 300).rstrip("/") or DEFAULT_SITE_URL


def read_public_base_url() -> str:
    return read_text(os.getenv("STS_MCP_PUBLIC_BASE_URL"), 300).rstrip("/")


def allowed_origins() -> list[str]:
    raw = read_text(os.getenv("STS_MCP_ALLOWED_ORIGINS"), 2000) or "*"
    origins = [part.strip() for part in raw.split(",") if part.strip()]
    return origins or ["*"]


def clamp_limit(value: int, default: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, min(parsed, maximum))


def trim_feed_items(items: list[dict[str, Any]], limit: int, kind: str = "") -> list[dict[str, Any]]:
    normalized_kind = read_text(kind, 40).lower()
    filtered = [
        item
        for item in items
        if not normalized_kind or read_text(item.get("kind"), 40).lower() == normalized_kind
    ]
    return filtered[:limit]


def compact_messages(messages: list[dict[str, Any]], limit: int = 8) -> list[dict[str, Any]]:
    trimmed = messages[-limit:]
    return [
        {
            "id": read_text(message.get("id"), 120),
            "role": read_text(message.get("role"), 40),
            "text": read_text(message.get("text"), 6000),
            "createdAt": read_text(message.get("createdAt"), 80),
            "citations": message.get("citations", [])[:6],
            "graphUpdates": message.get("graphUpdates", [])[:8],
        }
        for message in trimmed
    ]


async def request_site_api(
    method: str,
    path: str,
    *,
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> Any:
    async with httpx.AsyncClient(
        base_url=read_api_base_url(),
        timeout=DEFAULT_TIMEOUT_SECONDS,
        follow_redirects=True,
    ) as client:
        response = await client.request(method, path, json=payload, headers=headers or {})

    content_type = response.headers.get("content-type", "")
    body: dict[str, Any] | None = None
    if "application/json" in content_type:
        body = response.json()

    if not response.is_success:
        detail = ""
        if isinstance(body, dict):
            detail = read_text(body.get("detail"), 280)
        if not detail:
            detail = read_text(response.text, 280) or f"HTTP {response.status_code}"
        raise RuntimeError(f"Stop The Slop API error: {detail}")

    return body or {}


def server_info_payload() -> dict[str, Any]:
    public_base = read_public_base_url()
    mcp_endpoint = f"{public_base}/mcp" if public_base else ""
    return {
        "serverName": SERVER_NAME,
        "transport": "streamable-http",
        "siteUrl": read_site_url(),
        "siteApiBaseUrl": read_api_base_url(),
        "publicBaseUrl": public_base,
        "mcpEndpoint": mcp_endpoint,
        "toolCatalog": TOOL_CATALOG,
        "resourceCatalog": RESOURCE_CATALOG,
    }


mcp = FastMCP(
    SERVER_NAME,
    instructions=(
        "Use these tools to read Stop The Slop public knowledge, inspect topics, and write new "
        "signals into the same moderation and ingestion pipeline used by the website. "
        "Raw submissions are private; public output is graph-derived."
    ),
    stateless_http=True,
    json_response=True,
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)


@mcp.tool()
async def get_site_status() -> dict[str, Any]:
    """Check Stop The Slop health, AI readiness, and current public graph metrics."""
    health = await request_site_api("GET", "/healthz")
    feed = await request_site_api("GET", "/api/feed")
    config = await request_site_api("GET", "/api/config")
    return {
        "server": server_info_payload(),
        "siteHealth": health,
        "siteConfig": {
            "aiConfigured": bool(config.get("aiConfigured")),
            "authEnabled": bool(config.get("authEnabled")),
            "anonymousPosting": bool(config.get("anonymousPosting")),
        },
        "metrics": feed.get("metrics", {}),
    }


@mcp.tool()
async def get_public_feed(limit: int = 12, kind: str = "") -> dict[str, Any]:
    """Read recent public takeaways. Optional kind values include claim, guide, question, cluster, and entity."""
    payload = await request_site_api("GET", "/api/feed")
    capped_limit = clamp_limit(limit, default=12, maximum=24)
    return {
        "metrics": payload.get("metrics", {}),
        "items": trim_feed_items(payload.get("items", []), capped_limit, kind),
        "featuredEntities": payload.get("featuredEntities", [])[: min(capped_limit, 8)],
    }


@mcp.tool()
async def search_topics(query: str, limit: int = 8) -> dict[str, Any]:
    """Search topic pages by model, tool, vendor, workflow, or claim language."""
    search_query = read_text(query, 180)
    if not search_query:
        raise ValueError("Provide a non-empty topic query.")
    capped_limit = clamp_limit(limit, default=8, maximum=18)
    params = str(httpx.QueryParams({"q": search_query}))
    payload = await request_site_api("GET", f"/api/entities?{params}")
    items = payload if isinstance(payload, list) else []
    return {"query": search_query, "items": items[:capped_limit]}


@mcp.tool()
async def get_topic(entity_id: str) -> dict[str, Any]:
    """Read one topic page, including claims, guides, questions, and related topics."""
    topic_id = read_text(entity_id, 160)
    if not topic_id:
        raise ValueError("Provide an entity id from the wiki or search_topics.")
    return await request_site_api("GET", f"/api/entities/{topic_id}")


@mcp.tool()
async def submit_signal(text: str) -> dict[str, Any]:
    """Submit a new AI question, complaint, recommendation, or guide. Paste URLs inline in the text if needed."""
    body = read_text(text, 6000)
    if not body:
        raise ValueError("Provide a non-empty submission.")
    conversation = await request_site_api("POST", "/api/conversations", payload={"text": body})
    return {
        "conversationId": read_text(conversation.get("id"), 160),
        "title": read_text(conversation.get("title"), 160),
        "anonymousHandle": read_text(conversation.get("anonymousHandle"), 120),
        "manageToken": read_text(conversation.get("manageToken"), 240),
        "messages": compact_messages(conversation.get("messages", [])),
    }


@mcp.tool()
async def continue_conversation(conversation_id: str, manage_token: str, text: str) -> dict[str, Any]:
    """Append a follow-up turn to a private thread. Requires the manage token returned when the thread was created."""
    conv_id = read_text(conversation_id, 160)
    token = read_text(manage_token, 240)
    body = read_text(text, 6000)
    if not conv_id or not token or not body:
        raise ValueError("conversation_id, manage_token, and text are all required.")
    conversation = await request_site_api(
        "POST",
        f"/api/conversations/{conv_id}/turns",
        payload={"text": body, "manageToken": token},
    )
    return {
        "conversationId": read_text(conversation.get("id"), 160),
        "title": read_text(conversation.get("title"), 160),
        "anonymousHandle": read_text(conversation.get("anonymousHandle"), 120),
        "messages": compact_messages(conversation.get("messages", [])),
    }


@mcp.tool()
async def get_conversation(conversation_id: str, manage_token: str, max_messages: int = 12) -> dict[str, Any]:
    """Read a private thread by using the conversation id and its manage token."""
    conv_id = read_text(conversation_id, 160)
    token = read_text(manage_token, 240)
    if not conv_id or not token:
        raise ValueError("conversation_id and manage_token are required.")
    conversation = await request_site_api(
        "GET",
        f"/api/conversations/{conv_id}",
        headers={"X-Conversation-Token": token},
    )
    return {
        "conversationId": read_text(conversation.get("id"), 160),
        "title": read_text(conversation.get("title"), 160),
        "anonymousHandle": read_text(conversation.get("anonymousHandle"), 120),
        "createdAt": read_text(conversation.get("createdAt"), 80),
        "updatedAt": read_text(conversation.get("updatedAt"), 80),
        "messages": compact_messages(conversation.get("messages", []), clamp_limit(max_messages, 12, 30)),
    }


@mcp.resource("sts://server")
def read_server_resource() -> str:
    """Read Stop The Slop MCP server metadata and connection details."""
    return json.dumps(server_info_payload(), indent=2)


@mcp.resource("sts://feed")
async def read_feed_resource() -> str:
    """Read a recent snapshot of the public takeaway feed."""
    payload = await get_public_feed(limit=10)
    return json.dumps(payload, indent=2)


@mcp.resource("sts://topic/{entity_id}")
async def read_topic_resource(entity_id: str) -> str:
    """Read a specific topic page snapshot by entity id."""
    payload = await get_topic(entity_id)
    return json.dumps(payload, indent=2)


@mcp.prompt()
def research_topic_with_sts(entity_or_query: str) -> str:
    """Prompt template for researching an AI topic with Stop The Slop."""
    return (
        "Use the Stop The Slop MCP tools to inspect this AI topic with provenance.\n"
        f"Topic: {entity_or_query}\n"
        "1. If you only have a name, call search_topics first.\n"
        "2. Read the topic page with get_topic.\n"
        "3. Use get_public_feed if you need recent cross-topic context.\n"
        "4. Summarize what is repeated, what is contested, and what still looks thinly supported."
    )


async def homepage(_request) -> JSONResponse:
    return JSONResponse(
        {
            "service": "stoptheslop-mcp",
            "status": "ok",
            "mcpEndpoint": server_info_payload().get("mcpEndpoint"),
            "infoEndpoint": "/info",
            "healthEndpoint": "/healthz",
        }
    )


async def info(_request) -> JSONResponse:
    return JSONResponse(server_info_payload())


async def healthcheck(_request) -> JSONResponse:
    try:
        upstream = await request_site_api("GET", "/healthz")
        return JSONResponse(
            {
                "ok": True,
                "server": "stoptheslop-mcp",
                "transport": "streamable-http",
                "siteApiReachable": True,
                "siteHealth": upstream,
            }
        )
    except Exception as error:  # pragma: no cover
        return JSONResponse(
            {
                "ok": False,
                "server": "stoptheslop-mcp",
                "transport": "streamable-http",
                "siteApiReachable": False,
                "detail": read_text(error, 280),
            },
            status_code=503,
        )


@contextlib.asynccontextmanager
async def lifespan(_app: Starlette):
    async with mcp.session_manager.run():
        yield


app = Starlette(
    routes=[
        Route("/", endpoint=homepage),
        Route("/info", endpoint=info),
        Route("/healthz", endpoint=healthcheck),
        Mount("/", app=mcp.streamable_http_app()),
    ],
    lifespan=lifespan,
)

app = CORSMiddleware(
    app,
    allow_origins=allowed_origins(),
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["Mcp-Session-Id"],
)
