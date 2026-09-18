from src.infrastructure.provider_factory.connection_models import ConnectionModelNaturalLanguage


class ConnectOllama(ConnectionModelNaturalLanguage):
    def connection(self):
        from langchain_ollama import ChatOllama

        return ChatOllama(model=self.model, base_url=self.settings.OLLAMA_BASE_URL,
                          temperature=0, num_ctx=self.settings.MODEL_CONTEXT_TOKENS,
                          num_predict=self.settings.OUTPUT_TOKEN_BUDGET,
                          client_kwargs={"timeout": self.settings.LLM_TIMEOUT})
