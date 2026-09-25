from abc import ABC, abstractmethod

from src.config.settings import Settings


class ConnectionModelNaturalLanguage(ABC):
    def __init__(self, settings: Settings, model: str | None = None):
        self.settings = settings
        self.model = model or settings.model_name

    @abstractmethod
    def connection(self):
        """Return a LangChain chat model using the provider's native defaults."""
