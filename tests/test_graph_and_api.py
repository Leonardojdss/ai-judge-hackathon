import json
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from conftest import FakeAgents, FakeRepository, assessment_result, fixture_files
from src.infrastructure.storage.json_store import JsonResultStore
from src.main import create_app
from src.utils.errors import AssessmentError
from src.workflow_agentic.graph import get_compiled_graph
from src.workflow_agentic.registry import EVALUATORS


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
    assert len(agents.finished) == 9
    assert result["execution_status"] == "completed"
    assert result["final_synthesis"]["total_score"] == 0
    assert result["final_synthesis"]["maximum_score"] == 90
    assert len(list(settings.ASSESSMENT_OUTPUT_DIR.glob("*.json"))) == 1
    events = [json.loads(r.message) for r in caplog.records
              if r.levelname == "INFO" and r.message.startswith("{")]
    assert len([e for e in events if e["node"] == "synthesis" and e["event"] == "node_start"]) == 1
    synthesis_index = next(i for i, e in enumerate(events) if e["node"] == "synthesis")
    assert all(any(e["node"] == c and e["event"] == "node_end" for e in events[:synthesis_index]) for c in agents.finished)
    stages = {e["stage"] for e in events if e["event"] == "assessment_stage"}
    assert {"repository_metadata_started", "repository_tree_started", "repository_loaded",
            "context_collection_started", "context_collection_completed", "criterion_started",
            "criterion_completed", "synthesis_started", "synthesis_completed",
            "persistence_started", "persistence_completed"} <= stages


async def test_parallel_errors_are_preserved_with_null_total(settings):
    state = await run_graph(settings, FakeAgents(fail={"guardrails_security", "resilience_availability"}, barrier=True))
    result = state["final_result"]
    assert result["execution_status"] == "partial"
    assert result["final_synthesis"]["total_score"] is None
    assert result["final_synthesis"]["percentage"] is None
    assert len(result["errors"]) == 2
    assert [c["score"] for c in result["criteria"]] == [0, 0, None, None, 0, 0, 0, 0, 0]


async def test_loader_failure_persists_diagnostic_without_evaluating(settings):
    agents = FakeAgents()
    state = await run_graph(settings, agents, FakeRepository(failure=AssessmentError("NOT_FOUND", "Não encontrado.", 404)))
    assert not agents.calls
    assert state["final_result"]["execution_status"] == "failed"
    assert all(c["score"] is None for c in state["final_result"]["criteria"])
    assert json.loads(next(settings.ASSESSMENT_OUTPUT_DIR.glob("*.json")).read_text()) == state["final_result"]


def make_client(settings, provider=None, agents=None):
    app = create_app(settings)
    app.state.repository_factory = lambda *args: provider or FakeRepository()
    app.state.agents_factory = lambda *args: agents or FakeAgents()
    return TestClient(app, raise_server_exceptions=False)


def test_api_json_matches_atomic_artifact(settings, caplog):
    import logging
    caplog.set_level(logging.INFO)
    provider = FakeRepository()
    with make_client(settings, provider) as client:
        response = client.post("/ms_agent_server/V1/repository_assessment/", json={"repository_url": "owner/repo", "ref": "main"})
    assert response.status_code == 200, response.text
    result = response.json()
    assert set(result) == {"execution_id", "repository", "execution_status", "criteria",
                           "final_synthesis", "errors"}
    assert all(set(item) == {"criterion", "score", "maximum_score", "reason"}
               for item in result["criteria"])
    assert result["execution_id"] == response.headers["X-Execution-ID"]
    assert json.loads(next(settings.ASSESSMENT_OUTPUT_DIR.glob("*.json")).read_text()) == result
    assert not list(settings.ASSESSMENT_OUTPUT_DIR.glob("*.tmp"))
    assert provider.closed
    info_events = [json.loads(record.message) for record in caplog.records
                   if record.levelname == "INFO" and record.message.startswith("{")]
    stages = {event["stage"] for event in info_events
              if event.get("event") == "assessment_stage"}
    assert {"request_received", "graph_started", "graph_completed", "provider_closed"} <= stages
    allowed = {"timestamp", "message", "event", "stage", "node", "execution_id",
               "status", "duration_seconds", "attempt", "next_attempt",
               "delay_seconds", "score", "error_code", "error_reason",
               "execution_status", "retry_kind"}
    assert all(set(event) <= allowed for event in info_events)
    assert all(event.get("timestamp") and event.get("message") for event in info_events)


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


def test_api_rejects_incomplete_model_configuration_before_graph(settings):
    provider = FakeRepository()
    settings.OPENAI_API_KEY = None

    with make_client(settings, provider) as client:
        response = client.post(
            "/ms_agent_server/V1/repository_assessment/",
            json={"repository_url": "owner/repo"},
        )

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "MODEL_CONFIGURATION"
    assert provider.reads == []
    assert provider.closed


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
    states = await asyncio.gather(run_graph(settings, FakeAgents()), run_graph(settings, FakeAgents(fail={"guardrails_security"})))
    assert states[0]["final_result"]["errors"] == []
    assert len(states[1]["final_result"]["errors"]) == 1
    assert states[0]["execution_id"] != states[1]["execution_id"]


async def test_synthesis_keeps_individual_scores_and_rounds_percentage(settings):
    class ScoredAgents(FakeAgents):
        async def evaluate(self, criterion, prompt, state):
            return {"result": assessment_result(criterion, [0, 1, 1, 1, 1] if criterion == "guardrails_security" else [2, 2, 2, 2, 2]), "coverage": {}}
    result = (await run_graph(settings, ScoredAgents()))["final_result"]
    assert result["final_synthesis"]["total_score"] == 84
    assert result["final_synthesis"]["percentage"] == 93.33
    assert [c["score"] for c in result["criteria"]] == [10, 10, 10, 4, 10, 10, 10, 10, 10]
    assert "84/90 (93.33%)" in result["final_synthesis"]["summary"]
    assert "Aderência parcial: Guardrails e segurança." in result["final_synthesis"]["summary"]



@pytest.mark.parametrize("maturity", ["low", "medium", "high"])
async def test_controlled_repository_fixtures_flow_through_graph(settings, maturity):
    provider = FakeRepository(fixture_files(maturity))
    state = await run_graph(settings, FakeAgents(), provider)
    assert state["final_result"]["execution_status"] == "completed"
    assert len(state["final_result"]["criteria"]) == 9


async def test_registry_subset_controls_branches_and_maximum(settings):
    evaluators = EVALUATORS[:2]
    agents = FakeAgents()
    graph = get_compiled_graph(FakeRepository(), agents, JsonResultStore(settings.ASSESSMENT_OUTPUT_DIR), settings, evaluators=evaluators)
    state = await graph.ainvoke({"execution_id": str(uuid4()), "repository_url": "https://github.com/owner/repo"})
    assert state["final_result"]["final_synthesis"]["maximum_score"] == 20
    assert [c["criterion"] for c in state["final_result"]["criteria"]] == [e.criterion for e in evaluators]
    assert set(agents.calls) == {e.criterion for e in evaluators}


def test_api_partial_preserves_successes(settings):
    with make_client(settings, agents=FakeAgents(fail={"guardrails_security"})) as client:
        response = client.post("/ms_agent_server/V1/repository_assessment/", json={"repository_url": "owner/repo"})
    assert response.status_code == 200
    assert response.json()["execution_status"] == "partial"
    assert response.json()["final_synthesis"]["total_score"] is None


@pytest.mark.parametrize("invalid_guardrail", [False, True])
def test_nine_real_agents_validate_questions_and_persist_compact_response(settings, invalid_guardrail):
    from types import SimpleNamespace
    from conftest import model_assessment_output
    from src.workflow_agentic.agents.agents import Agents

    calls = []

    class Model:
        def with_structured_output(self, schema, **kwargs):
            self.schema = schema
            return self

        async def ainvoke(self, messages, **kwargs):
            criterion = messages[0][1].split("Critério: ")[1].split(" —")[0]
            calls.append(criterion)
            assert "def main():" in messages[1][1]
            scores = [2, 1, 1, 0, 2] if criterion == "software_architecture" else [2] * 5
            if criterion == "guardrails_security" and invalid_guardrail:
                scores[0] = 1
            return self.schema.model_validate(model_assessment_output(criterion, scores))

    agents = Agents(settings, lambda **kwargs: SimpleNamespace(connection=lambda: Model()))
    with make_client(settings, agents=agents) as client:
        response = client.post("/ms_agent_server/V1/repository_assessment/", json={"repository_url": "owner/repo"})
    assert response.status_code == 200
    result = response.json()
    assert set(calls) == {e.criterion for e in EVALUATORS}
    assert len(calls) == (11 if invalid_guardrail else 9)
    assert result["criteria"][0]["score"] == 6
    assert all(c["maximum_score"] == 10 for c in result["criteria"])
    assert all(set(c) == {"criterion", "score", "maximum_score", "reason"} for c in result["criteria"])
    assert result["final_synthesis"]["maximum_score"] == 90
    if invalid_guardrail:
        assert result["execution_status"] == "partial"
        assert result["criteria"][3]["score"] is None
        assert result["final_synthesis"]["total_score"] is None
        assert result["errors"][0]["reason"] == "structured_output_schema"
    else:
        assert result["execution_status"] == "completed"
        assert result["final_synthesis"]["total_score"] == 86
        assert result["final_synthesis"]["percentage"] == 95.56
        assert result["errors"] == []
    assert json.loads(next(settings.ASSESSMENT_OUTPUT_DIR.glob("*.json")).read_text()) == result


@pytest.mark.parametrize("kind", ["completed", "partial"])
def test_documented_examples_match_current_rubric(kind):
    from pathlib import Path
    from src.adapters.schemas.repository_assessment import RepositoryAssessmentResponse
    result = RepositoryAssessmentResponse.model_validate_json(Path(f"docs/examples/{kind}.json").read_text())
    assert [c.criterion for c in result.criteria] == [e.criterion for e in EVALUATORS]
    assert result.final_synthesis.maximum_score == 90
    assert all(c.maximum_score == 10 for c in result.criteria)
