"""Keeps this tool caught up with Marky and its competitors.
Each week it reads their feature and pricing pages, compares them with last week, and writes a report of
new features (data/watch/latest.md). The GitHub workflow turns that report into an issue, which a scheduled
Claude Code task can pick up and build."""
import datetime as dt, hashlib, re
from html.parser import HTMLParser
from .util import DATA, http, load_json, save_json, log

SOURCES = {
    "Marky": ["https://www.mymarky.ai/", "https://www.mymarky.ai/pricing", "https://www.mymarky.ai/features/generate",
              "https://www.mymarky.ai/agents", "https://www.mymarky.ai/blog"],
    "SocialBee": ["https://socialbee.com/features/", "https://socialbee.com/pricing/"],
    "Publer": ["https://publer.com/features", "https://publer.com/plans"],
    "FeedHive": ["https://www.feedhive.com/features", "https://www.feedhive.com/pricing"],
    "Metricool": ["https://metricool.com/pricing/"],
    "Predis.ai": ["https://predis.ai/pricing/"],
    "Ocoya": ["https://www.ocoya.com/pricing"],
}


class Lines(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.lines, self._on, self._buf, self._skip = [], None, [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "svg"):
            self._skip += 1
        elif tag in ("h1", "h2", "h3", "h4", "li", "summary") and not self._skip and self._on is None:
            self._on, self._buf = tag, []

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "svg"):
            self._skip = max(0, self._skip - 1)
        elif tag == self._on:
            t = " ".join("".join(self._buf).split())
            if 3 <= len(t) <= 160:
                self.lines.append(t)
            self._on = None

    def handle_data(self, d):
        if self._on:
            self._buf.append(d)


def _norm(s):
    return re.sub(r"[^a-z0-9 ]", "", s.lower()).strip()


def run():
    path = DATA / "watch" / "snapshot.json"
    snap = load_json(path, {})
    first = not snap
    report = []
    for vendor, urls in SOURCES.items():
        for url in urls:
            try:
                r = http().get(url, timeout=30)
                if r.status_code != 200:
                    continue
            except Exception as e:
                log(f"watch: {url} failed: {e}")
                continue
            p = Lines()
            p.feed(r.text)
            now_lines = {_norm(x): x for x in p.lines if _norm(x)}
            old = set(snap.get(url, {}).get("lines", []))
            added = [now_lines[k] for k in now_lines if k not in old]
            removed = [k for k in old if k not in now_lines]
            if old and (added or removed):
                report.append(f"### {vendor} - {url}\n" + "".join(f"- NEW: {a}\n" for a in added[:40])
                              + (f"- ({len(removed)} items removed)\n" if removed else ""))
            snap[url] = {"lines": sorted(now_lines), "hash": hashlib.sha1(r.content).hexdigest(),
                         "checked": dt.date.today().isoformat()}
    save_json(path, snap)
    out = DATA / "watch" / "latest.md"
    if report and not first:
        body = (f"# Competitor changes found {dt.date.today().isoformat()}\n\n"
                "New headings and list items on Marky's and competitors' feature/pricing pages since the last check. "
                "Review and decide which to add to Social Autopilot (see FEATURES.md).\n\n" + "\n".join(report))
        out.write_text(body, encoding="utf-8")
        log(f"watch: {len(report)} pages changed - see data/watch/latest.md")
    else:
        out.write_text("", encoding="utf-8")
        log("watch: baseline saved" if first else "watch: no changes")
    return out
