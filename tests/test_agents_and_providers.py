from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from conftest import assessment_result
from src.infrastructure.provider_factory.connection_models_factory import ConnectionModelFactory
from src.utils.errors import AssessmentError
from src.utils.prompts import RESPONSIBLE_AI_PROMPT
from src.workflow_agentic.agents.agents import Agents


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


async def test_structured_output_and_concrete_evidence(settings):
    factory, structured, model = model_factory(assessment_result("responsible_ai", 1))
    result = await Agents(settings, factory).evaluate("responsible_ai", RESPONSIBLE_AI_PROMPT, state())
    assert result["result"]["score"] == 1
    assert result["coverage"]["presented"]["src/main.py"] == [1, 2]
    assert model.with_structured_output.call_args.kwargs["method"] == "json_schema"


async def test_invalid_evidence_is_failure_without_retry(settings):
    factory, structured, _ = model_factory(assessment_result("responsible_ai", 2, snippet="invented()"))
    with pytest.raises(AssessmentError) as caught:
        await Agents(settings, factory).evaluate("responsible_ai", RESPONSIBLE_AI_PROMPT, state())
    assert caught.value.code == "INVALID_ASSESSMENT"
    assert caught.value.coverage["presented"]["src/main.py"]
    assert structured.ainvoke.await_count == 1


async def test_transient_model_retry_success(settings):
    factory, structured, _ = model_factory([httpx.ReadTimeout("private details"), assessment_result("responsible_ai")])
    result = await Agents(settings, factory).evaluate("responsible_ai", RESPONSIBLE_AI_PROMPT, state())
    assert structured.ainvoke.await_count == 2
    assert result["result"]["score"] == 0


async def test_wrapped_rate_limit_is_retried_but_auth_is_not(settings):
    class SdkError(Exception):
        def __init__(self, status):
            self.code = status
    wrapped = RuntimeError("SDK wrapper")
    wrapped.__cause__ = SdkError(429)
    factory, structured, _ = model_factory([wrapped, assessment_result("responsible_ai")])
    await Agents(settings, factory).evaluate("responsible_ai", RESPONSIBLE_AI_PROMPT, state())
    assert structured.ainvoke.await_count == 2
    factory, structured, _ = model_factory([SdkError(403)])
    with pytest.raises(AssessmentError):
        await Agents(settings, factory).evaluate("responsible_ai", RESPONSIBLE_AI_PROMPT, state())
    assert structured.ainvoke.await_count == 1


async def test_model_timeout_is_bounded(settings):
    settings.LLM_TIMEOUT = 0.01
    factory, structured, _ = model_factory(None)
    async def slow(*args, **kwargs):
        import asyncio
        await asyncio.sleep(10)
    structured.ainvoke.side_effect = slow
    with pytest.raises(AssessmentError) as caught:
        await Agents(settings, factory).evaluate("responsible_ai", RESPONSIBLE_AI_PROMPT, state())
    assert caught.value.code == "MODEL_TIMEOUT"
    assert structured.ainvoke.await_count == 3


@pytest.mark.parametrize("provider,module,name", [("openai", "langchain_openai", "ChatOpenAI"), ("ollama", "langchain_ollama", "ChatOllama"), ("aws_bedrock", "langchain_aws", "ChatBedrockConverse"), ("google_gemini", "langchain_google_genai", "ChatGoogleGenerativeAI")])
def test_factory_adapter_configuration(settings, monkeypatch, provider, module, name):
    settings.PROVIDER_LLM = provider
    constructor = MagicMock()
    monkeypatch.setattr(f"{module}.{name}", constructor)
    result = ConnectionModelFactory.create_connection_model(settings=settings).connection()
    assert result is constructor.return_value
    kwargs = constructor.call_args.kwargs
    assert kwargs.get("model", kwargs.get("model_id")) == "test-model"
    if provider == "aws_bedrock":
        assert kwargs["config"].retries["total_max_attempts"] == 1
        assert kwargs["config"].read_timeout == 90
    elif provider == "ollama":
        assert kwargs["client_kwargs"]["timeout"] == 90
        assert kwargs["num_ctx"] == settings.MODEL_CONTEXT_TOKENS
    else:
        assert kwargs["max_retries"] == 0
        assert kwargs["timeout"] == 90


def test_factory_requires_explicit_alternative_model(settings):
    settings.PROVIDER_LLM = "ollama"
    settings.LLM_MODEL = None
    with pytest.raises(ValueError, match="LLM_MODEL"):
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
    trace_node(client, {"node": "responsible_ai", "execution_id": "id"})
    assert "input" not in client.start_as_current_observation.call_args.kwargs


@pytest.mark.parametrize("provider,model_name", [("openai", "gpt-4.1-mini"), ("ollama", "qwen2.5:7b"), ("google_gemini", "gemini-2.5-flash"), ("aws_bedrock", "anthropic.claude-3-haiku-20240307-v1:0")])
def test_installed_adapters_accept_schema_without_network(settings, monkeypatch, provider, model_name):
    from src.adapters.schemas.repository_assessment import AssessmentResult
    from pydantic import SecretStr
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    monkeypatch.setenv("AWS_EC2_METADATA_DISABLED", "true")
    settings.PROVIDER_LLM = provider
    settings.LLM_MODEL = model_name
    settings.GEMINI_API_KEY = SecretStr("test")
    model = ConnectionModelFactory.create_connection_model(settings=settings).connection()
    structured = model.with_structured_output(AssessmentResult, method="function_calling" if provider == "aws_bedrock" else "json_schema")
    assert callable(structured.ainvoke)
