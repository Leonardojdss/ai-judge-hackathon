from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from conftest import model_assessment_output
from src.infrastructure.provider_factory.connection_models_factory import ConnectionModelFactory
from src.utils.errors import AssessmentError
from src.utils.prompts import PROMPTS

from src.workflow_agentic.agents.agents import Agents

ARCHITECTURE_PROMPT = PROMPTS["software_architecture"]


def model_factory(response):
    structured = SimpleNamespace(ainvoke=AsyncMock())
    if isinstance(response, list):
        structured.ainvoke.side_effect = response
    else:
        structured.ainvoke.return_value = response
    model = SimpleNamespace(with_structured_output=MagicMock(return_value=structured))
    return lambda **kwargs: SimpleNamespace(connection=lambda: model), structured, model


def state():
    return {"repository_metadata": {}, "repository_tree": [{"path": "src/main.py"}], "repository_files": {"src/main.py": "def main():\n    return 42\n"}}


async def test_structured_output_and_concrete_evidence(settings, caplog):
    import json
    import logging
    caplog.set_level(logging.INFO)
    factory, structured, model = model_factory(model_assessment_output("software_architecture", 1))
    result = await Agents(settings, factory).evaluate("software_architecture", ARCHITECTURE_PROMPT, state())
    assert sum(q["score"] for q in result["result"]["questions"]) == 5
    assert result["result"]["criterion"] == "software_architecture"
    assert {q["status"] for q in result["result"]["questions"]} == {"partially_meets"}
    assert result["coverage"]["presented"]["src/main.py"] == [1, 2]
    assert model.with_structured_output.call_args.kwargs["method"] == "json_schema"
    stages = [event["stage"] for record in caplog.records
              if record.levelname == "INFO" and record.message.startswith("{")
              and (event := json.loads(record.message)).get("event") == "assessment_stage"]
    assert stages == ["evaluator_context_started", "evaluator_context_ready",
                      "model_configuration_started", "model_invocation_started",
                      "model_response_received", "evidence_validation_started",
                      "evaluator_completed"]


async def test_invalid_evidence_is_failure_after_correction_attempt(settings):
    invalid = model_assessment_output("software_architecture", 2, snippet="invented()")
    factory, structured, _ = model_factory([invalid] * 3)
    with pytest.raises(AssessmentError) as caught:
        await Agents(settings, factory).evaluate("software_architecture", ARCHITECTURE_PROMPT, state())
    assert caught.value.code == "INVALID_ASSESSMENT"
    assert caught.value.reason == "evidence_snippet_not_found"
    assert caught.value.record("software_architecture")["reason"] == "evidence_snippet_not_found"
    assert caught.value.coverage["presented"]["src/main.py"]
    assert structured.ainvoke.await_count == 3


async def test_invalid_evidence_can_be_corrected_once(settings, caplog):
    import json
    import logging
    caplog.set_level(logging.INFO)
    invalid = model_assessment_output("software_architecture", 2, snippet="invented()")
    corrected = model_assessment_output("software_architecture", 2)
    factory, structured, _ = model_factory([invalid, corrected])

    result = await Agents(settings, factory).evaluate(
        "software_architecture", ARCHITECTURE_PROMPT, state(),
    )

    assert sum(question["score"] for question in result["result"]["questions"]) == 10
    assert structured.ainvoke.await_count == 2
    stages = [event["stage"] for record in caplog.records
              if record.levelname == "INFO" and record.message.startswith("{")
              and (event := json.loads(record.message)).get("event") == "assessment_stage"]
    assert "criterion_retry" in stages


async def test_transient_model_failure_is_retried(settings, caplog):
    factory, structured, _ = model_factory([
        TimeoutError("temporary"),
        model_assessment_output("software_architecture", 0),
    ])

    result = await Agents(settings, factory).evaluate(
        "software_architecture", ARCHITECTURE_PROMPT, state(),
    )

    assert result["result"]["criterion"] == "software_architecture"
    assert structured.ainvoke.await_count == 2


async def test_permanent_model_failure_is_not_retried(settings):
    class AuthenticationFailure(Exception):
        status_code = 401

    factory, structured, _ = model_factory(None)
    structured.ainvoke.side_effect = AuthenticationFailure("invalid key")

    with pytest.raises(AssessmentError) as caught:
        await Agents(settings, factory).evaluate(
            "software_architecture", ARCHITECTURE_PROMPT, state(),
        )

    assert caught.value.code == "MODEL_ERROR"
    assert structured.ainvoke.await_count == 1


@pytest.mark.parametrize("provider,module,name", [("openai", "langchain_openai", "ChatOpenAI"), ("ollama", "langchain_ollama", "ChatOllama"), ("aws_bedrock", "langchain_aws", "ChatBedrockConverse"), ("google_gemini", "langchain_google_genai", "ChatGoogleGenerativeAI")])
def test_factory_adapter_configuration(settings, monkeypatch, provider, module, name):
    from pydantic import SecretStr

    settings.PROVIDER_LLM = provider
    if provider == "google_gemini":
        settings.GEMINI_API_KEY = SecretStr("test-only")
    constructor = MagicMock()
    monkeypatch.setattr(f"{module}.{name}", constructor)
    result = ConnectionModelFactory.create_connection_model(settings=settings).connection()
    assert result is constructor.return_value
    kwargs = constructor.call_args.kwargs
    assert kwargs.get("model", kwargs.get("model_id")) == "test-model"
    for limiter in {"timeout", "max_retries", "max_tokens", "max_output_tokens",
                    "num_ctx", "num_predict", "client_kwargs", "config"}:
        assert limiter not in kwargs


def test_factory_requires_explicit_alternative_model(settings):
    settings.PROVIDER_LLM = "ollama"
    settings.LLM_MODEL = None
    with pytest.raises(ValueError, match="LLM_MODEL"):
        ConnectionModelFactory.create_connection_model(settings=settings)


def test_factory_requires_provider_credential(settings):
    settings.PROVIDER_LLM = "openai"
    settings.OPENAI_API_KEY = None

    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        ConnectionModelFactory.create_connection_model(settings=settings)


def test_langfuse_only_receives_operational_metadata(settings, monkeypatch):
    from src.infrastructure.langfuse.callback import get_langfuse_client, trace_node
    from pydantic import SecretStr
    settings.LANGFUSE_PUBLIC_KEY = "public"
    settings.LANGFUSE_SECRET_KEY = SecretStr("private")
    constructor = MagicMock()
    monkeypatch.setattr("langfuse.Langfuse", constructor)
    client = get_langfuse_client(settings)
    assert constructor.call_args.kwargs["mask"]({"code": "secret source"}) == "[REDACTED]"
    trace_node(client, {"node": "software_architecture", "execution_id": "id"})
    assert "input" not in client.start_as_current_observation.call_args.kwargs


@pytest.mark.parametrize("provider,model_name", [("openai", "gpt-5.4-mini"), ("ollama", "qwen2.5:7b"), ("google_gemini", "gemini-2.5-flash"), ("aws_bedrock", "anthropic.claude-3-haiku-20240307-v1:0")])
def test_installed_adapters_accept_schema_without_network(settings, monkeypatch, provider, model_name):
    from src.adapters.schemas.repository_assessment import ModelAssessmentOutput
    from pydantic import SecretStr
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    monkeypatch.setenv("AWS_EC2_METADATA_DISABLED", "true")
    settings.PROVIDER_LLM = provider
    settings.LLM_MODEL = model_name
    settings.GEMINI_API_KEY = SecretStr("test")
    model = ConnectionModelFactory.create_connection_model(settings=settings).connection()
    structured = model.with_structured_output(ModelAssessmentOutput, method="function_calling" if provider == "aws_bedrock" else "json_schema")
    assert callable(structured.ainvoke)
