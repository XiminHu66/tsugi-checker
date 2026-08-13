# Tsugi — ACG 追踪中心

Tsugi 是部署在 **GitHub Pages** 的静态 ACG dashboard。GitHub Actions 每日抓取公开数据并缓存为 JSON；浏览器负责展示、本机订阅和界面设置。

## 当前功能

- **更新流**：漫画柜、BiliNovel / Linovelib、CopyManga 等公开最新更新。
- **我的书架**：本机 LocalStorage 订阅 + `config/library.json` 云端深度追踪。
- **音乐追踪**：Billboard JAPAN Hot 100、近一周新曲、艺人关注、YouTube Music 入口。
- **游戏追踪**：
  - 手游：日本 App Store / Google Play + 国内 TapTap，经过数量与热度筛选。
  - PC：`scraper/steam_pc.py` 抓 Steam 热门新作 / 热门待发，`game_enrich.py` 补中文名、开发/发行商、类型与讨论度。
  - 主机：Famitsu 日本发售时间线。
- **ACG 新闻**：仅中文 / 繁中来源。
- **界面设置**：字号/缩放、密度、列数、主题图位置/透明度/模糊、明暗模式等，保存在浏览器本地。

## 目录

```text
index.html
styles.css
v5.css
app.js
games.css
games.js
ui-settings.css
ui-settings.js

config/
  content.json
  library.json
  library.example.json

data/
  feed.json
  feed.xml
  state.json
  site-updates.json
  acg-news.json
  music.json
  game-releases.json
  game-state.json

scraper/
  main.py
  sources.py
  aggregators.py
  music.py
  games.py
  steam_pc.py
  game_enrich.py

.github/workflows/update-feed.yml
```

## 调度

`.github/workflows/update-feed.yml`：

- 每天 **09:17 America/Los_Angeles** 完整刷新；
- Actions 页面手动 `Run workflow` 完整刷新；
- commit message 含 `[refresh]` 时完整刷新；
- 普通 push 只部署，不重复爬取。

PC 的稳定抓取链是：

```text
main.py
→ steam_pc.py
→ game_enrich.py
→ data/game-releases.json
```

`config/content.json` 不再保留已失效的 `featuredcategories` Steam legacy source。

## 书架

云端深度追踪编辑 `config/library.json`：

```json
{
  "items": [
    {
      "id": "my-title",
      "type": "manga",
      "source": "manhuagui",
      "title": "作品名",
      "url": "https://作品详情页",
      "enabled": true
    }
  ]
}
```

第一次成功抓取只建立 baseline；之后章节 / 话数变化才产生个人更新记录。

## 本地预览

```bash
python -m http.server 8000
```

然后打开 `http://localhost:8000`。

## 部署

GitHub → **Settings → Pages → Source → GitHub Actions**。

前端资源现在直接写在 `index.html` 中，不再由 workflow 临时修改 HTML，因此仓库源码与线上 Pages 结构一致。
