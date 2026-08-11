# Tsugi — 小说 / 漫画固定追更器

一个适合直接部署到 **GitHub Pages** 的静态追更面板。界面参考 Mihon / Tachiyomi 的“书架 + 更新”结构，但把抓取放到 **GitHub Actions**：每天检查固定作品 URL，检测最新章节变化后生成 JSON 与 Atom 更新流。

> 默认只抓取公开页面中的作品元数据、章节名称和原站链接，不镜像正文/漫画图片；不处理登录、付费内容、验证码或反爬绕过。

## 目录

- `index.html` / `styles.css` / `app.js`：GitHub Pages 前端
- `config/library.json`：你的固定追更书架
- `scraper/main.py`：每日检查任务
- `scraper/sources.py`：来源解析与通用章节识别
- `data/feed.json`：网页读取的更新流
- `data/feed.xml`：可给 Feedly / Reeder / FreshRSS 使用的 Atom feed
- `data/state.json`：上一次章节状态，用来判断“是否有新章节”

## 1. 添加作品

复制 `config/library.example.json` 中的格式到 `config/library.json`。`id` 必须唯一。

```json
{
  "items": [
    {
      "id": "my-novel-001",
      "type": "novel",
      "source": "bilinovel",
      "title": "我的轻小说",
      "url": "https://目标网站/作品详情页",
      "enabled": true
    },
    {
      "id": "my-manga-001",
      "type": "manga",
      "source": "manhuagui",
      "title": "我的漫画",
      "url": "https://目标网站/作品详情页",
      "enabled": true
    }
  ]
}
```

支持的 `source`：

- `bilinovel` / `linovelib`
- `wenku8`
- `manhuagui`
- `copymanga`
- `generic`

### 可选字段

- `fetch_mode`: `auto`（默认）、`requests`、`browser`
  - `auto` 会先普通 HTTP 请求，失败时再用无头 Chromium 渲染页面。
- `chapter_selector`: 某站点章节链接的 CSS selector，例如 `.chapter-list a`。内置启发式识别不准时非常有用。
- `chapter_order`: `last`（默认）或 `first`。如果该站章节列表是“最新章节在最上方”，设置为 `first`。
- `delay`: 每本作品抓取后的暂停秒数，默认 `1.5`。

## 2. 第一次初始化

打开 GitHub 仓库 → **Actions** → `Update novel & manga feed` → `Run workflow`。

第一次成功抓取只会建立基线，不会把当前所有章节当作“新更新”。以后发现最新章节 / 章节数量变化时才会生成更新条目。

## 3. 开启 GitHub Pages

仓库 → **Settings → Pages**：

1. Source 选择 `Deploy from a branch`
2. Branch 选择 `main`（或你的默认分支）
3. Folder 选择 `/ (root)`
4. 保存

之后访问 `https://你的用户名.github.io/仓库名/`。

## 4. 每日更新与 RSS

工作流默认 `16:00 UTC` 每天运行一次，约等于西雅图夏令时 `09:00`、冬令时 `08:00`。GitHub Actions 的 cron 使用 UTC；可直接修改 `.github/workflows/update-feed.yml`。

Atom 地址：

```text
https://你的用户名.github.io/仓库名/data/feed.xml
```

## 5. 来源失败怎么办

不同中文小说/漫画站点经常修改 DOM、启用 Cloudflare、限制机房 IP 或要求 JS 渲染，因此没有任何“永远不坏”的纯静态抓取方案。这个项目采取几层降级：

1. HTTP 请求抓取
2. 普通 Playwright Chromium 渲染（不做 stealth / 验证码绕过）
3. 自动寻找“目录 / 章节”链接并再请求一次
4. 通用章节标题启发式
5. 最后允许你给单本作品指定 `chapter_selector`

如果 GitHub Actions IP 被源站完全拦截，建议把该作品改为你可合法访问的其他公开来源；不要把账号 Cookie、密码或付费站点凭证提交到公开仓库。

## 本地预览

不要直接双击 `index.html`（浏览器可能阻止读取 JSON）。在项目目录运行：

```bash
python -m http.server 8000
```

然后访问 `http://localhost:8000`。
