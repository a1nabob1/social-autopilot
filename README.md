# Social Autopilot

This is a free, self-running replacement for Marky, built for **hoinow.com** (Alabama Coastal Insurance) and **finehomeloan.com** (Fine Home Loan).

Every hour it does the following:

1. **Reads both websites** from their sitemaps. It learns every page, FAQ, section and photo, and notices new or changed pages.
2. **Plans two weeks of posts** into your weekly time slots. The plan mixes FAQs, tips, guides, carousels, local posts, new-page announcements and seasonal posts. Older posts are recycled, reworded, with the best performers first.
3. **Checks every post against advertising rules.** Mortgage posts with a Reg Z trigger term (a rate, a payment amount or a down payment) are held for your review instead of posting, and so are promise words like "guaranteed" or "lowest". The NMLS and Equal Housing line is added to every mortgage post.
4. **Makes branded images** in your colors, logo and page photos: a square post, a Pinterest pin and carousel slides.
5. **Posts what's due** to Facebook, Instagram, LinkedIn, Google Business Profile, Pinterest, Threads and Bluesky. On Instagram, Facebook and Threads it puts the link in the first comment.
6. **Learns from results.** It pulls likes, comments and shares, finds your best hours and recycles your best posts first.
7. **Drafts replies to new Google reviews.**
8. **Rebuilds the dashboard** (`docs/index.html`) and a link-in-bio page for each brand.

Every Monday it also checks Marky and its competitors for new features and opens a GitHub issue listing them. See [FEATURES.md](FEATURES.md) for the full comparison.

**Cost: $0.** It runs on GitHub Actions, which is free and has no minute limit for public repositories. The platform APIs are free, and so is the optional Gemini AI tier.

---

## Quick start (on this PC)

```powershell
pip install -r requirements.txt
python -m autopilot run --dry-run     # read sites, plan posts, make images, post nothing
start docs\index.html                 # see the calendar
```

Commands:

| Command | What it does |
|---|---|
| `python -m autopilot run` | Everything: read the sites, plan, post anything due, learn, rebuild the dashboard |
| `python -m autopilot status` | List what's scheduled and what's held for review |
| `python -m autopilot approve <id>` | Approve a held or draft post (it takes the next open slot) |
| `python -m autopilot skip <id>` | Never post that one |
| `python -m autopilot import posts.csv` | Bulk-add your own posts (see `posts-example.csv`) |
| `python -m autopilot watch` | Check Marky and competitors for new features |
| `python -m autopilot --brand hoinow status` | Limit any command to one business (`hoinow` or `finehomeloan`) |

To edit a post's wording, open `data/queue/<brand>.json` and change its `captions` text.

## Run it automatically (free, on GitHub)

1. Create a **public** repo under the a1nabob1 account, for example `a1nabob1/social-autopilot`, and push this folder to it. It has to be public so Instagram, Pinterest, Google and Threads can fetch the images. No secrets are stored in the files.
2. In `config.toml`, set `public_base_url = "https://raw.githubusercontent.com/a1nabob1/social-autopilot/main"`.
3. Go to **Settings → Secrets and variables → Actions** and add a secret for each line of `.env.example` that you fill in.
4. Turn on the **Actions** tab. "Social Autopilot" runs every hour and "Watch Marky and competitors" runs every Monday.
5. Optional: turn on **Settings → Pages** with source `main` / `docs` to put the dashboard and link-in-bio pages online.

Until a platform is connected, its posts are written to `data/outbox/` so you can copy and paste them by hand.

## Connecting each platform (all free)

| Platform | How |
|---|---|
| **Facebook + Instagram** | At developers.facebook.com, create an app (Business type) and add the "Facebook Login for Business" and "Instagram Graph API" products. In Graph API Explorer, get a Page token with `pages_manage_posts, pages_read_engagement, instagram_basic, instagram_content_publish`, then exchange it for a long-lived token. It doesn't expire when it comes from a long-lived user token. `IG_USER_ID` is the `instagram_business_account` id on the Page. You admin your own Pages, so the app can stay in development mode and doesn't need app review. |
| **LinkedIn** | At developers.linkedin.com, create an app and add "Share on LinkedIn" to post as you, or "Community Management API" to post as the company page. Tokens last 60 days, so put a reminder on your calendar to renew. |
| **Google Business Profile** | In Google Cloud, create an OAuth client, then request Business Profile API access (approval is free and takes a few days). Get a refresh token with the `business.manage` scope from OAuth Playground. Find the account and location IDs with the Account Management API. |
| **Pinterest** | At developers.pinterest.com, create an app and get a token with `pins:write, boards:read`. Use the board ID you want to post to. |
| **Threads** | At developers.facebook.com, add the Threads API use case and generate a long-lived token. |
| **Bluesky** | In the Bluesky app, go to Settings → Privacy and security → App passwords. Use your handle and that app password. |
| **Gemini (optional AI)** | Get a free key at aistudio.google.com and set `ai = "gemini"` in config.toml. The rules check still runs after the AI rewrite. |

## Settings worth knowing (`config.toml`)

- `schedule`: weekly time slots per brand. One post per slot goes to every platform, with text tailored to each one.
- `mix`: the rotation of post types (`faq`, `tip`, `spotlight`, `carousel`, `local`).
- `approval = "manual"`: nothing posts until you `approve` it.
- `disclaimer` / `short_disclaimer`: Fine Home Loan wording approved by Weber Mortgage compliance on 2026-11-23. Get it re-approved before changing it.
- `auto_reply_reviews = true`: add this to a brand to auto-reply to 4–5 star Google reviews. Other reviews always wait for you.

## Not included yet

- Video (Marky's custom videos), and so TikTok and YouTube
- A visual drag-and-drop editor
