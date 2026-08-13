from __future__ import annotations
import json, re
from urllib.parse import urljoin
from datetime import datetime

import feedparser
import requests
from bs4 import BeautifulSoup

BILLBOARD_URL = "https://www.billboard-japan.com/charts/detail?a=hot100"
APPLE_NEW_JSON = [
    "https://rss.marketingtools.apple.com/api/v2/jp/music/new-music/50/songs.json",
    "https://rss.marketingtools.apple.com/api/v2/jp/music/new-releases/50/songs.json",
]
APPLE_NEW_RSS = "https://itunes.apple.com/WebObjects/MZStore.woa/wpa/MRSS/newreleases/sf=143462/genre=27/limit=50/rss.xml"


def _get(url, ua, timeout=25):
    r = requests.get(url, headers={"User-Agent": ua, "Accept-Language": "ja-JP,ja;q=0.9,en;q=0.6"}, timeout=timeout)
    r.raise_for_status()
    return r


def fetch_billboard_hot100(ua, limit=30):
    r = _get(BILLBOARD_URL, ua)
    soup = BeautifulSoup(r.text, "lxml")
    text = " ".join(soup.stripped_strings)
    m = re.search(r"(20\d{2}/\d{1,2}/\d{1,2})\s*公開", text)
    chart_date = m.group(1) if m else ""
    rows = []
    for i, cell in enumerate(soup.select("td.name_td"), start=1):
        title_el = cell.select_one("p.musuc_title")
        artist_el = cell.select_one("p.artist_name")
        title = title_el.get_text(" ", strip=True) if title_el else ""
        artist = artist_el.get_text(" ", strip=True) if artist_el else ""
        if not title or not artist:
            continue
        tr = cell.find_parent("tr")
        context = " ".join(tr.stripped_strings) if tr else ""
        last_m = re.search(r"前回[：:]\s*([0-9]+|-)", context)
        weeks_m = re.search(r"チャートイン[：:]\s*([0-9]+)", context)
        img = tr.select_one("img") if tr else None
        artwork = None
        if img:
            artwork = img.get("data-src") or img.get("data-original") or img.get("src")
            if artwork:
                artwork = urljoin(BILLBOARD_URL, artwork)
        link = None
        a = title_el.find_parent("a") if title_el else None
        if not a and cell:
            a = cell.select_one("a[href]")
        if a and a.get("href"):
            link = urljoin(BILLBOARD_URL, a.get("href"))
        rows.append({
            "rank": i,
            "last_rank": last_m.group(1) if last_m else "",
            "weeks": int(weeks_m.group(1)) if weeks_m else None,
            "title": title,
            "artist": artist,
            "artwork": artwork,
            "url": link or BILLBOARD_URL,
        })
        if len(rows) >= int(limit):
            break
    if not rows:
        raise RuntimeError("Billboard JAPAN Hot 100 parser returned no rows")
    return rows, chart_date


def _apple_result(row):
    return {
        "id": str(row.get("id") or ""),
        "title": row.get("name") or row.get("title") or "",
        "artist": row.get("artistName") or row.get("artist_name") or "",
        "artist_id": str(row.get("artistId") or row.get("artist_id") or ""),
        "album": row.get("collectionName") or row.get("albumName") or "",
        "release_date": row.get("releaseDate") or row.get("release_date") or "",
        "artwork": row.get("artworkUrl100") or row.get("artworkUrl") or row.get("artwork") or "",
        "url": row.get("url") or row.get("trackViewUrl") or row.get("collectionViewUrl") or "",
    }


def fetch_apple_new_releases(ua, limit=40):
    errors = []
    for url in APPLE_NEW_JSON:
        try:
            r = _get(url, ua)
            data = r.json()
            results = (data.get("feed") or {}).get("results") or []
            out = [_apple_result(x) for x in results]
            out = [x for x in out if x["title"] and x["artist"]]
            if out:
                return out[:int(limit)], url
        except Exception as e:
            errors.append(f"{url}: {type(e).__name__}: {e}")
    try:
        r = _get(APPLE_NEW_RSS, ua)
        feed = feedparser.parse(r.content)
        out = []
        for entry in feed.entries:
            title = str(entry.get("im_name") or entry.get("title") or "").strip()
            artist = str(entry.get("im_artist") or entry.get("author") or "").strip()
            if " - " in title and not artist:
                title, artist = [x.strip() for x in title.rsplit(" - ", 1)]
            images = entry.get("im_image") or []
            artwork = ""
            if isinstance(images, list) and images:
                last = images[-1]
                artwork = last.get("href") if isinstance(last, dict) else str(last)
            release_date = str(entry.get("im_releaseDate") or entry.get("published") or "")
            link = entry.get("link") or ""
            if title and artist:
                out.append({"id": str(entry.get("id") or link), "title": title, "artist": artist, "artist_id": "", "album": "", "release_date": release_date, "artwork": artwork, "url": link})
            if len(out) >= int(limit):
                break
        if out:
            return out, APPLE_NEW_RSS
    except Exception as e:
        errors.append(f"{APPLE_NEW_RSS}: {type(e).__name__}: {e}")
    raise RuntimeError("; ".join(errors) or "Apple new releases unavailable")


def refresh_music(content_cfg, generated, out_path, ua):
    cfg = content_cfg.get("music") or {}
    weekly = []
    new_releases = []
    statuses = {}
    chart_date = ""
    try:
        weekly, chart_date = fetch_billboard_hot100(ua, cfg.get("weekly_limit", 30))
        statuses["billboard_japan"] = {"label": "Billboard JAPAN Hot 100", "ok": True, "count": len(weekly), "checked_at": generated}
        print(f"MUSIC billboard_japan: {len(weekly)} items")
    except Exception as e:
        statuses["billboard_japan"] = {"label": "Billboard JAPAN Hot 100", "ok": False, "count": 0, "checked_at": generated, "error": f"{type(e).__name__}: {e}"}
        print(f"MUSIC ERR billboard_japan: {e}")
    try:
        new_releases, used_url = fetch_apple_new_releases(ua, cfg.get("new_release_limit", 40))
        statuses["apple_japan_new"] = {"label": "Apple 日本新发行", "ok": True, "count": len(new_releases), "checked_at": generated, "endpoint": used_url}
        print(f"MUSIC apple_japan_new: {len(new_releases)} items")
    except Exception as e:
        statuses["apple_japan_new"] = {"label": "Apple 日本新发行", "ok": False, "count": 0, "checked_at": generated, "error": f"{type(e).__name__}: {e}"}
        print(f"MUSIC ERR apple_japan_new: {e}")
    out_path.write_text(json.dumps({
        "generated_at": generated,
        "chart_date": chart_date,
        "weekly_chart": weekly,
        "new_releases": new_releases,
        "sources": statuses,
    }, ensure_ascii=False, indent=2) + "\n", "utf-8")
