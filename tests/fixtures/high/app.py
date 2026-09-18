from config import Settings
from providers import ModelProvider
from safety import validate_input, validate_output


class Application:
    def __init__(self, provider=None, settings=None):
        self.settings = settings or Settings()
        self.provider = provider or ModelProvider(self.settings)

    def answer(self, request):
        clean = validate_input(request)
        raw = self.provider.answer(clean)
        return validate_output(raw)
