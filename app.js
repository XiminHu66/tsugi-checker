const LOCAL_LIBRARY_KEY='tsugi-local-library-v1';
const LOCAL_UPDATES_KEY='tsugi-local-updates-v1';
const ARTIST_FOLLOWS_KEY='tsugi-followed-artists-v1';
const state={
  feed:null,library:null,site:null,news:null,content:null,music:null,games:null,
  filter:'all',siteFilter:'all',siteSource:'all',newsFilter:'all',query:'',musicView:'chart',gameView:'mobile',
  read:new Set(JSON.parse(localStorage.getItem('tsugi-read')||'[]')),
  localLibrary:loadLocalArray(LOCAL_LIBRARY_KEY),
  localUpdates:loadLocalArray(LOCAL_UPDATES_KEY),
  followedArtists:loadLocalArray(ARTIST_FOLLOWS_KEY)
};
const $=s=>document.querySelector(s);
const $$=s=>[...document.querySelectorAll(s)];
const esc=s=>String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
const fmt=d=>{if(!d)return '—';const x=new Date(d);if(Number.isNaN(+x))return d;return new Intl.DateTimeFormat('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}).format(x)};
const relativeTime=d=>{if(!d)return '';const x=new Date(d);if(Number.isNaN(+x))return '';const sec=Math.max(0,(Date.now()-x)/1000);if(sec<3600)return `${Math.max(1,Math.floor(sec/60))} 分钟前`;if(sec<86400)return `${Math.floor(sec/3600)} 小时前`;if(sec<86400*7)return `${Math.floor(sec/86400)} 天前`;return new Intl.DateTimeFormat('zh-CN',{month:'numeric',day:'numeric'}).format(x)};
function loadLocalArray(key){try{const x=JSON.parse(localStorage.getItem(key)||'[]');return Array.isArray(x)?x:[]}catch{return []}}
function saveLocalArray(key,value){localStorage.setItem(key,JSON.stringify(value))}
async function loadJSON(url,fallback){try{const r=await fetch(`${url}?v=${Date.now()}`,{cache:'no-store'});if(!r.ok)throw 0;return await r.json()}catch{return fallback}}
function normalizeUrl(raw){try{const u=new URL(raw,location.href);u.hash='';u.search='';return u.href.replace(/\/$/,'')}catch{return String(raw||'').replace(/[?#].*$/,'').replace(/\/$/,'')}}
function workKey(x){return `${x.source||''}|${normalizeUrl(x.url||'')}`}
function updateToken(x){return `${x.latest_url||''}|${x.latest||x.latest_chapter||''}|${x.chapter_count||''}`}
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

async function load(){
  $('#syncText').textContent='正在同步…';$('#syncDot').classList.remove('ok');
  const [feed,library,site,news,content,music,games]=await Promise.all([
    loadJSON('data/feed.json',{generated_at:null,updates:[],sources:{},items:{}}),
    loadJSON('config/library.json',{items:[]}),
    loadJSON('data/site-updates.json',{generated_at:null,items:[],sources:{}}),
    loadJSON('data/acg-news.json',{generated_at:null,items:[],sources:{}}),
    loadJSON('config/content.json',{site_updates:[],news:[],music:{}}),
    loadJSON('data/music.json',{generated_at:null,weekly_chart:[],new_releases:[],sources:{}}),
    loadJSON('data/game-releases.json',{generated_at:null,date_jst:null,items:{mobile:[],pc:[],console:[]},sources:{}})
  ]);
  state.feed=feed;state.library=library;state.site=site;state.news=news;state.content=content;state.music=music;state.games=games;
  syncLocalLibraryFromSite();
  renderAll();
  $('#syncDot').classList.add('ok');
  $('#syncText').textContent=(feed.generated_at||site.generated_at||news.generated_at||music.generated_at||games.generated_at)?'数据已加载':'尚未同步';
}

function remoteLibraryKeys(){
  const keys=new Set();
  for(const x of (state.library?.items||[]).filter(x=>x.enabled!==false))keys.add(workKey(x));
  return keys;
}
function isShelfItem(x){
  const key=workKey(x);if(remoteLibraryKeys().has(key))return true;
  return state.localLibrary.some(y=>workKey(y)===key || (y.source===x.source&&y.title===x.title));
}
function addToLocalShelf(item){
  if(isShelfItem(item))return;
  const now=new Date().toISOString();
  state.localLibrary.unshift({
    id:`local-${item.source}-${item.id||Math.random().toString(36).slice(2)}`,
    local:true,type:item.type,source:item.source,source_label:item.source_label,title:item.title,
    url:item.url,cover:item.cover,latest:item.latest||'最新更新',latest_url:item.latest_url||item.url,
    updated_text:item.updated_text||'',latest_token:updateToken(item),added_at:now,checked_at:state.site?.generated_at||now,changed_at:null
  });
  saveLocalArray(LOCAL_LIBRARY_KEY,state.localLibrary);renderSiteUpdates();renderLibrary();updateStats();
}
function removeLocalShelf(id){state.localLibrary=state.localLibrary.filter(x=>x.id!==id);saveLocalArray(LOCAL_LIBRARY_KEY,state.localLibrary);renderSiteUpdates();renderLibrary();updateStats()}
function syncLocalLibraryFromSite(){
  const rows=state.site?.items||[];let changed=false;
  state.localLibrary=state.localLibrary.map(sub=>{
    const match=rows.find(r=>workKey(r)===workKey(sub))||rows.find(r=>r.source===sub.source&&r.title===sub.title);
    if(!match)return sub;
    const token=updateToken(match);const had=sub.latest_token;const isNew=Boolean(had&&token&&token!==had);
    if(isNew){
      const id=`local-update-${sub.id}-${Date.now()}`;
      state.localUpdates.unshift({id,work_id:sub.id,type:sub.type,source:sub.source,source_label:sub.source_label||match.source_label,title:match.title,cover:match.cover||sub.cover,chapter_title:match.latest||'检测到更新',chapter_url:match.latest_url||match.url,url:match.url,detected_at:state.site?.generated_at||new Date().toISOString(),local:true});
      state.localUpdates=state.localUpdates.slice(0,200);changed=true;
    }
    return {...sub,title:match.title||sub.title,cover:match.cover||sub.cover,latest:match.latest||sub.latest,latest_url:match.latest_url||match.url||sub.latest_url,updated_text:match.updated_text||sub.updated_text,latest_token:token||had,checked_at:state.site?.generated_at||sub.checked_at,changed_at:isNew?(state.site?.generated_at||new Date().toISOString()):sub.changed_at};
  });
  saveLocalArray(LOCAL_LIBRARY_KEY,state.localLibrary);if(changed)saveLocalArray(LOCAL_UPDATES_KEY,state.localUpdates);
}

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
  $('#siteUpdatesGrid').innerHTML=visible.length?visible.map(x=>{const added=isShelfItem(x);return `<article class="site-update-card">
    <a class="site-card-main" href="${esc(x.latest_url||x.url)}" target="_blank" rel="noopener">
      ${imageHTML({cover:x.cover,type:x.type,className:'site-update-cover',placeholderClass:'site-update-placeholder'})}
      <div class="site-update-copy">
        <div class="site-meta"><span class="type-pill ${x.type==='manga'?'manga':'novel'}">${x.type==='manga'?'漫画':'小说'}</span><span class="site-source">${esc(x.source_label||x.source)}</span></div>
        <h3>${esc(x.title)}</h3><p class="site-latest">${esc(x.latest||'最新更新')}</p>
        <div class="site-meta"><span>${esc(x.updated_text||'')}</span><span>${x.latest_url?'直达最新章节 ↗':'打开作品页 ↗'}</span></div>
      </div>
    </a>
    <div class="site-card-actions"><span class="site-open-link">${x.latest_url?'已解析章节':'作品详情'}</span><button class="shelf-btn ${added?'added':''}" data-add-shelf="${esc(x.id)}" ${added?'disabled':''}>${added?'✓ 已在书架':'＋ 加入书架'}</button></div>
  </article>`}).join(''):`<div class="empty"><div>这个筛选下暂无站点更新。<small>来源失败时可以到“来源状态”查看原因。</small></div></div>`;
  $$('[data-add-shelf]').forEach(btn=>btn.onclick=e=>{e.preventDefault();e.stopPropagation();const item=all.find(x=>String(x.id)===btn.dataset.addShelf);if(item)addToLocalShelf(item)});
}

function filteredPersonalUpdates(){
  const remote=state.feed?.updates||[];const local=state.localUpdates||[];
  const list=[...remote,...local].sort((a,b)=>new Date(b.detected_at||0)-new Date(a.detected_at||0));
  const q=state.query.toLowerCase();
  return list.filter(u=>{const okType=state.filter==='all'||state.filter===u.type||(state.filter==='unread'&&!isRead(u.id));const text=`${u.title} ${u.chapter_title} ${u.source} ${u.source_label||''}`.toLowerCase();return okType&&(!q||text.includes(q))});
}
function renderLibraryUpdates(){
  const list=filteredPersonalUpdates();
  if(!list.length){$('#libraryUpdatesList').innerHTML=`<div class="empty"><div>暂无订阅更新记录。<small>云端订阅会独立检查；从更新流加入的本机订阅会在后续站点更新中自动比对。</small></div></div>`;return}
  $('#libraryUpdatesList').innerHTML=list.map(u=>`<article class="update-item ${isRead(u.id)?'':'unread'}" data-id="${esc(u.id)}">
    ${imageHTML({cover:u.cover,type:u.type,className:'update-cover',placeholderClass:'update-cover cover-placeholder'})}
    <div class="update-meta"><div class="row-title"><span class="type-pill ${u.type==='manga'?'manga':'novel'}">${u.type==='manga'?'漫画':'小说'}</span>${u.local?'<span class="type-pill manga">本机</span>':''}<h3>${esc(u.title)}</h3></div><p class="chapter">${esc(u.chapter_title||'检测到更新')}</p><div class="subline"><span>${esc(u.source_label||u.source)}</span></div></div>
    <div class="update-actions"><time>${fmt(u.detected_at)}</time><a class="open-link" target="_blank" rel="noopener" href="${esc(u.chapter_url||u.url)}">打开最新章节 ↗</a></div>
  </article>`).join('');
  $$('#libraryUpdatesList .update-item').forEach(el=>el.addEventListener('click',e=>{if(e.target.closest('a'))return;state.read.add(el.dataset.id);saveRead();renderLibraryUpdates()}));
}
function renderLibrary(){
  const remote=(state.library?.items||[]).filter(x=>x.enabled!==false);const remoteKeys=remoteLibraryKeys();
  const local=state.localLibrary.filter(x=>!remoteKeys.has(workKey(x)));
  const q=state.query.toLowerCase();const status=state.feed?.items||{};
  const remoteCards=remote.map(x=>{const s=status[x.id]||{};return {kind:'remote',id:x.id,type:x.type,source:x.source,title:s.title||x.title||x.id,url:x.url,cover:s.cover||x.cover,latest:s.latest_chapter||'等待首次同步',latest_url:s.latest_url||x.url,checked_at:s.checked_at,changed_at:s.changed_at,ok:s.ok!==false}});
  const localCards=local.map(x=>({kind:'local',...x,ok:true,latest:x.latest||'等待下一次站点更新'}));
  const visible=[...remoteCards,...localCards].filter(x=>!q||`${x.title} ${x.source} ${x.latest}`.toLowerCase().includes(q));
  $('#libraryGrid').innerHTML=visible.length?visible.map(x=>{const fresh=isRecent(x.changed_at);return `<article class="book-card ${x.kind==='local'?'local-book':''}">
      <a class="book-card-link" href="${esc(x.latest_url||x.url)}" target="_blank" rel="noopener" aria-label="打开 ${esc(x.title)}"></a>
      ${imageHTML({cover:x.cover,type:x.type,className:'book-cover',placeholderClass:'book-placeholder'})}
      ${x.kind==='local'?`<div class="book-card-controls"><button data-remove-local="${esc(x.id)}">取消订阅</button></div>`:''}
      <div class="book-card-body"><div class="badge-row"><span class="badge">${x.type==='manga'?'漫画':'小说'}</span><span class="badge ${x.kind==='local'?'local-library-tag':'status-ok'}">${x.kind==='local'?'本机追踪':'云端追踪'}</span>${fresh?'<span class="badge library-new">NEW</span>':''}</div><h3>${esc(x.title)}</h3><p class="book-latest">${esc(x.latest)}</p><p class="book-meta">${esc(sourceLabel(x.source,'site_updates')||x.source)} · 检查 ${fmt(x.checked_at)}</p><span class="book-open">打开最新章节 ↗</span></div>
    </article>`}).join(''):`<div class="empty"><div>书架还是空的。<small>可以直接从“更新流”点击“加入书架”，也可以通过 <code>config/library.json</code> 建立云端深度追踪。</small></div></div>`;
  $$('[data-remove-local]').forEach(b=>b.onclick=e=>{e.preventDefault();e.stopPropagation();removeLocalShelf(b.dataset.removeLocal)});
}

function renderNewsFilters(){
  const configured=(state.content?.news||[]).filter(x=>x.enabled!==false);const ids=new Set(configured.map(x=>x.id));if(state.newsFilter!=='all'&&!ids.has(state.newsFilter))state.newsFilter='all';
  $('#newsFilterChips').innerHTML=`<button class="chip ${state.newsFilter==='all'?'active':''}" data-news-filter="all">全部</button>`+configured.map(x=>`<button class="chip ${state.newsFilter===x.id?'active':''}" data-news-filter="${esc(x.id)}">${esc(x.label)}</button>`).join('');
  $$('.chip[data-news-filter]').forEach(b=>b.onclick=()=>{state.newsFilter=b.dataset.newsFilter;renderNews()});
}
function renderNews(){
  renderNewsFilters();const allowed=enabledSourceIds('news');const all=(state.news?.items||[]).filter(x=>!allowed.size||allowed.has(x.source));const q=state.query.toLowerCase();const visible=all.filter(x=>(state.newsFilter==='all'||x.source===state.newsFilter)&&(!q||`${x.title} ${x.summary} ${x.source_label} ${x.category}`.toLowerCase().includes(q)));const hero=visible[0];
  $('#newsHero').innerHTML=hero?`<a class="news-feature" href="${esc(hero.url)}" target="_blank" rel="noopener">${hero.image?`<img class="news-feature-image" src="${esc(hero.image)}" referrerpolicy="no-referrer" onerror="this.remove()">`:'<div class="news-feature-placeholder"></div>'}<div class="news-feature-copy"><div class="news-meta-row"><span class="news-badge">${esc(hero.source_label)}</span><span class="news-badge">${esc(hero.category)}</span><span class="news-time">${relativeTime(hero.published_at)}</span></div><h3>${esc(hero.title)}</h3><p>${esc(hero.summary||'')}</p><span class="news-feature-link">阅读原文 ↗</span></div></a>`:'';
  const rest=visible.slice(hero?1:0);$('#newsGrid').innerHTML=rest.length?rest.map(x=>`<a class="news-card" href="${esc(x.url)}" target="_blank" rel="noopener">${imageHTML({cover:x.image,type:'news',className:'news-thumb',placeholderClass:'news-thumb-placeholder',placeholderText:'NEWS'})}<div class="news-card-copy"><div class="news-card-meta"><span>${esc(x.source_label)}</span><span>·</span><span>${relativeTime(x.published_at)}</span></div><h3>${esc(x.title)}</h3><p>${esc(x.summary||'')}</p></div></a>`).join(''):(hero?'':`<div class="empty"><div>暂无中文 ACG 新闻。<small>下一次每日 / 手动抓取后生成。</small></div></div>`);
}

function jsonp(url,timeout=12000){
  return new Promise((resolve,reject)=>{const cb=`tsugi_cb_${Date.now()}_${Math.random().toString(36).slice(2)}`;const script=document.createElement('script');const timer=setTimeout(()=>cleanup(new Error('请求超时')),timeout);function cleanup(err,data){clearTimeout(timer);delete window[cb];script.remove();err?reject(err):resolve(data)}window[cb]=data=>cleanup(null,data);script.onerror=()=>cleanup(new Error('请求失败'));script.src=`${url}${url.includes('?')?'&':'?'}callback=${cb}`;document.head.appendChild(script)});
}
async function searchArtists(term){const url=`https://itunes.apple.com/search?term=${encodeURIComponent(term)}&country=jp&media=music&entity=musicArtist&limit=8&lang=ja_jp`;const data=await jsonp(url);return (data.results||[]).filter(x=>x.artistId&&x.artistName)}
async function lookupArtistSongs(artistId){const url=`https://itunes.apple.com/lookup?id=${encodeURIComponent(artistId)}&country=jp&entity=song&limit=8&sort=recent&lang=ja_jp`;const data=await jsonp(url);return (data.results||[]).filter(x=>x.wrapperType==='track'&&x.kind==='song').sort((a,b)=>new Date(b.releaseDate||0)-new Date(a.releaseDate||0))}
function isFollowingName(name){return state.followedArtists.some(x=>x.name===name)}
async function followArtistByName(name){
  if(!name||isFollowingName(name))return;
  try{const results=await searchArtists(name);const exact=results.find(x=>x.artistName.toLowerCase()===name.toLowerCase())||results[0];if(!exact)throw new Error('未找到艺人');const songs=await lookupArtistSongs(exact.artistId);state.followedArtists.unshift({id:String(exact.artistId),name:exact.artistName,genre:exact.primaryGenreName||'',followed_at:new Date().toISOString(),last_seen_track_id:songs[0]?.trackId?String(songs[0].trackId):null});saveLocalArray(ARTIST_FOLLOWS_KEY,state.followedArtists);renderMusic();}catch(e){alert(`关注失败：${e.message}`)}
}
function unfollowArtist(id){state.followedArtists=state.followedArtists.filter(x=>String(x.id)!==String(id));saveLocalArray(ARTIST_FOLLOWS_KEY,state.followedArtists);renderMusic()}
function markArtistSeen(id,trackId){const a=state.followedArtists.find(x=>String(x.id)===String(id));if(a){a.last_seen_track_id=String(trackId||'');saveLocalArray(ARTIST_FOLLOWS_KEY,state.followedArtists);renderFollowedArtists()}}
function artistFollowButton(name){const following=isFollowingName(name);return `<button class="follow-btn ${following?'following':''}" data-follow-artist="${esc(name)}" ${following?'disabled':''}>${following?'✓ 已关注':'＋ 关注艺人'}</button>`}
function bindArtistFollowButtons(){$$('[data-follow-artist]').forEach(b=>b.onclick=e=>{e.preventDefault();e.stopPropagation();followArtistByName(b.dataset.followArtist)})}
function youtubeMusicSearch(title,artist){return `https://music.youtube.com/search?q=${encodeURIComponent(`${title||''} ${artist||''}`.trim())}`}
function renderMusic(){
  const chart=state.music?.weekly_chart||[];const releases=state.music?.recent_songs||state.music?.new_releases||[];const q=state.query.toLowerCase();
  $('#musicChartCount').textContent=chart.length;$('#musicReleaseCount').textContent=releases.length;$('#followedArtistCount').textContent=state.followedArtists.length;$('#musicChartDate').textContent=state.music?.chart_date?`榜单公布：${state.music.chart_date}`:'每周更新';
  const c=chart.filter(x=>!q||`${x.title} ${x.artist}`.toLowerCase().includes(q));
  $('#musicChartList').innerHTML=c.length?c.map(x=>`<article class="music-chart-row"><div class="music-rank">${esc(x.rank)}</div>${imageHTML({cover:x.artwork,type:'music',className:'music-cover',placeholderClass:'music-cover cover-placeholder',placeholderText:'♪'})}<div class="music-track-copy"><h4>${esc(x.title)}${x.is_new?'<span class="chart-new-badge">NEW</span>':''}</h4><p>${esc(x.artist)}${x.last_rank?` · 上周 ${esc(x.last_rank)}`:''}${x.weeks?` · 在榜 ${esc(x.weeks)} 周`:''}</p></div><div class="music-row-actions">${artistFollowButton(x.artist)}<a class="music-service-link yt" href="${esc(x.youtube_music_url||youtubeMusicSearch(x.title,x.artist))}" target="_blank" rel="noopener">YouTube Music ↗</a><a class="music-service-link" href="${esc(x.url||'#')}" target="_blank" rel="noopener">Billboard ↗</a></div></article>`).join(''):`<div class="empty music-empty">暂无周榜数据。</div>`;
  const r=releases.filter(x=>!q||`${x.title} ${x.artist} ${x.album||''}`.toLowerCase().includes(q));
  $('#musicNewGrid').innerHTML=r.length?r.map(x=>`<article class="music-release-card">${imageHTML({cover:x.artwork,type:'music',className:'music-release-cover',placeholderClass:'music-release-cover cover-placeholder',placeholderText:'♪'})}<div class="music-release-copy"><span class="music-source-badge">${esc(x.period||'近一周')}</span><h4>${esc(x.title)}</h4><p>${esc(x.artist)}</p><p>${esc(x.source_label||'Apple Music Japan · 本周新曲')}</p><div class="music-release-actions">${artistFollowButton(x.artist)}<div class="music-service-group"><a class="music-service-link yt" href="${esc(x.youtube_music_url||youtubeMusicSearch(x.title,x.artist))}" target="_blank" rel="noopener">YT Music ↗</a><a class="music-service-link" href="${esc(x.url||'#')}" target="_blank" rel="noopener">来源 ↗</a></div></div></div></article>`).join(''):`<div class="empty music-empty">暂无近一周新曲。<small>若 Apple Music 页面结构临时变化，会自动回退到 Billboard 本周新进榜。</small></div>`;
  bindArtistFollowButtons();renderFollowedArtists();
}
async function renderFollowedArtists(){
  $('#followedArtistCount').textContent=state.followedArtists.length;
  if(!state.followedArtists.length){$('#followedArtistsGrid').innerHTML=`<div class="empty music-empty">还没有关注艺人。<small>可以从周榜 / 新发行直接关注，或在上方搜索。</small></div>`;return}
  $('#followedArtistsGrid').innerHTML=state.followedArtists.map(a=>`<article class="artist-card" id="artist-${esc(a.id)}"><div class="artist-card-top"><div><h4>${esc(a.name)}</h4><p class="artist-card-sub">${esc(a.genre||'Japan Music')}</p></div><div class="artist-card-actions"><button class="mini-btn" data-unfollow="${esc(a.id)}">取消</button></div></div><div class="artist-loading">正在检查最近新曲…</div></article>`).join('');
  $$('[data-unfollow]').forEach(b=>b.onclick=()=>unfollowArtist(b.dataset.unfollow));
  for(const artist of state.followedArtists){
    try{const songs=await lookupArtistSongs(artist.id);const top=songs[0];const hasNew=Boolean(top?.trackId&&artist.last_seen_track_id&&String(top.trackId)!==String(artist.last_seen_track_id));const card=$(`#artist-${CSS.escape(String(artist.id))}`);if(!card)continue;const list=songs.slice(0,4);card.innerHTML=`<div class="artist-card-top"><div><h4>${esc(artist.name)}</h4><p class="artist-card-sub">${esc(artist.genre||'Japan Music')}${hasNew?' · 有新曲':''}</p></div><div class="artist-card-actions">${hasNew?`<button class="mini-btn" data-seen="${esc(artist.id)}" data-track="${esc(top.trackId)}">标记已看</button>`:''}<button class="mini-btn" data-unfollow="${esc(artist.id)}">取消</button></div></div><div class="artist-release-list">${list.map((s,i)=>`<a class="artist-release" href="${esc(s.trackViewUrl||s.collectionViewUrl||'#')}" target="_blank" rel="noopener"><img src="${esc((s.artworkUrl100||'').replace('100x100','200x200'))}" onerror="this.style.visibility='hidden'"><div><h5>${esc(s.trackName)}</h5><p>${esc((s.releaseDate||'').slice(0,10))}</p></div>${hasNew&&i===0?'<span class="new-music-badge">NEW</span>':''}</a>`).join('')||'<div class="artist-loading">暂无最近歌曲</div>'}</div>`;card.querySelector('[data-unfollow]')?.addEventListener('click',()=>unfollowArtist(artist.id));card.querySelector('[data-seen]')?.addEventListener('click',e=>markArtistSeen(artist.id,e.currentTarget.dataset.track));
    }catch(e){const card=$(`#artist-${CSS.escape(String(artist.id))}`);if(card)card.querySelector('.artist-loading').textContent=`检查失败：${e.message}`}
  }
}
async function runArtistSearch(){const term=$('#artistSearchInput').value.trim();if(!term)return;$('#artistSearchResults').innerHTML='<div class="artist-loading">搜索中…</div>';try{const results=await searchArtists(term);$('#artistSearchResults').innerHTML=results.length?results.map(x=>`<div class="artist-result"><div><strong>${esc(x.artistName)}</strong><small>${esc(x.primaryGenreName||'Music')}</small></div>${artistFollowButton(x.artistName)}</div>`).join(''):'<div class="artist-loading">没有找到艺人</div>';bindArtistFollowButtons()}catch(e){$('#artistSearchResults').innerHTML=`<div class="artist-loading">搜索失败：${esc(e.message)}</div>`}}


function gameEffectiveDate(x){return x.release_date||x.first_seen||''}
function gameDateLabel(d,today){
  if(!d)return '日期未定';
  const x=new Date(`${d}T00:00:00`),t=new Date(`${today}T00:00:00`);if(Number.isNaN(+x)||Number.isNaN(+t))return d;
  const diff=Math.round((x-t)/86400000);const md=new Intl.DateTimeFormat('zh-CN',{month:'numeric',day:'numeric',weekday:'short'}).format(x);
  if(diff===0)return `${md} · 今天`;if(diff===-1)return `${md} · 昨天`;if(diff===1)return `${md} · 明天`;if(diff<0)return `${md} · ${Math.abs(diff)} 天前`;return `${md} · ${diff} 天后`;
}
function renderTimelineGame(x){
  const platforms=(x.platforms||[]).join(' / ');const featured=x.featured?'<span class="game-popular-badge">热门</span>':'';const mobile=x.category==='mobile'?'<span class="game-discovery-badge">商店新发现</span>':'';
  return `<a class="timeline-game ${x.is_today?'today':''}" href="${esc(x.url||'#')}" target="_blank" rel="noopener">
    ${imageHTML({cover:x.cover,type:'game',className:'timeline-game-cover',placeholderClass:'timeline-game-cover game-cover-placeholder',placeholderText:'GAME'})}
    <div class="timeline-game-copy"><div class="timeline-game-meta"><span>${esc(x.source_label||x.source||'')}</span>${featured}${mobile}</div><h4>${esc(x.title||'未命名游戏')}</h4><p>${esc(platforms||'平台未标注')}</p></div><span class="timeline-open">查看 ↗</span>
  </a>`;
}
function renderGameTimeline(rows,label){
  if(!rows.length)return `<div class="empty game-empty"><div>暂无${label}时间线数据。<small>下一次每日 / 手动刷新订阅源后更新。</small></div></div>`;
  const today=state.games?.date_jst||new Date().toISOString().slice(0,10);const groups=new Map();
  rows.forEach(x=>{const d=gameEffectiveDate(x)||'undated';if(!groups.has(d))groups.set(d,[]);groups.get(d).push(x)});
  return [...groups.entries()].sort((a,b)=>a[0].localeCompare(b[0])).map(([d,items])=>`<section class="game-timeline-day ${d===today?'today':''}"><div class="game-timeline-date"><span class="timeline-dot"></span><div><strong>${esc(gameDateLabel(d,today))}</strong><small>${esc(d)}</small></div></div><div class="game-timeline-items">${items.map(renderTimelineGame).join('')}</div></section>`).join('');
}
function renderGames(){
  const buckets=state.games?.items||{mobile:[],pc:[],console:[]};const q=state.query.toLowerCase();
  const get=key=>(buckets[key]||[]).filter(x=>!q||`${x.title} ${x.source_label} ${(x.platforms||[]).join(' ')}`.toLowerCase().includes(q));
  const mobile=get('mobile'),pc=get('pc'),consoleRows=get('console');const all=[...(buckets.mobile||[]),...(buckets.pc||[]),...(buckets.console||[])];
  const past=all.filter(x=>x.timeline_status==='past').length,todayCount=all.filter(x=>x.timeline_status==='today').length,upcoming=all.filter(x=>x.timeline_status==='upcoming').length;const w=state.games?.window||{};
  $('#gameDate').textContent=state.games?.date_jst?`日本时间 ${state.games.date_jst} · -${w.past_days??7} 天 / +${w.future_days??90} 天`:'等待首次抓取';
  $('#gamePastCount').textContent=past;$('#gameTodayCount').textContent=todayCount;$('#gameUpcomingCount').textContent=upcoming;
  $('#gameMobileGrid').innerHTML=renderGameTimeline(mobile,'手游');$('#gamePcGrid').innerHTML=renderGameTimeline(pc,'PC');$('#gameConsoleGrid').innerHTML=renderGameTimeline(consoleRows,'主机');
}

function renderSources(){
  const personal=Object.entries(state.feed?.sources||{}).map(([id,s])=>({group:'云端书架',id,label:s.label||id,ok:(s.failed||0)===0,count:s.ok||0,total:s.total||0,error:s.failed?`${s.failed} 个失败`:''}));
  const siteAllowed=enabledSourceIds('site_updates');const site=Object.entries(state.site?.sources||{}).filter(([id])=>!siteAllowed.size||siteAllowed.has(id)).map(([id,s])=>({group:'更新流',id,label:s.label||id,ok:s.ok!==false,count:s.count||0,total:s.count||0,error:s.error||''}));
  const newsAllowed=enabledSourceIds('news');const news=Object.entries(state.news?.sources||{}).filter(([id])=>!newsAllowed.size||newsAllowed.has(id)).map(([id,s])=>({group:'ACG 新闻',id,label:s.label||id,ok:s.ok!==false,count:s.count||0,total:s.count||0,error:s.error||''}));
  const music=Object.entries(state.music?.sources||{}).map(([id,s])=>({group:'音乐追踪',id,label:s.label||id,ok:s.ok!==false,count:s.count||0,total:s.count||0,error:s.error||''}));
  const games=Object.entries(state.games?.sources||{}).map(([id,s])=>({group:'游戏追踪',id,label:s.label||id,ok:s.ok!==false,count:s.count||0,total:s.count||0,error:s.error||''}));
  const entries=[...personal,...site,...news,...music,...games];$('#sourceStatus').innerHTML=entries.length?entries.map(s=>`<article class="source-card"><div class="source-top"><div><span class="section-kicker">${esc(s.group)}</span><h3>${esc(s.label)}</h3></div><i class="status-dot ${s.ok?'':'err'}"></i></div><strong>${s.count}<span style="color:var(--faint);font-size:.48em;font-weight:600"> ${s.group==='云端书架'?`/ ${s.total}`:'items'}</span></strong><p>${s.ok?'抓取正常':esc(s.error||'抓取失败')}</p></article>`).join(''):`<div class="empty">暂无来源状态。</div>`;
}
function updateStats(){
  const remote=(state.library?.items||[]).filter(x=>x.enabled!==false);const remoteKeys=remoteLibraryKeys();const local=state.localLibrary.filter(x=>!remoteKeys.has(workKey(x)));const site=(state.site?.items||[]).filter(x=>{const ids=enabledSourceIds('site_updates');return !ids.size||ids.has(x.source)});const news=(state.news?.items||[]).filter(x=>{const ids=enabledSourceIds('news');return !ids.size||ids.has(x.source)});
  const gameTotal=['mobile','pc','console'].reduce((n,k)=>n+(state.games?.items?.[k]||[]).length,0);$('#libraryCount').textContent=remote.length+local.length;$('#updateCount').textContent=site.length;$('#newsCount').textContent=news.length;$('#musicCount').textContent=(state.music?.weekly_chart||[]).length+(state.music?.new_releases||[]).length;$('#gameCount').textContent=gameTotal;$('#novelCount').textContent=site.filter(x=>x.type==='novel').length;$('#mangaCount').textContent=site.filter(x=>x.type==='manga').length;$('#todayUpdates').textContent=site.length;$('#lastSync').textContent=fmt(state.site?.generated_at||state.feed?.generated_at||state.news?.generated_at||state.music?.generated_at||state.games?.generated_at);
}
function renderAll(){renderSiteUpdates();renderLibrary();renderLibraryUpdates();renderNews();renderMusic();renderGames();renderSources();updateStats()}
function applyTheme(theme){document.documentElement.dataset.theme=theme;localStorage.setItem('tsugi-theme',theme);const meta=document.querySelector('meta[name="theme-color"]');if(meta)meta.content=theme==='light'?'#f4f6fb':'#090b10'}
const titles={updates:['更新流','汇总各小说 / 漫画来源最新更新，可直接加入书架。'],library:['我的书架','合并本机一键订阅与 GitHub Actions 云端追踪，并显示更新记录。'],music:['音乐追踪','Billboard 日本周榜、近一周新曲与艺人新曲追踪。'],games:['游戏追踪','过去 7 天到未来 90 天的游戏发售时间线；PC 仅保留 Steam 热门作品。'],news:['ACG 新闻','仅显示简体中文 / 繁体中文的 ACG 新闻。'],sources:['来源状态','检查阅读、音乐、游戏和中文 ACG 新闻最近一次抓取是否正常。'],settings:['设置说明','订阅作品、艺人关注、游戏发行、公开来源与同步频率设置。']};
$$('.nav-item').forEach(b=>b.onclick=()=>{$$('.nav-item').forEach(x=>x.classList.remove('active'));b.classList.add('active');$$('.tab').forEach(x=>x.classList.remove('active'));$('#'+b.dataset.tab).classList.add('active');$('#pageTitle').textContent=titles[b.dataset.tab][0];$('#pageSubtitle').textContent=titles[b.dataset.tab][1]});
$$('.chip[data-filter]').forEach(b=>b.onclick=()=>{$$('.chip[data-filter]').forEach(x=>x.classList.remove('active'));b.classList.add('active');state.filter=b.dataset.filter;renderLibraryUpdates()});
$$('.chip[data-site-filter]').forEach(b=>b.onclick=()=>{$$('.chip[data-site-filter]').forEach(x=>x.classList.remove('active'));b.classList.add('active');state.siteFilter=b.dataset.siteFilter;renderSiteUpdates()});
$$('[data-game-view]').forEach(b=>b.onclick=()=>{state.gameView=b.dataset.gameView;$$('[data-game-view]').forEach(x=>x.classList.toggle('active',x===b));$$('.game-pane').forEach(x=>x.classList.remove('active'));$(`#game${state.gameView==='mobile'?'Mobile':state.gameView==='pc'?'Pc':'Console'}Pane`).classList.add('active')});
$$('[data-music-view]').forEach(b=>b.onclick=()=>{state.musicView=b.dataset.musicView;$$('[data-music-view]').forEach(x=>x.classList.toggle('active',x===b));$$('.music-pane').forEach(x=>x.classList.remove('active'));$(`#music${state.musicView==='chart'?'Chart':state.musicView==='new'?'New':'Artists'}Pane`).classList.add('active');if(state.musicView==='artists')renderFollowedArtists()});
$('#search').addEventListener('input',e=>{state.query=e.target.value.trim();renderSiteUpdates();renderLibrary();renderLibraryUpdates();renderNews();renderMusic();renderGames()});
$('#refreshBtn').onclick=load;$('#themeBtn').onclick=()=>applyTheme(document.documentElement.dataset.theme==='light'?'dark':'light');$('#markAllRead').onclick=()=>{[...(state.feed?.updates||[]),...state.localUpdates].forEach(x=>state.read.add(x.id));saveRead();renderLibraryUpdates()};
$('#artistSearchBtn').onclick=runArtistSearch;$('#artistSearchInput').addEventListener('keydown',e=>{if(e.key==='Enter')runArtistSearch()});$('#refreshArtistsBtn').onclick=renderFollowedArtists;
applyTheme(document.documentElement.dataset.theme||'dark');load();
