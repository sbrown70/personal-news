# Daily Brief

A personal news page that combines my RSS feeds and newsletter sources into one list. When several outlets cover the same story, it shows **one card with a link to each outlet's version**.

It is rebuilt every hour by GitHub Actions and published with GitHub Pages. It uses only public RSS feeds, so there are no logins, passwords, API keys or secrets anywhere. If a link goes to a paywalled site, you log in on that site as usual.

## How it works

1. `build.py` downloads every feed in `sources.yaml`.
2. For the feeds that replace the NYT and WaPo morning emails, it drops opinion, cooking and wellness stories (rules in `sources.yaml` under `filters`).
3. It compares stories using a small open-source sentence-similarity model ([all-MiniLM-L6-v2](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2), downloaded publicly with no account). Stories from different outlets that say the same thing, within 48 hours of each other, are merged into one card.
4. It writes a static page to `site/` and GitHub Pages publishes it.

Stories stay on the page for 72 hours. Each build reads the previously published `items.json`, so a story doesn't disappear when it drops out of a feed.

## The page

- **Top Stories**: stories covered by 2 or more outlets in the last 36 hours, biggest first.
- **Everything** and one tab per section (News, Baseball, Cars, Policy & Ideas, Science, AI).
- Opening any link marks the whole story as read. **Hide read** gives you an inbox-zero view. A **New** badge marks stories that appeared since your last visit.
- **Feeds** tab: which feeds worked on the last run, and every story that was filtered out, so you can check the filters aren't too aggressive.

Read state is kept in your browser's local storage, so it is per device.

## Where the newsletters went

The daily emails aren't public, so each one is replaced by the public feed that carries the same stories:

| Email | Replaced by |
|---|---|
| NYT Morning Briefing | NYT Home Page, U.S., Politics and Business feeds (filtered) |
| WaPo morning headlines | WaPo National, Politics, World and Business feeds (filtered) |
| MLB Morning Lineup | MLB.com news feed |
| The Athletic Pulse / Daily / Weekly | The Athletic MLB feed |
| Econvitals (Jason Furman) | Econvitals site feed (auto-discovered) |

## Changing things

Everything is in `sources.yaml`:

- **Add a feed**: copy one of the entries. To bring over everything from Feedly, export OPML (Feedly → Organize → ⋯ → Export OPML) and add the `xmlUrl` values.
- **Filters**: edit `filters`. They only apply to sources marked `filter: true`.
- **Too much or too little merging**: change `similarity_threshold` (default 0.62). Raise it if unrelated stories get merged; lower it if duplicates slip through. Each Actions run logs the story pairs near the threshold so you can see what it's deciding.

Push to `main` and the page rebuilds. You can also run it by hand: Actions → Build news page → Run workflow.

## Running locally

```bash
pip install -r requirements.txt
python build.py            # writes site/index.html
```

## Notes

- GitHub Pages sites on free accounts are public. The page only contains public headlines and links, and has a `noindex` tag so search engines skip it.
- GitHub turns off scheduled workflows after 60 days with no repo activity. The workflow re-enables itself on each run to stop that.
