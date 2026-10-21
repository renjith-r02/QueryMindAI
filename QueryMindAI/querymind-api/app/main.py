import os

from fastapi import APIRouter, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.errors import HANDLED, describe_error
from app.routers import admin, datasources, guardrails, knowledge, queries


class ServiceResponse(BaseModel):
    message: str


class HealthResponse(BaseModel):
    status: str
    service: str


api_router = APIRouter()


@api_router.get("/", response_model=ServiceResponse, tags=["service"])
async def read_root() -> ServiceResponse:
    return ServiceResponse(message="QueryMind API is running")


@api_router.get("/health", response_model=HealthResponse, tags=["health"])
async def read_health() -> HealthResponse:
    return HealthResponse(status="ok", service="querymind-api")


app = FastAPI(
    title="QueryMind API",
    version="0.1.0",
    description="FastAPI service for QueryMind: index database knowledge, search it, "
    "generate SQL and answer questions from the databases.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.getenv("QUERYMIND_CORS_ORIGINS", "http://localhost:8080").split(",") if o],
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)
app.include_router(api_router)
app.include_router(knowledge.router)
app.include_router(queries.router)
app.include_router(admin.router)
app.include_router(datasources.router)
app.include_router(guardrails.router)


# -- errors from the shared QueryMind service ----------------------------------------------


async def service_error(_: Request, error: Exception) -> JSONResponse:
    status_code, detail = describe_error(error)
    return JSONResponse(status_code=status_code, content={"detail": detail})


for error_type in HANDLED:
    app.add_exception_handler(error_type, service_error)
