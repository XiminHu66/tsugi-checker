from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin

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


def app_title(anchor) -> str:
    for key in ("aria-label", "title"):
        t = clean(anchor.get(key))
        if 2 <= len(t) <= 100:
            return t
    img = anchor.select_one("img")
    if img:
        t = clean(img.get("alt"))
        if 2 <= len(t) <= 100:
            return t
    for sel in ("h2", "h3", "h4", "strong", "b", "span"):
        n = anchor.select_one(sel)
        t = clean(n.get_text(" ")) if n else ""
        if 2 <= len(t) <= 100:
            return t
    text = clean(anchor.get_text(" "))
    return text[:100] if 2 <= len(text) <= 140 else ""


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


def fetch_appstore_new(cfg: dict, ua: str):
    url = cfg.get("url") or "https://apps.apple.com/jp/iphone/room/1435822938"
    html = get_html(url, ua)
    soup = BeautifulSoup(html, "lxml")
    anchors = section_links(soup, re.compile(r"新着ゲーム|New Games", re.I), re.compile(r"/app/", re.I), int(cfg.get("limit", 36)))
    rows = []
    for a in anchors:
        title = app_title(a)
        href = urljoin(url, a.get("href") or "")
        if not title or "/app/" not in href:
            continue
        card = closest_card(a)
        rows.append({
            "id": stable_id("appstore", href, title),
            "category": "mobile",
            "source": "appstore",
            "source_label": "App Store 日本 · 新着游戏",
            "store": "iOS / iPadOS",
            "title": title,
            "url": href,
            "cover": image_from(card, url),
            "platforms": ["iOS"],
            "release_date": "",
        })
    return rows


def fetch_googleplay_new(cfg: dict, ua: str):
    url = cfg.get("url") or "https://play.google.com/store/games?hl=ja&gl=jp"
    html = get_html(url, ua)
    soup = BeautifulSoup(html, "lxml")
    anchors = section_links(soup, re.compile(r"新規リリースのゲーム|New releases", re.I), re.compile(r"/store/apps/details\?id=", re.I), int(cfg.get("limit", 36)))
    rows = []
    for a in anchors:
        title = app_title(a)
        href = urljoin("https://play.google.com", a.get("href") or "")
        if not title or "details?id=" not in href:
            continue
        card = closest_card(a)
        title = re.sub(r"\s+\d(?:\.\d)?\s*star.*$", "", title, flags=re.I).strip()
        rows.append({
            "id": stable_id("googleplay", href, title),
            "category": "mobile",
            "source": "googleplay",
            "source_label": "Google Play 日本 · 新規リリース",
            "store": "Android",
            "title": title,
            "url": href,
            "cover": image_from(card, url),
            "platforms": ["Android"],
            "release_date": "",
        })
    return rows


def fetch_steam_popular(cfg: dict, ua: str, source_id: str, source_label: str):
    url = cfg["url"]
    html = get_html(url, ua, accept_language="en-US,en;q=0.9")
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
            # Skip 'Coming soon' entries without an actual date: the timeline is date-driven.
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
            statuses[sid] = {"label": label, "ok": True, "count": len(found), "checked_at": generated}
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
            statuses[sid] = {"label": label, "ok": True, "count": len(filtered), "raw_count": len(found), "checked_at": generated}
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
