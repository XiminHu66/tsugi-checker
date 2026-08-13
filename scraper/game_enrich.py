from __future__ import annotations

import json
import math
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
GAME_FEED = ROOT / "data/game-releases.json"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151 Safari/537.36 TsugiUpdateChecker/1.0"

KNOWN_PUBLISHERS = (
    "capcom", "bandai namco", "square enix", "sega", "atlus", "konami",
    "koei tecmo", "ubisoft", "electronic arts", "ea games", "2k",
    "take-two", "rockstar", "xbox game studios", "microsoft",
    "bethesda", "activision", "blizzard", "sony interactive entertainment",
    "playstation publishing", "cd projekt", "valve", "devolver digital",
    "annapurna interactive", "focus entertainment", "thq nordic",
    "deep silver", "paradox interactive", "private division",
    "kepler interactive", "raw fury", "team17", "nacon", "505 games",
    "gearbox publishing", "krafton", "netease", "level infinite", "tencent",
    "hoyoverse", "mihoyo", "nexon", "pearl abyss", "ncsoft",
    "amazon games", "warner bros", "wb games", "humble games",
    "hooded horse", "plaion", "arc games", "fellow traveller",
    "playstack", "tinybuild", "curve games", "behavior interactive",
)

def clean(v) -> str:
    return re.sub(r"\s+", " ", str(v or "")).strip()

def appid_from_url(url: str) -> str:
    m = re.search(r"/app/(\d+)", url or "")
    return m.group(1) if m else ""

def apple_id_from_url(url: str) -> str:
    m = re.search(r"/id(\d+)", url or "")
    return m.group(1) if m else ""

def get_json(url: str, params=None, timeout=18):
    last = None
    for attempt in range(2):
        try:
            r = requests.get(
                url,
                params=params,
                headers={
                    "User-Agent": UA,
                    "Accept": "application/json,text/plain,*/*",
                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
                },
                timeout=timeout,
            )
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last = e
            if attempt == 0:
                time.sleep(0.35)
    raise last

def steam_details(appid: str) -> dict:
    payload = get_json(
        "https://store.steampowered.com/api/appdetails",
        {"appids": appid, "cc": "cn", "l": "schinese"},
    )
    node = payload.get(str(appid), {}) if isinstance(payload, dict) else {}
    if not node.get("success"):
        return {}
    return node.get("data") or {}

def steam_reviews(appid: str) -> dict:
    try:
        payload = get_json(
            f"https://store.steampowered.com/appreviews/{appid}",
            {
                "json": 1,
                "language": "all",
                "purchase_type": "all",
                "num_per_page": 0,
                "filter": "all",
            },
        )
    except Exception:
        return {}
    q = payload.get("query_summary") or {}
    total = int(q.get("total_reviews") or 0)
    pos = int(q.get("total_positive") or 0)
    neg = int(q.get("total_negative") or 0)
    pct = round(pos * 100 / max(1, pos + neg)) if total else None
    return {
        "review_count": total,
        "review_positive": pos,
        "review_negative": neg,
        "review_positive_percent": pct,
        "review_score_desc": clean(q.get("review_score_desc")),
    }

def is_notable_publisher(publishers: list[str]) -> tuple[bool, str]:
    for p in publishers:
        low = p.casefold()
        if any(k in low for k in KNOWN_PUBLISHERS):
            return True, p
    return False, ""

def pc_heat_fields(row: dict, review_count: int, notable: bool, notable_name: str) -> dict:
    labels = []
    level = "none"
    if review_count >= 100_000:
        labels.append("超高讨论")
        level = "high"
    elif review_count >= 20_000:
        labels.append("高讨论")
        level = "high"
    elif review_count >= 5_000:
        labels.append("热门")
        level = "medium"
    elif review_count >= 1_000:
        labels.append("有讨论度")
        level = "medium"

    upcoming = row.get("source") == "steam_popular_upcoming"
    if upcoming and not labels:
        labels.append("热门待发")
        level = "medium"

    if notable:
        labels.append("知名发行商")
        if level == "none":
            level = "medium"

    score = min(100.0, math.log10(max(1, review_count) + 1) * 19.0)
    if upcoming:
        score += 12
    if notable:
        score += 18

    return {
        "heat_label": labels[0] if labels else "",
        "heat_labels": labels,
        "heat_level": level,
        "heat_score": round(score, 2),
        "notable_publisher": notable,
        "notable_publisher_name": notable_name,
    }

def enrich_pc(row: dict) -> dict:
    out = dict(row)
    appid = appid_from_url(out.get("url", ""))
    if not appid:
        return out

    out["steam_appid"] = appid
    original_title = clean(out.get("title"))
    try:
        data = steam_details(appid)
    except Exception as e:
        out["metadata_error"] = f"appdetails: {type(e).__name__}: {e}"
        data = {}

    if data:
        cn_name = clean(data.get("name"))
        if original_title:
            out["title_en"] = original_title
        if cn_name:
            out["title_zh"] = cn_name

        developers = [clean(x) for x in (data.get("developers") or []) if clean(x)]
        publishers = [clean(x) for x in (data.get("publishers") or []) if clean(x)]
        genres = []
        for g in data.get("genres") or []:
            name = clean((g or {}).get("description"))
            if name and name not in genres:
                genres.append(name)

        out["developers"] = developers[:4]
        out["publishers"] = publishers[:4]
        # appdetails doesn't expose the full community tag list. Localized genres are
        # still useful searchable descriptors and are deliberately labelled "类型" in UI.
        out["tags"] = genres[:6]

        notable, notable_name = is_notable_publisher(publishers)
    else:
        notable, notable_name = False, ""

    review_data = {}
    # Upcoming games frequently have no meaningful review sample yet. Steam Popular
    # Upcoming itself is already a useful popularity signal, so avoid extra calls there.
    if out.get("source") != "steam_popular_upcoming":
        try:
            review_data = steam_reviews(appid)
        except Exception:
            review_data = {}

    out.update(review_data)
    out.update(pc_heat_fields(
        out,
        int(review_data.get("review_count") or 0),
        notable,
        notable_name,
    ))
    return out

def ios_rating(appid: str) -> dict:
    try:
        payload = get_json(
            "https://itunes.apple.com/lookup",
            {"id": appid, "country": "jp", "entity": "software"},
        )
    except Exception:
        return {}
    rows = payload.get("results") or []
    if not rows:
        return {}
    r = rows[0]
    return {
        "rating": r.get("averageUserRating"),
        "rating_count": int(r.get("userRatingCount") or 0),
    }

def mobile_heat(row: dict) -> dict:
    out = dict(row)
    labels = []
    level = "none"
    score = 0.0
    source = out.get("source")

    if source == "taptap_cn_new":
        rank = int(out.get("popularity_rank") or 999)
        rating = float(out.get("rating") or 0)
        if rank <= 3:
            labels.append(f"高热 TOP{rank}")
            level = "high"
            score += 95 - rank
        elif rank <= 8:
            labels.append(f"新品榜 #{rank}")
            level = "medium"
            score += 72 - rank
        if rating >= 8.5:
            labels.append(f"高口碑 {rating:.1f}")
            if level == "none":
                level = "medium"
            score += 12

    elif source == "taptap_cn_upcoming":
        rating = float(out.get("rating") or 0)
        if rating >= 8.5:
            labels.append(f"高口碑待发 {rating:.1f}")
            level = "medium"
            score += 68

    elif source == "appstore":
        appid = apple_id_from_url(out.get("url", ""))
        if appid:
            info = ios_rating(appid)
            out.update(info)
            count = int(info.get("rating_count") or 0)
            rating = float(info.get("rating") or 0)
            if count >= 10_000:
                labels.append("高讨论")
                level = "high"
                score += 88
            elif count >= 2_000:
                labels.append("热门")
                level = "medium"
                score += 70
            elif count >= 500:
                labels.append("有讨论度")
                level = "medium"
                score += 52
            if rating >= 4.7 and count >= 500:
                labels.append(f"高口碑 {rating:.1f}★")
                score += 10

    out["heat_label"] = labels[0] if labels else ""
    out["heat_labels"] = labels
    out["heat_level"] = level
    out["heat_score"] = round(score, 2)
    return out

def main():
    payload = json.loads(GAME_FEED.read_text("utf-8"))
    items = payload.setdefault("items", {})
    pc_rows = items.get("pc") or []
    mobile_rows = items.get("mobile") or []

    enriched_pc = []
    if pc_rows:
        with ThreadPoolExecutor(max_workers=min(6, len(pc_rows))) as pool:
            futures = {pool.submit(enrich_pc, row): i for i, row in enumerate(pc_rows)}
            temp = {}
            for fut in as_completed(futures):
                i = futures[fut]
                try:
                    temp[i] = fut.result()
                except Exception as e:
                    fallback = dict(pc_rows[i])
                    fallback["metadata_error"] = f"{type(e).__name__}: {e}"
                    temp[i] = fallback
            enriched_pc = [temp[i] for i in range(len(pc_rows))]
    items["pc"] = enriched_pc

    enriched_mobile = []
    # Mobile list is intentionally small, so App Store lookup cost stays tiny.
    with ThreadPoolExecutor(max_workers=min(5, max(1, len(mobile_rows)))) as pool:
        futures = {pool.submit(mobile_heat, row): i for i, row in enumerate(mobile_rows)}
        temp = {}
        for fut in as_completed(futures):
            i = futures[fut]
            try:
                temp[i] = fut.result()
            except Exception:
                temp[i] = mobile_rows[i]
        enriched_mobile = [temp[i] for i in range(len(mobile_rows))]
    items["mobile"] = enriched_mobile

    payload["metadata_enriched_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    GAME_FEED.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", "utf-8")

    pc_meta = sum(1 for x in enriched_pc if x.get("publishers") or x.get("developers"))
    pc_hot = sum(1 for x in enriched_pc if x.get("heat_label"))
    mobile_hot = sum(1 for x in enriched_mobile if x.get("heat_label"))
    print(f"GAME ENRICH pc metadata={pc_meta}/{len(enriched_pc)} hot={pc_hot}; mobile hot={mobile_hot}/{len(enriched_mobile)}")

if __name__ == "__main__":
    main()
