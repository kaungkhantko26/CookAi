from __future__ import annotations

import logging
import time
from typing import Any

import requests

import bot


logger = logging.getLogger(__name__)

ADMIN_BOT_TOKEN = bot.TELEGRAM_ADMIN_BOT_TOKEN
if not ADMIN_BOT_TOKEN:
    raise RuntimeError("TELEGRAM_ADMIN_BOT_TOKEN is missing.")

ADMIN_TELEGRAM_API_BASE = f"https://api.telegram.org/bot{ADMIN_BOT_TOKEN}"
ADMIN_COMMANDS = [
    {"command": "start", "description": "Show MENTOR admin dashboard help"},
    {"command": "help", "description": "Show admin commands"},
    {"command": "hash", "description": "Create a login hash"},
    {"command": "users", "description": "List known users"},
    {"command": "user", "description": "Inspect one user"},
    {"command": "approve", "description": "Approve a user ID"},
    {"command": "block", "description": "Block a user ID"},
    {"command": "unblock", "description": "Unblock a user ID"},
    {"command": "replyuser", "description": "Send a message to a user"},
]
admin_session = requests.Session()


def admin_telegram_api(method: str, payload: dict[str, Any]) -> dict[str, Any]:
    response = admin_session.post(
        f"{ADMIN_TELEGRAM_API_BASE}/{method}",
        json=payload,
        timeout=bot.REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    data = response.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram admin API error: {data}")
    return data


def admin_send_message(chat_id: int, text: str, reply_to_message_id: int | None = None) -> None:
    for chunk in bot.chunk_text(text or "Empty response."):
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "text": chunk,
        }
        if reply_to_message_id is not None:
            payload["reply_to_message_id"] = reply_to_message_id
            reply_to_message_id = None
        admin_telegram_api("sendMessage", payload)


def register_admin_commands() -> None:
    admin_telegram_api("setMyCommands", {"commands": ADMIN_COMMANDS, "scope": {"type": "default"}})
    logger.info("Registered %s admin bot commands", len(ADMIN_COMMANDS))


def get_admin_updates(offset: int | None = None) -> list[dict[str, Any]]:
    params: dict[str, Any] = {
        "timeout": bot.POLL_TIMEOUT,
        "allowed_updates": ["message"],
    }
    if offset is not None:
        params["offset"] = offset

    response = admin_session.get(
        f"{ADMIN_TELEGRAM_API_BASE}/getUpdates",
        params=params,
        timeout=bot.POLL_TIMEOUT + 10,
    )
    response.raise_for_status()
    data = response.json()
    if not data.get("ok"):
        raise RuntimeError(f"Admin polling error: {data}")
    return data.get("result", [])


def admin_help_text() -> str:
    return (
        "MENTOR admin dashboard commands:\n"
        "/start\n"
        "/help\n"
        "/hash\n"
        "/users\n"
        "/user <id>\n"
        "/approve <id>\n"
        "/block <id>\n"
        "/unblock <id>\n"
        "/replyuser <id> | <text>"
    )


def handle_admin_message(message: dict[str, Any]) -> None:
    chat = message.get("chat", {})
    from_user = message.get("from", {})
    chat_id = chat.get("id")
    user_id = from_user.get("id")
    text = (message.get("text") or "").strip()
    message_id = message.get("message_id")

    if not isinstance(chat_id, int) or not isinstance(user_id, int):
        logger.warning("Skipping malformed admin message: %s", message)
        return

    if not bot.is_admin_user(user_id):
        admin_send_message(chat_id, "Access denied.", reply_to_message_id=message_id)
        return

    bot.refresh_auth_related_state()
    command, argument = bot.parse_command(text)

    if text in {"/start", "/help"}:
        admin_send_message(chat_id, admin_help_text(), reply_to_message_id=message_id)
        return

    if command == "/hash":
        login_hash = bot.create_login_hash(user_id)
        admin_send_message(
            chat_id,
            (
                "New login hash created.\n"
                f"Hash: {login_hash}\n"
                "Send it to the user and tell them to use /login <hash> in the user bot."
            ),
            reply_to_message_id=message_id,
        )
        return

    if command == "/users":
        user_ids = sorted(set(bot.known_user_profiles) | bot.approved_user_ids | bot.blocked_user_ids | bot.TELEGRAM_ADMIN_USER_IDS)
        if not user_ids:
            admin_send_message(chat_id, "No users found.", reply_to_message_id=message_id)
            return

        lines = []
        for known_user_id in user_ids:
            profile = bot.known_user_profiles.get(known_user_id, {})
            label = bot.get_user_status_label(known_user_id)
            last_seen = str(profile.get("last_seen") or "").strip()
            suffix = f" | {bot.format_local_datetime(last_seen)}" if last_seen else ""
            lines.append(f"{known_user_id} | {label} | {bot.describe_user_name(profile)}{suffix}")
        admin_send_message(chat_id, "Known users\n" + "\n".join(lines), reply_to_message_id=message_id)
        return

    if command == "/user":
        if not argument:
            admin_send_message(chat_id, "Use /user <id>.", reply_to_message_id=message_id)
            return
        try:
            target_user_id = int(argument)
        except ValueError:
            admin_send_message(chat_id, "User ID must be a number.", reply_to_message_id=message_id)
            return
        admin_send_message(chat_id, bot.format_profile_summary(target_user_id), reply_to_message_id=message_id)
        return

    if command == "/approve":
        if not argument:
            admin_send_message(chat_id, "Use /approve <id>.", reply_to_message_id=message_id)
            return
        try:
            target_user_id = int(argument)
        except ValueError:
            admin_send_message(chat_id, "User ID must be a number.", reply_to_message_id=message_id)
            return
        status_message = bot.approve_user_access(target_user_id)
        bot.register_bot_commands()
        admin_send_message(chat_id, status_message, reply_to_message_id=message_id)
        if status_message == "User approved.":
            profile = bot.known_user_profiles.get(target_user_id, {})
            target_chat_id = profile.get("chat_id")
            if isinstance(target_chat_id, int):
                bot.send_message(
                    target_chat_id,
                    "Admin approved your access. You can use the bot now.",
                    reply_markup=bot.get_menu_keyboard("main"),
                )
        return

    if command == "/block":
        if not argument:
            admin_send_message(chat_id, "Use /block <id>.", reply_to_message_id=message_id)
            return
        try:
            target_user_id = int(argument)
        except ValueError:
            admin_send_message(chat_id, "User ID must be a number.", reply_to_message_id=message_id)
            return
        status_message = bot.block_user_access(target_user_id)
        bot.register_bot_commands()
        admin_send_message(chat_id, status_message, reply_to_message_id=message_id)
        if status_message == "User blocked.":
            profile = bot.known_user_profiles.get(target_user_id, {})
            target_chat_id = profile.get("chat_id")
            if isinstance(target_chat_id, int):
                bot.send_message(
                    target_chat_id,
                    "Your access has been blocked by the admin.",
                    reply_markup=bot.REMOVE_REPLY_KEYBOARD,
                )
        return

    if command == "/unblock":
        if not argument:
            admin_send_message(chat_id, "Use /unblock <id>.", reply_to_message_id=message_id)
            return
        try:
            target_user_id = int(argument)
        except ValueError:
            admin_send_message(chat_id, "User ID must be a number.", reply_to_message_id=message_id)
            return
        status_message = bot.unblock_user_access(target_user_id)
        bot.register_bot_commands()
        admin_send_message(chat_id, status_message, reply_to_message_id=message_id)
        profile = bot.known_user_profiles.get(target_user_id, {})
        target_chat_id = profile.get("chat_id")
        if isinstance(target_chat_id, int):
            bot.send_message(target_chat_id, "Admin removed your block. Use /login <hash> if you still need access.")
        return

    if command == "/replyuser":
        target_part, separator, reply_text = argument.partition("|")
        if not separator or not target_part.strip() or not reply_text.strip():
            admin_send_message(chat_id, "Use /replyuser <id> | <text>.", reply_to_message_id=message_id)
            return
        try:
            target_user_id = int(target_part.strip())
        except ValueError:
            admin_send_message(chat_id, "User ID must be a number.", reply_to_message_id=message_id)
            return
        profile = bot.known_user_profiles.get(target_user_id, {})
        target_chat_id = profile.get("chat_id")
        if not isinstance(target_chat_id, int):
            admin_send_message(chat_id, "No known chat ID for that user yet.", reply_to_message_id=message_id)
            return
        bot.send_message(target_chat_id, bot.normalize_plain_text(reply_text))
        admin_send_message(chat_id, "Message sent to user.", reply_to_message_id=message_id)
        return

    admin_send_message(chat_id, admin_help_text(), reply_to_message_id=message_id)


def main() -> None:
    logger.info("Admin bot started for admin user IDs %s", sorted(bot.TELEGRAM_ADMIN_USER_IDS))
    offset: int | None = None
    commands_registered = False

    while True:
        try:
            if not commands_registered:
                register_admin_commands()
                commands_registered = True
            updates = get_admin_updates(offset)
            for update in updates:
                offset = update["update_id"] + 1
                message = update.get("message")
                if message:
                    handle_admin_message(message)
        except KeyboardInterrupt:
            logger.info("Admin bot stopped by user")
            break
        except Exception:
            logger.exception("Admin polling loop failed, retrying shortly")
            time.sleep(3)


if __name__ == "__main__":
    main()
