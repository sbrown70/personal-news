#!/usr/bin/env python3
"""Debug helper: show what a URL actually returns (status, type, start of body, feed-looking links)."""
import re
import sys

import requests

UAS = {
    "bot": "Mozilla/5.0 (compatible; personal-news-aggregator/1.0)",
    "browser": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
}
for url in sys.argv[1:]:
    for name, ua in list(UAS.items())[:1]:
        try:
            r = requests.get(url, headers={"User-Agent": ua}, timeout=25)
            body = r.text
            print(f"=== {url} [{name}] -> {r.status_code} {r.headers.get('content-type')} final={r.url} len={len(body)}")
            print("    start:", re.sub(r"\s+", " ", body[:300]))
            if len(body) < 6000 and "html" in (r.headers.get("content-type") or ""):
                print("    full body:", re.sub(r"\s+", " ", body))
            scripts = re.findall(r'<script[^>]+src=["\']([^"\']+)', body, re.I)
            if scripts:
                print("    scripts:", scripts[:10])
            if "javascript" in (r.headers.get("content-type") or ""):
                urls = sorted(set(re.findall(r'["\'`]((?:https?://|/)[^"\'`\s]{3,120}\.(?:json|csv|xml)[^"\'`\s]{0,60})["\'`]', body)))
                print("    data urls in script:", urls[:40])
                print("    fetch() calls:", sorted(set(re.findall(r'fetch\(\s*["\'`]([^"\'`]+)', body)))[:40])
            links = sorted(set(re.findall(r'href=["\']([^"\']*(?:rss|feed|atom|\.xml)[^"\']*)', body, re.I)))[:15]
            if links:
                print("    feed-ish links:", links)
        except Exception as ex:
            print(f"=== {url} [{name}] -> ERROR {ex}")
