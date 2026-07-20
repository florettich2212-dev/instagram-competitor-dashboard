"""
Scrapes a single Instagram account and merges into existing data.json.
Called by GitHub Action with USERNAME env variable.
"""
import json, os, time, requests, io
from datetime import datetime, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

APIFY_TOKEN = os.environ["APIFY_TOKEN"]
USERNAME    = os.environ["USERNAME"]
OUT  = Path("output")
IMG  = OUT / "images"
OUT.mkdir(exist_ok=True)
IMG.mkdir(exist_ok=True)

IMG_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Referer": "https://www.instagram.com/",
}

REPO_RAW = "https://raw.githubusercontent.com/florettich2212-dev/instagram-competitor-dashboard/data"


def run_apify(actor_id, payload, timeout=300):
    run = requests.post(
        f"https://api.apify.com/v2/acts/{actor_id}/runs",
        params={"token": APIFY_TOKEN}, json=payload, timeout=30,
    )
    run.raise_for_status()
    data = run.json()["data"]
    run_id, dataset_id = data["id"], data["defaultDatasetId"]
    print(f"[apify] {actor_id} → {run_id}")
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(8)
        st = requests.get(f"https://api.apify.com/v2/actor-runs/{run_id}",
                          params={"token": APIFY_TOKEN}, timeout=15).json()["data"]["status"]
        print(f"  {st}")
        if st in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"):
            break
    items = requests.get(f"https://api.apify.com/v2/datasets/{dataset_id}/items",
                         params={"token": APIFY_TOKEN, "limit": 5000}, timeout=30).json()
    return items if isinstance(items, list) else []


def download_image(url, code):
    path = IMG / f"{code}.jpg"
    if path.exists():
        return f"images/{code}.jpg"
    try:
        r = requests.get(url, headers=IMG_HEADERS, timeout=15)
        if r.status_code == 200 and r.content:
            try:
                from PIL import Image
                img = Image.open(io.BytesIO(r.content)).convert("RGB")
                img.thumbnail((600, 600), Image.LANCZOS)
                img.save(path, "JPEG", quality=82, optimize=True)
            except Exception:
                path.write_bytes(r.content)
            return f"images/{code}.jpg"
    except Exception as e:
        print(f"[img] failed {code}: {e}")
    return None


def main():
    print(f"Scraping single account: @{USERNAME}")

    # Load existing data.json
    try:
        r = requests.get(f"{REPO_RAW}/data.json", timeout=15)
        existing = r.json() if r.status_code == 200 else []
    except Exception:
        existing = []
    print(f"Loaded existing data: {len(existing)} accounts")

    # Step 1: profile
    profiles = run_apify("apify~instagram-profile-scraper", {"usernames": [USERNAME]})
    profile = next((p for p in profiles if p.get("username") == USERNAME), {})
    followers = profile.get("followersCount", 0)
    full_name = profile.get("fullName", "")
    print(f"  followers: {followers}")

    # Step 2: posts — retry up to 3 times if Apify returns 0 (rate limit / login wall)
    posts_raw = []
    for attempt in range(1, 4):
        print(f"  posts attempt {attempt}/3 …")
        posts_raw = run_apify(
            "apify~instagram-scraper",
            {"directUrls": [f"https://www.instagram.com/{USERNAME}/"],
             "resultsType": "posts", "resultsLimit": 100,
             "proxy": {"useApifyProxy": True}},
        )
        print(f"  posts scraped: {len(posts_raw)}")
        if posts_raw:
            break
        if attempt < 3:
            print("  0 results — waiting 60s before retry …")
            time.sleep(60)
    if not posts_raw:
        print("  WARNING: all 3 attempts returned 0 posts")

    # Step 3: images
    tasks = [(p["displayUrl"], p["shortCode"], p)
             for p in posts_raw if p.get("displayUrl") and p.get("shortCode")]
    downloaded = 0
    with ThreadPoolExecutor(max_workers=10) as ex:
        futures = {ex.submit(download_image, url, code): post for url, code, post in tasks}
        for future in as_completed(futures):
            local = future.result()
            if local:
                futures[future]["localImage"] = local
                downloaded += 1
    print(f"  images: {downloaded}/{len(tasks)}")

    # Build posts output
    posts_out = []
    for post in posts_raw:
        ts = post.get("timestamp", "")
        if not ts:
            continue
        likes    = post.get("likesCount") or 0
        comments = post.get("commentsCount") or 0
        er = round((likes + comments) / followers * 100, 2) if followers else 0
        posts_out.append({
            "shortcode":        post.get("shortCode", ""),
            "url":              post.get("url", ""),
            "date":             ts,
            "likes":            likes,
            "comments":         comments,
            "views":            post.get("videoPlayCount") or post.get("videoViewCount") or 0,
            "engagement":       likes + comments,
            "engagement_rate":  er,
            "caption":          (post.get("caption") or "")[:280],
            "is_video":         post.get("type") == "Video",
            "thumbnail_url":    post.get("localImage") or "",
        })

    # Don't overwrite existing posts if Apify returned nothing (rate limit / block)
    existing_acc = next((a for a in existing if a["username"] == USERNAME), {})
    if not posts_out and existing_acc.get("posts"):
        print(f"WARNING: Apify returned 0 posts for @{USERNAME} — keeping existing {len(existing_acc['posts'])} posts")
        posts_out = existing_acc["posts"]

    new_entry = {
        "username":        USERNAME,
        "full_name":       full_name or existing_acc.get("full_name", ""),
        "followers":       followers or existing_acc.get("followers", 0),
        "posts":           posts_out,
        "fetched_at":      datetime.now(timezone.utc).isoformat(),
    }

    # Merge into existing data
    merged = [new_entry if a["username"] == USERNAME else a for a in existing]
    if not any(a["username"] == USERNAME for a in existing):
        merged.append(new_entry)

    with open(OUT / "data.json", "w") as f:
        json.dump(merged, f)
    print(f"Saved data.json — @{USERNAME}: {len(posts_out)} posts")


if __name__ == "__main__":
    main()
