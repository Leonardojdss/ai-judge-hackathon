import requests


def answer(message):
    response = requests.post("https://example.invalid/model", json={"prompt": message})
    return response.json()["text"]
