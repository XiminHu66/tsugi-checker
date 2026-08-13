from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

JST = timezone(timedelta(hours=9))
DATE_JP_RE = re.compile(r"(20\d{2})年\s*(\d{1,2})月\s*(\d{1,2})日")
DATE_EN_RE = re.compile(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2}),\s+(20\d{2})\b", re.I)
PLATFORM_RE = re.compile(r"\b(Switch2|Switch|PS5|PS4|XSX|XONE|Xbox Series X\|S|Xbox One|PC|Steam)\b", re.I)
MONTHS = {m.lower(): i for i, m in enumerate(("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"), 1)}


def clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def stable_id(source: str, url: str, title: str) -> str:
    return hashlib.sha1(f"{source}|{url}|{title}".encode("utf-8")).hexdigest()[:16]


def get_html(url: str, ua: str, timeout: int = 30) -> str:
    r = requests.get(
        url,
        headers={"User-Agent": ua, "Accept-Language": "ja-JP,ja;q=0.95,en;q=0.7"},
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
    # Prefer short visible child nodes before using the entire marketing card.
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
        # Google Play cards often append rating/category to text; aria-label/image alt is preferred above.
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


def fetch_steam_recent(cfg: dict, ua: str):
    url = cfg.get("url") or "https://store.steampowered.com/search/?sort_by=Released_DESC&category1=998&l=japanese&cc=jp"
    html = get_html(url, ua)
    soup = BeautifulSoup(html, "lxml")
    rows = []
    for a in soup.select("a.search_result_row")[: int(cfg.get("limit", 60))]:
        title_node = a.select_one("span.title") or a.select_one(".title")
        title = clean(title_node.get_text(" ")) if title_node else ""
        href = a.get("href") or ""
        if not title or not href:
            continue
        date_node = a.select_one(".search_released")
        date_text = clean(date_node.get_text(" ")) if date_node else ""
        release_date = parse_jp_date(date_text) or parse_en_date(date_text)
        img = a.select_one("img")
        cover = (img.get("src") or img.get("data-src") or "") if img else ""
        rows.append({
            "id": stable_id("steam", href.split("?")[0], title),
            "category": "pc",
            "source": "steam",
            "source_label": "Steam · Recently Released",
            "store": "Steam",
            "title": title,
            "url": href,
            "cover": cover,
            "platforms": ["PC"],
            "release_date": release_date,
            "release_text": date_text,
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


def fetch_famitsu_today(cfg: dict, ua: str, today_jst: str):
    dt = datetime.strptime(today_jst, "%Y-%m-%d")
    base = (cfg.get("url") or "https://www.famitsu.com/schedule").rstrip("/")
    url = f"{base}/all-platforms/{dt:%Y%m}" if base.endswith("/schedule") else base
    html = get_html(url, ua)
    soup = BeautifulSoup(html, "lxml")
    target = f"{dt.year}年{dt.month}月{dt.day}日"
    headings = [h for h in soup.find_all(["h2", "h3"]) if target in clean(h.get_text(" "))]
    rows = []
    seen = set()
    for heading in headings:
        for node in heading.find_all_next():
            if node is not heading and getattr(node, "name", None) in ("h2", "h3") and DATE_JP_RE.search(clean(node.get_text(" "))):
                break
            if getattr(node, "name", None) != "a" or not node.get("href"):
                continue
            text = clean(node.get_text(" "))
            if not text or text in ("その他のバージョンを見る", "詳細を見る") or len(text) > 160:
                continue
            card = closest_card(node, 900)
            context = clean(card.get_text(" ")) if card else text
            platforms = _famitsu_platforms(context)
            if not platforms:
                continue
            href = urljoin(url, node.get("href") or "")
            # Remove a leading platform label and trailing price/edition boilerplate.
            title = re.sub(r"^(?:Switch2|Switch|PS5|PS4|XSX|XONE|PC)\s*", "", text, flags=re.I)
            title = re.sub(r"\s+\d[\d,]*円.*$", "", title).strip()
            if len(title) < 2:
                continue
            key = (title.lower(), tuple(platforms))
            if key in seen:
                continue
            seen.add(key)
            base = {
                "id": stable_id("famitsu", href, title),
                "source": "famitsu",
                "source_label": "Famitsu 日本游戏发行日",
                "store": "发行日历",
                "title": title,
                "url": href,
                "cover": image_from(card, url),
                "platforms": platforms,
                "release_date": today_jst,
                "release_text": target,
            }
            if any(p == "PC" for p in platforms):
                rows.append({**base, "id": stable_id("famitsu-pc", href, title), "category": "pc"})
            if any(p in {"SWITCH", "SWITCH2", "PS5", "PS4", "XSX", "XONE"} for p in platforms):
                rows.append({**base, "id": stable_id("famitsu-console", href, title), "category": "console"})
    return rows


def dedupe(rows):
    out = []
    seen = set()
    # Prefer exact release-date rows over discovery-only rows, and rows with covers over rows without.
    for row in sorted(rows, key=lambda x: (bool(x.get("release_date")), bool(x.get("cover"))), reverse=True):
        key = (row.get("category"), re.sub(r"\W+", "", row.get("title", "").lower()))
        if not key[1] or key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def refresh_games(content_cfg: dict, generated: str, output_path: Path, state_path: Path, ua: str):
    cfg = content_cfg.get("games", {}) or {}
    today_jst = datetime.now(timezone.utc).astimezone(JST).date().isoformat()
    old_state = {}
    try:
        old_state = json.loads(state_path.read_text("utf-8"))
    except Exception:
        old_state = {"seen": {}}
    seen_state = old_state.get("seen", {}) if isinstance(old_state, dict) else {}
    baseline = not bool(seen_state)

    rows = []
    statuses = {}
    fetchers = [
        ("appstore", "App Store 日本 · 新着游戏", fetch_appstore_new),
        ("googleplay", "Google Play 日本 · 新規リリース", fetch_googleplay_new),
        ("steam", "Steam · Recently Released", fetch_steam_recent),
    ]
    source_cfg = cfg.get("sources", {}) if isinstance(cfg.get("sources", {}), dict) else {}
    for sid, label, fn in fetchers:
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

    fcfg = source_cfg.get("famitsu", {})
    if fcfg.get("enabled", True) is not False:
        try:
            found = fetch_famitsu_today(fcfg, ua, today_jst)
            rows.extend(found)
            statuses["famitsu"] = {"label": "Famitsu 日本游戏发行日", "ok": True, "count": len(found), "checked_at": generated}
            print(f"GAMES famitsu: {len(found)} items")
        except Exception as e:
            statuses["famitsu"] = {"label": "Famitsu 日本游戏发行日", "ok": False, "count": 0, "checked_at": generated, "error": f"{type(e).__name__}: {e}"}
            print(f"GAMES ERR famitsu: {e}")

    rows = dedupe(rows)
    new_seen = dict(seen_state)
    for row in rows:
        sid = row["id"]
        old = seen_state.get(sid, {})
        first_seen = old.get("first_seen") or today_jst
        row["first_seen"] = first_seen
        # Exact official/release-calendar dates take priority. Discovery-only mobile rows become NEW only after baseline.
        row["is_today"] = bool(row.get("release_date") == today_jst or (not row.get("release_date") and not baseline and first_seen == today_jst))
        new_seen[sid] = {"first_seen": first_seen, "last_seen": today_jst, "title": row.get("title"), "source": row.get("source")}

    grouped = {"mobile": [], "pc": [], "console": []}
    for row in rows:
        if row.get("category") in grouped:
            grouped[row["category"]].append(row)
    for key in grouped:
        grouped[key].sort(key=lambda x: (bool(x.get("is_today")), x.get("release_date") or x.get("first_seen") or ""), reverse=True)
        grouped[key] = grouped[key][: int(cfg.get("limit_per_category", 80))]

    state_path.write_text(json.dumps({"generated_at": generated, "seen": new_seen}, ensure_ascii=False, indent=2) + "\n", "utf-8")
    output_path.write_text(json.dumps({
        "generated_at": generated,
        "date_jst": today_jst,
        "items": grouped,
        "sources": statuses,
    }, ensure_ascii=False, indent=2) + "\n", "utf-8")
