from __future__ import annotations

import json
import os
import random
import time
from typing import Any

import requests

from config import get_setting


class GroqKeyRotator:
    """Round-robin rotation for Groq API keys with fallback on 429."""

    def __init__(self, env_key_name: str = "GROQ_API_KEYS") -> None:
        self.env_key_name = env_key_name
        self.key_index = 0
        self._keys = self._load_keys()
        self.current_key = self._keys[0] if self._keys else ""

    def _load_keys(self) -> list[str]:
        raw = get_setting(self.env_key_name, "")
        keys = [k.strip() for k in raw.split(",") if k.strip()]
        if not keys:
            return []
        return keys

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

    def reset(self) -> None:
        self.key_index = 0
        self._keys = self._load_keys()
        if self._keys:
            self.current_key = self._keys[0]

    def request(self, url: str, payload: dict[str, Any], timeout: int = 60) -> requests.Response:
        if not self._keys:
            raise RuntimeError("No Groq API keys configured.")

        for attempt in range(len(self._keys) * 3):
            key = self.get_current()
            headers = {
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            }
            try:
                response = requests.post(url, headers=headers, json=payload, timeout=timeout)
                if response.status_code == 429:
                    self.rotate()
                    time.sleep(1.2)
                    continue
                if response.status_code >= 400:
                    try:
                        error_data = response.json()
                    except Exception:
                        error_data = {"message": response.text}
                    raise RuntimeError(f"Groq API error {response.status_code}: {json.dumps(error_data)}")
                return response
            except requests.RequestException as exc:
                self.rotate()
                if attempt == (len(self._keys) * 3) - 1:
                    raise RuntimeError(f"Groq network failure: {exc}")
                time.sleep(1)

        raise RuntimeError("Groq request exhausted all retries.")
