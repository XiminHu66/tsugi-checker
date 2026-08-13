Tsugi v6.2 — UI layout + manual source refresh hotfix

覆盖仓库根目录：
- index.html
- v5.css

本补丁不会修改：
- .github/workflows/update-feed.yml
- config/library.json
- data/*
- scraper/*

修复内容：
1. 重置 site-update-card 继承自旧版 styles.css 的两列 grid，修复更新流文字被压成竖排的问题。
2. 新增“刷新订阅源”按钮。
3. 原圆形刷新按钮仍只负责重新读取已经生成的 JSON。
4. 直接触发 GitHub Actions 时，首次会要求 fine-grained PAT（仅此 repo，Actions: Read and write）。Token 仅保存在 sessionStorage，关闭标签页后清除，不会写进仓库；留空则自动打开 GitHub Actions 页面手动 Run workflow。
5. workflow / 定时任务不变。

建议普通 commit 即可，例如：
fix: repair update cards and add manual refresh

不需要 [refresh]，因为这个补丁本身不需要立即重新抓源。
