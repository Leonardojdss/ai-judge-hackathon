import re
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator

from src.utils.rubric import CRITERIA_BY_ID


def normalize_repository(value: str) -> str:
    value = value.strip()
    if value.startswith("https://"):
        parsed = urlsplit(value)
        if parsed.netloc != "github.com" or parsed.query or parsed.fragment:
            raise ValueError("Use a github.com repository URL")
        value = parsed.path.strip("/")
    value = value.removesuffix(".git")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9_.-]+", value):
        raise ValueError("Use https://github.com/owner/repo or owner/repo")
    if value.split("/")[1] in {".", ".."}:
        raise ValueError("Invalid repository")
    return "https://github.com/" + value


class RepositoryAssessmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    repository_url: str
    ref: str | None = Field(default=None, min_length=1, max_length=255)

    _normalize = field_validator("repository_url")(normalize_repository)

    @field_validator("ref")
    @classmethod
    def validate_ref(cls, value):
        if value and (value != value.strip() or any(ord(c) < 32 for c in value)):
            raise ValueError("Invalid git reference")
        return value


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Evidence(Contract):
    file: str = Field(min_length=1)
    description: str = Field(min_length=1)
    line: Annotated[StrictInt, Field(ge=1)]
    snippet: str = Field(min_length=1)


class QuestionAssessment(Contract):
    question_id: Annotated[StrictInt, Field(ge=1, le=5)]
    score: Annotated[StrictInt, Field(ge=0, le=2)]
    status: Literal["does_not_meet", "partially_meets", "meets"]
    reason: str = Field(min_length=1)
    evidence: list[Evidence]

    @model_validator(mode="after")
    def validate_result(self):
        if self.status != ("does_not_meet", "partially_meets", "meets")[self.score]:
            raise ValueError("Score and status disagree")
        if self.score > 0 and not self.evidence:
            raise ValueError("Positive scores require evidence")
        if not self.reason.strip():
            raise ValueError("Question reason must not be blank")
        return self


class ModelQuestionAssessment(Contract):
    """Minimal question contract requested from the model."""
    question_id: Annotated[StrictInt, Field(ge=1, le=5)]
    score: Annotated[StrictInt, Field(ge=0, le=2)]
    reason: str = Field(min_length=1)
    evidence: list[Evidence]


class ModelAssessmentOutput(Contract):
    """Provider output; server-owned criterion and status are deliberately absent."""
    questions: list[ModelQuestionAssessment] = Field(min_length=5, max_length=5)
    summary: str = Field(min_length=1)

    def to_assessment_result(self, criterion: str) -> "AssessmentResult":
        questions = [
            {
                **question.model_dump(),
                "status": ("does_not_meet", "partially_meets", "meets")[question.score],
            }
            for question in self.questions
        ]
        return AssessmentResult(
            criterion=criterion,
            questions=questions,
            summary=self.summary,
        )


class AssessmentResult(Contract):
    """Validated internal result with server-owned derived fields."""
    criterion: str = Field(min_length=1)
    questions: list[QuestionAssessment] = Field(min_length=5, max_length=5)
    summary: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_rubric(self):
        rubric = CRITERIA_BY_ID.get(self.criterion)
        if rubric is None:
            raise ValueError("Unknown criterion")
        if {q.question_id for q in self.questions} != {q.id for q in rubric.questions}:
            raise ValueError("All five questions must occur exactly once")
        for answer in self.questions:
            question = next(q for q in rubric.questions if q.id == answer.question_id)
            if answer.score not in question.allowed_scores:
                raise ValueError("Score not allowed for this rubric question")
        if not self.summary.strip():
            raise ValueError("Summary must not be blank")
        self.questions.sort(key=lambda q: q.question_id)
        return self

    @property
    def score(self) -> int:
        return sum(question.score for question in self.questions)


class CriterionScore(Contract):
    criterion: str
    score: Annotated[StrictInt, Field(ge=0, le=10)] | None = None
    maximum_score: Literal[10] = 10
    reason: str = Field(min_length=1)


class FinalSynthesis(Contract):
    total_score: int | None
    maximum_score: int
    percentage: float | None
    summary: str = Field(min_length=1)


class RepositoryAssessmentResponse(Contract):
    execution_id: str
    repository: dict
    execution_status: Literal["completed", "partial", "failed"]
    criteria: list[CriterionScore]
    final_synthesis: FinalSynthesis
    errors: list[dict]
