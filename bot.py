from __future__ import annotations

import base64
import html
import ipaddress
import io
import json
import logging
import mimetypes
import os
import re
import secrets
import socket
import tempfile
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv


load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

BASE_RESPONSE_RULES = (
    "Reply in plain text only. "
    "Do not use Markdown. "
    "Do not use #, *, **, backticks, tables, or bold formatting. "
    "Do not add maximum or minimum labels or sections unless the user explicitly asks for them. "
    "Keep the response minimal, simple, and easy to read."
)


def with_base_rules(prompt: str) -> str:
    prompt = prompt.strip()
    if BASE_RESPONSE_RULES in prompt:
        return prompt
    return f"{prompt} {BASE_RESPONSE_RULES}".strip()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "").strip()
OPENROUTER_API_URL = os.getenv(
    "OPENROUTER_API_URL",
    "https://openrouter.ai/api/v1/chat/completions",
).strip()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_ADMIN_BOT_TOKEN = os.getenv("TELEGRAM_ADMIN_BOT_TOKEN", "").strip()
BOT_SYSTEM_PROMPT = with_base_rules(
    os.getenv(
        "BOT_SYSTEM_PROMPT",
        "You are a helpful Telegram assistant.",
    )
)
PRESENTATION_SYSTEM_PROMPT = with_base_rules(
    os.getenv(
        "PRESENTATION_SYSTEM_PROMPT",
        (
            "You are an expert presentation and slide deck creator. "
            "When the user asks for a presentation, produce a practical deck draft that is ready "
            "to turn into slides. Start with a clear title and short deck objective, then provide "
            "a slide-by-slide outline using plain text. For each slide, include the slide title and "
            "concise points. When useful, also suggest speaker notes, visuals, or charts. Keep the "
            "structure clear, persuasive, concise, and easy to paste into a text file."
        ),
    )
)
BURMESE_SYSTEM_PROMPT = with_base_rules(
    os.getenv(
        "BURMESE_SYSTEM_PROMPT",
        (
            "You are a helpful Telegram assistant who writes natural, smooth Burmese. "
            "Reply like a real Burmese chatbot having a normal conversation. "
            "Use complete thoughts and complete ending sentences. "
            "Do not stop in the middle of a sentence. "
            "Avoid stiff literal translation. "
            "Do not mix random English words into Burmese unless the user asked for English or the term is truly standard. "
            "Prefer natural Burmese wording over transliterated technical fragments when possible. "
            "If the user writes in Burmese, reply in Burmese unless they ask otherwise."
        ),
    )
)
LINK_ANALYSIS_SYSTEM_PROMPT = with_base_rules(
    os.getenv(
        "LINK_ANALYSIS_SYSTEM_PROMPT",
        (
            "You analyze public web pages for the user. "
            "Give a short plain-text summary, key points, and any obvious red flags or missing context. "
            "If the page content is limited, say so clearly."
        ),
    )
)
FILE_ANALYSIS_SYSTEM_PROMPT = with_base_rules(
    os.getenv(
        "FILE_ANALYSIS_SYSTEM_PROMPT",
        (
            "You analyze user-uploaded files. "
            "Read the extracted contents and answer the user's request clearly. "
            "If no specific request is given, summarize the important points in a useful way."
        ),
    )
)
IMAGE_ANALYSIS_SYSTEM_PROMPT = with_base_rules(
    os.getenv(
        "IMAGE_ANALYSIS_SYSTEM_PROMPT",
        (
            "You analyze user-uploaded photos and images. "
            "Describe the important details, answer the user's question, and extract visible text when useful. "
            "If no question is given, provide a practical analysis of what is shown."
        ),
    )
)
GENERIC_COMMAND_SYSTEM_PROMPT = with_base_rules(
    os.getenv(
        "GENERIC_COMMAND_SYSTEM_PROMPT",
        (
            "You are a practical assistant that follows the user's requested output format closely. "
            "Be useful, clear, and well-structured."
        ),
    )
)
PDF_SYSTEM_PROMPT = with_base_rules(
    os.getenv(
        "PDF_SYSTEM_PROMPT",
        (
            "You prepare clean document text that will be exported to PDF. "
            "Keep the structure readable and helpful. "
            "If the user asks for a PDF on a topic, produce content that is ready to turn into a document."
        ),
    )
)
SOCIAL_CONTENT_SYSTEM_PROMPT = with_base_rules(
    os.getenv(
        "SOCIAL_CONTENT_SYSTEM_PROMPT",
        (
            "You are a strong social media content writer. "
            "When the user message includes the keyword content or contents, produce a longer-form "
            "social-media-ready version of the answer. "
            "Make it engaging, practical, and easy to post. "
            "Use a strong opening, clear structure, and a natural closing or call to action when useful. "
            "Match the user's language. "
            "If the user writes in Burmese, write smooth natural Burmese with complete ending sentences "
            "and avoid random English fragments unless needed."
        ),
    )
)
BOT_TIMEZONE = os.getenv("BOT_TIMEZONE", "Asia/Rangoon").strip()
BOT_STORAGE_PATH = os.getenv("BOT_STORAGE_PATH", "bot_state.json").strip()
ADMIN_DASHBOARD_PORT = int(os.getenv("ADMIN_DASHBOARD_PORT", "5060").strip())
ADMIN_DASHBOARD_PASSWORD = os.getenv("ADMIN_DASHBOARD_PASSWORD", "").strip()
ADMIN_DASHBOARD_SECRET = os.getenv("ADMIN_DASHBOARD_SECRET", "").strip()

URL_PATTERN = re.compile(r"https?://\S+", re.IGNORECASE)
MYANMAR_CHAR_PATTERN = re.compile(r"[\u1000-\u109F\uA9E0-\uA9FF\uAA60-\uAA7F]")
TAG_PATTERN = re.compile(r"<[^>]+>")
SIMPLE_TIME_PATTERN = re.compile(r"^\d{1,2}(:\d{2})?\s*(am|pm)?$", re.IGNORECASE)
CONTENTS_KEYWORD_PATTERN = re.compile(r"\bcontents?\b", re.IGNORECASE)
CONTENT_TYPE_JSON = "application/json"
MIME_TYPE_JPEG = "image/jpeg"
WEB_PAGE_SUMMARY_TITLE = "Web Page Summary"
CMD_HIDEBUTTONS = "/hidebuttons"
CMD_REWRITE = "/rewrite"
CMD_SUMMARIZE = "/summarize"
CMD_NOTE = "/note"
CMD_NOTES = "/notes"
USER_BOT_COMMANDS = [
    {"command": "start", "description": "Show bot intro and quick actions"},
    {"command": "help", "description": "Show all available commands"},
    {"command": "login", "description": "Log in with an access hash"},
    {"command": "menu", "description": "Show organized button menu"},
    {"command": "hidebuttons", "description": "Hide the button keyboard"},
    {"command": "reset", "description": "Clear chat memory and reset mode"},
    {"command": "english", "description": "Reply in English"},
    {"command": "burmese", "description": "Reply in smooth Burmese"},
    {"command": "persona", "description": "Set a reusable response role"},
    {"command": "tone", "description": "Set your preferred writing style"},
    {"command": "note", "description": "Save a note from text"},
    {"command": "notes", "description": "List or delete saved notes"},
    {"command": "analyze", "description": "Analyze a replied file or photo"},
    {"command": "pdf", "description": "Create a PDF from text or a reply"},
    {"command": "webpdf", "description": "Turn a web page into a PDF"},
    {"command": "caption", "description": "Create a social media caption"},
    {"command": "hook", "description": "Create strong opening hooks"},
    {"command": "carousel", "description": "Create a carousel post outline"},
    {"command": "script", "description": "Create a video or reel script"},
    {"command": "cta", "description": "Create call-to-action lines"},
    {"command": "hashtags", "description": "Create relevant hashtags"},
    {"command": "quiz", "description": "Create quiz questions from a topic"},
    {"command": "flashcards", "description": "Create study flashcards"},
    {"command": "explain", "description": "Explain a topic simply"},
    {"command": "exam", "description": "Create exam-style questions"},
    {"command": "plan", "description": "Create a business plan draft"},
    {"command": "pitch", "description": "Create a business pitch"},
    {"command": "pricing", "description": "Suggest pricing structure"},
    {"command": "strategy", "description": "Create a business strategy"},
    {"command": "swot", "description": "Create a SWOT analysis"},
    {"command": "businessmodel", "description": "Create a business model outline"},
    {"command": "qr", "description": "Create a QR code from text or a link"},
    {"command": "rewrite", "description": "Rewrite text in a better way"},
    {"command": "shorter", "description": "Make text shorter"},
    {"command": "formal", "description": "Make text more formal"},
    {"command": "friendly", "description": "Make text more friendly"},
    {"command": "translate", "description": "Translate text"},
    {"command": "fixgrammar", "description": "Fix grammar and wording"},
    {"command": "summarize", "description": "Summarize text"},
    {"command": "remind", "description": "Create a reminder"},
    {"command": "reminders", "description": "List or delete reminders"},
    {"command": "todo", "description": "Manage your to-do list"},
    {"command": "idea", "description": "Save a quick idea"},
    {"command": "ideas", "description": "List saved ideas"},
    {"command": "link", "description": "Analyze a public link"},
    {"command": "presentation", "description": "Create a simple deck outline"},
]
PUBLIC_BOT_COMMANDS = [
    {"command": "start", "description": "Start and see login help"},
    {"command": "help", "description": "Show basic help"},
    {"command": "login", "description": "Log in with an access hash"},
]
MAIN_REPLY_KEYBOARD = {
    "keyboard": [
        [{"text": "/help"}, {"text": "/reset"}, {"text": CMD_HIDEBUTTONS}],
        [{"text": "/analyze"}, {"text": "/pdf"}, {"text": "/webpdf"}],
        [{"text": "/link"}, {"text": "/qr"}],
        [{"text": "/caption"}, {"text": "/script"}, {"text": "/carousel"}],
        [{"text": "/quiz"}, {"text": "/flashcards"}, {"text": "/plan"}],
        [{"text": "/todo list"}, {"text": "/reminders"}, {"text": "/ideas"}],
        [{"text": "/burmese"}, {"text": "/english"}, {"text": "/menu more"}],
    ],
    "resize_keyboard": True,
    "is_persistent": True,
    "input_field_placeholder": "Choose a tool or type a message",
}
MORE_REPLY_KEYBOARD = {
    "keyboard": [
        [{"text": "/hook"}, {"text": "/cta"}, {"text": "/hashtags"}],
        [{"text": "/explain"}, {"text": "/exam"}],
        [{"text": "/pitch"}, {"text": "/pricing"}, {"text": "/strategy"}],
        [{"text": "/swot"}, {"text": "/businessmodel"}],
        [{"text": "/persona"}, {"text": "/tone"}],
        [{"text": CMD_REWRITE}, {"text": "/translate"}, {"text": CMD_SUMMARIZE}],
        [{"text": "/menu"}, {"text": CMD_HIDEBUTTONS}],
    ],
    "resize_keyboard": True,
    "is_persistent": True,
    "input_field_placeholder": "Choose more tools or type a message",
}
REMOVE_REPLY_KEYBOARD = {
    "remove_keyboard": True,
}
PERSONA_PROMPTS = {
    "coach": "Act like a practical coach. Be encouraging, direct, and action-focused.",
    "teacher": "Act like a clear teacher. Explain things simply and step by step.",
    "marketer": "Act like a sharp marketer. Focus on positioning, persuasion, and audience clarity.",
    "assistant": "Act like a reliable personal assistant. Be concise, organized, and useful.",
    "coder": "Act like a senior coding assistant. Be technical, precise, and solution-oriented.",
    "translator": "Act like a careful Burmese-English translator. Preserve meaning and natural phrasing.",
    "storyteller": "Act like a storyteller. Use vivid but clean language with a natural flow.",
}


def load_persistent_state() -> dict[str, Any]:
    if not os.path.exists(BOT_STORAGE_PATH):
        return {}

    try:
        with open(BOT_STORAGE_PATH, "r", encoding="utf-8") as storage_file:
            data = json.load(storage_file)
            return data if isinstance(data, dict) else {}
    except Exception:
        logger.exception("Could not load bot state from %s", BOT_STORAGE_PATH)
        return {}


def normalize_int_key_map(raw_data: Any) -> dict[int, Any]:
    normalized: dict[int, Any] = {}
    if not isinstance(raw_data, dict):
        return normalized

    for key, value in raw_data.items():
        try:
            normalized[int(key)] = value
        except (TypeError, ValueError):
            continue
    return normalized


def normalize_int_set(raw_data: Any) -> set[int]:
    normalized: set[int] = set()
    if isinstance(raw_data, (list, tuple, set)):
        for item in raw_data:
            try:
                normalized.add(int(item))
            except (TypeError, ValueError):
                continue
    return normalized


def normalize_dict_list(raw_data: Any) -> list[dict[str, Any]]:
    # Keep persisted collections structurally safe before the rest of the bot reads them.
    if not isinstance(raw_data, list):
        return []
    return [item for item in raw_data if isinstance(item, dict)]


PERSISTENT_STATE = load_persistent_state()


def parse_allowed_user_ids() -> set[int]:
    raw_ids = os.getenv("TELEGRAM_ALLOWED_USER_IDS", "").strip()
    if raw_ids:
        parsed_ids: set[int] = set()
        for raw_id in raw_ids.split(","):
            value = raw_id.strip()
            if not value:
                continue
            try:
                parsed_ids.add(int(value))
            except ValueError as exc:
                raise RuntimeError(
                    "TELEGRAM_ALLOWED_USER_IDS must be a comma-separated list of integers."
                ) from exc
        if not parsed_ids:
            raise RuntimeError("TELEGRAM_ALLOWED_USER_IDS is missing.")
        return parsed_ids

    legacy_user_id = os.getenv("TELEGRAM_ALLOWED_USER_ID", "").strip()
    if not legacy_user_id:
        raise RuntimeError(
            "Set TELEGRAM_ALLOWED_USER_IDS or TELEGRAM_ALLOWED_USER_ID in the environment."
        )

    try:
        return {int(legacy_user_id)}
    except ValueError as exc:
        raise RuntimeError("TELEGRAM_ALLOWED_USER_ID must be an integer.") from exc


TELEGRAM_ALLOWED_USER_IDS = parse_allowed_user_ids()


def parse_admin_user_ids() -> set[int]:
    raw_ids = os.getenv("TELEGRAM_ADMIN_USER_IDS", "").strip()
    if not raw_ids:
        return {1201884652}

    parsed_ids: set[int] = set()
    for raw_id in raw_ids.split(","):
        value = raw_id.strip()
        if not value:
            continue
        try:
            parsed_ids.add(int(value))
        except ValueError as exc:
            raise RuntimeError(
                "TELEGRAM_ADMIN_USER_IDS must be a comma-separated list of integers."
            ) from exc

    return parsed_ids or {1201884652}


TELEGRAM_ADMIN_USER_IDS = parse_admin_user_ids()

if not OPENROUTER_API_KEY:
    raise RuntimeError("OPENROUTER_API_KEY is missing.")
if not OPENROUTER_MODEL:
    raise RuntimeError("OPENROUTER_MODEL is missing.")
if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN is missing.")

TELEGRAM_API_BASE = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
MESSAGE_HISTORY_LIMIT = 6
TELEGRAM_MESSAGE_LIMIT = 4096
REQUEST_TIMEOUT = 60
POLL_TIMEOUT = 30
HISTORY_ENTRY_CHAR_LIMIT = 320
SUMMARY_ENTRY_CHAR_LIMIT = 180
CONVERSATION_SUMMARY_CHAR_LIMIT = 1200
RECENT_CONTEXT_CHAR_LIMIT = 2400
SOURCE_TEXT_CHAR_LIMIT = 3500
DEFAULT_MAX_TOKENS = 550
BURMESE_MAX_TOKENS = 700
PRESENTATION_MAX_TOKENS = 900
SOCIAL_CONTENT_MAX_TOKENS = 900
TRANSFORM_MAX_TOKENS = 380
SUMMARY_MAX_TOKENS = 220
LINK_ANALYSIS_MAX_TOKENS = 420
ATTACHMENT_ANALYSIS_MAX_TOKENS = 650
CONTINUATION_MAX_ROUNDS = 2
FILE_TEXT_CHAR_LIMIT = 8000
PDF_MAX_TOKENS = 900
COMMAND_PACK_MAX_TOKENS = 700

session = requests.Session()
conversation_history: dict[int, deque[dict[str, str]]] = defaultdict(
    lambda: deque(maxlen=MESSAGE_HISTORY_LIMIT)
)
conversation_modes: dict[int, str] = defaultdict(lambda: "chat")
response_languages: dict[int, str] = defaultdict(
    lambda: "default",
    {
        user_id: str(language)
        for user_id, language in normalize_int_key_map(
            PERSISTENT_STATE.get("response_languages")
        ).items()
    },
)
tone_preferences: dict[int, str] = {
    user_id: str(value)
    for user_id, value in normalize_int_key_map(PERSISTENT_STATE.get("tone_preferences")).items()
}
conversation_summaries: dict[int, str] = {}
persona_preferences: dict[int, str] = {
    user_id: str(value)
    for user_id, value in normalize_int_key_map(PERSISTENT_STATE.get("persona_preferences")).items()
}
todo_store: dict[int, list[dict[str, Any]]] = {
    user_id: value if isinstance(value, list) else []
    for user_id, value in normalize_int_key_map(PERSISTENT_STATE.get("todos")).items()
}
idea_store: dict[int, list[dict[str, Any]]] = {
    user_id: value if isinstance(value, list) else []
    for user_id, value in normalize_int_key_map(PERSISTENT_STATE.get("ideas")).items()
}
reminder_store: list[dict[str, Any]] = normalize_dict_list(PERSISTENT_STATE.get("reminders"))
approved_user_ids: set[int] = normalize_int_set(PERSISTENT_STATE.get("approved_user_ids"))
approved_user_ids.update(TELEGRAM_ALLOWED_USER_IDS)
approved_user_ids.update(TELEGRAM_ADMIN_USER_IDS)
blocked_user_ids: set[int] = normalize_int_set(PERSISTENT_STATE.get("blocked_user_ids"))
blocked_user_ids.difference_update(TELEGRAM_ADMIN_USER_IDS)
login_hash_store: dict[str, dict[str, Any]] = {
    str(key).strip().upper(): value
    for key, value in (PERSISTENT_STATE.get("login_hashes") or {}).items()
    if isinstance(key, str) and isinstance(value, dict)
}
known_user_profiles: dict[int, dict[str, Any]] = {
    user_id: value if isinstance(value, dict) else {}
    for user_id, value in normalize_int_key_map(PERSISTENT_STATE.get("known_user_profiles")).items()
}
activity_log: list[dict[str, Any]] = normalize_dict_list(PERSISTENT_STATE.get("activity_log"))
note_store: dict[int, list[dict[str, Any]]] = {
    user_id: value if isinstance(value, list) else []
    for user_id, value in normalize_int_key_map(PERSISTENT_STATE.get("notes")).items()
}


def write_state_payload(payload: dict[str, Any]) -> None:
    directory = os.path.dirname(BOT_STORAGE_PATH)
    if directory:
        os.makedirs(directory, exist_ok=True)

    temp_path = f"{BOT_STORAGE_PATH}.tmp"
    with open(temp_path, "w", encoding="utf-8") as storage_file:
        json.dump(payload, storage_file, ensure_ascii=False, indent=2)
    os.replace(temp_path, BOT_STORAGE_PATH)


def save_persistent_state() -> None:
    payload = {
        "response_languages": {str(key): value for key, value in response_languages.items()},
        "tone_preferences": {str(key): value for key, value in tone_preferences.items()},
        "persona_preferences": {str(key): value for key, value in persona_preferences.items()},
        "todos": {str(key): value for key, value in todo_store.items()},
        "ideas": {str(key): value for key, value in idea_store.items()},
        "notes": {str(key): value for key, value in note_store.items()},
        "reminders": reminder_store,
        "approved_user_ids": sorted(approved_user_ids),
        "blocked_user_ids": sorted(blocked_user_ids),
        "login_hashes": login_hash_store,
        "known_user_profiles": {str(key): value for key, value in known_user_profiles.items()},
        "activity_log": activity_log,
    }
    write_state_payload(payload)


def refresh_auth_related_state() -> None:
    disk_state = load_persistent_state()

    approved_user_ids.clear()
    approved_user_ids.update(normalize_int_set(disk_state.get("approved_user_ids")))
    approved_user_ids.update(TELEGRAM_ALLOWED_USER_IDS)
    approved_user_ids.update(TELEGRAM_ADMIN_USER_IDS)

    blocked_user_ids.clear()
    blocked_user_ids.update(normalize_int_set(disk_state.get("blocked_user_ids")))
    blocked_user_ids.difference_update(TELEGRAM_ADMIN_USER_IDS)

    login_hash_store.clear()
    login_hash_store.update(
        {
            str(key).strip().upper(): value
            for key, value in (disk_state.get("login_hashes") or {}).items()
            if isinstance(key, str) and isinstance(value, dict)
        }
    )

    known_user_profiles.clear()
    known_user_profiles.update(
        {
            user_id: value if isinstance(value, dict) else {}
            for user_id, value in normalize_int_key_map(disk_state.get("known_user_profiles")).items()
        }
    )

    activity_log.clear()
    raw_activity = disk_state.get("activity_log")
    if isinstance(raw_activity, list):
        for item in raw_activity:
            if isinstance(item, dict):
                activity_log.append(item)


def save_auth_related_state() -> None:
    disk_state = load_persistent_state()
    payload = disk_state if isinstance(disk_state, dict) else {}
    payload["approved_user_ids"] = sorted(approved_user_ids)
    payload["blocked_user_ids"] = sorted(blocked_user_ids)
    payload["login_hashes"] = login_hash_store
    payload["known_user_profiles"] = {str(key): value for key, value in known_user_profiles.items()}
    payload["activity_log"] = activity_log
    payload["notes"] = {str(key): value for key, value in note_store.items()}
    write_state_payload(payload)


def now_local() -> datetime:
    return datetime.now(ZoneInfo(BOT_TIMEZONE))


def new_item_id() -> str:
    return uuid.uuid4().hex[:8]


def is_admin_user(user_id: int) -> bool:
    return user_id in TELEGRAM_ADMIN_USER_IDS


def is_blocked_user(user_id: int) -> bool:
    return user_id in blocked_user_ids and not is_admin_user(user_id)


def is_authorized_user(user_id: int) -> bool:
    return not is_blocked_user(user_id) and (user_id in approved_user_ids or is_admin_user(user_id))


def generate_login_hash() -> str:
    return secrets.token_hex(5).upper()


def create_login_hash(created_by: int) -> str:
    refresh_auth_related_state()
    login_hash = generate_login_hash()
    while login_hash in login_hash_store:
        login_hash = generate_login_hash()

    login_hash_store[login_hash] = {
        "created_at": now_local().isoformat(),
        "created_by": created_by,
    }
    save_auth_related_state()
    return login_hash


def consume_login_hash(user_id: int, login_hash: str) -> tuple[bool, str]:
    refresh_auth_related_state()
    normalized_hash = login_hash.strip().upper()
    if not normalized_hash:
        return False, "Use /login <hash>."

    if is_blocked_user(user_id):
        return False, "Your access is blocked. Ask the admin to unblock you."

    if is_authorized_user(user_id):
        return True, "You already have access."

    hash_entry = login_hash_store.pop(normalized_hash, None)
    if not hash_entry:
        save_auth_related_state()
        return False, "Invalid or already used hash."

    approved_user_ids.add(user_id)
    save_auth_related_state()
    logger.info("Approved new user_id=%s via login hash", user_id)
    return True, "Login successful. Access granted."


def describe_user_name(profile: dict[str, Any]) -> str:
    first_name = str(profile.get("first_name", "")).strip()
    last_name = str(profile.get("last_name", "")).strip()
    full_name = " ".join(part for part in [first_name, last_name] if part).strip()
    username = str(profile.get("username", "")).strip()
    if full_name and username:
        return f"{full_name} (@{username})"
    if full_name:
        return full_name
    if username:
        return f"@{username}"
    return "Unknown user"


def get_account_link(user_id: int) -> str:
    profile = known_user_profiles.get(user_id, {})
    username = str(profile.get("username", "")).strip().lstrip("@")
    if username:
        return f"https://t.me/{username}"
    return f"tg://user?id={user_id}"


def get_user_status_label(user_id: int) -> str:
    if is_admin_user(user_id):
        return "admin"
    if user_id in blocked_user_ids:
        return "blocked"
    if user_id in approved_user_ids:
        return "approved"
    return "pending"


def format_profile_summary(user_id: int) -> str:
    profile = known_user_profiles.get(user_id, {})
    lines = [
        f"User ID: {user_id}",
        f"Status: {get_user_status_label(user_id)}",
        f"Name: {describe_user_name(profile)}",
        f"Account link: {get_account_link(user_id)}",
    ]
    if profile.get("chat_id"):
        lines.append(f"Chat ID: {profile['chat_id']}")
    if profile.get("first_seen"):
        lines.append(f"First seen: {format_local_datetime(str(profile['first_seen']))}")
    if profile.get("last_seen"):
        lines.append(f"Last seen: {format_local_datetime(str(profile['last_seen']))}")
    last_request = str(profile.get("last_request", "")).strip()
    if last_request:
        lines.append(f"Last request: {last_request}")
    return "\n".join(lines)


def append_activity_event(user_id: int, request_preview: str) -> None:
    refresh_auth_related_state()
    activity_log.append(
        {
            "id": new_item_id(),
            "user_id": user_id,
            "status": get_user_status_label(user_id),
            "account_link": get_account_link(user_id),
            "name": describe_user_name(known_user_profiles.get(user_id, {})),
            "message": clip_text(request_preview, 1200),
            "created_at": now_local().isoformat(),
        }
    )
    if len(activity_log) > 200:
        del activity_log[:-200]
    save_auth_related_state()


def update_known_user_profile(
    user_id: int,
    chat_id: int,
    from_user: dict[str, Any],
    request_preview: str,
) -> None:
    refresh_auth_related_state()
    existing = known_user_profiles.get(user_id, {})
    profile = {
        "chat_id": chat_id,
        "username": str(from_user.get("username") or "").strip(),
        "first_name": str(from_user.get("first_name") or "").strip(),
        "last_name": str(from_user.get("last_name") or "").strip(),
        "first_seen": existing.get("first_seen") or now_local().isoformat(),
        "last_seen": now_local().isoformat(),
        "last_request": clip_text(request_preview, 700),
    }
    known_user_profiles[user_id] = profile
    save_auth_related_state()


def get_message_request_preview(message: dict[str, Any], text: str) -> str:
    normalized_text = normalize_plain_text(text).strip()
    if normalized_text:
        return normalized_text

    if has_voice_input_attachment(message):
        return "[audio message]"

    if message.get("photo"):
        caption = normalize_plain_text(str(message.get("caption") or "")).strip()
        return f"[photo] {caption}".strip()

    document = message.get("document") or {}
    if document:
        file_name = str(document.get("file_name") or "file").strip()
        caption = normalize_plain_text(str(message.get("caption") or "")).strip()
        suffix = f" {caption}" if caption else ""
        return f"[document: {file_name}]{suffix}".strip()

    return "[non-text request]"


def notify_admins(text: str, exclude_user_id: int | None = None) -> None:
    for admin_user_id in sorted(TELEGRAM_ADMIN_USER_IDS):
        if exclude_user_id is not None and admin_user_id == exclude_user_id:
            continue
        try:
            if TELEGRAM_ADMIN_BOT_TOKEN:
                send_message_via_token(TELEGRAM_ADMIN_BOT_TOKEN, admin_user_id, text)
            else:
                send_message(admin_user_id, text)
        except Exception:
            logger.exception("Could not notify admin user_id=%s", admin_user_id)


def build_admin_request_notice(user_id: int, request_preview: str) -> str:
    status = get_user_status_label(user_id)
    title = "Unknown user reached the bot" if status == "pending" else "User activity"
    lines = [
        title,
        format_profile_summary(user_id),
        f"Message: {clip_text(request_preview, 1200)}",
        f"Reply command: /replyuser {user_id} | <text>",
    ]
    return "\n".join(lines)


def approve_user_access(target_user_id: int) -> str:
    refresh_auth_related_state()
    if is_admin_user(target_user_id):
        return "Admin accounts already have access."
    blocked_user_ids.discard(target_user_id)
    approved_user_ids.add(target_user_id)
    save_auth_related_state()
    return "User approved."


def block_user_access(target_user_id: int) -> str:
    refresh_auth_related_state()
    if is_admin_user(target_user_id):
        return "Admin accounts cannot be blocked."
    blocked_user_ids.add(target_user_id)
    approved_user_ids.discard(target_user_id)
    save_auth_related_state()
    return "User blocked."


def unblock_user_access(target_user_id: int) -> str:
    refresh_auth_related_state()
    blocked_user_ids.discard(target_user_id)
    save_auth_related_state()
    return "User unblocked."


def format_local_datetime(value: str) -> str:
    return datetime.fromisoformat(value).astimezone(ZoneInfo(BOT_TIMEZONE)).strftime(
        "%Y-%m-%d %H:%M"
    )


def chunk_text(text: str, limit: int = TELEGRAM_MESSAGE_LIMIT) -> list[str]:
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= limit:
            chunks.append(remaining)
            break

        split_at = remaining.rfind("\n", 0, limit)
        if split_at == -1 or split_at < limit // 2:
            split_at = limit
        chunks.append(remaining[:split_at].rstrip())
        remaining = remaining[split_at:].lstrip()
    return chunks


def telegram_api(method: str, payload: dict[str, Any]) -> dict[str, Any]:
    response = session.post(
        f"{TELEGRAM_API_BASE}/{method}",
        json=payload,
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    data = response.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram API error: {data}")
    return data


def send_message(
    chat_id: int,
    text: str,
    reply_to_message_id: int | None = None,
    reply_markup: dict[str, Any] | None = None,
) -> None:
    for index, chunk in enumerate(chunk_text(text or "Empty response.")):
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "text": chunk,
        }
        if index == 0 and reply_to_message_id is not None:
            payload["reply_to_message_id"] = reply_to_message_id
        if index == 0 and reply_markup is not None:
            payload["reply_markup"] = reply_markup
        telegram_api("sendMessage", payload)


def send_message_via_token(
    bot_token: str,
    chat_id: int,
    text: str,
    reply_to_message_id: int | None = None,
) -> None:
    if not bot_token:
        raise RuntimeError("Bot token is missing.")

    api_base = f"https://api.telegram.org/bot{bot_token}"
    for index, chunk in enumerate(chunk_text(text or "Empty response.")):
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "text": chunk,
        }
        if index == 0 and reply_to_message_id is not None:
            payload["reply_to_message_id"] = reply_to_message_id

        response = session.post(
            f"{api_base}/sendMessage",
            json=payload,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
        if not data.get("ok"):
            raise RuntimeError(f"Telegram API error: {data}")


def get_menu_keyboard(menu_name: str = "main") -> dict[str, Any]:
    if menu_name == "more":
        return MORE_REPLY_KEYBOARD
    return MAIN_REPLY_KEYBOARD


def send_chat_action(chat_id: int, action: str = "typing") -> None:
    telegram_api("sendChatAction", {"chat_id": chat_id, "action": action})


def send_document(
    chat_id: int,
    document_path: str,
    file_name: str,
    caption: str | None = None,
    reply_to_message_id: int | None = None,
) -> None:
    payload: dict[str, Any] = {
        "chat_id": str(chat_id),
    }
    if caption:
        payload["caption"] = caption
    if reply_to_message_id is not None:
        payload["reply_to_message_id"] = str(reply_to_message_id)

    with open(document_path, "rb") as document_file:
        response = session.post(
            f"{TELEGRAM_API_BASE}/sendDocument",
            data=payload,
            files={
                "document": (file_name, document_file, "application/pdf"),
            },
            timeout=REQUEST_TIMEOUT,
        )

    response.raise_for_status()
    data = response.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram API error: {data}")


def send_photo_file(
    chat_id: int,
    photo_path: str,
    file_name: str,
    caption: str | None = None,
    reply_to_message_id: int | None = None,
) -> None:
    payload: dict[str, Any] = {
        "chat_id": str(chat_id),
    }
    if caption:
        payload["caption"] = caption
    if reply_to_message_id is not None:
        payload["reply_to_message_id"] = str(reply_to_message_id)

    with open(photo_path, "rb") as photo_file:
        response = session.post(
            f"{TELEGRAM_API_BASE}/sendPhoto",
            data=payload,
            files={
                "photo": (file_name, photo_file, "image/png"),
            },
            timeout=REQUEST_TIMEOUT,
        )

    response.raise_for_status()
    data = response.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram API error: {data}")


def get_telegram_file_bytes(file_id: str) -> tuple[bytes, str]:
    file_data = telegram_api("getFile", {"file_id": file_id})
    try:
        file_path = str(file_data["result"]["file_path"])
    except (KeyError, TypeError) as exc:
        raise RuntimeError(f"Unexpected Telegram file response: {file_data}") from exc

    response = session.get(
        f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}",
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    return response.content, file_path


def register_bot_commands() -> None:
    refresh_auth_related_state()
    telegram_api(
        "setMyCommands",
        {
            "commands": PUBLIC_BOT_COMMANDS,
            "scope": {"type": "default"},
        },
    )
    telegram_api(
        "setMyCommands",
        {
            "commands": PUBLIC_BOT_COMMANDS,
            "scope": {"type": "all_private_chats"},
        },
    )

    scoped_chat_ids = set(known_user_profiles) | approved_user_ids | blocked_user_ids | TELEGRAM_ADMIN_USER_IDS
    for target_user_id in sorted(scoped_chat_ids):
        scope = {"type": "chat", "chat_id": target_user_id}
        if target_user_id in approved_user_ids and not is_blocked_user(target_user_id):
            telegram_api("setMyCommands", {"commands": USER_BOT_COMMANDS, "scope": scope})
        else:
            telegram_api("deleteMyCommands", {"scope": scope})

    logger.info(
        "Registered scoped bot commands: public=%s user=%s",
        len(PUBLIC_BOT_COMMANDS),
        len(USER_BOT_COMMANDS),
    )


def extract_text_content(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text = item.get("text", "")
                if text:
                    parts.append(str(text))
        return "\n".join(parts).strip()

    return ""


def normalize_plain_text(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    normalized = normalized.replace("**", "").replace("__", "").replace("`", "")

    lines: list[str] = []
    for line in normalized.split("\n"):
        line = re.sub(r"^\s{0,3}#{1,6}\s*", "", line)
        line = re.sub(r"^\s*>\s?", "", line)
        lines.append(line.rstrip())

    normalized = "\n".join(lines)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


def clip_text(text: str, limit: int) -> str:
    text = normalize_plain_text(text)
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def add_summary_fragment(user_id: int, role: str, content: str) -> None:
    fragment = f"{role}: {clip_text(content, SUMMARY_ENTRY_CHAR_LIMIT)}"
    existing = conversation_summaries.get(user_id, "").strip()
    updated = f"{existing}\n{fragment}".strip() if existing else fragment
    conversation_summaries[user_id] = updated[-CONVERSATION_SUMMARY_CHAR_LIMIT:].strip()


def append_history_message(user_id: int, role: str, content: str) -> None:
    history = conversation_history[user_id]
    if history.maxlen is not None and len(history) >= history.maxlen:
        dropped = history.popleft()
        dropped_role = "User" if dropped.get("role") == "user" else "Bot"
        add_summary_fragment(user_id, dropped_role, str(dropped.get("content", "")))

    history.append({"role": role, "content": clip_text(content, HISTORY_ENTRY_CHAR_LIMIT)})


def remember_exchange(user_id: int, user_message: str, assistant_reply: str) -> None:
    append_history_message(user_id, "user", user_message)
    append_history_message(user_id, "assistant", assistant_reply)


def contains_myanmar_text(text: str) -> bool:
    return bool(MYANMAR_CHAR_PATTERN.search(text))


def has_social_content_keyword(text: str) -> bool:
    return bool(CONTENTS_KEYWORD_PATTERN.search(text))


def guess_mime_type(file_name: str, fallback: str = "") -> str:
    guessed, _ = mimetypes.guess_type(file_name)
    return guessed or fallback or "application/octet-stream"


def is_image_type(file_name: str, mime_type: str) -> bool:
    mime = mime_type.lower()
    if mime.startswith("image/"):
        return True
    suffix = os.path.splitext(file_name.lower())[1]
    return suffix in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}


def extract_text_from_file_bytes(file_name: str, mime_type: str, file_bytes: bytes) -> str:
    suffix = os.path.splitext(file_name.lower())[1]

    if mime_type.startswith("text/") or suffix in {".txt", ".md", ".py", ".js", ".ts", ".html", ".css"}:
        return file_bytes.decode("utf-8", errors="ignore")

    if suffix in {".json"}:
        return file_bytes.decode("utf-8", errors="ignore")

    if suffix in {".csv", ".tsv"}:
        return file_bytes.decode("utf-8", errors="ignore")

    if suffix == ".pdf" or mime_type == "application/pdf":
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(file_bytes))
        pages: list[str] = []
        for page in reader.pages[:15]:
            pages.append(page.extract_text() or "")
        return "\n\n".join(pages)

    if suffix == ".docx" or mime_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        from docx import Document

        document = Document(io.BytesIO(file_bytes))
        return "\n".join(paragraph.text for paragraph in document.paragraphs)

    raise RuntimeError("Unsupported file type. Try txt, pdf, docx, csv, json, or an image.")


def build_data_url(mime_type: str, file_bytes: bytes) -> str:
    encoded = base64.b64encode(file_bytes).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def get_pdf_font_name() -> str:
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    if "BotPDFUnicode" in pdfmetrics.getRegisteredFontNames():
        return "BotPDFUnicode"

    candidates = [
        "/usr/share/fonts/truetype/noto/NotoSansMyanmar-Regular.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansMyanmar-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/Library/Fonts/Arial Unicode.ttf",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    ]
    for font_path in candidates:
        if os.path.exists(font_path):
            pdfmetrics.registerFont(TTFont("BotPDFUnicode", font_path))
            return "BotPDFUnicode"
    return "Helvetica"


def build_pdf_file(title: str, text: str, output_path: str) -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    font_name = get_pdf_font_name()
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "BotTitle",
        parent=styles["Title"],
        fontName=font_name,
        fontSize=18,
        leading=22,
        spaceAfter=10,
    )
    body_style = ParagraphStyle(
        "BotBody",
        parent=styles["BodyText"],
        fontName=font_name,
        fontSize=11,
        leading=16,
        spaceAfter=8,
    )

    story: list[Any] = [Paragraph(html.escape(title), title_style), Spacer(1, 6)]
    paragraphs = [part.strip() for part in normalize_plain_text(text).split("\n\n") if part.strip()]
    for paragraph in paragraphs:
        story.append(Paragraph(html.escape(paragraph).replace("\n", "<br/>"), body_style))
        story.append(Spacer(1, 4))

    document = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=title,
    )
    document.build(story)


def extract_first_url(text: str) -> str | None:
    match = URL_PATTERN.search(text)
    if not match:
        return None
    return match.group(0).rstrip(".,)]}>\"'")


def validate_public_url(raw_url: str) -> str:
    candidate = raw_url.strip()
    if "://" not in candidate:
        candidate = f"https://{candidate}"

    parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"}:
        raise RuntimeError("Only http and https links are supported.")
    if not parsed.hostname:
        raise RuntimeError("Invalid link.")

    try:
        address_infos = socket.getaddrinfo(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise RuntimeError("Could not resolve that link.") from exc

    for _, _, _, _, sockaddr in address_infos:
        ip = ipaddress.ip_address(sockaddr[0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
        ):
            raise RuntimeError("Only public links are allowed.")

    return parsed.geturl()


def extract_page_text(html_content: str) -> tuple[str, str]:
    title_match = re.search(r"(?is)<title[^>]*>(.*?)</title>", html_content)
    meta_description_match = re.search(
        r'(?is)<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']',
        html_content,
    )

    cleaned = re.sub(r"(?is)<(script|style|noscript).*?>.*?</\1>", " ", html_content)
    cleaned = re.sub(r"(?i)<br\s*/?>", "\n", cleaned)
    cleaned = re.sub(r"(?i)</p\s*>", "\n\n", cleaned)
    cleaned = re.sub(r"(?i)</div\s*>", "\n", cleaned)
    cleaned = TAG_PATTERN.sub(" ", cleaned)
    cleaned = html.unescape(cleaned)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r" ?\n ?", "\n", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()

    title = html.unescape(title_match.group(1)).strip() if title_match else ""
    description = (
        html.unescape(meta_description_match.group(1)).strip()
        if meta_description_match
        else ""
    )

    if description and description not in cleaned:
        cleaned = f"{description}\n\n{cleaned}".strip()

    return title, cleaned


def fetch_link_context(url: str) -> str:
    response = session.get(
        url,
        headers={"User-Agent": "cookai-link-analyzer/1.0"},
        timeout=20,
        allow_redirects=True,
    )
    response.raise_for_status()

    content_type = response.headers.get("Content-Type", "").lower()
    final_url = response.url

    if "text/html" in content_type:
        title, body = extract_page_text(response.text)
    elif "text/plain" in content_type or CONTENT_TYPE_JSON in content_type:
        title = ""
        body = response.text.strip()
    else:
        raise RuntimeError(f"Unsupported content type: {content_type or 'unknown'}")

    body = body[:6000].strip()
    if not body:
        raise RuntimeError("The link did not return enough readable text to analyze.")

    parts = [f"URL: {final_url}"]
    if title:
        parts.append(f"Title: {title}")
    parts.append("Page content:")
    parts.append(body)
    return "\n\n".join(parts)


def build_messages(
    user_id: int,
    user_message: str,
    system_prompt: str,
    include_history: bool = True,
) -> list[dict[str, str]]:
    system_prompt = build_system_prompt(user_id, system_prompt)

    messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]

    if include_history:
        summary = conversation_summaries.get(user_id, "").strip()
        if summary:
            messages.append(
                {
                    "role": "system",
                    "content": f"Conversation memory:\n{summary}",
                }
            )

        history: list[dict[str, str]] = []
        consumed_chars = 0
        for item in reversed(conversation_history[user_id]):
            content = str(item.get("content", ""))
            item_cost = len(content)
            if history and consumed_chars + item_cost > RECENT_CONTEXT_CHAR_LIMIT:
                break
            history.append(item)
            consumed_chars += item_cost
        history.reverse()
        messages.extend(history)

    messages.append({"role": "user", "content": user_message})
    return messages


def build_system_prompt(user_id: int, system_prompt: str) -> str:
    persona = persona_preferences.get(user_id, "").strip()
    if persona and persona in PERSONA_PROMPTS:
        system_prompt = f"{system_prompt}\n\n{PERSONA_PROMPTS[persona]}"

    tone_sample = tone_preferences.get(user_id, "").strip()
    if tone_sample:
        system_prompt = (
            f"{system_prompt}\n\n"
            "Match the user's preferred tone and writing style in any language you use. "
            "Keep the reply natural and do not copy the sample word-for-word unless needed. "
            f"Tone sample:\n{clip_text(tone_sample, 600)}"
        )
    return system_prompt


def request_chat_completion(
    user_id: int,
    user_message: str,
    system_prompt: str = BOT_SYSTEM_PROMPT,
    remember: bool = True,
    include_history: bool = True,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> str:
    messages = build_messages(
        user_id,
        clip_text(user_message, SOURCE_TEXT_CHAR_LIMIT),
        system_prompt,
        include_history=include_history,
    )
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": CONTENT_TYPE_JSON,
        "HTTP-Referer": "https://localhost",
        "X-Title": "cookai",
    }
    reply_parts: list[str] = []

    for round_index in range(CONTINUATION_MAX_ROUNDS + 1):
        payload = {
            "model": OPENROUTER_MODEL,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": max_tokens,
        }
        response = session.post(
            OPENROUTER_API_URL,
            headers=headers,
            json=payload,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()

        try:
            choice = data["choices"][0]
            content = choice["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"Unexpected model response: {data}") from exc

        segment = normalize_plain_text(extract_text_content(content))
        if not segment:
            raise RuntimeError("Model returned an empty response.")
        reply_parts.append(segment)

        if choice.get("finish_reason") != "length" or round_index >= CONTINUATION_MAX_ROUNDS:
            break

        messages.append({"role": "assistant", "content": segment})
        messages.append(
            {
                "role": "user",
                "content": (
                    "Continue exactly from where you stopped. "
                    "Do not repeat earlier text. "
                    "Finish the same reply naturally in the same language and tone."
                ),
            }
        )

    assistant_reply = normalize_plain_text("".join(reply_parts))

    if remember:
        remember_exchange(user_id, user_message, assistant_reply)
    return assistant_reply


def parse_command(text: str) -> tuple[str, str]:
    command, separator, remainder = text.partition(" ")
    return command, remainder.strip() if separator else ""


def set_tone_preference(user_id: int, sample_text: str) -> None:
    tone_preferences[user_id] = normalize_plain_text(sample_text)[:1500]
    save_persistent_state()


def clear_tone_preference(user_id: int) -> None:
    tone_preferences.pop(user_id, None)
    save_persistent_state()


def set_persona_preference(user_id: int, persona: str) -> None:
    persona_preferences[user_id] = persona
    save_persistent_state()


def clear_persona_preference(user_id: int) -> None:
    persona_preferences.pop(user_id, None)
    save_persistent_state()


def get_referenced_text(message: dict[str, Any], command_argument: str, user_id: int) -> str | None:
    replied_message = message.get("reply_to_message") or {}
    replied_text = (
        replied_message.get("text")
        or replied_message.get("caption")
        or ""
    ).strip()
    if replied_text:
        return replied_text
    if command_argument.strip():
        return command_argument.strip()
    return extract_last_assistant_reply(user_id)


def transform_text(
    user_id: int,
    command_name: str,
    source_text: str,
    instruction: str,
    max_tokens: int = TRANSFORM_MAX_TOKENS,
) -> str:
    system_prompt = with_base_rules(
        "You transform text exactly as requested. "
        "Return only the transformed result. "
        "Preserve the source language unless the instruction asks for another language."
    )
    answer = request_chat_completion(
        user_id,
        f"Instruction: {instruction}\n\nSource text:\n{clip_text(source_text, SOURCE_TEXT_CHAR_LIMIT)}",
        system_prompt=system_prompt,
        remember=False,
        include_history=False,
        max_tokens=max_tokens,
    )
    remember_exchange(user_id, f"{command_name}\n\n{source_text}", answer)
    return answer


def should_generate_pdf_content(text: str) -> bool:
    stripped = text.strip()
    return "\n" not in stripped and len(stripped) < 240


def get_pdf_source_text(message: dict[str, Any], command_argument: str, user_id: int) -> str | None:
    replied_text = get_referenced_text(message, command_argument, user_id)
    if replied_text:
        return replied_text
    return None


def create_pdf_document(user_id: int, message: dict[str, Any], command_argument: str) -> tuple[str, str]:
    source_text = get_pdf_source_text(message, command_argument, user_id)
    if not source_text:
        raise RuntimeError("Reply to a message with /pdf or use /pdf <text>.")

    document_text = source_text
    if command_argument.strip() and not (message.get("reply_to_message") or {}):
        if should_generate_pdf_content(command_argument):
            document_text = request_chat_completion(
                user_id,
                f"Create a clean PDF-ready document about:\n{command_argument}",
                system_prompt=PDF_SYSTEM_PROMPT,
                remember=False,
                include_history=False,
                max_tokens=PDF_MAX_TOKENS,
            )
        else:
            document_text = command_argument.strip()

    title = clip_text(document_text.splitlines()[0] if document_text.strip() else "Document", 80)
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as temp_file:
        pdf_path = temp_file.name

    try:
        build_pdf_file(title or "Document", document_text, pdf_path)
        return pdf_path, title or "Document"
    except Exception:
        try:
            os.remove(pdf_path)
        except OSError:
            pass
        raise


def run_structured_command(
    user_id: int,
    command_name: str,
    source_text: str,
    instruction: str,
    max_tokens: int = COMMAND_PACK_MAX_TOKENS,
) -> str:
    answer = request_chat_completion(
        user_id,
        f"Task: {instruction}\n\nInput:\n{clip_text(source_text, SOURCE_TEXT_CHAR_LIMIT)}",
        system_prompt=GENERIC_COMMAND_SYSTEM_PROMPT,
        remember=False,
        include_history=False,
        max_tokens=max_tokens,
    )
    remember_exchange(user_id, f"{command_name}\n\n{source_text}", answer)
    return answer


def create_qr_code_image(data: str) -> tuple[str, str]:
    import qrcode

    clean_data = data.strip()
    if not clean_data:
        raise RuntimeError("Use /qr <text or link>.")

    qr = qrcode.QRCode(border=2, box_size=10)
    qr.add_data(clean_data)
    qr.make(fit=True)
    # qrcode returns a wrapper object; get the concrete PIL image for type-safe saving.
    image = qr.make_image(fill_color="black", back_color="white").get_image()

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp_file:
        image_path = temp_file.name

    try:
        image.save(image_path)
        return image_path, clean_data
    except Exception:
        try:
            os.remove(image_path)
        except OSError:
            pass
        raise


def create_web_pdf_document(user_id: int, url: str) -> tuple[str, str]:
    validated_url = validate_public_url(url)
    link_context = fetch_link_context(validated_url)
    document_text = request_chat_completion(
        user_id,
        (
            "Create a clean PDF-ready web page brief from this page. "
            "Start with a clear title, then provide a concise summary and key points.\n\n"
            f"{link_context}"
        ),
        system_prompt=PDF_SYSTEM_PROMPT,
        remember=False,
        include_history=False,
        max_tokens=PDF_MAX_TOKENS,
    )

    title = clip_text(
        document_text.splitlines()[0] if document_text.strip() else WEB_PAGE_SUMMARY_TITLE,
        80,
    )
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as temp_file:
        pdf_path = temp_file.name

    try:
        build_pdf_file(title or WEB_PAGE_SUMMARY_TITLE, document_text, pdf_path)
        remember_exchange(user_id, f"/webpdf {validated_url}", document_text)
        return pdf_path, title or WEB_PAGE_SUMMARY_TITLE
    except Exception:
        try:
            os.remove(pdf_path)
        except OSError:
            pass
        raise


def has_voice_input_attachment(message: dict[str, Any]) -> bool:
    return bool(message.get("voice") or message.get("audio"))


def request_image_analysis(
    user_id: int,
    user_prompt: str,
    image_data_url: str,
    system_prompt: str = IMAGE_ANALYSIS_SYSTEM_PROMPT,
    max_tokens: int = ATTACHMENT_ANALYSIS_MAX_TOKENS,
) -> str:
    messages = [
        {"role": "system", "content": build_system_prompt(user_id, system_prompt)},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": clip_text(user_prompt, 1200)},
                {"type": "image_url", "image_url": {"url": image_data_url}},
            ],
        },
    ]
    payload = {
        "model": OPENROUTER_MODEL,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": max_tokens,
    }
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": CONTENT_TYPE_JSON,
        "HTTP-Referer": "https://localhost",
        "X-Title": "cookai",
    }

    response = session.post(
        OPENROUTER_API_URL,
        headers=headers,
        json=payload,
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    data = response.json()

    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"Unexpected model response: {data}") from exc

    assistant_reply = normalize_plain_text(extract_text_content(content))
    if not assistant_reply:
        raise RuntimeError("Model returned an empty response.")
    return assistant_reply


def analyze_photo_bytes(user_id: int, prompt: str, file_bytes: bytes, mime_type: str = MIME_TYPE_JPEG) -> str:
    data_url = build_data_url(mime_type, file_bytes)
    answer = request_image_analysis(user_id, prompt, data_url)
    remember_exchange(user_id, prompt, answer)
    return answer


def analyze_document_bytes(
    user_id: int,
    prompt: str,
    file_name: str,
    mime_type: str,
    file_bytes: bytes,
) -> str:
    if is_image_type(file_name, mime_type):
        answer = analyze_photo_bytes(
            user_id,
            prompt,
            file_bytes,
            mime_type or guess_mime_type(file_name, MIME_TYPE_JPEG),
        )
        remember_exchange(user_id, f"{prompt}\n\nFile: {file_name}", answer)
        return answer

    file_text = extract_text_from_file_bytes(file_name, mime_type, file_bytes)
    file_text = clip_text(file_text, FILE_TEXT_CHAR_LIMIT)
    answer = request_chat_completion(
        user_id,
        f"{prompt}\n\nFile name: {file_name}\nFile contents:\n{file_text}",
        system_prompt=FILE_ANALYSIS_SYSTEM_PROMPT,
        remember=False,
        include_history=False,
        max_tokens=ATTACHMENT_ANALYSIS_MAX_TOKENS,
    )
    remember_exchange(user_id, f"{prompt}\n\nFile: {file_name}", answer)
    return answer


def has_analyzable_attachment(message: dict[str, Any]) -> bool:
    return bool(message.get("photo") or message.get("document"))


def get_attachment_prompt(text: str | None, default_prompt: str) -> str:
    prompt = (text or "").strip()
    if not prompt:
        return default_prompt
    return prompt


def analyze_message_attachment(user_id: int, message: dict[str, Any], prompt: str) -> str:
    photos = message.get("photo") or []
    if photos:
        largest = photos[-1]
        file_id = largest.get("file_id")
        if not file_id:
            raise RuntimeError("Photo is missing a file ID.")
        file_bytes, file_path = get_telegram_file_bytes(str(file_id))
        mime_type = guess_mime_type(file_path, MIME_TYPE_JPEG)
        return analyze_photo_bytes(user_id, prompt, file_bytes, mime_type)

    document = message.get("document") or {}
    file_id = document.get("file_id")
    if not file_id:
        raise RuntimeError("Document is missing a file ID.")
    file_name = str(document.get("file_name") or "document")
    mime_type = str(document.get("mime_type") or guess_mime_type(file_name))
    file_bytes, _ = get_telegram_file_bytes(str(file_id))
    return analyze_document_bytes(user_id, prompt, file_name, mime_type, file_bytes)


def parse_translate_argument(message: dict[str, Any], argument: str) -> tuple[str, str]:
    replied_text = (
        (message.get("reply_to_message") or {}).get("text")
        or (message.get("reply_to_message") or {}).get("caption")
        or ""
    ).strip()

    if "|" in argument:
        target_language, source_text = argument.split("|", 1)
        target_language = target_language.strip()
        source_text = source_text.strip()
        if target_language and source_text:
            return target_language, source_text

    if replied_text and argument.strip():
        return argument.strip(), replied_text

    raise RuntimeError("Use /translate <language> | <text> or reply with /translate <language>")


def parse_human_datetime(raw_text: str) -> datetime:
    import dateparser

    settings = {
        "TIMEZONE": BOT_TIMEZONE,
        "TO_TIMEZONE": BOT_TIMEZONE,
        "RETURN_AS_TIMEZONE_AWARE": True,
        "PREFER_DATES_FROM": "future",
        "RELATIVE_BASE": now_local(),
    }
    # dateparser's runtime accepts this dict, but its published stubs are narrower.
    parsed = dateparser.parse(raw_text, settings=cast(Any, settings))
    if parsed is None:
        raise RuntimeError("Could not understand that time. Try: tomorrow 9am | call mom")

    if parsed <= now_local() and SIMPLE_TIME_PATTERN.match(raw_text.strip()):
        parsed = parsed + timedelta(days=1)
    return parsed.astimezone(ZoneInfo(BOT_TIMEZONE))


def parse_reminder_input(raw_text: str) -> tuple[str, str]:
    text = raw_text.strip()
    if "|" in text:
        when_text, reminder_text = text.split("|", 1)
        when_text = when_text.strip()
        reminder_text = reminder_text.strip()
        if not when_text or not reminder_text:
            raise RuntimeError("Use /remind <when> | <text>")
        return when_text, reminder_text

    if " to " in text:
        when_text, reminder_text = text.split(" to ", 1)
        when_text = when_text.strip()
        reminder_text = reminder_text.strip()
        if when_text and reminder_text:
            return when_text, reminder_text

    raise RuntimeError("Use /remind <when> | <text>")


def create_reminder(user_id: int, chat_id: int, raw_text: str) -> dict[str, Any]:
    when_text, reminder_text = parse_reminder_input(raw_text)
    due_at = parse_human_datetime(when_text)
    reminder = {
        "id": new_item_id(),
        "user_id": user_id,
        "chat_id": chat_id,
        "text": reminder_text,
        "due_at": due_at.isoformat(),
        "sent": False,
        "created_at": now_local().isoformat(),
    }
    reminder_store.append(reminder)
    save_persistent_state()
    return reminder


def list_reminders_for_user(user_id: int) -> list[dict[str, Any]]:
    pending = [item for item in reminder_store if item.get("user_id") == user_id and not item.get("sent")]
    pending.sort(key=lambda item: item.get("due_at", ""))
    return pending


def delete_reminder(user_id: int, reminder_id: str) -> bool:
    original_count = len(reminder_store)
    reminder_store[:] = [
        item
        for item in reminder_store
        if not (item.get("user_id") == user_id and str(item.get("id")) == reminder_id)
    ]
    changed = len(reminder_store) != original_count
    if changed:
        save_persistent_state()
    return changed


def add_todo(user_id: int, text: str) -> dict[str, Any]:
    item = {
        "id": new_item_id(),
        "text": normalize_plain_text(text),
        "done": False,
        "created_at": now_local().isoformat(),
    }
    todo_store.setdefault(user_id, []).append(item)
    save_persistent_state()
    return item


def list_todos(user_id: int) -> list[dict[str, Any]]:
    return todo_store.get(user_id, [])


def update_todo(user_id: int, todo_id: str, done: bool | None = None, delete: bool = False) -> bool:
    items = todo_store.get(user_id, [])
    updated = False
    kept: list[dict[str, Any]] = []
    for item in items:
        if str(item.get("id")) != todo_id:
            kept.append(item)
            continue
        if delete:
            updated = True
            continue
        if done is not None:
            item["done"] = done
            updated = True
        kept.append(item)
    if updated:
        todo_store[user_id] = kept
        save_persistent_state()
    return updated


def add_idea(user_id: int, text: str) -> dict[str, Any]:
    item = {
        "id": new_item_id(),
        "text": normalize_plain_text(text),
        "created_at": now_local().isoformat(),
    }
    idea_store.setdefault(user_id, []).append(item)
    save_persistent_state()
    return item


def list_ideas(user_id: int) -> list[dict[str, Any]]:
    return idea_store.get(user_id, [])


def add_note(user_id: int, text: str, source: str = "text") -> dict[str, Any]:
    item = {
        "id": new_item_id(),
        "text": normalize_plain_text(text),
        "source": source,
        "created_at": now_local().isoformat(),
    }
    note_store.setdefault(user_id, []).append(item)
    save_persistent_state()
    return item


def list_notes(user_id: int) -> list[dict[str, Any]]:
    return note_store.get(user_id, [])


def delete_note(user_id: int, note_id: str) -> bool:
    items = note_store.get(user_id, [])
    kept = [item for item in items if str(item.get("id")) != note_id]
    if len(kept) == len(items):
        return False
    note_store[user_id] = kept
    save_persistent_state()
    return True


def process_due_reminders() -> None:
    current_time = now_local()
    changed = False
    for reminder in reminder_store:
        if reminder.get("sent"):
            continue
        try:
            due_at = datetime.fromisoformat(str(reminder.get("due_at"))).astimezone(ZoneInfo(BOT_TIMEZONE))
        except Exception:
            logger.warning("Skipping malformed reminder %s", reminder)
            reminder["sent"] = True
            changed = True
            continue

        if due_at > current_time:
            continue

        try:
            send_message(
                int(reminder["chat_id"]),
                f"Reminder\n{reminder.get('text', '').strip()}",
            )
            reminder["sent"] = True
            changed = True
        except Exception:
            logger.exception("Failed to send reminder %s", reminder.get("id"))

    if changed:
        save_persistent_state()


def extract_last_assistant_reply(user_id: int) -> str | None:
    for message in reversed(conversation_history[user_id]):
        if message.get("role") == "assistant":
            content = str(message.get("content", "")).strip()
            if content:
                return content
    return None


def get_note_source_text(message: dict[str, Any], command_argument: str) -> tuple[str, str]:
    replied_message = message.get("reply_to_message") or {}
    replied_text = (
        replied_message.get("text")
        or replied_message.get("caption")
        or ""
    ).strip()
    if replied_text:
        return replied_text, "text"

    if command_argument.strip():
        return command_argument.strip(), "text"

    return "", ""


def get_system_prompt_for_message(user_id: int, text: str) -> str:
    if conversation_modes[user_id] == "presentation":
        return PRESENTATION_SYSTEM_PROMPT
    if has_social_content_keyword(text):
        return SOCIAL_CONTENT_SYSTEM_PROMPT
    if response_languages[user_id] == "burmese" or contains_myanmar_text(text):
        return BURMESE_SYSTEM_PROMPT
    return BOT_SYSTEM_PROMPT


def get_max_tokens_for_message(text: str) -> int:
    if has_social_content_keyword(text):
        return SOCIAL_CONTENT_MAX_TOKENS
    if contains_myanmar_text(text):
        return BURMESE_MAX_TOKENS
    return DEFAULT_MAX_TOKENS


def analyze_link(user_id: int, url: str) -> str:
    validated_url = validate_public_url(url)
    link_context = fetch_link_context(validated_url)
    answer = request_chat_completion(
        user_id,
        f"Analyze this link for the user.\n\n{link_context}",
        system_prompt=LINK_ANALYSIS_SYSTEM_PROMPT,
        remember=False,
        include_history=False,
        max_tokens=LINK_ANALYSIS_MAX_TOKENS,
    )
    remember_exchange(user_id, f"/link {validated_url}", answer)
    return answer


def handle_text_message(message: dict[str, Any]) -> None:  # NOSONAR
    chat = message.get("chat", {})
    from_user = message.get("from", {})
    chat_id = chat.get("id")
    user_id = from_user.get("id")
    text = (message.get("text") or message.get("caption") or "").strip()
    message_id = message.get("message_id")

    if not isinstance(chat_id, int) or not isinstance(user_id, int):
        logger.warning("Skipping malformed Telegram message: %s", message)
        return

    refresh_auth_related_state()
    current_has_attachment = has_analyzable_attachment(message)
    current_has_voice_input = has_voice_input_attachment(message)
    replied_message = message.get("reply_to_message") or {}
    reply_has_attachment = has_analyzable_attachment(replied_message)
    command, argument = parse_command(text)
    request_preview = get_message_request_preview(message, text)

    update_known_user_profile(user_id, chat_id, from_user, request_preview)

    if not is_admin_user(user_id):
        append_activity_event(user_id, request_preview)
        notify_admins(build_admin_request_notice(user_id, request_preview))

    if not is_authorized_user(user_id):
        if text == "/start":
            send_message(
                chat_id,
                (
                    "This bot uses access login.\n"
                    "Ask the admin for a one-time hash.\n"
                    "Then use /login <hash>.\n"
                    "Example:\n"
                    "/login A1B2C3D4E5"
                ),
                reply_to_message_id=message_id,
            )
            return

        if text == "/help":
            send_message(
                chat_id,
                (
                    "Access commands:\n"
                    "/start\n"
                    "/help\n"
                    "/login <hash>\n\n"
                    "Ask the admin for a one-time login hash."
                ),
                reply_to_message_id=message_id,
            )
            return

        if command == "/login":
            success, login_message = consume_login_hash(user_id, argument)
            if success:
                register_bot_commands()
                notify_admins(
                    (
                        "User logged in\n"
                        f"{format_profile_summary(user_id)}"
                    )
                )
            send_message(
                chat_id,
                login_message,
                reply_to_message_id=message_id,
                reply_markup=get_menu_keyboard("main") if success else None,
            )
            return

        logger.warning("Blocked unauthorized user_id=%s", user_id)
        send_message(
            chat_id,
            "Access restricted. Ask the admin for a login hash and use /login <hash>.",
            reply_to_message_id=message_id,
        )
        return

    if not text and not current_has_attachment and not current_has_voice_input:
        send_message(chat_id, "Send a text message.", reply_to_message_id=message_id)
        return

    if current_has_voice_input:
        send_message(
            chat_id,
            "Voice messages are disabled. Send text, a photo, or a supported file instead.",
            reply_to_message_id=message_id,
        )
        return

    if text == "/start":
        send_message(
            chat_id,
            (
                "Bot is online. Send a message to chat.\n"
                "Use /login <hash> only when setting up a new user.\n"
                "Use /presentation to switch into slide-making mode.\n"
                "Use /burmese to reply in Burmese.\n"
                "Use /persona <mode> for a reusable role.\n"
                "Use /tone <text> to set your writing style.\n"
                f"Use {CMD_NOTE} to save a text note.\n"
                "Send a photo or file to analyze it.\n"
                "Use /analyze to analyze a replied photo or file.\n"
                "Use /pdf to export text as a PDF file.\n"
                "Use /webpdf <url> to turn a web page into PDF.\n"
                "Use /caption, /quiz, /plan, or /qr for extra tools.\n"
                f"Use {CMD_REWRITE} or {CMD_SUMMARIZE} on a reply.\n"
                "Use /remind tomorrow 9am | call mom.\n"
                "Use /link <url> to analyze a public link.\n"
                "Use /reset to clear memory.\n"
                "Use the buttons below for quick access."
            ),
            reply_to_message_id=message_id,
            reply_markup=get_menu_keyboard("main"),
        )
        return

    if text == "/help":
        common_help = (
            "Commands:\n"
            "/start\n"
            "/help\n"
            "/reset\n"
            "/english\n"
            "/burmese [message]\n"
            "/persona <mode>\n"
            "/persona off\n"
            "/tone <text>\n"
            "/tone off\n"
            f"{CMD_NOTE}\n"
            f"{CMD_NOTES}\n"
            "/analyze\n"
            "/analyze <question>\n"
            "/pdf\n"
            "/pdf <text or topic>\n"
            "/webpdf <url>\n"
            "/caption\n"
            "/hook\n"
            "/carousel\n"
            "/script\n"
            "/cta\n"
            "/hashtags\n"
            "/quiz\n"
            "/flashcards\n"
            "/explain\n"
            "/exam\n"
            "/plan\n"
            "/pitch\n"
            "/pricing\n"
            "/strategy\n"
            "/swot\n"
            "/businessmodel\n"
            "/qr <text or link>\n"
            f"{CMD_REWRITE}\n"
            "/shorter\n"
            "/formal\n"
            "/friendly\n"
            "/translate <language> | <text>\n"
            "/fixgrammar\n"
            f"{CMD_SUMMARIZE}\n"
            "/remind <when> | <text>\n"
            "/reminders\n"
            "/todo add <text>\n"
            "/todo list\n"
            "/idea <text>\n"
            "/ideas\n"
            "/link <url>\n"
            "/presentation [topic or brief]"
        )
        send_message(
            chat_id,
            common_help,
            reply_to_message_id=message_id,
            reply_markup=get_menu_keyboard("main"),
        )
        send_message(
            chat_id,
            "Use /menu for the main button panel or /menu more for extra tools.",
            reply_to_message_id=message_id,
        )
        return

    if command == "/login":
        send_message(
            chat_id,
            "You already have access.",
            reply_to_message_id=message_id,
        )
        return

    if command in {"/voice", "/transcribe"}:
        send_message(
            chat_id,
            "Voice features are disabled. Send text, a photo, or a supported file instead.",
            reply_to_message_id=message_id,
        )
        return

    if command == CMD_NOTE:
        try:
            source_text, note_source = get_note_source_text(message, argument)
            if not source_text:
                send_message(
                    chat_id,
                    f"Use {CMD_NOTE} <text> or reply to a text message with {CMD_NOTE}.",
                    reply_to_message_id=message_id,
                )
                return
            item = add_note(user_id, source_text, source=note_source)
            send_message(
                chat_id,
                f"Note saved.\n{item['id']} - {clip_text(item['text'], 300)}",
                reply_to_message_id=message_id,
            )
        except requests.HTTPError as exc:
            logger.exception("HTTP error while creating note")
            error_body = exc.response.text[:500] if exc.response is not None else str(exc)
            send_message(chat_id, f"Note error:\n{error_body}", reply_to_message_id=message_id)
        except Exception as exc:
            logger.exception("Unexpected error while creating note")
            send_message(chat_id, f"Error: {exc}", reply_to_message_id=message_id)
        return

    if command == CMD_NOTES:
        lowered_argument = argument.lower()
        if lowered_argument.startswith("delete "):
            note_id = argument.split(" ", 1)[1].strip()
            if delete_note(user_id, note_id):
                send_message(chat_id, "Note deleted.", reply_to_message_id=message_id)
            else:
                send_message(chat_id, "Note not found.", reply_to_message_id=message_id)
            return

        items = list_notes(user_id)
        if not items:
            send_message(chat_id, "No saved notes.", reply_to_message_id=message_id)
            return
        lines = [
            f"{item['id']} - [{item.get('source', 'text')}] {clip_text(str(item.get('text', '')), 180)}"
            for item in items[-20:]
        ]
        send_message(
            chat_id,
            "Notes\n" + "\n".join(lines) + f"\n\nUse {CMD_NOTES} delete <id> to remove one.",
            reply_to_message_id=message_id,
        )
        return

    if command in {"/hash", "/users", "/user", "/approve", "/block", "/unblock", "/replyuser"}:
        send_message(
            chat_id,
            "Use the CookAI admin dashboard bot for admin controls.",
            reply_to_message_id=message_id,
        )
        return

    if text == "/menu":
        send_message(
            chat_id,
            "Main menu is ready below.",
            reply_to_message_id=message_id,
            reply_markup=get_menu_keyboard("main"),
        )
        return

    if text == "/menu more":
        send_message(
            chat_id,
            "More tools are shown below.",
            reply_to_message_id=message_id,
            reply_markup=get_menu_keyboard("more"),
        )
        return

    if text == CMD_HIDEBUTTONS:
        send_message(
            chat_id,
            "Buttons hidden. Use /menu anytime to show them again.",
            reply_to_message_id=message_id,
            reply_markup=REMOVE_REPLY_KEYBOARD,
        )
        return

    if text == "/reset":
        conversation_history[user_id].clear()
        conversation_modes[user_id] = "chat"
        response_languages[user_id] = "default"
        save_persistent_state()
        clear_tone_preference(user_id)
        clear_persona_preference(user_id)
        send_message(
            chat_id,
            "Conversation memory cleared. Default chat mode restored. Saved tone and persona cleared.",
            reply_to_message_id=message_id,
            reply_markup=get_menu_keyboard("main"),
        )
        return

    if text == "/english":
        response_languages[user_id] = "default"
        save_persistent_state()
        send_message(
            chat_id,
            "English mode enabled.",
            reply_to_message_id=message_id,
        )
        return

    if command == "/burmese":
        response_languages[user_id] = "burmese"
        save_persistent_state()
        if not argument:
            send_message(
                chat_id,
                "Burmese mode enabled. Send your message.",
                reply_to_message_id=message_id,
            )
            return

        try:
            send_chat_action(chat_id, "typing")
            answer = request_chat_completion(
                user_id,
                argument,
                system_prompt=SOCIAL_CONTENT_SYSTEM_PROMPT if has_social_content_keyword(argument) else BURMESE_SYSTEM_PROMPT,
                max_tokens=SOCIAL_CONTENT_MAX_TOKENS if has_social_content_keyword(argument) else BURMESE_MAX_TOKENS,
            )
            send_message(chat_id, answer, reply_to_message_id=message_id)
        except requests.HTTPError as exc:
            logger.exception("HTTP error while processing Burmese request")
            error_body = exc.response.text[:500] if exc.response is not None else str(exc)
            send_message(chat_id, f"API error:\n{error_body}", reply_to_message_id=message_id)
        except Exception as exc:
            logger.exception("Unexpected bot error during Burmese request")
            send_message(chat_id, f"Error: {exc}", reply_to_message_id=message_id)
        return

    if command == "/persona":
        selected = argument.strip().lower()
        if not selected:
            active = persona_preferences.get(user_id)
            modes = ", ".join(PERSONA_PROMPTS.keys())
            if active:
                send_message(
                    chat_id,
                    f"Current persona: {active}\nAvailable: {modes}\nUse /persona off to clear it.",
                    reply_to_message_id=message_id,
                )
            else:
                send_message(
                    chat_id,
                    f"Available personas: {modes}\nExample: /persona coder",
                    reply_to_message_id=message_id,
                )
            return

        if selected in {"off", "clear", "reset"}:
            clear_persona_preference(user_id)
            send_message(
                chat_id,
                "Persona cleared.",
                reply_to_message_id=message_id,
            )
            return

        if selected not in PERSONA_PROMPTS:
            send_message(
                chat_id,
                f"Unknown persona.\nAvailable: {', '.join(PERSONA_PROMPTS.keys())}",
                reply_to_message_id=message_id,
            )
            return

        set_persona_preference(user_id, selected)
        send_message(
            chat_id,
            f"Persona set to {selected}.",
            reply_to_message_id=message_id,
        )
        return

    if command == "/tone":
        if not argument:
            current_tone = tone_preferences.get(user_id)
            if current_tone:
                send_message(
                    chat_id,
                    f"Tone memory is active.\nCurrent sample:\n{current_tone}",
                    reply_to_message_id=message_id,
                )
            else:
                send_message(
                    chat_id,
                    "Set a tone sample like:\n/tone Write warm, short, confident replies.\nUse /tone off to clear it.",
                    reply_to_message_id=message_id,
                )
            return

        if argument.lower() in {"off", "clear", "reset"}:
            clear_tone_preference(user_id)
            send_message(
                chat_id,
                "Tone memory cleared.",
                reply_to_message_id=message_id,
            )
            return

        set_tone_preference(user_id, argument)
        send_message(
            chat_id,
            "Tone memory saved. Future replies will follow this style in English and Burmese.",
            reply_to_message_id=message_id,
        )
        return

    if command == "/analyze":
        target_message = replied_message if reply_has_attachment else message
        if not has_analyzable_attachment(target_message):
            send_message(
                chat_id,
                "Reply to a photo or file with /analyze, or send a photo/file with an optional caption.",
                reply_to_message_id=message_id,
            )
            return

        try:
            send_chat_action(chat_id, "typing")
            answer = analyze_message_attachment(
                user_id,
                target_message,
                get_attachment_prompt(argument, "Analyze this attachment and explain the important details."),
            )
            send_message(chat_id, answer, reply_to_message_id=message_id)
        except requests.HTTPError as exc:
            logger.exception("HTTP error while analyzing attachment")
            error_body = exc.response.text[:500] if exc.response is not None else str(exc)
            send_message(chat_id, f"Attachment analysis error:\n{error_body}", reply_to_message_id=message_id)
        except Exception as exc:
            logger.exception("Unexpected bot error during attachment analysis")
            send_message(chat_id, f"Error: {exc}", reply_to_message_id=message_id)
        return

    if command == "/pdf":
        pdf_path: str | None = None
        try:
            send_chat_action(chat_id, "upload_document")
            pdf_path, title = create_pdf_document(user_id, message, argument)
            send_document(
                chat_id,
                pdf_path,
                file_name=f"{re.sub(r'[^A-Za-z0-9_-]+', '-', title).strip('-') or 'document'}.pdf",
                caption="PDF ready.",
                reply_to_message_id=message_id,
            )
        except requests.HTTPError as exc:
            logger.exception("HTTP error while creating PDF")
            error_body = exc.response.text[:500] if exc.response is not None else str(exc)
            send_message(chat_id, f"PDF error:\n{error_body}", reply_to_message_id=message_id)
        except Exception as exc:
            logger.exception("Unexpected bot error during PDF creation")
            send_message(chat_id, f"Error: {exc}", reply_to_message_id=message_id)
        finally:
            if pdf_path:
                try:
                    os.remove(pdf_path)
                except OSError:
                    logger.warning("Could not delete temp PDF file %s", pdf_path)
        return

    if command == "/webpdf":
        pdf_path: str | None = None
        try:
            if not argument:
                send_message(chat_id, "Use /webpdf <url>.", reply_to_message_id=message_id)
                return
            send_chat_action(chat_id, "upload_document")
            pdf_path, title = create_web_pdf_document(user_id, argument)
            send_document(
                chat_id,
                pdf_path,
                file_name=f"{re.sub(r'[^A-Za-z0-9_-]+', '-', title).strip('-') or 'web-page'}.pdf",
                caption="Web PDF ready.",
                reply_to_message_id=message_id,
            )
        except requests.HTTPError as exc:
            logger.exception("HTTP error while creating web PDF")
            error_body = exc.response.text[:500] if exc.response is not None else str(exc)
            send_message(chat_id, f"Web PDF error:\n{error_body}", reply_to_message_id=message_id)
        except Exception as exc:
            logger.exception("Unexpected bot error during web PDF creation")
            send_message(chat_id, f"Error: {exc}", reply_to_message_id=message_id)
        finally:
            if pdf_path:
                try:
                    os.remove(pdf_path)
                except OSError:
                    logger.warning("Could not delete temp web PDF file %s", pdf_path)
        return

    command_pack_map = {
        "/caption": "Write a strong social media caption.",
        "/hook": "Write 10 strong social media hooks.",
        "/carousel": "Create a social media carousel outline with slide-by-slide content.",
        "/script": "Write a short social media video or reel script.",
        "/cta": "Write strong call-to-action lines.",
        "/hashtags": "Suggest relevant hashtags.",
        "/quiz": "Create a useful quiz with answers from this topic.",
        "/flashcards": "Create study flashcards from this topic.",
        "/explain": "Explain this topic simply and clearly for learning.",
        "/exam": "Create exam-style questions and answers from this topic.",
        "/plan": "Create a practical business plan draft.",
        "/pitch": "Create a business pitch.",
        "/pricing": "Suggest a pricing structure and reasoning.",
        "/strategy": "Create a practical business strategy.",
        "/swot": "Create a SWOT analysis.",
        "/businessmodel": "Create a business model outline.",
    }

    if command in command_pack_map:
        source_text = get_referenced_text(message, argument, user_id)
        if not source_text:
            send_message(
                chat_id,
                f"Reply to a message with {command} or pass text after the command.",
                reply_to_message_id=message_id,
            )
            return

        try:
            send_chat_action(chat_id, "typing")
            answer = run_structured_command(
                user_id,
                command,
                source_text,
                command_pack_map[command],
            )
            send_message(chat_id, answer, reply_to_message_id=message_id)
        except requests.HTTPError as exc:
            logger.exception("HTTP error while running command pack")
            error_body = exc.response.text[:500] if exc.response is not None else str(exc)
            send_message(chat_id, f"API error:\n{error_body}", reply_to_message_id=message_id)
        except Exception as exc:
            logger.exception("Unexpected bot error during command pack")
            send_message(chat_id, f"Error: {exc}", reply_to_message_id=message_id)
        return

    if command == "/qr":
        qr_path: str | None = None
        try:
            source_text = get_referenced_text(message, argument, user_id)
            if not source_text:
                send_message(chat_id, "Use /qr <text or link>.", reply_to_message_id=message_id)
                return
            send_chat_action(chat_id, "upload_photo")
            qr_path, qr_value = create_qr_code_image(source_text)
            send_photo_file(
                chat_id,
                qr_path,
                file_name="qrcode.png",
                caption=f"QR code ready.\n{clip_text(qr_value, 200)}",
                reply_to_message_id=message_id,
            )
        except requests.HTTPError as exc:
            logger.exception("HTTP error while creating QR code")
            error_body = exc.response.text[:500] if exc.response is not None else str(exc)
            send_message(chat_id, f"QR error:\n{error_body}", reply_to_message_id=message_id)
        except Exception as exc:
            logger.exception("Unexpected bot error during QR creation")
            send_message(chat_id, f"Error: {exc}", reply_to_message_id=message_id)
        finally:
            if qr_path:
                try:
                    os.remove(qr_path)
                except OSError:
                    logger.warning("Could not delete temp QR file %s", qr_path)
        return

    if command in {CMD_REWRITE, "/shorter", "/formal", "/friendly", "/fixgrammar", CMD_SUMMARIZE}:
        instruction_map = {
            CMD_REWRITE: "Rewrite this to sound better while keeping the meaning.",
            "/shorter": "Make this shorter and tighter while keeping the main meaning.",
            "/formal": "Rewrite this in a formal and polished tone.",
            "/friendly": "Rewrite this in a warm, friendly, natural tone.",
            "/fixgrammar": "Fix grammar, spelling, and awkward wording without changing the meaning.",
            CMD_SUMMARIZE: "Summarize this clearly and briefly.",
        }
        source_text = get_referenced_text(message, argument, user_id)
        if not source_text:
            send_message(
                chat_id,
                f"Reply to a message with {command} or pass text after the command.",
                reply_to_message_id=message_id,
            )
            return

        try:
            send_chat_action(chat_id, "typing")
            answer = transform_text(
                user_id,
                command,
                source_text,
                instruction_map[command],
                max_tokens=SUMMARY_MAX_TOKENS if command == CMD_SUMMARIZE else TRANSFORM_MAX_TOKENS,
            )
            send_message(chat_id, answer, reply_to_message_id=message_id)
        except requests.HTTPError as exc:
            logger.exception("HTTP error while transforming text")
            error_body = exc.response.text[:500] if exc.response is not None else str(exc)
            send_message(chat_id, f"API error:\n{error_body}", reply_to_message_id=message_id)
        except Exception as exc:
            logger.exception("Unexpected bot error during text transform")
            send_message(chat_id, f"Error: {exc}", reply_to_message_id=message_id)
        return

    if command == "/translate":
        try:
            target_language, source_text = parse_translate_argument(message, argument)
        except Exception as exc:
            send_message(chat_id, f"Error: {exc}", reply_to_message_id=message_id)
            return

        try:
            send_chat_action(chat_id, "typing")
            answer = transform_text(
                user_id,
                command,
                source_text,
                f"Translate this into {target_language}. Keep it natural and accurate.",
            )
            send_message(chat_id, answer, reply_to_message_id=message_id)
        except requests.HTTPError as exc:
            logger.exception("HTTP error while translating text")
            error_body = exc.response.text[:500] if exc.response is not None else str(exc)
            send_message(chat_id, f"API error:\n{error_body}", reply_to_message_id=message_id)
        except Exception as exc:
            logger.exception("Unexpected bot error during translation")
            send_message(chat_id, f"Error: {exc}", reply_to_message_id=message_id)
        return

    if command == "/remind":
        if not argument:
            send_message(
                chat_id,
                "Use /remind <when> | <text>\nExample:\n/remind tomorrow 9am | call mom",
                reply_to_message_id=message_id,
            )
            return

        try:
            reminder = create_reminder(user_id, chat_id, argument)
            send_message(
                chat_id,
                f"Reminder saved.\nID: {reminder['id']}\nWhen: {format_local_datetime(reminder['due_at'])}\nText: {reminder['text']}",
                reply_to_message_id=message_id,
            )
        except Exception as exc:
            send_message(chat_id, f"Error: {exc}", reply_to_message_id=message_id)
        return

    if command == "/reminders":
        action = argument.strip().split(maxsplit=1)
        if action and action[0].lower() == "delete" and len(action) == 2:
            if delete_reminder(user_id, action[1].strip()):
                send_message(chat_id, "Reminder deleted.", reply_to_message_id=message_id)
            else:
                send_message(chat_id, "Reminder not found.", reply_to_message_id=message_id)
            return

        reminders = list_reminders_for_user(user_id)
        if not reminders:
            send_message(chat_id, "No pending reminders.", reply_to_message_id=message_id)
            return

        reminder_lines = [
            f"{item['id']} - {format_local_datetime(item['due_at'])} - {item['text']}"
            for item in reminders
        ]
        send_message(chat_id, "Pending reminders\n" + "\n".join(reminder_lines), reply_to_message_id=message_id)
        return

    if command == "/todo":
        todo_parts = argument.strip().split(maxsplit=1)
        if not todo_parts:
            send_message(
                chat_id,
                "Use /todo add <text>, /todo list, /todo done <id>, or /todo delete <id>.",
                reply_to_message_id=message_id,
            )
            return

        action = todo_parts[0].lower()
        payload = todo_parts[1].strip() if len(todo_parts) > 1 else ""

        if action == "add":
            if not payload:
                send_message(chat_id, "Use /todo add <text>.", reply_to_message_id=message_id)
                return
            item = add_todo(user_id, payload)
            send_message(chat_id, f"Todo saved.\n{item['id']} - {item['text']}", reply_to_message_id=message_id)
            return

        if action == "list":
            items = list_todos(user_id)
            if not items:
                send_message(chat_id, "Your todo list is empty.", reply_to_message_id=message_id)
                return
            lines = [
                f"{item['id']} - {'[done]' if item.get('done') else '[open]'} {item['text']}"
                for item in items
            ]
            send_message(chat_id, "Todo list\n" + "\n".join(lines), reply_to_message_id=message_id)
            return

        if action == "done" and payload:
            if update_todo(user_id, payload, done=True):
                send_message(chat_id, "Todo marked done.", reply_to_message_id=message_id)
            else:
                send_message(chat_id, "Todo not found.", reply_to_message_id=message_id)
            return

        if action == "delete" and payload:
            if update_todo(user_id, payload, delete=True):
                send_message(chat_id, "Todo deleted.", reply_to_message_id=message_id)
            else:
                send_message(chat_id, "Todo not found.", reply_to_message_id=message_id)
            return

        send_message(
            chat_id,
            "Use /todo add <text>, /todo list, /todo done <id>, or /todo delete <id>.",
            reply_to_message_id=message_id,
        )
        return

    if command == "/idea":
        if not argument:
            send_message(chat_id, "Use /idea <text>.", reply_to_message_id=message_id)
            return
        item = add_idea(user_id, argument)
        send_message(chat_id, f"Idea saved.\n{item['id']} - {item['text']}", reply_to_message_id=message_id)
        return

    if command == "/ideas":
        items = list_ideas(user_id)
        if not items:
            send_message(chat_id, "No saved ideas.", reply_to_message_id=message_id)
            return
        lines = [f"{item['id']} - {item['text']}" for item in items]
        send_message(chat_id, "Ideas\n" + "\n".join(lines), reply_to_message_id=message_id)
        return

    if command == "/presentation":
        conversation_modes[user_id] = "presentation"
        if not argument:
            send_message(
                chat_id,
                (
                    "Presentation mode enabled.\n"
                    "Send a topic or brief, or use:\n"
                    "/presentation Q2 sales review for a 10-minute team update"
                ),
                reply_to_message_id=message_id,
            )
            return

        try:
            send_chat_action(chat_id, "typing")
            answer = request_chat_completion(
                user_id,
                argument,
                system_prompt=PRESENTATION_SYSTEM_PROMPT,
                max_tokens=PRESENTATION_MAX_TOKENS,
            )
            send_message(chat_id, answer, reply_to_message_id=message_id)
        except requests.HTTPError as exc:
            logger.exception("HTTP error while processing presentation request")
            error_body = exc.response.text[:500] if exc.response is not None else str(exc)
            send_message(chat_id, f"API error:\n{error_body}", reply_to_message_id=message_id)
        except Exception as exc:
            logger.exception("Unexpected bot error during presentation request")
            send_message(chat_id, f"Error: {exc}", reply_to_message_id=message_id)
        return

    if command == "/link":
        if not argument:
            send_message(
                chat_id,
                "Send a public URL like:\n/link https://example.com",
                reply_to_message_id=message_id,
            )
            return

        try:
            send_chat_action(chat_id, "typing")
            answer = analyze_link(user_id, argument)
            send_message(chat_id, answer, reply_to_message_id=message_id)
        except requests.HTTPError as exc:
            logger.exception("HTTP error while analyzing link")
            error_body = exc.response.text[:500] if exc.response is not None else str(exc)
            send_message(chat_id, f"Link fetch error:\n{error_body}", reply_to_message_id=message_id)
        except Exception as exc:
            logger.exception("Unexpected bot error during link analysis")
            send_message(chat_id, f"Error: {exc}", reply_to_message_id=message_id)
        return

    auto_url = extract_first_url(text)
    if auto_url and text == auto_url:
        try:
            send_chat_action(chat_id, "typing")
            answer = analyze_link(user_id, auto_url)
            send_message(chat_id, answer, reply_to_message_id=message_id)
        except requests.HTTPError as exc:
            logger.exception("HTTP error while auto-analyzing link")
            error_body = exc.response.text[:500] if exc.response is not None else str(exc)
            send_message(chat_id, f"Link fetch error:\n{error_body}", reply_to_message_id=message_id)
        except Exception as exc:
            logger.exception("Unexpected bot error during auto link analysis")
            send_message(chat_id, f"Error: {exc}", reply_to_message_id=message_id)
        return

    if current_has_attachment and (not text or not command.startswith("/")):
        try:
            send_chat_action(chat_id, "typing")
            answer = analyze_message_attachment(
                user_id,
                message,
                get_attachment_prompt(text, "Analyze this attachment and explain the important details."),
            )
            send_message(chat_id, answer, reply_to_message_id=message_id)
        except requests.HTTPError as exc:
            logger.exception("HTTP error while auto-analyzing attachment")
            error_body = exc.response.text[:500] if exc.response is not None else str(exc)
            send_message(chat_id, f"Attachment analysis error:\n{error_body}", reply_to_message_id=message_id)
        except Exception as exc:
            logger.exception("Unexpected bot error during auto attachment analysis")
            send_message(chat_id, f"Error: {exc}", reply_to_message_id=message_id)
        return

    lowered_text = text.lower()
    if lowered_text.startswith("remind me "):
        try:
            reminder = create_reminder(user_id, chat_id, text[len("remind me "):])
            send_message(
                chat_id,
                f"Reminder saved.\nID: {reminder['id']}\nWhen: {format_local_datetime(reminder['due_at'])}\nText: {reminder['text']}",
                reply_to_message_id=message_id,
            )
        except Exception as exc:
            send_message(chat_id, f"Error: {exc}", reply_to_message_id=message_id)
        return

    if lowered_text.startswith("save this idea"):
        idea_text = text[len("save this idea"):].lstrip(" :.-")
        if idea_text:
            item = add_idea(user_id, idea_text)
            send_message(chat_id, f"Idea saved.\n{item['id']} - {item['text']}", reply_to_message_id=message_id)
            return

    if lowered_text.startswith("add todo "):
        item = add_todo(user_id, text[len("add todo "):])
        send_message(chat_id, f"Todo saved.\n{item['id']} - {item['text']}", reply_to_message_id=message_id)
        return

    if lowered_text in {"track my to-do list", "track my todo list", "show my todo list"}:
        items = list_todos(user_id)
        if not items:
            send_message(chat_id, "Your todo list is empty.", reply_to_message_id=message_id)
        else:
            lines = [
                f"{item['id']} - {'[done]' if item.get('done') else '[open]'} {item['text']}"
                for item in items
            ]
            send_message(chat_id, "Todo list\n" + "\n".join(lines), reply_to_message_id=message_id)
        return

    try:
        send_chat_action(chat_id, "typing")
        answer = request_chat_completion(
            user_id,
            text,
            system_prompt=get_system_prompt_for_message(user_id, text),
            max_tokens=get_max_tokens_for_message(text),
        )
        send_message(chat_id, answer, reply_to_message_id=message_id)
    except requests.HTTPError as exc:
        logger.exception("HTTP error while processing message")
        error_body = exc.response.text[:500] if exc.response is not None else str(exc)
        send_message(chat_id, f"API error:\n{error_body}", reply_to_message_id=message_id)
    except Exception as exc:
        logger.exception("Unexpected bot error")
        send_message(chat_id, f"Error: {exc}", reply_to_message_id=message_id)


def get_updates(offset: int | None = None) -> list[dict[str, Any]]:
    params: dict[str, Any] = {
        "timeout": POLL_TIMEOUT,
        "allowed_updates": ["message"],
    }
    if offset is not None:
        params["offset"] = offset

    response = session.get(
        f"{TELEGRAM_API_BASE}/getUpdates",
        params=params,
        timeout=POLL_TIMEOUT + 10,
    )
    response.raise_for_status()
    data = response.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram polling error: {data}")
    return data.get("result", [])


def main() -> None:
    logger.info("Bot started for allowed user IDs %s", sorted(TELEGRAM_ALLOWED_USER_IDS))
    offset: int | None = None
    commands_registered = False
    last_reminder_check = 0.0

    while True:
        try:
            if not commands_registered:
                register_bot_commands()
                commands_registered = True
            if time.time() - last_reminder_check >= 5:
                process_due_reminders()
                last_reminder_check = time.time()
            updates = get_updates(offset)
            for update in updates:
                offset = update["update_id"] + 1
                message = update.get("message")
                if message:
                    handle_text_message(message)
        except KeyboardInterrupt:
            logger.info("Bot stopped by user")
            break
        except Exception:
            logger.exception("Polling loop failed, retrying shortly")
            time.sleep(3)


if __name__ == "__main__":
    main()
