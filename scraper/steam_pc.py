from __future__ import annotations

import json
import re
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from bs4 import BeautifulSoup
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
GAME_FEED = ROOT / "data/game-releases.json"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151 Safari/537.36 TsugiUpdateChecker/1.0"

MONTHS = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}

DATE_MDY = re.compile(
    r"\b(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+(\d{1,2}),\s+(20\d{2})\b",
    re.I,
)
DATE_DMY = re.compile(
    r"\b(\d{1,2})\s+(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?),?\s+(20\d{2})\b",
    re.I,
)


def clean(value) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def parse_date(text: str) -> str:
    text = clean(text)
    m = DATE_MDY.search(text)
    if m:
        month = MONTHS.get(m.group(1).lower())
        if month:
            return f"{int(m.group(3)):04d}-{month:02d}-{int(m.group(2)):02d}"
    m = DATE_DMY.search(text)
    if m:
        month = MONTHS.get(m.group(2).lower())
        if month:
            return f"{int(m.group(3)):04d}-{month:02d}-{int(m.group(1)):02d}"
    return ""


def as_date(value: str) -> date | None:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except Exception:
        return None


def clean_store_url(url: str) -> str:
    try:
        parts = urlsplit(url)
        return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
    except Exception:
        return url.split("?")[0]


def row_from_values(source_id: str, label: str, title: str, href: str, cover: str, date_text: str) -> dict | None:
    release_date = parse_date(date_text)
    if not title or not href or not release_date:
        return None
    href = clean_store_url(href)
    m = re.search(r"/app/(\d+)", href)
    appid = m.group(1) if m else href
    return {
        "id": f"steam-{source_id}-{appid}",
        "category": "pc",
        "source": source_id,
        "source_label": label,
        "store": "Steam",
        "title": clean(title),
        "url": href,
        "cover": clean(cover),
        "platforms": ["PC"],
        "release_date": release_date,
        "release_text": clean(date_text),
        "featured": True,
        "popularity_label": "Steam 热门",
    }


def parse_results_html(html: str, source_id: str, label: str, limit: int) -> list[dict]:
    soup = BeautifulSoup(html or "", "lxml")
    out: list[dict] = []
    for a in soup.select("a.search_result_row")[:limit]:
        title_node = a.select_one("span.title") or a.select_one(".title")
        date_node = a.select_one(".search_released")
        img = a.select_one("img")
        row = row_from_values(
            source_id,
            label,
            title_node.get_text(" ") if title_node else "",
            a.get("href") or "",
            (img.get("src") or img.get("data-src") or "") if img else "",
            date_node.get_text(" ") if date_node else "",
        )
        if row:
            out.append(row)
    return out


def search_url(filter_name: str, sort_by: str) -> str:
    return (
        "https://store.steampowered.com/search/"
        f"?filter={filter_name}&sort_by={sort_by}&category1=998&os=win"
        "&ignore_preferences=1&ndl=1&cc=us&l=english"
    )


def results_api_url(filter_name: str, sort_by: str, count: int) -> str:
    return (
        "https://store.steampowered.com/search/results/"
        f"?query=&start=0&count={count}&dynamic_data=&sort_by={sort_by}"
        f"&filter={filter_name}&category1=998&os=win&ignore_preferences=1"
        "&infinite=1&cc=us&l=english"
    )


def scrape_one(page, source_id: str, label: str, filter_name: str, sort_by: str, limit: int) -> tuple[int, list[dict], str]:
    url = search_url(filter_name, sort_by)
    page.goto(url, wait_until="domcontentloaded", timeout=60000)

    # Wait for Steam's actual result rows rather than sleeping a fixed amount.
    try:
        page.wait_for_selector("a.search_result_row", timeout=20000)
    except PlaywrightTimeoutError:
        pass

    locator = page.locator("a.search_result_row")
    dom_count = locator.count()
    rows: list[dict] = []
    if dom_count:
        for i in range(min(dom_count, limit)):
            node = locator.nth(i)
            try:
                title = node.locator("span.title").first.inner_text(timeout=3000)
            except Exception:
                title = ""
            try:
                date_text = node.locator(".search_released").first.inner_text(timeout=3000)
            except Exception:
                date_text = ""
            try:
                href = node.get_attribute("href") or ""
            except Exception:
                href = ""
            try:
                img = node.locator("img").first
                cover = img.get_attribute("src") or img.get_attribute("data-src") or ""
            except Exception:
                cover = ""
            row = row_from_values(source_id, label, title, href, cover, date_text)
            if row:
                rows.append(row)

    # Fallback: ask Steam's same-origin results endpoint from inside the browser session.
    # This survives cases where the rendered search shell does not populate its DOM on CI.
    api_note = "dom"
    if not rows:
        api_url = results_api_url(filter_name, sort_by, max(limit, 50))
        try:
            raw = page.evaluate(
                """async (url) => {
                    const r = await fetch(url, {credentials: 'include'});
                    return await r.text();
                }""",
                api_url,
            )
            payload = json.loads(raw)
            html = payload.get("results_html") or payload.get("html") or ""
            rows = parse_results_html(html, source_id, label, limit)
            api_note = f"api_html={len(html)}"
        except Exception as e:
            api_note = f"api_error={type(e).__name__}: {e}"

    return dom_count, rows, api_note


def main() -> None:
    payload = json.loads(GAME_FEED.read_text("utf-8"))
    window = payload.get("window") or {}
    start = as_date(window.get("start") or "")
    end = as_date(window.get("end") or "")
    if not start or not end:
        raise RuntimeError("game-releases.json is missing a valid timeline window")

    specs = [
        ("steam_popular_new", "Steam · Popular New Releases", "popularnew", "Released_DESC", 60),
        ("steam_popular_upcoming", "Steam · Popular Upcoming", "popularcomingsoon", "Released_ASC", 80),
    ]

    pc_rows: list[dict] = []
    sources = payload.setdefault("sources", {})

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=UA,
            locale="en-US",
            viewport={"width": 1440, "height": 1200},
        )
        # Harmless storefront cookies that remove some preference/age friction.
        context.add_cookies([
            {"name": "birthtime", "value": "568022401", "domain": "store.steampowered.com", "path": "/"},
            {"name": "lastagecheckage", "value": "1-January-1988", "domain": "store.steampowered.com", "path": "/"},
        ])
        page = context.new_page()

        for source_id, label, filter_name, sort_by, limit in specs:
            try:
                dom_count, raw_rows, note = scrape_one(page, source_id, label, filter_name, sort_by, limit)
                filtered = []
                for row in raw_rows:
                    d = as_date(row.get("release_date") or "")
                    if d and start <= d <= end:
                        filtered.append(row)
                pc_rows.extend(filtered)
                sources[source_id] = {
                    "label": label,
                    "ok": bool(raw_rows),
                    "count": len(filtered),
                    "raw_count": len(raw_rows),
                    "dom_count": dom_count,
                    "checked_at": payload.get("generated_at"),
                }
                if not raw_rows:
                    sources[source_id]["error"] = f"Steam page produced no parseable dated rows ({note})"
                print(
                    f"STEAMPC {source_id}: {len(filtered)} timeline items "
                    f"({len(raw_rows)} parsed, dom={dom_count}, {note})"
                )
            except Exception as e:
                sources[source_id] = {
                    "label": label,
                    "ok": False,
                    "count": 0,
                    "raw_count": 0,
                    "checked_at": payload.get("generated_at"),
                    "error": f"{type(e).__name__}: {e}",
                }
                print(f"STEAMPC ERR {source_id}: {type(e).__name__}: {e}")

        context.close()
        browser.close()

    # Deduplicate games that may occur in both lists. Prefer the first occurrence.
    dedup: list[dict] = []
    seen: set[str] = set()
    for row in pc_rows:
        key = clean_store_url(row.get("url") or "") or row.get("id") or row.get("title")
        if key in seen:
            continue
        seen.add(key)
        dedup.append(row)

    dedup.sort(key=lambda x: (x.get("release_date") or "9999-99-99", x.get("title", "").casefold()))
    payload.setdefault("items", {})["pc"] = dedup[:120]
    GAME_FEED.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(f"STEAMPC final PC timeline: {len(dedup[:120])} items")


if __name__ == "__main__":
    main()
