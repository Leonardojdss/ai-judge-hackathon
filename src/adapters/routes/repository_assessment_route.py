import asyncio
import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from src.adapters.schemas.repository_assessment import RepositoryAssessmentRequest, RepositoryAssessmentResponse
from src.infrastructure.repository.provider import RepositoryProvider
from src.infrastructure.storage.json_store import JsonResultStore
from src.utils.errors import AssessmentError
from src.utils.logging import log_stage
from src.workflow_agentic.agents.agents import Agents
from src.workflow_agentic.graph import get_compiled_graph

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/V1/repository_assessment/", response_model=RepositoryAssessmentResponse,
             responses={403: {"description": "Repositório não autorizado"}, 404: {"description": "Não encontrado"},
                        500: {"description": "Falha de configuração ou persistência"},
                        502: {"description": "Integração indisponível"}, 504: {"description": "Tempo limite"}})
async def repository_assessment_endpoint(payload: RepositoryAssessmentRequest, request: Request):
    settings = request.app.state.settings
    execution_id = request.state.execution_id
    log_stage(logger, "request_received", "Requisição de avaliação recebida.",
              execution_id=execution_id, repository=payload.repository_url,
              ref_supplied=payload.ref is not None)
    provider = request.app.state.repository_factory(payload.repository_url, payload.ref, settings)
    try:
        try:
            settings.validate_llm_configuration()
        except ValueError:
            raise AssessmentError(
                "MODEL_CONFIGURATION",
                "Configure PROVIDER_LLM, LLM_MODEL e a credencial do provider no .env.",
                500,
            ) from None
        agents = request.app.state.agents_factory(settings)
        store = request.app.state.store_factory(settings.ASSESSMENT_OUTPUT_DIR)
        graph = get_compiled_graph(provider, agents, store, settings, request.app.state.telemetry)
        log_stage(logger, "graph_started", "Fluxo de avaliação iniciado.",
                  execution_id=execution_id, repository=payload.repository_url)
        result = await graph.ainvoke({"repository_url": payload.repository_url, "ref": payload.ref,
                                     "execution_id": execution_id, "errors": [], "evaluator_results": {}})
        log_stage(logger, "graph_completed", "Fluxo de avaliação concluído.",
                  execution_id=execution_id, repository=payload.repository_url,
                  execution_status=result.get("final_result", {}).get("execution_status"),
                  error_code=result.get("fatal_error", {}).get("code"))
        if result.get("fatal_error"):
            error = result["fatal_error"]
            return JSONResponse(status_code=error["http_status"], content={"execution_id": execution_id,
                                "error": {"code": error["code"], "message": error["message"]}})
        return result["final_result"]
    finally:
        try:
            await asyncio.to_thread(provider.close)
            log_stage(logger, "provider_closed", "Cliente do GitHub encerrado.",
                      execution_id=execution_id, repository=payload.repository_url)
        except Exception:
            logger.warning("Falha ao encerrar cliente GitHub; execution_id=%s", execution_id)


def configure_dependencies(app):
    app.state.repository_factory = RepositoryProvider
    app.state.agents_factory = Agents
    app.state.store_factory = JsonResultStore
