import argparse, csv, datetime as dt, os, sys
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


def cmd_check(a):
    """Read-only test of each connection: looks up the account name and token permissions. Never posts."""
    from .util import env, http
    from .publish import GRAPH
    bad = 0
    for b in brands(a.brand):
        print(f"\n{b['name']}")
        page, token, ig = env(b["id"], "FB_PAGE_ID"), env(b["id"], "FB_TOKEN"), env(b["id"], "IG_USER_ID")
        if not (page and token):
            print("  facebook:  not connected")
            continue
        r = http().get(f"{GRAPH}/{page}", params={"fields": "name,instagram_business_account", "access_token": token}, timeout=30).json()
        if "error" in r:
            bad += 1
            print(f"  facebook:  ERROR {r['error'].get('message')}")
            continue
        print(f"  facebook:  OK, page '{r['name']}'")
        dbg = http().get(f"{GRAPH}/debug_token", params={"input_token": token, "access_token": token}, timeout=30).json().get("data", {})
        exp = dbg.get("expires_at", 0)
        print(f"  token:     {'never expires' if not exp else 'EXPIRES ' + dt.datetime.fromtimestamp(exp).isoformat()}")
        need = {"pages_manage_posts", "pages_read_engagement", "pages_manage_engagement", "instagram_basic",
                "instagram_content_publish", "instagram_manage_comments"}
        missing = need - set(dbg.get("scopes", []))
        if dbg.get("scopes") and missing:
            print(f"  missing permissions: {', '.join(sorted(missing))}")
        linked = (r.get("instagram_business_account") or {}).get("id")
        if not ig:
            print(f"  instagram: not connected{f' (linked account id is {linked})' if linked else ' (no Instagram business account linked to this Page)'}")
        else:
            j = http().get(f"{GRAPH}/{ig}", params={"fields": "username", "access_token": token}, timeout=30).json()
            if "error" in j:
                bad += 1
                print(f"  instagram: ERROR {j['error'].get('message')}")
            else:
                print(f"  instagram: OK, @{j['username']}")
    print("\nGoogle Business Profile")
    from .publish import _google_token, Skip
    for b in brands(a.brand):
        acct, loc = env(b["id"], "GBP_ACCOUNT_ID"), env(b["id"], "GBP_LOCATION_ID")
        if not (acct and loc):
            print(f"  {b['id']}: not connected")
            continue
        try:
            gt = _google_token(b)
            j = http().get(f"https://mybusinessbusinessinformation.googleapis.com/v1/locations/{loc}",
                           params={"readMask": "title"}, headers={"Authorization": f"Bearer {gt}"}, timeout=30).json()
            if "error" in j:
                raise RuntimeError(j["error"].get("message"))
            print(f"  {b['id']}: OK, listing '{j.get('title')}'")
        except Skip:
            print(f"  {b['id']}: not connected (sign-in key missing)")
        except Exception as e:
            bad += 1
            print(f"  {b['id']}: ERROR {e}")
    print("\nBluesky (shared)")
    bh, bp = os.environ.get("BLUESKY_HANDLE", "").strip(), os.environ.get("BLUESKY_APP_PASSWORD", "").strip()
    if not (bh and bp):
        print("  bluesky:   not connected")
    else:
        r = http().post("https://bsky.social/xrpc/com.atproto.server.createSession",
                        json={"identifier": bh, "password": bp}, timeout=30)
        if r.status_code == 200:
            print(f"  bluesky:   OK, @{r.json().get('handle')}")
        else:
            bad += 1
            print(f"  bluesky:   ERROR {r.status_code} {r.text[:120]}")
    print("\nThreads")
    for b in brands(a.brand):
        tt = env(b["id"], "THREADS_TOKEN")
        if not tt:
            print(f"  {b['id']}: not connected")
            continue
        j = http().get("https://graph.threads.net/v1.0/me", params={"fields": "username", "access_token": tt}, timeout=30).json()
        if "error" in j:
            bad += 1
            print(f"  {b['id']}: ERROR {j['error'].get('message')}")
        else:
            print(f"  {b['id']}: OK, @{j.get('username')}")
    token = os.environ.get("LINKEDIN_TOKEN", "").strip()
    print("\nLinkedIn (shared)")
    if not token:
        print("  linkedin:  not connected")
    else:
        from .publish import linkedin_person
        try:
            urn, name = linkedin_person(token)
            print(f"  linkedin:  OK, posting as {name} ({urn})")
        except Exception as e:
            bad += 1
            print(f"  linkedin:  ERROR {e}")
    if bad:
        sys.exit(1)


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
    sub.add_parser("check", help="test each connected account without posting").set_defaults(fn=cmd_check)
    a = ap.parse_args()
    DATA.mkdir(exist_ok=True)
    a.fn(a)
