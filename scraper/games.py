from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

JST = timezone(timedelta(hours=9))
DATE_JP_RE = re.compile(r"(20\d{2})年\s*(\d{1,2})月\s*(\d{1,2})日")
DATE_EN_RE = re.compile(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2}),\s+(20\d{2})\b", re.I)
PLATFORM_RE = re.compile(r"\b(Switch2|Switch|PS5|PS4|XSX|XONE|Xbox Series X\|S|Xbox One|PC|Steam)\b", re.I)
MONTHS = {m.lower(): i for i, m in enumerate(("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"), 1)}
CONSOLE_PLATFORMS = {"SWITCH", "SWITCH2", "PS5", "PS4", "XSX", "XONE"}


def clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def stable_id(source: str, url: str, title: str) -> str:
    return hashlib.sha1(f"{source}|{url}|{title}".encode("utf-8")).hexdigest()[:16]


def get_html(url: str, ua: str, timeout: int = 30, accept_language: str = "ja-JP,ja;q=0.95,en;q=0.7") -> str:
    r = requests.get(
        url,
        headers={"User-Agent": ua, "Accept-Language": accept_language},
        timeout=timeout,
    )
    r.raise_for_status()
    return r.text


def get_browser_html(url: str, ua: str, locale: str = "ja-JP", wait_ms: int = 2200) -> str:
    """Render storefront pages that return a mostly empty app shell to plain requests."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=ua, locale=locale)
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
    return f"{int(m.group(3)):04d}-{MONTHS[m.group(1).lower()]:02d}-{int(m.group(2)):02d}"


def parse_any_date(text: str) -> str:
    return parse_jp_date(text) or parse_en_date(text)


def image_from(node, base: str) -> str:
    if not node:
        return ""
    img = node.select_one("img") if hasattr(node, "select_one") else None
    if not img:
        return ""
    src = img.get("src") or img.get("data-src") or img.get("data-original") or ""
    if not src or src.startswith("data:"):
        return ""
    return urljoin(base, src)


def closest_card(anchor, max_chars: int = 650):
    for p in anchor.parents:
        if getattr(p, "name", None) not in ("li", "article", "div", "section"):
            continue
        text = clean(p.get_text(" "))
        if 2 <= len(text) <= max_chars:
            return p
    return anchor.parent


def app_title(anchor, card=None) -> str:
    noise = {"表示", "入手", "開く", "インストール", "install", "open", "view"}
    nodes = [anchor]
    if card is not None and card is not anchor:
        nodes.append(card)
    for node in nodes:
        for key in ("aria-label", "title"):
            t = clean(node.get(key)) if hasattr(node, "get") else ""
            if 2 <= len(t) <= 120 and t.casefold() not in noise:
                return t
        img = node.select_one("img") if hasattr(node, "select_one") else None
        if img:
            t = clean(img.get("alt") or img.get("aria-label"))
            if 2 <= len(t) <= 120 and t.casefold() not in noise:
                return t
        for sel in ("h1", "h2", "h3", "h4", "strong", ".title", "[data-testid*=title]", "span"):
            n = node.select_one(sel) if hasattr(node, "select_one") else None
            t = clean(n.get_text(" ")) if n else ""
            if 2 <= len(t) <= 120 and t.casefold() not in noise:
                return t
    text = clean((card or anchor).get_text(" "))
    text = re.sub(r"\s+[0-5](?:\.[0-9])?\s*(?:star|★).*$", "", text, flags=re.I)
    text = re.sub(r"\s+(?:表示|入手|インストール).*$", "", text)
    return text[:120] if 2 <= len(text) <= 180 and text.casefold() not in noise else ""


def section_links(soup: BeautifulSoup, marker_re: re.Pattern, href_re: re.Pattern, limit: int = 36):
    marker = soup.find(string=marker_re)
    start = marker.parent if marker else soup
    out = []
    seen = set()
    for a in start.find_all_next("a", href=True):
        href = a.get("href") or ""
        if not href_re.search(href):
            continue
        if href in seen:
            continue
        seen.add(href)
        out.append(a)
        if len(out) >= limit:
            break
    return out


def _store_anchors(soup: BeautifulSoup, href_re: re.Pattern, limit: int):
    out = []
    seen = set()
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
    anchors = _store_anchors(soup, href_re, max(limit * 3, limit))
    rows = []
    seen = set()
    for a in anchors:
        href = urljoin(url, a.get("href") or "")
        if href in seen:
            continue
        card = closest_card(a, 1000)
        title = app_title(a, card)
        if not title:
            continue
        # Skip generic CTAs accidentally captured as titles.
        if title.casefold() in {"表示", "入手", "open", "install", "view"}:
            continue
        seen.add(href)
        rows.append({
            "id": stable_id(source, href, title),
            "category": "mobile",
            "source": source,
            "source_label": label,
            "store": store,
            "title": title,
            "url": href,
            "cover": image_from(card, url),
            "platforms": [platform],
            "release_date": "",
        })
        if len(rows) >= limit:
            break
    return rows


def fetch_appstore_new(cfg: dict, ua: str):
    url = cfg.get("url") or "https://apps.apple.com/jp/iphone/room/1435822938"
    limit = int(cfg.get("limit", 36))
    label = "App Store 日本 · 新着游戏"
    href_re = re.compile(r"(?:https?://apps\.apple\.com)?/jp/app/|/app/", re.I)
    html = get_html(url, ua)
    rows = _parse_mobile_store(html, url, "appstore", label, "iOS / iPadOS", "iOS", href_re, limit)
    if not rows:
        html = get_browser_html(url, ua, "ja-JP")
        rows = _parse_mobile_store(html, url, "appstore", label, "iOS / iPadOS", "iOS", href_re, limit)
    return rows


def fetch_googleplay_new(cfg: dict, ua: str):
    # A dedicated Google Play collection is much more stable than trying to locate
    # the section inside the generic /store/games landing page.
    url = cfg.get("url") or "https://play.google.com/store/apps/collection/promotion_3000791_new_releases_games?hl=ja&gl=jp"
    limit = int(cfg.get("limit", 36))
    label = "Google Play 日本 · 新規リリース"
    href_re = re.compile(r"/store/apps/details\?(?:[^#]*&)?id=", re.I)
    html = get_html(url, ua)
    rows = _parse_mobile_store(html, url, "googleplay", label, "Android", "Android", href_re, limit)
    if not rows:
        html = get_browser_html(url, ua, "ja-JP", 3000)
        rows = _parse_mobile_store(html, url, "googleplay", label, "Android", "Android", href_re, limit)
    return rows


def _steam_result_html(cfg: dict, ua: str, source_id: str) -> str:
    """Use Steam's search-results response instead of the JS-heavy search shell."""
    page_url = cfg.get("url") or ""
    parsed = urlparse(page_url)
    qs = parse_qs(parsed.query)
    filter_name = (qs.get("filter") or ["popularnew" if source_id == "steam_popular_new" else "popularcomingsoon"])[0]
    sort_by = (qs.get("sort_by") or ["Released_DESC" if source_id == "steam_popular_new" else "Released_ASC"])[0]
    limit = int(cfg.get("limit", 100))
    endpoint = "https://store.steampowered.com/search/results/"
    params = {
        "filter": filter_name,
        "start": 0,
        "count": limit,
        "sort_by": sort_by,
        "cc": "jp",
        "l": "english",
        "ignore_preferences": 1,
        "infinite": 1,
        "json": 1,
    }
    r = requests.get(endpoint, params=params, headers={"User-Agent": ua, "Accept-Language": "en-US,en;q=0.9"}, timeout=30)
    r.raise_for_status()
    try:
        data = r.json()
    except Exception:
        data = {}
    html = data.get("results_html") or data.get("html") or ""
    if html:
        return html
    # Fallback to a rendered search page if Steam changes the JSON envelope.
    fallback = page_url or f"https://store.steampowered.com/search/?filter={filter_name}&sort_by={sort_by}&l=english&cc=jp&ignore_preferences=1"
    joiner = "&" if "?" in fallback else "?"
    if "ignore_preferences=" not in fallback:
        fallback += joiner + "ignore_preferences=1"
    return get_browser_html(fallback, ua, "en-US", 2500)


def fetch_steam_popular(cfg: dict, ua: str, source_id: str, source_label: str):
    html = _steam_result_html(cfg, ua, source_id)
    soup = BeautifulSoup(html, "lxml")
    rows = []
    for a in soup.select("a.search_result_row")[: int(cfg.get("limit", 100))]:
        title_node = a.select_one("span.title") or a.select_one(".title")
        title = clean(title_node.get_text(" ")) if title_node else ""
        href = a.get("href") or ""
        if not title or not href:
            continue
        date_node = a.select_one(".search_released")
        date_text = clean(date_node.get_text(" ")) if date_node else ""
        release_date = parse_any_date(date_text)
        if not release_date:
            continue
        img = a.select_one("img")
        cover = (img.get("src") or img.get("data-src") or "") if img else ""
        clean_url = href.split("?")[0]
        rows.append({
            "id": stable_id(source_id, clean_url, title),
            "category": "pc",
            "source": source_id,
            "source_label": source_label,
            "store": "Steam",
            "title": title,
            "url": href,
            "cover": cover,
            "platforms": ["PC"],
            "release_date": release_date,
            "release_text": date_text,
            "featured": True,
            "popularity_label": "Steam 热门",
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
        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)


def fetch_famitsu_console_window(cfg: dict, ua: str, start_date: date, end_date: date):
    base_url = (cfg.get("url") or "https://www.famitsu.com/schedule").rstrip("/")
    rows = []
    seen = set()
    for month in _month_iter(start_date, end_date):
        url = f"{base_url}/all-platforms/{month:%Y%m}" if base_url.endswith("/schedule") else base_url
        html = get_html(url, ua)
        soup = BeautifulSoup(html, "lxml")
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
                text = clean(node.get_text(" "))
                if not text or text in ("その他のバージョンを見る", "詳細を見る") or len(text) > 180:
                    continue
                card = closest_card(node, 1000)
                context = clean(card.get_text(" ")) if card else text
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
    out = []
    seen = set()
    for row in sorted(rows, key=lambda x: (bool(x.get("featured")), bool(x.get("cover"))), reverse=True):
        key = (row.get("category"), row.get("release_date") or row.get("first_seen") or "", re.sub(r"\W+", "", row.get("title", "").lower()))
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

    rows = []
    statuses = {}
    source_cfg = cfg.get("sources", {}) if isinstance(cfg.get("sources", {}), dict) else {}

    # Mobile: store discovery dates. App stores don't provide a reliable future release calendar.
    for sid, label, fn in [
        ("appstore", "App Store 日本 · 新着游戏", fetch_appstore_new),
        ("googleplay", "Google Play 日本 · 新規リリース", fetch_googleplay_new),
    ]:
        scfg = source_cfg.get(sid, {})
        if scfg.get("enabled", True) is False:
            continue
        try:
            found = fn(scfg, ua)
            rows.extend(found)
            statuses[sid] = {"label": label, "ok": bool(found), "count": len(found), "checked_at": generated}
            if not found:
                statuses[sid]["error"] = "No items parsed"
            print(f"GAMES {sid}: {len(found)} items")
        except Exception as e:
            statuses[sid] = {"label": label, "ok": False, "count": 0, "checked_at": generated, "error": f"{type(e).__name__}: {e}"}
            print(f"GAMES ERR {sid}: {e}")

    # PC: deliberately use Steam's own popularity-curated lists instead of every release.
    steam_defs = [
        ("steam_popular_new", "Steam · Popular New Releases"),
        ("steam_popular_upcoming", "Steam · Popular Upcoming"),
    ]
    for sid, label in steam_defs:
        scfg = source_cfg.get(sid, {})
        if scfg.get("enabled", True) is False:
            continue
        try:
            found = fetch_steam_popular(scfg, ua, sid, label)
            filtered = []
            for row in found:
                d = _as_date(row.get("release_date") or "")
                if not d:
                    continue
                if sid == "steam_popular_new" and past_start <= d <= today:
                    filtered.append(row)
                elif sid == "steam_popular_upcoming" and today < d <= future_end:
                    filtered.append(row)
            rows.extend(filtered)
            statuses[sid] = {"label": label, "ok": bool(found), "count": len(filtered), "raw_count": len(found), "checked_at": generated}
            if not found:
                statuses[sid]["error"] = "No Steam results parsed"
            print(f"GAMES {sid}: {len(filtered)} timeline items ({len(found)} raw)")
        except Exception as e:
            statuses[sid] = {"label": label, "ok": False, "count": 0, "checked_at": generated, "error": f"{type(e).__name__}: {e}"}
            print(f"GAMES ERR {sid}: {e}")

    # Console: Famitsu provides explicit Japanese release dates across multiple months.
    fcfg = source_cfg.get("famitsu", {})
    if fcfg.get("enabled", True) is not False:
        try:
            found = fetch_famitsu_console_window(fcfg, ua, past_start, future_end)
            rows.extend(found)
            statuses["famitsu"] = {"label": "Famitsu 日本游戏发行日", "ok": True, "count": len(found), "checked_at": generated}
            print(f"GAMES famitsu: {len(found)} timeline items")
        except Exception as e:
            statuses["famitsu"] = {"label": "Famitsu 日本游戏发行日", "ok": False, "count": 0, "checked_at": generated, "error": f"{type(e).__name__}: {e}"}
            print(f"GAMES ERR famitsu: {e}")

    # Persist mobile discovery history so the UI can actually show the previous 7 days.
    new_seen = dict(seen_state)
    current_mobile_ids = set()
    for row in rows:
        if row.get("category") != "mobile":
            continue
        sid = row["id"]
        current_mobile_ids.add(sid)
        old = seen_state.get(sid, {}) if isinstance(seen_state.get(sid, {}), dict) else {}
        first_seen = old.get("first_seen") or today_jst
        row["first_seen"] = first_seen
        new_seen[sid] = {
            "first_seen": first_seen,
            "last_seen": today_jst,
            "title": row.get("title"),
            "source": row.get("source"),
            "row": {k: v for k, v in row.items() if k not in ("is_today", "timeline_status", "days_from_today")},
        }

    # Rehydrate mobile games first seen within the last 7 days even if a store list rotated them out.
    for sid, saved in seen_state.items():
        if sid in current_mobile_ids or not isinstance(saved, dict):
            continue
        first = _as_date(saved.get("first_seen") or "")
        row = saved.get("row")
        if first and past_start <= first <= today and isinstance(row, dict) and row.get("category") == "mobile":
            restored = dict(row)
            restored["first_seen"] = saved.get("first_seen")
            rows.append(restored)

    rows = dedupe(rows)
    rows = [_decorate_timeline(row, today) for row in rows]

    grouped = {"mobile": [], "pc": [], "console": []}
    for row in rows:
        category = row.get("category")
        if category not in grouped:
            continue
        effective = _as_date(row.get("release_date") or row.get("first_seen") or "")
        if category == "mobile":
            if not effective or not (past_start <= effective <= today):
                continue
        else:
            if not effective or not (past_start <= effective <= future_end):
                continue
        grouped[category].append(row)

    for key in grouped:
        grouped[key].sort(key=lambda x: (x.get("release_date") or x.get("first_seen") or "", x.get("title") or ""))
        grouped[key] = grouped[key][: int(cfg.get("limit_per_category", 160))]

    # Prune discovery state after a reasonable retention window.
    retention_start = today - timedelta(days=max(past_days + 30, 45))
    pruned_seen = {}
    for sid, saved in new_seen.items():
        if not isinstance(saved, dict):
            continue
        first = _as_date(saved.get("first_seen") or "")
        last = _as_date(saved.get("last_seen") or "")
        if (last and last >= retention_start) or (first and first >= retention_start):
            pruned_seen[sid] = saved

    state_path.write_text(json.dumps({"generated_at": generated, "seen": pruned_seen}, ensure_ascii=False, indent=2) + "\n", "utf-8")
    output_path.write_text(json.dumps({
        "generated_at": generated,
        "date_jst": today_jst,
        "window": {
            "past_days": past_days,
            "future_days": future_days,
            "start": past_start.isoformat(),
            "end": future_end.isoformat(),
        },
        "items": grouped,
        "sources": statuses,
    }, ensure_ascii=False, indent=2) + "\n", "utf-8")
