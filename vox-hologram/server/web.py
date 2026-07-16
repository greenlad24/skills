"""VOX web layer — dependency-free search + page fetch (v2).

This is the *only* part of VOX that reaches the public internet, and only for the
optional "sources" feature — the LLM brain stays 100% local. Everything here is:

- **Per-request and short-timeout.** Nothing runs at import; a call that fails,
  times out, or is offline degrades to an empty list / an ``{"error": ...}`` dict
  and never raises to the caller. VOX must keep talking when the web is down.
- **Stdlib-only parsing.** Search results and pages are parsed with
  ``html.parser`` / ``re`` / ``html`` — no beautifulsoup, lxml, or readability.
  The only third-party dependency is ``httpx`` (already a VOX dep).

Public surface:
- ``search(query, count)``  -> ``[{title, url, snippet, source}]`` via DuckDuckGo.
- ``fetch(url)``            -> a "reader" payload (title/text/images/…) per API.md.
- ``reachable()``           -> best-effort, briefly-cached internet check.
"""

from __future__ import annotations

import re
import time
from html.parser import HTMLParser
from typing import Dict, List, Optional
from urllib.parse import parse_qs, unquote, urljoin, urlparse

import httpx

# A browser-like User-Agent — DuckDuckGo's HTML endpoint and many sites serve
# stripped or bot-blocked responses to obviously-automated clients.
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

_SEARCH_TIMEOUT = 6.0
_FETCH_TIMEOUT = 8.0
_REACH_TIMEOUT = 3.0

# Cap fetched bodies so a hostile / huge page can't blow up memory (~2 MB).
_MAX_BYTES = 2 * 1024 * 1024
# Cleaned reader text is capped so grounding context stays small (~4000 chars).
_MAX_TEXT = 4000
_MAX_IMAGES = 6

# DuckDuckGo's no-JS HTML endpoint. It accepts a POST with ``q`` and returns a
# plain server-rendered result list we can parse with html.parser.
_DDG_HTML = "https://html.duckduckgo.com/html/"
_DDG_LITE = "https://lite.duckduckgo.com/lite/"

# A stable, lightweight host used purely to probe connectivity.
_REACH_URL = "https://duckduckgo.com/"


def _headers() -> Dict[str, str]:
    return {
        "User-Agent": _UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }


def _host(url: str) -> str:
    """Registrable-ish host for display (netloc, lowercased, ``www.`` stripped)."""
    try:
        netloc = urlparse(url).netloc.lower()
    except Exception:  # noqa: BLE001 — never let host parsing raise
        return ""
    # Drop any userinfo / port.
    netloc = netloc.split("@")[-1].split(":")[0]
    if netloc.startswith("www."):
        netloc = netloc[4:]
    return netloc


def _unwrap_ddg(href: Optional[str]) -> str:
    """Turn a DuckDuckGo ``/l/?uddg=<encoded>`` redirect into the real target."""
    if not href:
        return ""
    href = href.strip()
    if href.startswith("//"):
        href = "https:" + href
    try:
        parsed = urlparse(href)
    except Exception:  # noqa: BLE001
        return href
    if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
        target = parse_qs(parsed.query).get("uddg")
        if target:
            # parse_qs already percent-decodes; unquote again is a safe no-op.
            return unquote(target[0])
    return href


# --- Search -----------------------------------------------------------------
class _DDGResultParser(HTMLParser):
    """Extract ``result__a`` (title/link) + ``result__snippet`` blocks from the
    DuckDuckGo HTML page. Deliberately forgiving: any structural surprise just
    yields fewer results rather than an exception."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.results: List[Dict[str, str]] = []
        self._cur: Optional[Dict[str, str]] = None
        self._capture: Optional[str] = None  # "title" | "snippet"
        self._buf: List[str] = []

    def _flush(self) -> None:
        if self._cur and self._cur.get("url") and self._cur.get("title"):
            self.results.append(self._cur)
        self._cur = None

    def _end_capture(self) -> None:
        if self._cur is not None and self._capture is not None:
            self._cur[self._capture] = re.sub(r"\s+", " ", "".join(self._buf)).strip()
        self._capture = None
        self._buf = []

    def handle_starttag(self, tag, attrs):
        if tag != "a":
            return
        a = dict(attrs)
        cls = a.get("class") or ""
        if "result__a" in cls:
            # A new result begins — commit the previous one first.
            self._end_capture()
            self._flush()
            self._cur = {
                "url": _unwrap_ddg(a.get("href")),
                "title": "",
                "snippet": "",
            }
            self._capture = "title"
            self._buf = []
        elif "result__snippet" in cls and self._cur is not None:
            self._end_capture()
            self._capture = "snippet"
            self._buf = []

    def handle_endtag(self, tag):
        if tag == "a" and self._capture is not None:
            self._end_capture()

    def handle_data(self, data):
        if self._capture is not None:
            self._buf.append(data)

    def close(self):  # type: ignore[override]
        super().close()
        self._end_capture()
        self._flush()


class _DDGLiteParser(HTMLParser):
    """Fallback parser for the ``lite.duckduckgo.com`` layout, whose result links
    carry ``class="result-link"``."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.results: List[Dict[str, str]] = []
        self._cur: Optional[Dict[str, str]] = None
        self._capture = False
        self._buf: List[str] = []

    def handle_starttag(self, tag, attrs):
        if tag != "a":
            return
        a = dict(attrs)
        cls = a.get("class") or ""
        if "result-link" in cls:
            self._cur = {"url": _unwrap_ddg(a.get("href")), "title": "", "snippet": ""}
            self._capture = True
            self._buf = []

    def handle_endtag(self, tag):
        if tag == "a" and self._capture and self._cur is not None:
            self._cur["title"] = re.sub(r"\s+", " ", "".join(self._buf)).strip()
            if self._cur.get("url") and self._cur.get("title"):
                self.results.append(self._cur)
            self._cur = None
            self._capture = False
            self._buf = []

    def handle_data(self, data):
        if self._capture:
            self._buf.append(data)


async def search(query: str, count: int = 4) -> List[Dict[str, str]]:
    """Dependency-free web search via DuckDuckGo's no-JS HTML endpoint.

    Returns up to ``count`` ``{title, url, snippet, source}`` dicts. Never raises:
    transport errors, timeouts, or parse issues degrade to whatever could be
    recovered (possibly ``[]``).
    """
    query = (query or "").strip()
    if not query:
        return []
    try:
        count = int(count)
    except (TypeError, ValueError):
        count = 4
    if count <= 0:
        return []

    html_text = ""
    used_lite = False
    try:
        async with httpx.AsyncClient(
            timeout=_SEARCH_TIMEOUT, follow_redirects=True, headers=_headers()
        ) as client:
            try:
                resp = await client.post(_DDG_HTML, data={"q": query, "kl": "us-en"})
                resp.raise_for_status()
                html_text = resp.text
            except httpx.HTTPError:
                # Fall back to the even-simpler lite endpoint.
                used_lite = True
                resp = await client.post(_DDG_LITE, data={"q": query})
                resp.raise_for_status()
                html_text = resp.text
    except Exception:  # noqa: BLE001 — offline / blocked / timeout => no results
        return []

    results: List[Dict[str, str]] = []
    try:
        if not used_lite:
            parser = _DDGResultParser()
            parser.feed(html_text)
            parser.close()
            results = parser.results
        if used_lite or not results:
            lite = _DDGLiteParser()
            lite.feed(html_text)
            results = results or lite.results
    except Exception:  # noqa: BLE001 — malformed markup => return what we have
        pass

    out: List[Dict[str, str]] = []
    seen = set()
    for r in results:
        url = (r.get("url") or "").strip()
        title = (r.get("title") or "").strip()
        if not url or not title or url in seen:
            continue
        if not url.lower().startswith(("http://", "https://")):
            continue
        seen.add(url)
        out.append(
            {
                "title": title,
                "url": url,
                "snippet": (r.get("snippet") or "").strip(),
                "source": _host(url),
            }
        )
        if len(out) >= count:
            break
    return out


# --- Fetch ------------------------------------------------------------------
_SKIP_TAGS = {"script", "style", "noscript", "template", "svg", "iframe", "canvas"}
_SOFT_SKIP = {"nav", "header", "footer", "aside", "form"}
_BLOCK_TAGS = {
    "p", "div", "br", "li", "ul", "ol", "tr", "table", "section", "article",
    "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "pre", "figure",
    "figcaption", "main", "hr", "td", "th",
}

# URL fragments that usually indicate a tracking pixel / spacer / chrome.
_IMG_BLOCKLIST = re.compile(
    r"(1x1|pixel|spacer|blank\.gif|beacon|track|analytics|doubleclick|\.svg([?#]|$))",
    re.IGNORECASE,
)


class _PageParser(HTMLParser):
    """Pull a readable title, main text, and candidate images out of a page,
    skipping script/style/nav chrome. Best-effort and exception-tolerant."""

    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.title = ""
        self.og_title = ""
        self.og_image = ""
        self.images: List[str] = []
        self._seen_img = set()
        self._text: List[str] = []
        self._skip_depth = 0
        self._in_title = False

    def _abs(self, url: Optional[str]) -> str:
        if not url:
            return ""
        url = url.strip()
        if not url or url.startswith(("data:", "javascript:", "#")):
            return ""
        try:
            return urljoin(self.base_url, url)
        except Exception:  # noqa: BLE001
            return url

    def _add_image(self, a: Dict[str, str]) -> None:
        src = a.get("src") or a.get("data-src") or a.get("data-original") or ""
        absolute = self._abs(src)
        if not absolute or absolute in self._seen_img:
            return
        if _IMG_BLOCKLIST.search(absolute):
            return
        # Drop obvious tracking pixels / tiny sprites declared inline.
        for dim in ("width", "height"):
            val = a.get(dim)
            if val:
                try:
                    if int(re.sub(r"[^\d]", "", val) or "999") <= 2:
                        return
                except ValueError:
                    pass
        self._seen_img.add(absolute)
        if len(self.images) < 30:
            self.images.append(absolute)

    def _extract(self, tag: str, a: Dict[str, str]) -> None:
        if tag == "meta":
            prop = (a.get("property") or a.get("name") or "").lower()
            content = a.get("content") or ""
            if not content:
                return
            if prop == "og:title" and not self.og_title:
                self.og_title = content.strip()
            elif prop in ("og:image", "og:image:url", "og:image:secure_url",
                          "twitter:image") and not self.og_image:
                self.og_image = self._abs(content)
        elif tag == "img":
            self._add_image(a)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        self._extract(tag, a)
        if tag == "title":
            self._in_title = True
        if tag in _SKIP_TAGS or tag in _SOFT_SKIP:
            self._skip_depth += 1
        elif tag in _BLOCK_TAGS:
            self._text.append(" ")

    def handle_startendtag(self, tag, attrs):
        self._extract(tag, dict(attrs))

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        if tag in _SKIP_TAGS or tag in _SOFT_SKIP:
            if self._skip_depth > 0:
                self._skip_depth -= 1
        elif tag in _BLOCK_TAGS:
            self._text.append(" ")

    def handle_data(self, data):
        if self._in_title:
            self.title += data
            return
        if self._skip_depth == 0 and data.strip():
            self._text.append(data)

    def text(self) -> str:
        collapsed = re.sub(r"\s+", " ", "".join(self._text)).strip()
        return collapsed[:_MAX_TEXT]


def _allow_iframe(headers: httpx.Headers) -> bool:
    """Best-effort: may the frontend embed this page in an ``<iframe>``?

    Conservative — any framing-restricting header returns False.
    """
    xfo = (headers.get("x-frame-options") or "").lower()
    if "deny" in xfo or "sameorigin" in xfo or "allow-from" in xfo:
        return False
    csp = (headers.get("content-security-policy") or "").lower()
    match = re.search(r"frame-ancestors([^;]*)", csp)
    if match:
        directive = match.group(1).strip()
        # ``frame-ancestors *`` permits framing; anything else restricts it.
        if directive and directive != "*":
            return False
    return True


def _decode(body: bytes, content_type: str) -> str:
    match = re.search(r"charset=([\w\-]+)", content_type or "", re.IGNORECASE)
    if match:
        try:
            return body.decode(match.group(1), errors="replace")
        except LookupError:
            pass
    return body.decode("utf-8", errors="replace")


async def fetch(url: str) -> Dict[str, object]:
    """Fetch ``url`` and return a cleaned "reader" payload (see API.md /api/fetch).

    On any failure returns ``{"error": "...", "url": url}`` rather than raising.
    """
    url = (url or "").strip()
    if not url.lower().startswith(("http://", "https://")):
        return {"error": "invalid_url", "url": url}

    try:
        async with httpx.AsyncClient(
            timeout=_FETCH_TIMEOUT, follow_redirects=True, headers=_headers()
        ) as client:
            async with client.stream("GET", url) as resp:
                resp.raise_for_status()
                final_url = str(resp.url)
                headers = resp.headers
                content_type = headers.get("content-type", "")
                chunks: List[bytes] = []
                total = 0
                async for chunk in resp.aiter_bytes():
                    chunks.append(chunk)
                    total += len(chunk)
                    if total >= _MAX_BYTES:
                        break
        body = b"".join(chunks)[:_MAX_BYTES]
    except Exception as exc:  # noqa: BLE001 — offline / 4xx / 5xx / timeout
        return {"error": str(exc) or exc.__class__.__name__, "url": url}

    source = _host(final_url)
    allow_iframe = _allow_iframe(headers)

    # Only parse things that are actually HTML/XML — binary payloads (PDF,
    # images) would decode to garbage.
    if content_type and not re.search(r"html|xml|text", content_type, re.IGNORECASE):
        return {
            "url": final_url,
            "title": "",
            "text": "",
            "images": [],
            "image": None,
            "source": source,
            "allow_iframe": allow_iframe,
        }

    html_text = _decode(body, content_type)
    parser = _PageParser(final_url)
    try:
        parser.feed(html_text)
        parser.close()
    except Exception:  # noqa: BLE001 — salvage whatever parsed before the error
        pass

    title = (parser.title.strip() or parser.og_title).strip()
    text = parser.text()

    images: List[str] = []
    seen = set()
    for candidate in ([parser.og_image] if parser.og_image else []) + parser.images:
        if candidate and candidate not in seen:
            seen.add(candidate)
            images.append(candidate)
        if len(images) >= _MAX_IMAGES:
            break

    image = parser.og_image or (images[0] if images else None)

    return {
        "url": final_url,
        "title": title,
        "text": text,
        "images": images,
        "image": image,
        "source": source,
        "allow_iframe": allow_iframe,
    }


# --- Reachability -----------------------------------------------------------
# Briefly cached so a chat turn / config poll doesn't hit the network every time.
_REACH_TTL = 30.0
_reach_cache: Dict[str, float] = {"ts": 0.0, "ok": 0.0}


async def reachable() -> bool:
    """Best-effort, briefly-cached internet reachability. Never raises."""
    now = time.monotonic()
    if now - _reach_cache["ts"] < _REACH_TTL and _reach_cache["ts"] > 0.0:
        return bool(_reach_cache["ok"])

    ok = False
    try:
        async with httpx.AsyncClient(
            timeout=_REACH_TIMEOUT, follow_redirects=True, headers=_headers()
        ) as client:
            try:
                resp = await client.head(_REACH_URL)
            except httpx.HTTPError:
                # Some hosts reject HEAD; a tiny GET still confirms connectivity.
                resp = await client.get(_REACH_URL)
            ok = resp.status_code < 500
    except Exception:  # noqa: BLE001 — any failure => treat as offline
        ok = False

    _reach_cache["ts"] = now
    _reach_cache["ok"] = 1.0 if ok else 0.0
    return ok
