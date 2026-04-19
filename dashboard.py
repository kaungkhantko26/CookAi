from __future__ import annotations

import hmac
from typing import Any

from flask import Flask, flash, redirect, render_template, request, session, url_for
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


def is_logged_in() -> bool:
    return bool(session.get("admin_logged_in"))


def require_login() -> bool:
    return request.endpoint in {"login", "login_post", "static"} or is_logged_in()


@app.before_request
def enforce_login() -> Any:
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
        return redirect(url_for("index"))
    flash("Invalid password.", "error")
    return redirect(url_for("login"))


@app.post("/logout")
def logout() -> Any:
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
        pending_count=pending_count,
        approved_count=len(bot.approved_user_ids - bot.TELEGRAM_ADMIN_USER_IDS),
        blocked_count=len(bot.blocked_user_ids),
    )


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
