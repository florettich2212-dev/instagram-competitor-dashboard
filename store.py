"""
Shared merge logic for the incremental scrapers.

The store (data.json on the `data` branch) is the source of truth for post
history. Scrapers only ever fetch a recent window from Apify and union it in by
shortcode, so:
  * history is never re-pulled (Apify bills per post returned)
  * a rate-limited run that returns few or zero posts can't delete anything
"""


def merge_posts(stored, fresh, followers):
    """Union stored history with a freshly scraped window, keyed by shortcode.

    Fresh data overwrites metrics for posts we already had (engagement moves over
    time) but never clears stored media when the new payload omits it.

    Returns (merged_posts_newest_first, added_count).
    """
    by_code = {}
    for p in stored:
        code = p.get("shortcode")
        if code:
            by_code[code] = dict(p)

    added = 0
    for p in fresh:
        code = p.get("shortcode")
        if not code:
            continue
        if code in by_code:
            old = by_code[code]
            for k in ("likes", "comments", "engagement", "engagement_rate",
                      "caption", "date", "url", "is_video"):
                if k in p:
                    old[k] = p[k]
            # Keep the best value ever seen for fields Apify sometimes returns empty
            old["views"] = p.get("views") or old.get("views", 0)
            old["video_url"] = p.get("video_url") or old.get("video_url", "")
            if p.get("thumbnail_url"):
                old["thumbnail_url"] = p["thumbnail_url"]
            if p.get("slides"):
                old["slides"] = p["slides"]
        else:
            by_code[code] = p
            added += 1

    merged = list(by_code.values())
    # Follower counts drift, so recompute ER across all history for consistency
    if followers:
        for p in merged:
            p["engagement_rate"] = round((p.get("engagement") or 0) / followers * 100, 2)
    merged.sort(key=lambda p: p.get("date") or "", reverse=True)
    return merged, added
