from src.infrastructure.provider_factory.connection_models import ConnectionModelNaturalLanguage


class ConnectGoogleGenAI(ConnectionModelNaturalLanguage):
    def connection(self):
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(model=self.model, api_key=self.settings.GEMINI_API_KEY,
                                      temperature=0)
