import argparse, csv, datetime as dt, sys
from .util import DATA, load_env, config, load_json, save_json, log, tz, now
from . import crawl, generate, publish, dashboard, insights, reviews, watch, images


def brands(only=None):
    out = []
    for b in config()["brands"]:
        if only and b["id"] != only:
            continue
        store = load_json(DATA / "pages" / f"{b['id']}.json", {"pages": {}})
        home = store["pages"].get(b["site"].rstrip("/") + "/") or next(iter(store["pages"].values()), {})
        b["_icon"] = home.get("icon", "")
        out.append(b)
    return out


def cmd_run(a):
    for b in brands(a.brand):
        store = crawl.crawl_brand(b)
        b["_icon"] = b["_icon"] or next((p.get("icon") for p in store["pages"].values() if p.get("icon")), "")
        generate.plan_brand(b, store)
        publish.publish_brand(b, dry_run=a.dry_run)
        try:
            insights.update_brand(b)
            reviews.run_brand(b)
        except Exception as e:
            log(f"[{b['id']}] extras failed: {e}")
    log(f"dashboard: {dashboard.build()}")


def cmd_crawl(a):
    for b in brands(a.brand):
        crawl.crawl_brand(b)


def cmd_plan(a):
    for b in brands(a.brand):
        generate.plan_brand(b, load_json(DATA / "pages" / f"{b['id']}.json", {"pages": {}, "fresh": []}))
    dashboard.build()


def cmd_publish(a):
    for b in brands(a.brand):
        publish.publish_brand(b, dry_run=a.dry_run)
    dashboard.build()


def _find(pid):
    for b in brands():
        path = DATA / "queue" / f"{b['id']}.json"
        q = load_json(path, [])
        for p in q:
            if p["id"] == pid:
                return b, q, p, path
    sys.exit(f"No post with id {pid}")


def cmd_approve(a):
    b, q, p, path = _find(a.id)
    if not p.get("slot"):
        taken = {x.get("slot") for x in q}
        free = [s for s in generate.slots(b, 30) if s.isoformat() not in taken]
        if not free:
            sys.exit("No open slot in the next 30 days")
        p["slot"] = free[0].isoformat()
    p["status"] = "approved"
    p["approved_by_you"] = True
    save_json(path, q)
    dashboard.build()
    print(f"Approved {p['id']} for {p['slot']}")


def cmd_skip(a):
    b, q, p, path = _find(a.id)
    p["status"] = "skipped"
    save_json(path, q)
    dashboard.build()
    print(f"Skipped {p['id']}")


def cmd_import(a):
    """Bulk add your own posts from a CSV: brand,when(YYYY-MM-DD HH:MM),headline,body,url,image(optional)"""
    added = 0
    by_id = {b["id"]: b for b in brands()}
    with open(a.csv, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            b = by_id[row["brand"].strip()]
            slot = dt.datetime.strptime(row["when"].strip(), "%Y-%m-%d %H:%M").replace(tzinfo=tz())
            cand = {"key": f"csv|{row['headline']}", "headline": row["headline"], "body": row["body"],
                    "url": row.get("url") or b["site"], "page": {"image": row.get("image", "")}}
            post = generate.build_post(b, cand, "spotlight", slot, 0)
            from . import compliance
            reasons = compliance.check(post["headline"] + " " + post["body"], b["industry"])
            post["status"] = "needs_review" if reasons else "approved"
            post["hold_reasons"] = reasons
            post["captions"] = generate.captions(post, b)
            images.render(post, b)
            path = DATA / "queue" / f"{b['id']}.json"
            q = load_json(path, [])
            q.append(post)
            save_json(path, sorted(q, key=lambda p: p.get("slot") or "9999"))
            added += 1
    dashboard.build()
    print(f"Imported {added} posts")


def cmd_status(a):
    for b in brands(a.brand):
        q = load_json(DATA / "queue" / f"{b['id']}.json", [])
        print(f"\n{b['name']}")
        for p in q:
            if p["status"] in ("approved", "draft", "needs_review", "partial"):
                print(f"  {p['status']:13} {(p.get('slot') or '-')[:16]:16} {p['id']:32} {p['headline'][:60]}")


def main():
    load_env()
    ap = argparse.ArgumentParser(prog="python -m autopilot", description="Free social media autopilot")
    ap.add_argument("--brand", help="only this brand id (hoinow or finehomeloan)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, fn, hlp in [("run", cmd_run, "crawl + plan + post + learn + dashboard (what the schedule runs)"),
                          ("crawl", cmd_crawl, "read the websites"), ("plan", cmd_plan, "fill open schedule slots"),
                          ("publish", cmd_publish, "post anything that is due"), ("status", cmd_status, "list the queue")]:
        p = sub.add_parser(name, help=hlp)
        p.set_defaults(fn=fn)
        if name in ("run", "publish"):
            p.add_argument("--dry-run", action="store_true", help="don't post; write to data/outbox")
    p = sub.add_parser("approve", help="approve a held or draft post")
    p.add_argument("id"); p.set_defaults(fn=cmd_approve)
    p = sub.add_parser("skip", help="never post this one")
    p.add_argument("id"); p.set_defaults(fn=cmd_skip)
    p = sub.add_parser("import", help="bulk add posts from a CSV file")
    p.add_argument("csv"); p.set_defaults(fn=cmd_import)
    sub.add_parser("watch", help="check Marky and competitors for new features").set_defaults(fn=lambda a: watch.run())
    sub.add_parser("dashboard", help="rebuild docs/index.html").set_defaults(fn=lambda a: print(dashboard.build()))
    a = ap.parse_args()
    DATA.mkdir(exist_ok=True)
    a.fn(a)
