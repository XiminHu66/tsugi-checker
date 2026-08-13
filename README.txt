Tsugi v7.1 game source hotfix

Fixes:
- Steam Popular New / Popular Upcoming: use Steam search/results response instead of the JS-heavy search shell, with Chromium fallback.
- App Store Japan: robust card-title parsing + Chromium fallback.
- Google Play Japan: switch to the dedicated new-releases-games collection + Chromium fallback.
- Source status now reports zero parsed items as unhealthy instead of silently green.

Upload/replace:
- scraper/games.py
- config/content.json

Recommended commit message:
fix: repair PC and mobile game sources [refresh]
