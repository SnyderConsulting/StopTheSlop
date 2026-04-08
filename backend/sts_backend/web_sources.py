from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from .common import normalize_domain, read_text, validate_public_import_url
from .config import WEB_IMPORT_USER_AGENT


def read_meta_content(soup: BeautifulSoup, *names: str) -> str:
    for name in names:
        tag = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
        content = read_text((tag or {}).get("content", ""), 500)
        if content:
            return content
    return ""


def read_query_list(env_name: str, default: list[str]) -> list[str]:
    import os

    configured = [read_text(item, 200) for item in os.getenv(env_name, "").splitlines()]
    cleaned = [item for item in configured if item]
    return cleaned or default[:]


def infer_web_source_type(source_url: str, domain: str = "", og_type: str = "") -> str:
    normalized_domain = normalize_domain(domain or urlparse(read_text(source_url, 1800)).hostname or "")
    path = (urlparse(read_text(source_url, 1800)).path or "").lower()
    normalized_og_type = read_text(og_type, 120).lower()

    if normalized_domain in {"youtube.com", "youtu.be", "vimeo.com", "tiktok.com"}:
        return "video"
    if normalized_domain in {"reddit.com", "news.ycombinator.com", "x.com", "twitter.com", "bsky.app", "threads.net"}:
        return "conversation"
    if normalized_domain == "github.com" and ("/issues/" in path or "/discussions/" in path or "/pull/" in path):
        return "conversation"
    if "video" in normalized_og_type:
        return "video"
    if normalized_domain in {"medium.com", "substack.com"} or ".substack.com" in normalized_domain:
        return "blog"
    if normalized_og_type == "article":
        return "article"
    return "article"


def extract_youtube_thumbnail(source_url: str) -> str:
    parsed = urlparse(read_text(source_url, 1800))
    hostname = normalize_domain(parsed.hostname or "")
    video_id = ""
    if hostname == "youtu.be":
        video_id = parsed.path.strip("/").split("/")[0]
    elif hostname == "youtube.com":
        video_id = read_text(parse_qs(parsed.query).get("v", [""])[0], 120)
    if not video_id:
        return ""
    return f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"


def build_web_post_id(source_url: str) -> str:
    import hashlib

    digest = hashlib.sha1(read_text(source_url, 1800).encode("utf-8")).hexdigest()[:18]
    return f"web-{digest}"


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
    image_url = read_meta_content(soup, "og:image", "twitter:image")
    if image_url:
        image_url = urljoin(final_url, image_url)
    published_at = read_meta_content(
        soup,
        "article:published_time",
        "og:published_time",
        "parsely-pub-date",
        "pubdate",
    )
    author_name = read_meta_content(soup, "author", "article:author", "parsely-author")
    og_type = read_meta_content(soup, "og:type")
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
    if not image_url:
        image_url = extract_youtube_thumbnail(final_url)

    return {
        "url": final_url,
        "domain": domain,
        "title": read_text(title or domain or "Imported page", 180),
        "description": read_text(description, 320),
        "excerpt": read_text(excerpt, 1200),
        "siteName": site_name,
        "sourceLabel": present_import_source_label(domain, site_name, final_url),
        "sourceType": infer_web_source_type(final_url, domain, og_type),
        "imageUrl": read_text(image_url, 1800),
        "publishedAt": read_text(published_at, 80),
        "authorName": read_text(author_name, 120),
    }
