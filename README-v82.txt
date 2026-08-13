Tsugi v8.2 累计前端自定义补丁

这是 v8.1 + 本次界面自定义的累计包。

覆盖/新增：
- game-v8.css
- game-v8.js
- scraper/game_enrich.py
- ui-settings.css
- ui-settings.js
- .github/workflows/update-feed.yml

不会覆盖：
- index.html
- app.js
- styles.css / v5.css
- scraper/steam_pc.py / scraper/games.py
- config/library.json
- data/*.json

新增设置：
1. 布局
   - 整体显示大小 90–120%
   - 页面左右留白
   - 桌面侧栏宽度
   - 紧凑 / 标准 / 舒适预设
   - 游戏桌面每行 2/3/4/5/自动
   - sticky topbar
   - 减少动画
   - 隐藏背景网格/光晕

2. 主题图
   - 本地上传（自动压缩）
   - 图片 URL
   - 开关 / 移除
   - X/Y 位置滑杆
   - 预览图直接拖动调整焦点
   - 透明度
   - 模糊
   - 界面遮罩
   - cover / contain
   - 顶部 / 居中 / 偏左 / 偏右 / 底部快捷位置
   所有外观设置只保存在浏览器 localStorage，不写入 GitHub。

3. UX
   - 记住主 Tab
   - 记住游戏 / 音乐子 Tab
   - / 聚焦搜索
   - Esc 清空搜索
   - 一键恢复默认

同时包含 v8.1：
- 游戏卡片字号整体提升
- Google Play “アイコン画像”标题显示清理
- game_enrich.py datetime.utcnow warning 修复

这次只要部署前端即可，不需要重新抓取。
建议 commit：
feat: add customizable UI settings and theme background
不要加 [refresh]。
