---
name: update
description: Refresh the Daily Brief now. Rebuild the page with fresh feeds, then run the Claude review (REVIEW.md) on it. Use when the reader says "update", "refresh", "do an update now", "run the review" or similar.
---

# Update the Daily Brief now

The reader wants the page current: the latest news, with the editor pass applied. Do both steps; don't stop to ask what "update" means.

1. **Sync.** `git pull --ff-only origin main`

2. **Rebuild with fresh feeds.** News sites are blocked from cloud sessions, so the build has to run on GitHub Actions:
   ```bash
   gh workflow run build.yml -R sbrown70/personal-news --ref main
   ```
   Wait a few seconds, find the new run with `gh run list -R sbrown70/personal-news --workflow build.yml --limit 1 --json databaseId,status`, then `gh run watch <id> -R sbrown70/personal-news --exit-status`. If a build was already running, yours queues behind it; that's fine. If the build fails, show the failing lines (`gh run view <id> -R sbrown70/personal-news --log-failed`) and stop.

3. **Review.** Follow REVIEW.md, "Steps" section, from step 2 on (you already pulled). Read `review/overrides.json` (themes first) before deciding. Push with `git push origin HEAD:main`. Your branch name doesn't matter, because the site builds from `main`. Pushing starts another short rebuild that applies your decisions.
   - If the review finds nothing to change, there's nothing to commit. The page is already fresh from step 2.

4. **Reply briefly:** "Page rebuilt at <time>", then the review summary: counts, and one line per promoted or demoted story with the reason. Mention that the site updates a minute or two after the push.
