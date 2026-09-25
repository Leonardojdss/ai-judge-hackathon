"""Versioned hackathon rubric, shared by prompts and deterministic validation."""
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Question:
    id: int
    text: str
    anchors: tuple[tuple[int, str], ...]
    allow_documentation: bool

    @property
    def allowed_scores(self) -> tuple[int, ...]:
        return tuple(score for score, _ in self.anchors)


@dataclass(frozen=True)
class Criterion:
    id: str
    title: str
    questions: tuple[Question, ...]

    @property
    def maximum_score(self) -> int:
        return sum(max(question.allowed_scores) for question in self.questions)


_data = json.loads(Path(__file__).with_name("hackathon_rubric.json").read_text(encoding="utf-8"))
RUBRIC_VERSION = _data["version"]
RUBRIC = tuple(Criterion(
    id=criterion["id"], title=criterion["title"],
    questions=tuple(Question(
        id=question["id"], text=question["text"],
        anchors=tuple((int(score), text) for score, text in question["anchors"].items()),
        allow_documentation=question["allow_documentation"],
    ) for question in criterion["questions"]),
) for criterion in _data["criteria"])
CRITERIA_BY_ID = {criterion.id: criterion for criterion in RUBRIC}
