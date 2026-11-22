#!/usr/bin/env python3
"""Offline smoke test: run the full build against made-up feeds.

    python3 tests/fixture_build.py [out_dir]

No network needed. Feeds not listed below simply "fail" (expected). Without
network the similarity model can't download, so merging falls back to TF-IDF
and a few merges look odd; that's expected here, not a bug. It prints which
stories were shown and which were held back, and why. Expected: Tamagotchi,
the puppy story, MLB rumors, the Padres analysis and the GM Authority
clickbait are held; the Petriello piece, the "Inside the Skubal deal"
feature, WaPo's The 7 story, NYT front-page stories and the GM stock story
are shown.
"""
import email.utils
import json
import re
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import build  # noqa: E402
import os  # noqa: E402
os.environ.setdefault("NEWS_TFIDF_ONLY", "1")  # the model can't download offline; skip the retries

now = time.time()
def rss(items):
    body = "".join(f"<item><title>{t}</title><link>{l}</link><description>{d}</description><author>{a}</author><pubDate>{email.utils.formatdate(now-h*3600)}</pubDate></item>" for t,l,d,a,h in items)
    return f"<?xml version='1.0'?><rss version='2.0'><channel><title>x</title>{body}</channel></rss>".encode()
FEEDS = {
 "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml": rss([
   ("Army Rejected a Cleaner Option to Destroy Explosives in Iowa","https://www.nytimes.com/2026/11/21/us/army-iowa.html","Records reviewed by The Times show the Army chose open burning.","x",3),
   ("Fed Holds Interest Rates Steady, Signals Cuts Later This Year","https://www.nytimes.com/2026/11/21/business/fed-rates.html","The Federal Reserve kept interest rates unchanged and signaled cuts.","x",2),
 ] + [(f"Filler front story number {k} about city budget votes","https://www.nytimes.com/2026/11/21/nyregion/f%d.html"%k,"Council voted.","x",4) for k in range(5)] + [
   ("Why Nostalgia for Tamagotchis, the Virtual Pets, Won't Die","https://www.nytimes.com/2026/11/21/style/tamagotchi.html","Millennials are answering the beeping call.","x",1),
 ]),
 "https://feeds.washingtonpost.com/rss/business": rss([
   ("Federal Reserve leaves interest rates unchanged, signals cuts ahead","https://www.washingtonpost.com/business/2026/11/21/fed-rates/","The Fed held interest rates steady and signaled cuts later this year.","x",1.5),
   ("Man convicted of starting deadly Palisades fire in California","https://www.washingtonpost.com/the-seven/2026/11/21/palisades-fire/","A jury convicted him.","x",3),
   ("A stray puppy hopped onto a car salesman's lap and saved her life","https://www.washingtonpost.com/lifestyle/2026/11/21/puppy/","Heartwarming.","x",4),
 ]),
 "https://www.mlb.com/feeds/news/rss.xml": rss([
   ("Might LA deal Teo to give De Paula a longer look in '27?","https://www.mlb.com/news/teo","x","Sonja Chen",3),
   ("What the Padres' improved infield defense might mean for their offseason","https://www.mlb.com/news/padres","x","Jared Greenspan",6),
   ("Hot Stove Rumors: Webb, Peralta, Mets, Yankees","https://www.mlb.com/news/rumors","x","MLB.com",2),
   ("2 free-agent outfielders, nearly identical stats. Who is the better investment?","https://www.mlb.com/news/petriello","x","Mike Petriello",5),
   ("Tigers sign Tarik Skubal to record extension","https://www.mlb.com/news/skubal","Detroit and ace Tarik Skubal agreed to a record contract extension.","",8),
 ]),
 "https://www.nytimes.com/athletic/rss/mlb/": rss([
   ("Tarik Skubal, Tigers agree to record extension: Sources","https://www.nytimes.com/athletic/1/skubal/","Ace Tarik Skubal and the Detroit Tigers agreed to a record contract extension.","",7),
   ("Why the Giants are listening to trade offers for ace Logan Webb","https://www.nytimes.com/athletic/2/webb/","x","",2),
   ("Inside the Skubal deal: how the Tigers kept their ace","https://www.nytimes.com/athletic/3/inside/","Long read.","",5),
   ("The best and worst uniforms of the season ranked","https://www.nytimes.com/athletic/4/unis/","Fun list.","",5),
 ]),
 "https://gmauthority.com/blog/feed/": rss([
   ("1962 Chevy Corvette vs. 1967 Chevy Corvette Convertible: Which One Would You Buy?","https://gmauthority.com/blog/a/","x","",10),
   ("Buick Envista Discount, Lease, Finance Deals For November 2026","https://gmauthority.com/blog/b/","x","",11),
   ("GM Adds New Chevrolet Pickup Experience Drive Events In Argentina","https://gmauthority.com/blog/c/","x","",12),
   ("GM Stock Value Plummets 8 Percent During Week Of November 16th","https://gmauthority.com/blog/d/","x","",9),
   ("Chevy Trax Gets New Seat Fabric Option For 2027 Model Year","https://gmauthority.com/blog/e/","x","",9),
 ]),
}
class R:
    def __init__(s, c, code=200): s.content=c; s.status_code=code; s.text=c.decode() if c else ""
    def raise_for_status(s):
        if s.status_code!=200: raise Exception(f"HTTP {s.status_code}")
build.http_get = lambda url, timeout=25: R(FEEDS[url]) if url in FEEDS else R(b"", 404)
out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp())
build.build(ROOT / "sources.yaml", out, None)
d = json.loads(re.search(r"const DATA = (.*?);\n", (out/"index.html").read_text()).group(1))
print("\nSHOWN:"); [print(f"  {c['signal'] or '':15s} {[l['outlet'] for l in c['links']]} {c['title'][:70]}") for c in d["clusters"]]
print("HELD:"); [print(f"  {c['reason']:32s} [{c['links'][0]['outlet']}] {c['title'][:70]}") for c in d["held"]]
