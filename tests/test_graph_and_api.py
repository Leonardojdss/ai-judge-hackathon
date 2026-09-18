import json
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from conftest import FakeAgents, FakeRepository, assessment_result, fixture_files
from src.infrastructure.storage.json_store import JsonResultStore
from src.main import create_app
from src.utils.errors import AssessmentError
from src.workflow_agentic.graph import get_compiled_graph


async def run_graph(settings, agents, provider=None):
    provider = provider or FakeRepository()
    graph = get_compiled_graph(provider, agents, JsonResultStore(settings.ASSESSMENT_OUTPUT_DIR), settings)
    return await graph.ainvoke({"execution_id": str(uuid4()), "repository_url": "https://github.com/owner/repo", "errors": [], "evaluator_results": {}})


async def test_real_graph_parallel_barrier_synthesis_once(settings, caplog):
    import logging
    caplog.set_level(logging.INFO)
    agents = FakeAgents(barrier=True)
    state = await run_graph(settings, agents)
    result = state["final_result"]
    assert len(agents.finished) == 3
    assert result["execution_status"] == "completed"
    assert result["assessment"]["total_score"] == 0
    assert result["assessment"]["maximum_score"] == 6
    assert len(list(settings.ASSESSMENT_OUTPUT_DIR.glob("*.json"))) == 1
    events = [json.loads(r.message) for r in caplog.records if r.message.startswith('{"event"')]
    assert len([e for e in events if e["node"] == "synthesis" and e["event"] == "node_start"]) == 1
    synthesis_index = next(i for i, e in enumerate(events) if e["node"] == "synthesis")
    assert all(any(e["node"] == c and e["event"] == "node_end" for e in events[:synthesis_index]) for c in agents.finished)


async def test_parallel_errors_are_preserved_with_null_total(settings):
    state = await run_graph(settings, FakeAgents(fail={"responsible_ai", "engineering_mechanisms"}, barrier=True))
    result = state["final_result"]
    assert result["execution_status"] == "partial"
    assert result["assessment"]["total_score"] is None
    assert result["assessment"]["percentage"] is None
    assert len(result["errors"]) == 2
    assert [c["score"] for c in result["assessment"]["criteria"]] == [None, 0, None]


async def test_loader_failure_persists_diagnostic_without_evaluating(settings):
    agents = FakeAgents()
    state = await run_graph(settings, agents, FakeRepository(failure=AssessmentError("NOT_FOUND", "Não encontrado.", 404)))
    assert not agents.calls
    assert state["final_result"]["execution_status"] == "failed"
    assert all(c["execution_status"] == "not_run" for c in state["final_result"]["assessment"]["criteria"])
    assert json.loads(next(settings.ASSESSMENT_OUTPUT_DIR.glob("*.json")).read_text()) == state["final_result"]


def make_client(settings, provider=None, agents=None):
    app = create_app(settings)
    app.state.repository_factory = lambda *args: provider or FakeRepository()
    app.state.agents_factory = lambda *args: agents or FakeAgents()
    return TestClient(app, raise_server_exceptions=False)


def test_api_json_matches_atomic_artifact(settings):
    provider = FakeRepository()
    with make_client(settings, provider) as client:
        response = client.post("/ms_agent_server/V1/repository_assessment/", json={"repository_url": "owner/repo", "ref": "main"})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["metadata"]["execution_id"] == response.headers["X-Execution-ID"]
    assert json.loads(next(settings.ASSESSMENT_OUTPUT_DIR.glob("*.json")).read_text()) == result
    assert not list(settings.ASSESSMENT_OUTPUT_DIR.glob("*.tmp"))
    assert provider.closed


@pytest.mark.parametrize("code,status", [("REPOSITORY_AUTH", 403), ("NOT_FOUND", 404), ("REPOSITORY_UNAVAILABLE", 502), ("REPOSITORY_TIMEOUT", 504)])
def test_api_acquisition_errors_have_id_and_persisted_diagnostic(settings, code, status):
    with make_client(settings, FakeRepository(failure=AssessmentError(code, "Falha controlada.", status))) as client:
        response = client.post("/ms_agent_server/V1/repository_assessment/", json={"repository_url": "owner/repo"})
    assert response.status_code == status
    assert response.json()["error"]["code"] == code
    assert response.json()["execution_id"]
    assert len(list(settings.ASSESSMENT_OUTPUT_DIR.glob("*.json"))) == 1


def test_api_invalid_input_is_sanitized(settings):
    with make_client(settings) as client:
        response = client.post("/ms_agent_server/V1/repository_assessment/", json={"repository_url": "https://secret:password@github.com/a/b"})
    assert response.status_code == 422
    assert "password" not in response.text


def test_persistence_failure_returns_500_without_success(settings, monkeypatch):
    def fail(*args):
        raise OSError("private filesystem details")
    monkeypatch.setattr("src.infrastructure.storage.json_store.os.replace", fail)
    with make_client(settings) as client:
        response = client.post("/ms_agent_server/V1/repository_assessment/", json={"repository_url": "owner/repo"})
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "PERSISTENCE_ERROR"
    assert "private filesystem" not in response.text
    assert not list(settings.ASSESSMENT_OUTPUT_DIR.iterdir())


async def test_state_isolation_between_runs(settings):
    import asyncio
    states = await asyncio.gather(run_graph(settings, FakeAgents()), run_graph(settings, FakeAgents(fail={"responsible_ai"})))
    assert states[0]["final_result"]["errors"] == []
    assert len(states[1]["final_result"]["errors"]) == 1
    assert states[0]["execution_id"] != states[1]["execution_id"]


async def test_synthesis_keeps_individual_scores_and_rounds_percentage(settings):
    class ScoredAgents(FakeAgents):
        async def evaluate(self, criterion, prompt, state):
            return {"result": assessment_result(criterion, 1 if criterion == "responsible_ai" else 2), "coverage": {}}
    result = (await run_graph(settings, ScoredAgents()))["final_result"]
    assert result["assessment"]["total_score"] == 5
    assert result["assessment"]["percentage"] == 83.33
    assert [c["score"] for c in result["assessment"]["criteria"]] == [1, 2, 2]
    assert result["metadata"]["recommendations"] == ["Ampliar testes."]


@pytest.mark.parametrize("maturity", ["low", "medium", "high"])
async def test_controlled_repository_fixtures_flow_through_graph(settings, maturity):
    provider = FakeRepository(fixture_files(maturity))
    state = await run_graph(settings, FakeAgents(), provider)
    assert state["final_result"]["execution_status"] == "completed"
    assert state["final_result"]["metadata"]["files_analyzed"] == len(provider.files)


async def test_new_evaluator_uses_registry_without_graph_changes(settings):
    from src.workflow_agentic.registry import EVALUATORS, Evaluator
    evaluators = (*EVALUATORS, Evaluator("testing", "Evaluate tests"))
    graph = get_compiled_graph(FakeRepository(), FakeAgents(), JsonResultStore(settings.ASSESSMENT_OUTPUT_DIR), settings, evaluators=evaluators)
    state = await graph.ainvoke({"execution_id": str(uuid4()), "repository_url": "https://github.com/owner/repo"})
    assert state["final_result"]["assessment"]["maximum_score"] == 8
    assert len(state["final_result"]["assessment"]["criteria"]) == 4


def test_api_partial_preserves_successes(settings):
    with make_client(settings, agents=FakeAgents(fail={"responsible_ai"})) as client:
        response = client.post("/ms_agent_server/V1/repository_assessment/", json={"repository_url": "owner/repo"})
    assert response.status_code == 200
    assert response.json()["execution_status"] == "partial"
    assert response.json()["assessment"]["total_score"] is None
