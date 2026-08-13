from __future__ import annotations

import hashlib
import html as html_lib
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

JST = timezone(timedelta(hours=9))
CST = timezone(timedelta(hours=8))
DATE_JP_RE = re.compile(r"(20\d{2})年\s*(\d{1,2})月\s*(\d{1,2})日")
DATE_EN_RE = re.compile(
    r"\b(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+(\d{1,2}),\s+(20\d{2})\b",
    re.I,
)
PLATFORM_RE = re.compile(r"\b(Switch2|Switch|PS5|PS4|XSX|XONE|Xbox Series X\|S|Xbox One|PC|Steam)\b", re.I)
MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10,
    "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}
CONSOLE_PLATFORMS = {"SWITCH", "SWITCH2", "PS5", "PS4", "XSX", "XONE"}
MOJIBAKE_HINTS = ("ã", "â", "Â", "æ", "å", "ç", "ï¿½", "ð")


def clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def repair_text(value: str) -> str:
    """Repair the common UTF-8-as-Latin-1 mojibake seen on apps.apple.com."""
    text = html_lib.unescape(clean(value))
    if not text or not any(mark in text for mark in MOJIBAKE_HINTS):
        return text
    try:
        candidate = text.encode("latin-1").decode("utf-8")
    except Exception:
        return text
    old_score = sum(text.count(x) for x in MOJIBAKE_HINTS)
    new_score = sum(candidate.count(x) for x in MOJIBAKE_HINTS)
    return candidate if new_score < old_score else text


def stable_id(source: str, url: str, title: str = "") -> str:
    return hashlib.sha1(f"{source}|{url}|{title}".encode("utf-8")).hexdigest()[:16]


def _decode_response(r: requests.Response) -> str:
    # Apple storefront HTML has historically omitted / confused charset metadata.
    # Prefer UTF-8 because the JP storefront is UTF-8, then fall back to Requests detection.
    try:
        return r.content.decode("utf-8")
    except UnicodeDecodeError:
        enc = r.apparent_encoding or r.encoding or "utf-8"
        return r.content.decode(enc, errors="replace")


def get_html(url: str, ua: str, timeout: int = 30, accept_language: str = "ja-JP,ja;q=0.95,en;q=0.7") -> str:
    r = requests.get(
        url,
        headers={
            "User-Agent": ua,
            "Accept-Language": accept_language,
            "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
        },
        timeout=timeout,
    )
    r.raise_for_status()
    return _decode_response(r)


def get_browser_html(url: str, ua: str, locale: str = "ja-JP", wait_ms: int = 2200) -> str:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=ua, locale=locale, viewport={"width": 1440, "height": 1200})
        page = context.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(wait_ms)
        html = page.content()
        context.close()
        browser.close()
        return html


def parse_jp_date(text: str) -> str:
    m = DATE_JP_RE.search(text or "")
    if m:
        return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    short = re.search(r"(\d{1,2})月\s*(\d{1,2})日", text or "")
    if short:
        year = datetime.now(timezone.utc).astimezone(JST).year
        return f"{year:04d}-{int(short.group(1)):02d}-{int(short.group(2)):02d}"
    return ""


def parse_en_date(text: str) -> str:
    m = DATE_EN_RE.search(text or "")
    if not m:
        return ""
    month = MONTHS.get(m.group(1).lower())
    return f"{int(m.group(3)):04d}-{month:02d}-{int(m.group(2)):02d}" if month else ""


def parse_any_date(text: str) -> str:
    return parse_jp_date(text) or parse_en_date(text)


def _srcset_best(value: str) -> str:
    if not value:
        return ""
    candidates = []
    for part in value.split(","):
        bit = part.strip().split()
        if bit:
            candidates.append(bit[0])
    return candidates[-1] if candidates else ""


def image_from(node, base: str) -> str:
    if not node or not hasattr(node, "select_one"):
        return ""
    img = node.select_one("img")
    if not img:
        return ""
    # Prefer lazy/real images and srcset. App Store's plain src is often a 1x1 GIF.
    candidates = [
        img.get("data-src"), img.get("data-original"), img.get("data-lazy-src"),
        _srcset_best(img.get("data-srcset") or ""), _srcset_best(img.get("srcset") or ""),
    ]
    picture = img.parent if getattr(img.parent, "name", None) == "picture" else None
    if picture:
        for source in picture.select("source[srcset]"):
            candidates.append(_srcset_best(source.get("srcset") or ""))
    candidates.append(img.get("src"))
    for src in candidates:
        src = clean(src)
        if not src or src.startswith("data:") or "1x1.gif" in src:
            continue
        return urljoin(base, src)
    return ""


def closest_card(anchor, max_chars: int = 1000):
    best = None
    for p in anchor.parents:
        if getattr(p, "name", None) not in ("li", "article", "div", "section"):
            continue
        text = clean(p.get_text(" "))
        if 2 <= len(text) <= max_chars:
            best = p
            # A card with an image and only a handful of links is usually the right scope.
            if p.select_one("img") and len(p.select("a[href]")) <= 6:
                return p
    return best or anchor.parent


def app_title(anchor, card=None) -> str:
    noise = {"表示", "入手", "開く", "インストール", "install", "open", "view", "get"}
    nodes = [anchor]
    if card is not None and card is not anchor:
        nodes.append(card)
    for node in nodes:
        for key in ("aria-label", "title"):
            t = repair_text(node.get(key)) if hasattr(node, "get") else ""
            if 2 <= len(t) <= 140 and t.casefold() not in noise:
                return t
        img = node.select_one("img") if hasattr(node, "select_one") else None
        if img:
            t = repair_text(img.get("alt") or img.get("aria-label"))
            if 2 <= len(t) <= 140 and t.casefold() not in noise:
                return t
        for sel in ("h1", "h2", "h3", "h4", "strong", ".title", "[data-testid*=title]", "span"):
            n = node.select_one(sel) if hasattr(node, "select_one") else None
            t = repair_text(n.get_text(" ")) if n else ""
            if 2 <= len(t) <= 140 and t.casefold() not in noise:
                return t
    text = repair_text((card or anchor).get_text(" "))
    text = re.sub(r"\s+[0-5](?:\.[0-9])?\s*(?:star|★).*$", "", text, flags=re.I)
    text = re.sub(r"\s+(?:表示|入手|インストール).*$", "", text)
    return text[:140] if 2 <= len(text) <= 220 and text.casefold() not in noise else ""


def _store_anchors(soup: BeautifulSoup, href_re: re.Pattern, limit: int):
    out, seen = [], set()
    for a in soup.select("a[href]"):
        href = a.get("href") or ""
        if not href_re.search(href) or href in seen:
            continue
        seen.add(href)
        out.append(a)
        if len(out) >= limit:
            break
    return out


def _parse_mobile_store(html: str, url: str, source: str, label: str, store: str, platform: str, href_re: re.Pattern, limit: int):
    soup = BeautifulSoup(html, "lxml")
    anchors = _store_anchors(soup, href_re, max(limit * 4, limit))
    rows, seen = [], set()
    for a in anchors:
        href = urljoin(url, a.get("href") or "")
        if href in seen:
            continue
        card = closest_card(a, 1200)
        title = app_title(a, card)
        if not title or title.casefold() in {"表示", "入手", "open", "install", "view", "get"}:
            continue
        seen.add(href)
        # URL-only ID keeps first_seen stable even if storefront wording/encoding changes.
        row_id = stable_id(source, href)
        legacy_title = ""
        try:
            legacy_title = title.encode("utf-8").decode("latin-1")
        except Exception:
            pass
        rows.append({
            "id": row_id,
            "legacy_id": stable_id(source, href, legacy_title) if legacy_title else "",
            "category": "mobile",
            "source": source,
            "source_label": label,
            "store": store,
            "title": title,
            "url": href,
            "cover": image_from(card, url),
            "platforms": [platform],
            "release_date": "",
            "region": "JP",
            "featured": True,
            "popularity_label": "日本新着精选",
        })
        if len(rows) >= limit:
            break
    return rows


def fetch_appstore_new(cfg: dict, ua: str):
    url = cfg.get("url") or "https://apps.apple.com/jp/iphone/room/1435822938"
    limit = int(cfg.get("limit", 36))
    href_re = re.compile(r"(?:https?://apps\.apple\.com)?/jp/app/|/app/", re.I)
    rows = _parse_mobile_store(get_html(url, ua), url, "appstore", "App Store 日本 · 新着精选", "iOS / iPadOS", "iOS", href_re, limit)
    if not rows:
        rows = _parse_mobile_store(get_browser_html(url, ua), url, "appstore", "App Store 日本 · 新着精选", "iOS / iPadOS", "iOS", href_re, limit)
    return rows


def fetch_googleplay_new(cfg: dict, ua: str):
    url = cfg.get("url") or "https://play.google.com/store/apps/collection/promotion_3000791_new_releases_games?hl=ja&gl=jp"
    limit = int(cfg.get("limit", 36))
    href_re = re.compile(r"/store/apps/details\?(?:[^#]*&)?id=", re.I)
    rows = _parse_mobile_store(get_html(url, ua), url, "googleplay", "Google Play 日本 · 新規リリース精选", "Android", "Android", href_re, limit)
    if not rows:
        rows = _parse_mobile_store(get_browser_html(url, ua, "ja-JP", 3000), url, "googleplay", "Google Play 日本 · 新規リリース精选", "Android", "Android", href_re, limit)
    return rows



def _taptap_title(anchor, card=None) -> str:
    """Extract the game title from TapTap ranking/calendar cards."""
    nodes = [anchor]
    if card is not None and card is not anchor:
        nodes.append(card)
    for node in nodes:
        if hasattr(node, "select_one"):
            img = node.select_one("img[alt]")
            if img:
                title = repair_text(img.get("alt"))
                title = re.sub(r"\s*(?:icon|图标)$", "", title, flags=re.I).strip()
                if 2 <= len(title) <= 100:
                    return title
            for sel in ("h1", "h2", "h3", "h4", ".title", "[class*=title]"):
                n = node.select_one(sel)
                if n:
                    title = repair_text(n.get_text(" "))
                    if 2 <= len(title) <= 100:
                        return title
    text = repair_text(anchor.get_text(" "))
    text = re.sub(r"^(?:首发|预下载|新游预约|限量测试|不限量测试|测试招募)\s*(?:\d{1,2}:\d{2}\s*开始)?\s*", "", text)
    # TapTap cards usually separate the rating into its own span; when flattened,
    # cut at the first standalone score token rather than at digits inside titles.
    text = re.split(r"\s+(?:(?:10(?:\.0)?)|(?:[0-9](?:\.\d)?))\s+", text, maxsplit=1)[0]
    return text.strip()[:100]


def _taptap_rating(card) -> float | None:
    if not card:
        return None
    text = clean(card.get_text(" "))
    vals = []
    for m in re.finditer(r"(?<![\d.])(10(?:\.0)?|[5-9](?:\.\d)?)(?![\d.])", text):
        try:
            vals.append(float(m.group(1)))
        except Exception:
            pass
    return vals[0] if vals else None


def fetch_taptap_new(cfg: dict, ua: str):
    """Mainland-China mobile discovery: TapTap's download-weighted new-game chart."""
    url = cfg.get("url") or "https://www.taptap.cn/top/download/new"
    limit = int(cfg.get("limit", 8))
    soup = BeautifulSoup(get_html(url, ua, accept_language="zh-CN,zh;q=0.95"), "lxml")
    rows, seen = [], set()
    for a in soup.select('a[href*="/app/"]'):
        href = urljoin(url, a.get("href") or "")
        if not re.search(r"/app/\d+", href) or href in seen:
            continue
        card = closest_card(a, 900)
        title = _taptap_title(a, card)
        if not title or title in {"下载手机 APP", "下载 TapTap"}:
            continue
        seen.add(href)
        rank = len(rows) + 1
        rating = _taptap_rating(card)
        rows.append({
            "id": stable_id("taptap_cn_new", href),
            "category": "mobile",
            "source": "taptap_cn_new",
            "source_label": "TapTap 中国 · 新品榜",
            "store": "TapTap",
            "title": title,
            "url": href,
            "cover": image_from(card, url),
            "platforms": ["移动端"],
            "release_date": "",
            "region": "CN",
            "featured": True,
            "popularity_rank": rank,
            "rating": rating,
            "popularity_label": f"TapTap 新品榜 #{rank}",
        })
        if len(rows) >= limit:
            break
    return rows


def _date_from_month_day(month: int, day: int, today: date) -> date:
    candidate = date(today.year, month, day)
    # Upcoming pages can cross New Year. Treat a date far behind today as next year.
    if candidate < today - timedelta(days=45):
        candidate = date(today.year + 1, month, day)
    return candidate


def fetch_taptap_upcoming(cfg: dict, ua: str):
    """Popular upcoming mainland-China releases from TapTap's release calendar.

    Only true '首发' entries are included; tests, preloads and version updates are
    intentionally excluded so the mobile timeline remains a release timeline.
    """
    url = cfg.get("url") or "https://www.taptap.cn/upcoming"
    limit = int(cfg.get("limit", 8))
    today_cn = datetime.now(timezone.utc).astimezone(CST).date()
    soup = BeautifulSoup(get_html(url, ua, accept_language="zh-CN,zh;q=0.95"), "lxml")
    start_text = soup.find(string=lambda x: x and clean(x) == "即将上线")
    start = start_text.parent if start_text else soup
    current_date = None
    rows, seen = [], set()
    date_re = re.compile(r"^(\d{1,2})/(\d{1,2})\s*周")
    for node in start.find_all_next():
        if getattr(node, "name", None) in ("script", "style"):
            continue
        text = repair_text(node.get_text(" ")) if hasattr(node, "get_text") else repair_text(node)
        if text in {"下载手机 APP", "热门游戏"} and rows:
            break
        if len(text) <= 32:
            dm = date_re.search(text)
            if dm:
                try:
                    current_date = _date_from_month_day(int(dm.group(1)), int(dm.group(2)), today_cn)
                except Exception:
                    current_date = None
                continue
        if getattr(node, "name", None) != "a" or not node.get("href") or current_date is None:
            continue
        href = urljoin(url, node.get("href") or "")
        if not re.search(r"/app/\d+", href) or href in seen:
            continue
        card = closest_card(node, 900)
        event_text = repair_text(card.get_text(" ")) if card else repair_text(node.get_text(" "))
        if "首发" not in event_text:
            continue
        title = _taptap_title(node, card)
        if not title:
            continue
        seen.add(href)
        rating = _taptap_rating(card)
        rows.append({
            "id": stable_id("taptap_cn_upcoming", href),
            "category": "mobile",
            "source": "taptap_cn_upcoming",
            "source_label": "TapTap 中国 · 即将首发",
            "store": "TapTap",
            "title": title,
            "url": href,
            "cover": image_from(card, url),
            "platforms": ["移动端"],
            "release_date": current_date.isoformat(),
            "release_text": current_date.strftime("%m/%d") + " 首发",
            "region": "CN",
            "featured": True,
            "rating": rating,
            "popularity_label": "TapTap 即将上线",
        })
        if len(rows) >= limit:
            break
    return rows

def _steam_release_detail(appid: int, ua: str):
    url = "https://store.steampowered.com/api/appdetails"
    try:
        r = requests.get(url, params={"appids": appid, "cc": "jp", "l": "english"}, headers={"User-Agent": ua}, timeout=20)
        r.raise_for_status()
        payload = r.json().get(str(appid), {})
        if not payload.get("success"):
            return appid, "", ""
        data = payload.get("data") or {}
        release = clean((data.get("release_date") or {}).get("date"))
        return appid, parse_any_date(release), release
    except Exception:
        return appid, "", ""


def fetch_steam_featured(cfg: dict, ua: str, source_id: str, source_label: str, category: str):
    """Use Steam's storefront featured-category JSON instead of brittle search-result DOM.

    new_releases / coming_soon are front-page curated sets, which is a better fit for
    'known / discussed' titles than all Recently Released products.
    """
    endpoint = cfg.get("api_url") or "https://store.steampowered.com/api/featuredcategories"
    limit = int(cfg.get("limit", 30))
    r = requests.get(endpoint, params={"cc": "jp", "l": "english"}, headers={"User-Agent": ua, "Accept": "application/json"}, timeout=30)
    r.raise_for_status()
    payload = r.json()
    items = ((payload.get(category) or {}).get("items") or [])[:limit]
    if not items:
        raise RuntimeError(f"Steam featuredcategories returned no {category} items")

    appids = [int(x.get("id")) for x in items if x.get("id") and int(x.get("type", 0)) == 0]
    details = {}
    with ThreadPoolExecutor(max_workers=min(8, max(1, len(appids)))) as pool:
        futures = [pool.submit(_steam_release_detail, appid, ua) for appid in appids]
        for fut in as_completed(futures):
            appid, release_iso, release_text = fut.result()
            details[appid] = (release_iso, release_text)

    rows = []
    for item in items:
        if int(item.get("type", 0)) != 0:
            continue
        appid = int(item.get("id") or 0)
        title = repair_text(item.get("name"))
        release_date, release_text = details.get(appid, ("", ""))
        if not appid or not title or not release_date:
            continue
        app_url = f"https://store.steampowered.com/app/{appid}/"
        cover = item.get("large_capsule_image") or item.get("header_image") or item.get("small_capsule_image") or ""
        rows.append({
            "id": stable_id(source_id, app_url),
            "category": "pc",
            "source": source_id,
            "source_label": source_label,
            "store": "Steam",
            "title": title,
            "url": app_url,
            "cover": cover,
            "platforms": ["PC"],
            "release_date": release_date,
            "release_text": release_text,
            "featured": True,
            "popularity_label": "Steam 精选",
        })
    return rows


def _famitsu_platforms(text: str):
    found = []
    for p in PLATFORM_RE.findall(text or ""):
        p = p.upper()
        if p == "STEAM":
            p = "PC"
        elif p.startswith("XBOX SERIES"):
            p = "XSX"
        elif p == "XBOX ONE":
            p = "XONE"
        if p not in found:
            found.append(p)
    return found


def _month_iter(start: date, end: date):
    current = date(start.year, start.month, 1)
    last = date(end.year, end.month, 1)
    while current <= last:
        yield current
        current = date(current.year + 1, 1, 1) if current.month == 12 else date(current.year, current.month + 1, 1)


def fetch_famitsu_console_window(cfg: dict, ua: str, start_date: date, end_date: date):
    base_url = (cfg.get("url") or "https://www.famitsu.com/schedule").rstrip("/")
    rows, seen = [], set()
    for month in _month_iter(start_date, end_date):
        url = f"{base_url}/all-platforms/{month:%Y%m}" if base_url.endswith("/schedule") else base_url
        soup = BeautifulSoup(get_html(url, ua), "lxml")
        for heading in soup.find_all(["h2", "h3"]):
            heading_text = clean(heading.get_text(" "))
            dm = DATE_JP_RE.search(heading_text)
            if not dm:
                continue
            release_date = date(int(dm.group(1)), int(dm.group(2)), int(dm.group(3)))
            if not (start_date <= release_date <= end_date):
                continue
            release_iso = release_date.isoformat()
            for node in heading.find_all_next():
                if node is not heading and getattr(node, "name", None) in ("h2", "h3") and DATE_JP_RE.search(clean(node.get_text(" "))):
                    break
                if getattr(node, "name", None) != "a" or not node.get("href"):
                    continue
                text = repair_text(node.get_text(" "))
                if not text or text in ("その他のバージョンを見る", "詳細を見る") or len(text) > 180:
                    continue
                card = closest_card(node, 1200)
                context = repair_text(card.get_text(" ")) if card else text
                platforms = _famitsu_platforms(context)
                if not any(p in CONSOLE_PLATFORMS for p in platforms):
                    continue
                href = urljoin(url, node.get("href") or "")
                title = re.sub(r"^(?:Switch2|Switch|PS5|PS4|XSX|XONE|PC)\s*", "", text, flags=re.I)
                title = re.sub(r"\s+\d[\d,]*円.*$", "", title).strip()
                title = re.sub(r"\s*価格\s*未定.*$", "", title).strip()
                if len(title) < 2:
                    continue
                key = (release_iso, title.casefold(), tuple(platforms))
                if key in seen:
                    continue
                seen.add(key)
                rows.append({
                    "id": stable_id("famitsu-console", href, f"{release_iso}|{title}"),
                    "category": "console",
                    "source": "famitsu",
                    "source_label": "Famitsu 日本游戏发行日",
                    "store": "发行日历",
                    "title": title,
                    "url": href,
                    "cover": image_from(card, url),
                    "platforms": platforms,
                    "release_date": release_iso,
                    "release_text": heading_text,
                })
    return rows


def dedupe(rows):
    out, seen = [], set()
    for row in sorted(rows, key=lambda x: (bool(x.get("featured")), bool(x.get("cover"))), reverse=True):
        key = (
            row.get("category"),
            row.get("release_date") or row.get("first_seen") or "",
            re.sub(r"\W+", "", row.get("title", "").lower()),
        )
        if not key[2] or key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def _as_date(value: str):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except Exception:
        return None


def _decorate_timeline(row, today: date):
    effective = _as_date(row.get("release_date") or row.get("first_seen") or "")
    if not effective:
        row["timeline_status"] = "unknown"
        row["days_from_today"] = None
        row["is_today"] = False
        return row
    delta = (effective - today).days
    row["days_from_today"] = delta
    row["is_today"] = delta == 0
    row["timeline_status"] = "today" if delta == 0 else ("past" if delta < 0 else "upcoming")
    return row


def refresh_games(content_cfg: dict, generated: str, output_path: Path, state_path: Path, ua: str):
    cfg = content_cfg.get("games", {}) or {}
    today = datetime.now(timezone.utc).astimezone(JST).date()
    today_jst = today.isoformat()
    past_days = int(cfg.get("past_days", 7))
    future_days = int(cfg.get("future_days", 90))
    past_start = today - timedelta(days=past_days)
    future_end = today + timedelta(days=future_days)

    try:
        old_state = json.loads(state_path.read_text("utf-8"))
    except Exception:
        old_state = {"seen": {}}
    seen_state = old_state.get("seen", {}) if isinstance(old_state, dict) else {}

    rows, statuses = [], {}
    source_cfg = cfg.get("sources", {}) if isinstance(cfg.get("sources", {}), dict) else {}

    # Mobile: JP storefront discovery + CN TapTap popularity-filtered discovery.
    # App Store / Google Play rows use first discovery as their date. TapTap upcoming
    # rows carry explicit future release dates. Source limits are intentionally small
    # so mobile never becomes an unfiltered storefront dump.
    for sid, label, fn in [
        ("appstore", "App Store 日本 · 新着精选", fetch_appstore_new),
        ("googleplay", "Google Play 日本 · 新規リリース精选", fetch_googleplay_new),
        ("taptap_cn_new", "TapTap 中国 · 新品榜", fetch_taptap_new),
        ("taptap_cn_upcoming", "TapTap 中国 · 即将首发", fetch_taptap_upcoming),
    ]:
        scfg = source_cfg.get(sid, {})
        if scfg.get("enabled", True) is False:
            continue
        try:
            found = fn(scfg, ua)
            if not found:
                raise RuntimeError("No items parsed")
            for row in found:
                prior = seen_state.get(row["id"])
                if not prior and row.get("legacy_id"):
                    prior = seen_state.get(row["legacy_id"])
                first_seen = (prior or {}).get("first_seen") or today_jst
                row["first_seen"] = first_seen
                row.pop("legacy_id", None)
                rows.append(row)
                seen_state[row["id"]] = {
                    "first_seen": first_seen,
                    "last_seen": today_jst,
                    "title": row["title"],
                    "source": sid,
                }
            statuses[sid] = {"label": label, "ok": True, "count": len(found), "checked_at": generated}
            print(f"GAMES {sid}: {len(found)} items")
        except Exception as e:
            statuses[sid] = {"label": label, "ok": False, "count": 0, "checked_at": generated, "error": f"{type(e).__name__}: {e}"}
            print(f"GAMES ERR {sid}: {e}")

    # Steam: use storefront curated JSON sets + appdetails for exact dates.
    steam_specs = [
        ("steam_popular_new", "Steam · 精选新品", "new_releases"),
        ("steam_popular_upcoming", "Steam · 精选即将推出", "coming_soon"),
    ]
    for sid, label, category in steam_specs:
        scfg = source_cfg.get(sid, {})
        if scfg.get("enabled", True) is False:
            continue
        try:
            found = fetch_steam_featured(scfg, ua, sid, label, category)
            raw_count = len(found)
            filtered = []
            for row in found:
                d = _as_date(row.get("release_date", ""))
                if d and past_start <= d <= future_end:
                    filtered.append(row)
            rows.extend(filtered)
            statuses[sid] = {
                "label": label,
                "ok": bool(raw_count),
                "count": len(filtered),
                "raw_count": raw_count,
                "checked_at": generated,
            }
            if not raw_count:
                statuses[sid]["error"] = "No items parsed"
            print(f"GAMES {sid}: {len(filtered)} timeline items ({raw_count} raw)")
        except Exception as e:
            statuses[sid] = {"label": label, "ok": False, "count": 0, "raw_count": 0, "checked_at": generated, "error": f"{type(e).__name__}: {e}"}
            print(f"GAMES ERR {sid}: {e}")

    # Console: Famitsu supplies exact dates and already works reliably in this repo.
    famitsu_cfg = source_cfg.get("famitsu", {})
    if famitsu_cfg.get("enabled", True) is not False:
        try:
            found = fetch_famitsu_console_window(famitsu_cfg, ua, past_start, future_end)
            rows.extend(found)
            statuses["famitsu"] = {"label": "Famitsu 日本游戏发行日", "ok": bool(found), "count": len(found), "checked_at": generated}
            if not found:
                statuses["famitsu"]["error"] = "No items parsed"
            print(f"GAMES famitsu: {len(found)} timeline items")
        except Exception as e:
            statuses["famitsu"] = {"label": "Famitsu 日本游戏发行日", "ok": False, "count": 0, "checked_at": generated, "error": f"{type(e).__name__}: {e}"}
            print(f"GAMES ERR famitsu: {e}")

    decorated = [_decorate_timeline(x, today) for x in dedupe(rows)]
    mobile = []
    for x in decorated:
        if x.get("category") != "mobile":
            continue
        release_d = _as_date(x.get("release_date", ""))
        seen_d = _as_date(x.get("first_seen", ""))
        if release_d:
            if past_start <= release_d <= future_end:
                mobile.append(x)
        elif seen_d and seen_d >= past_start:
            mobile.append(x)

    # Final mobile cap by region/status. This prevents one storefront refresh from
    # flooding the page while retaining a useful mix of JP/CN recent and CN upcoming.
    mf = cfg.get("mobile_filter", {}) or {}
    jp_recent_limit = int(mf.get("jp_recent_limit", 10))
    cn_recent_limit = int(mf.get("cn_recent_limit", 8))
    cn_upcoming_limit = int(mf.get("cn_upcoming_limit", 8))
    jp_recent = [x for x in mobile if x.get("region") == "JP" and x.get("timeline_status") != "upcoming"]
    jp_recent.sort(key=lambda x: (0 if x.get("source") == "appstore" else 1, x.get("title", "").casefold()))
    jp_recent = jp_recent[:jp_recent_limit]
    cn_recent = [x for x in mobile if x.get("region") == "CN" and x.get("timeline_status") != "upcoming"]
    cn_recent.sort(key=lambda x: (x.get("popularity_rank") or 999, -(x.get("rating") or 0)))
    cn_recent = cn_recent[:cn_recent_limit]
    cn_upcoming = [x for x in mobile if x.get("region") == "CN" and x.get("timeline_status") == "upcoming"]
    cn_upcoming.sort(key=lambda x: (x.get("release_date") or "9999-99-99", -(x.get("rating") or 0)))
    cn_upcoming = cn_upcoming[:cn_upcoming_limit]
    mobile = jp_recent + cn_recent + cn_upcoming
    pc = [x for x in decorated if x.get("category") == "pc" and x.get("timeline_status") in ("past", "today", "upcoming")]
    console = [x for x in decorated if x.get("category") == "console" and x.get("timeline_status") in ("past", "today", "upcoming")]

    # Chronological timeline. Same-day featured items retain their source ordering reasonably well.
    key_fn = lambda x: (x.get("release_date") or x.get("first_seen") or "9999-99-99", x.get("title", "").casefold())
    mobile.sort(key=key_fn)
    pc.sort(key=key_fn)
    console.sort(key=key_fn)

    limit = int(cfg.get("limit_per_category", 160))
    payload = {
        "generated_at": generated,
        "date_jst": today_jst,
        "window": {"past_days": past_days, "future_days": future_days, "start": past_start.isoformat(), "end": future_end.isoformat()},
        "items": {"mobile": mobile[:limit], "pc": pc[:limit], "console": console[:limit]},
        "sources": statuses,
    }
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", "utf-8")
    state_path.write_text(json.dumps({"generated_at": generated, "seen": seen_state}, ensure_ascii=False, indent=2) + "\n", "utf-8")
