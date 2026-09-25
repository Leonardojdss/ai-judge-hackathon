from pathlib import Path

import pytest
from pydantic import ValidationError

from conftest import assessment_result
from src.adapters.schemas.repository_assessment import AssessmentResult
from src.utils.prompts import PROMPTS
from src.utils.rubric import CRITERIA_BY_ID, RUBRIC
from src.workflow_agentic.agents.evidence import prepare_context, validate_evidence
from src.workflow_agentic.registry import EVALUATORS


def test_full_rubric_preserves_all_user_questions_and_scoring_anchors():
    original = Path("docs/hackathon-criteria.md").read_text()
    assert len(RUBRIC) == 9
    assert sum(c.maximum_score for c in RUBRIC) == 90
    assert [e.criterion for e in EVALUATORS] == [c.id for c in RUBRIC]
    for criterion in RUBRIC:
        assert len(criterion.questions) == 5
        assert criterion.maximum_score == 10
        for question in criterion.questions:
            assert question.text in original
            assert question.text in PROMPTS[criterion.id]
            for _, anchor in question.anchors:
                assert anchor in original
                assert anchor in PROMPTS[criterion.id]


@pytest.mark.parametrize("criterion", [c.id for c in RUBRIC])
@pytest.mark.parametrize("score", [0, 2])
def test_all_criteria_sum_five_question_scores(criterion, score):
    raw = assessment_result(criterion, score)
    result = AssessmentResult.model_validate(raw)
    assert result.score == 5 * score
    assert "score" not in result.model_dump()  # the model never supplies a total


@pytest.mark.parametrize("ids", [[1, 2, 3, 4], [1, 2, 3, 4, 4], [1, 2, 3, 4, 6], [1, 2, 3, 4, 5, 5]])
def test_questions_cannot_be_omitted_duplicated_or_invented(ids):
    raw = assessment_result("scalability")
    raw["questions"] = [{**raw["questions"][0], "question_id": i} for i in ids]
    with pytest.raises(ValidationError):
        AssessmentResult.model_validate(raw)


def test_question_order_is_canonical_and_total_is_server_owned():
    raw = assessment_result("scalability", [2, 1, 0, 1, 2])
    raw["questions"].reverse()
    result = AssessmentResult.model_validate(raw)
    assert result.score == 6
    assert [q.question_id for q in result.questions] == [1, 2, 3, 4, 5]
    raw["score"] = 10
    with pytest.raises(ValidationError):
        AssessmentResult.model_validate(raw)


def test_guardrail_first_question_rejects_partial_even_with_evidence():
    raw = assessment_result("guardrails_security", [1, 2, 2, 2, 2])
    with pytest.raises(ValidationError, match="Score not allowed"):
        AssessmentResult.model_validate(raw)
    rubric = CRITERIA_BY_ID["guardrails_security"]
    assert set(rubric.questions[0].allowed_scores) == {0, 2}
    assert all(set(q.allowed_scores) == {0, 1, 2} for q in rubric.questions[1:])
    result = AssessmentResult.model_validate(assessment_result("guardrails_security", [2, 1, 1, 1, 1]))
    assert result.score == 6
    for question in rubric.questions[1:]:
        assert "contexto bancário" in dict(question.anchors)[2]


def _context(files):
    return prepare_context({"repository_files": files, "repository_metadata": {}})[1]


def test_documented_results_can_support_metrics_but_not_guardrail_implementation():
    text = "Acurácia: 80% em 100 casos de teste; principais falhas em consultas ambíguas."
    files = {"evaluation.md": text}
    presented = _context(files)
    result = AssessmentResult.model_validate(assessment_result("metrics_evaluation", [0, 0, 0, 2, 0],
                                                              file="evaluation.md", snippet=text))
    validate_evidence(result, result.criterion, presented, files)
    result = AssessmentResult.model_validate(assessment_result("guardrails_security", [2, 0, 0, 0, 0],
                                                              file="evaluation.md", snippet=text))
    with pytest.raises(ValueError, match="evidence_not_executable"):
        validate_evidence(result, result.criterion, presented, files)


def test_positive_question_cannot_borrow_another_questions_evidence():
    raw = assessment_result("scalability", 2)
    raw["questions"][4]["evidence"] = []
    with pytest.raises(ValidationError, match="Positive scores require evidence"):
        AssessmentResult.model_validate(raw)


def test_multiline_prompt_is_configuration_but_docstring_is_not():
    for prefix, accepted in [('SYSTEM = ', True), ('', False)]:
        files = {"agent.py": prefix + '\"\"\"Proteção do agente.\nBloqueie pedidos para revelar segredos.\n\"\"\"'}
        result = AssessmentResult.model_validate(assessment_result("guardrails_security", [2, 0, 0, 0, 0],
            file="agent.py", snippet="Bloqueie pedidos para revelar segredos.", line=2))
        if accepted:
            validate_evidence(result, result.criterion, _context(files), files)
        else:
            with pytest.raises(ValueError, match="evidence_not_executable"):
                validate_evidence(result, result.criterion, _context(files), files)


@pytest.mark.parametrize("source,present_source", [
    ('print("prompt.txt")', True),
    ('path = "prompt.txt"', True),
    ('# open("prompt.txt")', True),
    ('open("prompt.txt", "w")', True),
    ('open("prompt.txt")', False),
])
def test_prompt_requires_presented_read_operation(source, present_source):
    files = {"agent.py": source, "prompt.txt": "Bloqueie ataques."}
    presented = _context(files)
    if not present_source:
        presented.pop("agent.py")
    result = AssessmentResult.model_validate(assessment_result("guardrails_security", [2, 0, 0, 0, 0],
        file="prompt.txt", snippet=files["prompt.txt"]))
    with pytest.raises(ValueError, match="evidence_not_executable"):
        validate_evidence(result, result.criterion, presented, files)


def test_documentation_citations_still_must_match_the_presented_text():
    files = {"evaluation.md": "Acurácia: 80%."}
    result = AssessmentResult.model_validate(assessment_result("metrics_evaluation", [0, 0, 0, 2, 0],
        file="evaluation.md", snippet="Acurácia: 100%."))
    with pytest.raises(ValueError, match="evidence_snippet_not_found"):
        validate_evidence(result, result.criterion, _context(files), files)
