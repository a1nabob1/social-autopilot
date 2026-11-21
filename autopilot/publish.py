"""Posts due items to every connected platform using each platform's own free API.
A platform with no token is skipped and the post is saved to data/outbox so nothing is lost."""
import datetime as dt, json, os, time
from pathlib import Path
from .util import DATA, ROOT, http, env, load_json, save_json, log, now, config
from .generate import run_id

GRAPH = "https://graph.facebook.com/v21.0"
MAX_TRIES = 3


class Skip(Exception):
    pass


def public_url(rel):
    base = config()["settings"].get("public_base_url", "").rstrip("/")
    if not base:
        raise Skip("needs public_base_url in config.toml (Instagram/Pinterest/Google/Threads need an image web address)")
    return f"{base}/{rel}"


def _check(r):
    if r.status_code >= 400:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:300]}")
    return r.json() if r.content else {}


# ---------------- Facebook Page ----------------
_page_tokens = {}


def page_token(page, token):
    """A system-user key can act for the Page; Facebook posts need the Page's own key, which it hands back."""
    if page not in _page_tokens:
        j = http().get(f"{GRAPH}/{page}", params={"fields": "access_token", "access_token": token}, timeout=30).json()
        _page_tokens[page] = j.get("access_token") or token
    return _page_tokens[page]


def facebook(post, brand, cap):
    page, token = env(brand["id"], "FB_PAGE_ID"), env(brand["id"], "FB_TOKEN")
    if not (page and token):
        raise Skip("not connected")
    token = page_token(page, token)
    files = post["images"].get("slides") or [post["images"]["square"]]
    ids = []
    for f in files:  # upload full-size originals (no compression by us)
        with open(ROOT / f, "rb") as fh:
            j = _check(http().post(f"{GRAPH}/{page}/photos", data={"published": "false", "access_token": token},
                                   files={"source": fh}, timeout=120))
        ids.append(j["id"])
    data = {"message": cap["text"], "access_token": token}
    for i, pid in enumerate(ids):
        data[f"attached_media[{i}]"] = json.dumps({"media_fbid": pid})
    j = _check(http().post(f"{GRAPH}/{page}/feed", data=data, timeout=60))
    if cap.get("first_comment"):
        try:
            _check(http().post(f"{GRAPH}/{j['id']}/comments", data={"message": cap["first_comment"], "access_token": token}, timeout=30))
        except Exception as e:
            log(f"  facebook first comment failed: {e}")
    return {"id": j["id"], "url": f"https://facebook.com/{j['id']}"}


# ---------------- Instagram (business account linked to the Page) ----------------
def instagram(post, brand, cap):
    ig, token = env(brand["id"], "IG_USER_ID"), env(brand["id"], "FB_TOKEN")
    if not (ig and token):
        raise Skip("not connected")
    slides = post["images"].get("slides")
    if slides:
        kids = [_check(http().post(f"{GRAPH}/{ig}/media", data={"image_url": public_url(s), "is_carousel_item": "true",
                                                                "access_token": token}, timeout=60))["id"] for s in slides]
        cid = _check(http().post(f"{GRAPH}/{ig}/media", data={"media_type": "CAROUSEL", "children": ",".join(kids),
                                                              "caption": cap["text"], "access_token": token}, timeout=60))["id"]
    else:
        cid = _check(http().post(f"{GRAPH}/{ig}/media", data={"image_url": public_url(post["images"]["square"]),
                                                              "caption": cap["text"], "access_token": token}, timeout=60))["id"]
    for _ in range(12):  # wait for Instagram to finish processing
        st = _check(http().get(f"{GRAPH}/{cid}", params={"fields": "status_code", "access_token": token}, timeout=30))
        if st.get("status_code") in ("FINISHED", None):
            break
        if st.get("status_code") == "ERROR":
            raise RuntimeError("Instagram could not process the image")
        time.sleep(5)
    j = _check(http().post(f"{GRAPH}/{ig}/media_publish", data={"creation_id": cid, "access_token": token}, timeout=60))
    if cap.get("first_comment"):
        try:
            _check(http().post(f"{GRAPH}/{j['id']}/comments", data={"message": cap["first_comment"], "access_token": token}, timeout=30))
        except Exception as e:
            log(f"  instagram first comment failed: {e}")
    return {"id": j["id"]}


# ---------------- LinkedIn (company page or personal profile) ----------------
def linkedin(post, brand, cap):
    token, author = env(brand["id"], "LINKEDIN_TOKEN"), env(brand["id"], "LINKEDIN_AUTHOR")  # urn:li:organization:123 or urn:li:person:abc
    if not (token and author):
        raise Skip("not connected")
    h = {"Authorization": f"Bearer {token}", "LinkedIn-Version": os.environ.get("LINKEDIN_VERSION", "202510"),
         "X-Restli-Protocol-Version": "2.0.0", "Content-Type": "application/json"}
    init = _check(http().post("https://api.linkedin.com/rest/images?action=initializeUpload", headers=h,
                              json={"initializeUploadRequest": {"owner": author}}, timeout=30))["value"]
    with open(ROOT / post["images"]["square"], "rb") as fh:
        up = http().put(init["uploadUrl"], data=fh.read(), headers={"Authorization": f"Bearer {token}"}, timeout=120)
    if up.status_code >= 400:
        raise RuntimeError(f"LinkedIn image upload {up.status_code}")
    body = {"author": author, "commentary": _li_escape(cap["text"]), "visibility": "PUBLIC",
            "distribution": {"feedDistribution": "MAIN_FEED", "targetEntities": [], "thirdPartyDistributionChannels": []},
            "content": {"media": {"id": init["image"], "altText": post["headline"][:300]}},
            "lifecycleState": "PUBLISHED", "isReshareDisabledByAuthor": False}
    r = http().post("https://api.linkedin.com/rest/posts", headers=h, json=body, timeout=60)
    _check(r)
    return {"id": r.headers.get("x-restli-id", "")}


def _li_escape(text):
    """LinkedIn's post text format treats these characters as markup, so they must be escaped."""
    for ch in "\\|{}@[]()<>#*_~":
        text = text.replace(ch, "\\" + ch)
    return text


# ---------------- Google Business Profile ----------------
def _google_token(brand):
    cid, secret = os.environ.get("GOOGLE_CLIENT_ID", ""), os.environ.get("GOOGLE_CLIENT_SECRET", "")
    refresh = env(brand["id"], "GBP_REFRESH_TOKEN") or os.environ.get("GOOGLE_REFRESH_TOKEN", "")
    if not (cid and secret and refresh):
        raise Skip("not connected")
    return _check(http().post("https://oauth2.googleapis.com/token", data={"client_id": cid, "client_secret": secret,
                                                                          "refresh_token": refresh, "grant_type": "refresh_token"}, timeout=30))["access_token"]


def google_business(post, brand, cap):
    acct, loc = env(brand["id"], "GBP_ACCOUNT_ID"), env(brand["id"], "GBP_LOCATION_ID")
    if not (acct and loc):
        raise Skip("not connected")
    token = _google_token(brand)
    body = {"languageCode": "en-US", "summary": cap["text"], "topicType": "STANDARD",
            "callToAction": {"actionType": cap.get("button", "LEARN_MORE"), "url": cap["link"]},
            "media": [{"mediaFormat": "PHOTO", "sourceUrl": public_url(post["images"]["square"])}]}
    j = _check(http().post(f"https://mybusiness.googleapis.com/v4/accounts/{acct}/locations/{loc}/localPosts",
                           headers={"Authorization": f"Bearer {token}"}, json=body, timeout=60))
    return {"id": j.get("name", ""), "url": j.get("searchUrl", "")}


# ---------------- Pinterest ----------------
def pinterest(post, brand, cap):
    token, board = env(brand["id"], "PINTEREST_TOKEN"), env(brand["id"], "PINTEREST_BOARD_ID")
    if not (token and board):
        raise Skip("not connected")
    j = _check(http().post("https://api.pinterest.com/v5/pins", headers={"Authorization": f"Bearer {token}"},
                           json={"board_id": board, "title": cap["title"], "description": cap["text"], "link": cap["link"],
                                 "alt_text": post["headline"][:500],
                                 "media_source": {"source_type": "image_url", "url": public_url(post["images"]["pin"])}}, timeout=60))
    return {"id": j["id"], "url": f"https://www.pinterest.com/pin/{j['id']}/"}


# ---------------- Threads ----------------
def threads(post, brand, cap):
    uid, token = env(brand["id"], "THREADS_USER_ID"), env(brand["id"], "THREADS_TOKEN")
    if not (uid and token):
        raise Skip("not connected")
    base = "https://graph.threads.net/v1.0"
    cid = _check(http().post(f"{base}/{uid}/threads", data={"media_type": "IMAGE", "image_url": public_url(post["images"]["square"]),
                                                            "text": cap["text"], "access_token": token}, timeout=60))["id"]
    time.sleep(20)  # Threads asks for a short wait before publishing
    j = _check(http().post(f"{base}/{uid}/threads_publish", data={"creation_id": cid, "access_token": token}, timeout=60))
    if cap.get("first_comment"):
        try:
            rid = _check(http().post(f"{base}/{uid}/threads", data={"media_type": "TEXT", "text": cap["first_comment"],
                                                                    "reply_to_id": j["id"], "access_token": token}, timeout=60))["id"]
            time.sleep(5)
            _check(http().post(f"{base}/{uid}/threads_publish", data={"creation_id": rid, "access_token": token}, timeout=60))
        except Exception as e:
            log(f"  threads reply failed: {e}")
    return {"id": j["id"]}


# ---------------- Bluesky ----------------
def bluesky(post, brand, cap):
    handle, pw = env(brand["id"], "BLUESKY_HANDLE"), env(brand["id"], "BLUESKY_APP_PASSWORD")
    if not (handle and pw):
        raise Skip("not connected")
    pds = "https://bsky.social/xrpc"
    sess = _check(http().post(f"{pds}/com.atproto.server.createSession", json={"identifier": handle, "password": pw}, timeout=30))
    h = {"Authorization": f"Bearer {sess['accessJwt']}"}
    raw = (ROOT / post["images"]["square"]).read_bytes()
    if len(raw) > 950_000:  # Bluesky's image limit is ~1 MB
        from PIL import Image
        import io
        buf = io.BytesIO()
        Image.open(io.BytesIO(raw)).convert("RGB").save(buf, "JPEG", quality=90)
        raw, mime = buf.getvalue(), "image/jpeg"
    else:
        mime = "image/png"
    blob = _check(http().post(f"{pds}/com.atproto.repo.uploadBlob", headers={**h, "Content-Type": mime}, data=raw, timeout=60))["blob"]
    text = cap["text"]
    start = text.encode().find(cap["link"].encode())
    facets = [] if start < 0 else [{"index": {"byteStart": start, "byteEnd": start + len(cap["link"].encode())},
                                    "features": [{"$type": "app.bsky.richtext.facet#link", "uri": cap["link"]}]}]
    rec = {"$type": "app.bsky.feed.post", "text": text, "facets": facets, "createdAt": dt.datetime.utcnow().isoformat() + "Z",
           "embed": {"$type": "app.bsky.embed.images", "images": [{"alt": post["headline"], "image": blob}]}}
    j = _check(http().post(f"{pds}/com.atproto.repo.createRecord", headers=h,
                           json={"repo": sess["did"], "collection": "app.bsky.feed.post", "record": rec}, timeout=30))
    return {"id": j["uri"], "url": f"https://bsky.app/profile/{handle}/post/{j['uri'].rsplit('/', 1)[-1]}"}


POSTERS = {"facebook": facebook, "instagram": instagram, "linkedin": linkedin, "google_business": google_business,
           "pinterest": pinterest, "threads": threads, "bluesky": bluesky}


def publish_brand(brand, dry_run=False):
    qpath = DATA / "queue" / f"{brand['id']}.json"
    queue = load_json(qpath, [])
    hist_path = DATA / "history" / f"{brand['id']}.json"
    history = load_json(hist_path, {})
    t = now()
    sent = 0
    for post in queue:
        if post["status"] not in ("approved", "partial") or not post.get("slot"):
            continue
        if dt.datetime.fromisoformat(post["slot"]) > t:
            continue
        if post.get("created_run") == run_id() and run_id() != "local":
            continue  # images were made in this run and aren't online yet; next run will post it
        log(f"[{brand['id']}] publishing {post['id']}: {post['headline']}")
        for platform in brand["platforms"]:
            res = post["results"].get(platform, {})
            if res.get("ok") or res.get("tries", 0) >= MAX_TRIES:
                continue
            if dry_run:
                _outbox(post, platform)
                post["results"][platform] = {"ok": False, "skipped": "dry run (saved to outbox)"}
                continue
            try:
                out = POSTERS[platform](post, brand, post["captions"][platform])
                post["results"][platform] = {"ok": True, "at": t.isoformat(timespec="seconds"), **out}
                log(f"  {platform}: posted {out.get('url', out.get('id', ''))}")
            except Skip as e:
                _outbox(post, platform)
                post["results"][platform] = {"ok": False, "skipped": str(e)}
                log(f"  {platform}: skipped ({e})")
            except Exception as e:
                post["results"][platform] = {"ok": False, "error": str(e)[:400], "tries": res.get("tries", 0) + 1}
                log(f"  {platform}: FAILED ({e})")
        failed = [p for p, r in post["results"].items() if r.get("error") and r.get("tries", 0) < MAX_TRIES]
        if not any(r.get("ok") for r in post["results"].values()) and not failed:
            post["status"] = "outbox"  # nothing is connected yet: copy is in data/outbox, content stays fresh
            log("  nothing connected - saved to data/outbox for manual posting")
            continue
        post["status"] = "partial" if failed else "posted"
        post["posted_at"] = t.isoformat(timespec="seconds")
        h = history.setdefault(post["source_key"], {"uses": 0})
        if not post.get("counted"):
            h["uses"] = h.get("uses", 0) + 1
            post["counted"] = True
        h["last"] = post["posted_at"]
        sent += 1
    save_json(qpath, queue)
    save_json(hist_path, history)
    return sent


def _outbox(post, platform):
    d = DATA / "outbox" / post["brand"]
    d.mkdir(parents=True, exist_ok=True)
    cap = post["captions"][platform]
    img = post["images"]["pin" if platform == "pinterest" else "square"]
    (d / f"{post['id']}-{platform}.txt").write_text(
        f"PLATFORM: {platform}\nWHEN: {post['slot']}\nIMAGE: {img}\n\n" + "\n\n".join(f"[{k}]\n{v}" for k, v in cap.items()),
        encoding="utf-8")
