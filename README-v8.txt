Tsugi v8 游戏信息增强补丁

覆盖/新增：
- .github/workflows/update-feed.yml
- scraper/game_enrich.py
- game-v8.js
- game-v8.css

保留现有：
- scraper/steam_pc.py（v7.4 已跑通的 PC 抓取链）
- scraper/games.py
- app.js / v5.css / index.html
- 所有 data/*.json 与 config/library.json

功能：
1. 手游：
   - TapTap 新品榜 TOP3 / TOP8 高亮
   - TapTap 高评分高亮
   - App Store 日本通过公开 Lookup 补评分数；评分量较高时标记高讨论/热门
   - Google Play 没有可靠公开讨论量指标时不伪造热度

2. PC：
   - Steam 中文商店名优先；没有中文名时回退英文
   - 补开发商、发行商、中文类型标签
   - 已发行游戏读取 Steam 评价总量/好评率作为讨论度 indicator
   - Popular Upcoming 作为“热门待发” indicator
   - 知名发行商单独高亮
   - 同一天按 heat_score 优先

3. 排序：
   - 今日发行
   - 未来 30 天
   - 31–90 天（默认折叠）
   - 过去 7 天（默认折叠 + 低亮）

建议本次 commit：
feat: enrich game metadata and prioritize PC timeline [refresh]

必须运行一次完整刷新才能生成开发商/发行商/中文名/热度字段。
