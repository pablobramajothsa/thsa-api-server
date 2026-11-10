"""Punto de entrada. Se ejecuta como factory:

uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import oracledb
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import Settings
from app.db import Database, DatabaseError, OracleDatabase
from app.db_jdbc import JdbcDatabase
from app.logging_conf import setup_logging
from app.middleware import RequestContextMiddleware, error_logger, internal_error_response
from app.ratelimit import RateLimitMiddleware
from app.routers import BASE_MODULES, VIEW_MODULES
from app.security import TOKEN_URL
from app.users import UserStore

logger = logging.getLogger("api")


async def _database_error_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    error_logger.error(
        "database error",
        exc_info=exc,
        extra={"request_id": request_id, "path": request.url.path},
    )
    return internal_error_response(request_id)


def create_app(
    settings: Settings | None = None,
    database: Database | None = None,
    users: UserStore | None = None,
) -> FastAPI:
    settings = settings or Settings()
    setup_logging(settings.log_level)
    users = users if users is not None else UserStore(settings.users_file)
    users.load()  # falla al arrancar si el archivo de usuarios es inválido
    production = settings.is_production

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if users.get_count() == 0:
            logger.warning(
                "no API users configured: every /v1 request will be rejected",
                extra={"users_file": str(users.path)},
            )
        yield
        app.state.db.close()

    app = FastAPI(
        title="API de vistas Oracle",
        version="1.0.0",
        docs_url=None if production else "/docs",
        redoc_url=None if production else "/redoc",
        openapi_url=None if production else "/openapi.json",
        lifespan=lifespan,
    )
    app.state.settings = settings
    if database is None:
        database = (
            JdbcDatabase(settings) if settings.db_driver == "jdbc" else OracleDatabase(settings)
        )
    app.state.db = database
    app.state.users = users

    app.add_exception_handler(oracledb.Error, _database_error_handler)
    app.add_exception_handler(DatabaseError, _database_error_handler)

    # El último middleware agregado es el más externo:
    # RequestContext -> CORS -> RateLimit -> rutas
    app.add_middleware(
        RateLimitMiddleware,
        rate=settings.rate_limit,
        storage_uri=settings.rate_limit_storage_uri,
        path_limits={TOKEN_URL: settings.login_rate_limit},
    )
    if settings.cors_origin_list:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origin_list,
            allow_methods=["GET", "POST"],
            allow_headers=["Authorization", "Content-Type"],
            allow_credentials=False,
            max_age=600,
        )
    app.add_middleware(RequestContextMiddleware, production=production)

    # Las vistas publicadas se registran en app/routers/__init__.py (VIEW_MODULES).
    for module in (*BASE_MODULES, *VIEW_MODULES):
        app.include_router(module.router)
    return app
