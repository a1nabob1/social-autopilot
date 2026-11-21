"""Learns from results (Metricool/FeedHive-style): pulls likes/comments/shares for posted items, scores each
piece of content so the best ones get recycled first, and tracks which hours get the most engagement."""
import datetime as dt
from .util import DATA, http, env, load_json, save_json, log
from .publish import GRAPH


def _fb(post_id, token):
    j = http().get(f"{GRAPH}/{post_id}", params={"fields": "reactions.summary(true),comments.summary(true),shares",
                                                 "access_token": token}, timeout=30).json()
    return (j.get("reactions", {}).get("summary", {}).get("total_count", 0)
            + 2 * j.get("comments", {}).get("summary", {}).get("total_count", 0)
            + 3 * j.get("shares", {}).get("count", 0))


def _ig(media_id, token):
    j = http().get(f"{GRAPH}/{media_id}", params={"fields": "like_count,comments_count", "access_token": token}, timeout=30).json()
    return j.get("like_count", 0) + 2 * j.get("comments_count", 0)


def update_brand(brand):
    token = env(brand["id"], "FB_TOKEN")
    if not token:
        return
    queue = load_json(DATA / "queue" / f"{brand['id']}.json", [])
    history = load_json(DATA / "history" / f"{brand['id']}.json", {})
    stats = {"by_hour": {}, "updated": dt.datetime.now().isoformat(timespec="seconds"), "top": []}
    scored = []
    for post in queue:
        if post["status"] not in ("posted", "partial"):
            continue
        score = 0
        try:
            if post["results"].get("facebook", {}).get("ok"):
                score += _fb(post["results"]["facebook"]["id"], token)
            if post["results"].get("instagram", {}).get("ok"):
                score += _ig(post["results"]["instagram"]["id"], token)
        except Exception as e:
            log(f"[{brand['id']}] insights failed for {post['id']}: {e}")
            continue
        post["engagement"] = score
        hour = str(dt.datetime.fromisoformat(post["slot"]).hour)
        b = stats["by_hour"].setdefault(hour, {"posts": 0, "engagement": 0})
        b["posts"] += 1
        b["engagement"] += score
        if post["source_key"] in history:
            history[post["source_key"]]["score"] = max(history[post["source_key"]].get("score", 0), score)
        scored.append((score, post["headline"], post["id"]))
    stats["top"] = sorted(scored, reverse=True)[:10]
    save_json(DATA / "stats" / f"{brand['id']}.json", stats)
    save_json(DATA / "history" / f"{brand['id']}.json", history)
    save_json(DATA / "queue" / f"{brand['id']}.json", queue)
    log(f"[{brand['id']}] engagement updated for {len(scored)} posts")
