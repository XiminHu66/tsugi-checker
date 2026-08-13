Tsugi v6 · 每日新游戏追踪

新增“游戏追踪”Tab：
- 手游：App Store 日本新着游戏 + Google Play 日本新規リリース
- PC：Steam Recently Released + Famitsu 日本发行日历
- 主机：Famitsu 日本发行日历（Switch/Switch 2、PS5/PS4、Xbox Series/Xbox One）

每日抓取逻辑：
- 仍沿用现有 16:00 UTC 的每日 workflow（PDT 09:00 / PST 08:00）。
- 明确有发行日期的数据按日本时间当天标记 TODAY。
- App Store / Google Play 对不提供精确发行日的条目使用 game-state.json 记录首次发现日；首次建立基线不会把整页误报为 TODAY，之后新出现条目才标记 TODAY。
- 普通 push 仍只部署；schedule、手动 Run workflow 或 commit message 含 [refresh] 时才抓取。

新增文件：
- scraper/games.py
- data/game-releases.json
- data/game-state.json

修改文件：
- index.html
- app.js
- v5.css
- config/content.json
- scraper/main.py
- .github/workflows/update-feed.yml

推荐这次上传后的 commit message：
feat: add daily game release tracker [refresh]

这样会立即建立游戏数据基线并部署。
