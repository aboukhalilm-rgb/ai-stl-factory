from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import dotenv_values, set_key

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
    for folder in [CREDENTIALS_DIR, LOGS_DIR, EXPORTS_DIR, GENERATED_DIR]:
        folder.mkdir(parents=True, exist_ok=True)


def load_env() -> dict:
    ensure_directories()
    if not ENV_PATH.exists():
        ENV_PATH.write_text("", encoding="utf-8")
    env = dotenv_values(str(ENV_PATH))
    return {key: value for key, value in env.items() if value is not None}


def write_env(data: dict) -> None:
    env = load_env()
    env.update(data)
    for key, value in env.items():
        set_key(str(ENV_PATH), key, str(value))


def get_setting(key: str, default: str = "") -> str:
    value = load_env().get(key, default)
    return str(value)


def ensure_initial_password() -> None:
    password = get_setting("APP_PASSWORD", "")
    if not password:
        set_key(str(ENV_PATH), "APP_PASSWORD", "admin123")


def get_category_names() -> list[str]:
    return DEFAULT_CATEGORIES


def get_default_category() -> str:
    return DEFAULT_CATEGORIES[0]


def get_config_summary() -> dict:
    env = load_env()
    return {
        "app_name": env.get("APP_NAME", "AI STL Creation Factory"),
        "app_port": int(env.get("APP_PORT", "5000")),
        "password_set": bool(env.get("APP_PASSWORD")),
        "groq_keys": env.get("GROQ_API_KEYS", ""),
        "telegram_token": bool(env.get("TELEGRAM_BOT_TOKEN")),
        "telegram_chat_id": bool(env.get("TELEGRAM_CHAT_ID")),
        "google_drive_enabled": bool(env.get("GOOGLE_DRIVE_FOLDER_ID")),
    }


def get_service_account_path() -> Path | None:
    path = get_setting("GOOGLE_SERVICE_ACCOUNT_FILE", "")
    if not path:
        return None
    p = Path(path)
    if not p.is_absolute():
        p = BASE_DIR / p
    if p.exists():
        return p
    return None


if __name__ == "__main__":
    ensure_directories()
    print(json.dumps(get_config_summary(), indent=2))
