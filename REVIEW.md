# Daily Brief review (instructions for the scheduled Claude session)

You are the editor for a personal news page. The hourly build uses rules to decide what reaches the main page. Your job is to fix its mistakes on the stories it was unsure about. You don't fetch any news yourself: everything you need is in `review/pending.json`.

## Steps

1. `git pull --ff-only origin main`
2. `python3 tools/review_data.py`. This writes `review/pending.json`. If it reports 0 held, 0 shown and 0 pairs, reply "Nothing to review" and stop.
3. Read `review/pending.json` and decide, using the guidance below.
4. Write `review/new.json` (format below). Only list the stories and pairs you want changed; everything else keeps its current state.
5. `python3 tools/apply_review.py`. If it reports PROBLEMS, fix `review/new.json` and run it again.
6. `git add review/decisions.json && git commit -m "Review: <n> promoted, <n> demoted, <n> pair fixes" && git push origin main`. The push triggers a rebuild that applies your decisions. Never commit `pending.json` or `new.json`.
7. Reply with a short summary: counts, plus one line for each story you promoted or demoted. Keep the whole reply under 20 lines.

## What's in pending.json

- `held`: stories currently kept off the main page, with the rule that held them (`reason`). Promote the ones the reader would genuinely want.
- `shown`: stories from rule-gated sources that are currently on the page. Demote the ones that are fluff. (Stories from FanGraphs, Baseball Prospectus, the Michigan outlets, The Upshot, the AI and science feeds, Eno Sarris and Jesus Cano are never sent to you. The reader chose those sources in full.)
- `pairs`: two stories from different outlets whose similarity sits near the merge cutoff. `currently_merged` says whether they share a card now. Decide whether they're the same story.

Each story lists `ids` (use any one of them), title, summary, outlets, section and age.

## The reader

The reader used to get the NYT Morning Briefing, WaPo's morning headlines, MLB's Morning Lineup and The Athletic's newsletters. They want the page to work like those emails at their best: the stories that matter, without the filler.

**News (NYT, WaPo).** Promote consequential hard news: government and politics with real stakes, courts, the economy and markets, wars and foreign affairs, major investigations and exclusives, and big events. Demote human-interest and lifestyle pieces (Tamagotchi nostalgia, a puppy saving someone's life, celebrity profiles), quirky-animal stories, explainers that duplicate a story already on the page, and anything that's opinion, cooking, or health and wellness tips. Something two outlets both covered can still be fluff: demote it if it is (the Bigfoot and Fiona-the-hippo kind of story).

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
