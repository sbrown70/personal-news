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
    for rank, e in enumerate(feed.entries):
        link = e.get("link") or ""
        title = strip_html(e.get("title", ""))
        if not link or not title:
            continue
        summary = strip_html(e.get("summary", "") or e.get("description", ""))
        if src.get("google_news"):
            # "Headline - ESPN" -> "Headline"; the summary just repeats the headline.
            title = re.sub(r"\s+[-–|]\s+[^-–|]{2,40}$", "", title)
        if summary.startswith(title[:60]):
            summary = ""
        if len(title.split()) < 4:
            continue  # section index pages and teasers ("Chevrolet News", "Here's the latest.")
        tags = [t.get("term", "") for t in e.get("tags", []) if t.get("term")]
        entries.append({
            "url": link,
            "title": title,
            "summary": truncate(summary, 400),
            "published": entry_time(e),
            "tags": tags,
            "author": e.get("author", "") or "",
            "rank": rank,  # position in the feed; on NYT's home-page feed this is editors' placement
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


# ---------------------------------------------------------------- selection

def _rx(patterns) -> list[re.Pattern]:
    return [re.compile(p, re.I) for p in patterns or []]


class Selector:
    """Decides which stories reach the main page.

    Two steps:
      1. held_reason(): per-story drops for rumor and clickbait headlines on the
         sources that opt in (rumor_rules, drop_titles, drop_question_headlines).
      2. pass_signal(): for sources marked `gate: true`, a single-outlet story is
         shown only if it carries an importance signal: an allow-listed byline,
         NYT front-page placement, an editors'-pick URL (WaPo's The 7), scoop or
         feature language, or a source-specific keyword. Stories covered by two or
         more outlets always pass (that check happens per card, in build()).
    Anything that fails goes to the "Held back" tab instead of disappearing.
    """

    def __init__(self, cfg: dict, sources: list[dict]):
        sel = cfg.get("selection", {})
        self.rumor = _rx(sel.get("rumor_patterns"))
        self.scoop = _rx(sel.get("scoop_patterns"))
        self.feature = _rx(sel.get("feature_patterns"))
        self.picks = {k.lower(): v for k, v in (sel.get("editor_pick_urls") or {}).items()}
        for src in sources:
            src["_drop"] = _rx(src.get("drop_titles"))
            src["_keywords"] = _rx(src.get("pass_keywords"))
            src["_authors"] = [a.lower() for a in src.get("pass_authors", [])]

    @staticmethod
    def author_ok(it: dict, src: dict) -> bool:
        a = (it.get("author") or "").lower()
        return bool(a) and any(name in a for name in src["_authors"])

    def held_reason(self, it: dict, src: dict) -> str | None:
        if self.author_ok(it, src):
            return None
        title = it["title"]
        if src.get("rumor_rules"):
            for p in self.rumor:
                if p.search(title):
                    return "rumor/speculation"
        for p in src["_drop"]:
            if p.search(title):
                return "clickbait/marketing"
        if src.get("drop_question_headlines") and title.rstrip().endswith("?"):
            return "question headline"
        return None

    def pass_signal(self, it: dict, src: dict) -> str | None:
        """Return why this story may show on its own, or None."""
        if not src.get("gate"):
            return "source"
        if self.author_ok(it, src):
            return "byline"
        if it.get("front_page"):
            return "NYT front page"
        url = it["url"].lower()
        for frag, label in self.picks.items():
            if frag in url:
                return label
        text = f"{it['title']} {it.get('summary', '')}"
        if any(p.search(text) for p in self.scoop):
            return "Scoop"
        if any(p.search(text) for p in self.feature):
            return "Feature"
        if any(p.search(it["title"]) for p in src["_keywords"]):
            return "keyword"
        return None


# Signals worth showing as a small label on the card.
VISIBLE_SIGNALS = ("NYT front page", "WaPo The 7", "Scoop", "Feature")


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


def cluster(items: list[dict], threshold: float, window_h: float, lex_weight: float = 0.3) -> list[list[int]]:
    """Average-linkage clustering, restricted to a time window.

    Similarity = sentence-embedding cosine + lex_weight * TF-IDF cosine. The
    embedding catches paraphrases ("Fed holds rates" / "Federal Reserve leaves
    rates unchanged"); the TF-IDF term rewards shared rare words (names, places),
    which keeps same-topic-but-different stories (two prospect lists) apart.
    """
    n = len(items)
    if n == 0:
        return []
    if n == 1:
        return [[0]]
    from scipy.cluster.hierarchy import fcluster, linkage
    from scipy.spatial.distance import squareform

    texts = [f"{it['title']}. {it['summary'][:300]}" for it in items]
    vecs = embed(texts)
    emb = vecs @ vecs.T
    lex_vecs = tfidf(texts)
    lex_vecs /= np.maximum(np.linalg.norm(lex_vecs, axis=1, keepdims=True), 1e-9)
    sim = emb + lex_weight * (lex_vecs @ lex_vecs.T)
    times = np.array([it["time"] for it in items], dtype=np.float64)
    far = np.abs(times[:, None] - times[None, :]) > window_h * 3600
    sim[far] = 0.0
    # Two stories from the same outlet only merge if they are very close
    # (e.g. the same article listed under two section feeds with different URLs).
    outlets = np.array([it["outlet"] for it in items])
    same = outlets[:, None] == outlets[None, :]
    sim[same & (emb < 0.9)] = 0.0
    top = 1.0 + lex_weight
    np.fill_diagonal(sim, top)
    dist = np.clip(top - sim, 0.0, 3.0)
    dist = (dist + dist.T) / 2
    np.fill_diagonal(dist, 0.0)

    if os.environ.get("NEWS_DEBUG"):
        _debug_pairs(items, sim, outlets, threshold)
    if os.environ.get("NEWS_DUMP"):
        _dump(items, vecs)

    z = linkage(squareform(dist, checks=False), method="average")
    labels = fcluster(z, t=top - threshold, criterion="distance")
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
        "variants": {},
    }
    # Optional: extra models to compare, e.g. NEWS_DUMP_MODELS="BAAI/bge-small-en-v1.5,BAAI/bge-base-en-v1.5"
    from fastembed import TextEmbedding

    cache = os.environ.get("FASTEMBED_CACHE_PATH", str(ROOT / ".cache" / "fastembed"))
    for name in filter(None, os.environ.get("NEWS_DUMP_MODELS", "").split(",")):
        model = TextEmbedding(name, cache_dir=cache)
        for kind, texts in (("title", [it["title"] for it in items]),
                            ("full", [f"{it['title']}. {it['summary'][:300]}" for it in items])):
            v = np.array(list(model.embed(texts, batch_size=64)), dtype=np.float32)
            v /= np.maximum(np.linalg.norm(v, axis=1, keepdims=True), 1e-9)
            blob["variants"][f"{name}|{kind}"] = {"dim": int(v.shape[1]), "vecs": base64.b64encode(v.astype(np.float16).tobytes()).decode()}
            log(f"   dumped {name} {kind}")
    print("NEWSDUMP:" + base64.b64encode(gzip.compress(json.dumps(blob).encode())).decode(), flush=True)


def _debug_pairs(items, sim, outlets, threshold):
    """Print cross-outlet pairs near the threshold so it can be tuned."""
    iu = np.triu_indices(len(items), 1)
    vals = sim[iu]
    mask = (vals > threshold - 0.1) & (vals < threshold + 0.1) & (outlets[iu[0]] != outlets[iu[1]])
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
    selector = Selector(cfg, sources)
    always_drop = [re.compile(p, re.I) for p in cfg.get("always_drop_titles", [])]
    now = time.time()
    default_ret = cfg.get("retention_hours", 72)
    sec_ret = {s["id"]: s.get("retention_hours", default_ret) * 3600 for s in cfg["sections"]}
    max_ret = max([*sec_ret.values(), *(s.get("retention_hours", 0) * 3600 for s in sources)])

    def expired(src: dict, t: float) -> bool:
        limit = src["retention_hours"] * 3600 if src.get("retention_hours") else sec_ret.get(src["section"], default_ret * 3600)
        return now - t > limit

    log(f"Fetching {len(sources)} feeds…")
    with ThreadPoolExecutor(max_workers=12) as pool:
        results = list(pool.map(fetch_source, sources))

    status = []
    filtered_log = []
    fresh: dict[str, dict] = {}
    seen_titles: set[tuple[str, str]] = set()  # (outlet, title): same story under two URLs
    for src, res in zip(sources, results):
        kept = dropped = 0
        for e in res["entries"]:
            if any(p.search(e["title"]) for p in always_drop):
                continue
            why = reason(e) if src.get("filter") else None
            if why:
                dropped += 1
                filtered_log.append({"source": src["name"], "title": e["title"], "url": e["url"], "why": why})
                continue
            norm = normalize_url(e["url"])
            iid = item_id(norm)
            tkey = (src["outlet"], e["title"].lower())
            if tkey in seen_titles and iid not in fresh:
                continue
            seen_titles.add(tkey)
            t = e["published"] or now
            if t > now + 3600:
                t = now
            if expired(src, t):
                continue
            front = e["rank"] < src.get("front_page_positions", 0)
            existing = fresh.get(iid)
            if existing and existing["priority"] <= src["priority"]:
                existing["front_page"] = existing.get("front_page") or front
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
                "author": e["author"],
                "front_page": front or bool(existing and existing.get("front_page")),
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
        if old.get("id") and now - old.get("time", 0) <= max_ret:
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
        if expired(s, it["time"]):
            del merged[iid]
    for iid, it in fresh.items():
        prev = merged.get(iid)
        it["first_seen"] = prev.get("first_seen", now) if prev else now
        # Once a story has been on NYT's front page, remember it.
        it["front_page"] = it.get("front_page") or bool(prev and prev.get("front_page"))
        merged[iid] = it
    all_items = sorted(merged.values(), key=lambda x: -x["time"])

    held: list[dict] = []
    items = []
    for it in all_items:
        why = selector.held_reason(it, src_by_name[it["source"]])
        if why:
            held.append(_card([it], it["section"], now) | {"reason": why})
        else:
            items.append(it)
    log(f"{len(all_items)} stories in the window; {len(held)} held back as rumor/clickbait")

    groups = cluster(items, cfg.get("similarity_threshold", 0.70), cfg.get("merge_window_hours", 48),
                     cfg.get("lexical_weight", 0.3))
    section_order = [s["id"] for s in cfg["sections"]]
    clusters = []
    single_outlet_held = 0
    for g in groups:
        members = sorted((items[i] for i in g), key=lambda x: (x["priority"], x["time"]))
        # The card goes in the section most of its links come from (ties: config order).
        sec_counts = Counter(m["section"] for m in members)
        section = min(sec_counts, key=lambda s: (-sec_counts[s], section_order.index(s) if s in section_order else 99))
        card = _card(members, section, now)
        signals = [selector.pass_signal(m, src_by_name[m["source"]]) for m in members]
        if card["outlets"] >= 2 or any(signals):
            card["signal"] = next((s for s in signals if s in VISIBLE_SIGNALS), "")
            clusters.append(card)
        else:
            held.append(card | {"reason": "one outlet, no importance signal"})
            single_outlet_held += 1
    clusters.sort(key=lambda c: -c["time"])
    held.sort(key=lambda c: -c["time"])
    multi = sum(1 for c in clusters if len(c["links"]) > 1)
    log(f"{len(clusters)} cards ({multi} with coverage from more than one link), similarity via {getattr(embed, 'method', 'n/a')}")
    log(f"{len(held)} held back ({single_outlet_held} single-outlet stories without an importance signal)")
    for c in clusters:
        if c.get("signal"):
            log(f"   passed via {c['signal']}: [{c['links'][0]['outlet']}] {c['title'][:90]}")

    out_dir.mkdir(parents=True, exist_ok=True)
    page_data = {
        "generated": now,
        "sections": cfg["sections"],
        "clusters": clusters,
        "held": held,
        "status": status,
        "filtered": filtered_log,
    }
    template = (ROOT / "templates" / "index.html").read_text()
    payload = json.dumps(page_data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    (out_dir / "index.html").write_text(template.replace("/*__DATA__*/null", payload))
    (out_dir / "items.json").write_text(json.dumps({"generated": now, "items": all_items}, ensure_ascii=False))
    (out_dir / ".nojekyll").write_text("")
    log(f"Wrote {out_dir / 'index.html'}")


def _card(members: list[dict], section: str, now: float) -> dict:
    """One card on the page: a story and every outlet's link to it."""
    lead = members[0]
    summary = lead["summary"] or next((m["summary"] for m in members if m["summary"]), "")
    return {
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
    }


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
