#!/usr/bin/env python3
"""Find a story's id by words in its headline: python3 tools/find_story.py bigfoot hippo

Searches every card (shown and held back) in the latest successful build and
prints its ids, status, outlets and headline. Use the first id with
tools/override.py.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from review_data import latest_build_line  # noqa: E402


def main() -> None:
    words = [w.lower() for w in sys.argv[1:]]
    if not words:
        sys.exit(__doc__)
    run, rows = latest_build_line("CARDINDEX")
    hits = [r for r in rows if all(w in (r["title"] + " " + " ".join(r["outlets"])).lower() for w in words)]
    print(f"build {run['databaseId']} ({run['createdAt']}): {len(hits)} match(es)")
    for r in hits[:25]:
        print(f"  {r['ids'][0]}  {r['status']:5s}  {', '.join(r['outlets'])}  {r['title']}"
              + (f"  [{r['why']}]" if r["why"] else ""))


if __name__ == "__main__":
    main()
