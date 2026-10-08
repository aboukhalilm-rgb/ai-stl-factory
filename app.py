from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import requests
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from config import get_service_account_path, get_setting


class TelegramNotifier:
    def __init__(self) -> None:
        self.token = get_setting("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = get_setting("TELEGRAM_CHAT_ID", "")

    def is_configured(self) -> bool:
        return bool(self.token and self.chat_id)

    def send_text(self, message: str) -> bool:
        if not self.is_configured():
            return False
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = {"chat_id": self.chat_id, "text": message, "parse_mode": "HTML"}
        try:
            response = requests.post(url, json=payload, timeout=30)
            return response.status_code == 200
        except requests.RequestException:
            return False

    def send_stl_success(self, result: dict[str, Any]) -> bool:
        if not self.is_configured():
            return False

        file_path = Path(result.get("file_path", ""))
        caption = (
            "<b>STL generated</b>\n"
            f"Title: {result.get('title', 'N/A')}\n"
            f"Category: {result.get('category', 'N/A')}\n"
            f"File: {file_path.name if file_path.name else 'n/a'}"
        )

        if not file_path.exists():
            return self.send_text(caption)

        try:
            with open(file_path, "rb") as stream:
                response = requests.post(
                    f"https://api.telegram.org/bot{self.token}/sendDocument",
                    data={"chat_id": self.chat_id, "caption": caption, "parse_mode": "HTML"},
                    files={"document": (file_path.name, stream, "application/octet-stream")},
                    timeout=60,
                )
            return response.status_code == 200
        except requests.RequestException:
            return False


class GoogleDriveArchiver:
    def __init__(self) -> None:
        self.folder_id = get_setting("GOOGLE_DRIVE_FOLDER_ID", "")
        self.service_account_file = get_service_account_path()

    def is_configured(self) -> bool:
        return bool(self.folder_id and self.service_account_file and self.service_account_file.exists())

    def upload_stl(self, file_path: str, category: str) -> str | None:
        if not self.is_configured():
            return None
        try:
            credentials = service_account.Credentials.from_service_account_file(
                str(self.service_account_file),
                scopes=["https://www.googleapis.com/auth/drive"],
            )
            service = build("drive", "v3", credentials=credentials)

            folder_name = category.replace("/", "_").replace(" ", "_")
            folder_metadata = {
                "name": folder_name,
                "mimeType": "application/vnd.google-apps.folder",
                "parents": [self.folder_id],
            }
            try:
                folder = service.files().create(body=folder_metadata, fields="id").execute()
                destination_folder = folder.get("id")
            except Exception:
                destination_folder = self.folder_id

            file_obj = Path(file_path)
            media = MediaFileUpload(str(file_obj), mimetype="application/octet-stream", resumable=True)
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            file_metadata = {
                "name": f"{file_obj.stem}_{timestamp}.stl",
                "parents": [destination_folder],
            }
            uploaded = service.files().create(body=file_metadata, media_body=media, fields="id,webViewLink").execute()
            return uploaded.get("webViewLink")
        except Exception:
            return None


if __name__ == "__main__":
    notifier = TelegramNotifier()
    print("Telegram configured:", notifier.is_configured())
    drive = GoogleDriveArchiver()
    print("Google Drive configured:", drive.is_configured())
