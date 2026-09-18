import asyncio
import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from src.adapters.schemas.repository_assessment import RepositoryAssessmentRequest, RepositoryAssessmentResponse
from src.infrastructure.repository.provider import RepositoryProvider
from src.infrastructure.storage.json_store import JsonResultStore
from src.workflow_agentic.agents.agents import Agents
from src.workflow_agentic.graph import get_compiled_graph

router = APIRouter()


@router.post("/V1/repository_assessment/", response_model=RepositoryAssessmentResponse,
             responses={403: {"description": "Repositório não autorizado"}, 404: {"description": "Não encontrado"},
                        500: {"description": "Falha de configuração ou persistência"},
                        502: {"description": "Integração indisponível"}, 504: {"description": "Tempo limite"}})
async def repository_assessment_endpoint(payload: RepositoryAssessmentRequest, request: Request):
    settings = request.app.state.settings
    execution_id = request.state.execution_id
    provider = request.app.state.repository_factory(payload.repository_url, payload.ref, settings)
    try:
        agents = request.app.state.agents_factory(settings)
        store = request.app.state.store_factory(settings.ASSESSMENT_OUTPUT_DIR)
        graph = get_compiled_graph(provider, agents, store, settings, request.app.state.telemetry)
        result = await graph.ainvoke({"repository_url": payload.repository_url, "ref": payload.ref,
                                     "execution_id": execution_id, "errors": [], "evaluator_results": {}})
        if result.get("fatal_error"):
            error = result["fatal_error"]
            return JSONResponse(status_code=error["http_status"], content={"execution_id": execution_id,
                                "error": {"code": error["code"], "message": error["message"]}})
        return result["final_result"]
    finally:
        try:
            await asyncio.to_thread(provider.close)
        except Exception:
            logging.getLogger(__name__).warning("Falha ao encerrar cliente GitHub; execution_id=%s", execution_id)


def configure_dependencies(app):
    app.state.repository_factory = RepositoryProvider
    app.state.agents_factory = Agents
    app.state.store_factory = JsonResultStore
