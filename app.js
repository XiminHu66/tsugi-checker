const state={feed:null,library:null,filter:'all',query:'',read:new Set(JSON.parse(localStorage.getItem('tsugi-read')||'[]'))};
const $=s=>document.querySelector(s);
const $$=s=>[...document.querySelectorAll(s)];
const esc=s=>String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
const fmt=d=>{if(!d)return '—';const x=new Date(d);if(Number.isNaN(+x))return d;return new Intl.DateTimeFormat('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}).format(x)};
const dayKey=d=>{const x=new Date(d);return Number.isNaN(+x)?'':`${x.getFullYear()}-${String(x.getMonth()+1).padStart(2,'0')}-${String(x.getDate()).padStart(2,'0')}`};
const dayLabel=d=>{const x=new Date(d);if(Number.isNaN(+x))return '较早更新';const now=new Date();const today=dayKey(now);const y=new Date(now);y.setDate(now.getDate()-1);if(dayKey(x)===today)return '今天';if(dayKey(x)===dayKey(y))return '昨天';return new Intl.DateTimeFormat('zh-CN',{month:'long',day:'numeric',weekday:'short'}).format(x)};
async function loadJSON(url,fallback){try{const r=await fetch(`${url}?v=${Date.now()}`,{cache:'no-store'});if(!r.ok)throw 0;return await r.json()}catch{return fallback}}
async function load(){
  $('#syncText').textContent='正在同步…';
  $('#syncDot').classList.remove('ok');
  const [feed,library]=await Promise.all([
    loadJSON('data/feed.json',{generated_at:null,updates:[],sources:{},items:{}}),
    loadJSON('config/library.json',{items:[]})
  ]);
  state.feed=feed;state.library=library;renderAll();
  $('#syncDot').classList.add('ok');
  $('#syncText').textContent=feed.generated_at?'数据已加载':'尚未同步';
}
function saveRead(){localStorage.setItem('tsugi-read',JSON.stringify([...state.read]))}
function isRead(id){return state.read.has(id)}
function imageHTML({cover,type,className='cover',placeholderClass='cover cover-placeholder'}){
  return cover
    ? `<img class="${className}" src="${esc(cover)}" loading="lazy" referrerpolicy="no-referrer" onerror="this.outerHTML='<div class=&quot;${placeholderClass}&quot;>${type==='manga'?'漫':'文'}</div>'">`
    : `<div class="${placeholderClass}">${type==='manga'?'漫':'文'}</div>`;
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
  const unique=[]; const seen=new Set();
  for(const item of updates){
    const k=item.work_id||item.id||item.url||item.title;
    if(seen.has(k)) continue;
    seen.add(k); unique.push(item);
    if(unique.length>=6) break;
  }
  const libraryItems=(state.library?.items||[]).filter(x=>x.enabled!==false);
  const fallback=libraryItems.slice(0,6).map(x=>({title:x.title,type:x.type,url:x.url,cover:x.cover,chapter_title:'等待首次同步',source:x.source,source_label:x.source}));
  const items=(unique.length?unique:fallback);
  $('#spotlightRail').innerHTML=items.length?items.map(item=>`<article class="spotlight-card">
    ${imageHTML({cover:item.cover,type:item.type,className:'spotlight-cover',placeholderClass:'spotlight-placeholder'})}
    <div class="spotlight-meta">
      <div class="spotlight-top">
        <span class="type-pill ${item.type==='manga'?'manga':'novel'}">${item.type==='manga'?'漫画':'小说'}</span>
        <a class="floating-link" href="${esc(item.chapter_url||item.url||'#')}" target="_blank" rel="noopener">打开 ↗</a>
      </div>
      <h3>${esc(item.title||'未命名作品')}</h3>
      <p>${esc(item.chapter_title||'等待同步更新')}</p>
    </div>
  </article>`).join(''):`<div class="empty"><div>暂无可展示作品。<small>先在 <code>config/library.json</code> 添加书目，或等待首次同步。</small></div></div>`;
}
function renderUpdates(){
  const filtered=filteredUpdates();
  if(!filtered.length){
    $('#updatesList').innerHTML=`<div class="empty"><div>当前筛选下没有更新。<small>首次运行 GitHub Actions 后，新章节会按照日期出现在这里。</small></div></div>`;
    return;
  }
  const groups=new Map();
  filtered.forEach(u=>{const k=dayKey(u.detected_at)||'older';if(!groups.has(k))groups.set(k,[]);groups.get(k).push(u)});
  $('#updatesList').innerHTML=[...groups.entries()].map(([,items])=>`<section class="date-group">
    <div class="date-separator">${dayLabel(items[0]?.detected_at)}</div>
    ${items.map(u=>`<article class="update-item ${u.type==='manga'?'manga':'novel'} ${isRead(u.id)?'':'unread'}" data-id="${esc(u.id)}">
      ${imageHTML({cover:u.cover,type:u.type,className:'update-cover',placeholderClass:'update-cover cover-placeholder'})}
      <div class="update-meta">
        <div class="row-title"><span class="type-pill ${u.type==='manga'?'manga':'novel'}">${u.type==='manga'?'漫画':'小说'}</span><h3>${esc(u.title)}</h3></div>
        <p class="chapter">${esc(u.chapter_title||'检测到更新')}</p>
        <div class="subline"><span>${esc(u.source_label||u.source)}</span><span>${u.chapter_count?`共 ${u.chapter_count} 章/话`:''}</span></div>
      </div>
      <div class="update-actions"><time>${fmt(u.detected_at)}</time><a class="open-link" target="_blank" rel="noopener" href="${esc(u.chapter_url||u.url)}">打开原站 ↗</a></div>
    </article>`).join('')}
  </section>`).join('');
  $$('.update-item').forEach(el=>el.addEventListener('click',e=>{if(e.target.closest('a'))return;state.read.add(el.dataset.id);saveRead();renderUpdates();updateStats()}));
}
function renderLibrary(){
  const items=(state.library?.items||[]).filter(x=>x.enabled!==false);
  const q=state.query.toLowerCase();
  const visible=items.filter(x=>!q||`${x.title} ${x.source}`.toLowerCase().includes(q));
  const status=state.feed?.items||{};
  $('#libraryGrid').innerHTML=visible.length?visible.map(x=>{
    const s=status[x.id]||{};
    const title=s.title||x.title||x.id;
    const latest=s.latest_chapter||'等待首次同步';
    const checked=fmt(s.checked_at);
    const ok=s.ok!==false;
    const cover=s.cover||x.cover;
    return `<article class="book-card">
      ${imageHTML({cover,type:x.type,className:'book-cover',placeholderClass:'book-placeholder'})}
      <div class="book-card-body">
        <div class="badge-row">
          <span class="badge">${x.type==='manga'?'漫画':'小说'}</span>
          <span class="badge ${ok?'status-ok':'status-err'}">${ok?'追更中':'抓取失败'}</span>
        </div>
        <h3>${esc(title)}</h3>
        <p class="book-latest">${esc(latest)}</p>
        <p class="book-meta">${esc(x.source)} · ${checked}</p>
      </div>
    </article>`;
  }).join(''):`<div class="empty"><div>书架还是空的。<small>先在 <code>config/library.json</code> 添加要追踪的作品。</small></div></div>`;
}
function renderSources(){
  const src=state.feed?.sources||{};
  const entries=Object.entries(src);
  $('#sourceStatus').innerHTML=entries.length?entries.map(([name,s])=>`<article class="source-card"><div class="source-top"><h3>${esc(s.label||name)}</h3><i class="status-dot ${s.failed?'err':''}"></i></div><strong>${s.ok||0}<span style="color:#637082;font-size:.55em;font-weight:600"> / ${s.total||0}</span></strong><p>成功抓取 · ${s.failed||0} 个失败</p></article>`).join(''):`<div class="empty"><div>暂无来源状态。<small>首次同步完成后会在这里显示各来源健康度。</small></div></div>`;
}
function updateStats(){
  const items=(state.library?.items||[]).filter(x=>x.enabled!==false);
  const updates=state.feed?.updates||[];
  const today=dayKey(new Date());
  $('#libraryCount').textContent=items.length;
  $('#updateCount').textContent=updates.filter(x=>!isRead(x.id)).length;
  $('#novelCount').textContent=items.filter(x=>x.type==='novel').length;
  $('#mangaCount').textContent=items.filter(x=>x.type==='manga').length;
  $('#todayUpdates').textContent=updates.filter(x=>dayKey(x.detected_at)===today).length;
  $('#lastSync').textContent=fmt(state.feed?.generated_at);
}
function renderAll(){renderSpotlight();renderUpdates();renderLibrary();renderSources();updateStats()}
const titles={
  updates:['更新流','集中查看今天新增的小说章节与漫画话数。'],
  library:['我的书架','封面优先的大书架视图，适合快速扫一眼追更状态。'],
  sources:['来源状态','检查每个漫画 / 小说来源最近一次抓取是否正常。'],
  settings:['设置说明','作品列表、同步频率与本地已读状态的配置方式。']
};
$$('.nav-item').forEach(b=>b.onclick=()=>{
  $$('.nav-item').forEach(x=>x.classList.remove('active'));
  $$(`.nav-item[data-tab="${b.dataset.tab}"]`).forEach(x=>x.classList.add('active'));
  $$('.tab').forEach(x=>x.classList.remove('active'));
  $('#'+b.dataset.tab).classList.add('active');
  $('#pageTitle').textContent=titles[b.dataset.tab][0];
  $('#pageSubtitle').textContent=titles[b.dataset.tab][1];
});
$$('.chip').forEach(b=>b.onclick=()=>{$$('.chip').forEach(x=>x.classList.remove('active'));b.classList.add('active');state.filter=b.dataset.filter;renderUpdates()});
$('#search').addEventListener('input',e=>{state.query=e.target.value.trim();renderUpdates();renderLibrary()});
$('#refreshBtn').onclick=load;
$('#markAllRead').onclick=()=>{(state.feed?.updates||[]).forEach(x=>state.read.add(x.id));saveRead();renderUpdates();updateStats()};
load();
