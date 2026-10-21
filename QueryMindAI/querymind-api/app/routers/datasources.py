"""Data source settings, stored in Qdrant (querymind-agentic `querymind.datasources`)."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from querymind.datasources import (
    DataSource,
    DataSourceInput,
    DataSourceNotFoundError,
    DuplicateDataSourceError,
)
from querymind.service import QueryMindService

from app.dependencies import get_service

router = APIRouter(prefix="/datasources", tags=["data sources"])

Service = Annotated[QueryMindService, Depends(get_service)]

NOT_FOUND = {404: {"description": "No data source with that id"}}
CONFLICT = {409: {"description": "Another data source already has that name"}}
ENV_ID = "env:"  # prefix of databases configured only in .env


def _env_entry(source_id: str, service: QueryMindService) -> DataSource:
    if (source := service.env_datasource(source_id)) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Data source not found.")
    return source


@router.get("", response_model=list[DataSource], summary="List data sources")
def list_datasources(service: Service) -> list[DataSource]:
    """Saved data sources (oldest first), then databases configured only in .env (`origin: "env"`,
    id `env:<name>`). The first call saves the documented ones from the schema files.

    Queries use a saved data source's settings; any field left empty, and the password, come from
    QUERYMIND_DB_<NAME> in .env. Databases without a saved data source use the .env URL as is."""
    return service.list_datasources()


@router.get(
    "/{source_id}",
    response_model=DataSource,
    responses=NOT_FOUND,
    summary="Get a data source",
)
def get_datasource(source_id: str, service: Service) -> DataSource:
    if source_id.startswith(ENV_ID):
        return _env_entry(source_id, service)
    try:
        return service.datasources.get(source_id)
    except DataSourceNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Data source not found.") from None


@router.post(
    "",
    response_model=DataSource,
    status_code=status.HTTP_201_CREATED,
    responses=CONFLICT,
    summary="Create a data source",
)
def create_datasource(body: DataSourceInput, service: Service) -> DataSource:
    """Connection fields depend on the type and never include passwords; credentials stay on the server."""
    try:
        return service.datasources.create(body)
    except DuplicateDataSourceError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from None


@router.put(
    "/{source_id}",
    response_model=DataSource,
    responses=NOT_FOUND | CONFLICT,
    summary="Replace a data source",
)
def update_datasource(source_id: str, body: DataSourceInput, service: Service) -> DataSource:
    """Replace a saved data source. For an `env:<name>` id, the settings are saved as a new data source."""
    if source_id.startswith(ENV_ID):
        _env_entry(source_id, service)
        return create_datasource(body, service)
    try:
        return service.datasources.update(source_id, body)
    except DataSourceNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Data source not found.") from None
    except DuplicateDataSourceError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from None


@router.delete(
    "/{source_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=NOT_FOUND | {409: {"description": "Configured in .env; cannot be deleted here"}},
    summary="Delete a data source",
)
def delete_datasource(source_id: str, service: Service) -> Response:
    if source_id.startswith(ENV_ID):
        _env_entry(source_id, service)
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This database is configured in the server's .env file (QUERYMIND_DB_<NAME>); remove it there.",
        )
    try:
        service.datasources.delete(source_id)
    except DataSourceNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Data source not found.") from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)
