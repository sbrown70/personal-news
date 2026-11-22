#!/usr/bin/env python3
"""Add a reader override: python3 tools/override.py keep|hide <story id> "note"

keep = show the story even if Claude demoted it or the rules held it back.
hide = keep it off the page even if Claude promoted it.
Story ids are shown on the Promoted / Demoted tabs. Commit and push afterwards.
"""
import datetime
import json
import sys
from pathlib import Path

PATH = Path(__file__).resolve().parent.parent / "review" / "overrides.json"


def main() -> None:
    if len(sys.argv) != 4 or sys.argv[1] not in ("keep", "hide"):
        sys.exit(__doc__)
    kind, sid, note = sys.argv[1:]
    data = json.loads(PATH.read_text())
    other = "hide" if kind == "keep" else "keep"
    data.get(other, {}).pop(sid, None)  # a story can't be both
    data.setdefault(kind, {})[sid] = {"note": note, "added": datetime.date.today().isoformat()}
    PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    print(f"{kind} {sid}: {note}")


if __name__ == "__main__":
    main()
