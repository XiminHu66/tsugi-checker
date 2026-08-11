from __future__ import annotations
import re
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup

CHAPTER_WORDS = re.compile(r"(第\s*[0-9一二三四五六七八九十百千万零〇两\.\-]+\s*[章话回卷节]|序章|终章|后记|番外|幕间|Chapter\s*\d+|Ch\.?\s*\d+)", re.I)
NOISE = re.compile(r"(登录|注册|首页|排行|分类|搜索|收藏|书架|评论|上一页|下一页|返回|作者|标签|下载|APP)")

@dataclass
class Parsed:
    title: str
    cover: str | None
    latest_chapter: str | None
    latest_url: str | None
    chapter_count: int
    catalog_url: str | None = None

SOURCE_LABELS = {
    "bilinovel": "BiliNovel / Linovelib",
    "linovelib": "BiliNovel / Linovelib",
    "wenku8": "轻小说文库 · Wenku8",
    "manhuagui": "漫画柜 · Manhuagui",
    "copymanga": "拷贝漫画 · CopyManga",
    "generic": "Generic"
}

def clean(s: str | None) -> str:
    return re.sub(r"\s+", " ", s or "").strip()

def meta(soup: BeautifulSoup, *keys: str) -> str | None:
    for key in keys:
        node = soup.select_one(f'meta[property="{key}"]') or soup.select_one(f'meta[name="{key}"]')
        if node and node.get("content"):
            return clean(node["content"])
    return None

def title_from(soup: BeautifulSoup, fallback: str) -> str:
    t = meta(soup, "og:title", "twitter:title")
    if t: return re.split(r"[_|\-–—]", t)[0].strip()
    h = soup.select_one("h1")
    if h: return clean(h.get_text(" "))
    if soup.title: return re.split(r"[_|\-–—]", clean(soup.title.get_text(" ")))[0].strip()
    return fallback

def cover_from(soup: BeautifulSoup, base: str) -> str | None:
    c = meta(soup, "og:image", "twitter:image")
    if c: return urljoin(base, c)
    for sel in [".book-cover img", ".cover img", ".book img", ".detail img", "img"]:
        n=soup.select_one(sel)
        if n:
            src=n.get("data-src") or n.get("data-original") or n.get("src")
            if src and not src.startswith("data:"): return urljoin(base, src)
    return None

def candidate_score(text: str, href: str, source: str) -> int:
    t=clean(text); h=href.lower(); score=0
    if not t or len(t)>120 or NOISE.search(t): return -99
    if CHAPTER_WORDS.search(t): score += 10
    if re.search(r"\d", t): score += 1
    if source in ("manhuagui","copymanga") and re.search(r"chapter|comic/.+/.+\.html|/chapter/", h): score += 3
    if source in ("bilinovel","linovelib","wenku8") and re.search(r"novel|book|read|\d+\.html?", h): score += 2
    if t in ("阅读","开始阅读","继续阅读"): score -= 3
    return score

def get_chapters(soup: BeautifulSoup, base: str, source: str, selector: str | None = None):
    nodes = soup.select(selector) if selector else soup.select("a[href]")
    out=[]; seen=set()
    for i,a in enumerate(nodes):
        text=clean(a.get_text(" ")); href=urljoin(base,a.get("href") or "")
        if not href.startswith("http"): continue
        score=candidate_score(text,href,source)
        if score<5: continue
        key=(text,href)
        if key in seen: continue
        seen.add(key); out.append((i,score,text,href))
    return out

def find_catalog(soup: BeautifulSoup, base: str) -> str | None:
    patterns=("目录","章节","全部章节","作品目录","小说目录","开始阅读")
    for a in soup.select("a[href]"):
        t=clean(a.get_text(" "))
        if any(p in t for p in patterns):
            href=urljoin(base,a.get("href") or "")
            if href.startswith("http"): return href
    return None

def parse(html: str, url: str, item: dict) -> Parsed:
    source=item.get("source","generic").lower(); soup=BeautifulSoup(html,"lxml")
    title=title_from(soup,item.get("title") or item.get("id") or "Untitled")
    cover=cover_from(soup,url)
    chapters=get_chapters(soup,url,source,item.get("chapter_selector"))
    # Page order differs by source. Prefer the visually last chapter-like link;
    # if a site renders newest-first, a custom chapter_selector can be supplied.
    order=item.get('chapter_order','last')
    latest=(chapters[0] if order=='first' else chapters[-1]) if chapters else None
    return Parsed(title,cover,latest[2] if latest else None,latest[3] if latest else None,len(chapters),find_catalog(soup,url))
