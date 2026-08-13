Tsugi v7 — music weekly-new + game release timeline

覆盖仓库：
- index.html
- app.js
- v5.css
- README.md
- config/content.json
- scraper/music.py
- scraper/games.py

不会覆盖：
- config/library.json
- data/feed.json / state.json / site-updates.json / acg-news.json
- data/music.json / data/game-releases.json / data/game-state.json
- .github/workflows/update-feed.yml

本版变化：
1. Billboard JAPAN 周榜增加 YouTube Music 链接。
2. 原“新发行”改为“近一周新曲”：优先 Apple Music Japan Best New Songs，失败自动回退 Billboard 本周新进榜。
3. 游戏页改为过去 7 天 → 今天 → 未来 90 天发售时间线。
4. PC 只抓 Steam Popular New Releases / Popular Upcoming，不再抓全部 Recently Released。
5. 主机通过 Famitsu 多月发行日历覆盖过去 7 天与未来 90 天。
6. 手游保留最近 7 天 App Store / Google Play 新发现；商店无可靠未来日期，因此不伪造未来手游日历。
7. 保留 v6.2 更新流卡片布局修复和网页“刷新订阅源”按钮。

上传后建议 commit：
feat: improve music and game timelines [refresh]

[refresh] 会让这次提交立即重新生成 music.json / game-releases.json。
日常 09:17 America/Los_Angeles 定时任务保持不变。
