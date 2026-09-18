from src.config.settings import Settings
from src.infrastructure.provider_factory.aws_bedrock import ConnectAWSBedrock
from src.infrastructure.provider_factory.google import ConnectGoogleGenAI
from src.infrastructure.provider_factory.ollama import ConnectOllama
from src.infrastructure.provider_factory.openai import ConnectOpenAI


class ConnectionModelFactory:
    _registry = {"openai": ConnectOpenAI, "ollama": ConnectOllama,
                 "aws_bedrock": ConnectAWSBedrock, "google_gemini": ConnectGoogleGenAI}

    @staticmethod
    def create_connection_model(provider: str | None = None, **kwargs):
        settings = kwargs.pop("settings", None) or Settings()
        provider = provider or settings.PROVIDER_LLM
        if provider not in ConnectionModelFactory._registry:
            raise ValueError("Unsupported model provider")
        if provider != settings.PROVIDER_LLM:
            settings = settings.model_copy(update={"PROVIDER_LLM": provider})
        return ConnectionModelFactory._registry[provider](settings=settings, **kwargs)
