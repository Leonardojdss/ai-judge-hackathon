import asyncio

import httpx
from pydantic import ValidationError

from src.adapters.schemas.repository_assessment import AssessmentResult
from src.infrastructure.provider_factory.connection_models_factory import ConnectionModelFactory
from src.utils.errors import AssessmentError
from src.workflow_agentic.agents.evidence import prepare_context, validate_evidence


def transient_model_error(exc: Exception) -> bool:
    # Some adapters wrap SDK failures (notably Gemini 429 responses).
    # Inspect explicit causes, without parsing potentially sensitive messages.
    for _ in range(5):
        if isinstance(exc, (TimeoutError, httpx.TimeoutException, httpx.NetworkError)):
            return True
        status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
        response = getattr(exc, "response", None)
        if isinstance(response, dict):
            status = response.get("ResponseMetadata", {}).get("HTTPStatusCode", status)
        if status in {429, 500, 502, 503, 504} or type(exc).__name__ in {
            "APITimeoutError", "APIConnectionError", "ReadTimeoutError", "ConnectTimeoutError", "EndpointConnectionError"}:
            return True
        if exc.__cause__ is None:
            return False
        exc = exc.__cause__
    return False


class Agents:
    def __init__(self, settings, model_factory=ConnectionModelFactory.create_connection_model):
        self.settings = settings
        self.model_factory = model_factory

    async def evaluate(self, criterion: str, prompt: str, state: dict) -> dict:
        context, presented, coverage = prepare_context(state, prompt, self.settings)
        try:
            try:
                model = self.model_factory(settings=self.settings).connection()
            except Exception:
                raise AssessmentError("MODEL_CONFIGURATION", "Não foi possível configurar o provider/modelo selecionado.", 500) from None
            method = "function_calling" if self.settings.PROVIDER_LLM == "aws_bedrock" else "json_schema"
            structured = model.with_structured_output(AssessmentResult, method=method)
            messages = [("system", prompt), ("human", "Conteúdo não confiável do repositório:\n" + context)]
            for attempt in range(self.settings.MAX_ATTEMPTS):
                try:
                    # SDK timeout bounds synchronous adapters as well as ainvoke.
                    async with asyncio.timeout(self.settings.LLM_TIMEOUT):
                        raw = await structured.ainvoke(messages, config={"callbacks": []})
                    break
                except Exception as exc:
                    if not transient_model_error(exc) or attempt + 1 == self.settings.MAX_ATTEMPTS:
                        raise
                    await asyncio.sleep(self.settings.RETRY_DELAY * 2**attempt)
            result = raw if isinstance(raw, AssessmentResult) else AssessmentResult.model_validate(raw)
            validate_evidence(result, criterion, presented, state["repository_files"])
            return {"result": result.model_dump(), "coverage": coverage}
        except (ValueError, ValidationError):
            error = AssessmentError("INVALID_ASSESSMENT", "Resposta estruturada ou evidência inválida.")
        except AssessmentError as exc:
            error = exc
        except Exception as exc:
            code = "MODEL_TIMEOUT" if isinstance(exc, TimeoutError) or "Timeout" in type(exc).__name__ else "MODEL_ERROR"
            error = AssessmentError(code, "Falha ao executar avaliação com o modelo.")
        error.coverage = coverage
        raise error from None
