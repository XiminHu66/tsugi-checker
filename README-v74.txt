Tsugi v7.4 PC hotfix

Why:
- v7.3 mobile feeds work, but Steam PC remains 0 raw items on GitHub Actions.
- The previous code depended on Steam storefront JSON that is not returning usable PC candidates on the runner.

What changes:
1. Adds scraper/steam_pc.py.
   - Opens Steam Popular New Releases and Popular Upcoming with Playwright.
   - Waits for actual search_result_row elements.
   - Falls back to Steam's same-origin search/results endpoint from inside the browser session.
   - Keeps only games with exact dates inside the existing -7/+90 day timeline window.
   - Replaces only data/game-releases.json -> items.pc and the two Steam source statuses.
2. Updates workflow to run steam_pc.py immediately after scraper/main.py.
3. Does not change the daily 09:17 America/Los_Angeles schedule.

Upload both paths preserving directories, then run workflow_dispatch once (or use a commit message containing [refresh]).
Expected log lines:
STEAMPC steam_popular_new: ...
STEAMPC steam_popular_upcoming: ...
STEAMPC final PC timeline: ...
