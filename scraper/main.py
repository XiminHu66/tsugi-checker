from __future__ import annotations
import json, os, sys, time, hashlib
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup
from sources import parse, SOURCE_LABELS

ROOT=Path(__file__).resolve().parents[1]
CONFIG=ROOT/'config/library.json'; STATE=ROOT/'data/state.json'; FEED=ROOT/'data/feed.json'; XML=ROOT/'data/feed.xml'
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
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        page=browser.new_page(user_agent=UA,locale='zh-CN',viewport={'width':1280,'height':900})
        page.goto(url,wait_until='domcontentloaded',timeout=45000)
        page.wait_for_timeout(1800)
        html=page.content(); browser.close(); return html

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

def main():
    cfg=load(CONFIG,{'items':[]}); state=load(STATE,{'items':{}}); oldfeed=load(FEED,{'updates':[]})
    generated=now(); updates=list(oldfeed.get('updates',[])); item_out={}; sources={}
    enabled=[x for x in cfg.get('items',[]) if x.get('enabled',True)]
    if not enabled:
        print('No enabled items. Add entries to config/library.json.')
        return
    for idx,item in enumerate(enabled):
        sid=item.get('source','generic'); sources.setdefault(sid,{'label':SOURCE_LABELS.get(sid,sid),'ok':0,'failed':0,'total':0}); sources[sid]['total']+=1
        prev=state.setdefault('items',{}).get(item['id'],{})
        try:
            html=fetch(item['url'],item.get('fetch_mode','auto'))
            p=parse(html,item['url'],item)
            # Some detail pages only link to a catalog. Follow it once when no chapter is found.
            if not p.latest_chapter and p.catalog_url and p.catalog_url!=item['url']:
                html2=fetch(p.catalog_url,item.get('fetch_mode','auto')); p2=parse(html2,p.catalog_url,item)
                p.title=p.title or p2.title; p.cover=p.cover or p2.cover; p.latest_chapter=p2.latest_chapter; p.latest_url=p2.latest_url; p.chapter_count=p2.chapter_count
            key=(p.latest_url or '')+'|'+(p.latest_chapter or '')+'|'+str(p.chapter_count)
            prevkey=prev.get('key')
            # First successful scrape initializes state without flooding the feed.
            if prevkey and key and key!=prevkey:
                updates.insert(0,make_update(item,p,generated))
            current={'key':key,'latest_chapter':p.latest_chapter,'latest_url':p.latest_url,'chapter_count':p.chapter_count,'title':p.title,'cover':p.cover,'checked_at':generated,'ok':True}
            state['items'][item['id']]=current; item_out[item['id']]=current; sources[sid]['ok']+=1
            print(f"OK  {item['id']}: {p.latest_chapter or 'no chapter detected'}")
        except Exception as e:
            current={**prev,'checked_at':generated,'ok':False,'error':f'{type(e).__name__}: {e}'}; state['items'][item['id']]=current; item_out[item['id']]=current; sources[sid]['failed']+=1
            print(f"ERR {item['id']}: {e}",file=sys.stderr)
        time.sleep(float(item.get('delay',1.5)))
    # Remove duplicate update IDs while preserving order.
    dedup=[]; seen=set()
    for u in updates:
        if u.get('id') in seen: continue
        seen.add(u.get('id')); dedup.append(u)
    feed={'generated_at':generated,'updates':dedup[:200],'items':item_out,'sources':sources}
    STATE.write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n','utf-8'); FEED.write_text(json.dumps(feed,ensure_ascii=False,indent=2)+'\n','utf-8'); XML.write_text(build_atom(feed),'utf-8')

if __name__=='__main__': main()
