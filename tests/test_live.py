"""Opt-in calls; fixture source is data and is never executed."""
import os
from uuid import uuid4

import pytest

from conftest import FakeRepository, fixture_files
from src.config.settings import Settings
from src.infrastructure.storage.json_store import JsonResultStore
from src.workflow_agentic.agents.agents import Agents
from src.workflow_agentic.graph import get_compiled_graph
from src.adapters.schemas.repository_assessment import AssessmentResult
from src.utils.rubric import RUBRIC

pytestmark = [pytest.mark.live, pytest.mark.skipif(os.environ.get("RUN_LIVE_ASSESSMENTS") != "1", reason="External model calls require explicit opt-in")]


@pytest.mark.parametrize("maturity", ["low", "medium", "high"])
async def test_live_classification(maturity, tmp_path):
    settings = Settings(ASSESSMENT_OUTPUT_DIR=tmp_path)
    provider = FakeRepository(fixture_files(maturity))
    graph = get_compiled_graph(provider, Agents(settings), JsonResultStore(tmp_path), settings)
    state = await graph.ainvoke({"execution_id": str(uuid4()), "repository_url": "https://github.com/fixture/" + maturity})
    result = state["final_result"]
    assert result["execution_status"] == "completed", result["errors"]
    assert [c["criterion"] for c in result["criteria"]] == [c.id for c in RUBRIC]
    for criterion in result["criteria"]:
        details = AssessmentResult.model_validate(state["evaluator_results"][criterion["criterion"]]["result"])
        assert criterion["score"] == details.score
        assert len(details.questions) == 5
        assert all(q.evidence for q in details.questions if q.score > 0)
    # These small fixtures have no evaluation dataset/process; a mature provider
    # alone must not earn points for all nine criteria.
    scores = {c["criterion"]: c["score"] for c in result["criteria"]}
    assert scores["metrics_evaluation"] <= 4
    if maturity == "low":
        assert scores["guardrails_security"] == 0
        assert scores["resilience_availability"] <= 2
    if maturity == "high":
        assert scores["software_architecture"] >= 6
        assert scores["resilience_availability"] >= 6
    assert result["final_synthesis"]["total_score"] == sum(scores.values())
