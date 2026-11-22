# Daily Brief

A personal news page that combines my RSS feeds and newsletter sources into one list. When several outlets cover the same story, it shows **one card with a link to each outlet's version**.

It is rebuilt every hour by GitHub Actions and published with GitHub Pages. It uses only public RSS feeds, so there are no logins, passwords, API keys or secrets anywhere. If a link goes to a paywalled site, you log in on that site as usual.

## How it works

1. `build.py` downloads every feed in `sources.yaml`.
2. For the feeds that replace the NYT and WaPo morning emails, it drops opinion, cooking and wellness stories (rules in `sources.yaml` under `filters`).
3. It decides what reaches the main page (details below), holding back rumors, clickbait, and minor stories only one outlet ran.
4. It compares stories using a small open-source sentence-similarity model ([all-MiniLM-L6-v2](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2), downloaded publicly with no account). Stories from different outlets that say the same thing, within 48 hours of each other, are merged into one card.
5. It writes a static page to `site/` and GitHub Pages publishes it.

Stories stay on the page for 72 hours. Each build reads the previously published `items.json`, so a story doesn't disappear when it drops out of a feed.

## What makes the main page

The NYT, WaPo, MLB.com, The Athletic, ESPN and GM Authority feeds publish far more than the curated emails did, so they are "gated". A story from one of them shows if:

- **two or more outlets covered it**, or
- it has an **importance signal**:
  - **NYT front page**: in the top 6 of NYT's home-page feed, which is in editors' placement order. This is how exclusives get through: a big scoop leads the home page.
  - **WaPo The 7**: the URL is part of WaPo's morning briefing.
  - **Scoop or feature language**: "exclusive", "documents show", "Sources:", "Inside the…", "behind the scenes", and similar.
  - **Allowed bylines**: David Adler, Mike Petriello and Tom Tango on MLB.com.
  - **Company-level keywords** for GM Authority: earnings, recalls, plants, UAW, executives, regulation.

Rumor and speculation headlines (MLB.com, The Athletic, ESPN) and clickbait or marketing headlines (GM Authority) are held back regardless.

Eno Sarris and Jesus Cano (Braves beat) come from their own author feeds and always show. Everything else, like FanGraphs, Michigan outlets, The Upshot and the car sites, isn't gated.

Nothing is thrown away: held stories are listed on the **Held back** tab with the reason. All rules live in `sources.yaml` (`gate`, `rumor_rules`, `drop_titles`, `pass_authors`, `pass_keywords`, and the shared `selection` patterns).

## Claude review

Three times a day (5:43 AM, 10:43 AM and 6:43 PM Eastern, and on request), a scheduled Claude Code session running Sonnet acts as editor for the stories the rules were unsure about. It runs on the Claude plan, with no API key. It:

- **promotes** important stories the rules held back,
- **demotes** fluff that slipped through (even when two outlets covered it),
- **fixes merges** for story pairs near the similarity cutoff.

It reads what to review from the build log (`tools/review_data.py`), records verdicts in `review/decisions.json` (`tools/apply_review.py`) and pushes, which rebuilds the page. Promoted cards carry a "Claude pick" label; demoted ones show on Held back with Claude's reason. It never touches ungated sources or allowed bylines. Its instructions, including what counts as important, are in `REVIEW.md`: edit that file to change its judgment.

Your corrections live in `review/overrides.json`: `keep` / `hide` for individual stories (`python3 tools/override.py keep|hide <id> "note"`), and `themes`, the standing taste rules the reviewer follows. Every Sunday evening, the same session folds new notes into themes and removes story entries older than 14 days, so the file stays short. The schedule and the reviewer session are in claude.ai under scheduled tasks and sessions.

## The page

- **Top Stories**: from the last 36 hours, stories covered by 2 or more outlets or flagged as NYT front page, WaPo The 7, a scoop or a feature. Biggest first.
- **Everything** and one tab per section (News, Baseball, Cars, Policy & Ideas, Science, AI).
- Opening any link marks the whole story as read. **Hide read** gives you an inbox-zero view. A **New** badge marks stories that appeared since your last visit.
- **Held back** tab: stories kept off the main page and why.
- **Feeds** tab: which feeds worked on the last run, and every story that was filtered out, so you can check the filters aren't too aggressive.

Read state is kept in your browser's local storage, so it is per device.

## Where the newsletters went

The daily emails aren't public, so each one is replaced by the public feed that carries the same stories. (Jason Furman's Econvitals is left out on purpose: it's a standalone dashboard, best read on its own at econvitals.org.)

| Email | Replaced by |
|---|---|
| NYT Morning Briefing | NYT Home Page, U.S., Politics and Business feeds (filtered) |
| WaPo morning headlines | WaPo National, Politics, World and Business feeds (filtered) |
| MLB Morning Lineup | MLB.com news feed |
| The Athletic Pulse / Daily / Weekly | The Athletic MLB feed |

## Changing things

Everything is in `sources.yaml`:

- **Add a feed**: copy one of the entries. To bring over everything from Feedly, export OPML (Feedly → Organize → ⋯ → Export OPML) and add the `xmlUrl` values.
- **Filters**: edit `filters`. They only apply to sources marked `filter: true`.
- **Too much or too little merging**: change `similarity_threshold` (default 0.70). Raise it if unrelated stories get merged; lower it if duplicates slip through. Each Actions run logs the story pairs near the threshold so you can see what it's deciding.

Push to `main` and the page rebuilds. You can also run it by hand: Actions → Build news page → Run workflow.

## Running locally

```bash
pip install -r requirements.txt
python build.py            # writes site/index.html
```

## Notes

- GitHub Pages sites on free accounts are public. The page only contains public headlines and links, and has a `noindex` tag so search engines skip it.
- GitHub turns off scheduled workflows after 60 days with no repo activity. The workflow re-enables itself on each run to stop that.
