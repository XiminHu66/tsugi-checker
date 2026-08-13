Tsugi v7.3 cumulative patch
===========================

This patch INCLUDES BOTH:
- v7.2: mobile mojibake/image fixes, Steam PC source redesign, replacement Chinese news sources
- v7.3: mainland-China mobile tracking + mobile popularity/quantity filtering

Replace these files in the repository:
  scraper/games.py
  config/content.json

Recommended commit message:
  fix: improve filtered JP CN mobile and PC feeds [refresh]

Important: include [refresh] or manually run the workflow once after upload.

Mobile behavior after this patch:
- Japan recent: App Store JP + Google Play JP, capped to a small curated set
- China recent: TapTap 新品榜, top 8 by recent download heat
- China upcoming: TapTap 即将上线, only true 首发 entries, top 8
- Tests / test recruitment / version updates / pure pre-download events are excluded from China upcoming releases
- Current caps: JP recent 10, CN recent 8, CN upcoming 8

PC behavior inherited from v7.2:
- Steam front-page new_releases + coming_soon curated sets
- appdetails used to resolve actual release dates
- timeline window remains past 7 days + future 90 days

News replacements inherited from v7.2:
- GNN
- GCORES
- 游研社 direct feed
- GameLook direct feed
