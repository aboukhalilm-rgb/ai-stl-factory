from __future__ import annotations

import atexit
import json
import logging
import random
from datetime import datetime
from pathlib import Path
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler

from config import BASE_DIR, LOGS_DIR, DEFAULT_CATEGORIES, get_setting
from key_rotator import GroqKeyRotator
from stl_generator import GenerationRequest, STLGenerator
from uploader import TelegramNotifier


LOG_PATH = LOGS_DIR / "factory.log"


def configure_logging() -> logging.Logger:
    logger = logging.getLogger("ai_stl_factory")
    logger.setLevel(logging.INFO)
    if logger.handlers:
        return logger
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    file_handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)
    return logger


class STLFactoryScheduler:
    def __init__(self, stl_generator: STLGenerator | None = None, notifier: TelegramNotifier | None = None) -> None:
        self.logger = configure_logging()
        self.scheduler = BackgroundScheduler()
        self.generator = stl_generator or STLGenerator(GroqKeyRotator())
        self.notifier = notifier or TelegramNotifier()
        self._running = False

    def pick_category(self, category_name: str | None = None) -> str:
        if category_name:
            return category_name
        return random.choice(DEFAULT_CATEGORIES)

    def run_one_job(self, category_name: str | None = None, count: int = 1) -> dict[str, Any]:
        category = self.pick_category(category_name)
        self.logger.info("Starting scheduled generation for category: %s", category)
        request = GenerationRequest(category=category, count=count, custom_parameters={})
        try:
            result = self.generator.generate_model(request)
            self.logger.info("Completed generation for %s: %s", category, result.get("file_path"))
            if self.notifier.is_configured():
                self.notifier.send_stl_success(result)
            return result
        except Exception as exc:
            self.logger.exception("Generation failed for %s: %s", category, exc)
            return {"category": category, "error": str(exc), "status": "failed"}

    def start(self) -> None:
        if self._running:
            return
        self.scheduler.add_job(
            func=self.run_one_job,
            trigger="interval",
            seconds=int(get_setting("SCHEDULER_INTERVAL_SECONDS", "10800")),
            id="ai_stl_factory_job",
            replace_existing=True,
        )
        self.scheduler.start()
        atexit.register(self.shutdown)
        self._running = True
        self.logger.info("Scheduler started with 3-hour interval.")

    def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
        self._running = False
        self.logger.info("Scheduler shut down.")


if __name__ == "__main__":
    scheduler = STLFactoryScheduler()
    scheduler.start()
    print("Factory scheduler running. Press Ctrl+C to stop.")
    while True:
        import time
        time.sleep(1)
