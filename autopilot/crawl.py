"""Reads each website (sitemap -> pages) and remembers what is on it, so posts come from your own content
and new or changed pages get announced automatically."""
import hashlib, json, time
from html.parser import HTMLParser
from urllib.parse import urljoin
from xml.etree import ElementTree as ET
from .util import DATA, http, load_json, save_json, log, now, config

SKIP_TAGS = {"style", "noscript", "nav", "footer", "svg", "form"}


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.meta, self.h1, self.sections, self.jsonld, self.icons = {}, [], [], [], []
        self._tag, self._buf, self._skip = None, [], 0

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        if tag == "script":
            if a.get("type") == "application/ld+json":
                self._tag, self._buf = "ldjson", []
            else:
                self._skip += 1
            return
        if tag in SKIP_TAGS:
            self._skip += 1
            return
        if tag == "meta":
            k = (a.get("name") or a.get("property") or "").lower()
            if k and a.get("content"):
                self.meta[k] = a["content"]
        if tag == "link" and "icon" in a.get("rel", "").lower() and a.get("href"):
            self.icons.append((a.get("sizes", ""), a["href"]))
        if not self._skip and tag in ("title", "h1", "h2", "h3", "p", "li") and self._tag is None:
            self._tag, self._buf = tag, []

    def handle_endtag(self, tag):
        if tag == "script":
            if self._tag == "ldjson":
                self.jsonld.append("".join(self._buf))
                self._tag = None
            else:
                self._skip = max(0, self._skip - 1)
            return
        if tag in SKIP_TAGS:
            self._skip = max(0, self._skip - 1)
            return
        if tag != self._tag:
            return
        text = " ".join("".join(self._buf).split())
        self._tag = None
        if not text:
            return
        if tag == "title":
            self.title = text
        elif tag == "h1":
            self.h1.append(text)
        elif tag in ("h2", "h3"):
            self.sections.append({"h": text, "p": []})
        elif len(text) > 50:
            if not self.sections:
                self.sections.append({"h": "", "p": []})
            self.sections[-1]["p"].append(text)

    def handle_data(self, d):
        if self._tag:
            self._buf.append(d)


def _faqs(blocks):
    out = []

    def walk(node):
        if isinstance(node, list):
            for n in node:
                walk(n)
        elif isinstance(node, dict):
            t = node.get("@type")
            if t == "Question" or (isinstance(t, list) and "Question" in t):
                ans = node.get("acceptedAnswer") or {}
                if isinstance(ans, list):
                    ans = ans[0] if ans else {}
                q, a = node.get("name", ""), ans.get("text", "")
                if q and a:
                    out.append({"q": " ".join(q.split()), "a": _strip_html(a)})
            for v in node.values():
                if isinstance(v, (list, dict)):
                    walk(v)

    for b in blocks:
        try:
            walk(json.loads(b))
        except (json.JSONDecodeError, TypeError):
            continue
    seen, uniq = set(), []
    for f in out:
        if f["q"] not in seen:
            seen.add(f["q"])
            uniq.append(f)
    return uniq


def _strip_html(s):
    p = HTMLParser()
    parts = []
    p.handle_data = parts.append
    p.feed(s)
    return " ".join(" ".join(parts).split())


def sitemap_urls(url, depth=0):
    r = http().get(url, timeout=30)
    r.raise_for_status()
    root = ET.fromstring(r.content)
    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    urls = []
    for sm in root.findall("s:sitemap/s:loc", ns):
        if depth < 2:
            urls += sitemap_urls(sm.text.strip(), depth + 1)
    for loc in root.findall("s:url", ns):
        u = loc.find("s:loc", ns).text.strip()
        lm = loc.find("s:lastmod", ns)
        urls.append((u, lm.text.strip() if lm is not None else ""))
    return urls


def parse_page(url, html):
    p = PageParser()
    p.feed(html)
    image = p.meta.get("og:image") or p.meta.get("twitter:image") or ""
    sections = [s for s in p.sections if s["p"]][:20]
    icon = ""
    if p.icons:
        icon = sorted(p.icons, key=lambda x: int((x[0] or "0x0").split("x")[0] or 0) if x[0][:1].isdigit() else 0)[-1][1]
    page = {
        "url": url,
        "title": p.title,
        "description": p.meta.get("description") or p.meta.get("og:description", ""),
        "h1": p.h1[0] if p.h1 else p.title,
        "sections": sections,
        "faqs": _faqs(p.jsonld)[:15],
        "image": urljoin(url, image) if image else "",
        "icon": urljoin(url, icon) if icon else "",
    }
    body = json.dumps([page["h1"], page["description"], sections, page["faqs"]], sort_keys=True)
    page["hash"] = hashlib.sha1(body.encode()).hexdigest()
    return page


def crawl_brand(brand):
    cfg = config()["settings"]
    store_path = DATA / "pages" / f"{brand['id']}.json"
    store = load_json(store_path, {"pages": {}, "fresh": []})
    first_run = not store["pages"]
    try:
        urls = sitemap_urls(brand["sitemap"])
    except Exception as e:  # keep going with what we already know
        log(f"[{brand['id']}] sitemap failed: {e}")
        return store
    excluded = [x.lower() for x in cfg.get("exclude_paths", [])]
    stamp = now().isoformat(timespec="seconds")
    changed = 0
    for url, lastmod in urls:
        if any(x in url.lower() for x in excluded):
            continue
        old = store["pages"].get(url)
        if old and old.get("lastmod") == lastmod and lastmod:
            continue  # sitemap says nothing changed - skip the download
        try:
            r = http().get(url, timeout=30)
            if r.status_code != 200 or "text/html" not in r.headers.get("content-type", ""):
                continue
            page = parse_page(url, r.text)
        except Exception as e:
            log(f"[{brand['id']}] could not read {url}: {e}")
            continue
        page["lastmod"] = lastmod
        page["first_seen"] = old["first_seen"] if old else stamp
        if old and old["hash"] == page["hash"]:
            page["last_changed"] = old.get("last_changed", old["first_seen"])
        else:
            page["last_changed"] = stamp
            if not first_run:  # don't announce the whole site on day one
                kind = "updated" if old else "new"
                store["fresh"] = [f for f in store["fresh"] if f["url"] != url] + [{"url": url, "kind": kind, "at": stamp}]
                changed += 1
        store["pages"][url] = page
        time.sleep(0.3)
    store["crawled_at"] = stamp
    save_json(store_path, store)
    log(f"[{brand['id']}] crawled {len(store['pages'])} pages, {changed} new/updated")
    return store
