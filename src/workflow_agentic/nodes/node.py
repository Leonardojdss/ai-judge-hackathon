import asyncio
import json
import logging
import time
from datetime import datetime, timezone

from src.adapters.schemas.repository_assessment import Assessment, CriterionOutcome, RepositoryAssessmentResponse
from src.infrastructure.langfuse.callback import trace_node
from src.utils.errors import AssessmentError
from src.utils.prompts import PROMPT_VERSION
from src.workflow_agentic.context import build_context

logger = logging.getLogger(__name__)


def observed(name, operation, settings, telemetry=None):
    async def node(state):
        started = datetime.now(timezone.utc).isoformat()
        clock = time.monotonic()
        status = "completed"
        error_code = None
        files_analyzed = len(state.get("repository_files", {}))
        logger.info(json.dumps({"event": "node_start", "node": name,
                                "execution_id": state["execution_id"],
                                "repository": state["repository_url"], "start_time": started}))
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
                        "model": settings.LLM_MODEL or ("gpt-4.1-mini" if settings.PROVIDER_LLM == "openai" else "unconfigured"),
                        "error": error_code}
            logger.info(json.dumps(metadata))
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
            metadata = await asyncio.to_thread(provider.get_repository_metadata)
            collected["repository_metadata"] = metadata
            tree = await asyncio.to_thread(provider.get_file_tree)
            collected["repository_tree"] = tree
            errors = []
            try:
                readme_path, readme = await asyncio.to_thread(provider.get_readme)
            except AssessmentError as exc:
                if exc.code not in {"NOT_FOUND", "FILE_TOO_LARGE", "BINARY_FILE", "FILE_EXCLUDED", "READ_BUDGET"}:
                    raise
                readme_path, readme = None, None
                errors.append(exc.record("repository_loader"))
            return {"repository_metadata": metadata, "repository_tree": tree,
                    "readme_content": readme, "repository_files": {readme_path: readme} if readme_path else {},
                    "errors": errors}
        except Exception as exc:
            return {**collected, **fatal_update("repository_loader", exc)}
    return node


def repository_context_builder_node(provider, settings):
    async def node(state):
        try:
            return await asyncio.to_thread(build_context, provider, state["repository_tree"],
                                           state["repository_files"], settings)
        except Exception as exc:
            return fatal_update("context_builder", exc)
    return node


def evaluator_node(evaluator, agents):
    async def node(state):
        try:
            evaluated = await agents.evaluate(evaluator.criterion, evaluator.prompt, state)
            outcome = {"execution_status": "completed", **evaluated}
            return {"evaluator_results": {evaluator.criterion: outcome}}
        except Exception as exc:
            error = exc if isinstance(exc, AssessmentError) else AssessmentError("MODEL_ERROR", "Falha ao executar avaliação.")
            return {"evaluator_results": {evaluator.criterion: {"execution_status": "failed", "coverage": getattr(error, "coverage", {})}},
                    "errors": [error.record(evaluator.criterion)]}
    return node


def synthesis_node(evaluators, settings):
    async def node(state):
        outcomes = state.get("evaluator_results", {})
        criteria = []
        errors = []
        coverage = dict(state.get("coverage", {}))
        coverage["evaluators"] = {}
        for evaluator in evaluators:
            outcome = outcomes.get(evaluator.criterion)
            if outcome:
                coverage["evaluators"][evaluator.criterion] = outcome.get("coverage", {})
            if outcome and outcome["execution_status"] == "completed":
                criteria.append(CriterionOutcome(**outcome["result"], execution_status="completed"))
            else:
                missing = outcome is None
                if missing and not state.get("fatal_error"):
                    errors.append({"node": "synthesis", "type": "MISSING_CRITERION", "message": f"Critério ausente: {evaluator.criterion}."})
                criteria.append(CriterionOutcome(criterion=evaluator.criterion,
                                                  execution_status="not_run" if missing else "failed",
                                                  summary="Avaliação não executada." if missing else "Avaliação indisponível por falha; nenhuma nota foi atribuída."))
        complete = all(c.execution_status == "completed" for c in criteria)
        total = sum(c.score for c in criteria) if complete else None
        maximum = 2 * len(evaluators)
        execution_status = "completed" if complete else ("failed" if not any(c.execution_status == "completed" for c in criteria) else "partial")
        summary = " ".join(f"{c.criterion}: {c.summary}" for c in criteria)
        if not complete:
            summary = "Avaliação incompleta; pontuação consolidada indisponível. " + summary
        final = RepositoryAssessmentResponse(
            repository=state.get("repository_metadata", {"url": state["repository_url"], "name": state["repository_url"].removeprefix("https://github.com/"), "commit": None}),
            assessment=Assessment(total_score=total, maximum_score=maximum,
                                  percentage=round(total / maximum * 100, 2) if complete else None,
                                  criteria=criteria),
            summary=summary, execution_status=execution_status,
            errors=state.get("errors", []) + errors,
            metadata={"execution_id": state["execution_id"], "assessment_version": "1.0",
                      "prompt_version": PROMPT_VERSION, "files_analyzed": len(state.get("repository_files", {})),
                      "provider": settings.PROVIDER_LLM,
                      "model": settings.LLM_MODEL or ("gpt-4.1-mini" if settings.PROVIDER_LLM == "openai" else None),
                      "created_at": datetime.now(timezone.utc).isoformat(), "coverage": coverage,
                      "recommendations": list(dict.fromkeys(r for c in criteria for r in c.recommendations))})
        return {"final_result": final.model_dump(mode="json"), "errors": errors}
    return node


def json_output_node(store):
    async def node(state):
        path = await asyncio.to_thread(store.write, state["execution_id"], state["final_result"])
        return {"output_path": path}
    return node
