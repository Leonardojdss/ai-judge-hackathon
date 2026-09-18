from dataclasses import dataclass

from src.utils.prompts import ENGINEERING_MECHANISMS_PROMPT, RESPONSIBLE_AI_PROMPT, SOFTWARE_ARCHITECTURE_PROMPT


@dataclass(frozen=True)
class Evaluator:
    criterion: str
    prompt: str


EVALUATORS = (
    Evaluator("responsible_ai", RESPONSIBLE_AI_PROMPT),
    Evaluator("software_architecture", SOFTWARE_ARCHITECTURE_PROMPT),
    Evaluator("engineering_mechanisms", ENGINEERING_MECHANISMS_PROMPT),
)
