import asyncio
import logging
import time
from datetime import datetime, timezone

from pydantic import ValidationError

from src.adapters.schemas.repository_assessment import AssessmentResult, CriterionScore, FinalSynthesis, RepositoryAssessmentResponse
from src.infrastructure.langfuse.callback import trace_node
from src.utils.errors import AssessmentError
from src.utils.logging import log_info, log_stage
from src.utils.rubric import CRITERIA_BY_ID, RUBRIC_VERSION
from src.utils.prompts import PROMPT_VERSION
from src.workflow_agentic.guardrails.prompt_injection import GUARDRAIL_VERSION
from src.workflow_agentic.context import build_context

logger = logging.getLogger(__name__)


def _criterion_label(criterion: str) -> str:
    return CRITERIA_BY_ID[criterion].title


def _join_labels(labels: list[str]) -> str:
    if len(labels) < 2:
        return "".join(labels)
    return ", ".join(labels[:-1]) + " e " + labels[-1]


def final_summary(criteria: list[CriterionScore], complete: bool,
                  total: int | None, maximum: int, percentage: float | None) -> str:
    if not complete:
        completed = [f"{_criterion_label(item.criterion)} ({item.score}/{item.maximum_score})"
                     for item in criteria if item.score is not None]
        unavailable = [_criterion_label(item.criterion) for item in criteria if item.score is None]
        parts = ["Avaliação incompleta; pontuação consolidada indisponível."]
        if completed:
            parts.append("Critérios concluídos: " + _join_labels(completed) + ".")
        if unavailable:
            parts.append("Critérios indisponíveis: " + _join_labels(unavailable) + ".")
        return " ".join(parts)

    parts = [f"Pontuação final: {total}/{maximum} ({percentage:.2f}%)."]
    descriptions = (("Atende plenamente", lambda item: item.score == item.maximum_score),
                    ("Aderência parcial", lambda item: 0 < item.score < item.maximum_score),
                    ("Sem evidência suficiente", lambda item: item.score == 0))
    for description, matches in descriptions:
        labels = [_criterion_label(item.criterion) for item in criteria if matches(item)]
        if labels:
            parts.append(f"{description}: {_join_labels(labels)}.")
    return " ".join(parts)


def observed(name, operation, settings, telemetry=None):
    async def node(state):
        started = datetime.now(timezone.utc).isoformat()
        clock = time.monotonic()
        status = "completed"
        error_code = None
        files_analyzed = len(state.get("repository_files", {}))
        log_info(logger, "node_start", "Etapa iniciada.",
                 execution_id=state["execution_id"], node=name)
        try:
            update = await operation(state)
            files_analyzed = len(update.get("repository_files", state.get("repository_files", {})))
            if update.get("fatal_error") or update.get("errors"):
                failed_evaluator = any(r.get("execution_status") == "failed" for r in update.get("evaluator_results", {}).values())
                status = "failed" if update.get("fatal_error") or failed_evaluator else "warning"
                error_code = update.get("errors", [{}])[-1].get("type")
            return update
        except Exception as exc:
            status = "failed"
            error_code = exc.code if isinstance(exc, AssessmentError) else "INTERNAL_ERROR"
            raise
        finally:
            metadata = {"event": "node_end", "repository": state["repository_url"],
                        "execution_id": state["execution_id"], "node": name,
                        "start_time": started, "end_time": datetime.now(timezone.utc).isoformat(),
                        "duration": round(time.monotonic() - clock, 4), "status": status,
                        "files_analyzed": files_analyzed,
                        "provider": settings.PROVIDER_LLM,
                        "rubric_version": RUBRIC_VERSION, "prompt_version": PROMPT_VERSION,
                        "guardrail_version": GUARDRAIL_VERSION,
                        "model": settings.LLM_MODEL or "unconfigured",
                        "error": error_code}
            log_info(logger, "node_end",
                     "Etapa concluída." if status == "completed" else "Etapa finalizada com ocorrência.",
                     execution_id=state["execution_id"], node=name, status=status,
                     duration_seconds=metadata["duration"], error_code=error_code)
            trace_node(telemetry, metadata)
    return node


def fatal_update(node: str, exc: Exception) -> dict:
    error = exc if isinstance(exc, AssessmentError) else AssessmentError("INTERNAL_ERROR", "Falha interna na preparação da avaliação.", 500)
    return {"errors": [error.record(node)], "fatal_error": {
        "code": error.code, "message": error.message, "http_status": error.http_status}}


def repository_loader_node(provider):
    async def node(state):
        collected = {}
        try:
            log_stage(logger, "repository_metadata_started", "Resolvendo repositório, referência e commit.",
                      execution_id=state["execution_id"], node="repository_loader",
                      repository=state["repository_url"])
            metadata = await asyncio.to_thread(provider.get_repository_metadata)
            collected["repository_metadata"] = metadata
            log_stage(logger, "repository_tree_started", "Listando árvore do commit resolvido.",
                      execution_id=state["execution_id"], node="repository_loader",
                      repository=state["repository_url"], commit=metadata.get("commit"))
            tree = await asyncio.to_thread(provider.get_file_tree)
            collected["repository_tree"] = tree
            errors = []
            try:
                readme_path, readme = await asyncio.to_thread(provider.get_readme)
            except AssessmentError as exc:
                if exc.code not in {"NOT_FOUND", "BINARY_FILE", "FILE_EXCLUDED"}:
                    raise
                readme_path, readme = None, None
                errors.append(exc.record("repository_loader"))
            log_stage(logger, "repository_loaded", "Metadados e árvore do repositório carregados.",
                      execution_id=state["execution_id"], node="repository_loader",
                      repository=state["repository_url"], commit=metadata.get("commit"),
                      files_discovered=len(tree), readme_found=readme_path is not None,
                      tree_truncated=provider.tree_truncated)
            return {"repository_metadata": metadata, "repository_tree": tree,
                    "readme_content": readme, "repository_files": {readme_path: readme} if readme_path else {},
                    "errors": errors}
        except Exception as exc:
            return {**collected, **fatal_update("repository_loader", exc)}
    return node


def repository_context_builder_node(provider):
    async def node(state):
        try:
            log_stage(logger, "context_collection_started", "Lendo arquivos textuais elegíveis.",
                      execution_id=state["execution_id"], node="context_builder",
                      repository=state["repository_url"],
                      files_discovered=len(state["repository_tree"]))
            result = await asyncio.to_thread(build_context, provider, state["repository_tree"],
                                             state["repository_files"])
            coverage = result["coverage"]
            log_stage(logger, "context_collection_completed", "Contexto do repositório coletado.",
                      execution_id=state["execution_id"], node="context_builder",
                      repository=state["repository_url"],
                      files_read=coverage["files_read"], bytes_read=coverage["bytes_read"],
                      files_omitted=len(coverage["omitted"]), read_errors=len(result["errors"]))
            return result
        except Exception as exc:
            return fatal_update("context_builder", exc)
    return node


def evaluator_node(evaluator, agents):
    async def node(state):
        try:
            log_stage(logger, "criterion_started", "Avaliação do critério iniciada.",
                      execution_id=state["execution_id"], node=evaluator.criterion,
                      repository=state["repository_url"], maximum_score=evaluator.maximum_score)
            evaluated = await agents.evaluate(evaluator.criterion, evaluator.prompt, state)
            result = AssessmentResult.model_validate(evaluated["result"])
            if result.criterion != evaluator.criterion:
                raise AssessmentError("INVALID_ASSESSMENT", "Critério retornado não corresponde ao solicitado.", reason="criterion_mismatch")
            evaluated["result"] = result.model_dump()
            log_stage(logger, "criterion_completed", "Avaliação do critério concluída.",
                      execution_id=state["execution_id"], node=evaluator.criterion,
                      repository=state["repository_url"], score=result.score,
                      maximum_score=evaluator.maximum_score)
            outcome = {"execution_status": "completed", **evaluated}
            return {"evaluator_results": {evaluator.criterion: outcome}}
        except Exception as exc:
            if isinstance(exc, AssessmentError):
                error = exc
            elif isinstance(exc, ValidationError):
                error = AssessmentError("INVALID_ASSESSMENT", "Respostas às perguntas inválidas.", reason="structured_output_schema")
            else:
                error = AssessmentError("MODEL_ERROR", "Falha ao executar avaliação.")
            log_stage(logger, "criterion_failed", "Avaliação do critério falhou.",
                      execution_id=state["execution_id"], node=evaluator.criterion,
                      repository=state["repository_url"], error_code=error.code,
                      error_reason=error.reason)
            return {"evaluator_results": {evaluator.criterion: {"execution_status": "failed", "coverage": getattr(error, "coverage", {})}},
                    "errors": [error.record(evaluator.criterion)]}
    return node


def synthesis_node(evaluators):
    async def node(state):
        log_stage(logger, "synthesis_started", "Consolidando resultados dos critérios.",
                  execution_id=state["execution_id"], node="synthesis",
                  repository=state["repository_url"], expected_criteria=len(evaluators),
                  received_criteria=len(state.get("evaluator_results", {})))
        outcomes = state.get("evaluator_results", {})
        criteria = []
        errors = []
        for evaluator in evaluators:
            outcome = outcomes.get(evaluator.criterion)
            if outcome and outcome["execution_status"] == "completed":
                result = AssessmentResult.model_validate(outcome["result"])
                criteria.append(CriterionScore(criterion=evaluator.criterion,
                                               score=result.score, maximum_score=evaluator.maximum_score,
                                               reason=result.summary))
            else:
                missing = outcome is None
                if missing and not state.get("fatal_error"):
                    errors.append({"node": "synthesis", "type": "MISSING_CRITERION", "message": f"Critério ausente: {evaluator.criterion}."})
                reason = ("Avaliação não executada porque a aquisição do repositório falhou."
                          if missing and state.get("fatal_error") else
                          "Avaliação não executada." if missing else
                          "Avaliação indisponível por falha; nenhuma nota foi atribuída.")
                criteria.append(CriterionScore(criterion=evaluator.criterion, score=None, reason=reason))
        complete = all(c.score is not None for c in criteria)
        total = sum(c.score for c in criteria) if complete else None
        maximum = sum(evaluator.maximum_score for evaluator in evaluators)
        percentage = round(total / maximum * 100, 2) if complete else None
        execution_status = "completed" if complete else ("failed" if not any(c.score is not None for c in criteria) else "partial")
        summary = final_summary(criteria, complete, total, maximum, percentage)
        if any(outcome.get("coverage", {}).get("guardrail", {}).get("reasons") for outcome in outcomes.values()):
            summary += " A cobertura foi reduzida pelo guardrail; trechos suspeitos não foram usados como evidência."
        final = RepositoryAssessmentResponse(
            execution_id=state["execution_id"],
            repository=state.get("repository_metadata", {"url": state["repository_url"], "name": state["repository_url"].removeprefix("https://github.com/"), "commit": None}),
            execution_status=execution_status, criteria=criteria,
            final_synthesis=FinalSynthesis(total_score=total, maximum_score=maximum,
                                           percentage=percentage,
                                           summary=summary),
            errors=state.get("errors", []) + errors)
        log_stage(logger, "synthesis_completed", "Síntese final concluída.",
                  execution_id=state["execution_id"], node="synthesis",
                  repository=state["repository_url"], execution_status=execution_status,
                  completed_criteria=sum(c.score is not None for c in criteria),
                  failed_criteria=sum(c.score is None for c in criteria),
                  total_score=total, maximum_score=maximum, percentage=percentage)
        return {"final_result": final.model_dump(mode="json"), "errors": errors}
    return node


def json_output_node(store):
    async def node(state):
        log_stage(logger, "persistence_started", "Persistindo resultado da avaliação.",
                  execution_id=state["execution_id"], node="json_output",
                  repository=state["repository_url"])
        path = await asyncio.to_thread(store.write, state["execution_id"], state["final_result"])
        log_stage(logger, "persistence_completed", "Resultado persistido com escrita atômica.",
                  execution_id=state["execution_id"], node="json_output",
                  repository=state["repository_url"])
        return {"output_path": path}
    return node
