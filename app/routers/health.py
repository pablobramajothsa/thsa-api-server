"""Chequeo de salud: verifica la conexión a Oracle sin exponer detalles."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.db import Database, get_db

logger = logging.getLogger("api.health")

router = APIRouter(tags=["health"])


@router.get("/health", include_in_schema=False)
def health(db: Annotated[Database, Depends(get_db)]) -> JSONResponse:
    try:
        healthy = db.scalar("SELECT 1 FROM DUAL", {}) == 1
    except Exception:
        logger.warning("health check failed", exc_info=True)
        healthy = False
    if healthy:
        return JSONResponse({"status": "ok"})
    return JSONResponse({"status": "unavailable"}, status_code=503)
