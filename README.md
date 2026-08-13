# Tsugi — ACG 追踪中心

Tsugi 是一个部署在 **GitHub Pages** 的静态 ACG dashboard。数据由 **GitHub Actions** 定时抓取并缓存为 JSON，浏览器只负责展示和本机订阅状态。

> 只抓公开页面中的标题、封面、章节/话数、发行信息和原站链接；不镜像正文或漫画内容，不处理登录、付费、验证码或反爬绕过。

## 功能

- **更新流**：漫画柜、BiliNovel / Linovelib、CopyManga 等公开最新更新。
- **我的书架**：
  - 从更新流一键加入的“本机追踪”保存在 LocalStorage；每天新的站点更新到达时自动比对。
  - `config/library.json` 中的“云端追踪”由 GitHub Actions 主动打开作品页检查，可靠性更高。
- **音乐追踪**：Billboard JAPAN Hot 100、Apple 日本新发行，以及浏览器本机保存的艺人新曲关注。
- **游戏追踪**：手游、PC、主机每日新发行 / 新发现。
- **ACG 新闻**：只启用中文或繁体中文来源。
- **明暗主题**：浏览器本地保存偏好。

## 关键文件

- `index.html` / `styles.css` / `v5.css` / `app.js`：前端
- `config/content.json`：公开更新流、中文新闻、音乐、游戏来源配置
- `config/library.json`：云端深度追踪书架
- `scraper/main.py`：总抓取入口
- `scraper/sources.py`：单作品章节解析
- `scraper/aggregators.py`：站点更新流与 RSS 聚合
- `scraper/music.py`：日本音乐榜 / 新发行
- `scraper/games.py`：手游 / PC / 主机新发行
- `data/*.json`：GitHub Pages 读取的缓存数据

## 每日计划

工作流位于 `.github/workflows/update-feed.yml`。

默认每天 **09:17 America/Los_Angeles** 执行一次完整抓取，自动处理 PDT / PST。特意避开整点，降低 GitHub Actions 高负载导致延迟的概率。

普通 push 只重新部署静态站点；以下情况会完整抓取：

- 每日 schedule
- Actions 页面手动 `Run workflow`
- commit message 包含 `[refresh]`

## 添加云端书架作品

编辑 `config/library.json`：

```json
{
  "items": [
    {
      "id": "my-manga-001",
      "type": "manga",
      "source": "manhuagui",
      "title": "作品名",
      "url": "https://作品详情页",
      "enabled": true
    }
  ]
}
```

支持 `linovelib` / `bilinovel`、`manhuagui`、`copymanga`、`wenku8`、`generic`。

第一次成功抓取只建立 baseline；以后最新章节、URL 或章节数量发生变化才生成个人更新记录。

## 部署

GitHub 仓库 → **Settings → Pages → Build and deployment → Source → GitHub Actions**。

第一次或修改抓取器后，建议在 Actions 手动运行一次 `Update feed & deploy Pages`。

## 本地预览

```bash
python -m http.server 8000
```

打开 `http://localhost:8000`。不要直接双击 `index.html`，否则浏览器可能阻止读取 JSON。

## 抓取失败说明

中文小说 / 漫画站经常调整 DOM 或限制机房 IP。Tsugi 会在公开访问范围内使用普通 requests 或普通 Playwright 浏览器降级，不做 stealth、验证码绕过或账号 Cookie 注入。单一来源失败不会阻止其他来源和 Pages 部署。
