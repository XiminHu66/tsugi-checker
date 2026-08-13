/* Tsugi · game intelligence UI override.
   Loaded after app.js so it can reuse state/$/esc/imageHTML while keeping the stable
   stable Steam scraping/rendering code untouched. */
(() => {
  const sameText=(a,b)=>String(a||'').trim().toLocaleLowerCase()===String(b||'').trim().toLocaleLowerCase();
  const cleanGameTitle=t=>String(t||'').trim()
    .replace(/^「(.+)」のアイコン画像$/,'$1')
    .replace(/^(.+?)のアイコン画像$/,'$1')
    .replace(/^「(.+)」アイコン画像$/,'$1');
  const gameDays=(x,today)=>{
    const d=gameEffectiveDate(x);if(!d)return null;
    const a=new Date(`${d}T00:00:00`),b=new Date(`${today}T00:00:00`);
    if(Number.isNaN(+a)||Number.isNaN(+b))return null;
    return Math.round((a-b)/86400000);
  };
  const countFmt=n=>{
    n=Number(n||0);if(!n)return '';
    if(n>=10000)return `${(n/10000).toFixed(n>=100000?0:1)}万`;
    if(n>=1000)return `${(n/1000).toFixed(1)}k`;
    return String(n);
  };
  const gameSearchText=x=>[
    x.title,x.title_zh,x.title_en,x.source_label,
    ...(x.platforms||[]),...(x.developers||[]),...(x.publishers||[]),...(x.tags||[])
  ].filter(Boolean).join(' ').toLowerCase();

  renderTimelineGame=function(x){
    const platforms=(x.platforms||[]).join(' / ');
    const displayTitle=cleanGameTitle(x.title_zh||x.title||'未命名游戏');
    const altTitle=x.title_en&&!sameText(x.title_en,displayTitle)?x.title_en:'';
    const heat=x.heat_label?`<span class="game-heat-badge ${esc(x.heat_level||'medium')}">${esc(x.heat_label)}</span>`:'';
    const publisherBadge=x.notable_publisher?`<span class="game-publisher-badge">知名发行</span>`:'';
    const rank=x.popularity_rank?`<span class="game-rank-badge">#${esc(x.popularity_rank)}</span>`:'';
    const discovery=(x.category==='mobile'&&!x.heat_label)?`<span class="game-discovery-badge">${esc(x.popularity_label||'商店精选')}</span>`:'';
    const devs=(x.developers||[]).slice(0,2).join(' / ');
    const pubs=(x.publishers||[]).slice(0,2).join(' / ');
    const companies=x.category==='pc'&&((devs)||(pubs))?`<div class="game-company-lines">
      ${devs?`<div><b>开发</b><span>${esc(devs)}</span></div>`:''}
      ${pubs?`<div><b>发行</b><span>${esc(pubs)}</span></div>`:''}
    </div>`:'';
    const tags=x.category==='pc'&&x.tags?.length?`<div class="game-mini-tags">${x.tags.slice(0,5).map(t=>`<span>${esc(t)}</span>`).join('')}</div>`:'';
    const reviewCount=Number(x.review_count||0);
    const review=x.category==='pc'&&reviewCount?`<div class="game-review-note">${countFmt(reviewCount)} 条评价${x.review_positive_percent!=null?` · ${esc(x.review_positive_percent)}% 好评`:''}</div>`:'';
    const rating=x.category==='mobile'&&x.rating?`<div class="game-review-note">${Number(x.rating).toFixed(1)}★${x.rating_count?` · ${countFmt(x.rating_count)} 评分`:''}</div>`:'';
    return `<a class="timeline-game ${x.is_today?'today':''} ${x.category==='pc'?'pc-rich':''} ${x.heat_level==='high'?'high-heat':''}" href="${esc(x.url||'#')}" target="_blank" rel="noopener">
      ${imageHTML({cover:x.cover,type:'game',className:'timeline-game-cover',placeholderClass:'timeline-game-cover game-cover-placeholder',placeholderText:'GAME'})}
      <div class="timeline-game-copy">
        <div class="timeline-game-meta"><span>${esc(x.source_label||x.source||'')}</span>${heat}${publisherBadge}${rank}${discovery}</div>
        <h4>${esc(displayTitle)}</h4>
        ${altTitle?`<div class="game-title-en">${esc(altTitle)}</div>`:''}
        <p>${esc(platforms||'平台未标注')}</p>
        ${companies}${tags}${review}${rating}
      </div>
      <span class="timeline-open">查看 ↗</span>
    </a>`;
  };

  renderGameTimeline=function(rows,label){
    if(!rows.length)return `<div class="empty game-empty"><div>暂无${label}时间线数据。<small>下一次每日 / 手动刷新订阅源后更新。</small></div></div>`;
    const today=state.games?.date_jst||new Date().toISOString().slice(0,10),groups=new Map();
    rows.forEach(x=>{const d=gameEffectiveDate(x)||'undated';if(!groups.has(d))groups.set(d,[]);groups.get(d).push(x)});
    return [...groups.entries()].sort((a,b)=>a[0].localeCompare(b[0])).map(([d,items])=>{
      const sorted=[...items].sort((a,b)=>(Number(b.heat_score||0)-Number(a.heat_score||0))||String(a.title_zh||a.title||'').localeCompare(String(b.title_zh||b.title||''),'zh-CN'));
      return `<section class="game-timeline-day ${d===today?'today':''}"><div class="game-timeline-date"><span class="timeline-dot"></span><div><strong>${esc(gameDateLabel(d,today))}</strong><small>${esc(d)}</small></div></div><div class="game-timeline-items">${sorted.map(renderTimelineGame).join('')}</div></section>`;
    }).join('');
  };

  const pcBlock=(title,sub,rows,cls='')=>!rows.length?'':`<section class="pc-window-block ${cls}">
    <div class="pc-window-head"><div><span>${esc(title)}</span><small>${esc(sub)}</small></div><strong>${rows.length}</strong></div>
    ${renderGameTimeline(rows,'PC')}
  </section>`;

  const pcDetails=(title,sub,rows,cls='')=>!rows.length?'':`<details class="pc-window-details ${cls}">
    <summary><div><span>${esc(title)}</span><small>${esc(sub)}</small></div><strong>${rows.length}</strong></summary>
    <div class="pc-window-detail-body">${renderGameTimeline(rows,'PC')}</div>
  </details>`;

  function renderPcTimeline(rows){
    if(!rows.length)return `<div class="empty game-empty"><div>暂无 PC 时间线数据。<small>下一次每日 / 手动刷新订阅源后更新。</small></div></div>`;
    const today=state.games?.date_jst||new Date().toISOString().slice(0,10);
    const todayRows=[],next30=[],later=[],past=[],unknown=[];
    rows.forEach(x=>{
      const diff=gameDays(x,today);
      if(diff===0)todayRows.push(x);
      else if(diff!=null&&diff>=1&&diff<=30)next30.push(x);
      else if(diff!=null&&diff>30)later.push(x);
      else if(diff!=null&&diff<0)past.push(x);
      else unknown.push(x);
    });
    const byHeat=(a,b)=>(Number(b.heat_score||0)-Number(a.heat_score||0));
    todayRows.sort(byHeat);
    return [
      pcBlock('今日发行','今天优先展示；同日按讨论度 / 热度排序',todayRows,'pc-today-priority'),
      pcBlock('接下来 30 天','近期即将发售作品，按日期排列；同日热门作品优先',next30,'pc-next-month'),
      pcDetails('更远期 · 31–90 天','默认折叠，避免远期作品挤占近期视线',later,'pc-later'),
      pcDetails('近期已发售 · 过去 7 天','默认折叠并降低视觉权重，仍可展开查询',past,'pc-past'),
      pcDetails('日期未定','少量 Steam 热门但尚无可靠日期的作品',unknown,'pc-undated')
    ].join('');
  }

  renderGames=function(){
    const buckets=state.games?.items||{mobile:[],pc:[],console:[]},q=state.query.toLowerCase();
    const get=key=>(buckets[key]||[]).filter(x=>!q||gameSearchText(x).includes(q));
    const mobile=get('mobile'),pc=get('pc'),consoleRows=get('console');
    const all=[...(buckets.mobile||[]),...(buckets.pc||[]),...(buckets.console||[])];
    const past=all.filter(x=>x.timeline_status==='past').length;
    const todayCount=all.filter(x=>x.timeline_status==='today').length;
    const upcoming=all.filter(x=>x.timeline_status==='upcoming').length;
    const w=state.games?.window||{};
    $('#gameDate').textContent=state.games?.date_jst?`日本时间 ${state.games.date_jst} · -${w.past_days??7} 天 / +${w.future_days??90} 天`:'等待首次抓取';
    $('#gamePastCount').textContent=past;$('#gameTodayCount').textContent=todayCount;$('#gameUpcomingCount').textContent=upcoming;
    $('#gameMobileGrid').innerHTML=renderGameTimeline(mobile,'手游');
    $('#gamePcGrid').innerHTML=renderPcTimeline(pc);
    $('#gameConsoleGrid').innerHTML=renderGameTimeline(consoleRows,'主机');
  };

  const pcHelp=document.querySelector('#gamePcPane .game-pane-head p');
  if(pcHelp)pcHelp.textContent='今日发行优先，其次展示未来 30 天；31–90 天与过去 7 天默认折叠。卡片会补充中文名、类型、开发商、发行商和 Steam 评价热度。';
  const mobileHelp=document.querySelector('#gameMobilePane .game-pane-head p');
  if(mobileHelp)mobileHelp.textContent='日本与国内手游均经过数量筛选；TapTap 排名/评分与 App Store 评分量可用于标记高热、高讨论或高口碑作品。';

  if(state.games)renderGames();
})();
