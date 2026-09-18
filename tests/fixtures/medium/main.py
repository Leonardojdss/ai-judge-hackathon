from service import AnswerService


def answer(message):
    if not isinstance(message, str) or len(message) > 4000:
        raise ValueError("Invalid message")
    return AnswerService().answer(message)
