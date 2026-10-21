from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from querymind.service import QueryMindService

from app.dependencies import get_service
from app.schemas import IndexRequest, IndexResponse, SearchHitOut, SourceFile

router = APIRouter(tags=["knowledge"])

Service = Annotated[QueryMindService, Depends(get_service)]


@router.get("/sources", response_model=list[SourceFile])
def list_sources(service: Service) -> list[SourceFile]:
    """Schema and question/SQL files that can be indexed."""
    return [SourceFile(name=path.name, size_bytes=path.stat().st_size) for path in service.source_files()]


@router.post("/index", response_model=IndexResponse)
def index(body: IndexRequest, service: Service) -> IndexResponse:
    """Parse source files and replace their chunks in the vector collection."""
    paths = None
    if body.files:
        # Only files from the server's source directory can be indexed, never arbitrary paths.
        available = {path.name: path for path in service.source_files()}
        unknown = sorted(set(body.files) - available.keys())
        if unknown:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                f"Unknown source file(s): {', '.join(unknown)}. Available: {', '.join(sorted(available))}",
            )
        paths = [available[name] for name in dict.fromkeys(body.files)]

    report = service.index(
        paths,
        database=body.database,
        dialect=body.dialect,
        recreate=body.recreate,
        dry_run=body.dry_run,
    )
    return IndexResponse.from_report(report, include_chunks=body.include_chunks)


@router.get("/search", response_model=list[SearchHitOut], response_model_exclude_none=True)
def search(
    service: Service,
    q: Annotated[str, Query(min_length=1, max_length=2000, description="Text to search for")],
    limit: Annotated[int, Query(ge=1, le=50)] = 5,
    doc_type: Annotated[str | None, Query(description="e.g. table, example_query, business_rule")] = None,
    database: Annotated[str | None, Query(description="e.g. ecommerce, returns_db")] = None,
    include_content: bool = False,
) -> list[SearchHitOut]:
    """Semantic search over the indexed knowledge."""
    hits = service.search(q, limit=limit, doc_type=doc_type, database=database)
    return [SearchHitOut.from_hit(hit, include_content) for hit in hits]
