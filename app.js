const state={
  feed:null,library:null,site:null,news:null,content:null,
  filter:'all',siteFilter:'all',siteSource:'all',newsFilter:'all',query:'',
  read:new Set(JSON.parse(localStorage.getItem('tsugi-read')||'[]'))
};
const $=s=>document.querySelector(s);
const $$=s=>[...document.querySelectorAll(s)];
const esc=s=>String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
const fmt=d=>{if(!d)return '—';const x=new Date(d);if(Number.isNaN(+x))return d;return new Intl.DateTimeFormat('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}).format(x)};
const relativeTime=d=>{if(!d)return '';const x=new Date(d);if(Number.isNaN(+x))return '';const sec=Math.max(0,(Date.now()-x)/1000);if(sec<3600)return `${Math.max(1,Math.floor(sec/60))} 分钟前`;if(sec<86400)return `${Math.floor(sec/3600)} 小时前`;if(sec<86400*7)return `${Math.floor(sec/86400)} 天前`;return new Intl.DateTimeFormat('zh-CN',{month:'numeric',day:'numeric'}).format(x)};
async function loadJSON(url,fallback){try{const r=await fetch(`${url}?v=${Date.now()}`,{cache:'no-store'});if(!r.ok)throw 0;return await r.json()}catch{return fallback}}
async function load(){
  $('#syncText').textContent='正在同步…';$('#syncDot').classList.remove('ok');
  const [feed,library,site,news,content]=await Promise.all([
    loadJSON('data/feed.json',{generated_at:null,updates:[],sources:{},items:{}}),
    loadJSON('config/library.json',{items:[]}),
    loadJSON('data/site-updates.json',{generated_at:null,items:[],sources:{}}),
    loadJSON('data/acg-news.json',{generated_at:null,items:[],sources:{}}),
    loadJSON('config/content.json',{site_updates:[],news:[]})
  ]);
  state.feed=feed;state.library=library;state.site=site;state.news=news;state.content=content;
  renderAll();
  $('#syncDot').classList.add('ok');
  $('#syncText').textContent=(feed.generated_at||site.generated_at||news.generated_at)?'数据已加载':'尚未同步';
}
function saveRead(){localStorage.setItem('tsugi-read',JSON.stringify([...state.read]))}
function isRead(id){return state.read.has(id)}
function isRecent(d,hours=72){if(!d)return false;const x=new Date(d);return !Number.isNaN(+x)&&(Date.now()-x.getTime())<hours*3600*1000}
function imageHTML({cover,type,className='cover',placeholderClass='cover cover-placeholder',placeholderText=null}){
  const text=placeholderText||((type==='manga')?'漫':'文');
  return cover
    ? `<img class="${className}" src="${esc(cover)}" loading="lazy" referrerpolicy="no-referrer" onerror="this.outerHTML='<div class=&quot;${placeholderClass}&quot;>${esc(text)}</div>'">`
    : `<div class="${placeholderClass}">${esc(text)}</div>`;
}
function enabledSourceIds(kind){return new Set((state.content?.[kind]||[]).filter(x=>x.enabled!==false).map(x=>x.id))}
function sourceLabel(id,kind){const row=(state.content?.[kind]||[]).find(x=>x.id===id);return row?.label||id}

function renderSiteUpdates(){
  const allowed=enabledSourceIds('site_updates');
  const all=(state.site?.items||[]).filter(x=>!allowed.size||allowed.has(x.source));
  const q=state.query.toLowerCase();
  const configured=(state.content?.site_updates||[]).filter(x=>x.enabled!==false);
  const sources=configured.length?configured.map(x=>[x.id,x.label]):[...new Map(all.map(x=>[x.source,x.source_label||x.source])).entries()];
  const statuses=state.site?.sources||{};
  $('#siteSourceBar').innerHTML=`<button class="source-filter ${state.siteSource==='all'?'active':''}" data-site-source="all">全部来源</button>`+
    sources.map(([id,label])=>`<button class="source-filter ${state.siteSource===id?'active':''}" data-site-source="${esc(id)}">${esc(label)}${statuses[id]?.ok===false?' · 失败':''}</button>`).join('');
  $$('.source-filter').forEach(b=>b.onclick=()=>{state.siteSource=b.dataset.siteSource;renderSiteUpdates()});
  const visible=all.filter(x=>(state.siteFilter==='all'||x.type===state.siteFilter)&&(state.siteSource==='all'||x.source===state.siteSource)&&(!q||`${x.title} ${x.latest} ${x.source_label}`.toLowerCase().includes(q)));
  $('#siteUpdatesGrid').innerHTML=visible.length?visible.map(x=>`<a class="site-update-card" href="${esc(x.latest_url||x.url)}" target="_blank" rel="noopener">
    ${imageHTML({cover:x.cover,type:x.type,className:'site-update-cover',placeholderClass:'site-update-placeholder'})}
    <div class="site-update-copy">
      <div class="site-meta"><span class="type-pill ${x.type==='manga'?'manga':'novel'}">${x.type==='manga'?'漫画':'小说'}</span><span class="site-source">${esc(x.source_label||x.source)}</span></div>
      <h3>${esc(x.title)}</h3>
      <p class="site-latest">${esc(x.latest||'最新更新')}</p>
      <div class="site-meta"><span>${esc(x.updated_text||'')}</span><span>${x.latest_url?'直达最新章节 ↗':'打开作品页 ↗'}</span></div>
    </div>
  </a>`).join(''):`<div class="empty"><div>这个筛选下暂无站点更新。<small>来源失败时可以到“来源状态”查看原因。</small></div></div>`;
}

function filteredPersonalUpdates(){
  const list=[...(state.feed?.updates||[])].sort((a,b)=>new Date(b.detected_at||0)-new Date(a.detected_at||0));
  const q=state.query.toLowerCase();
  return list.filter(u=>{
    const okType=state.filter==='all'||state.filter===u.type||(state.filter==='unread'&&!isRead(u.id));
    const text=`${u.title} ${u.chapter_title} ${u.source} ${u.source_label||''}`.toLowerCase();
    return okType&&(!q||text.includes(q));
  });
}
function renderLibraryUpdates(){
  const list=filteredPersonalUpdates();
  if(!list.length){
    $('#libraryUpdatesList').innerHTML=`<div class="empty"><div>暂无订阅更新记录。<small>第一次抓取只建立基线；订阅作品之后出现新章节 / 新话时会记录在这里。</small></div></div>`;
    return;
  }
  $('#libraryUpdatesList').innerHTML=list.map(u=>`<article class="update-item ${isRead(u.id)?'':'unread'}" data-id="${esc(u.id)}">
    ${imageHTML({cover:u.cover,type:u.type,className:'update-cover',placeholderClass:'update-cover cover-placeholder'})}
    <div class="update-meta"><div class="row-title"><span class="type-pill ${u.type==='manga'?'manga':'novel'}">${u.type==='manga'?'漫画':'小说'}</span><h3>${esc(u.title)}</h3></div><p class="chapter">${esc(u.chapter_title||'检测到更新')}</p><div class="subline"><span>${esc(u.source_label||u.source)}</span><span>${u.chapter_count?`共 ${u.chapter_count} 章/话`:''}</span></div></div>
    <div class="update-actions"><time>${fmt(u.detected_at)}</time><a class="open-link" target="_blank" rel="noopener" href="${esc(u.chapter_url||u.url)}">打开最新章节 ↗</a></div>
  </article>`).join('');
  $$('#libraryUpdatesList .update-item').forEach(el=>el.addEventListener('click',e=>{if(e.target.closest('a'))return;state.read.add(el.dataset.id);saveRead();renderLibraryUpdates();updateStats()}));
}
function renderLibrary(){
  const items=(state.library?.items||[]).filter(x=>x.enabled!==false);
  const q=state.query.toLowerCase();
  const visible=items.filter(x=>!q||`${x.title} ${x.source}`.toLowerCase().includes(q));
  const status=state.feed?.items||{};
  $('#libraryGrid').innerHTML=visible.length?visible.map(x=>{
    const s=status[x.id]||{};const ok=s.ok!==false;const fresh=isRecent(s.changed_at);const href=s.latest_url||x.url;
    return `<a class="book-card" href="${esc(href)}" target="_blank" rel="noopener">
      ${imageHTML({cover:s.cover||x.cover,type:x.type,className:'book-cover',placeholderClass:'book-placeholder'})}
      <div class="book-card-body">
        <div class="badge-row"><span class="badge">${x.type==='manga'?'漫画':'小说'}</span><span class="badge ${ok?'status-ok':'status-err'}">${ok?'追更中':'抓取失败'}</span>${fresh?'<span class="badge library-new">NEW</span>':''}</div>
        <h3>${esc(s.title||x.title||x.id)}</h3>
        <p class="book-latest">${esc(s.latest_chapter||'等待首次同步')}</p>
        <p class="book-meta">${esc(sourceLabel(x.source,'site_updates')||x.source)} · 检查 ${fmt(s.checked_at)}</p>
        <span class="book-open">${s.latest_url?'打开最新章节':'打开作品页'} ↗</span>
      </div>
    </a>`;
  }).join(''):`<div class="empty"><div>书架还是空的。<small>在 <code>config/library.json</code> 加入作品后，这里会显示订阅作品和当前最新章节 / 话数。</small></div></div>`;
}

function renderNewsFilters(){
  const configured=(state.content?.news||[]).filter(x=>x.enabled!==false);
  const ids=new Set(configured.map(x=>x.id));
  if(state.newsFilter!=='all'&&!ids.has(state.newsFilter))state.newsFilter='all';
  $('#newsFilterChips').innerHTML=`<button class="chip ${state.newsFilter==='all'?'active':''}" data-news-filter="all">全部</button>`+
    configured.map(x=>`<button class="chip ${state.newsFilter===x.id?'active':''}" data-news-filter="${esc(x.id)}">${esc(x.label)}</button>`).join('');
  $$('.chip[data-news-filter]').forEach(b=>b.onclick=()=>{state.newsFilter=b.dataset.newsFilter;renderNews()});
}
function renderNews(){
  renderNewsFilters();
  const allowed=enabledSourceIds('news');
  const all=(state.news?.items||[]).filter(x=>!allowed.size||allowed.has(x.source));
  const q=state.query.toLowerCase();
  const visible=all.filter(x=>(state.newsFilter==='all'||x.source===state.newsFilter)&&(!q||`${x.title} ${x.summary} ${x.source_label} ${x.category}`.toLowerCase().includes(q)));
  const hero=visible[0];
  $('#newsHero').innerHTML=hero?`<a class="news-feature" href="${esc(hero.url)}" target="_blank" rel="noopener">${hero.image?`<img class="news-feature-image" src="${esc(hero.image)}" referrerpolicy="no-referrer" onerror="this.remove()">`:'<div class="news-feature-placeholder"></div>'}<div class="news-feature-copy"><div class="news-meta-row"><span class="news-badge">${esc(hero.source_label)}</span><span class="news-badge">${esc(hero.category)}</span><span class="news-time">${relativeTime(hero.published_at)}</span></div><h3>${esc(hero.title)}</h3><p>${esc(hero.summary||'')}</p><span class="news-feature-link">阅读原文 ↗</span></div></a>`:'';
  const rest=visible.slice(hero?1:0);
  $('#newsGrid').innerHTML=rest.length?rest.map(x=>`<a class="news-card" href="${esc(x.url)}" target="_blank" rel="noopener">${imageHTML({cover:x.image,type:'news',className:'news-thumb',placeholderClass:'news-thumb-placeholder',placeholderText:'NEWS'})}<div class="news-card-copy"><div class="news-card-meta"><span>${esc(x.source_label)}</span><span>·</span><span>${relativeTime(x.published_at)}</span></div><h3>${esc(x.title)}</h3><p>${esc(x.summary||'')}</p></div></a>`).join(''):(hero?'':`<div class="empty"><div>暂无中文 ACG 新闻。<small>新版来源会在下一次每日 / 手动抓取后生成。</small></div></div>`);
}
function renderSources(){
  const personal=Object.entries(state.feed?.sources||{}).map(([id,s])=>({group:'我的书架',id,label:s.label||id,ok:(s.failed||0)===0,count:s.ok||0,total:s.total||0,error:s.failed?`${s.failed} 个失败`:''}));
  const siteAllowed=enabledSourceIds('site_updates');
  const site=Object.entries(state.site?.sources||{}).filter(([id])=>!siteAllowed.size||siteAllowed.has(id)).map(([id,s])=>({group:'更新流',id,label:s.label||id,ok:s.ok!==false,count:s.count||0,total:s.count||0,error:s.error||''}));
  const newsAllowed=enabledSourceIds('news');
  const news=Object.entries(state.news?.sources||{}).filter(([id])=>!newsAllowed.size||newsAllowed.has(id)).map(([id,s])=>({group:'ACG 新闻',id,label:s.label||id,ok:s.ok!==false,count:s.count||0,total:s.count||0,error:s.error||''}));
  const entries=[...personal,...site,...news];
  $('#sourceStatus').innerHTML=entries.length?entries.map(s=>`<article class="source-card"><div class="source-top"><div><span class="section-kicker">${esc(s.group)}</span><h3>${esc(s.label)}</h3></div><i class="status-dot ${s.ok?'':'err'}"></i></div><strong>${s.count}<span style="color:var(--faint);font-size:.48em;font-weight:600"> ${s.group==='我的书架'?`/ ${s.total}`:'items'}</span></strong><p>${s.ok?'抓取正常':esc(s.error||'抓取失败')}</p></article>`).join(''):`<div class="empty"><div>暂无来源状态。<small>首次同步完成后会显示来源健康度。</small></div></div>`;
}
function updateStats(){
  const library=(state.library?.items||[]).filter(x=>x.enabled!==false);
  const site=(state.site?.items||[]).filter(x=>{const ids=enabledSourceIds('site_updates');return !ids.size||ids.has(x.source)});
  const news=(state.news?.items||[]).filter(x=>{const ids=enabledSourceIds('news');return !ids.size||ids.has(x.source)});
  $('#libraryCount').textContent=library.length;
  $('#updateCount').textContent=site.length;
  $('#newsCount').textContent=news.length;
  $('#novelCount').textContent=site.filter(x=>x.type==='novel').length;
  $('#mangaCount').textContent=site.filter(x=>x.type==='manga').length;
  $('#todayUpdates').textContent=site.length;
  $('#lastSync').textContent=fmt(state.site?.generated_at||state.feed?.generated_at||state.news?.generated_at);
}
function renderAll(){renderSiteUpdates();renderLibrary();renderLibraryUpdates();renderNews();renderSources();updateStats()}
function applyTheme(theme){document.documentElement.dataset.theme=theme;localStorage.setItem('tsugi-theme',theme);const meta=document.querySelector('meta[name="theme-color"]');if(meta)meta.content=theme==='light'?'#f4f6fb':'#090b10'}
const titles={
  updates:['更新流','汇总各小说 / 漫画来源最新更新，并解析最新章节与话数。'],
  library:['我的书架','查看你的订阅作品、当前最新章节 / 话数与订阅更新记录。'],
  news:['ACG 新闻','仅显示简体中文 / 繁体中文的 ACG 新闻。'],
  sources:['来源状态','检查更新流、我的书架和中文 ACG 新闻最近一次抓取是否正常。'],
  settings:['设置说明','订阅作品、公开更新源、中文 ACG 新闻与同步频率设置。']
};
$$('.nav-item').forEach(b=>b.onclick=()=>{$$('.nav-item').forEach(x=>x.classList.remove('active'));b.classList.add('active');$$('.tab').forEach(x=>x.classList.remove('active'));$('#'+b.dataset.tab).classList.add('active');$('#pageTitle').textContent=titles[b.dataset.tab][0];$('#pageSubtitle').textContent=titles[b.dataset.tab][1]});
$$('.chip[data-filter]').forEach(b=>b.onclick=()=>{$$('.chip[data-filter]').forEach(x=>x.classList.remove('active'));b.classList.add('active');state.filter=b.dataset.filter;renderLibraryUpdates()});
$$('.chip[data-site-filter]').forEach(b=>b.onclick=()=>{$$('.chip[data-site-filter]').forEach(x=>x.classList.remove('active'));b.classList.add('active');state.siteFilter=b.dataset.siteFilter;renderSiteUpdates()});
$('#search').addEventListener('input',e=>{state.query=e.target.value.trim();renderSiteUpdates();renderLibrary();renderLibraryUpdates();renderNews()});
$('#refreshBtn').onclick=load;
$('#themeBtn').onclick=()=>applyTheme(document.documentElement.dataset.theme==='light'?'dark':'light');
$('#markAllRead').onclick=()=>{(state.feed?.updates||[]).forEach(x=>state.read.add(x.id));saveRead();renderLibraryUpdates();updateStats()};
applyTheme(document.documentElement.dataset.theme||'dark');
load();
