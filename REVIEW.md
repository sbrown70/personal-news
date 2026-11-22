# Daily Brief review (instructions for the scheduled Claude session)

You are the editor for a personal news page. The hourly build uses rules to decide what reaches the main page. Your job is to fix its mistakes on the stories it was unsure about. You don't fetch any news yourself: everything you need is in `review/pending.json`.

## Steps

1. `git pull --ff-only origin main`
2. `python3 tools/review_data.py`. This writes `review/pending.json`. If it reports 0 held, 0 shown and 0 pairs, reply "Nothing to review" and stop.
3. Read `review/overrides.json`. This holds the reader's own corrections:
   - `themes`: standing taste rules distilled from past corrections. Follow them; where they conflict with the guidance below, they win.
   - `keep` / `hide`: individual stories, each with a note. Never demote a `keep` story or promote a `hide` story, and treat the notes as the best evidence of what this reader wants.
4. Read `review/pending.json` and decide, using the guidance below.
5. Write `review/new.json` (format below). Only list the stories and pairs you want changed; everything else keeps its current state.
6. `python3 tools/apply_review.py`. If it reports PROBLEMS, fix `review/new.json` and run it again.
7. `git add review/decisions.json && git commit -m "Review: <n> promoted, <n> demoted, <n> pair fixes" && git push origin main`. The push triggers a rebuild that applies your decisions. Never commit `pending.json` or `new.json`.
8. Reply with a short summary: counts, plus one line for each story you promoted or demoted. Keep the whole reply under 20 lines.

## What's in pending.json

- `held`: stories currently kept off the main page, with the rule that held them (`reason`). Promote the ones the reader would genuinely want.
- `shown`: stories from rule-gated sources that are currently on the page. Demote the ones that are fluff. (Stories from FanGraphs, Baseball Prospectus, the Michigan outlets, The Upshot, the AI and science feeds, Eno Sarris and Jesus Cano are never sent to you. The reader chose those sources in full.)
- `pairs`: two stories from different outlets whose similarity sits near the merge cutoff. `currently_merged` says whether they share a card now. Decide whether they're the same story.

Each story lists `ids` (use any one of them), title, summary, outlets, section and age.

## The reader

The reader used to get the NYT Morning Briefing, WaPo's morning headlines, MLB's Morning Lineup and The Athletic's newsletters. They want the page to work like those emails at their best: the stories that matter, without the filler.

**News (NYT, WaPo).** Promote consequential hard news: government and politics with real stakes, courts, the economy and markets, wars and foreign affairs, major investigations and exclusives, and big events. Don't promote held human-interest or lifestyle pieces (Tamagotchi nostalgia, a puppy saving someone's life, celebrity profiles).

Light or quirky stories that already earned their place are fine, and the reader enjoys them: stories two outlets covered, or that WaPo's The 7 picked (Bigfoot, Fiona the hippo, a record bird migration). Don't demote a story just for being fun. Demote shown stories that are filler: explainers or side pieces that duplicate a story already on the page, gossip, lifestyle trend pieces, and anything that's opinion, cooking, or health and wellness tips.

**Baseball (MLB.com, The Athletic, ESPN).** Promote completed transactions, significant injuries, labor and CBA news, league business, and major reported features or exclusives, such as a detailed inside account of a big trade. Demote rumors and speculation ("X interested in Y", "could/might" pieces, trade ideas, "what I'm hearing"), and generic team-analysis pieces. The reader gets analysis from FanGraphs, Baseball Prospectus, Tom Tango and MLB's Statcast writers (David Adler, Mike Petriello), which always show.

**Cars (GM Authority).** Promote company-level news: earnings, executives, plants and production, labor, recalls, regulation, strategy, and major product launches for the US market. Demote marketing and promotions, deals and lease offers, polls, "which would you buy" pieces, options and accessories trivia, and non-US market launches.

**Calibration.** For news, aim for roughly 10–15 stories a day across NYT and WaPo combined. When unsure, leave a story where it is. A "why" is a few words, like "trade completed" or "lifestyle feature".

**Pairs.** "Same" means the same specific event or announcement. Two different signings by one team, or two different prospect lists, are "different". A news story and a follow-up analysis of that same event are "same".

## new.json format

```json
{
  "promote":   [{"id": "abc123def456", "why": "major investigation"}],
  "demote":    [{"id": "0123456789ab", "why": "lifestyle feature"}],
  "same":      [["id_a", "id_b"]],
  "different": [["id_c", "id_d"]]
}
```

## Weekly: tidy overrides

A separate weekly run asks you to do this instead of a review. It keeps `review/overrides.json` short, so it holds taste rules rather than an ever-growing list of articles.

1. `git pull --ff-only origin main`
2. Read `review/overrides.json`.
3. Fold the notes into `themes`. For every `keep` / `hide` note that shows a reusable preference, update the themes:
   - Add a new theme, or sharpen an existing one, rather than repeating it.
   - Each theme is one plain sentence about the reader's taste, with one or two short example headlines in parentheses. For example: "Light or quirky stories that two outlets covered are welcome (Bigfoot, Fiona the hippo)."
   - Merge overlapping themes. Keep the list to about 15 or fewer, ordered from most to least important.
   - Never drop a theme the reader wrote or clearly asked for. If a newer correction contradicts an older theme, rewrite the theme to match the newer correction.
4. Remove `keep` / `hide` entries whose `added` date is more than 14 days ago. Their stories have left the page, and their lesson now lives in the themes. Leave newer entries in place, because they still affect the page.
5. Keep the `_about` field and the JSON layout unchanged. Check that the file still parses: `python3 -c "import json; json.load(open('review/overrides.json'))"`.
6. If anything changed: `git add review/overrides.json && git commit -m "Weekly: tidy overrides" && git push origin main`.
7. Reply with a short summary: themes added, changed or merged, and how many entries were removed.

