from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from transition2exec import __version__
from transition2exec.api.models import (
    PatchRequest,
    PatchResponse,
    Transition2ExecRequest,
    Transition2ExecResponse,
)
from transition2exec.config import settings
from transition2exec.patch.service import patch_service
from transition2exec.service import service as transition2exec_service

app = FastAPI(title="transition2exec", version=__version__)


@app.exception_handler(Exception)
async def internal_error_handler(_: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=500, content={"error": "internal_error", "detail": str(exc)})


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": jsonable_encoder(exc.errors())})


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/version")
async def version() -> dict[str, str]:
    return {"service": settings.service_name, "version": __version__, "model": settings.model_name}


@app.post("/transition2exec", response_model=Transition2ExecResponse)
async def transition2exec(request: Transition2ExecRequest) -> Transition2ExecResponse:
    return transition2exec_service.build_plan(request)


@app.post("/patchTaskExecutionOutcomeToAbstractOutcome", response_model=PatchResponse)
async def patch_task_execution_outcome(request: PatchRequest) -> PatchResponse:
    return patch_service.resolve(request)
