import logging
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from src.adapters.routes.repository_assessment_route import configure_dependencies, router
from src.config.settings import Settings
from src.infrastructure.langfuse.callback import get_langfuse_client
from src.utils.errors import AssessmentError


def create_app(settings: Settings | None = None) -> FastAPI:
    configuration = settings or Settings()
    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    logging.getLogger("src").setLevel(logging.INFO)

    @asynccontextmanager
    async def lifespan(app):
        app.state.telemetry = get_langfuse_client(configuration)
        yield
        if app.state.telemetry:
            try:
                app.state.telemetry.flush()
            except Exception:
                logging.getLogger(__name__).warning("Falha ao finalizar telemetria.")

    application = FastAPI(title="Repository Assessment API", version="1.0", lifespan=lifespan)
    application.state.settings = configuration
    application.state.telemetry = None
    configure_dependencies(application)
    application.include_router(router, prefix="/ms_agent_server", tags=["repository assessment"])

    @application.middleware("http")
    async def execution_id(request: Request, call_next):
        request.state.execution_id = str(uuid4())
        response = await call_next(request)
        response.headers["X-Execution-ID"] = request.state.execution_id
        return response

    @application.exception_handler(RequestValidationError)
    async def invalid_request(request, exc):
        return JSONResponse(status_code=422, content={"execution_id": request.state.execution_id,
                            "error": {"code": "INVALID_REQUEST", "message": "Entrada inválida. Consulte o contrato em /docs."}})

    @application.exception_handler(AssessmentError)
    async def assessment_error(request, exc):
        return JSONResponse(status_code=exc.http_status, content={"execution_id": request.state.execution_id,
                            "error": {"code": exc.code, "message": exc.message}})

    @application.exception_handler(Exception)
    async def unexpected_error(request, exc):
        logging.getLogger(__name__).error("Falha interna; execution_id=%s", request.state.execution_id)
        return JSONResponse(status_code=500, content={"execution_id": request.state.execution_id,
                            "error": {"code": "INTERNAL_ERROR", "message": "Falha interna ao executar a avaliação."}})

    @application.get("/health", tags=["health"])
    async def health():
        return {"status": "ok"}

    return application


app = create_app()

if __name__ == "__main__":
    import uvicorn

    logging.basicConfig(level=logging.INFO)
    uvicorn.run("src.main:app", host="127.0.0.1", port=8000)
