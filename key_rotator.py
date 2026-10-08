from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dotenv import dotenv_values, set_key
from cryptography.fernet import Fernet
from werkzeug.security import generate_password_hash

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
CREDENTIALS_DIR = BASE_DIR / "credentials"
LOGS_DIR = BASE_DIR / "logs"
EXPORTS_DIR = BASE_DIR / "exports"
GENERATED_DIR = BASE_DIR / "generated"

DEFAULT_CATEGORIES = [
    "Tabletop Miniatures & D&D Figurines",
    "Articulated Print-in-Place Toys",
    "Home Organizers & Office Accessories",
    "Resin Jewelry Casting Molds",
    "Dental & Medical Models",
    "Classic Car Parts & Discontinued Machinery Spares",
    "Accessibility Aids",
    "Custom Electronics Enclosures",
    "Parametric Engineering Fittings & Pipe Connectors",
]


def ensure_directories() -> None:
    for folder in (CREDENTIALS_DIR, LOGS_DIR, EXPORTS_DIR, GENERATED_DIR):
        folder.mkdir(parents=True, exist_ok=True)


def load_env() -> dict[str, str]:
    ensure_directories()
    if not ENV_PATH.exists():
        ENV_PATH.write_text("", encoding="utf-8")
    values = dotenv_values(str(ENV_PATH))
    cleaned: dict[str, str] = {}
    for key, value in values.items():
        if key and value is not None:
            cleaned[key] = str(value)
    return cleaned


def write_env(data: dict[str, Any]) -> None:
    env = load_env()
    env.update({str(key): str(value) for key, value in data.items() if value is not None})
    for key, value in env.items():
        set_key(str(ENV_PATH), key, value)


def get_setting(key: str, default: str = "") -> str:
    return str(load_env().get(key, default) or default)


def set_setting(key: str, value: Any) -> None:
    write_env({key: value})


def ensure_initial_password() -> None:
    if get_setting("APP_PASSWORD_HASH"):
        return
    default_hash = generate_password_hash("admin123")
    set_setting("APP_PASSWORD_HASH", default_hash)
    set_setting("APP_SECRET_KEY", Fernet.generate_key().decode("utf-8"))


def get_fernet_key() -> str:
    key = get_setting("APP_ENCRYPTION_KEY", "")
    if not key:
        key = Fernet.generate_key().decode("utf-8")
        set_setting("APP_ENCRYPTION_KEY", key)
    return key


def get_default_category() -> str:
    return DEFAULT_CATEGORIES[0]


def get_category_names() -> list[str]:
    return list(DEFAULT_CATEGORIES)


def get_service_account_path() -> Path | None:
    path_value = get_setting("GOOGLE_SERVICE_ACCOUNT_FILE", "")
    if not path_value:
        return None
    candidate = Path(path_value)
    if not candidate.is_absolute():
        candidate = BASE_DIR / candidate
    return candidate if candidate.exists() else None


def get_config_summary() -> dict[str, Any]:
    env = load_env()
    return {
        "app_name": env.get("APP_NAME", "AI STL Creation Factory"),
        "app_port": int(env.get("APP_PORT", "5000")),
        "password_set": bool(env.get("APP_PASSWORD_HASH") or env.get("APP_PASSWORD")),
        "groq_keys": env.get("GROQ_API_KEYS", ""),
        "telegram_token": bool(env.get("TELEGRAM_BOT_TOKEN")),
        "telegram_chat_id": bool(env.get("TELEGRAM_CHAT_ID")),
        "google_drive_enabled": bool(env.get("GOOGLE_DRIVE_FOLDER_ID")),
        "scheduler_seconds": int(env.get("SCHEDULER_INTERVAL_SECONDS", "10800")),
    }


if __name__ == "__main__":
    ensure_directories()
    print(json.dumps(get_config_summary(), indent=2))
