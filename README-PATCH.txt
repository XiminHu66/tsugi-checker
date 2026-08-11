Tsugi v4 patch

覆盖到仓库根目录，保留目录结构：
- index.html
- app.js
- config/content.json
- scraper/main.py
- .github/workflows/update-feed.yml

不要覆盖 config/library.json、data/state.json、data/feed.json。

上传时建议 commit message 包含 [refresh]，例如：
feat: update Tsugi feeds [refresh]
这样这一轮 push 会立即抓取一次；之后普通 push 只部署，定时/手动运行才抓取。

定时抓取：每日 16:00 UTC（PDT 09:00 / PST 08:00）。
