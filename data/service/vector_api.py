import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.logging_setup import setup_logging
from core.memory import memory

setup_logging()
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/data/vector", tags=["data"])


class VectorQueryRequest(BaseModel):
    query: str
    n_results: int = Field(default=5, ge=1, le=50)
    threshold: Optional[float] = None
    where: Optional[Dict[str, Any]] = None


@router.post("/search")
def vector_search(payload: VectorQueryRequest):
    try:
        results = memory.recall_with_metadata(
            payload.query,
            n_results=payload.n_results,
            threshold=payload.threshold,
            source=payload.where.get("source") if payload.where else None,
        )
        return {"query": payload.query, "results": results}
    except Exception as e:
        logger.exception("Vector search failed.")
        raise HTTPException(status_code=500, detail=str(e)) from e
