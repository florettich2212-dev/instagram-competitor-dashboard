"""
GitHub Action scraper — runs on demand, outputs data.json + images/ to ./output/
"""
import json
import os
import time
import requests
from datetime import datetime, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import io

APIFY_TOKEN = os.environ["APIFY_TOKEN"]
OUT = Path("output")
IMG = OUT / "images"
OUT.mkdir(exist_ok=True)
IMG.mkdir(exist_ok=True)

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
    result = {u: {"full_name": "", "followers": 0, "posts": []} for u in COMPETITORS}

    print("Step 1/3: profiles …")
    profiles = run_apify("apify~instagram-profile-scraper", {"usernames": COMPETITORS})
    for p in profiles:
        u = p.get("username", "")
        if u in result:
            result[u]["full_name"] = p.get("fullName", "")
            result[u]["followers"] = p.get("followersCount", 0)
    print(f"  → {len(profiles)} profiles fetched")

    print("Step 2/3: posts …")
    direct_urls = [f"https://www.instagram.com/{u}/" for u in COMPETITORS]
    posts_raw = run_apify(
        "apify~instagram-scraper",
        {
            "directUrls": direct_urls,
            "resultsType": "posts",
            "resultsLimit": 75,
            "proxy": {"useApifyProxy": True, "apifyProxyGroups": ["RESIDENTIAL"]},
        },
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
    print(f"  → {total} posts fetched")

    print("Step 3/3: images …")
    tasks = [
        (post["displayUrl"], post["shortCode"], post)
        for acc in result.values()
        for post in acc["posts"]
        if post.get("displayUrl") and post.get("shortCode")
    ]

    downloaded = 0
    with ThreadPoolExecutor(max_workers=10) as ex:
        futures = {ex.submit(download_image, url, code): post for url, code, post in tasks}
        for future in as_completed(futures):
            local = future.result()
            if local:
                futures[future]["localImage"] = local
                downloaded += 1
    print(f"  → {downloaded}/{len(tasks)} images downloaded")

    # Build final JSON — save ALL posts unfiltered (frontend filters by days)
    output = []
    for u in COMPETITORS:
        acc = result[u]
        followers = acc["followers"]
        posts_out = []
        for post in acc["posts"]:
            ts = post.get("timestamp", "")
            if not ts:
                continue
            likes = post.get("likesCount") or 0
            comments = post.get("commentsCount") or 0
            engagement = likes + comments
            er = round(engagement / followers * 100, 2) if followers else 0
            posts_out.append({
                "shortcode": post.get("shortCode", ""),
                "url": post.get("url", ""),
                "date": ts,
                "likes": likes,
                "comments": comments,
                "engagement": engagement,
                "engagement_rate": er,
                "caption": (post.get("caption") or "")[:280],
                "is_video": post.get("type") == "Video",
                "thumbnail_url": post.get("localImage") or "",
            })
        output.append({
            "username": u,
            "full_name": acc["full_name"],
            "followers": followers,
            "posts": posts_out,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        })

    with open(OUT / "data.json", "w") as f:
        json.dump(output, f)
    print(f"Saved output/data.json — {sum(len(a['posts']) for a in output)} posts total")


if __name__ == "__main__":
    main()
