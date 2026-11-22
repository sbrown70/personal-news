---
name: override
description: Show or hide a specific story on the Daily Brief, overriding the rules or the Claude review, and teach the reviewer the reader's taste. Use when the reader says keep, show, un-demote, restore, hide, remove or "don't show me" about a story, or states a standing preference about what belongs on the page.
---

# Override a story

Reader overrides live in `review/overrides.json`. They beat both the rules and the Claude review, and the reviewer reads them, especially the notes and `themes`, to learn the reader's taste.

1. `git pull --ff-only origin main`

2. **Find the story's id:** `python3 tools/find_story.py <a few headline words>`. This searches every card in the latest build, shown and held.
   - Several matches: pick the obvious one, or ask the reader if it's genuinely unclear.
   - No match: the story has probably aged off the page (72 hours for news, 2 weeks for slow sections). Say so; no override is needed.

3. **Add the override:**
   ```bash
   python3 tools/override.py keep <id> "<note>"   # show it (un-demote, or rescue from Held back)
   python3 tools/override.py hide <id> "<note>"   # keep it off the page
   ```
   The note teaches the reviewer, so make it say why, in the reader's terms. For example: "Fiona the hippo: fun enough, covered by two outlets", not just "keep".

4. **Standing preferences.** If the reader states a general rule ("I don't care about X", "always show me Y"), also add it to `themes` in `review/overrides.json`: one plain sentence, with an example headline in parentheses. Keep the JSON valid and the `_about` field unchanged.

5. **Publish:**
   ```bash
   git add review/overrides.json && git commit -m "Override: <keep|hide> <short title>" && git push origin HEAD:main
   ```
   The push starts a rebuild; the change is live in about 2 minutes. If the push to `main` is refused, push your branch and tell the reader it needs merging.

6. **Confirm** in one or two lines: what changed, and that it shows on the Demoted tab (keep) or Promoted tab (hide) as the reader's override.
