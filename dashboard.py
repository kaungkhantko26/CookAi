from __future__ import annotations

import hashlib
import hmac
import secrets
from typing import Any

import requests
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

PUBLIC_WEB_ORIGINS = {
    "https://kaungkhantko.studio",
    "https://www.kaungkhantko.studio",
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
    "redeem_web_hash",
}


WEB_TERMINAL_HELP = """Available commands
/help                 show this command list
/clear                clear terminal screen
/reset                reset web chat memory
/english              use normal English replies
/burmese [message]    use Burmese replies
/chinese [message]    use Chinese replies
/language <name>      reply in any language, for example Japanese, Thai, Spanish
/presentation <brief> create a slide/deck outline
/link <url>           analyze a public link
/rewrite <text>       rewrite text clearly
/summarize <text>     summarize text
/shorter <text>       make text shorter
/formal <text>        make text formal
/friendly <text>      make text friendly
/caption <topic>      write a social caption
/hook <topic>         write hooks
/hashtags <topic>     suggest hashtags

You can also type any normal message."""

LANGUAGE_ALIASES = {
    "default": "default",
    "auto": "default",
    "english": "default",
    "en": "default",
    "burmese": "Burmese",
    "myanmar": "Burmese",
    "mm": "Burmese",
    "my": "Burmese",
    "chinese": "Chinese",
    "zh": "Chinese",
    "cn": "Chinese",
    "mandarin": "Chinese",
}
web_language_preferences: dict[int, str] = {}


def require_login() -> bool:
    return request.endpoint in PUBLIC_ENDPOINTS or is_logged_in()


@app.after_request
def add_public_api_headers(response: Any) -> Any:
    origin = request.headers.get("Origin", "")
    if origin in PUBLIC_WEB_ORIGINS:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        response.headers["Vary"] = "Origin"
    return response


def get_web_user_id(client_key: str = "") -> int:
    normalized_key = bot.normalize_plain_text(client_key).strip()
    if normalized_key:
        digest = hashlib.sha256(normalized_key.encode("utf-8")).hexdigest()
        return -(int(digest[:12], 16) % 2_000_000_000) - 1

    existing = session.get("web_user_id")
    if isinstance(existing, int):
        return existing

    # Keep website users separate from real Telegram IDs.
    web_user_id = -secrets.randbelow(2_000_000_000) - 1
    session["web_user_id"] = web_user_id
    return web_user_id


def normalize_web_language(language: str) -> str:
    normalized = bot.normalize_plain_text(language).strip()
    if not normalized:
        return "default"
    return LANGUAGE_ALIASES.get(normalized.lower(), normalized[:60])


def get_web_language(user_id: int) -> str:
    value = web_language_preferences.get(user_id) or str(session.get("web_language") or "default")
    return normalize_web_language(value)


def set_web_language(user_id: int, language: str) -> str:
    normalized = normalize_web_language(language)
    web_language_preferences[user_id] = normalized
    session["web_language"] = normalized
    return normalized


def get_language_system_prompt(language: str) -> str:
    if language == "default":
        return bot.BOT_SYSTEM_PROMPT
    if language.lower() == "burmese":
        return bot.BURMESE_SYSTEM_PROMPT
    return bot.with_base_rules(
        (
            f"Reply in {language}. "
            "Use natural, fluent wording a native speaker would expect. "
            "Do not translate word-for-word. "
            "Keep names, URLs, code, commands, and technical identifiers unchanged unless translation is requested. "
            "If a technical English term is standard in that language, you may include it naturally."
        )
    )


def get_web_system_prompt(user_id: int, text: str) -> str:
    language = get_web_language(user_id)
    if language.lower() == "burmese" or bot.contains_myanmar_text(text):
        return bot.BURMESE_SYSTEM_PROMPT
    if language != "default":
        return get_language_system_prompt(language)
    return bot.get_system_prompt_for_message(user_id, text)


def get_web_max_tokens(user_id: int, text: str) -> int:
    language = get_web_language(user_id)
    if language.lower() == "burmese" or bot.contains_myanmar_text(text):
        return bot.BURMESE_MAX_TOKENS
    return bot.get_max_tokens_for_message(text)


def run_web_transform(user_id: int, command: str, argument: str) -> str:
    instruction_map = {
        "/rewrite": "Rewrite this to sound better while keeping the meaning.",
        "/summarize": "Summarize this clearly and briefly.",
        "/shorter": "Make this shorter and tighter while keeping the main meaning.",
        "/formal": "Rewrite this in a formal and polished tone.",
        "/friendly": "Rewrite this in a warm, friendly, natural tone.",
    }
    if not argument.strip():
        return f"Usage: {command} <text>"

    return bot.transform_text(
        user_id,
        command,
        argument,
        instruction_map[command],
        max_tokens=bot.SUMMARY_MAX_TOKENS if command == "/summarize" else bot.TRANSFORM_MAX_TOKENS,
    )


def run_web_command_pack(user_id: int, command: str, argument: str) -> str:
    instruction_map = {
        "/caption": "Write a strong social media caption.",
        "/hook": "Write 10 strong social media hooks.",
        "/hashtags": "Suggest relevant hashtags.",
    }
    if not argument.strip():
        return f"Usage: {command} <topic or text>"

    return bot.run_structured_command(
        user_id,
        command,
        argument,
        instruction_map[command],
    )


def process_web_chat_message(user_id: int, raw_text: str, requested_language: str = "") -> str:
    if requested_language:
        set_web_language(user_id, requested_language)

    text = bot.normalize_plain_text(raw_text).strip()
    if not text:
        return "Type a command or message first."

    command, argument = bot.parse_command(text)
    command = command.lower()

    if command == "/help":
        return WEB_TERMINAL_HELP

    if command == "/clear":
        return "Screen cleared."

    if command == "/reset":
        bot.conversation_history[user_id].clear()
        bot.conversation_summaries.pop(user_id, None)
        bot.conversation_modes[user_id] = "chat"
        set_web_language(user_id, "default")
        return "Web chat memory reset."

    if command == "/english":
        set_web_language(user_id, "default")
        return "English mode enabled."

    if command in {"/burmese", "/chinese"}:
        language = "Burmese" if command == "/burmese" else "Chinese"
        set_web_language(user_id, language)
        if not argument:
            return f"{language} mode enabled. Type your message."
        return bot.request_chat_completion(
            user_id,
            argument,
            system_prompt=get_language_system_prompt(language),
            max_tokens=bot.BURMESE_MAX_TOKENS if language == "Burmese" else bot.DEFAULT_MAX_TOKENS,
        )

    if command == "/language":
        if not argument:
            current_language = get_web_language(user_id)
            return (
                f"Current language: {current_language}\n"
                "Use /language <name>, for example:\n"
                "/language Burmese\n"
                "/language Chinese\n"
                "/language Japanese\n"
                "/language Thai\n"
                "/language Spanish\n"
                "Use /language default or /english to return to normal."
            )
        language = set_web_language(user_id, argument)
        if language == "default":
            return "Default language mode enabled."
        return f"{language} mode enabled. Future replies will use {language}."

    if command == "/presentation":
        bot.conversation_modes[user_id] = "presentation"
        if not argument:
            return "Usage: /presentation <topic or brief>"
        return bot.request_chat_completion(
            user_id,
            argument,
            system_prompt=bot.PRESENTATION_SYSTEM_PROMPT,
            max_tokens=bot.PRESENTATION_MAX_TOKENS,
        )

    if command == "/link":
        if not argument:
            return "Usage: /link https://example.com"
        return bot.analyze_link(user_id, argument)

    if command in {"/rewrite", "/summarize", "/shorter", "/formal", "/friendly"}:
        return run_web_transform(user_id, command, argument)

    if command in {"/caption", "/hook", "/hashtags"}:
        return run_web_command_pack(user_id, command, argument)

    auto_url = bot.extract_first_url(text)
    if auto_url and text == auto_url:
        return bot.analyze_link(user_id, auto_url)

    return bot.request_chat_completion(
        user_id,
        text,
        system_prompt=get_web_system_prompt(user_id, text),
        max_tokens=get_web_max_tokens(user_id, text),
    )


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


@app.get("/bot")
@app.get("/terminal")
def web_terminal() -> str:
    return render_template("terminal.html")


@app.get("/health")
def web_health() -> dict[str, str]:
    return {"status": "ok"}


@app.route("/api/chat", methods=["POST", "OPTIONS"])
def web_chat() -> Any:
    if request.method == "OPTIONS":
        return ("", 204)

    payload = request.get_json(silent=True) or {}
    message = str(payload.get("message") or "").strip()
    client_key = str(payload.get("client_id") or "")
    requested_language = str(payload.get("language") or "")
    user_id = get_web_user_id(client_key)

    try:
        answer = process_web_chat_message(user_id, message, requested_language=requested_language)
    except requests.HTTPError as exc:
        app.logger.exception("HTTP error while processing website chat")
        error_body = exc.response.text[:500] if exc.response is not None else str(exc)
        return jsonify({"ok": False, "reply": f"API error:\n{error_body}"}), 502
    except Exception as exc:
        app.logger.exception("Website chat failed")
        return jsonify({"ok": False, "reply": f"Error: {exc}"}), 500

    return jsonify({"ok": True, "reply": answer})


@app.route("/api/redeem-hash", methods=["POST", "OPTIONS"])
def redeem_web_hash() -> Any:
    if request.method == "OPTIONS":
        return ("", 204)

    payload = request.get_json(silent=True) or {}
    login_hash = str(payload.get("hash") or "").strip()
    client_key = str(payload.get("client_id") or "")
    user_id = get_web_user_id(client_key)
    success, message = bot.consume_login_hash(user_id, login_hash)
    return jsonify({"ok": success, "message": message})


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
