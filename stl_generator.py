from __future__ import annotations

import json
import time
from typing import Any

import requests

from config import get_setting


class GroqKeyRotator:
    """Safe round-robin rotation for Groq API keys with retry and rate-limit handling."""

    def __init__(self, env_key_name: str = "GROQ_API_KEYS") -> None:
        self.env_key_name = env_key_name
        self.key_index = 0
        self._keys = self._load_keys()
        self.current_key = self._keys[0] if self._keys else ""
        self.last_error: str | None = None

    def _load_keys(self) -> list[str]:
        raw = get_setting(self.env_key_name, "")
        return [item.strip() for item in raw.split(",") if item.strip()]

    def refresh(self) -> None:
        self._keys = self._load_keys()
        if not self._keys:
            self.current_key = ""
            self.key_index = 0
            return
        self.key_index %= len(self._keys)
        self.current_key = self._keys[self.key_index]

    def rotate(self) -> str:
        if not self._keys:
            raise RuntimeError("No Groq API keys configured.")
        self.key_index = (self.key_index + 1) % len(self._keys)
        self.current_key = self._keys[self.key_index]
        return self.current_key

    def get_current(self) -> str:
        if not self._keys:
            raise RuntimeError("No Groq API keys configured.")
        return self._keys[self.key_index]

    def request(self, url: str, payload: dict[str, Any], timeout: int = 90) -> requests.Response:
        if not self._keys:
            raise RuntimeError("No Groq API keys configured.")

        max_attempts = max(1, len(self._keys) * 4)
        for attempt in range(max_attempts):
            key = self.get_current()
            headers = {
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            }
            try:
                response = requests.post(url, headers=headers, json=payload, timeout=timeout)
                if response.status_code == 429:
                    self.last_error = f"Rate limited by Groq (429)."
                    self.rotate()
                    time.sleep(2.0)
                    continue
                if response.status_code in {500, 502, 503, 504}:
                    self.last_error = f"Groq service error status {response.status_code}."
                    self.rotate()
                    time.sleep(1.5)
                    continue
                if response.status_code >= 400:
                    try:
                        error_body = response.json()
                    except ValueError:
                        error_body = {"message": response.text}
                    raise RuntimeError(f"Groq API request failed with status {response.status_code}: {json.dumps(error_body)}")
                return response
            except requests.RequestException as exc:
                self.last_error = f"Network failure: {exc}"
                self.rotate()
                if attempt == max_attempts - 1:
                    raise RuntimeError(f"Groq service unavailable: {exc}") from exc
                time.sleep(1.5)

        raise RuntimeError("Groq request exhausted all retries.")

    def request_json(self, url: str, payload: dict[str, Any], timeout: int = 90) -> dict[str, Any]:
        response = self.request(url, payload, timeout=timeout)
        try:
            return response.json()
        except ValueError as exc:
            raise RuntimeError(f"Groq API returned invalid JSON: {response.text}") from exc
