"""
Targeted image-quality upgrade.

Images downloaded before the 1080px change are capped at 600px and look soft in
the full-screen viewer. Re-pulling whole profiles to fix them is wasteful, so
this scrapes only the specific posts worth upgrading, by their post URL.

Defaults to carousels/slideshows above a like threshold: Reels stream video from
Instagram directly (already sharp), and low-engagement posts aren't worth credit.

Apify bills one result per post URL, so cost == number of posts selected.

Env:
  APIFY_TOKEN    required
  MIN_LIKES      like threshold (default 2000)
  INCLUDE_REELS  set to "true" to also upgrade video covers (default false)
  MAX_POSTS      safety cap on how many posts to request (default 400)
"""
import io
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

from store import merge_posts

APIFY_TOKEN = os.environ["APIFY_TOKEN"]
REPO_RAW = "https://raw.githubusercontent.com/florettich2212-dev/instagram-competitor-dashboard/data"
MIN_LIKES = int(os.environ.get("MIN_LIKES", "2000"))
INCLUDE_REELS = os.environ.get("INCLUDE_REELS", "false").strip().lower() == "true"
MAX_POSTS = int(os.environ.get("MAX_POSTS", "400"))
BATCH = 60          # post URLs per Apify run
OLD_CAP = 600       # anything this size or smaller predates the 1080px upgrade

OUT = Path("output")
IMG = OUT / "images"
OUT.mkdir(exist_ok=True)
IMG.mkdir(exist_ok=True)

IMG_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Referer": "https://www.instagram.com/",
    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
}


def run_apify(actor_id, payload, timeout=900):
    run = requests.post(
        f"https://api.apify.com/v2/acts/{actor_id}/runs",
        params={"token": APIFY_TOKEN}, json=payload, timeout=30,
    )
    if run.status_code >= 400:
        print(f"[apify] HTTP {run.status_code}: {run.text[:400]}")
        if run.status_code == 401:
            print("[apify] => TOKEN REJECTED. Update the APIFY_TOKEN repo secret.")
        elif run.status_code in (402, 403):
            print("[apify] => QUOTA/PERMISSION issue. Check Billing > Usage on Apify.")
    run.raise_for_status()
    data = run.json()["data"]
    run_id, dataset_id = data["id"], data["defaultDatasetId"]
    print(f"[apify] {actor_id} -> {run_id}")
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(8)
        st = requests.get(f"https://api.apify.com/v2/actor-runs/{run_id}",
                          params={"token": APIFY_TOKEN}, timeout=15).json()["data"]["status"]
        if st in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"):
            print(f"[apify] {st}")
            break
    items = requests.get(f"https://api.apify.com/v2/datasets/{dataset_id}/items",
                         params={"token": APIFY_TOKEN, "limit": 5000}, timeout=60).json()
    return items if isinstance(items, list) else []


def is_low_res(rel_path):
    """True if the stored image predates the 1080px upgrade (or is missing)."""
    p = OUT / rel_path
    if not p.exists():
        return True
    try:
        from PIL import Image
        with Image.open(p) as im:
            return max(im.size) <= OLD_CAP
    except Exception:
        return True


def download_image(url, code):
    path = IMG / f"{code}.jpg"
    try:
        r = requests.get(url, headers=IMG_HEADERS, timeout=20)
        if r.status_code == 200 and r.content:
            try:
                from PIL import Image
                img = Image.open(io.BytesIO(r.content)).convert("RGB")
                img.thumbnail((1080, 1080), Image.LANCZOS)
                img.save(path, "JPEG", quality=90, optimize=True)
            except Exception:
                path.write_bytes(r.content)
            return f"images/{code}.jpg"
    except Exception as e:
        print(f"[img] failed {code}: {e}")
    return None


def main():
    data = requests.get(f"{REPO_RAW}/data.json", timeout=30).json()
    print(f"[store] {len(data)} accounts / {sum(len(a['posts']) for a in data)} posts")
    print(f"[filter] slideshows only={not INCLUDE_REELS}, min likes={MIN_LIKES}")

    # Pick the posts worth spending credit on
    targets = []
    for acc in data:
        for p in acc.get("posts", []):
            if not INCLUDE_REELS and p.get("is_video"):
                continue
            if not INCLUDE_REELS and len(p.get("slides") or []) < 2:
                continue          # single images aren't slideshows
            if (p.get("likes") or 0) <= MIN_LIKES:
                continue
            media = [p.get("thumbnail_url")] + list(p.get("slides") or [])
            if any(m and is_low_res(m) for m in media):
                targets.append((acc["username"], p))

    targets.sort(key=lambda t: t[1].get("likes") or 0, reverse=True)
    if len(targets) > MAX_POSTS:
        print(f"[filter] capping {len(targets)} -> {MAX_POSTS} highest-liked")
        targets = targets[:MAX_POSTS]

    if not targets:
        print("Nothing to upgrade — all selected images are already 1080px.")
        return
    print(f"[filter] {len(targets)} posts to upgrade "
          f"(~{len(targets)} Apify results ≈ ${len(targets) * 2.30 / 1000:.2f})")

    urls = [p["url"] for _, p in targets if p.get("url")]
    scraped = []
    batches = [urls[i:i + BATCH] for i in range(0, len(urls), BATCH)]
    for n, b in enumerate(batches, 1):
        print(f"[scrape] batch {n}/{len(batches)} — {len(b)} posts")
        scraped += run_apify("apify~instagram-scraper",
                             {"directUrls": b, "resultsType": "posts",
                              "resultsLimit": len(b),
                              "proxy": {"useApifyProxy": True}})
        if n < len(batches):
            time.sleep(20)
    print(f"[scrape] {len(scraped)} posts returned")

    # Re-download cover + every carousel slide at 1080px
    by_code = {s.get("shortCode"): s for s in scraped if s.get("shortCode")}
    jobs = []
    for s in by_code.values():
        code = s["shortCode"]
        if s.get("displayUrl"):
            jobs.append((s["displayUrl"], code))
        children = [c.get("displayUrl") for c in (s.get("childPosts") or [])[:10]
                    if c.get("displayUrl")]
        for i, url in enumerate(children[1:]):
            jobs.append((url, f"{code}_{i + 2}"))

    done = 0
    with ThreadPoolExecutor(max_workers=10) as ex:
        futs = {ex.submit(download_image, u, c): c for u, c in jobs}
        for f in as_completed(futs):
            if f.result():
                done += 1
    print(f"[images] {done}/{len(jobs)} re-downloaded at 1080px")

    # Refresh metrics for the posts we touched; media paths are unchanged
    out = []
    for acc in data:
        fresh = []
        for p in acc.get("posts", []):
            s = by_code.get(p.get("shortcode"))
            if not s:
                continue
            likes = s.get("likesCount") or p.get("likes") or 0
            comments = s.get("commentsCount") or p.get("comments") or 0
            q = dict(p)
            q.update({
                "likes": likes,
                "comments": comments,
                "engagement": likes + comments,
                "views": s.get("videoPlayCount") or s.get("videoViewCount") or p.get("views") or 0,
            })
            fresh.append(q)
        posts, _ = merge_posts(acc.get("posts", []), fresh, acc.get("followers", 0))
        acc = dict(acc)
        acc["posts"] = posts
        out.append(acc)

    with open(OUT / "data.json", "w") as f:
        json.dump(out, f)
    print(f"Saved output/data.json — {sum(len(a['posts']) for a in out)} posts")


if __name__ == "__main__":
    main()
