#!/usr/bin/env python3
"""Build the personal news page.

Fetches every public feed in sources.yaml, drops filtered stories, merges
duplicate coverage of the same story into one card, and writes a static site
to ./site. No logins or API keys are used anywhere.
"""
from __future__ import annotations

import argparse
import calendar
import hashlib
import html
import json
import math
import os
import re
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import feedparser
import numpy as np
import requests
import yaml

ROOT = Path(__file__).resolve().parent
USER_AGENT = "Mozilla/5.0 (compatible; personal-news-aggregator/1.0)"
EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


def log(*args):
    print(*args, file=sys.stderr, flush=True)


# ---------------------------------------------------------------- text utils

class _Stripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data):
        self.parts.append(data)


def strip_html(text: str) -> str:
    if not text:
        return ""
    s = _Stripper()
    try:
        s.feed(text)
        out = " ".join(s.parts)
    except Exception:
        out = re.sub(r"<[^>]+>", " ", text)
    out = html.unescape(out)
    return re.sub(r"\s+", " ", out).strip()


def truncate(text: str, n: int = 300) -> str:
    if len(text) <= n:
        return text
    cut = text[:n].rsplit(" ", 1)[0]
    return cut.rstrip(",;:.") + "…"


TRACKING_PARAMS = re.compile(r"^(utm_|smid|smtyp|ref|cmpid|partner|emc|itid|fbclid|gclid|mc_)", re.I)


def normalize_url(url: str) -> str:
    try:
        p = urlsplit(url.strip())
    except ValueError:
        return url.strip()
    host = p.netloc.lower().removeprefix("www.")
    query = [(k, v) for k, v in parse_qsl(p.query) if not TRACKING_PARAMS.match(k)]
    if host.endswith("nytimes.com") or host.endswith("washingtonpost.com"):
        query = []
    path = p.path.rstrip("/") or "/"
    return urlunsplit(("https", host, path, urlencode(query), ""))


def item_id(norm_url: str) -> str:
    return hashlib.sha1(norm_url.encode()).hexdigest()[:12]


# ---------------------------------------------------------------- fetching

def http_get(url: str, timeout: int = 25) -> requests.Response:
    return requests.get(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"}, timeout=timeout)


def parse_feed(url: str):
    resp = http_get(url)
    resp.raise_for_status()
    feed = feedparser.parse(resp.content)
    if not feed.entries:
        raise ValueError("no entries" + (f" ({feed.bozo_exception})" if feed.bozo else ""))
    return feed


def discover_feeds(site: str) -> list[str]:
    resp = http_get(site)
    resp.raise_for_status()
    links = re.findall(r"<link[^>]+>", resp.text, re.I)
    found = []
    for tag in links:
        if re.search(r"application/(rss|atom)\+xml", tag, re.I):
            m = re.search(r'href=["\']([^"\']+)', tag, re.I)
            if m:
                found.append(urljoin(site, html.unescape(m.group(1))))
    return found


def entry_time(e) -> float | None:
    for key in ("published_parsed", "updated_parsed", "created_parsed"):
        t = e.get(key)
        if t:
            return float(calendar.timegm(t))
    return None


def fetch_source(src: dict) -> dict:
    """Return {'status':..., 'url':..., 'entries':[...]} for one source."""
    errors = []
    candidates = list(src.get("urls", []))
    feed = used = None
    for url in candidates:
        try:
            feed, used = parse_feed(url), url
            break
        except Exception as ex:  # noqa: BLE001
            errors.append(f"{url}: {ex}")
    if feed is None and src.get("site"):
        try:
            for url in discover_feeds(src["site"]):
                if url in candidates:
                    continue
                try:
                    feed, used = parse_feed(url), url
                    break
                except Exception as ex:  # noqa: BLE001
                    errors.append(f"{url}: {ex}")
            else:
                errors.append(f"{src['site']}: no feed found on homepage")
        except Exception as ex:  # noqa: BLE001
            errors.append(f"{src['site']}: {ex}")
    if feed is None:
        return {"ok": False, "url": None, "entries": [], "errors": errors}

    entries = []
    for e in feed.entries:
        link = e.get("link") or ""
        title = strip_html(e.get("title", ""))
        if not link or not title:
            continue
        summary = strip_html(e.get("summary", "") or e.get("description", ""))
        tags = [t.get("term", "") for t in e.get("tags", []) if t.get("term")]
        entries.append({
            "url": link,
            "title": title,
            "summary": truncate(summary, 400),
            "published": entry_time(e),
            "tags": tags,
        })
    return {"ok": True, "url": used, "entries": entries, "errors": errors}


# ---------------------------------------------------------------- filtering

def make_filter(rules: dict):
    url_bits = [s.lower() for s in rules.get("url_contains", [])]
    cats = {s.lower() for s in rules.get("categories", [])}
    words = rules.get("title_words", [])
    title_re = re.compile(r"\b(" + "|".join(re.escape(w) for w in words) + r")\b", re.I) if words else None

    def reason(entry: dict) -> str | None:
        u = entry["url"].lower()
        for b in url_bits:
            if b in u:
                return f"url contains {b}"
        for t in entry.get("tags", []):
            if t.lower().strip() in cats:
                return f"category {t}"
        if title_re:
            m = title_re.search(entry["title"])
            if m:
                return f"headline word '{m.group(1)}'"
        return None

    return reason


# ---------------------------------------------------------------- similarity

def embed(texts: list[str]) -> np.ndarray:
    """Sentence embeddings (normalized). Falls back to TF-IDF if the model can't load."""
    try:
        from fastembed import TextEmbedding

        cache = os.environ.get("FASTEMBED_CACHE_PATH", str(ROOT / ".cache" / "fastembed"))
        model = TextEmbedding(EMBED_MODEL, cache_dir=cache)
        vecs = np.array(list(model.embed(texts, batch_size=64)), dtype=np.float32)
        method = "embeddings"
    except Exception as ex:  # noqa: BLE001
        log(f"!! embedding model unavailable ({ex}); falling back to TF-IDF")
        vecs = tfidf(texts)
        method = "tfidf"
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    norms[norms == 0] = 1
    embed.method = method
    return vecs / norms


STOP = set("""a an the and or but of to in on for with at by from as is are was were be been it its this that
these those he she they we you i his her their our your not no yes will would can could has have had do does did
about after before over under into out up down new more most than then so if what who how why when where which
says said say just also amid""".split())


def tfidf(texts: list[str]) -> np.ndarray:
    docs = [[w for w in re.findall(r"[a-z0-9']+", t.lower()) if w not in STOP and len(w) > 2] for t in texts]
    vocab: dict[str, int] = {}
    df = Counter()
    for d in docs:
        df.update(set(d))
    for w, c in df.items():
        if c >= 2:
            vocab[w] = len(vocab)
    n = len(docs)
    mat = np.zeros((n, max(len(vocab), 1)), dtype=np.float32)
    for i, d in enumerate(docs):
        for w, c in Counter(d).items():
            j = vocab.get(w)
            if j is not None:
                mat[i, j] = (1 + math.log(c)) * math.log((1 + n) / (1 + df[w]))
    return mat


def cluster(items: list[dict], threshold: float, window_h: float) -> list[list[int]]:
    """Average-linkage clustering on cosine similarity, restricted to a time window."""
    n = len(items)
    if n == 0:
        return []
    if n == 1:
        return [[0]]
    from scipy.cluster.hierarchy import fcluster, linkage
    from scipy.spatial.distance import squareform

    texts = [f"{it['title']}. {it['summary'][:300]}" for it in items]
    vecs = embed(texts)
    sim = vecs @ vecs.T
    times = np.array([it["time"] for it in items], dtype=np.float64)
    far = np.abs(times[:, None] - times[None, :]) > window_h * 3600
    sim[far] = 0.0
    # Two stories from the same outlet only merge if they are very close
    # (e.g. the same article listed under two section feeds with different URLs).
    outlets = np.array([it["outlet"] for it in items])
    same = outlets[:, None] == outlets[None, :]
    sim[same] = np.where(sim[same] >= 0.9, sim[same], 0.0)
    np.fill_diagonal(sim, 1.0)
    dist = np.clip(1.0 - sim, 0.0, 2.0)
    dist = (dist + dist.T) / 2
    np.fill_diagonal(dist, 0.0)

    if os.environ.get("NEWS_DEBUG"):
        _debug_pairs(items, sim, outlets, threshold)
    if os.environ.get("NEWS_DUMP"):
        _dump(items, vecs)

    z = linkage(squareform(dist, checks=False), method="average")
    labels = fcluster(z, t=1.0 - threshold, criterion="distance")
    groups: dict[int, list[int]] = {}
    for i, lab in enumerate(labels):
        groups.setdefault(int(lab), []).append(i)
    return list(groups.values())


def _dump(items, vecs):
    """Print stories and their vectors as one compressed line, for tuning offline."""
    import base64
    import gzip

    blob = {
        "items": [{k: it[k] for k in ("title", "summary", "outlet", "section", "time")} for it in items],
        "vecs": base64.b64encode(vecs.astype(np.float16).tobytes()).decode(),
        "dim": int(vecs.shape[1]),
    }
    print("NEWSDUMP:" + base64.b64encode(gzip.compress(json.dumps(blob).encode())).decode(), flush=True)


def _debug_pairs(items, sim, outlets, threshold):
    """Print cross-outlet pairs near the threshold so it can be tuned."""
    iu = np.triu_indices(len(items), 1)
    vals = sim[iu]
    mask = (vals > threshold - 0.12) & (vals < threshold + 0.12) & (outlets[iu[0]] != outlets[iu[1]])
    idx = np.argsort(-vals[mask])[:60]
    a, b, v = iu[0][mask][idx], iu[1][mask][idx], vals[mask][idx]
    log(f"--- pairs near threshold {threshold} ({embed.method}) ---")
    for i, j, s in zip(a, b, v):
        mark = "MERGE" if s >= threshold else "     "
        log(f"{s:.3f} {mark} [{items[i]['outlet']}] {items[i]['title'][:70]}  ||  [{items[j]['outlet']}] {items[j]['title'][:70]}")


# ---------------------------------------------------------------- state

def load_previous(path: str | None) -> list[dict]:
    if not path:
        return []
    try:
        if path.startswith("http"):
            r = http_get(path)
            if r.status_code != 200:
                log(f"   no previous state at {path} (HTTP {r.status_code})")
                return []
            data = r.json()
        else:
            data = json.loads(Path(path).read_text())
        items = data.get("items", [])
        log(f"   loaded {len(items)} items from previous build")
        return items
    except Exception as ex:  # noqa: BLE001
        log(f"   could not load previous state: {ex}")
        return []


# ---------------------------------------------------------------- main build

def build(config_path: Path, out_dir: Path, previous: str | None) -> None:
    cfg = yaml.safe_load(config_path.read_text())
    sources = cfg["sources"]
    for i, s in enumerate(sources):
        s.setdefault("priority", i)
    reason = make_filter(cfg.get("filters", {}))
    now = time.time()
    retention = cfg.get("retention_hours", 72) * 3600

    log(f"Fetching {len(sources)} feeds…")
    with ThreadPoolExecutor(max_workers=12) as pool:
        results = list(pool.map(fetch_source, sources))

    status = []
    filtered_log = []
    fresh: dict[str, dict] = {}
    for src, res in zip(sources, results):
        kept = dropped = 0
        for e in res["entries"]:
            why = reason(e) if src.get("filter") else None
            if why:
                dropped += 1
                filtered_log.append({"source": src["name"], "title": e["title"], "url": e["url"], "why": why})
                continue
            norm = normalize_url(e["url"])
            iid = item_id(norm)
            t = e["published"] or now
            if t > now + 3600:
                t = now
            if now - t > retention:
                continue
            existing = fresh.get(iid)
            if existing and existing["priority"] <= src["priority"]:
                continue
            fresh[iid] = {
                "id": iid,
                "url": e["url"],
                "title": e["title"],
                "summary": e["summary"],
                "outlet": src["outlet"],
                "source": src["name"],
                "section": src["section"],
                "priority": src["priority"],
                "time": t,
            }
            kept += 1
        status.append({
            "name": src["name"],
            "ok": res["ok"],
            "url": res["url"],
            "kept": kept,
            "filtered": dropped,
            "errors": res["errors"] if not res["ok"] else [],
        })
        flag = "ok " if res["ok"] else "ERR"
        log(f"  [{flag}] {src['name']}: {kept} kept, {dropped} filtered" + ("" if res["ok"] else f"  {res['errors']}"))

    # Merge with the previous build so stories persist after they fall out of a feed.
    merged: dict[str, dict] = {}
    for old in load_previous(previous):
        if now - old.get("time", 0) <= retention and old.get("id"):
            merged[old["id"]] = old
    src_by_name = {s["name"]: s for s in sources}
    for iid, it in list(merged.items()):
        s = src_by_name.get(it.get("source"))
        if s is None:  # source removed from config
            del merged[iid]
            continue
        if s.get("filter") and reason({"url": it["url"], "title": it["title"], "tags": []}):
            del merged[iid]
            continue
        it["section"], it["outlet"], it["priority"] = s["section"], s["outlet"], s["priority"]
    for iid, it in fresh.items():
        prev = merged.get(iid)
        it["first_seen"] = prev.get("first_seen", now) if prev else now
        merged[iid] = it
    items = sorted(merged.values(), key=lambda x: -x["time"])
    log(f"{len(items)} stories in the {cfg.get('retention_hours', 72)}h window")

    groups = cluster(items, cfg.get("similarity_threshold", 0.62), cfg.get("merge_window_hours", 48))
    section_order = [s["id"] for s in cfg["sections"]]
    clusters = []
    for g in groups:
        members = sorted((items[i] for i in g), key=lambda x: (x["priority"], x["time"]))
        lead = members[0]
        # The card goes in the section most of its links come from (ties: config order).
        sec_counts = Counter(m["section"] for m in members)
        section = min(sec_counts, key=lambda s: (-sec_counts[s], section_order.index(s) if s in section_order else 99))
        summary = lead["summary"] or next((m["summary"] for m in members if m["summary"]), "")
        clusters.append({
            "id": lead["id"],
            "title": lead["title"],
            "summary": truncate(summary, 300),
            "section": section,
            "time": max(m["time"] for m in members),
            "first_time": min(m["time"] for m in members),
            "first_seen": min(m.get("first_seen", now) for m in members),
            "outlets": len({m["outlet"] for m in members}),
            "links": [
                {"id": m["id"], "url": m["url"], "outlet": m["outlet"], "title": m["title"], "time": m["time"]}
                for m in sorted(members, key=lambda x: (x["priority"], x["time"]))
            ],
        })
    clusters.sort(key=lambda c: -c["time"])
    multi = sum(1 for c in clusters if len(c["links"]) > 1)
    log(f"{len(clusters)} cards ({multi} with coverage from more than one link), similarity via {getattr(embed, 'method', 'n/a')}")

    out_dir.mkdir(parents=True, exist_ok=True)
    page_data = {
        "generated": now,
        "sections": cfg["sections"],
        "clusters": clusters,
        "status": status,
        "filtered": filtered_log,
    }
    template = (ROOT / "templates" / "index.html").read_text()
    payload = json.dumps(page_data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    (out_dir / "index.html").write_text(template.replace("/*__DATA__*/null", payload))
    (out_dir / "items.json").write_text(json.dumps({"generated": now, "items": items}, ensure_ascii=False))
    (out_dir / ".nojekyll").write_text("")
    log(f"Wrote {out_dir / 'index.html'}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default=str(ROOT / "sources.yaml"))
    ap.add_argument("--out", default=str(ROOT / "site"))
    ap.add_argument("--previous", default=os.environ.get("PREVIOUS_STATE"),
                    help="URL or path of the last build's items.json, so stories persist between runs")
    args = ap.parse_args()
    build(Path(args.config), Path(args.out), args.previous)


if __name__ == "__main__":
    main()
