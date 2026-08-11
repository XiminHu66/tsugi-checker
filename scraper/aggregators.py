from __future__ import annotations
import hashlib, re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin, urlparse

import feedparser
import requests
from bs4 import BeautifulSoup

NOISE = re.compile(r"^(首页|主页|登录|注册|更多|下一页|上一页|排行榜|分类|搜索|我的书架|APP|下载)$", re.I)
UPDATE_RE = re.compile(r"((?:更新至|最新(?:章节|话|話|卷)?|最近更新|最後更新|最后更新)[：:\s]*[^\s|]{1,40}|第\s*[0-9一二三四五六七八九十百千万零〇两\.\-]+\s*[章话話回卷节節])", re.I)
DATE_RE = re.compile(r"(20\d{2}[-/.年]\d{1,2}[-/.月]\d{1,2}(?:日)?(?:\s+\d{1,2}:\d{2})?)")

WORK_PATTERNS = {
    "manhuagui": re.compile(r"/comic/\d+/?$", re.I),
    "copymanga": re.compile(r"/(?:comic|h5/details/comic)/[^/?#]+/?$", re.I),
    "linovelib": re.compile(r"/(?:novel|book)/\d+(?:\.html)?/?$", re.I),
    "wenku8": re.compile(r"/(?:book/\d+\.htm|modules/article/articleinfo\.php\?id=\d+)", re.I),
}

def clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()

def _image_from(node, base):
    if not node: return None
    img=node.select_one("img")
    if not img: return None
    src=img.get("data-src") or img.get("data-original") or img.get("data-lazy-src") or img.get("src")
    if not src or src.startswith("data:"): return None
    return urljoin(base,src)

def _container(anchor):
    candidates=[]
    for p in anchor.parents:
        if getattr(p, "name", None) in ("li","article","div","section","tr"):
            text=clean(p.get_text(" "))
            if 2 <= len(text) <= 800:
                candidates.append((p,text))
        if len(candidates)>=8:
            break
    for p,text in candidates:
        # Prefer a metadata-bearing card, but do not climb into a list wrapper that
        # contains many unrelated work links (which can leak another title's date).
        workish=sum(1 for a in p.select("a[href]") if re.search(r"/(?:comic|novel|book|h5/details/comic)/", a.get("href") or "", re.I))
        if workish <= 2 and (UPDATE_RE.search(text) or DATE_RE.search(text)):
            return p
    return candidates[0][0] if candidates else anchor.parent


def anchor_title(a, source):
    for sel in ("h1","h2","h3","h4",".title",".bookname",".book-name",".name","strong","b"):
        n=a.select_one(sel)
        t=clean(n.get_text(" ")) if n else ""
        if 2 <= len(t) <= 90 and not NOISE.match(t): return t
    img=a.select_one("img")
    if img:
        t=clean(img.get("alt") or img.get("title"))
        if 2 <= len(t) <= 90 and not NOISE.match(t): return t
    raw=clean(a.get("title") or a.get_text(" "))
    if source=="manhuagui":
        m=re.search(r"^(?:连载|完结)?\s*(.+?)\s*作\s*者[：:]",raw)
        if m:return clean(m.group(1))[:90]
    if source=="linovelib":
        raw=re.sub(r"^(?:[0-9]+(?:\.[0-9]+)?|㊙︎)\s*","",raw)
        # Card text often starts with the title and then a long synopsis. Prefer a visible short child above;
        # otherwise keep the first phrase before sentence punctuation as a conservative fallback.
        first=re.split(r"[。！？]",raw,1)[0]
        if 2 <= len(first) <= 90:return first
    return raw[:90] if 2 <= len(raw) else ""

def _source_scope(soup, source):
    # CopyManga's home page contains ranking/recommendation links before the latest block.
    # Restrict discovery to the smallest ancestor around the “热门更新 / 熱門更新” heading
    # that contains a meaningful set of comic links. Fall back to the full document if
    # the site changes its markup.
    if source == "copymanga":
        marker = soup.find(string=re.compile(r"热门更新|熱門更新", re.I))
        if marker:
            for node in [marker.parent, *list(marker.parents)[:7]]:
                if not getattr(node, "select", None):
                    continue
                links = [a for a in node.select("a[href]") if re.search(r"/(?:comic|h5/details/comic)/", a.get("href") or "", re.I)]
                if 4 <= len(links) <= 80:
                    return node
    return soup

def _candidate_anchors(soup, source):
    soup=_source_scope(soup,source)
    pattern=WORK_PATTERNS.get(source)
    candidates=[]
    for a in soup.select("a[href]"):
        title=anchor_title(a,source)
        if not title or len(title)<2 or NOISE.match(title):
            continue
        href=a.get("href") or ""
        full=urljoin("https://placeholder.invalid",href)
        path=urlparse(full).path + ("?"+urlparse(full).query if urlparse(full).query else "")
        score=0
        if pattern and pattern.search(path): score+=10
        if source=="linovelib" and re.search(r"/novel/\d+",path): score+=8
        if source=="wenku8" and ("articleinfo" in path or re.search(r"/book/\d+\.htm",path)): score+=8
        if source=="manhuagui" and "/comic/" in path: score+=7
        if source=="copymanga" and "/comic/" in path: score+=7
        parent=_container(a); context=clean(parent.get_text(" ")) if parent else ""
        if UPDATE_RE.search(context): score+=4
        if DATE_RE.search(context): score+=2
        if score>=7: candidates.append((score,a,parent,title))
    return candidates

def parse_site_latest(html, base_url, source, label, item_type, limit=24):
    soup=BeautifulSoup(html,"lxml")
    out=[]; seen=set()
    for _,a,parent,title in _candidate_anchors(soup,source):
        url=urljoin(base_url,a.get("href") or "")
        key=(title,url)
        if key in seen: continue
        seen.add(key)
        context=clean(parent.get_text(" ")) if parent else title
        update_match=UPDATE_RE.search(context)
        date_match=DATE_RE.search(context)
        latest=clean(update_match.group(1)) if update_match else "最新更新"
        out.append({
            "id": hashlib.sha1(f"{source}|{url}|{latest}".encode()).hexdigest()[:16],
            "type": item_type,
            "source": source,
            "source_label": label,
            "title": title,
            "latest": latest,
            "updated_text": clean(date_match.group(1)) if date_match else "",
            "url": url,
            "cover": _image_from(parent,base_url),
        })
        if len(out)>=int(limit): break
    return out

def _entry_time(entry):
    for key in ("published_parsed","updated_parsed"):
        value=entry.get(key)
        if value:
            try:return datetime(*value[:6],tzinfo=timezone.utc)
            except Exception:pass
    for key in ("published","updated"):
        value=entry.get(key)
        if value:
            try:
                dt=parsedate_to_datetime(value)
                if dt.tzinfo is None: dt=dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(timezone.utc)
            except Exception:pass
    return datetime(1970,1,1,tzinfo=timezone.utc)

def _feed_image(entry):
    for block in entry.get("media_content",[]) or []:
        if block.get("url"): return block["url"]
    for block in entry.get("media_thumbnail",[]) or []:
        if block.get("url"): return block["url"]
    for block in entry.get("enclosures",[]) or []:
        href=block.get("href") or block.get("url")
        if href and (str(block.get("type","")).startswith("image/") or re.search(r"\.(?:jpg|jpeg|png|webp)(?:\?|$)",href,re.I)):
            return href
    summary=entry.get("summary") or entry.get("description") or ""
    soup=BeautifulSoup(summary,"lxml")
    img=soup.select_one("img[src]")
    return img.get("src") if img else None

def _feed_summary(entry):
    raw=entry.get("summary") or entry.get("description") or ""
    text=clean(BeautifulSoup(raw,"lxml").get_text(" "))
    return text[:240]

def fetch_news_feed(url,label,category,source_id,limit=24,timeout=25,user_agent=None):
    headers={"User-Agent":user_agent or "TsugiReader/1.0","Accept-Language":"zh-CN,zh;q=0.9,en;q=0.7"}
    response=requests.get(url,headers=headers,timeout=timeout)
    response.raise_for_status()
    parsed=feedparser.parse(response.content)
    if getattr(parsed,"bozo",False) and not parsed.entries:
        raise RuntimeError(str(getattr(parsed,"bozo_exception","RSS parse failed")))
    out=[]
    for entry in parsed.entries[:int(limit)]:
        title=clean(entry.get("title")); link=entry.get("link")
        if not title or not link: continue
        dt=_entry_time(entry)
        out.append({
            "id":hashlib.sha1(f"{source_id}|{link}".encode()).hexdigest()[:16],
            "source":source_id,
            "source_label":label,
            "category":category,
            "title":title,
            "url":link,
            "summary":_feed_summary(entry),
            "image":_feed_image(entry),
            "published_at":dt.isoformat().replace("+00:00","Z") if dt.year>1970 else "",
            "_sort":dt.timestamp(),
        })
    return out
