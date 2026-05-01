from __future__ import annotations

import hmac
import ipaddress
import secrets
import time
from typing import Any

from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for
from waitress import serve

import bot


if not bot.ADMIN_DASHBOARD_PASSWORD:
    raise RuntimeError("ADMIN_DASHBOARD_PASSWORD is missing.")
if not bot.ADMIN_DASHBOARD_SECRET:
    raise RuntimeError("ADMIN_DASHBOARD_SECRET is missing.")

app = Flask(__name__)
app.secret_key = bot.ADMIN_DASHBOARD_SECRET
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = True
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-XSS-Protection": "1; mode=block",
    "X-Permitted-Cross-Domain-Policies": "none",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains; preload",
    "Content-Security-Policy": (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "connect-src 'self'; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    ),
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
}


def is_logged_in() -> bool:
    return bool(session.get("admin_logged_in"))


PUBLIC_ENDPOINTS = {
    "login",
    "login_post",
    "static",
    "web_terminal",
    "web_chat",
    "web_health",
    "honeypot",
    "not_found_page",
}
HONEYPOT_PREFIXES = (
    "/admin",
    "/admin.html",
    "/wp-admin",
    "/phpmyadmin",
    "/cpanel",
)


ADMIN_SESSION_LIMIT = 300
RATE_LIMIT_BUCKETS: dict[str, list[float]] = {}
RATE_LIMIT_RULES = {
    "login_post": (8, 300),
}
CSRF_TOKEN_BYTES = 32


def require_login() -> bool:
    return request.endpoint in PUBLIC_ENDPOINTS or is_logged_in()


def get_or_create_session_token(key: str) -> str:
    token = session.get(key)
    if isinstance(token, str) and len(token) >= 32:
        return token
    token = secrets.token_urlsafe(CSRF_TOKEN_BYTES)
    session[key] = token
    return token


def get_csrf_token() -> str:
    return get_or_create_session_token("csrf_token")


def is_valid_session_token(key: str, submitted_token: str) -> bool:
    expected_token = session.get(key)
    return (
        isinstance(expected_token, str)
        and bool(submitted_token)
        and hmac.compare_digest(submitted_token, expected_token)
    )


@app.context_processor
def inject_security_tokens() -> dict[str, str]:
    return {"csrf_token": get_csrf_token()}


def is_honeypot_path(path: str) -> bool:
    normalized_path = (path or "").lower()
    return any(
        normalized_path == prefix or normalized_path.startswith(f"{prefix}/")
        for prefix in HONEYPOT_PREFIXES
    )


@app.after_request
def add_response_headers(response: Any) -> Any:
    for header, value in SECURITY_HEADERS.items():
        response.headers[header] = value
    if request.endpoint not in {"web_terminal", "web_chat", "web_health", "not_found_page", "honeypot"}:
        response.headers["Cache-Control"] = "no-store, max-age=0"
        response.headers["Pragma"] = "no-cache"
    return response


def get_request_ip() -> str:
    forwarded_for = str(request.headers.get("X-Forwarded-For") or "").strip()
    remote_addr = str(request.remote_addr or "").strip()
    try:
        is_local_proxy = ipaddress.ip_address(remote_addr).is_loopback
    except ValueError:
        is_local_proxy = False
    if forwarded_for and is_local_proxy:
        return forwarded_for.split(",", 1)[0].strip()
    return remote_addr


def is_rate_limited(endpoint: str | None, ip_address: str) -> bool:
    if request.method == "OPTIONS":
        return False
    if not endpoint or endpoint not in RATE_LIMIT_RULES:
        return False

    max_requests, window_seconds = RATE_LIMIT_RULES[endpoint]
    now = time.time()
    bucket_key = f"{endpoint}:{ip_address}"
    recent_requests = [
        timestamp
        for timestamp in RATE_LIMIT_BUCKETS.get(bucket_key, [])
        if now - timestamp < window_seconds
    ]
    if len(recent_requests) >= max_requests:
        RATE_LIMIT_BUCKETS[bucket_key] = recent_requests
        return True
    recent_requests.append(now)
    RATE_LIMIT_BUCKETS[bucket_key] = recent_requests
    return False


def get_request_meta() -> dict[str, str]:
    return {
        "ip": get_request_ip(),
        "user_agent": bot.clip_text(str(request.headers.get("User-Agent") or "").strip(), 240),
        "origin": bot.clip_text(str(request.headers.get("Origin") or "").strip(), 160),
        "referrer": bot.clip_text(str(request.headers.get("Referer") or "").strip(), 240),
        "path": bot.clip_text(str(request.path or "").strip(), 120),
    }

def record_admin_session_event(action: str, ok: bool = True, reason: str = "") -> None:
    bot.refresh_auth_related_state()
    bot.admin_session_log.append(
        {
            "id": bot.new_item_id(),
            "action": action,
            "ok": ok,
            "reason": bot.clip_text(reason, 240),
            "created_at": bot.now_local().isoformat(),
            **get_request_meta(),
        }
    )
    if len(bot.admin_session_log) > ADMIN_SESSION_LIMIT:
        del bot.admin_session_log[:-ADMIN_SESSION_LIMIT]
    bot.save_auth_related_state()

@app.before_request
def enforce_login() -> Any:
    if is_honeypot_path(request.path):
        return None
    if request.endpoint is None:
        return None
    if is_rate_limited(request.endpoint, get_request_ip()):
        return jsonify({"ok": False, "reply": "Too many requests. Try again later."}), 429
    if request.method == "POST" and request.endpoint not in {"web_chat"}:
        submitted_token = str(request.form.get("csrf_token") or "")
        if not is_valid_session_token("csrf_token", submitted_token):
            record_admin_session_event("csrf_reject", ok=False, reason=request.endpoint or "unknown")
            return jsonify({"ok": False, "reply": "Request rejected."}), 403
    if require_login():
        return None
    return redirect(url_for("login"))


def dashboard_user_rows() -> list[dict[str, Any]]:
    bot.refresh_auth_related_state()
    user_ids = sorted(
        set(bot.known_user_profiles)
        | bot.approved_user_ids
        | bot.blocked_user_ids
        | bot.TELEGRAM_ADMIN_USER_IDS
    )
    rows: list[dict[str, Any]] = []
    for user_id in user_ids:
        profile = bot.known_user_profiles.get(user_id, {})
        rows.append(
            {
                "user_id": user_id,
                "status": bot.get_user_status_label(user_id),
                "name": bot.describe_user_name(profile),
                "account_link": bot.get_account_link(user_id),
                "chat_id": profile.get("chat_id"),
                "last_seen": bot.format_local_datetime(str(profile["last_seen"])) if profile.get("last_seen") else "",
                "last_request": str(profile.get("last_request") or "").strip(),
            }
        )
    return rows


def dashboard_activity_rows() -> list[dict[str, Any]]:
    bot.refresh_auth_related_state()
    rows: list[dict[str, Any]] = []
    for item in reversed(bot.activity_log[-60:]):
        created_at = str(item.get("created_at") or "").strip()
        rows.append(
            {
                "user_id": item.get("user_id"),
                "status": str(item.get("status") or ""),
                "name": str(item.get("name") or ""),
                "account_link": str(item.get("account_link") or ""),
                "message": str(item.get("message") or ""),
                "created_at": bot.format_local_datetime(created_at) if created_at else "",
            }
        )
    return rows


def dashboard_admin_session_rows() -> list[dict[str, Any]]:
    bot.refresh_auth_related_state()
    rows: list[dict[str, Any]] = []
    for item in reversed(bot.admin_session_log[-100:]):
        created_at = str(item.get("created_at") or "").strip()
        rows.append(
            {
                "action": str(item.get("action") or ""),
                "ok": bool(item.get("ok", True)),
                "reason": str(item.get("reason") or ""),
                "ip": str(item.get("ip") or ""),
                "user_agent": str(item.get("user_agent") or ""),
                "created_at": bot.format_local_datetime(created_at) if created_at else "",
            }
        )
    return rows


@app.get("/login")
def login() -> str:
    if is_logged_in():
        return redirect(url_for("index"))
    return render_template("login.html")


@app.post("/login")
def login_post() -> Any:
    password = str(request.form.get("password") or "")
    if hmac.compare_digest(password, bot.ADMIN_DASHBOARD_PASSWORD):
        session["admin_logged_in"] = True
        record_admin_session_event("login", ok=True)
        return redirect(url_for("index"))
    record_admin_session_event("login", ok=False, reason="invalid password")
    flash("Invalid password.", "error")
    return redirect(url_for("login"))


@app.post("/logout")
def logout() -> Any:
    if is_logged_in():
        record_admin_session_event("logout", ok=True)
    session.clear()
    return redirect(url_for("login"))


@app.get("/")
def index() -> str:
    bot.refresh_auth_related_state()
    pending_count = len(
        [
            user_id
            for user_id in bot.known_user_profiles
            if bot.get_user_status_label(user_id) == "pending"
        ]
    )
    return render_template(
        "dashboard.html",
        users=dashboard_user_rows(),
        activity=dashboard_activity_rows(),
        admin_sessions=dashboard_admin_session_rows(),
        pending_count=pending_count,
        approved_count=len(bot.approved_user_ids - bot.TELEGRAM_ADMIN_USER_IDS),
        blocked_count=len(bot.blocked_user_ids),
    )


@app.get("/bot")
@app.get("/terminal")
def web_terminal() -> tuple[str, int]:
    return ("Website removed.", 410)


@app.get("/health")
def web_health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/404")
def not_found_page() -> tuple[str, int]:
    return ("Not found.", 404)


@app.errorhandler(404)
def handle_not_found(_: Exception) -> tuple[str, int]:
    if request.path.startswith("/api/"):
        return jsonify({"ok": False, "reply": "API route not found."}), 404
    return ("Not found.", 404)


@app.errorhandler(405)
def handle_method_not_allowed(_: Exception) -> tuple[Any, int]:
    if request.path.startswith("/api/"):
        return jsonify({"ok": False, "reply": "Method not allowed."}), 405
    return ("Method not allowed.", 405)


@app.get("/admin")
@app.get("/admin/")
@app.get("/admin.html")
@app.get("/admin/<path:requested_path>")
@app.get("/wp-admin")
@app.get("/wp-admin/<path:requested_path>")
@app.get("/phpmyadmin")
@app.get("/phpmyadmin/<path:requested_path>")
@app.get("/cpanel")
@app.get("/cpanel/<path:requested_path>")
def honeypot(requested_path: str = "") -> tuple[str, int]:
    app.logger.warning(
        "Honeypot hit path=%s ip=%s ua=%s",
        request.path,
        get_request_ip(),
        request.headers.get("User-Agent", ""),
    )
    return ("Not found.", 404)


@app.route("/api/chat", methods=["POST", "OPTIONS"])
def web_chat() -> Any:
    return jsonify({"ok": False, "reply": "Website chat has been removed."}), 410


@app.post("/hash")
def create_hash() -> Any:
    login_hash = bot.create_login_hash(next(iter(sorted(bot.TELEGRAM_ADMIN_USER_IDS))))
    flash(f"New login hash: {login_hash}", "success")
    return redirect(url_for("index"))


@app.post("/user/<int:user_id>/approve")
def approve_user(user_id: int) -> Any:
    result = bot.approve_user_access(user_id)
    bot.register_bot_commands()
    profile = bot.known_user_profiles.get(user_id, {})
    target_chat_id = profile.get("chat_id")
    if result == "User approved." and isinstance(target_chat_id, int):
        bot.send_message(
            target_chat_id,
            "Admin approved your access. You can use the bot now.",
            reply_markup=bot.get_menu_keyboard("main"),
        )
    flash(result, "success")
    return redirect(url_for("index"))


@app.post("/user/<int:user_id>/block")
def block_user(user_id: int) -> Any:
    result = bot.block_user_access(user_id)
    bot.register_bot_commands()
    profile = bot.known_user_profiles.get(user_id, {})
    target_chat_id = profile.get("chat_id")
    if result == "User blocked." and isinstance(target_chat_id, int):
        bot.send_message(
            target_chat_id,
            "Your access has been blocked by the admin.",
            reply_markup=bot.REMOVE_REPLY_KEYBOARD,
        )
    flash(result, "success")
    return redirect(url_for("index"))


@app.post("/user/<int:user_id>/unblock")
def unblock_user(user_id: int) -> Any:
    result = bot.unblock_user_access(user_id)
    bot.register_bot_commands()
    profile = bot.known_user_profiles.get(user_id, {})
    target_chat_id = profile.get("chat_id")
    if isinstance(target_chat_id, int):
        bot.send_message(target_chat_id, "Admin removed your block. Use /login <hash> if you still need access.")
    flash(result, "success")
    return redirect(url_for("index"))


@app.post("/reply")
def reply_user() -> Any:
    target_user_id = int(str(request.form.get("user_id") or "0"))
    reply_text = bot.normalize_plain_text(str(request.form.get("message") or ""))
    if not reply_text:
        flash("Reply text is required.", "error")
        return redirect(url_for("index"))

    bot.refresh_auth_related_state()
    profile = bot.known_user_profiles.get(target_user_id, {})
    target_chat_id = profile.get("chat_id")
    if not isinstance(target_chat_id, int):
        flash("No chat ID known for that user yet.", "error")
        return redirect(url_for("index"))

    bot.send_message(target_chat_id, reply_text)
    flash("Message sent to user.", "success")
    return redirect(url_for("index"))


if __name__ == "__main__":
    serve(app, host="127.0.0.1", port=bot.ADMIN_DASHBOARD_PORT)
