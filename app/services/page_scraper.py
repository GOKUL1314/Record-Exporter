from __future__ import annotations

import asyncio
import json
import re
from typing import Any, Awaitable, Callable
from urllib.parse import urljoin

from bs4 import BeautifulSoup, NavigableString, Tag
import httpx

from app.config import (
    PAGE_FETCH_DELAY_SECONDS,
    PAGE_FETCH_MAX_CONCURRENCY,
    PAGE_FETCH_RETRIES,
    PAGE_FETCH_TIMEOUT_SECONDS,
)
from app.schemas import PageDetails, PageSection
from app.services.url_safety import UnsafeURLError, validate_url

_ZERO_WIDTH_RE = re.compile(r"[\u200b\u200c\u200d\ufeff]")
_WHITESPACE_RE = re.compile(r"[ \t\r\f\v]+")
_HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
_LABEL_CLASS_KEYWORDS = (
    "title-label",
    "card-title",
    "section-title",
    "section-heading",
    "accordion-title",
    "panel-title",
)
_STRIP_TAGS = {
    "script",
    "style",
    "noscript",
    "svg",
    "iframe",
    "template",
    "nav",
    "footer",
    "input",
    "select",
    "textarea",
}
_COOKIE_ATTR_RE = re.compile(r"cookie|consent|gdpr|onetrust|cybot", re.IGNORECASE)
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


def _clean_text(text: str) -> str:
    text = _ZERO_WIDTH_RE.sub("", text or "")
    text = _WHITESPACE_RE.sub(" ", text)
    return text.strip()


def _is_cookie_banner(tag: Tag) -> bool:
    attrs = tag.attrs or {}
    tokens: list[str] = []
    for key in ("id", "class", "aria-label", "data-testid"):
        val = attrs.get(key)
        if isinstance(val, list):
            tokens.extend(str(v) for v in val)
        elif val:
            tokens.append(str(val))
    combined = " ".join(tokens)
    return bool(combined and _COOKIE_ATTR_RE.search(combined))


def _remove_noise(root: Tag) -> None:
    for tag in list(root.find_all(True)):
        if tag.parent is None:
            continue
        name = (tag.name or "").lower()
        if name in _STRIP_TAGS:
            tag.decompose()
            continue
        if tag.get("aria-hidden") == "true" or tag.has_attr("hidden"):
            tag.decompose()
            continue
        if name == "button" and not tag.has_attr("aria-expanded"):
            tag.decompose()
            continue
        if tag.get("role") == "navigation":
            tag.decompose()
            continue
        if _is_cookie_banner(tag):
            tag.decompose()
            continue


def _is_section_marker(tag: Tag) -> bool:
    name = (tag.name or "").lower()
    if name in _HEADING_TAGS or name in ("summary", "legend", "dt"):
        text = _clean_text(tag.get_text(" ", strip=True))
        return 0 < len(text) <= 140
    if tag.get("role") == "heading":
        text = _clean_text(tag.get_text(" ", strip=True))
        return 0 < len(text) <= 140

    classes = tag.get("class") or []
    class_str = " ".join(str(c).lower() for c in classes)
    if any(kw in class_str for kw in _LABEL_CLASS_KEYWORDS):
        # Avoid containers that hold multiple paragraphs or nested headings.
        if tag.find(_HEADING_TAGS) or tag.find(["p", "ul", "ol"]):
            return False
        text = _clean_text(tag.get_text(" ", strip=True))
        return 0 < len(text) <= 80

    return False


def _has_block_children(tag: Tag) -> bool:
    block_names = {
        "div",
        "section",
        "article",
        "main",
        "aside",
        "p",
        "ul",
        "ol",
        "li",
        "blockquote",
        "pre",
        "table",
        "dl",
        "dd",
        "dt",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
    }
    return any(
        isinstance(child, Tag) and (child.name or "").lower() in block_names
        for child in tag.children
    )


def _extract_tokens(root: Tag) -> list[tuple[str, str]]:
    """Walk the DOM tree in order and emit ('heading'|'bullet'|'para', text) tokens."""
    tokens: list[tuple[str, str]] = []

    def walk(node: Tag) -> None:
        if _is_section_marker(node):
            heading = _clean_text(node.get_text(" ", strip=True))
            if heading:
                tokens.append(("heading", heading))
            return

        name = (node.name or "").lower()
        if name == "li":
            # Handle nested lists inside an li without flattening everything into one blob.
            nested_lists = node.find_all(["ul", "ol"], recursive=False)
            if nested_lists:
                direct_parts = []
                for child in node.children:
                    if isinstance(child, Tag) and (child.name or "").lower() in ("ul", "ol"):
                        continue
                    txt = (
                        _clean_text(child.get_text(" ", strip=True))
                        if isinstance(child, Tag)
                        else _clean_text(str(child))
                    )
                    if txt:
                        direct_parts.append(txt)
                if direct_parts:
                    tokens.append(("bullet", " ".join(direct_parts)))
                for nl in nested_lists:
                    walk(nl)
            else:
                text = _clean_text(node.get_text(" ", strip=True))
                if text:
                    tokens.append(("bullet", text))
            return

        if name in ("p", "blockquote", "pre", "dd"):
            # Some sites put headings inside <p> or similar; check first.
            if node.find(_is_section_marker):
                for child in node.children:
                    if isinstance(child, Tag):
                        walk(child)
                return
            text = _clean_text(node.get_text(" ", strip=True))
            if text:
                tokens.append(("para", text))
            return

        if not _has_block_children(node):
            text = _clean_text(node.get_text(" ", strip=True))
            if text:
                tokens.append(("para", text))
            return

        # Mixed inline text + block children inside a container
        inline_buf: list[str] = []

        def flush_inline() -> None:
            if inline_buf:
                joined = _clean_text(" ".join(inline_buf))
                if joined:
                    tokens.append(("para", joined))
                inline_buf.clear()

        for child in node.children:
            if isinstance(child, NavigableString):
                txt = _clean_text(str(child))
                if txt:
                    inline_buf.append(txt)
            elif isinstance(child, Tag):
                cname = (child.name or "").lower()
                if cname in ("span", "a", "strong", "b", "em", "i", "code", "small", "time"):
                    if _is_section_marker(child):
                        flush_inline()
                        walk(child)
                    else:
                        txt = _clean_text(child.get_text(" ", strip=True))
                        if txt:
                            inline_buf.append(txt)
                else:
                    flush_inline()
                    walk(child)
        flush_inline()

    walk(root)
    return tokens


def _tokens_to_sections(tokens: list[tuple[str, str]], page_title: str) -> list[PageSection]:
    raw_sections: list[tuple[str, list[str]]] = []
    current_heading: str | None = None
    current_lines: list[str] = []

    normalized_title = _clean_text(page_title).lower()

    def flush_section() -> None:
        nonlocal current_heading, current_lines
        if current_heading and current_lines:
            raw_sections.append((current_heading, current_lines))
        elif current_lines and not current_heading:
            raw_sections.append(("Overview", current_lines))
        current_lines = []

    for kind, text in tokens:
        if kind == "heading":
            # If the page's top H1 duplicates the page title, keep content under "Overview"
            # only if meaningful paragraphs follow before the next real heading.
            flush_section()
            is_page_title_h1 = (
                normalized_title
                and (
                    text.lower() == normalized_title
                    or normalized_title.startswith(text.lower())
                )
            )
            current_heading = "Overview" if is_page_title_h1 else text
        elif kind == "bullet":
            if current_heading is None:
                current_heading = "Overview"
            current_lines.append(f"- {text}")
        else:
            if current_heading is None:
                current_heading = "Overview"
            # Avoid repeating the heading immediately as the first line.
            if not current_lines and current_heading and text.lower() == current_heading.lower():
                continue
            current_lines.append(text)

    flush_section()

    # Format paragraphs and bullet blocks cleanly and deduplicate identical sections.
    sections: list[PageSection] = []
    seen: set[tuple[str, str]] = set()
    seen_headings_content: dict[str, str] = {}

    for heading, lines in raw_sections:
        formatted_blocks: list[str] = []
        bullet_group: list[str] = []

        for line in lines:
            if line.startswith("- "):
                bullet_group.append(line)
            else:
                if bullet_group:
                    formatted_blocks.append("\n".join(bullet_group))
                    bullet_group = []
                formatted_blocks.append(line)
        if bullet_group:
            formatted_blocks.append("\n".join(bullet_group))

        content = "\n\n".join(formatted_blocks).strip()
        if not content:
            continue

        key = (heading.lower(), content)
        if key in seen:
            continue

        # Skip duplicate responsive blocks with the same heading where content is a duplicate/subset.
        prev_content = seen_headings_content.get(heading.lower())
        if prev_content is not None and (
            content == prev_content or content in prev_content
        ):
            continue

        seen.add(key)
        seen_headings_content[heading.lower()] = content
        sections.append(PageSection(heading=heading, content=content))

    return sections


def _extract_embedded_json_sections(soup: BeautifulSoup) -> tuple[str, list[PageSection]]:
    """Fallback extraction from JSON-LD or __NEXT_DATA__ when DOM text is sparse."""
    title = ""
    sections: list[PageSection] = []

    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = (script.string or "").strip()
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        items = payload if isinstance(payload, list) else [payload]
        for item in items:
            if not isinstance(item, dict):
                continue
            if not title and isinstance(item.get("name"), str):
                title = _clean_text(item["name"])
            desc = item.get("description")
            if isinstance(desc, str) and desc.strip():
                sections.append(PageSection(heading="Description", content=desc.strip()))
            loc = item.get("location")
            if isinstance(loc, dict):
                loc_parts = []
                if isinstance(loc.get("name"), str):
                    loc_parts.append(loc["name"])
                addr = loc.get("address")
                if isinstance(addr, dict):
                    addr_vals = [
                        str(addr.get(k))
                        for k in ("streetAddress", "addressLocality", "addressRegion", "addressCountry")
                        if addr.get(k)
                    ]
                    if addr_vals:
                        loc_parts.append(", ".join(addr_vals))
                if loc_parts:
                    sections.append(PageSection(heading="Location", content="\n".join(loc_parts)))

    if sections:
        return title, sections

    next_data = soup.find("script", id="__NEXT_DATA__")
    if next_data and next_data.string:
        try:
            data = json.loads(next_data.string)
        except json.JSONDecodeError:
            return title, sections

        collected: list[str] = []

        def scan(obj: Any, depth: int = 0) -> None:
            if depth > 8 or len(collected) >= 10:
                return
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if k in ("name", "title") and not title and isinstance(v, str) and len(v) < 200:
                        title_candidate = _clean_text(v)
                        if title_candidate:
                            collected.append(f"{k}: {title_candidate}")
                    elif k in ("description", "summary", "about", "bio") and isinstance(v, str) and len(v.strip()) > 20:
                        collected.append(v.strip())
                    else:
                        scan(v, depth + 1)
            elif isinstance(obj, list):
                for item in obj[:20]:
                    scan(item, depth + 1)

        scan(data)
        if collected:
            sections.append(PageSection(heading="Page Content", content="\n\n".join(collected)))

    return title, sections


def extract_page_details(html: str, url: str) -> PageDetails:
    """Parse HTML into page title and dynamic heading/content sections."""
    soup = BeautifulSoup(html or "", "lxml")

    title = ""
    if soup.title and soup.title.string:
        title = _clean_text(soup.title.string)
    if not title:
        og_title = soup.find("meta", attrs={"property": "og:title"})
        if og_title and og_title.get("content"):
            title = _clean_text(str(og_title["content"]))

    # Inspect embedded JSON before stripping script tags.
    json_title, json_sections = _extract_embedded_json_sections(soup)
    if not title and json_title:
        title = json_title

    root = soup.find("main") or soup.find(attrs={"role": "main"}) or soup.find("article") or soup.body or soup
    _remove_noise(root)

    tokens = _extract_tokens(root)
    sections = _tokens_to_sections(tokens, title)

    total_chars = sum(len(s.content) for s in sections)
    if total_chars < 40 and json_sections:
        sections = json_sections

    return PageDetails(
        url=url,
        title=title,
        fetch_status="ok" if (sections or title) else "empty",
        sections=sections,
    )


def _needs_browser_fallback(html: str, details: PageDetails) -> bool:
    total_chars = sum(len(s.content) for s in details.sections)
    if total_chars >= 80:
        return False
    lower = (html or "").lower()
    if any(
        marker in lower
        for marker in (
            "enable javascript",
            "you need to enable javascript",
            "id=\"__next\"",
            "id=\"root\"",
            "id=\"app\"",
            "data-reactroot",
        )
    ):
        return True
    return total_chars == 0


async def _fetch_html_httpx(url: str) -> tuple[str, str]:
    """Fetch URL with redirect validation and timeout. Returns (final_url, html)."""
    current_url = validate_url(url)
    headers = {"User-Agent": _USER_AGENT, "Accept": "text/html,application/xhtml+xml,*/*"}

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(PAGE_FETCH_TIMEOUT_SECONDS),
        follow_redirects=False,
        headers=headers,
    ) as client:
        for _ in range(6):
            resp = await client.get(current_url)
            if resp.status_code in (301, 302, 303, 307, 308):
                location = resp.headers.get("location")
                if not location:
                    break
                next_url = urljoin(current_url, location)
                current_url = validate_url(next_url)
                continue
            resp.raise_for_status()
            content_type = (resp.headers.get("content-type") or "").lower()
            if content_type and "html" not in content_type and "xml" not in content_type and "text/" not in content_type:
                raise ValueError(f"Unsupported content type: {content_type.split(';')[0]}")
            return current_url, resp.text

    raise ValueError("Too many redirects")


async def _fetch_html_playwright(url: str) -> tuple[str, str]:
    """Render a JS page using Playwright Chromium, raising RuntimeError if browser is missing."""
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise RuntimeError("browser not installed") from exc

    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(headless=True)
        except Exception as exc:
            msg = str(exc).lower()
            if "executable doesn't exist" in msg or "playwright install" in msg or "browser" in msg:
                raise RuntimeError("browser not installed") from exc
            raise

        try:
            context = await browser.new_context(user_agent=_USER_AGENT)
            page = await context.new_page()

            async def _route_handler(route: Any) -> None:
                req_url = route.request.url
                if req_url.startswith(("http://", "https://")):
                    try:
                        validate_url(req_url, resolve_dns=False)
                    except UnsafeURLError:
                        await route.abort()
                        return
                await route.continue_()

            await page.route("**/*", _route_handler)
            await page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=int(PAGE_FETCH_TIMEOUT_SECONDS * 1000),
            )
            try:
                await page.wait_for_load_state("networkidle", timeout=5000)
            except Exception:
                pass
            html = await page.content()
            final_url = page.url or url
            validate_url(final_url)
            return final_url, html
        finally:
            await browser.close()


async def fetch_page_details(url: str) -> PageDetails:
    """Fetch a single URL (HTTP first, Playwright fallback on JS-only pages) with 1 retry."""
    cleaned_url = (url or "").strip()
    if not cleaned_url:
        return PageDetails(url="", title="", fetch_status="skipped", sections=[])

    try:
        validate_url(cleaned_url)
    except UnsafeURLError as exc:
        return PageDetails(
            url=cleaned_url,
            title="",
            fetch_status=f"Could not fetch: {exc}",
            sections=[],
        )

    last_error = "request failed"
    for attempt in range(PAGE_FETCH_RETRIES + 1):
        try:
            final_url, html = await _fetch_html_httpx(cleaned_url)
            details = extract_page_details(html, final_url)

            if _needs_browser_fallback(html, details):
                try:
                    pw_url, pw_html = await _fetch_html_playwright(final_url)
                    pw_details = extract_page_details(pw_html, pw_url)
                    if sum(len(s.content) for s in pw_details.sections) > sum(len(s.content) for s in details.sections):
                        details = pw_details
                except RuntimeError as exc:
                    if "browser not installed" in str(exc).lower() and not details.sections:
                        return PageDetails(
                            url=cleaned_url,
                            title=details.title,
                            fetch_status="Could not fetch: browser not installed",
                            sections=[],
                        )
                except Exception as exc:
                    if not details.sections:
                        last_error = str(exc) or "browser render failed"
                        if attempt < PAGE_FETCH_RETRIES:
                            await asyncio.sleep(0.3)
                            continue
                        return PageDetails(
                            url=cleaned_url,
                            title=details.title,
                            fetch_status=f"Could not fetch: {last_error}",
                            sections=[],
                        )

            details.fetch_status = "ok"
            return details
        except UnsafeURLError as exc:
            return PageDetails(
                url=cleaned_url,
                title="",
                fetch_status=f"Could not fetch: {exc}",
                sections=[],
            )
        except httpx.TimeoutException:
            last_error = "request timed out"
        except httpx.HTTPStatusError as exc:
            last_error = f"HTTP {exc.response.status_code}"
        except Exception as exc:
            last_error = str(exc) or "request failed"

        if attempt < PAGE_FETCH_RETRIES:
            await asyncio.sleep(0.3)

    return PageDetails(
        url=cleaned_url,
        title="",
        fetch_status=f"Could not fetch: {last_error}",
        sections=[],
    )


async def fetch_many_page_details(
    items: list[tuple[int, str]],
    get_cached: Callable[[str], PageDetails | None] | None = None,
    set_cached: Callable[[str, PageDetails], None] | None = None,
    on_progress: Callable[[int, int, int, PageDetails], Awaitable[None]] | None = None,
) -> dict[int, PageDetails]:
    """Fetch page details for (record_number, url) pairs with concurrency=5 and caching."""
    total = len(items)
    results: dict[int, PageDetails] = {}
    semaphore = asyncio.Semaphore(PAGE_FETCH_MAX_CONCURRENCY)
    completed = 0
    progress_lock = asyncio.Lock()

    async def worker(record_number: int, url: str) -> None:
        nonlocal completed
        cleaned = (url or "").strip()

        if not cleaned:
            details = PageDetails(url="", title="", fetch_status="skipped", sections=[])
        else:
            cached = get_cached(cleaned) if get_cached else None
            if cached is not None:
                details = cached
            else:
                async with semaphore:
                    if PAGE_FETCH_DELAY_SECONDS > 0:
                        await asyncio.sleep(PAGE_FETCH_DELAY_SECONDS)
                    details = await fetch_page_details(cleaned)
                if set_cached is not None and details.fetch_status == "ok":
                    set_cached(cleaned, details)

        results[record_number] = details
        async with progress_lock:
            completed += 1
            if on_progress is not None:
                await on_progress(completed, total, record_number, details)

    await asyncio.gather(*(worker(rec_num, url) for rec_num, url in items))
    return results
