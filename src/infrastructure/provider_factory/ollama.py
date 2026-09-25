from src.infrastructure.provider_factory.connection_models import ConnectionModelNaturalLanguage


class ConnectOllama(ConnectionModelNaturalLanguage):
    def connection(self):
        from langchain_ollama import ChatOllama

        return ChatOllama(model=self.model, base_url=self.settings.OLLAMA_BASE_URL,
                          temperature=0)
