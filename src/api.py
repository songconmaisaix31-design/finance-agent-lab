from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError as FastApiRequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .pipeline_adapter import (
    PIPELINE_STAGES,
    AdapterRunRequest,
    StageAlreadyRunningError,
    StageContractError,
    create_run,
    execute_stage,
    get_artifacts,
    get_run,
)
from .pipeline_service import (
    InputValidationError,
    PathSafetyError,
    PipelineError,
    RequestValidationError,
)


class PipelineStage(str, Enum):
    intake = "intake"
    normalize = "normalize"
    calculate = "calculate"
    reconcile = "reconcile"
    report = "report"


class RunCreateRequest(BaseModel):
    city_id: str = Field(..., examples=["guan"])
    input_path: str
    output_root: str
    mode: Literal["execute", "audit"] = "execute"
    unknown_type_policy: Literal["error", "report_only"] = "error"
    run_id: str | None = None


class ErrorResponse(BaseModel):
    error_code: str
    message: str
    status_code: int
    run_id: str | None = None
    stage: str | None = None
    retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


class StageResultResponse(BaseModel):
    schema_version: str
    run_id: str
    stage: PipelineStage
    status: Literal["pending", "running", "success", "warning", "failed", "rejected", "skipped"]
    message: str | None = None
    metrics: dict[str, str] = Field(default_factory=dict)
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    started_at: str | None = None
    ended_at: str | None = None
    duration_ms: int = 0
    attempt_id: str | None = None
    attempt: int = 0
    contract_version: str | None = None
    error: dict[str, str] | None = None
    result: dict[str, Any] | None = None


class RunStatusResponse(BaseModel):
    schema_version: str
    run_id: str
    city_id: str
    status: str
    current_stage: str | None = None
    mode: str
    created_at: str
    updated_at: str
    stages: dict[str, StageResultResponse]
    run_dir: str | None = None
    summary_path: str | None = None
    manifest_path: str | None = None
    artifacts: list[dict[str, Any]] = Field(default_factory=list)


class RunCreatedResponse(RunStatusResponse):
    pass


class ArtifactListResponse(BaseModel):
    schema_version: str
    run_id: str
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    manifest_path: str | None = None


app = FastAPI(
    title="Finance Pipeline Adapter",
    version="1.0.0",
    description="HTTP adapter for n8n orchestration. Financial calculations remain in the Python service layer.",
)


@app.exception_handler(StageContractError)
async def stage_error_handler(request: Request, exc: StageContractError):
    status_code = 404 if str(exc).startswith("Run not found:") else 409
    retryable = isinstance(exc, StageAlreadyRunningError)
    return _error_response(exc.error_code, str(exc), status_code, request, retryable=retryable, details=getattr(exc, "details", {}))


@app.exception_handler(PipelineError)
async def pipeline_error_handler(request: Request, exc: PipelineError):
    return _error_response(getattr(exc, "error_code", "PIPELINE_FAILED"), str(exc), 400, request)


@app.exception_handler(InputValidationError)
async def input_error_handler(request: Request, exc: InputValidationError):
    return _error_response(exc.error_code, str(exc), 400, request)


@app.exception_handler(PathSafetyError)
async def path_error_handler(request: Request, exc: PathSafetyError):
    return _error_response(exc.error_code, str(exc), 400, request)


@app.exception_handler(RequestValidationError)
async def request_error_handler(request: Request, exc: RequestValidationError):
    return _error_response(getattr(exc, "error_code", "INVALID_REQUEST"), str(exc), 422, request)


@app.exception_handler(FastApiRequestValidationError)
async def fastapi_validation_error_handler(request: Request, exc: FastApiRequestValidationError):
    return _error_response("REQUEST_VALIDATION_FAILED", "Request validation failed", 422, request)


@app.exception_handler(HTTPException)
async def http_error_handler(request: Request, exc: HTTPException):
    detail = exc.detail if isinstance(exc.detail, dict) else {}
    return _error_response(
        str(detail.get("error_code", "HTTP_ERROR")),
        str(detail.get("message", exc.detail)),
        exc.status_code,
        request,
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    return _error_response("INTERNAL_SERVER_ERROR", "Internal server error", 500, request)


@app.get("/api/v1/health", response_model=HealthResponse, responses={500: {"model": ErrorResponse}})
@app.get("/health", response_model=HealthResponse, responses={500: {"model": ErrorResponse}}, deprecated=True)
def health():
    return {"status": "ok", "service": "finance-pipeline-api", "version": app.version}


@app.post(
    "/api/v1/runs",
    response_model=RunCreatedResponse,
    responses={400: {"model": ErrorResponse}, 409: {"model": ErrorResponse}, 422: {"model": ErrorResponse, "description": "Unprocessable Entity"}, 500: {"model": ErrorResponse}},
)
@app.post(
    "/runs",
    response_model=RunCreatedResponse,
    responses={400: {"model": ErrorResponse}, 409: {"model": ErrorResponse}, 422: {"model": ErrorResponse, "description": "Unprocessable Entity"}, 500: {"model": ErrorResponse}},
    deprecated=True,
)
def create_pipeline_run(payload: RunCreateRequest):
    return create_run(
        AdapterRunRequest(
            city_id=payload.city_id,
            input_path=Path(payload.input_path),
            output_root=Path(payload.output_root),
            mode=payload.mode,
            unknown_type_policy=payload.unknown_type_policy,
            run_id=payload.run_id,
        )
    )


@app.get(
    "/api/v1/runs/{run_id}",
    response_model=RunStatusResponse,
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
@app.get(
    "/runs/{run_id}",
    response_model=RunStatusResponse,
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    deprecated=True,
)
def read_pipeline_run(run_id: str):
    return get_run(run_id)


@app.post(
    "/api/v1/runs/{run_id}/stages/{stage}",
    response_model=StageResultResponse,
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}, 422: {"model": ErrorResponse, "description": "Unprocessable Entity"}, 500: {"model": ErrorResponse}},
)
@app.post(
    "/runs/{run_id}/stages/{stage}",
    response_model=StageResultResponse,
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}, 422: {"model": ErrorResponse, "description": "Unprocessable Entity"}, 500: {"model": ErrorResponse}},
    deprecated=True,
)
def execute_pipeline_stage(run_id: str, stage: PipelineStage):
    if stage.value not in PIPELINE_STAGES:
        raise HTTPException(status_code=404, detail={"error_code": "UNKNOWN_STAGE", "message": stage.value})
    return execute_stage(run_id, stage.value)


@app.get(
    "/api/v1/runs/{run_id}/artifacts",
    response_model=ArtifactListResponse,
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
@app.get(
    "/runs/{run_id}/artifacts",
    response_model=ArtifactListResponse,
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    deprecated=True,
)
def read_pipeline_artifacts(run_id: str):
    return get_artifacts(run_id)


def _error_response(error_code: str, message: str, status_code: int, request: Request, *, retryable: bool = False, details: dict[str, Any] | None = None) -> JSONResponse:
    parts = request.url.path.strip("/").split("/")
    offset = 2 if len(parts) >= 2 and parts[0] == "api" and parts[1] == "v1" else 0
    scoped = parts[offset:]
    run_id = scoped[1] if len(scoped) >= 2 and scoped[0] == "runs" else None
    stage = scoped[3] if len(scoped) >= 4 and scoped[0] == "runs" and scoped[2] == "stages" else None
    return JSONResponse(
        status_code=status_code,
        content={
            "error_code": error_code,
            "message": message,
            "status_code": status_code,
            "run_id": run_id,
            "stage": stage,
            "retryable": retryable,
            "details": details or {},
        },
    )
