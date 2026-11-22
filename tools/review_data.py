#!/usr/bin/env python3
"""Fetch what the latest successful build wants reviewed, into review/pending.json.

Reads the REVIEWDATA line from the build log through the GitHub CLI (`gh`),
so it works from any session that can see this repository.
"""
import base64
import gzip
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def gh(*args: str) -> str:
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout


def repo_name() -> str:
    url = subprocess.run(["git", "-C", str(ROOT), "remote", "get-url", "origin"],
                         check=True, capture_output=True, text=True).stdout.strip()
    m = re.search(r"github\.com[:/]([^/]+/[^/.]+)", url)
    if not m:
        sys.exit(f"can't tell the GitHub repo from {url}")
    return m.group(1)


def latest_build_line(tag: str) -> tuple[dict, object]:
    """Return (run info, decoded payload) for the last `TAG:` line in the latest successful build log."""
    repo = repo_name()
    runs = json.loads(gh("run", "list", "-R", repo, "--workflow", "build.yml", "--status", "success",
                         "--limit", "1", "--json", "databaseId,createdAt"))
    if not runs:
        sys.exit("no successful build yet")
    run = runs[0]
    jobs = json.loads(gh("run", "view", str(run["databaseId"]), "-R", repo, "--json", "jobs"))["jobs"]
    job = next(j for j in jobs if j["name"] == "build")
    log = gh("api", f"repos/{repo}/actions/jobs/{job['databaseId']}/logs")
    blobs = re.findall(tag + r":(\S+)", log)
    if not blobs:
        sys.exit(f"that build has no {tag} line")
    return run, json.loads(gzip.decompress(base64.b64decode(blobs[-1])))


def main() -> None:
    run, data = latest_build_line("REVIEWDATA")
    data["build_run"] = run["databaseId"]
    data["build_time"] = run["createdAt"]
    out = ROOT / "review" / "pending.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1))
    print(f"build {run['databaseId']} ({run['createdAt']}): "
          f"{len(data['held'])} held, {len(data['shown'])} shown, {len(data['pairs'])} pairs to review -> {out}")


if __name__ == "__main__":
    main()
