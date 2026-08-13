Tsugi v5 patch
==============

新增：
1. 更新流卡片一键加入“我的书架”（LocalStorage 本机订阅）。
2. 我的书架合并显示本机订阅 + config/library.json 云端订阅。
3. 本机订阅在每日 site-updates.json 刷新后自动比较最新章节/话数，并生成本机更新记录。
4. 新增“音乐追踪”：Billboard JAPAN Hot 100 周榜、日本新发行、艺人关注与最近新曲检查。
5. 音乐发现数据写入 data/music.json；艺人关注存浏览器 LocalStorage。
6. 沿用 v4 workflow：普通 push 只 deploy；schedule / workflow_dispatch / commit message 含 [refresh] 时执行完整抓取。

上传覆盖这些文件/路径：
- index.html
- app.js
- v5.css (new)
- config/content.json
- scraper/main.py
- scraper/music.py (new)
- data/music.json (new)
- .github/workflows/update-feed.yml

不会覆盖：
- config/library.json
- data/state.json
- data/feed.json
- data/feed.xml

首次上传建议 commit message：
feat: add shelf actions and music tracking [refresh]

这样会立即跑一次完整抓取并生成 data/music.json。
