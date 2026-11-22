#!/usr/bin/env python3
"""Merge the reviewer's verdicts (review/new.json) into review/decisions.json.

new.json format (every list optional):
  {
    "promote":   [{"id": "<any id of a held story>", "why": "short reason"}],
    "demote":    [{"id": "<any id of a shown story>", "why": "short reason"}],
    "same":      [["<id a>", "<id b>"]],   # pairs that ARE the same story
    "different": [["<id a>", "<id b>"]]    # pairs that are NOT
  }

Every story and pair in review/pending.json is marked reviewed, so it isn't
sent again; pairs you didn't list keep their current merge state. Verdicts
older than 14 days are pruned.
"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KEEP_DAYS = 14


def main() -> None:
    pending = json.loads((ROOT / "review" / "pending.json").read_text())
    new_path = ROOT / "review" / "new.json"
    new = json.loads(new_path.read_text()) if new_path.exists() else {}
    dec_path = ROOT / "review" / "decisions.json"
    dec = json.loads(dec_path.read_text()) if dec_path.exists() else {}
    for k in ("reviewed", "promote", "demote", "pairs"):
        dec.setdefault(k, {})
    now = time.time()

    held_ids = {i for c in pending["held"] for i in c["ids"]}
    shown_ids = {i for c in pending["shown"] for i in c["ids"]}
    pair_keys = {"|".join(sorted((p["a"], p["b"]))): p for p in pending["pairs"]}
    problems = []

    for kind, valid in (("promote", held_ids), ("demote", shown_ids)):
        for entry in new.get(kind, []):
            if entry.get("id") not in valid:
                problems.append(f"{kind}: id {entry.get('id')!r} is not a {'held' if kind == 'promote' else 'shown'} story")
                continue
            dec[kind][entry["id"]] = {"why": str(entry.get("why", ""))[:120], "at": now}

    verdicts = {}
    for verdict in ("same", "different"):
        for pair in new.get(verdict, []):
            key = "|".join(sorted(pair))
            if key not in pair_keys:
                problems.append(f"{verdict}: pair {pair} is not in pending.json")
                continue
            verdicts[key] = verdict
    if problems:
        print("PROBLEMS, nothing written (fix review/new.json and run again):\n  " + "\n  ".join(problems))
        sys.exit(1)

    for key, p in pair_keys.items():
        v = verdicts.get(key, "same" if p["currently_merged"] else "different")
        dec["pairs"][key] = {"verdict": v, "at": now}

    for c in pending["held"] + pending["shown"]:
        for i in c["ids"]:
            dec["reviewed"][i] = now

    cutoff = now - KEEP_DAYS * 86400
    for k in ("promote", "demote", "pairs"):
        dec[k] = {i: v for i, v in dec[k].items() if v["at"] >= cutoff}
    dec["reviewed"] = {i: t for i, t in dec["reviewed"].items() if t >= cutoff}
    dec["last_review"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now))

    dec_path.write_text(json.dumps(dec, indent=1, sort_keys=True) + "\n")
    print(f"promoted {len(new.get('promote', []))}, demoted {len(new.get('demote', []))}, "
          f"pairs changed {sum(1 for k, v in verdicts.items() if v != ('same' if pair_keys[k]['currently_merged'] else 'different'))}, "
          f"marked {len(held_ids | shown_ids)} stories and {len(pair_keys)} pairs reviewed")


if __name__ == "__main__":
    main()
