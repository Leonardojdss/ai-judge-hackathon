import logging
import time

import requests

logger = logging.getLogger(__name__)


class ModelProvider:
    def __init__(self, settings, session=None):
        self.settings = settings
        self.session = session or requests.Session()

    def answer(self, message):
        started = time.monotonic()
        for attempt in range(self.settings.attempts):
            try:
                response = self.session.post(self.settings.model_url, json={"prompt": message}, timeout=self.settings.timeout)
                response.raise_for_status()
                logger.info("model_completed duration=%s", time.monotonic() - started)
                return response.json()
            except (requests.Timeout, requests.ConnectionError):
                logger.warning("model_transient_failure attempt=%s", attempt + 1)
                if attempt + 1 == self.settings.attempts:
                    return {"text": "Service temporarily unavailable"}
                time.sleep(2 ** attempt)
