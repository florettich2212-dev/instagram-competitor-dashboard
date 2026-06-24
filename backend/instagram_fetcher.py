import json
import os
import time
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path

CACHE_DIR = Path(__file__).parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)
IMG_DIR = Path(__file__).parent / "images"
IMG_DIR.mkdir(exist_ok=True)
CACHE_TTL_HOURS = 12

APIFY_TOKEN = os.environ.get("APIFY_TOKEN", "")
ALL_CACHE = CACHE_DIR / "all_profiles.json"

IMG_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Referer": "https://www.instagram.com/",
    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
}

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
]


def _run_async(actor_id: str, payload: dict, timeout: int = 300) -> list:
    run = requests.post(
        f"https://api.apify.com/v2/acts/{actor_id}/runs",
        params={"token": APIFY_TOKEN},
        json=payload,
        timeout=30,
    )
    run.raise_for_status()
    run_id = run.json()["data"]["id"]
    dataset_id = run.json()["data"]["defaultDatasetId"]
    print(f"[apify] started {actor_id} → run {run_id}")

    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(6)
        status = requests.get(
            f"https://api.apify.com/v2/actor-runs/{run_id}",
            params={"token": APIFY_TOKEN}, timeout=10,
        ).json()["data"]["status"]
        print(f"[apify] {run_id} → {status}")
        if status in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"):
            break

    items = requests.get(
        f"https://api.apify.com/v2/datasets/{dataset_id}/items",
        params={"token": APIFY_TOKEN, "limit": 5000},
        timeout=30,
    ).json()
    return items if isinstance(items, list) else []


def _fetch_raw() -> dict:
    result = {u: {"full_name": "", "followers": 0, "profile_pic_url": "", "posts": [], "error": None} for u in COMPETITORS}

    # ── Profile data (followers, name) ──
    print("[fetch] step 1/2: profile scraper …")
    profiles = _run_async("apify~instagram-profile-scraper", {"usernames": COMPETITORS})
    for p in profiles:
        u = p.get("username", "")
        if u not in result:
            continue
        if p.get("error"):
            result[u]["error"] = p.get("errorDescription", p["error"])
            continue
        result[u]["full_name"] = p.get("fullName", "")
        result[u]["followers"] = p.get("followersCount", 0)
        result[u]["profile_pic_url"] = p.get("profilePicUrl", "")

    # ── Posts (up to 100 per account via directUrls — covers ~180 days) ──
    print("[fetch] step 2/2: post scraper …")
    direct_urls = [f"https://www.instagram.com/{u}/" for u in COMPETITORS]
    posts_raw = _run_async(
        "apify~instagram-scraper",
        {"directUrls": direct_urls, "resultsType": "posts", "resultsLimit": 75},
        timeout=600,
    )

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
            "caption": post.get("caption") or "",
            "type": post.get("type", "Image"),
            "displayUrl": post.get("displayUrl") or "",
        })

    total = sum(len(v["posts"]) for v in result.values())
    print(f"[fetch] done — {total} posts, downloading images …")
    _download_images(result)
    return result


def _download_images(result: dict):
    """Download post thumbnails to disk in parallel."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    tasks = []
    for acc in result.values():
        for post in acc.get("posts", []):
            url = post.get("displayUrl", "")
            code = post.get("shortCode", "")
            if url and code:
                tasks.append((url, code, post))

    def fetch_one(args):
        url, code, post = args
        local_path = IMG_DIR / f"{code}.jpg"
        if local_path.exists():
            post["localImage"] = f"/api/images/{code}.jpg"
            return False
        try:
            r = requests.get(url, headers=IMG_HEADERS, timeout=10)
            if r.status_code == 200 and r.content:
                local_path.write_bytes(r.content)
                post["localImage"] = f"/api/images/{code}.jpg"
                return True
        except Exception:
            pass
        return False

    downloaded = 0
    with ThreadPoolExecutor(max_workers=20) as ex:
        for result in as_completed(ex.submit(fetch_one, t) for t in tasks):
            if result.result():
                downloaded += 1

    print(f"[images] downloaded {downloaded} new images")


def _all_cache_valid() -> bool:
    return ALL_CACHE.exists() and (time.time() - ALL_CACHE.stat().st_mtime) < CACHE_TTL_HOURS * 3600


def _parse_posts(raw_posts: list, followers: int, days: int) -> list:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    posts = []
    for post in raw_posts:
        ts = post.get("timestamp")
        if not ts:
            continue
        post_date = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if post_date < cutoff:
            continue
        likes = post.get("likesCount") or 0
        comments = post.get("commentsCount") or 0
        engagement = likes + comments
        er = round(engagement / followers * 100, 2) if followers else 0
        posts.append({
            "shortcode": post.get("shortCode", ""),
            "url": post.get("url", ""),
            "date": post_date.isoformat(),
            "likes": likes,
            "comments": comments,
            "engagement": engagement,
            "engagement_rate": er,
            "caption": (post.get("caption") or "")[:280],
            "is_video": post.get("type") == "Video",
            "thumbnail_url": post.get("localImage") or post.get("displayUrl") or "",
        })
    posts.sort(key=lambda p: p["likes"], reverse=True)
    return posts


def fetch_all(days: int = 180) -> list:
    if _all_cache_valid():
        with open(ALL_CACHE) as f:
            raw = json.load(f)
    else:
        if not APIFY_TOKEN:
            return [{"username": u, "full_name": "", "followers": 0, "posts": [], "error": "APIFY_TOKEN not set", "fetched_at": ""} for u in COMPETITORS]
        raw = _fetch_raw()
        with open(ALL_CACHE, "w") as f:
            json.dump(raw, f)

    results = []
    for u in COMPETITORS:
        acc = raw.get(u, {})
        followers = acc.get("followers", 0)
        results.append({
            "username": u,
            "full_name": acc.get("full_name", ""),
            "followers": followers,
            "profile_pic_url": acc.get("profile_pic_url", ""),
            "posts": _parse_posts(acc.get("posts", []), followers, days),
            "error": acc.get("error"),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        })
    return results


def fetch_profile(username: str, days: int = 180) -> dict:
    for r in fetch_all(days):
        if r["username"] == username:
            return r
    return {"username": username, "error": "Not found", "posts": [], "followers": 0, "full_name": "", "fetched_at": ""}


def invalidate_cache():
    for f in CACHE_DIR.glob("*.json"):
        f.unlink()
