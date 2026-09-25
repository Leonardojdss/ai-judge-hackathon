from dataclasses import dataclass

from src.utils.prompts import PROMPTS
from src.utils.rubric import CRITERIA_BY_ID, RUBRIC


@dataclass(frozen=True)
class Evaluator:
    criterion: str
    prompt: str

    @property
    def maximum_score(self) -> int:
        return CRITERIA_BY_ID[self.criterion].maximum_score


EVALUATORS = tuple(Evaluator(criterion.id, PROMPTS[criterion.id]) for criterion in RUBRIC)
