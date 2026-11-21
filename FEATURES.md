# Feature comparison

Checked against Marky's site and pricing on 2026-11-21. The weekly watcher (`python -m autopilot watch`) keeps an eye on Marky, SocialBee, Publer, FeedHive, Metricool, Predis.ai and Ocoya. It opens a GitHub issue when their feature or pricing pages change.

| Feature | Marky ($39–$229/mo) | Social Autopilot (free) | Idea from |
|---|---|---|---|
| Posts made from your website | Yes | Yes: reads every page in the sitemap, including FAQs, sections, page photos and site icon | Marky |
| Branded images in your colors and logo | Yes | Yes: square, Pinterest pin and carousel slides | Marky |
| Carousels | Yes | Yes: built from each page's FAQ (Instagram carousel, Facebook multi-photo) | Marky |
| Full-quality images | Users complain of compressed thumbnails | Uploaded at full size as lossless PNG | Fixes a Marky complaint |
| Platforms | FB, IG, LinkedIn, Google Business, Pinterest, TikTok, YouTube | FB, IG, LinkedIn, Google Business, Pinterest, **Threads, Bluesky** | SocialBee/Publer |
| Channel limit | 5–8, then $7/mo each | Unlimited | — |
| New website pages posted automatically | No | Yes: new or changed pages are found and announced within the hour | Publer/FeedHive (RSS) |
| Content categories in rotation | Themes | Yes: FAQ / tip / guide / carousel / local mix per brand | SocialBee |
| Evergreen recycling, reworded | No | Yes: after 45 days, with new hooks and calls to action, best performers first | SocialBee + FeedHive |
| Seasonal and holiday calendar | Partly | Yes: hurricane season, flood wait, Veterans Day (VA loans), holidays | Loomly |
| Link in the first comment | No | Yes: Instagram, Facebook, Threads | FeedHive/Buffer |
| Learns your best posting hours | No | Yes: moves posts toward the hours with the most engagement | Metricool |
| Analytics / top posts | Basic | Likes, comments and shares from FB/IG, top-10 list on the dashboard | Metricool |
| Approval workflow | Pro plan only ($229) | Free: `approval = "manual"` in config | Planable |
| Mortgage and insurance advertising rules check | No | Yes: Reg Z trigger terms, NMLS/Equal Housing line, promise words are held for review | Built for you |
| Google review reply drafts | Yes | Yes: drafts every new review; optional auto-reply to 4–5 stars | Marky / Vista Social |
| Link-in-bio page | No | Yes: `docs/links-<brand>.html` | Publer |
| Bulk upload | Yes | Yes: CSV import | SocialBee/Publer |
| AI writing | Paid AI | Free templates by default; optional free Gemini tier | — |
| Failure alerts | Chat support | A GitHub issue opens automatically if a run fails | — |
| Custom AI videos | 3–15/mo | **Not yet** | Next on the list |
| TikTok / YouTube | Yes | **Not yet** (both need video) | Next on the list |
| Visual drag-and-drop editor | Yes | No: edit the text in the queue file, or approve and skip with commands | — |
