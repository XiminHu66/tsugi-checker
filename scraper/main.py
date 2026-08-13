from __future__ import annotations
import json, os, sys, time, hashlib, re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, urljoin
import requests
from bs4 import BeautifulSoup
from sources import parse, SOURCE_LABELS
from aggregators import parse_site_latest, fetch_news_feed
from music import refresh_music
from games import refresh_games

ROOT=Path(__file__).resolve().parents[1]
CONFIG=ROOT/'config/library.json'; CONTENT=ROOT/'config/content.json'; STATE=ROOT/'data/state.json'; FEED=ROOT/'data/feed.json'; XML=ROOT/'data/feed.xml'; SITE_FEED=ROOT/'data/site-updates.json'; NEWS_FEED=ROOT/'data/acg-news.json'; MUSIC_FEED=ROOT/'data/music.json'; GAME_FEED=ROOT/'data/game-releases.json'; GAME_STATE=ROOT/'data/game-state.json'
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151 Safari/537.36 TsugiUpdateChecker/1.0"

def now(): return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00','Z')
def load(path,default):
    try:return json.loads(path.read_text('utf-8'))
    except:return default

def fetch_requests(url):
    r=requests.get(url,headers={'User-Agent':UA,'Accept-Language':'zh-CN,zh;q=0.9,en;q=0.6'},timeout=25)
    r.raise_for_status();
    if len(r.text)<500: raise RuntimeError(f"response too short ({len(r.text)} bytes)")
    return r.text

def fetch_browser(url):
    return fetch_browser_batch([url]).get(url, '')

def fetch_browser_batch(urls, wait_ms=900):
    """Fetch several pages in one Chromium session to avoid repeated browser startups."""
    from playwright.sync_api import sync_playwright
    out={}
    urls=[u for u in urls if u]
    if not urls: return out
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True)
        context=browser.new_context(user_agent=UA,locale='zh-CN',viewport={'width':1280,'height':900})
        page=context.new_page()
        for url in urls:
            try:
                page.goto(url,wait_until='domcontentloaded',timeout=45000)
                page.wait_for_timeout(wait_ms)
                out[url]=page.content()
            except Exception as e:
                out[url]=e
        context.close(); browser.close()
    return out

def fetch(url,mode='auto'):
    if mode=='browser': return fetch_browser(url)
    try:return fetch_requests(url)
    except Exception:
        if mode=='requests': raise
        return fetch_browser(url)

def xml_escape(s):
    return str(s or '').replace('&','&amp;').replace('<','&lt;').replace('>','&gt;').replace('"','&quot;')

def make_update(item,p,detected):
    raw=f"{item['id']}|{p.latest_url}|{p.latest_chapter}"
    return {'id':hashlib.sha1(raw.encode()).hexdigest()[:16],'work_id':item['id'],'type':item.get('type','novel'),'source':item.get('source','generic'),'source_label':SOURCE_LABELS.get(item.get('source','generic'),item.get('source','generic')),'title':p.title or item.get('title',item['id']),'cover':p.cover,'chapter_title':p.latest_chapter or '检测到目录变化','chapter_url':p.latest_url or item['url'],'url':item['url'],'chapter_count':p.chapter_count,'detected_at':detected}

def build_atom(feed):
    updated=feed.get('generated_at') or now(); entries=[]
    for u in feed.get('updates',[])[:100]:
        entries.append(f'''  <entry><title>{xml_escape(u.get('title'))} · {xml_escape(u.get('chapter_title'))}</title><id>urn:tsugi:{xml_escape(u.get('id'))}</id><updated>{xml_escape(u.get('detected_at'))}</updated><link href="{xml_escape(u.get('chapter_url') or u.get('url'))}"/><summary>{xml_escape(u.get('source_label') or u.get('source'))}</summary></entry>''')
    return '<?xml version="1.0" encoding="utf-8"?>\n<feed xmlns="http://www.w3.org/2005/Atom"><title>Tsugi 小说与漫画更新流</title><id>urn:tsugi:feed</id><updated>'+xml_escape(updated)+'</updated>\n'+'\n'.join(entries)+'\n</feed>\n'


def enrich_site_rows(found, src):
    """Optionally open work detail pages to resolve a concrete latest chapter/episode and direct URL."""
    if not src.get('enrich', False):
        return found
    limit=min(len(found), int(src.get('enrich_limit', len(found))))
    sid=src.get('id','generic')
    mode=src.get('detail_fetch_mode','requests')
    batch={}
    if mode == 'browser':
        batch=fetch_browser_batch([row.get('url') for row in found[:limit]], wait_ms=int(src.get('detail_wait_ms',900)))
    for row in found[:limit]:
        try:
            detail=batch.get(row['url']) if mode == 'browser' else fetch(row['url'], mode)
            if isinstance(detail, Exception): raise detail
            if not detail: raise RuntimeError('empty detail page')
            item={
                'id':row['id'], 'title':row.get('title'), 'url':row['url'],
                'source':sid, 'type':row.get('type',src.get('type','novel')),
                'chapter_order':src.get('chapter_order','first')
            }
            soup=BeautifulSoup(detail,'lxml')
            # Linovelib exposes a dedicated “最后更新·日期 章节名” link on work pages.
            if sid == 'linovelib':
                latest_anchor=None
                for a in soup.select('a[href]'):
                    text=' '.join(a.stripped_strings)
                    if re.search(r'(?:最后|最後)更新', text):
                        latest_anchor=a; break
                if latest_anchor:
                    text=' '.join(latest_anchor.stripped_strings)
                    m=re.search(r'(?:最后|最後)更新[·：:\s]*(20\d{2}[-/.]\d{1,2}[-/.]\d{1,2})?\s*(.*)', text)
                    if m:
                        if m.group(1): row['updated_text']=m.group(1)
                        if m.group(2): row['latest']=m.group(2).strip()
                    row['latest_url']=urljoin(row['url'], latest_anchor.get('href') or '')
            # CopyManga renders its chapter list client-side, but the concrete latest
            # chapter is present in the server-rendered <title> and update date text.
            if sid == 'copymanga':
                title_text=' '.join(soup.title.stripped_strings) if soup.title else ''
                m=re.search(r'-(第\s*[^-]{1,36}?(?:话|話|章|回|卷))-', title_text)
                if m: row['latest']=m.group(1).strip()
                page_text=' '.join(soup.stripped_strings)
                dm=re.search(r'(?:最后|最後)更新[：:\s]*(20\d{2}[-/.]\d{1,2}[-/.]\d{1,2})', page_text)
                if dm: row['updated_text']=dm.group(1)
            parsed=parse(detail,row['url'],item)
            if parsed.latest_chapter and (not row.get('latest') or row.get('latest')=='最新更新'):
                row['latest']=parsed.latest_chapter
            if parsed.latest_url and not row.get('latest_url'):
                row['latest_url']=parsed.latest_url
            if parsed.cover and not row.get('cover'):
                row['cover']=parsed.cover
            if parsed.chapter_count:
                row['chapter_count']=parsed.chapter_count
        except Exception as e:
            row['enrich_error']=f'{type(e).__name__}: {e}'
            print(f"SITE ENRICH WARN {sid} {row.get('title')}: {e}", file=sys.stderr)
        time.sleep(float(src.get('detail_delay',0.18)))
    return found

def refresh_site_updates(content_cfg, generated):
    items=[]; statuses={}
    for src in content_cfg.get('site_updates',[]):
        if not src.get('enabled',True): continue
        sid=src.get('id','generic'); label=src.get('label',sid)
        try:
            page_urls=src.get('page_urls') or [src['url']]
            found=[]; seen=set()
            for page_url in page_urls:
                html=fetch(page_url,src.get('fetch_mode','auto'))
                rows=parse_site_latest(html,page_url,sid,label,src.get('type','novel'),src.get('limit',24))
                for row in rows:
                    key=(row.get('source'),row.get('url'))
                    if key in seen: continue
                    seen.add(key); found.append(row)
                if len(found)>=int(src.get('limit',24)): break
            found=found[:int(src.get('limit',24))]
            if not found: raise RuntimeError('no latest items detected')
            found=enrich_site_rows(found,src)
            for row in found: row['fetched_at']=generated
            items.extend(found)
            statuses[sid]={'label':label,'ok':True,'count':len(found),'checked_at':generated}
            print(f"SITE {sid}: {len(found)} items")
        except Exception as e:
            statuses[sid]={'label':label,'ok':False,'count':0,'checked_at':generated,'error':f'{type(e).__name__}: {e}'}
            print(f"SITE ERR {sid}: {e}",file=sys.stderr)
    SITE_FEED.write_text(json.dumps({'generated_at':generated,'items':items[:400],'sources':statuses},ensure_ascii=False,indent=2)+'\n','utf-8')

def refresh_news(content_cfg, generated):
    items=[]; statuses={}
    for src in content_cfg.get('news',[]):
        if not src.get('enabled',True): continue
        sid=src.get('id','news'); label=src.get('label',sid)
        try:
            found=fetch_news_feed(src['url'],label,src.get('category','ACG'),sid,src.get('limit',24),user_agent=UA)
            items.extend(found)
            statuses[sid]={'label':label,'ok':True,'count':len(found),'checked_at':generated}
            print(f"NEWS {sid}: {len(found)} items")
        except Exception as e:
            statuses[sid]={'label':label,'ok':False,'count':0,'checked_at':generated,'error':f'{type(e).__name__}: {e}'}
            print(f"NEWS ERR {sid}: {e}",file=sys.stderr)
    items.sort(key=lambda x:x.pop('_sort',0),reverse=True)
    seen=set(); dedup=[]
    for row in items:
        key=row.get('url') or row.get('title')
        if key in seen: continue
        seen.add(key); dedup.append(row)
    NEWS_FEED.write_text(json.dumps({'generated_at':generated,'items':dedup[:72],'sources':statuses},ensure_ascii=False,indent=2)+'\n','utf-8')

def main():
    cfg=load(CONFIG,{'items':[]}); content_cfg=load(CONTENT,{'site_updates':[],'news':[]}); state=load(STATE,{'items':{}}); oldfeed=load(FEED,{'updates':[]})
    generated=now(); updates=list(oldfeed.get('updates',[])); item_out={}; sources={}
    enabled=[x for x in cfg.get('items',[]) if x.get('enabled',True)]
    if not enabled:
        print('No enabled library items. Skipping personal tracking; public feeds will still refresh.')
    for idx,item in enumerate(enabled):
        sid=item.get('source','generic'); sources.setdefault(sid,{'label':SOURCE_LABELS.get(sid,sid),'ok':0,'failed':0,'total':0}); sources[sid]['total']+=1
        prev=state.setdefault('items',{}).get(item['id'],{})
        try:
            html=fetch(item['url'],item.get('fetch_mode','auto'))
            p=parse(html,item['url'],item)
            if not p.latest_chapter and p.catalog_url and p.catalog_url!=item['url']:
                html2=fetch(p.catalog_url,item.get('fetch_mode','auto')); p2=parse(html2,p.catalog_url,item)
                p.title=p.title or p2.title; p.cover=p.cover or p2.cover; p.latest_chapter=p2.latest_chapter; p.latest_url=p2.latest_url; p.chapter_count=p2.chapter_count
            key=(p.latest_url or '')+'|'+(p.latest_chapter or '')+'|'+str(p.chapter_count)
            prevkey=prev.get('key')
            changed=bool(prevkey and key and key!=prevkey)
            if changed:
                updates.insert(0,make_update(item,p,generated))
            current={'key':key,'latest_chapter':p.latest_chapter,'latest_url':p.latest_url,'chapter_count':p.chapter_count,'title':p.title,'cover':p.cover,'checked_at':generated,'changed_at':generated if changed else prev.get('changed_at'),'ok':True}
            state['items'][item['id']]=current; item_out[item['id']]=current; sources[sid]['ok']+=1
            print(f"OK  {item['id']}: {p.latest_chapter or 'no chapter detected'}")
        except Exception as e:
            current={**prev,'checked_at':generated,'ok':False,'error':f'{type(e).__name__}: {e}'}; state['items'][item['id']]=current; item_out[item['id']]=current; sources[sid]['failed']+=1
            print(f"ERR {item['id']}: {e}",file=sys.stderr)
        time.sleep(float(item.get('delay',1.5)))
    dedup=[]; seen=set()
    for u in updates:
        if u.get('id') in seen: continue
        seen.add(u.get('id')); dedup.append(u)
    feed={'generated_at':generated,'updates':dedup[:200],'items':item_out,'sources':sources}
    STATE.write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n','utf-8'); FEED.write_text(json.dumps(feed,ensure_ascii=False,indent=2)+'\n','utf-8'); XML.write_text(build_atom(feed),'utf-8')
    refresh_site_updates(content_cfg,generated)
    refresh_news(content_cfg,generated)
    refresh_music(content_cfg,generated,MUSIC_FEED,UA)
    refresh_games(content_cfg,generated,GAME_FEED,GAME_STATE,UA)

if __name__=='__main__': main()
