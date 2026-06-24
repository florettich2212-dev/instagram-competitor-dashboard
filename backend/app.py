from flask import Flask, jsonify, request, send_file, Response, session, redirect, url_for
from flask_cors import CORS
from instagram_fetcher import fetch_all, fetch_profile, COMPETITORS, invalidate_cache, IMG_DIR
import requests as http
from pathlib import Path
import threading
import hashlib
import os
import secrets

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))
FRONTEND = Path(__file__).parent.parent / "frontend" / "index.html"
LOGIN_PAGE = Path(__file__).parent.parent / "frontend" / "login.html"
CORS(app)

DASHBOARD_PASSWORD = os.environ.get("DASHBOARD_PASSWORD", "leonie2024")

# ── Background refresh state ──
_refresh_state = {"status": "idle", "error": None}
_refresh_lock = threading.Lock()

_img_cache = {}
_img_lock = threading.Lock()

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Referer": "https://www.instagram.com/",
    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
}


def require_auth(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("authenticated"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "Unauthorized"}), 401
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        if request.form.get("password") == DASHBOARD_PASSWORD:
            session["authenticated"] = True
            return redirect(url_for("index"))
        error = "Incorrect password"
    return send_file(LOGIN_PAGE) if not error else (
        send_file(LOGIN_PAGE).get_data(as_text=True).replace(
            "<!--ERROR-->", f'<p class="error">{error}</p>'
        ), 200, {"Content-Type": "text/html"}
    )


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@require_auth
def index():
    return send_file(FRONTEND)


@app.route("/api/competitors")
@require_auth
def get_competitors():
    days = int(request.args.get("days", 180))
    return jsonify(fetch_all(days))


@app.route("/api/refresh", methods=["POST"])
@require_auth
def refresh_start():
    with _refresh_lock:
        if _refresh_state["status"] == "running":
            return jsonify({"status": "running"})
        _refresh_state["status"] = "running"
        _refresh_state["error"] = None

    days = int(request.args.get("days", 180))

    def run():
        try:
            invalidate_cache()
            fetch_all(days)
            with _refresh_lock:
                _refresh_state["status"] = "done"
        except Exception as e:
            with _refresh_lock:
                _refresh_state["status"] = "error"
                _refresh_state["error"] = str(e)

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"status": "running"})


@app.route("/api/refresh/status")
@require_auth
def refresh_status():
    with _refresh_lock:
        return jsonify(dict(_refresh_state))


@app.route("/api/images/<filename>")
@require_auth
def serve_image(filename):
    path = IMG_DIR / filename
    if not path.exists():
        return "", 404
    return send_file(path, mimetype="image/jpeg")


@app.route("/api/image-proxy")
@require_auth
def image_proxy():
    url = request.args.get("url", "")
    if not (url.startswith("https://scontent") or url.startswith("https://instagram.")):
        return "", 400
    key = hashlib.md5(url.encode()).hexdigest()
    with _img_lock:
        if key in _img_cache:
            ct, data = _img_cache[key]
            return Response(data, content_type=ct)
    try:
        r = http.get(url, headers=HEADERS, timeout=15)
        if r.status_code != 200:
            return "", 502
        ct = r.headers.get("Content-Type", "image/jpeg")
        content = r.content
        with _img_lock:
            _img_cache[key] = (ct, content)
        return Response(content, content_type=ct)
    except Exception:
        return "", 502


@app.route("/api/competitors/list")
@require_auth
def list_competitors():
    return jsonify(COMPETITORS)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5051))
    app.run(debug=False, host="0.0.0.0", port=port)
