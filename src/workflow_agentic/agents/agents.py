import asyncio
import json
import logging

from pydantic import ValidationError

from src.adapters.schemas.repository_assessment import AssessmentResult, ModelAssessmentOutput
from src.infrastructure.provider_factory.connection_models_factory import ConnectionModelFactory
from src.utils.errors import AssessmentError
from src.utils.logging import log_stage
from src.workflow_agentic.agents.evidence import EvidenceValidationError, prepare_context, validate_evidence
from src.workflow_agentic.guardrails.prompt_injection import GUARDRAIL_INSTRUCTIONS


logger = logging.getLogger(__name__)

REPAIR_INSTRUCTION = """A resposta anterior foi rejeitada pelo servidor pelo motivo: {reason}.
Gere novamente a avaliação completa. Retorne exatamente cinco perguntas, com IDs 1
a 5 sem repetição. Respeite as notas permitidas. Para nota positiva, copie como
evidência somente um trecho literal, contíguo e exatamente presente no JSON fornecido,
com caminho e linha inicial corretos. Retorne apenas questions e summary no schema.
"""


def log_guardrail(coverage: dict, criterion: str, execution_id: str | None):
    guardrail = coverage.get("guardrail", {})
    if guardrail.get("reasons"):
        logger.warning(json.dumps({"event": "guardrail_filtered", "node": criterion,
                                   "execution_id": execution_id, "guardrail_version": guardrail["version"],
                                   "removed_lines": guardrail["removed_lines"],
                                   "removed_files": guardrail["removed_files"],
                                   "reasons": guardrail["reasons"]}))


def is_transient_model_error(error: Exception) -> bool:
    """Recognize retryable provider failures without depending on one SDK."""
    current = error
    visited = set()
    while current is not None and id(current) not in visited:
        visited.add(id(current))
        status = getattr(current, "status_code", None)
        if status in {408, 409, 425, 429} or isinstance(status, int) and status >= 500:
            return True
        name = type(current).__name__.lower()
        if any(term in name for term in ("timeout", "connection", "ratelimit", "unavailable")):
            return True
        current = current.__cause__ or current.__context__
    return False


class Agents:
    def __init__(self, settings, model_factory=ConnectionModelFactory.create_connection_model):
        self.settings = settings
        self.model_factory = model_factory

    async def evaluate(self, criterion: str, prompt: str, state: dict) -> dict:
        coverage = {}
        execution_id = state.get("execution_id")
        try:
            log_stage(logger, "evaluator_context_started", "Preparando contexto seguro para o avaliador.",
                      execution_id=execution_id, node=criterion)
            context, presented, coverage = prepare_context(state)
            log_guardrail(coverage, criterion, state.get("execution_id"))
            log_stage(logger, "evaluator_context_ready", "Contexto seguro preparado.",
                      execution_id=execution_id, node=criterion,
                      files_presented=coverage["files_presented"],
                      lines_presented=coverage["lines_presented"],
                      guardrail_removed_lines=coverage["guardrail"]["removed_lines"])
            try:
                log_stage(logger, "model_configuration_started", "Configurando provider e modelo.",
                          execution_id=execution_id, node=criterion,
                          provider=self.settings.PROVIDER_LLM,
                          model=self.settings.model_name)
                model = self.model_factory(settings=self.settings).connection()
            except Exception:
                raise AssessmentError("MODEL_CONFIGURATION", "Não foi possível configurar o provider/modelo selecionado.", 500) from None
            method = "function_calling" if self.settings.PROVIDER_LLM == "aws_bedrock" else "json_schema"
            structured = model.with_structured_output(ModelAssessmentOutput, method=method)
            base_messages = [("system", GUARDRAIL_INSTRUCTIONS + "\n" + prompt), ("human", context)]
            messages = base_messages
            max_attempts = self.settings.CRITERION_MAX_ATTEMPTS
            for attempt in range(1, max_attempts + 1):
                try:
                    log_stage(logger, "model_invocation_started", "Enviando critério ao modelo.",
                              execution_id=execution_id, node=criterion, attempt=attempt,
                              provider=self.settings.PROVIDER_LLM,
                              model=self.settings.model_name)
                    raw = await structured.ainvoke(messages, config={"callbacks": []})
                    log_stage(logger, "model_response_received", "Resposta estruturada recebida do modelo.",
                              execution_id=execution_id, node=criterion, attempt=attempt)
                    model_result = (raw if isinstance(raw, ModelAssessmentOutput)
                                    else ModelAssessmentOutput.model_validate(raw))
                    result = model_result.to_assessment_result(criterion)
                    log_stage(logger, "evidence_validation_started", "Validando perguntas, notas e evidências.",
                              execution_id=execution_id, node=criterion,
                              questions=len(result.questions), attempt=attempt)
                    validate_evidence(result, criterion, presented, state["repository_files"])
                    log_stage(logger, "evaluator_completed", "Critério validado e concluído.",
                              execution_id=execution_id, node=criterion,
                              score=result.score, maximum_score=10, attempt=attempt)
                    return {"result": result.model_dump(), "coverage": coverage}
                except (EvidenceValidationError, ValidationError) as exc:
                    reason = exc.reason if isinstance(exc, EvidenceValidationError) else "structured_output_schema"
                    if attempt == max_attempts:
                        raise
                    delay = self.settings.CRITERION_RETRY_DELAY * 2 ** (attempt - 1)
                    log_stage(logger, "criterion_retry", "Resposta inválida; nova tentativa agendada.",
                              execution_id=execution_id, node=criterion,
                              retry_kind="validation", error_reason=reason,
                              next_attempt=attempt + 1, delay_seconds=delay)
                    messages = base_messages + [("system", REPAIR_INSTRUCTION.format(reason=reason))]
                    if delay:
                        await asyncio.sleep(delay)
                except ValueError:
                    reason = "invalid_assessment_value"
                    if attempt == max_attempts:
                        raise
                    delay = self.settings.CRITERION_RETRY_DELAY * 2 ** (attempt - 1)
                    log_stage(logger, "criterion_retry", "Resposta inválida; nova tentativa agendada.",
                              execution_id=execution_id, node=criterion,
                              retry_kind="validation", error_reason=reason,
                              next_attempt=attempt + 1, delay_seconds=delay)
                    messages = base_messages + [("system", REPAIR_INSTRUCTION.format(reason=reason))]
                    if delay:
                        await asyncio.sleep(delay)
                except Exception as exc:
                    if attempt == max_attempts or not is_transient_model_error(exc):
                        raise
                    delay = self.settings.CRITERION_RETRY_DELAY * 2 ** (attempt - 1)
                    log_stage(logger, "criterion_retry", "Falha transitória do modelo; nova tentativa agendada.",
                              execution_id=execution_id, node=criterion,
                              retry_kind="transient_model_error",
                              error_type=type(exc).__name__, next_attempt=attempt + 1,
                              delay_seconds=delay)
                    messages = base_messages
                    if delay:
                        await asyncio.sleep(delay)
        except EvidenceValidationError as exc:
            log_stage(logger, "assessment_rejected", "Avaliação rejeitada após as tentativas.",
                      execution_id=execution_id, node=criterion, error_reason=exc.reason)
            error = AssessmentError("INVALID_ASSESSMENT", "Resposta estruturada ou evidência inválida.",
                                    reason=exc.reason)
        except ValidationError:
            log_stage(logger, "assessment_rejected", "Avaliação rejeitada após as tentativas.",
                      execution_id=execution_id, node=criterion,
                      error_reason="structured_output_schema")
            error = AssessmentError("INVALID_ASSESSMENT", "Resposta estruturada ou evidência inválida.",
                                    reason="structured_output_schema")
        except ValueError:
            log_stage(logger, "assessment_rejected", "Avaliação rejeitada após as tentativas.",
                      execution_id=execution_id, node=criterion,
                      error_reason="invalid_assessment_value")
            error = AssessmentError("INVALID_ASSESSMENT", "Resposta estruturada ou evidência inválida.",
                                    reason="invalid_assessment_value")
        except AssessmentError as exc:
            error = exc
            if not coverage:
                coverage = getattr(error, "coverage", {})
                log_guardrail(coverage, criterion, state.get("execution_id"))
        except Exception as exc:
            code = "MODEL_TIMEOUT" if isinstance(exc, TimeoutError) or "Timeout" in type(exc).__name__ else "MODEL_ERROR"
            error = AssessmentError(code, "Falha ao executar avaliação com o modelo.")
        error.coverage = coverage
        raise error from None
