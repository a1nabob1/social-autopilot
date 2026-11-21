"""Writes docs/index.html (calendar of every planned, held and posted item) and docs/links-<brand>.html
(a free 'link in bio' page that always lists your latest posts)."""
import datetime as dt, html
from .util import ROOT, DATA, load_json, config, now

CSS = """
:root{--bg:#f6f7f9;--card:#fff;--ink:#1b2430;--muted:#5c6773;--line:#e2e6ea;--ok:#1d7a46;--warn:#a35a00;--bad:#b3261e;--chip:#eef1f4}
@media (prefers-color-scheme:dark){:root{--bg:#12161b;--card:#1b2128;--ink:#e8ecf0;--muted:#9aa5b1;--line:#2c343d;--ok:#5cc58b;--warn:#f0a94b;--bad:#ff8a80;--chip:#252d36}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,Segoe UI,Arial,sans-serif}
main{max-width:1100px;margin:0 auto;padding:24px 16px}h1{font-size:24px;margin:0 0 4px}h2{font-size:18px;margin:28px 0 10px}
.muted{color:var(--muted)}.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:14px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;overflow:hidden}.card img{width:100%;display:block;aspect-ratio:1}
.card .b{padding:10px 12px}.chip{display:inline-block;background:var(--chip);border-radius:99px;padding:1px 9px;font-size:12px;margin:2px 4px 2px 0}
.ok{color:var(--ok)}.warn{color:var(--warn)}.bad{color:var(--bad)}details{margin-top:6px}pre{white-space:pre-wrap;font:12px/1.45 ui-monospace,Consolas,monospace;background:var(--chip);padding:8px;border-radius:8px}
.stats{display:flex;gap:12px;flex-wrap:wrap}.stat{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:10px 16px}
.stat b{display:block;font-size:22px}
"""


def _img(rel):
    base = config()["settings"].get("public_base_url", "").rstrip("/")
    return f"{base}/{rel}" if base else f"../{rel}"


def _when(iso):
    if not iso:
        return "not scheduled"
    return dt.datetime.fromisoformat(iso).strftime("%a %b %d, %I:%M %p").replace(" 0", " ")


def _card(p, brand):
    e = html.escape
    st = p["status"]
    cls = {"posted": "ok", "approved": "", "needs_review": "warn", "partial": "bad", "draft": "warn"}.get(st, "")
    res = "".join(
        f'<span class="chip {"ok" if r.get("ok") else ("bad" if r.get("error") else "muted")}">{e(k)}'
        f'{" ✓" if r.get("ok") else (" ✗" if r.get("error") else " –")}</span>' for k, r in p.get("results", {}).items())
    reasons = "".join(f"<li>{e(x)}</li>" for x in p.get("hold_reasons", []))
    caps = "".join(f"<details><summary>{e(k)}</summary><pre>{e(v.get('text', ''))}</pre></details>" for k, v in p["captions"].items())
    return (f'<div class="card"><img loading="lazy" src="{_img(p["images"]["square"])}" alt="{e(p["headline"])}">'
            f'<div class="b"><div class="muted">{e(_when(p.get("slot")))} · {e(brand["name"])}</div>'
            f'<b>{e(p["headline"])}</b><div><span class="chip">{e(p["kind"])}</span><span class="chip {cls}">{e(st)}</span>'
            f'{"<span class=chip>AI</span>" if p.get("ai") else ""}{"<span class=chip>recycled</span>" if p.get("variant") else ""}</div>'
            f'{"<ul class=warn>" + reasons + "</ul>" if reasons else ""}<div>{res}</div>{caps}'
            f'<div class="muted" style="font-size:12px">id: {e(p["id"])}</div></div></div>')


def build():
    cfg = config()
    out = ROOT / "docs"
    out.mkdir(exist_ok=True)
    t = now().isoformat()
    sections = []
    for brand in cfg["brands"]:
        q = load_json(DATA / "queue" / f"{brand['id']}.json", [])
        up = [p for p in q if p["status"] in ("approved", "draft") and p.get("slot", "") >= t[:10]]
        held = [p for p in q if p["status"] == "needs_review"]
        done = sorted([p for p in q if p["status"] in ("posted", "partial")], key=lambda p: p["slot"], reverse=True)[:12]
        rv = load_json(DATA / "reviews" / f"{brand['id']}.json", {})
        waiting = [v for v in rv.values() if not v["replied"]]
        stats = load_json(DATA / "stats" / f"{brand['id']}.json", {})
        sections.append(
            f'<h2>{html.escape(brand["name"])} <span class="muted">({html.escape(brand["short"])})</span></h2>'
            f'<div class="stats"><div class="stat"><b>{len(up)}</b>scheduled</div><div class="stat"><b>{len(held)}</b>need your review</div>'
            f'<div class="stat"><b>{sum(1 for p in q if p["status"] == "posted")}</b>posted</div>'
            f'<div class="stat"><b>{len(waiting)}</b>review replies drafted</div></div>'
            + (f'<h3>Held for review (rules check)</h3><p class="muted">Approve with <code>python -m autopilot approve ID</code> after fixing the wording, or leave them.</p><div class="grid">{"".join(_card(p, brand) for p in held)}</div>' if held else "")
            + f'<h3>Coming up</h3><div class="grid">{"".join(_card(p, brand) for p in up) or "<p class=muted>Nothing planned yet.</p>"}</div>'
            + (f'<h3>Recently posted</h3><div class="grid">{"".join(_card(p, brand) for p in done)}</div>' if done else "")
            + (f'<h3>Top posts</h3><ol>{"".join(f"<li>{html.escape(h)} ({s})</li>" for s, h, _ in stats.get("top", [])[:5])}</ol>' if stats.get("top") else ""))
        _link_page(brand, q, out)
    page = (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>Social Autopilot</title><style>{CSS}</style></head><body><main><h1>Social Autopilot</h1>'
            f'<div class="muted">Updated {html.escape(_when(t))}</div>{"".join(sections)}</main></body></html>')
    (out / "index.html").write_text(page, encoding="utf-8")
    return out / "index.html"


def _link_page(brand, queue, out):
    posts = sorted([p for p in queue if p["status"] in ("posted", "partial")], key=lambda p: p["slot"], reverse=True)[:12]
    e = html.escape
    items = "".join(f'<a class="card" href="{e(p["url"])}" style="text-decoration:none;color:inherit">'
                    f'<img src="{_img(p["images"]["square"])}" alt=""><div class="b"><b>{e(p["headline"])}</b></div></a>' for p in posts)
    page = (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{e(brand["name"])} links</title><style>{CSS}</style></head><body><main style="max-width:640px">'
            f'<h1>{e(brand["name"])}</h1><p class="muted">{e(brand["location"])} · {e(brand["phone"])}</p>'
            f'<p><a href="{e(brand["cta_url"])}"><b>{e(brand["cta"])}</b></a> · <a href="{e(brand["site"])}">Website</a></p>'
            f'<div class="grid">{items or "<p class=muted>Posts will appear here.</p>"}</div>'
            f'<p class="muted" style="font-size:12px">{e(brand.get("disclaimer", ""))}</p></main></body></html>')
    (out / f"links-{brand['id']}.html").write_text(page, encoding="utf-8")
