from src.infrastructure.provider_factory.connection_models import ConnectionModelNaturalLanguage


class ConnectOpenAI(ConnectionModelNaturalLanguage):
    def connection(self):
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(model=self.model, api_key=self.settings.OPENAI_API_KEY,
                          temperature=0, timeout=self.settings.LLM_TIMEOUT,
                          max_retries=0, max_tokens=self.settings.OUTPUT_TOKEN_BUDGET)
