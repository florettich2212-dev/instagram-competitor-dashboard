"""
GitHub Action scraper — incremental by default to minimise Apify usage.

Apify bills per post returned, so we never re-pull history we already have:
  * incremental (default) — only the newest RECENT_LIMIT posts per known account
  * backfill (MODE=backfill) — deep pull of BACKFILL_LIMIT posts for every account

Accounts with no stored posts (newly added) are always deep-pulled, so adding a
competitor to COMPETITORS just works without a manual backfill run.

Posts are merged into the existing store by shortcode: new ones are appended,
recent ones get refreshed engagement, and older history is preserved untouched.
Outputs data.json + images/ to ./output/
"""
import json
import os
import time
import requests
from datetime import datetime, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import io

from store import merge_posts

APIFY_TOKEN = os.environ["APIFY_TOKEN"]
REPO_RAW = "https://raw.githubusercontent.com/florettich2212-dev/instagram-competitor-dashboard/data"
OUT = Path("output")
IMG = OUT / "images"
OUT.mkdir(exist_ok=True)
IMG.mkdir(exist_ok=True)

MODE = os.environ.get("MODE", "incremental").strip().lower()
# Instagram returns newest-first, so a shallow window still catches all new activity
RECENT_LIMIT = int(os.environ.get("RECENT_LIMIT", "24"))
# Explicit MODE=backfill rebuilds deep history for everyone (expensive, rarely needed)
BACKFILL_LIMIT = int(os.environ.get("BACKFILL_LIMIT", "200"))
# Auto-pull for accounts we have no history for. 60 covers ~6+ months for a
# typical creator, which is the dashboard's longest window — much cheaper than
# a full backfill and Apify bills per post returned.
NEW_ACCOUNT_LIMIT = int(os.environ.get("NEW_ACCOUNT_LIMIT", "60"))

COMPETITORS = [
    "lamaisondeleoniie",
    "housenumbereight_",
    "imdavidkoe",
    "mimiennes.home",
    "such.a.sasha",
    "smnstr_",
    "charlottetaylr",
    "seventeenandfive",
    "marangelinari",
    "lille_arkiv",
    "iamlinaangelina",
    "maeisonjen",
    "eloisepreen",
    "bernstein_",
    "herz.und.blut",
    "konradpichlmeier",
    "ronneshome",
    "hannesmauritzson",
    "pieterpeulen",
    "maisonbymia",
    "casa.anaclara",
    "maison_herrfurth",
    "liebs_hier",
    "metsamoodi",
    "rachel.spanjersberg",
    "kirani.home",
    "birsiw",
]

IMG_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Referer": "https://www.instagram.com/",
    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
}


def run_apify(actor_id, payload, timeout=600):
    run = requests.post(
        f"https://api.apify.com/v2/acts/{actor_id}/runs",
        params={"token": APIFY_TOKEN},
        json=payload,
        timeout=30,
    )
    if run.status_code >= 400:
        # Surface Apify's own message — the CI log otherwise only shows a bare
        # HTTPError, and 401 (bad token) vs 402 (quota exhausted) need different fixes.
        print(f"\n[apify] HTTP {run.status_code} from {actor_id}")
        print(f"[apify] response: {run.text[:500]}")
        if run.status_code == 401:
            print("[apify] => TOKEN REJECTED. Create a token at console.apify.com "
                  "(Settings > API & Integrations) and update the APIFY_TOKEN repo secret.")
        elif run.status_code in (402, 403):
            print("[apify] => QUOTA/PERMISSION issue. Check Billing > Usage at console.apify.com.")
        print()
    run.raise_for_status()
    data = run.json()["data"]
    run_id = data["id"]
    dataset_id = data["defaultDatasetId"]
    print(f"[apify] started {actor_id} → {run_id}")

    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(8)
        status = requests.get(
            f"https://api.apify.com/v2/actor-runs/{run_id}",
            params={"token": APIFY_TOKEN}, timeout=15,
        ).json()["data"]["status"]
        print(f"[apify] {status}")
        if status in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"):
            break

    items = requests.get(
        f"https://api.apify.com/v2/datasets/{dataset_id}/items",
        params={"token": APIFY_TOKEN, "limit": 5000},
        timeout=30,
    ).json()
    return items if isinstance(items, list) else []


OLD_CAP = 600  # images saved before the 1080px upgrade were capped at this


def download_image(url, code):
    path = IMG / f"{code}.jpg"
    if path.exists():
        # Re-fetch images still capped at the old 600px so they upgrade to 1080px.
        # Anything larger is already current and is skipped (no bandwidth cost).
        try:
            from PIL import Image
            with Image.open(path) as im:
                if max(im.size) > OLD_CAP:
                    return f"images/{code}.jpg"
        except Exception:
            return f"images/{code}.jpg"
        path.unlink(missing_ok=True)
    try:
        r = requests.get(url, headers=IMG_HEADERS, timeout=15)
        if r.status_code == 200 and r.content:
            try:
                from PIL import Image
                img = Image.open(io.BytesIO(r.content)).convert("RGB")
                # 1080px = Instagram's native size; keeps the full-screen viewer sharp on retina
                img.thumbnail((1080, 1080), Image.LANCZOS)
                img.save(path, "JPEG", quality=90, optimize=True)
            except Exception:
                path.write_bytes(r.content)
            return f"images/{code}.jpg"
    except Exception as e:
        print(f"[img] failed {code}: {e}")
    return None


def build_slides(post):
    """Ordered local image paths for a carousel: cover first, then each extra slide.
    Returns [] for single-image posts so the frontend can just check length."""
    if len(post.get("childUrls", [])) < 2:
        return []
    cover = post.get("localImage")
    if not cover:
        return []
    extra = post.get("localSlides", {})
    slides = [cover]
    for i in range(len(post["childUrls"]) - 1):
        if i in extra:
            slides.append(extra[i])
    return slides if len(slides) > 1 else []


def load_existing():
    """Previously stored accounts, keyed by username. Empty dict on first run."""
    try:
        r = requests.get(f"{REPO_RAW}/data.json", timeout=25)
        if r.status_code != 200:
            print(f"[store] no existing data.json (HTTP {r.status_code}) — treating as first run")
            return {}
        data = r.json()
        total = sum(len(a.get("posts", [])) for a in data)
        print(f"[store] loaded {len(data)} accounts / {total} posts")
        return {a["username"]: a for a in data}
    except Exception as e:
        print(f"[store] could not load existing data.json ({e}) — treating as first run")
        return {}


def scrape_posts(usernames, limit, label, batch_size):
    """Fetch posts for a set of accounts, batched to avoid Instagram rate limiting."""
    out = []
    batches = [usernames[i:i + batch_size] for i in range(0, len(usernames), batch_size)]
    for n, batch in enumerate(batches, 1):
        print(f"  [{label}] batch {n}/{len(batches)} — {len(batch)} accounts × {limit} posts")
        out += run_apify(
            "apify~instagram-scraper",
            {"directUrls": [f"https://www.instagram.com/{u}/" for u in batch],
             "resultsType": "posts", "resultsLimit": limit,
             "proxy": {"useApifyProxy": True}},
        )
        if n < len(batches):
            print("    waiting 30s before next batch …")
            time.sleep(30)
    return out


def main():
    print(f"MODE={MODE} (recent={RECENT_LIMIT}, backfill={BACKFILL_LIMIT})")
    existing = load_existing()
    result = {u: {"full_name": "", "followers": 0, "posts": []} for u in COMPETITORS}

    # Profiles are ~1 billed result each — cheap, and postsCount tells us which
    # accounts actually published something since last run.
    print("Step 1/4: profiles …")
    profiles = run_apify("apify~instagram-profile-scraper", {"usernames": COMPETITORS})
    for p in profiles:
        u = p.get("username", "")
        if u in result:
            result[u]["full_name"] = p.get("fullName", "")
            result[u]["followers"] = p.get("followersCount", 0)
            result[u]["posts_count"] = p.get("postsCount") or 0
    print(f"  → {len(profiles)} profiles fetched")

    # Accounts we have no history for must be deep-pulled regardless of mode
    known = [u for u in COMPETITORS if existing.get(u, {}).get("posts")]
    unknown = [u for u in COMPETITORS if u not in known]
    if MODE == "backfill":
        deep, shallow, skipped = COMPETITORS, [], []
    else:
        deep = unknown
        # Skip accounts whose profile post count is unchanged: they published
        # nothing new, and their existing posts are already old enough that
        # engagement has effectively plateaued.
        shallow, skipped = [], []
        for u in known:
            live = result[u].get("posts_count") or 0
            seen = existing.get(u, {}).get("posts_count")
            (skipped if (live and seen and live == seen) else shallow).append(u)
        if skipped:
            print(f"  skipping {len(skipped)} account(s) with no new posts: {', '.join(skipped)}")

    print(f"Step 2/4: posts — {len(shallow)} incremental, {len(deep)} full pull, "
          f"{len(skipped)} skipped")
    if deep:
        print(f"  full pull for: {', '.join(deep)}")

    deep_limit = BACKFILL_LIMIT if MODE == "backfill" else NEW_ACCOUNT_LIMIT
    est = len(shallow) * RECENT_LIMIT + len(deep) * deep_limit + len(COMPETITORS)
    print(f"  estimated Apify results this run: ~{est}")

    posts_raw = []
    if shallow:
        posts_raw += scrape_posts(shallow, RECENT_LIMIT, "recent", 12)
    if deep:
        if shallow:
            print("  waiting 30s before full-pull batches …")
            time.sleep(30)
        posts_raw += scrape_posts(deep, deep_limit, "full", 6)

    for post in posts_raw:
        if post.get("error"):
            continue
        u = post.get("ownerUsername", "")
        if u not in result:
            continue
        result[u]["posts"].append({
            "shortCode": post.get("shortCode", ""),
            "url": post.get("url", ""),
            "timestamp": post.get("timestamp", ""),
            "likesCount": post.get("likesCount") or 0,
            "commentsCount": post.get("commentsCount") or 0,
            "viewsCount": post.get("videoPlayCount") or post.get("videoViewCount") or 0,
            "videoUrl": post.get("videoUrl") or "",
            "caption": post.get("caption") or "",
            "type": post.get("type", "Image"),
            "displayUrl": post.get("displayUrl") or "",
            # Carousel slides ("Sidecar" posts), capped at Instagram's classic limit of 10
            "childUrls": [
                c.get("displayUrl") for c in (post.get("childPosts") or [])[:10]
                if c.get("displayUrl")
            ],
        })
    total = sum(len(v["posts"]) for v in result.values())
    print(f"  → {total} posts returned by Apify")

    print("Step 3/4: images …")
    all_posts = [post for acc in result.values() for post in acc["posts"]]
    tasks = [
        (post["displayUrl"], post["shortCode"], post)
        for post in all_posts
        if post.get("displayUrl") and post.get("shortCode")
    ]
    # Carousel slide 1 is the cover we already fetch, so start slide files at index 2
    slide_tasks = [
        (url, f"{post['shortCode']}_{i + 2}", post, i)
        for post in all_posts
        if post.get("shortCode")
        for i, url in enumerate(post.get("childUrls", [])[1:])
    ]

    downloaded = 0
    with ThreadPoolExecutor(max_workers=10) as ex:
        futures = {ex.submit(download_image, url, code): post for url, code, post in tasks}
        for future in as_completed(futures):
            local = future.result()
            if local:
                futures[future]["localImage"] = local
                downloaded += 1
    print(f"  → {downloaded}/{len(tasks)} covers downloaded")

    slides_done = 0
    with ThreadPoolExecutor(max_workers=10) as ex:
        futures = {
            ex.submit(download_image, url, code): (post, i)
            for url, code, post, i in slide_tasks
        }
        for future in as_completed(futures):
            local = future.result()
            post, i = futures[future]
            if local:
                post.setdefault("localSlides", {})[i] = local
                slides_done += 1
    print(f"  → {slides_done}/{len(slide_tasks)} extra carousel slides downloaded")

    # Step 4: merge the freshly scraped window into stored history.
    # A shortcode union can only grow, so a rate-limited run can never delete data.
    print("Step 4/4: merging into store …")
    output = []
    total_added = 0
    for u in COMPETITORS:
        acc = result[u]
        old_acc = existing.get(u, {})
        followers = acc["followers"] or old_acc.get("followers", 0)

        fresh = []
        for post in acc["posts"]:
            ts = post.get("timestamp", "")
            if not ts:
                continue
            likes = post.get("likesCount") or 0
            comments = post.get("commentsCount") or 0
            engagement = likes + comments
            fresh.append({
                "shortcode": post.get("shortCode", ""),
                "url": post.get("url", ""),
                "date": ts,
                "likes": likes,
                "comments": comments,
                "views": post.get("viewsCount") or 0,
                "video_url": post.get("videoUrl") or "",
                "engagement": engagement,
                "engagement_rate": round(engagement / followers * 100, 2) if followers else 0,
                "caption": (post.get("caption") or "")[:280],
                "is_video": post.get("type") == "Video",
                "thumbnail_url": post.get("localImage") or "",
                "slides": build_slides(post),
            })

        stored = old_acc.get("posts", [])
        posts_out, added = merge_posts(stored, fresh, followers)
        total_added += added
        if u in skipped:
            print(f"  @{u}: skipped (no new posts) — {len(posts_out)} kept")
        elif added or len(stored) != len(posts_out):
            print(f"  @{u}: {len(stored)} stored + {len(fresh)} scraped → "
                  f"{len(posts_out)} total ({added} new)")
        elif not fresh and stored:
            print(f"  @{u}: 0 scraped (rate-limited?) — kept {len(stored)} stored")

        # Only advance the stored post count when we actually pulled this account,
        # otherwise a skip would hide posts published during a failed run.
        scraped = u in shallow or u in deep
        posts_count = acc.get("posts_count") if scraped else old_acc.get("posts_count")

        output.append({
            "username": u,
            "full_name": acc["full_name"] or old_acc.get("full_name", ""),
            "followers": followers,
            "posts_count": posts_count or old_acc.get("posts_count") or 0,
            "posts": posts_out,
            # Always "now": the frontend polls this to detect a completed refresh
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        })

    with open(OUT / "data.json", "w") as f:
        json.dump(output, f)
    grand = sum(len(a["posts"]) for a in output)
    print(f"Saved output/data.json — {grand} posts total, {total_added} newly added "
          f"({total} pulled from Apify this run)")


if __name__ == "__main__":
    main()
