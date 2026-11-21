"""Plans posts into the open schedule slots, writes the text for every platform, and makes the images."""
import datetime as dt, hashlib, json, os, random, re
from .util import DATA, load_json, save_json, log, now, tz, config, http
from . import compliance, images, seasons

DAYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
LOCAL_WORDS = ("county", "gulf", "fairhope", "pensacola", "mobile", "daphne", "foley", "orange-beach",
               "gulf-shores", "moving", "local", "alabama", "florida", "spanish-fort", "baldwin", "escambia")

HOOKS = {
    "faq": ["A question we hear all the time:", "Let's clear this one up:", "You asked, here's the straight answer:",
            "Quick answer to a common question:", "Wondering about this? You're not alone."],
    "tip": ["Quick tip:", "Worth knowing:", "Here's something most people miss:", "Save this for later:",
            "One thing to check this week:"],
    "spotlight": ["Have you seen this?", "Here's how we can help:", "Plain-English guide:", "Start here:"],
    "carousel": ["Swipe through the answers", "Your questions, answered", "The quick guide (swipe)"],
    "local": ["For our {location} neighbors:", "Local know-how for {location}:", "Living in {location}? Read this."],
    "new_page": ["New on our website:", "Just published:", "Fresh guide on the site:"],
    "updated_page": ["We just updated this guide:", "Updated with the latest info:"],
    "season": ["{label}:", "This time of year:", "Heads up for {label}:"],
}
GENERIC = {"sources", "references", "related", "related pages", "related guides", "faq", "faqs", "contact", "contact us",
           "about", "about us", "more", "next steps", "learn more", "resources", "summary", "in short", "disclaimer",
           "frequently asked questions", "official resources", "helpful links", "sources and references", "citations", "get started", "get a quote", "questions"}
VAGUE = {"it", "this", "that", "them", "these", "those", "here", "more"}
CTA_VARIANTS = ["{cta}", "Learn more", "Read the full guide", "Questions? Reach out anytime", "Get the details"]


def trim(text, limit):
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    cut = text[:limit]
    end = max(cut.rfind(". "), cut.rfind("? "), cut.rfind("! "))
    return cut[: end + 1] if end > limit * 0.5 else cut.rsplit(" ", 1)[0] + "..."


def short_headline(text, limit=80):
    text = re.sub(r"\s*[|–—-]\s*(Alabama Coastal Insurance|Fine Home Loan|hoinow\.com).*$", "", text).strip()
    return trim(text, limit).rstrip(".")


def slots(brand, days):
    """Upcoming publish times from the brand's weekly schedule (e.g. 'Tue 09:00')."""
    zone, start = tz(), now()
    best = best_hours(brand)
    out = []
    for d in range(days + 1):
        day = (start + dt.timedelta(days=d)).date()
        for s in brand["schedule"]:
            wd, hm = s.split()
            if DAYS[wd[:3].lower()] != day.weekday():
                continue
            h, m = map(int, hm.split(":"))
            if best:  # nudge toward the hour that has engaged best, within 3 hours
                near = min(best, key=lambda b: abs(b - h))
                if abs(near - h) <= 3:
                    h = near
            t = dt.datetime(day.year, day.month, day.day, h, m, tzinfo=zone)
            if t > start + dt.timedelta(minutes=30):
                out.append(t)
    return sorted(out)


def best_hours(brand):
    if not config()["settings"].get("learn_best_times"):
        return []
    stats = load_json(DATA / "stats" / f"{brand['id']}.json", {})
    hours = stats.get("by_hour", {})
    if sum(v["posts"] for v in hours.values()) < 10:
        return []
    ranked = sorted(hours.items(), key=lambda kv: kv[1]["engagement"] / max(kv[1]["posts"], 1), reverse=True)
    return [int(h) for h, _ in ranked[:3]]


def candidates(brand, store, kind):
    pages = list(store["pages"].values())
    out = []
    for p in pages:
        if kind == "faq":
            for f in p["faqs"]:
                out.append({"key": f"faq|{p['url']}|{f['q']}", "headline": f["q"], "body": f["a"], "page": p})
        elif kind == "tip":
            for s in p["sections"]:
                h = s["h"]
                if not h or len(" ".join(s["p"])) < 120 or h.endswith("?") or h.lower().strip(": ") in GENERIC:
                    continue
                words = h.lower().rstrip(".:").split()
                if len(words) < 4 or words[-1] in VAGUE:  # e.g. "Ways to plan for it" makes no sense alone
                    continue
                out.append({"key": f"tip|{p['url']}|{s['h']}", "headline": h, "body": " ".join(s["p"]), "page": p})
        elif kind == "spotlight":
            if p["description"]:
                out.append({"key": f"spot|{p['url']}", "headline": p["h1"], "body": p["description"], "page": p})
        elif kind == "carousel":
            if len(p["faqs"]) >= 3:
                out.append({"key": f"car|{p['url']}", "headline": p["h1"], "body": p["description"] or p["faqs"][0]["a"],
                            "page": p, "slides": [{"h": f["q"], "t": trim(f["a"], 260)} for f in p["faqs"][:5]]})
        elif kind == "local":
            if any(w in p["url"].lower() for w in LOCAL_WORDS) and p["description"]:
                out.append({"key": f"local|{p['url']}", "headline": p["h1"], "body": p["description"], "page": p})
    return out


def headkey(text):
    return "head|" + re.sub(r"[^a-z0-9]", "", text.lower())[:60]


def pick(cands, history, recycle_days, taken):
    cands = [c for c in cands if headkey(c["headline"]) not in taken]  # same question on two pages -> post once
    fresh = [c for c in cands if c["key"] not in history and c["key"] not in taken]
    if fresh:
        return random.choice(fresh), 0
    cutoff = (now() - dt.timedelta(days=recycle_days)).isoformat()
    old = [c for c in cands if c["key"] not in taken and history.get(c["key"], {}).get("last", "") < cutoff]
    if old:
        # FeedHive-style: recycle the best performers first
        old.sort(key=lambda c: (-history[c["key"]].get("score", 0), history[c["key"]]["last"]))
        c = old[0]
        return c, history[c["key"]].get("uses", 1)
    return None, 0


def fill(template, brand, label=""):
    return template.format(location=brand.get("location", ""), label=label, cta=brand["cta"])


def build_post(brand, cand, kind, slot, variant):
    seed = int(hashlib.md5(f"{cand['key']}{variant}".encode()).hexdigest(), 16)
    rnd = random.Random(seed)
    hook = "" if kind == "season" else fill(rnd.choice(HOOKS[kind]), brand, cand.get("label", ""))
    page = cand.get("page") or {}
    post = {
        "id": f"{brand['id']}-{slot.strftime('%Y%m%d-%H%M')}",
        "brand": brand["id"],
        "slot": slot.isoformat(),
        "kind": kind,
        "source_key": cand["key"],
        "variant": variant,
        "hook": hook,
        "headline": short_headline(cand["headline"]),
        "body": trim(cand["body"], 420),
        "url": cand.get("url") or page.get("url") or brand["site"],
        "label": cand.get("label") or {"faq": "FAQ", "tip": "TIP", "spotlight": "GUIDE", "carousel": "SWIPE",
                                         "local": "LOCAL", "new_page": "NEW", "updated_page": "UPDATED"}.get(kind, "TIP"),
        "slides": cand.get("slides", []),
        "photo": page.get("image", ""),
        "cta": fill(rnd.choice(CTA_VARIANTS), brand) if variant else brand["cta"],
        "hashtags": rnd.sample(brand["hashtags"], k=min(5, len(brand["hashtags"]))),
        "created_at": now().isoformat(timespec="seconds"),
        "created_run": run_id(),
        "results": {},
    }
    if config()["settings"].get("ai") == "gemini" and os.environ.get("GEMINI_API_KEY"):
        ai_polish(post, brand)
    return post


def ai_polish(post, brand):
    """Optional: Google's free Gemini tier rewrites the text in a friendlier voice. Rules check still runs after."""
    s = config()["settings"]
    prompt = (
        f"You write social posts for {brand['name']} ({brand['industry']}, {brand['location']}) for {brand['audience']}. "
        "Rewrite the post below: warm, plain English, short sentences, no emojis in the headline, no hype. "
        "Never promise approval, rates, savings, prices or coverage. Never add numbers, rates, percentages or dollar amounts "
        "that are not in the source. Keep every fact from the source and add none. "
        'Return JSON {"hook": str (under 60 chars), "headline": str (under 70 chars), "body": str (under 380 chars)}.\n\n'
        + json.dumps({"hook": post["hook"], "headline": post["headline"], "body": post["body"]})
    )
    try:
        r = http().post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{s.get('gemini_model', 'gemini-flash-latest')}:generateContent",
            params={"key": os.environ["GEMINI_API_KEY"]},
            json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"responseMimeType": "application/json"}},
            timeout=60,
        )
        r.raise_for_status()
        out = json.loads(r.json()["candidates"][0]["content"]["parts"][0]["text"])
        for k in ("hook", "headline", "body"):
            if isinstance(out.get(k), str) and out[k].strip():
                post[k] = out[k].strip()
        post["ai"] = True
    except Exception as e:
        log(f"[{brand['id']}] AI rewrite skipped: {e}")


def captions(post, brand):
    disc = brand.get("disclaimer", "")
    short_disc = brand.get("short_disclaimer", disc)
    tags = " ".join(post["hashtags"])
    first_comment = config()["settings"].get("first_comment", True)
    core = f"{post['hook']}\n\n{post['headline']}\n\n{post['body']}"
    if post["slides"]:
        core += "\n\n" + "\n".join(f"- {s['h']}" for s in post["slides"])
    link_line = f"{post['cta']}: {post['url']}"
    c = {
        "facebook": {"text": f"{core}\n\n{link_line}\nCall {brand['phone']}\n\n{disc}\n\n{' '.join(post['hashtags'][:3])}"},
        "instagram": {"text": f"{core}\n\nLink in bio, or visit {brand['short']}\nCall {brand['phone']}\n\n{disc}\n.\n{tags}"},
        "linkedin": {"text": f"{post['headline']}\n\n{post['body']}\n\n{link_line}\n\n{disc}\n\n{' '.join(post['hashtags'][:3])}"},
        "google_business": {"text": compliance.scrub_for_google(f"{post['headline']}\n\n{post['body']}\n\n{disc}")[:1450],
                            "button": "LEARN_MORE", "link": post["url"]},
        "pinterest": {"title": post["headline"][:100],
                      "text": trim(f"{post['body']} {brand['name']}, {brand['location']}. {short_disc}", 490), "link": post["url"]},
        "threads": {"text": trim(f"{post['headline']}\n\n{post['body']}", 400 - len(short_disc)) + f"\n\n{short_disc}"},
        "bluesky": {"text": _bsky(post, short_disc), "link": post["url"]},
    }
    if first_comment:
        for p in ("instagram", "facebook", "threads"):
            c[p]["first_comment"] = f"{link_line}"
    return c


def _bsky(post, disc):
    room = 300 - len(disc) - len(post["url"]) - 6
    return f"{trim(post['headline'] + '. ' + post['body'], room)}\n{post['url']}\n{disc}"


def run_id():
    return os.environ.get("GITHUB_RUN_ID") or os.environ.get("AUTOPILOT_RUN_ID") or "local"


def plan_brand(brand, store):
    s = config()["settings"]
    qpath = DATA / "queue" / f"{brand['id']}.json"
    queue = load_json(qpath, [])
    hist_path = DATA / "history" / f"{brand['id']}.json"
    history = load_json(hist_path, {})
    taken_slots = {p["slot"] for p in queue if p.get("slot")}
    taken_keys = {p["source_key"] for p in queue if p["status"] in ("approved", "scheduled", "needs_review", "draft")}
    recent = (now() - dt.timedelta(days=s.get("recycle_after_days", 45))).isoformat()
    taken_keys |= {headkey(p["headline"]) for p in queue if p["status"] != "skipped" and (p.get("slot") or "9") > recent}
    made = held = 0
    new_this_week = sum(1 for p in queue if p["kind"] in ("new_page", "updated_page")
                        and p["slot"] > (now() - dt.timedelta(days=7)).isoformat())
    mix = brand.get("mix", ["faq", "tip", "spotlight"])
    for i, slot in enumerate(slots(brand, s.get("days_ahead", 14))):
        if slot.isoformat() in taken_slots:
            continue
        options = []
        # 1. new or changed website pages go first (Publer/FeedHive-style auto-posting from your site)
        if store.get("fresh") and new_this_week < s.get("max_new_page_posts_per_week", 3):
            f = store["fresh"][0]
            page = store["pages"].get(f["url"])
            if page:
                kind = "new_page" if f["kind"] == "new" else "updated_page"
                options.append((kind, {"key": f"{kind}|{f['url']}|{f['at']}", "headline": page["h1"],
                                       "body": page["description"] or (page["sections"][0]["p"][0] if page["sections"] else ""),
                                       "page": page}, 0))
        # 2. seasonal / holiday posts (Loomly-style calendar)
        for ev in seasons.due(brand["industry"], slot.date()):
            key = f"season|{ev['key']}|{slot.year}"
            if key not in history and key not in taken_keys:
                page = seasons.best_page(store, ev.get("match", []))
                options.append(("season", {"key": key, "headline": ev["headline"], "body": ev["body"], "label": ev["label"],
                                           "page": page, "url": page["url"] if page else brand["site"]}, 0))
        # 3. the normal content mix (SocialBee-style categories, evergreen recycling)
        for k in range(len(mix)):
            kind = mix[(i + k) % len(mix)]
            cand, uses = pick(candidates(brand, store, kind), history, s.get("recycle_after_days", 45), taken_keys)
            if cand:
                options.append((kind, cand, uses))
        for kind, cand, variant in options:
            post = build_post(brand, cand, kind, slot, variant)
            reasons = compliance.check(" ".join([post["hook"], post["headline"], post["body"]]
                                                + [x["h"] + " " + x["t"] for x in post["slides"]]), brand["industry"])
            if reasons:
                post.update(status="needs_review", hold_reasons=reasons, slot=None, id=f"{brand['id']}-held-{hashlib.md5(post['source_key'].encode()).hexdigest()[:8]}")
                if post["source_key"] not in {p["source_key"] for p in queue}:
                    post["captions"] = captions(post, brand)
                    images.render(post, brand)
                    queue.append(post)
                    held += 1
                taken_keys.add(post["source_key"])
                continue
            post["status"] = "approved" if s.get("approval", "auto") == "auto" else "draft"
            post["captions"] = captions(post, brand)
            images.render(post, brand)
            queue.append(post)
            taken_keys.add(post["source_key"])
            taken_keys.add(headkey(cand["headline"]))
            taken_slots.add(post["slot"])
            if kind in ("new_page", "updated_page"):
                store["fresh"].pop(0)
                new_this_week += 1
                save_json(DATA / "pages" / f"{brand['id']}.json", store)
            made += 1
            break
    queue.sort(key=lambda p: p.get("slot") or "9999")
    save_json(qpath, queue)
    log(f"[{brand['id']}] planned {made} posts, held {held} for review, queue size {len(queue)}")
    return queue
