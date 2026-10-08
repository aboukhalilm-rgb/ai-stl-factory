from __future__ import annotations

import logging
import random
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler

from config import DEFAULT_CATEGORIES, LOGS_DIR, get_setting
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
        self.scheduler = BackgroundScheduler(daemon=True)
        self.generator = stl_generator or STLGenerator(GroqKeyRotator())
        self.notifier = notifier or TelegramNotifier()
        self._running = False

    def pick_category(self, category_name: str | None = None) -> str:
        if category_name:
            return category_name
        return random.choice(DEFAULT_CATEGORIES)

    def run_one_job(self, category_name: str | None = None, count: int = 1) -> dict[str, Any]:
        category = self.pick_category(category_name)
        self.logger.info("Starting generation for category: %s", category)
        results: list[dict[str, Any]] = []
        for _ in range(max(1, count)):
            request = GenerationRequest(category=category, count=count)
            try:
                result = self.generator.generate_model(request)
                results.append(result)
                self.logger.info("Completed generation: %s", result.get("file_path"))
                if self.notifier.is_configured():
                    self.notifier.send_stl_success(result)
            except Exception as exc:
                self.logger.exception("Generation failed for %s: %s", category, exc)
                results.append({"category": category, "status": "failed", "error": str(exc)})
        return {"category": category, "items": results, "count": len(results)}

    def start(self) -> None:
        if self._running:
            return

        interval_seconds = int(get_setting("SCHEDULER_INTERVAL_SECONDS", "10800"))
        self.scheduler.add_job(
            func=self.run_one_job,
            trigger="interval",
            seconds=interval_seconds,
            id="ai_stl_factory_job",
            replace_existing=True,
        )
        self.scheduler.start()
        self._running = True
        self.logger.info("Scheduler started with %s second interval.", interval_seconds)

    def stop(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
        self._running = False
        self.logger.info("Scheduler stopped.")


if __name__ == "__main__":
    scheduler = STLFactoryScheduler()
    scheduler.start()
    import time

    while True:
        time.sleep(1)
