import re
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator


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


class Mechanism(Contract):
    mechanism: str = Field(min_length=1)
    implemented: bool
    evidence: list[Evidence]

    @model_validator(mode="after")
    def require_evidence(self):
        if self.implemented and not self.evidence:
            raise ValueError("Implemented mechanisms require evidence")
        return self


class AssessmentResult(Contract):
    criterion: str = Field(min_length=1)
    score: Annotated[StrictInt, Field(ge=0, le=2)]
    status: Literal["does_not_meet", "partially_meets", "meets"]
    summary: str = Field(min_length=1)
    evidence: list[Evidence]
    recommendations: list[str]
    mechanisms: list[Mechanism]

    @model_validator(mode="after")
    def validate_result(self):
        if self.status != ("does_not_meet", "partially_meets", "meets")[self.score]:
            raise ValueError("Score and status disagree")
        if self.score > 0 and not self.evidence:
            raise ValueError("Positive scores require evidence")
        if not self.criterion.strip() or not self.summary.strip():
            raise ValueError("Criterion and summary must not be blank")
        return self


class CriterionOutcome(Contract):
    criterion: str
    execution_status: Literal["completed", "failed", "not_run"]
    score: Annotated[StrictInt, Field(ge=0, le=2)] | None = None
    maximum_score: int = 2
    status: Literal["does_not_meet", "partially_meets", "meets"] | None = None
    summary: str
    evidence: list[Evidence] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    mechanisms: list[Mechanism] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_outcome(self):
        if self.execution_status == "completed":
            AssessmentResult(criterion=self.criterion, score=self.score, status=self.status,
                             summary=self.summary, evidence=self.evidence,
                             recommendations=self.recommendations, mechanisms=self.mechanisms)
        elif self.score is not None or self.status is not None:
            raise ValueError("Uncompleted criteria cannot carry a score or rating")
        return self


class Assessment(Contract):
    total_score: int | None
    maximum_score: int
    percentage: float | None
    criteria: list[CriterionOutcome]


class RepositoryAssessmentResponse(Contract):
    repository: dict
    assessment: Assessment
    summary: str
    metadata: dict
    execution_status: Literal["completed", "partial", "failed"]
    errors: list[dict]
