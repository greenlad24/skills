"""Free, local product scraping: page metadata, JSON-LD, images, and a web search.

E-commerce sites (TikTok Shop, Shopee, Lazada) often render with JavaScript or block
bots, so this is best-effort. The LLM research step (web search) fills the gaps.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import quote_plus, urljoin, urlparse, parse_qs, unquote

import requests
from bs4 import BeautifulSoup

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
HEADERS = {"User-Agent": UA, "Accept-Language": "th-TH,th;q=0.9,en;q=0.8"}
URL_RE = re.compile(r"https?://\S+")


def find_url(text: str) -> str:
    m = URL_RE.search(text or "")
    return m.group(0).rstrip(").,") if m else ""


def _get(url: str, timeout: int = 15) -> requests.Response | None:
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        if r.status_code < 400:
            return r
    except requests.RequestException:
        pass
    return None


def _jsonld_products(soup: BeautifulSoup) -> list:
    out = []
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except (ValueError, TypeError):
            continue
        stack = data if isinstance(data, list) else [data]
        while stack:
            d = stack.pop()
            if isinstance(d, dict):
                if "@graph" in d:
                    stack.extend(d["@graph"] if isinstance(d["@graph"], list) else [d["@graph"]])
                t = d.get("@type")
                if t == "Product" or (isinstance(t, list) and "Product" in t):
                    out.append(d)
            elif isinstance(d, list):
                stack.extend(d)
    return out


BLOCK_MARKERS = ("security check", "verify you are human", "verifying you are human", "just a moment",
                 "access denied", "captcha", "are you a robot", "attention required", "please enable javascript",
                 "unusual traffic", "ตรวจสอบความปลอดภัย", "ยืนยันว่าคุณเป็นมนุษย์")


def is_blocked_page(title: str, text: str = "") -> bool:
    """TikTok/Shopee/Lazada often answer bots with a captcha / security-check page."""
    head = f"{title or ''} {(text or '')[:400]}".lower()
    return any(m in head for m in BLOCK_MARKERS)


def scrape_url(url: str) -> dict:
    """Return {url, final_url, title, description, price, currency, rating, images[], text}."""
    info = {"url": url, "final_url": url, "title": "", "description": "", "price": "",
            "currency": "", "rating": "", "images": [], "text": "", "ok": False}
    r = _get(url)
    if r is None:
        return info
    info["final_url"] = r.url
    ctype = r.headers.get("content-type", "")
    if "html" not in ctype:
        return info
    soup = BeautifulSoup(r.text, "html.parser")

    def meta(*names):
        for n in names:
            t = soup.find("meta", attrs={"property": n}) or soup.find("meta", attrs={"name": n})
            if t and t.get("content"):
                return t["content"].strip()
        return ""

    info["title"] = meta("og:title", "twitter:title") or (soup.title.string.strip() if soup.title and soup.title.string else "")
    info["description"] = meta("og:description", "description", "twitter:description")
    info["price"] = meta("product:price:amount", "og:price:amount")
    info["currency"] = meta("product:price:currency", "og:price:currency")
    imgs = [meta("og:image", "twitter:image")]
    for p in _jsonld_products(soup):
        info["title"] = info["title"] or str(p.get("name", ""))
        info["description"] = info["description"] or str(p.get("description", ""))[:1500]
        offers = p.get("offers")
        if isinstance(offers, list) and offers:
            offers = offers[0]
        if isinstance(offers, dict):
            info["price"] = info["price"] or str(offers.get("price") or offers.get("lowPrice") or "")
            info["currency"] = info["currency"] or str(offers.get("priceCurrency", ""))
        ar = p.get("aggregateRating")
        if isinstance(ar, dict):
            info["rating"] = f"{ar.get('ratingValue', '')} ({ar.get('reviewCount') or ar.get('ratingCount') or '?'} reviews)"
        im = p.get("image")
        imgs.extend(im if isinstance(im, list) else [im])
    for s in soup(["script", "style", "noscript"]):
        s.decompose()
    text = re.sub(r"\s+", " ", soup.get_text(" ")).strip()
    info["text"] = text[:4000]
    seen = []
    for i in imgs:
        if isinstance(i, dict):
            i = i.get("url", "")
        if isinstance(i, str) and i:
            full = urljoin(r.url, i)
            if full not in seen:
                seen.append(full)
    info["images"] = seen[:6]
    info["ok"] = bool(info["title"] or info["text"]) and not is_blocked_page(info["title"], info["text"])
    if not info["ok"]:
        info["blocked"] = True
    return info


def web_search(query: str, limit: int = 8) -> list:
    """Free DuckDuckGo HTML search → [{title, url, snippet}]. Empty list if blocked."""
    r = None
    try:
        r = requests.post("https://html.duckduckgo.com/html/", data={"q": query, "kl": "th-th"},
                          headers=HEADERS, timeout=15)
    except requests.RequestException:
        return []
    if r is None or r.status_code >= 400:
        return []
    soup = BeautifulSoup(r.text, "html.parser")
    out = []
    for res in soup.select(".result"):
        a = res.select_one("a.result__a")
        if not a:
            continue
        href = a.get("href", "")
        if "uddg=" in href:  # DDG redirect wrapper
            href = unquote(parse_qs(urlparse(href).query).get("uddg", [href])[0])
        snip = res.select_one(".result__snippet")
        out.append({"title": a.get_text(" ", strip=True), "url": href,
                    "snippet": snip.get_text(" ", strip=True) if snip else ""})
        if len(out) >= limit:
            break
    return out


def download_images(urls: list, dest: Path, limit: int = 5) -> list:
    """Save product images (usable as 'product_photo' shots and as LLM vision input)."""
    dest.mkdir(parents=True, exist_ok=True)
    saved = []
    for i, u in enumerate(urls[:limit]):
        r = _get(u, timeout=20)
        if r is None:
            continue
        ct = r.headers.get("content-type", "")
        ext = ".png" if "png" in ct else ".webp" if "webp" in ct else ".jpg"
        if "image" not in ct or len(r.content) < 2000:
            continue
        p = dest / f"product_{i + 1}{ext}"
        p.write_bytes(r.content)
        saved.append(p)
    return saved


def gather(query_text: str, image_paths: list, project_dir: Path, log=print) -> dict:
    """Everything we can learn for free before calling an LLM."""
    url = find_url(query_text)
    name = URL_RE.sub("", query_text or "").strip()
    page = {}
    if url:
        log(f"Fetching {url} …")
        page = scrape_url(url)
        log("Page read OK" if page.get("ok") else "Page blocked or JS-only (the AI will research it instead)")
    search_q = (page.get("title") if page.get("ok") else "") or name   # never search a captcha page title
    results = []
    if search_q:
        log(f"Web search: {search_q[:80]}")
        results = web_search(search_q + " รีวิว")
        results += web_search(search_q + " tiktok")
    imgs = []
    if page.get("images"):
        imgs = download_images(page["images"], project_dir / "product_images")
        log(f"Saved {len(imgs)} product images")
    return {
        "input_text": query_text,
        "url": url,
        "name_hint": name,
        "page": page,
        "search_results": results[:14],
        "product_images": [str(p) for p in imgs],
        "user_images": [str(p) for p in image_paths],
    }


def search_url(q: str) -> str:
    return "https://www.google.com/search?q=" + quote_plus(q)
