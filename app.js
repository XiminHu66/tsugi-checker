const state={
  feed:null,library:null,site:null,news:null,
  filter:'all',siteFilter:'all',siteSource:'all',newsFilter:'all',query:'',
  read:new Set(JSON.parse(localStorage.getItem('tsugi-read')||'[]'))
};
const $=s=>document.querySelector(s);
const $$=s=>[...document.querySelectorAll(s)];
const esc=s=>String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
const fmt=d=>{if(!d)return '—';const x=new Date(d);if(Number.isNaN(+x))return d;return new Intl.DateTimeFormat('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}).format(x)};
const dayKey=d=>{const x=new Date(d);return Number.isNaN(+x)?'':`${x.getFullYear()}-${String(x.getMonth()+1).padStart(2,'0')}-${String(x.getDate()).padStart(2,'0')}`};
const dayLabel=d=>{const x=new Date(d);if(Number.isNaN(+x))return '较早更新';const now=new Date();const today=dayKey(now);const y=new Date(now);y.setDate(now.getDate()-1);if(dayKey(x)===today)return '今天';if(dayKey(x)===dayKey(y))return '昨天';return new Intl.DateTimeFormat('zh-CN',{month:'long',day:'numeric',weekday:'short'}).format(x)};
const relativeTime=d=>{if(!d)return '';const x=new Date(d);if(Number.isNaN(+x))return '';const sec=Math.max(0,(Date.now()-x)/1000);if(sec<3600)return `${Math.max(1,Math.floor(sec/60))} 分钟前`;if(sec<86400)return `${Math.floor(sec/3600)} 小时前`;if(sec<86400*7)return `${Math.floor(sec/86400)} 天前`;return new Intl.DateTimeFormat('zh-CN',{month:'numeric',day:'numeric'}).format(x)};
async function loadJSON(url,fallback){try{const r=await fetch(`${url}?v=${Date.now()}`,{cache:'no-store'});if(!r.ok)throw 0;return await r.json()}catch{return fallback}}
async function load(){
  $('#syncText').textContent='正在同步…';$('#syncDot').classList.remove('ok');
  const [feed,library,site,news]=await Promise.all([
    loadJSON('data/feed.json',{generated_at:null,updates:[],sources:{},items:{}}),
    loadJSON('config/library.json',{items:[]}),
    loadJSON('data/site-updates.json',{generated_at:null,items:[],sources:{}}),
    loadJSON('data/acg-news.json',{generated_at:null,items:[],sources:{}})
  ]);
  state.feed=feed;state.library=library;state.site=site;state.news=news;renderAll();
  $('#syncDot').classList.add('ok');$('#syncText').textContent=(feed.generated_at||site.generated_at||news.generated_at)?'数据已加载':'尚未同步';
}
function saveRead(){localStorage.setItem('tsugi-read',JSON.stringify([...state.read]))}
function isRead(id){return state.read.has(id)}
function imageHTML({cover,type,className='cover',placeholderClass='cover cover-placeholder',placeholderText=null}){
  const text=placeholderText||((type==='manga')?'漫':'文');
  return cover
    ? `<img class="${className}" src="${esc(cover)}" loading="lazy" referrerpolicy="no-referrer" onerror="this.outerHTML='<div class=&quot;${placeholderClass}&quot;>${esc(text)}</div>'">`
    : `<div class="${placeholderClass}">${esc(text)}</div>`;
}
function filteredUpdates(){
  const list=[...(state.feed?.updates||[])].sort((a,b)=>new Date(b.detected_at||0)-new Date(a.detected_at||0));
  const q=state.query.toLowerCase();
  return list.filter(u=>{
    const okType=state.filter==='all'||state.filter===u.type||(state.filter==='unread'&&!isRead(u.id));
    const text=`${u.title} ${u.chapter_title} ${u.source} ${u.source_label||''}`.toLowerCase();
    return okType&&(!q||text.includes(q));
  });
}
function renderSpotlight(){
  const updates=[...(state.feed?.updates||[])].sort((a,b)=>new Date(b.detected_at||0)-new Date(a.detected_at||0));
  const unique=[];const seen=new Set();
  for(const item of updates){const k=item.work_id||item.id||item.url||item.title;if(seen.has(k))continue;seen.add(k);unique.push(item);if(unique.length>=6)break}
  const library=(state.library?.items||[]).filter(x=>x.enabled!==false);
  const status=state.feed?.items||{};
  const fallback=library.slice(0,6).map(x=>({title:status[x.id]?.title||x.title,type:x.type,url:status[x.id]?.latest_url||x.url,cover:status[x.id]?.cover||x.cover,chapter_title:status[x.id]?.latest_chapter||'等待首次同步'}));
  const items=unique.length?unique:fallback;
  $('#spotlightRail').innerHTML=items.length?items.map(item=>`<article class="spotlight-card">
    ${imageHTML({cover:item.cover,type:item.type,className:'spotlight-cover',placeholderClass:'spotlight-placeholder'})}
    <div class="spotlight-meta"><div class="spotlight-top"><span class="type-pill ${item.type==='manga'?'manga':'novel'}">${item.type==='manga'?'漫画':'小说'}</span><a class="floating-link" href="${esc(item.chapter_url||item.url||'#')}" target="_blank" rel="noopener">打开 ↗</a></div><h3>${esc(item.title||'未命名作品')}</h3><p>${esc(item.chapter_title||'等待同步更新')}</p></div>
  </article>`).join(''):`<div class="empty"><div>暂无个人追更作品。<small>先在 <code>config/library.json</code> 加入作品。</small></div></div>`;
}
function renderUpdates(){
  const filtered=filteredUpdates();
  if(!filtered.length){$('#updatesList').innerHTML=`<div class="empty"><div>当前筛选下没有个人追更更新。<small>第一次抓取只建立基线；之后检测到新章节时才会出现在这里。</small></div></div>`;return}
  const groups=new Map();filtered.forEach(u=>{const k=dayKey(u.detected_at)||'older';if(!groups.has(k))groups.set(k,[]);groups.get(k).push(u)});
  $('#updatesList').innerHTML=[...groups.entries()].map(([,items])=>`<section class="date-group"><div class="date-separator">${dayLabel(items[0]?.detected_at)}</div>${items.map(u=>`<article class="update-item ${isRead(u.id)?'':'unread'}" data-id="${esc(u.id)}">
    ${imageHTML({cover:u.cover,type:u.type,className:'update-cover',placeholderClass:'update-cover cover-placeholder'})}
    <div class="update-meta"><div class="row-title"><span class="type-pill ${u.type==='manga'?'manga':'novel'}">${u.type==='manga'?'漫画':'小说'}</span><h3>${esc(u.title)}</h3></div><p class="chapter">${esc(u.chapter_title||'检测到更新')}</p><div class="subline"><span>${esc(u.source_label||u.source)}</span><span>${u.chapter_count?`共 ${u.chapter_count} 章/话`:''}</span></div></div>
    <div class="update-actions"><time>${fmt(u.detected_at)}</time><a class="open-link" target="_blank" rel="noopener" href="${esc(u.chapter_url||u.url)}">打开原站 ↗</a></div>
  </article>`).join('')}</section>`).join('');
  $$('.update-item').forEach(el=>el.addEventListener('click',e=>{if(e.target.closest('a'))return;state.read.add(el.dataset.id);saveRead();renderUpdates();updateStats()}));
}
function renderSiteUpdates(){
  const all=state.site?.items||[];
  const q=state.query.toLowerCase();
  const sources=[...new Map(all.map(x=>[x.source,x.source_label||x.source])).entries()];
  const statuses=state.site?.sources||{};
  $('#siteSourceBar').innerHTML=`<button class="source-filter ${state.siteSource==='all'?'active':''}" data-site-source="all">全部来源</button>`+sources.map(([id,label])=>`<button class="source-filter ${state.siteSource===id?'active':''}" data-site-source="${esc(id)}">${esc(label)}</button>`).join('')+Object.entries(statuses).filter(([id])=>!sources.some(([sid])=>sid===id)).map(([id,s])=>`<button class="source-filter ${state.siteSource===id?'active':''}" data-site-source="${esc(id)}">${esc(s.label||id)}${s.ok===false?' · 失败':''}</button>`).join('');
  $$('.source-filter').forEach(b=>b.onclick=()=>{state.siteSource=b.dataset.siteSource;renderSiteUpdates()});
  const visible=all.filter(x=>(state.siteFilter==='all'||x.type===state.siteFilter)&&(state.siteSource==='all'||x.source===state.siteSource)&&(!q||`${x.title} ${x.latest} ${x.source_label}`.toLowerCase().includes(q)));
  $('#siteUpdatesGrid').innerHTML=visible.length?visible.map(x=>`<a class="site-update-card" href="${esc(x.url)}" target="_blank" rel="noopener">
    ${imageHTML({cover:x.cover,type:x.type,className:'site-update-cover',placeholderClass:'site-update-placeholder'})}
    <div class="site-update-copy"><div class="site-meta"><span class="type-pill ${x.type==='manga'?'manga':'novel'}">${x.type==='manga'?'漫画':'小说'}</span><span class="site-source">${esc(x.source_label||x.source)}</span></div><h3>${esc(x.title)}</h3><p class="site-latest">${esc(x.latest||'最新更新')}</p><div class="site-meta"><span>${esc(x.updated_text||'')}</span></div></div>
  </a>`).join(''):`<div class="empty"><div>这个筛选下暂无站点更新。<small>来源抓取失败时可以到“来源状态”查看原因。</small></div></div>`;
}
function renderLibrary(){
  const items=(state.library?.items||[]).filter(x=>x.enabled!==false);const q=state.query.toLowerCase();const visible=items.filter(x=>!q||`${x.title} ${x.source}`.toLowerCase().includes(q));const status=state.feed?.items||{};
  $('#libraryGrid').innerHTML=visible.length?visible.map(x=>{const s=status[x.id]||{};const ok=s.ok!==false;return `<article class="book-card">${imageHTML({cover:s.cover||x.cover,type:x.type,className:'book-cover',placeholderClass:'book-placeholder'})}<div class="book-card-body"><div class="badge-row"><span class="badge">${x.type==='manga'?'漫画':'小说'}</span><span class="badge ${ok?'status-ok':'status-err'}">${ok?'追更中':'抓取失败'}</span></div><h3>${esc(s.title||x.title||x.id)}</h3><p class="book-latest">${esc(s.latest_chapter||'等待首次同步')}</p><p class="book-meta">${esc(x.source)} · ${fmt(s.checked_at)}</p></div></article>`}).join(''):`<div class="empty"><div>书架还是空的。<small>先在 <code>config/library.json</code> 添加要追踪的作品。</small></div></div>`;
}
function renderNews(){
  const all=state.news?.items||[];const q=state.query.toLowerCase();
  const visible=all.filter(x=>(state.newsFilter==='all'||x.source===state.newsFilter)&&(!q||`${x.title} ${x.summary} ${x.source_label} ${x.category}`.toLowerCase().includes(q)));
  const hero=visible[0];
  $('#newsHero').innerHTML=hero?`<a class="news-feature" href="${esc(hero.url)}" target="_blank" rel="noopener">${hero.image?`<img class="news-feature-image" src="${esc(hero.image)}" referrerpolicy="no-referrer" onerror="this.remove()">`:'<div class="news-feature-placeholder"></div>'}<div class="news-feature-copy"><div class="news-meta-row"><span class="news-badge">${esc(hero.source_label)}</span><span class="news-badge">${esc(hero.category)}</span><span class="news-time">${relativeTime(hero.published_at)}</span></div><h3>${esc(hero.title)}</h3><p>${esc(hero.summary||'')}</p><span class="news-feature-link">阅读原文 ↗</span></div></a>`:'';
  const rest=visible.slice(hero?1:0);
  $('#newsGrid').innerHTML=rest.length?rest.map(x=>`<a class="news-card" href="${esc(x.url)}" target="_blank" rel="noopener">${imageHTML({cover:x.image,type:'news',className:'news-thumb',placeholderClass:'news-thumb-placeholder',placeholderText:'NEWS'})}<div class="news-card-copy"><div class="news-card-meta"><span>${esc(x.source_label)}</span><span>·</span><span>${relativeTime(x.published_at)}</span></div><h3>${esc(x.title)}</h3><p>${esc(x.summary||'')}</p></div></a>`).join(''):(hero?'':`<div class="empty"><div>暂无 ACG 新闻。<small>运行一次 GitHub Action 后会读取 RSS 并生成缓存。</small></div></div>`);
}
function renderSources(){
  const personal=Object.entries(state.feed?.sources||{}).map(([id,s])=>({group:'我的追更',id,label:s.label||id,ok:(s.failed||0)===0,count:s.ok||0,total:s.total||0,error:s.failed?`${s.failed} 个失败`:''}));
  const site=Object.entries(state.site?.sources||{}).map(([id,s])=>({group:'站点最新',id,label:s.label||id,ok:s.ok!==false,count:s.count||0,total:s.count||0,error:s.error||''}));
  const news=Object.entries(state.news?.sources||{}).map(([id,s])=>({group:'ACG 新闻',id,label:s.label||id,ok:s.ok!==false,count:s.count||0,total:s.count||0,error:s.error||''}));
  const entries=[...personal,...site,...news];
  $('#sourceStatus').innerHTML=entries.length?entries.map(s=>`<article class="source-card"><div class="source-top"><div><span class="section-kicker">${esc(s.group)}</span><h3>${esc(s.label)}</h3></div><i class="status-dot ${s.ok?'':'err'}"></i></div><strong>${s.count}<span style="color:var(--faint);font-size:.48em;font-weight:600"> ${s.group==='我的追更'?`/ ${s.total}`:'items'}</span></strong><p>${s.ok?'抓取正常':esc(s.error||'抓取失败')}</p></article>`).join(''):`<div class="empty"><div>暂无来源状态。<small>首次同步完成后会显示个人追更、站点最新和新闻源健康度。</small></div></div>`;
}
function updateStats(){
  const items=(state.library?.items||[]).filter(x=>x.enabled!==false);const updates=state.feed?.updates||[];const today=dayKey(new Date());
  $('#libraryCount').textContent=items.length;$('#updateCount').textContent=updates.filter(x=>!isRead(x.id)).length;$('#newsCount').textContent=(state.news?.items||[]).length;
  $('#novelCount').textContent=items.filter(x=>x.type==='novel').length;$('#mangaCount').textContent=items.filter(x=>x.type==='manga').length;$('#todayUpdates').textContent=updates.filter(x=>dayKey(x.detected_at)===today).length;
  $('#lastSync').textContent=fmt(state.feed?.generated_at||state.site?.generated_at||state.news?.generated_at);
}
function renderAll(){renderSpotlight();renderUpdates();renderSiteUpdates();renderLibrary();renderNews();renderSources();updateStats()}
function applyTheme(theme){document.documentElement.dataset.theme=theme;localStorage.setItem('tsugi-theme',theme);const meta=document.querySelector('meta[name="theme-color"]');if(meta)meta.content=theme==='light'?'#f4f6fb':'#090b10'}
const titles={
  updates:['更新流','在“我的追更”和“站点最新”之间切换。'],
  library:['我的书架','封面优先的大书架视图，适合快速扫一眼追更状态。'],
  news:['ACG 新闻','聚合中文 ACG、日本游戏与动画漫画新闻。'],
  sources:['来源状态','检查个人追更、站点最新与新闻 RSS 最近一次抓取是否正常。'],
  settings:['设置说明','作品列表、公开内容源、同步频率与本地主题设置。']
};
$$('.nav-item').forEach(b=>b.onclick=()=>{$$('.nav-item').forEach(x=>x.classList.remove('active'));b.classList.add('active');$$('.tab').forEach(x=>x.classList.remove('active'));$('#'+b.dataset.tab).classList.add('active');$('#pageTitle').textContent=titles[b.dataset.tab][0];$('#pageSubtitle').textContent=titles[b.dataset.tab][1]});
$$('.flow-option').forEach(b=>b.onclick=()=>{$$('.flow-option').forEach(x=>x.classList.remove('active'));b.classList.add('active');$('.flow-pane.active')?.classList.remove('active');$('#'+(b.dataset.flow==='site'?'siteFlow':'personalFlow')).classList.add('active');$('#flowHint').innerHTML=b.dataset.flow==='site'?'显示各站公开最新更新，用来发现今天有什么新内容。':'只显示你加入 <code>library.json</code> 的作品更新。'});
$$('.chip[data-filter]').forEach(b=>b.onclick=()=>{$$('.chip[data-filter]').forEach(x=>x.classList.remove('active'));b.classList.add('active');state.filter=b.dataset.filter;renderUpdates()});
$$('.chip[data-site-filter]').forEach(b=>b.onclick=()=>{$$('.chip[data-site-filter]').forEach(x=>x.classList.remove('active'));b.classList.add('active');state.siteFilter=b.dataset.siteFilter;renderSiteUpdates()});
$$('.chip[data-news-filter]').forEach(b=>b.onclick=()=>{$$('.chip[data-news-filter]').forEach(x=>x.classList.remove('active'));b.classList.add('active');state.newsFilter=b.dataset.newsFilter;renderNews()});
$('#search').addEventListener('input',e=>{state.query=e.target.value.trim();renderUpdates();renderSiteUpdates();renderLibrary();renderNews()});
$('#refreshBtn').onclick=load;
$('#themeBtn').onclick=()=>applyTheme(document.documentElement.dataset.theme==='light'?'dark':'light');
$('#markAllRead').onclick=()=>{(state.feed?.updates||[]).forEach(x=>state.read.add(x.id));saveRead();renderUpdates();updateStats()};
applyTheme(document.documentElement.dataset.theme||'dark');
load();
