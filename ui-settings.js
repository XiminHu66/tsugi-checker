/* Tsugi v8.2 · browser-local UI customization */
(() => {
  const KEY='tsugi-ui-settings-v2';
  const TAB_KEY='tsugi-last-tab-v1';
  const GAME_VIEW_KEY='tsugi-last-game-view-v1';
  const MUSIC_VIEW_KEY='tsugi-last-music-view-v1';
  const defaults={
    uiZoom:100,
    pagePad:34,
    sidebarWidth:280,
    density:'standard',
    gameCols:'auto',
    stickyTopbar:false,
    reduceMotion:false,
    hideDecor:false,
    themeEnabled:false,
    themeSource:'',
    themeImage:'',
    themePosX:50,
    themePosY:50,
    themeOpacity:36,
    themeBlur:0,
    themeDim:42,
    themeFit:'cover'
  };
  let cfg=loadCfg();
  let toastTimer=null;

  function loadCfg(){
    try{return {...defaults,...JSON.parse(localStorage.getItem(KEY)||'{}')}}
    catch{return {...defaults}}
  }
  function saveCfg(){
    try{localStorage.setItem(KEY,JSON.stringify(cfg))}
    catch(e){notify('设置保存失败：浏览器本地存储空间不足。')}
  }
  function notify(msg){
    let el=document.querySelector('.tsugi-settings-toast');
    if(!el){
      el=document.createElement('div');
      el.className='tsugi-settings-toast';
      document.body.appendChild(el);
    }
    clearTimeout(toastTimer);
    el.textContent=msg;
    el.classList.add('show');
    toastTimer=setTimeout(()=>el.classList.remove('show'),2600);
  }
  function ensureBg(){
    let bg=document.getElementById('tsugiCustomThemeBg');
    if(!bg){
      bg=document.createElement('div');
      bg.id='tsugiCustomThemeBg';
      bg.className='tsugi-custom-theme-bg';
      document.body.prepend(bg);
    }
    let shade=document.getElementById('tsugiCustomThemeShade');
    if(!shade){
      shade=document.createElement('div');
      shade.id='tsugiCustomThemeShade';
      shade.className='tsugi-custom-theme-shade';
      bg.after(shade);
    }
    return {bg,shade};
  }
  function effectiveImage(){
    return cfg.themeImage||cfg.themeSource||'';
  }
  function cssImage(url){
    return url ? `url("${String(url).replace(/\\/g,'\\\\').replace(/"/g,'\\"')}")` : 'none';
  }
  function applyCfg(){
    const root=document.documentElement;
    const body=document.body;
    root.style.setProperty('--tsugi-ui-zoom',String(Number(cfg.uiZoom||100)/100));
    root.style.setProperty('--tsugi-page-pad',`${Number(cfg.pagePad||34)}px`);
    root.style.setProperty('--tsugi-sidebar-width',`${Number(cfg.sidebarWidth||280)}px`);
    root.style.setProperty('--theme-pos-x',`${Number(cfg.themePosX||50)}%`);
    root.style.setProperty('--theme-pos-y',`${Number(cfg.themePosY||50)}%`);
    root.style.setProperty('--theme-image-opacity',String(Number(cfg.themeOpacity||0)/100));
    root.style.setProperty('--theme-image-blur',`${Number(cfg.themeBlur||0)}px`);
    root.style.setProperty('--theme-dim',String(Number(cfg.themeDim||0)/100));
    body.dataset.density=cfg.density||'standard';
    if(cfg.gameCols==='auto')delete body.dataset.gameCols;else body.dataset.gameCols=cfg.gameCols;
    body.classList.toggle('sticky-topbar',!!cfg.stickyTopbar);
    body.classList.toggle('reduce-motion',!!cfg.reduceMotion);
    body.classList.toggle('hide-decor',!!cfg.hideDecor);
    const {bg}=ensureBg();
    const img=effectiveImage();
    const enabled=!!cfg.themeEnabled&&!!img;
    body.classList.toggle('has-custom-theme',enabled);
    bg.style.backgroundImage=cssImage(img);
    bg.style.backgroundSize=cfg.themeFit||'cover';
    updatePreview();
  }
  function updatePreview(){
    const img=document.getElementById('themePreviewImage');
    const shade=document.getElementById('themePreviewShade');
    const effective=effectiveImage();
    if(img){
      img.style.backgroundImage=cssImage(effective);
      img.style.backgroundPosition=`${cfg.themePosX}% ${cfg.themePosY}%`;
      img.style.backgroundSize=cfg.themeFit||'cover';
      img.style.opacity=String((cfg.themeOpacity||0)/100);
      img.style.filter=`blur(${cfg.themeBlur||0}px)`;
    }
    if(shade){
      const light=document.documentElement.dataset.theme==='light';
      shade.style.background=light
        ? `rgba(241,245,251,${(cfg.themeDim||0)/100})`
        : `rgba(5,8,14,${(cfg.themeDim||0)/100})`;
    }
  }
  function setCfg(key,val,{save=true,apply=true}={}){
    cfg[key]=val;
    if(save)saveCfg();
    if(apply)applyCfg();
    syncControls(key);
  }
  function rangeRow(label,key,min,max,step,suffix=''){
    return `<div class="ui-control"><label for="ui-${key}">${label}</label><input id="ui-${key}" data-ui-range="${key}" type="range" min="${min}" max="${max}" step="${step}" value="${cfg[key]}"><output id="out-${key}">${cfg[key]}${suffix}</output></div>`;
  }
  function switchRow(label,key){
    return `<div class="ui-switch-line"><span>${label}</span><label class="ui-switch"><input type="checkbox" data-ui-switch="${key}" ${cfg[key]?'checked':''}><i></i></label></div>`;
  }
  function buildPanel(){
    const host=document.querySelector('#settings .settings-grid');
    const settingsTab=document.getElementById('settings');
    if(!settingsTab||document.getElementById('tsugiUiCustomizer'))return;
    const panel=document.createElement('section');
    panel.id='tsugiUiCustomizer';
    panel.className='tsugi-ui-customizer';
    panel.innerHTML=`
      <div class="ui-customizer-head">
        <div><span class="section-kicker">APPEARANCE / LOCAL</span><h3>界面与主题设置</h3><p>这些设置只保存在当前浏览器。主题图支持 URL 或本地上传，并可拖动预览图调整焦点位置。</p></div>
        <button class="ui-reset-btn" id="uiResetAll">恢复默认</button>
      </div>
      <div class="ui-settings-grid">
        <article class="ui-settings-card">
          <h4>布局与可读性</h4>
          <p>快速调整整体比例、留白、侧栏和信息密度。</p>
          <div class="ui-preset-row">
            <button class="ui-preset-btn" data-ui-preset="compact">紧凑</button>
            <button class="ui-preset-btn" data-ui-preset="standard">标准</button>
            <button class="ui-preset-btn" data-ui-preset="comfortable">舒适</button>
          </div>
          ${rangeRow('整体显示大小','uiZoom',90,120,5,'%')}
          ${rangeRow('页面左右留白','pagePad',18,52,2,'px')}
          ${rangeRow('桌面侧栏宽度','sidebarWidth',240,340,10,'px')}
          <div class="ui-control"><span class="control-label">信息密度</span><select data-ui-select="density"><option value="compact">紧凑</option><option value="standard">标准</option><option value="comfortable">舒适</option></select><output></output></div>
          <div class="ui-control"><span class="control-label">游戏每行卡片</span><select data-ui-select="gameCols"><option value="auto">自动</option><option value="2">2 列</option><option value="3">3 列</option><option value="4">4 列</option><option value="5">5 列</option></select><output></output></div>
          ${switchRow('顶部标题栏滚动时固定','stickyTopbar')}
          ${switchRow('减少动画效果','reduceMotion')}
          ${switchRow('隐藏背景网格与光晕','hideDecor')}
          <div class="settings-hotkeys"><span><kbd>/</kbd> 搜索</span><span><kbd>Esc</kbd> 清空搜索</span><span>刷新后保留当前 Tab</span></div>
        </article>
        <article class="ui-settings-card">
          <h4>主题图</h4>
          <p>本地图片会压缩后存在浏览器；URL 模式适合使用长期稳定的图片地址。</p>
          <div class="theme-editor">
            <div class="theme-preview" id="themePreview">
              <div class="theme-preview-image" id="themePreviewImage"></div>
              <div class="theme-preview-shade" id="themePreviewShade"></div>
              <div class="theme-preview-hint">拖动图片调整焦点 · 位置 ${cfg.themePosX}% / ${cfg.themePosY}%</div>
            </div>
            <div class="theme-tools">
              ${switchRow('启用主题图','themeEnabled')}
              <div class="theme-source-actions">
                <label class="ui-action-btn" for="themeFileInput">上传本地图片</label>
                <input class="theme-file-input" id="themeFileInput" type="file" accept="image/*">
                <button class="ui-action-btn danger" id="themeRemoveImage">移除图片</button>
              </div>
              <div class="theme-url-row"><input id="themeUrlInput" placeholder="https://... 图片地址" value="${cfg.themeSource||''}"><button class="ui-action-btn" id="themeApplyUrl">使用 URL</button></div>
              ${rangeRow('水平位置','themePosX',0,100,1,'%')}
              ${rangeRow('垂直位置','themePosY',0,100,1,'%')}
              ${rangeRow('图片可见度','themeOpacity',5,100,1,'%')}
              ${rangeRow('背景模糊','themeBlur',0,18,1,'px')}
              ${rangeRow('界面遮罩','themeDim',0,80,1,'%')}
              <div class="ui-control"><span class="control-label">图片填充</span><select data-ui-select="themeFit"><option value="cover">铺满 Cover</option><option value="contain">完整 Contain</option></select><output></output></div>
              <div class="theme-position-presets"><button class="theme-pos-btn" data-theme-pos="50,0">顶部</button><button class="theme-pos-btn" data-theme-pos="50,50">居中</button><button class="theme-pos-btn" data-theme-pos="25,50">偏左</button><button class="theme-pos-btn" data-theme-pos="75,50">偏右</button><button class="theme-pos-btn" data-theme-pos="50,100">底部</button></div>
              <div class="theme-storage-note">建议图片横向 ≥ 1920px。本地上传会自动缩放到最长边约 2560px 并转为 WebP/JPEG，以减少浏览器存储占用。</div>
            </div>
          </div>
        </article>
      </div>`;
    if(host)settingsTab.insertBefore(panel,host);else settingsTab.appendChild(panel);
    bindPanel();
    syncControls();
    updatePreview();
  }
  function syncControls(){
    document.querySelectorAll('[data-ui-range]').forEach(el=>{
      const k=el.dataset.uiRange;
      el.value=cfg[k];
      const out=document.getElementById(`out-${k}`);
      if(out){
        const suffix={uiZoom:'%',pagePad:'px',sidebarWidth:'px',themePosX:'%',themePosY:'%',themeOpacity:'%',themeBlur:'px',themeDim:'%'}[k]||'';
        out.textContent=`${cfg[k]}${suffix}`;
      }
    });
    document.querySelectorAll('[data-ui-switch]').forEach(el=>el.checked=!!cfg[el.dataset.uiSwitch]);
    document.querySelectorAll('[data-ui-select]').forEach(el=>el.value=String(cfg[el.dataset.uiSelect]));
    document.querySelectorAll('[data-ui-preset]').forEach(el=>el.classList.toggle('active',el.dataset.uiPreset===cfg.density));
    const url=document.getElementById('themeUrlInput');
    if(url&&document.activeElement!==url)url.value=cfg.themeSource||'';
    const hint=document.querySelector('.theme-preview-hint');
    if(hint)hint.textContent=`拖动图片调整焦点 · 位置 ${cfg.themePosX}% / ${cfg.themePosY}%`;
  }
  function bindPanel(){
    document.querySelectorAll('[data-ui-range]').forEach(el=>el.addEventListener('input',()=>{
      const key=el.dataset.uiRange;
      cfg[key]=Number(el.value);
      saveCfg();applyCfg();syncControls();
    }));
    document.querySelectorAll('[data-ui-switch]').forEach(el=>el.addEventListener('change',()=>setCfg(el.dataset.uiSwitch,el.checked)));
    document.querySelectorAll('[data-ui-select]').forEach(el=>el.addEventListener('change',()=>setCfg(el.dataset.uiSelect,el.value)));
    document.querySelectorAll('[data-ui-preset]').forEach(el=>el.addEventListener('click',()=>{
      const p=el.dataset.uiPreset;
      const map={
        compact:{density:'compact',uiZoom:95,pagePad:24,sidebarWidth:260,gameCols:'5'},
        standard:{density:'standard',uiZoom:100,pagePad:34,sidebarWidth:280,gameCols:'auto'},
        comfortable:{density:'comfortable',uiZoom:110,pagePad:40,sidebarWidth:300,gameCols:'3'}
      }[p];
      Object.assign(cfg,map);saveCfg();applyCfg();syncControls();notify(`已应用“${el.textContent.trim()}”预设`);
    }));
    document.getElementById('uiResetAll')?.addEventListener('click',()=>{
      if(!confirm('恢复所有界面设置为默认值？本地主题图也会移除。'))return;
      cfg={...defaults};saveCfg();applyCfg();syncControls();notify('界面设置已恢复默认');
    });
    document.getElementById('themeApplyUrl')?.addEventListener('click',()=>{
      const value=(document.getElementById('themeUrlInput')?.value||'').trim();
      cfg.themeSource=value;
      cfg.themeImage='';
      cfg.themeEnabled=!!value;
      saveCfg();applyCfg();syncControls();
      notify(value?'已应用主题图 URL':'主题图 URL 已清空');
    });
    document.getElementById('themeRemoveImage')?.addEventListener('click',()=>{
      cfg.themeImage='';cfg.themeSource='';cfg.themeEnabled=false;
    });
    // Corrected below after function definition.
    const removeBtn=document.getElementById('themeRemoveImage');
    if(removeBtn)removeBtn.onclick=()=>{
      cfg.themeImage='';cfg.themeSource='';cfg.themeEnabled=false;
      saveCfg();applyCfg();syncControls();notify('主题图已移除');
    };
    document.getElementById('themeFileInput')?.addEventListener('change',async e=>{
      const file=e.target.files?.[0];if(!file)return;
      try{
        notify('正在压缩主题图…');
        const data=await compressImage(file,2560,0.84);
        cfg.themeImage=data;cfg.themeSource='';cfg.themeEnabled=true;
        cfg.themePosX=50;cfg.themePosY=50;
        saveCfg();applyCfg();syncControls();notify('本地主题图已应用');
      }catch(err){notify(`主题图处理失败：${err.message||err}`)}
      e.target.value='';
    });
    document.querySelectorAll('[data-theme-pos]').forEach(btn=>btn.addEventListener('click',()=>{
      const [x,y]=btn.dataset.themePos.split(',').map(Number);
      cfg.themePosX=x;cfg.themePosY=y;saveCfg();applyCfg();syncControls();
    }));
    bindPreviewDrag();
  }
  async function compressImage(file,maxSide=2560,quality=.84){
    const src=await fileToDataUrl(file);
    const img=await loadImage(src);
    let w=img.naturalWidth||img.width,h=img.naturalHeight||img.height;
    const scale=Math.min(1,maxSide/Math.max(w,h));
    w=Math.max(1,Math.round(w*scale));h=Math.max(1,Math.round(h*scale));
    const canvas=document.createElement('canvas');canvas.width=w;canvas.height=h;
    const ctx=canvas.getContext('2d',{alpha:false});
    ctx.drawImage(img,0,0,w,h);
    let blob=await canvasToBlob(canvas,'image/webp',quality);
    if(!blob||blob.size>2_800_000)blob=await canvasToBlob(canvas,'image/jpeg',Math.max(.68,quality-.08));
    if(!blob)throw new Error('浏览器无法压缩该图片');
    if(blob.size>3_800_000)throw new Error('图片压缩后仍过大，请换一张尺寸更小的图片');
    return await fileToDataUrl(blob);
  }
  function fileToDataUrl(file){return new Promise((res,rej)=>{const r=new FileReader();r.onload=()=>res(r.result);r.onerror=()=>rej(r.error||new Error('读取失败'));r.readAsDataURL(file)})}
  function loadImage(src){return new Promise((res,rej)=>{const i=new Image();i.onload=()=>res(i);i.onerror=()=>rej(new Error('无法读取图片'));i.src=src})}
  function canvasToBlob(c,type,q){return new Promise(res=>c.toBlob(res,type,q))}
  function bindPreviewDrag(){
    const el=document.getElementById('themePreview');if(!el)return;
    let dragging=false;
    const move=e=>{
      if(!dragging)return;
      const r=el.getBoundingClientRect();
      cfg.themePosX=Math.max(0,Math.min(100,Math.round((e.clientX-r.left)/r.width*100)));
      cfg.themePosY=Math.max(0,Math.min(100,Math.round((e.clientY-r.top)/r.height*100)));
      applyCfg();syncControls();
    };
    el.addEventListener('pointerdown',e=>{dragging=true;el.classList.add('dragging');el.setPointerCapture?.(e.pointerId);move(e)});
    el.addEventListener('pointermove',move);
    const end=()=>{if(dragging){dragging=false;el.classList.remove('dragging');saveCfg()}};
    el.addEventListener('pointerup',end);el.addEventListener('pointercancel',end);
  }

  function bindPersistence(){
    document.querySelectorAll('.nav-item[data-tab]').forEach(btn=>btn.addEventListener('click',()=>localStorage.setItem(TAB_KEY,btn.dataset.tab)));
    document.querySelectorAll('[data-game-view]').forEach(btn=>btn.addEventListener('click',()=>localStorage.setItem(GAME_VIEW_KEY,btn.dataset.gameView)));
    document.querySelectorAll('[data-music-view]').forEach(btn=>btn.addEventListener('click',()=>localStorage.setItem(MUSIC_VIEW_KEY,btn.dataset.musicView)));
    setTimeout(()=>{
      const tab=localStorage.getItem(TAB_KEY);
      if(tab)document.querySelector(`.nav-item[data-tab="${CSS.escape(tab)}"]`)?.click();
      const gv=localStorage.getItem(GAME_VIEW_KEY);
      if(gv)document.querySelector(`[data-game-view="${CSS.escape(gv)}"]`)?.click();
      const mv=localStorage.getItem(MUSIC_VIEW_KEY);
      if(mv)document.querySelector(`[data-music-view="${CSS.escape(mv)}"]`)?.click();
    },30);
  }
  function bindHotkeys(){
    document.addEventListener('keydown',e=>{
      const tag=(document.activeElement?.tagName||'').toLowerCase();
      const typing=tag==='input'||tag==='textarea'||tag==='select'||document.activeElement?.isContentEditable;
      if(e.key==='/'&&!typing){
        e.preventDefault();document.getElementById('search')?.focus();
      }
      if(e.key==='Escape'){
        const search=document.getElementById('search');
        if(search&&search.value){
          search.value='';
          search.dispatchEvent(new Event('input',{bubbles:true}));
        }
        if(document.activeElement instanceof HTMLElement)document.activeElement.blur();
      }
    });
  }

  // Apply immediately so background/layout do not wait for data loading.
  ensureBg();applyCfg();
  buildPanel();
  bindPersistence();
  bindHotkeys();

  // The theme button can change light/dark after this script; keep preview shade in sync.
  document.getElementById('themeBtn')?.addEventListener('click',()=>setTimeout(updatePreview,0));
})();

/* v9.2 · keep the subtle "最后同步" timestamp in sync with data refreshes. */
(() => {
  const shortFmt = new Intl.DateTimeFormat('zh-CN', {
    month:'2-digit', day:'2-digit',
    hour:'2-digit', minute:'2-digit',
    hour12:false
  });
  const fullFmt = new Intl.DateTimeFormat('zh-CN', {
    year:'numeric', month:'2-digit', day:'2-digit',
    hour:'2-digit', minute:'2-digit', second:'2-digit',
    hour12:false, timeZoneName:'short'
  });

  async function readSiteStamp(){
    const response=await fetch(`data/site-updates.json?v=${Date.now()}`,{cache:'no-store'});
    if(!response.ok)throw new Error(`HTTP ${response.status}`);
    const data=await response.json();
    return data?.generated_at||'';
  }

  function renderSiteStamp(raw){
    const el=document.getElementById('pageUpdatedAt');
    if(!el)return;
    const d=raw?new Date(raw):null;
    if(!d||Number.isNaN(+d)){
      el.textContent='最后同步 · 尚无记录';
      el.removeAttribute('title');
      return;
    }
    el.textContent=`最后同步 · ${shortFmt.format(d)}`;
    el.title=`阅读更新流最后完成抓取：${fullFmt.format(d)}`;
  }

  async function refreshSiteStamp(){
    try{renderSiteStamp(await readSiteStamp())}
    catch{
      const el=document.getElementById('pageUpdatedAt');
      if(el)el.textContent='最后同步 · 暂不可用';
    }
  }

  // Expose one shared hook so future refresh flows can update the same timestamp.
  window.refreshPageUpdatedAt=refreshSiteStamp;

  // The small circular button reloads generated JSON through app.js.
  // Refresh this independent timestamp immediately after that reload starts.
  document.getElementById('refreshBtn')?.addEventListener('click',()=>{
    setTimeout(refreshSiteStamp,180);
  });

  // "刷新订阅源" completes asynchronously in GitHub Actions. Watch the same
  // generated_at field so the timestamp changes as soon as the new Pages data appears.
  document.getElementById('sourceRefreshBtn')?.addEventListener('click',async()=>{
    let before='';
    try{before=await readSiteStamp()}catch{}
    for(let i=0;i<24;i++){
      await new Promise(r=>setTimeout(r,12500));
      try{
        const current=await readSiteStamp();
        if(current&&current!==before){
          renderSiteStamp(current);
          return;
        }
      }catch{}
    }
  });
})();

