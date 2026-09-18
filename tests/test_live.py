"""Opt-in calls; fixture source is data and is never executed."""
import os
from uuid import uuid4

import pytest

from conftest import FakeRepository, fixture_files
from src.config.settings import Settings
from src.infrastructure.storage.json_store import JsonResultStore
from src.workflow_agentic.agents.agents import Agents
from src.workflow_agentic.graph import get_compiled_graph

pytestmark = [pytest.mark.live, pytest.mark.skipif(os.environ.get("RUN_LIVE_ASSESSMENTS") != "1", reason="External model calls require explicit opt-in")]


@pytest.mark.parametrize("maturity,expected", [("low", [{0}, {0, 1}, {0}]), ("medium", [{1}, {1}, {1}]), ("high", [{2}, {2}, {2}])])
async def test_live_classification(maturity, expected, tmp_path):
    settings = Settings(ASSESSMENT_OUTPUT_DIR=tmp_path)
    provider = FakeRepository(fixture_files(maturity))
    graph = get_compiled_graph(provider, Agents(settings), JsonResultStore(tmp_path), settings)
    state = await graph.ainvoke({"execution_id": str(uuid4()), "repository_url": "https://github.com/fixture/" + maturity})
    result = state["final_result"]
    assert result["execution_status"] == "completed", result["errors"]
    for criterion, acceptable in zip(result["assessment"]["criteria"], expected):
        assert criterion["score"] in acceptable, criterion
