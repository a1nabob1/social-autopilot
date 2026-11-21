"""Google review manager: pulls new Google reviews and drafts a reply for each one.
Replies are only posted automatically if you turn on auto_reply_reviews for 4-5 star reviews."""
import os, random
from .util import DATA, http, env, load_json, save_json, log, config
from .publish import _google_token, Skip

POSITIVE = ["Thank you so much, {name}! We're glad we could help, and we're always here if you need anything.",
            "{name}, thank you for the kind words! It was a pleasure working with you.",
            "We really appreciate you taking the time to share this, {name}. Thank you for trusting us!"]
NEUTRAL = ["Thank you for the feedback, {name}. We'd like to hear more about how we can do better. Please give us a call at {phone}."]
NEGATIVE = ["{name}, we're sorry to hear about your experience. We want to make this right. Please call us at {phone} so we can talk it through."]
STARS = {"ONE": 1, "TWO": 2, "THREE": 3, "FOUR": 4, "FIVE": 5}


def run_brand(brand):
    acct, loc = env(brand["id"], "GBP_ACCOUNT_ID"), env(brand["id"], "GBP_LOCATION_ID")
    if not (acct and loc):
        return
    try:
        token = _google_token(brand)
    except Skip:
        return
    base = f"https://mybusiness.googleapis.com/v4/accounts/{acct}/locations/{loc}/reviews"
    r = http().get(base, headers={"Authorization": f"Bearer {token}"}, params={"pageSize": 50}, timeout=30)
    if r.status_code >= 400:
        log(f"[{brand['id']}] reviews failed: {r.status_code} {r.text[:200]}")
        return
    path = DATA / "reviews" / f"{brand['id']}.json"
    store = load_json(path, {})
    auto = brand.get("auto_reply_reviews", False)
    for rv in r.json().get("reviews", []):
        rid = rv["reviewId"]
        stars = STARS.get(rv.get("starRating"), 0)
        name = (rv.get("reviewer", {}).get("displayName") or "there").split()[0]
        if rid in store or rv.get("reviewReply"):
            continue
        pool = POSITIVE if stars >= 4 else NEUTRAL if stars == 3 else NEGATIVE
        draft = random.choice(pool).format(name=name, phone=brand["phone"])
        item = {"stars": stars, "name": name, "comment": rv.get("comment", ""), "draft": draft, "replied": False}
        if auto and stars >= 4:
            pr = http().put(f"{base}/{rid}/reply", headers={"Authorization": f"Bearer {token}"}, json={"comment": draft}, timeout=30)
            item["replied"] = pr.status_code < 400
        store[rid] = item
    save_json(path, store)
    log(f"[{brand['id']}] reviews: {sum(1 for v in store.values() if not v['replied'])} drafts waiting")
