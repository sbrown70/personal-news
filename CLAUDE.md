# Daily Brief: personal news page

A personal news page for one reader. It combines their RSS feeds (formerly in Feedly) with public replacements for their morning newsletters (NYT Morning Briefing, WaPo headlines, MLB Morning Lineup, The Athletic). Duplicate coverage merges into one card with a link per outlet; rumor, clickbait and minor single-outlet stories are held back. Live at https://sbrown70.github.io/personal-news/.

**No logins, ever.** Everything uses public feeds; the reader logs in on the news sites themselves when they click through. Don't add anything that needs credentials, API keys or GitHub secrets without asking.

## How it works

| Piece | What it does |
|---|---|
| `.github/workflows/build.yml` | Hourly (and on every push to `main`): runs `build.py`, publishes `site/` to GitHub Pages. |
| `build.py` | Fetches feeds → filters (opinion, cooking, wellness) → holds back rumors and clickbait → merges duplicates (sentence embeddings + TF-IDF) → gates single-outlet stories → applies the Claude review → writes `site/index.html` + `site/items.json`. |
| `sources.yaml` | All feeds and all rules: sections, `gate`, `rumor_rules`, `drop_titles`, `pass_authors`, `pass_keywords`, shared `selection` patterns, merge threshold. Comments explain each field. |
| `templates/index.html` | The page. Tabs: Top Stories, Read later, Everything, sections, Promoted, Demoted, Held back, Feeds. Read state and Read later (a saved copy of each story, kept until removed) live in the browser's local storage. |
| `REVIEW.md` | Instructions for the Claude review (the editor pass) and the weekly overrides tidy. |
| `review/decisions.json` | Claude's verdicts (promote, demote, pair merges, what's been reviewed). Written only by `tools/apply_review.py`. |
| `review/overrides.json` | The reader's own corrections: `themes` (standing taste rules), `keep` / `hide` (story ids). The reader's choices beat Claude's. |
| `tools/review_data.py` | Pulls what the latest build wants reviewed (the `REVIEWDATA` line in its log) into `review/pending.json`. |
| `tools/apply_review.py` | Merges `review/new.json` verdicts into `review/decisions.json`. |
| `tools/find_story.py` | Finds a story's id by headline words (from the `CARDINDEX` line in the latest build log). |
| `tools/override.py` | Adds a `keep` / `hide` override. |
| `tools/probe.py` + `.github/workflows/debug.yml` | Debugging: probe URLs from GitHub's servers, or dump stories and vectors for tuning. |
| `tests/fixture_build.py` | Offline smoke test against made-up feeds. |

## Working in a cloud session: what you can and can't reach

- **News sites are blocked from cloud sessions**, and so are `*.github.io` and Hugging Face. Don't try to fetch feeds or the published page from here.
- **GitHub works through `gh`**, and GitHub Actions runners have open internet. To test anything network-related, run it on Actions and read the log:
  - Rebuild now: `gh workflow run build.yml -R sbrown70/personal-news --ref main`, then `gh run watch <id>`.
  - Read a run's log: `gh run view <id> -R sbrown70/personal-news --log` (or `gh api repos/sbrown70/personal-news/actions/jobs/<job id>/logs`).
  - Probe a URL from GitHub's servers: `gh workflow run debug.yml -R sbrown70/personal-news --ref main -f urls="<url> <url>"`.
  - Build artifacts **can't** be downloaded here (their storage host is blocked); everything you need is printed to the log.
- **Local test without network:** `python3 tests/fixture_build.py`.

## Git

The site builds only from `main`. Your session may start on its own `claude/...` branch: that's fine, but **push with `git push origin HEAD:main`** (after `git pull --ff-only origin main`), or the change never reaches the site. If that push is refused, push your branch and tell the reader it needs merging. Never commit `review/pending.json` or `review/new.json`.

## Common requests

- **"Update", "refresh", "do an update now", "run the review"**: use the `/update` skill. Rebuild with fresh feeds, then do the Claude review (REVIEW.md), so the page has the latest news and the reviewer's pass on it.
- **"Keep / show / hide / un-demote <story>"**: use the `/override` skill.
- **Change what the reviewer considers important**: edit `REVIEW.md` (general guidance) or the `themes` in `review/overrides.json` (the reader's taste rules, which win).
- **Add or remove a source**: edit `sources.yaml`. Probe a new feed URL with the debug workflow first, then push and check the build log line `[ok ] <name>: N kept`. Sites that block GitHub (ESPN, Automotive News) can go through a Google News search feed (`google_news: true`). Slow-posting sources need `retention_hours`.
- **Too much or too little merging**: `similarity_threshold` / `lexical_weight` in `sources.yaml` (tuned on ~350 labelled pairs; each build logs pairs near the cutoff).
- **A source is too noisy**: give it `gate: true`, plus `rumor_rules`, `drop_titles` or `pass_keywords` as needed.

## Scheduled work

- **Daily Brief review**: 5:43 AM, 10:43 AM and 6:43 PM Eastern. A scheduled task wakes the dedicated "Daily Brief reviewer" session (Sonnet), which follows REVIEW.md.
- **Daily Brief weekly overrides tidy**: Sundays at 8:21 PM Eastern, same session. It folds `keep` / `hide` notes into `themes` and removes entries older than 14 days.
- Both run on the reader's Claude plan, not an API key. The reader can pause them or **Run now** under scheduled tasks in claude.ai.

## Reader's preferences, in brief

The reader wants a morning-briefing page: consequential news, without filler. They're fine with light or quirky stories that earned their place (covered by two outlets, or in WaPo's The 7). Baseball: completed transactions, injuries, labor, and major features or exclusives yes; rumors and speculation no. Their analysis comes from FanGraphs, Baseball Prospectus, Tom Tango, the Statcast writers (David Adler, Mike Petriello), Eno Sarris and Jesus Cano (Braves beat). GM Authority: company-level news yes; marketing, deals and non-US launches no. They skip Econvitals on purpose (it's a standalone dashboard). See REVIEW.md and `review/overrides.json` for the details.
