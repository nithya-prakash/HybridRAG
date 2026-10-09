"""Fetch the plain text of a fixed list of Wikipedia articles into this folder as Markdown.

Source: the public MediaWiki API (en.wikipedia.org), text licensed CC BY-SA 4.0. Each article is
capped at MAX_CHARS so the corpus stays small. The titles are grouped into confusable clusters
(similar languages, rivers, scientists, energy sources, ML models) so that retrieval has to tell
near-neighbours apart. Run: python fetch_wiki.py
"""
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

MAX_CHARS = 16000
OUT = Path(__file__).parent
TITLES = [
    "Python (programming language)", "Ruby (programming language)", "Rust (programming language)",
    "Go (programming language)", "Kotlin (programming language)", "Swift (programming language)",
    "Danube", "Rhine", "Elbe", "Oder",
    "Marie Curie", "Lise Meitner", "Rosalind Franklin", "Emmy Noether", "Ada Lovelace",
    "Solar power", "Wind power", "Hydroelectricity", "Geothermal energy", "Nuclear power",
    "Munich", "Hamburg", "Stuttgart", "Cologne",
    "Transformer (deep learning)", "Convolutional neural network", "Recurrent neural network",
    "Gradient boosting", "Random forest", "Support vector machine",
]


def fetch(title: str) -> str:
    q = urllib.parse.urlencode({"action": "query", "prop": "extracts", "explaintext": 1,
                                "redirects": 1, "titles": title, "format": "json"})
    req = urllib.request.Request("https://en.wikipedia.org/w/api.php?" + q,
                                 headers={"User-Agent": "HybridRAG-eval/1.0 (portfolio project)"})
    for attempt in range(6):  # the API rate-limits bursts; back off and retry
        try:
            data = json.load(urllib.request.urlopen(req, timeout=30))
            break
        except urllib.error.HTTPError as e:
            if e.code != 429 or attempt == 5:
                raise
            time.sleep(15 * (attempt + 1))
    page = next(iter(data["query"]["pages"].values()))
    text = page.get("extract", "")
    text = re.sub(r"^={2,}\s*(.+?)\s*={2,}$", lambda m: "## " + m.group(1), text, flags=re.M)
    return f"# {page['title']}\n\n{text}"[:MAX_CHARS]


if __name__ == "__main__":
    for t in TITLES:
        slug = re.sub(r"[^a-z0-9]+", "_", t.lower()).strip("_")
        if (OUT / f"{slug}.md").exists():
            continue
        time.sleep(2)
        (OUT / f"{slug}.md").write_text(fetch(t), encoding="utf-8")
        print(slug)
