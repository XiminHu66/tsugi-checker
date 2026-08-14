from __future__ import annotations

import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
FEED = ROOT / "data/site-updates.json"
CONFIG = ROOT / "config/content.json"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151 Safari/537.36 TsugiUpdateChecker/1.0"

DATE_RE = re.compile(
    r"(20\d{2})\s*[-/.年]\s*(\d{1,2})\s*[-/.月]\s*(\d{1,2})(?:\s*日)?",
    re.I,
)

def load_json(path: Path, default):
    try:
        return json.loads(path.read_text("utf-8"))
    except Exception:
        return default

def normalize_date(value: str) -> str:
    m = DATE_RE.search(str(value or ""))
    if not m:
        return ""
    try:
        y, mo, d = map(int, m.groups())
        return datetime(y, mo, d).date().isoformat()
    except Exception:
        return ""

def soup_date(soup: BeautifulSoup) -> str:
    for node in soup.select("meta[content]"):
        key = " ".join(str(node.get(x) or "") for x in ("property", "name", "itemprop")).lower()
        if any(k in key for k in ("modified", "updated", "datemodified", "datepublished")):
            value = normalize_date(node.get("content") or "")
            if value:
                return value

    for node in soup.select("time[datetime]"):
        value = normalize_date(node.get("datetime") or "")
        if value:
            return value

    text = " ".join(soup.stripped_strings)
    for pattern in (
        r"(?:最后|最後)\s*更新(?:时间|時間|日期)?\s*[·：:\s]*(20\d{2}\s*[-/.年]\s*\d{1,2}\s*[-/.月]\s*\d{1,2}(?:\s*日)?)",
        r"(20\d{2}\s*[-/.年]\s*\d{1,2}\s*[-/.月]\s*\d{1,2}(?:\s*日)?)[^。|]{0,35}(?:最后|最後)\s*更新",
    ):
        m = re.search(pattern, text, re.I)
        if m:
            value = normalize_date(m.group(1))
            if value:
                return value
    return ""

def update_linovelib(row: dict, html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    date = soup_date(soup)
    if date:
        row["updated_text"] = date

    novel_id = ""
    m_id = re.search(r"/novel/(\d+)", row.get("url", ""))
    if m_id:
        novel_id = m_id.group(1)

    marker = soup.find(string=re.compile(r"(?:最后|最後)\s*更新", re.I))
    candidates = []
    if marker:
        node = marker.parent
        for _ in range(5):
            if not node:
                break
            if getattr(node, "select", None):
                candidates.extend(node.select("a[href]"))
            node = node.parent

    if novel_id:
        candidates.extend(
            a for a in soup.select("a[href]")
            if re.search(rf"/novel/{re.escape(novel_id)}/", a.get("href") or "")
            and "catalog" not in (a.get("href") or "").lower()
        )

    seen = set()
    for a in candidates:
        href = a.get("href") or ""
        text = " ".join(a.stripped_strings).strip()
        key = (href, text)
        if key in seen:
            continue
        seen.add(key)
        if not text:
            continue
        cleaned = re.sub(
            r"^(?:最后|最後)\s*更新(?:时间|時間|日期)?\s*[·：:\s]*"
            r"(?:20\d{2}\s*[-/.年]\s*\d{1,2}\s*[-/.月]\s*\d{1,2}(?:\s*日)?)?\s*",
            "",
            text,
            flags=re.I,
        ).strip()
        if (
            2 <= len(cleaned) <= 100
            and "catalog" not in href.lower()
            and cleaned not in ("目录", "目錄", "书籍目录", "小說目錄")
        ):
            if not row.get("latest") or row.get("latest") == "最新更新":
                row["latest"] = cleaned
            if href:
                row["latest_url"] = urljoin(row["url"], href)
            break
    return row

def update_copymanga(row: dict, html: bytes) -> dict:
    soup = BeautifulSoup(html, "lxml")
    date = soup_date(soup)
    if date:
        row["updated_text"] = date

    title_text = " ".join(soup.title.stripped_strings) if soup.title else ""
    m = re.search(r"-(第\s*[^-]{1,48}?(?:话|話|章|回|卷))-", title_text)
    if m:
        row["latest"] = m.group(1).strip()
    return row

def request_bytes(url: str) -> bytes:
    response = requests.get(
        url,
        headers={"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.6"},
        timeout=25,
    )
    response.raise_for_status()
    if len(response.content) < 500:
        raise RuntimeError(f"response too short ({len(response.content)} bytes)")
    return response.content

def enrich_copy_rows(rows: list[dict]) -> None:
    targets = [r for r in rows if r.get("source") == "copymanga" and not r.get("updated_text")]
    if not targets:
        return

    with ThreadPoolExecutor(max_workers=min(5, len(targets))) as pool:
        futures = [pool.submit(lambda row=r: update_copymanga(row, request_bytes(row["url"]))) for r in targets]
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                print(f"SITE DATE WARN copymanga: {type(e).__name__}: {e}", file=sys.stderr)

def enrich_linovelib_rows(rows: list[dict]) -> None:
    targets = [
        r for r in rows
        if r.get("source") == "linovelib"
        and (not r.get("updated_text") or not r.get("latest") or r.get("latest") == "最新更新")
    ]
    if not targets:
        return

    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=UA,
            locale="zh-CN",
            viewport={"width": 1280, "height": 900},
        )
        page = context.new_page()
        for row in targets:
            try:
                page.goto(row["url"], wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(450)
                update_linovelib(row, page.content())
            except Exception as e:
                print(
                    f"SITE DATE WARN linovelib {row.get('title')}: {type(e).__name__}: {e}",
                    file=sys.stderr,
                )
        context.close()
        browser.close()

def date_key(row: dict):
    value = normalize_date(row.get("updated_text") or "")
    if not value:
        return 0
    try:
        return datetime.fromisoformat(value).date().toordinal()
    except Exception:
        return 0

def main():
    payload = load_json(FEED, {"items": [], "sources": {}})
    cfg = load_json(CONFIG, {"site_updates": []})
    enabled_date_sources = {
        x.get("id")
        for x in cfg.get("site_updates", [])
        if x.get("enabled", True) and x.get("date_enrich", False)
    }

    rows = payload.get("items") or []
    if "copymanga" in enabled_date_sources:
        enrich_copy_rows(rows)
    if "linovelib" in enabled_date_sources:
        enrich_linovelib_rows(rows)

    for row in rows:
        normalized = normalize_date(row.get("updated_text") or "")
        if normalized:
            row["updated_text"] = normalized

    # Stable global sort: newest dates first, same-day order remains source/parser order.
    rows.sort(key=date_key, reverse=True)
    payload["items"] = rows

    statuses = payload.setdefault("sources", {})
    for sid in ("manhuagui", "linovelib", "copymanga"):
        source_rows = [r for r in rows if r.get("source") == sid]
        if not source_rows:
            continue
        missing = sum(1 for r in source_rows if not normalize_date(r.get("updated_text") or ""))
        statuses.setdefault(sid, {})["date_complete"] = len(source_rows) - missing
        statuses[sid]["date_missing"] = missing
        print(f"SITE DATE {sid}: {len(source_rows)-missing}/{len(source_rows)} dated")

    FEED.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", "utf-8")

if __name__ == "__main__":
    main()
