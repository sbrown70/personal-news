#!/usr/bin/env python3
"""Debug helper: show what a URL returns. Feeds: list entries. HTML: feed links and article links."""
import re
import sys

import feedparser
import requests

UA = "Mozilla/5.0 (compatible; personal-news-aggregator/1.0)"
for url in sys.argv[1:]:
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=25)
    except Exception as ex:
        print(f"=== {url} -> ERROR {ex}")
        continue
    body, ctype = r.text, r.headers.get("content-type") or ""
    print(f"=== {url} -> {r.status_code} {ctype} final={r.url} len={len(body)}")
    feed = feedparser.parse(r.content)
    if feed.entries:
        print(f"    FEED '{feed.feed.get('title')}' with {len(feed.entries)} entries")
        for e in feed.entries[:12]:
            tags = [t.get("term") for t in e.get("tags", [])][:4]
            print(f"    - {e.get('title','')[:80]} | author={e.get('author','')} | tags={tags} | {e.get('link','')[:100]}")
        continue
    print("    start:", re.sub(r"\s+", " ", body[:200]))
    feeds = sorted(set(re.findall(r'href=["\']([^"\']*(?:rss|feed|atom|\.xml)[^"\']*)', body, re.I)))[:10]
    if feeds:
        print("    feed-ish links:", feeds)
    arts = list(dict.fromkeys(re.findall(r'href=["\']((?:https?://[^"\']+)?/20\d\d/\d\d/\d\d/[^"\'#?]+)', body)))
    print(f"    {len(arts)} dated article links:", arts[:25])
    other = list(dict.fromkeys(re.findall(r'href=["\'](/(?:research|paper|papers|article|articles|post|posts)/[^"\'#?]+)', body)))
    if other:
        print(f"    {len(other)} other content links:", other[:15])
