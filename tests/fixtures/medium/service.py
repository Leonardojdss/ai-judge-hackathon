import requests


class AnswerService:
    def answer(self, message):
        try:
            response = requests.post("https://example.invalid/model", json={"prompt": message})
            response.raise_for_status()
            return response.json()["text"]
        except requests.RequestException:
            return "Service unavailable"
