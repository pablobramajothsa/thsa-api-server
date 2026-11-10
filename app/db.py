"""Acceso a Oracle mediante un pool de conexiones de python-oracledb.

Oracle 11g no está soportado por el modo thin (requiere 12.1+), así que se usa el modo
thick con Oracle Instant Client 19 (la última versión de cliente que conecta con 11.2).

El pool se crea de forma diferida en el primer uso: así la API arranca aunque la base
no esté disponible, y /health informa el estado real.
"""

import logging
import threading
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Any, Protocol

import oracledb
from fastapi import Request

from app.config import Settings

logger = logging.getLogger("api.db")

Row = dict[str, Any]
Binds = Mapping[str, Any]


class DatabaseError(Exception):
    """Error de acceso a la base (cualquier backend). El mensaje solo se loguea, nunca se
    devuelve al cliente."""


class Database(Protocol):
    """Interfaz mínima que usan los routers; los tests la reemplazan por un fake."""

    def fetch_all(self, sql: str, binds: Binds) -> list[Row]: ...

    def fetch_one(self, sql: str, binds: Binds) -> Row | None: ...

    def scalar(self, sql: str, binds: Binds) -> Any: ...

    def close(self) -> None: ...


_client_lock = threading.Lock()
_client_initialized = False


def _init_thick_mode(lib_dir: str | None) -> None:
    global _client_initialized
    with _client_lock:
        if not _client_initialized:
            oracledb.init_oracle_client(lib_dir=lib_dir)
            _client_initialized = True


class OracleDatabase:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._pool: oracledb.ConnectionPool | None = None
        self._lock = threading.Lock()

    def _get_pool(self) -> oracledb.ConnectionPool:
        if self._pool is None:
            with self._lock:
                if self._pool is None:
                    s = self._settings
                    _init_thick_mode(s.oracle_client_lib_dir)
                    self._pool = oracledb.create_pool(
                        user=s.db_user,
                        password=s.db_password.get_secret_value(),
                        dsn=s.dsn,
                        min=s.db_pool_min,
                        max=s.db_pool_max,
                        increment=1,
                        getmode=oracledb.POOL_GETMODE_TIMEDWAIT,
                        wait_timeout=s.db_pool_wait_timeout_ms,
                        ping_interval=60,
                    )
                    logger.info(
                        "connection pool created",
                        extra={"pool_min": s.db_pool_min, "pool_max": s.db_pool_max},
                    )
        return self._pool

    @contextmanager
    def _cursor(self) -> Iterator[oracledb.Cursor]:
        with self._get_pool().acquire() as conn:
            conn.call_timeout = self._settings.db_call_timeout_ms
            with conn.cursor() as cursor:
                yield cursor

    @staticmethod
    def _rows_as_dicts(cursor: oracledb.Cursor) -> None:
        columns = [description[0].lower() for description in cursor.description]
        cursor.rowfactory = lambda *values: dict(zip(columns, values, strict=True))

    def fetch_all(self, sql: str, binds: Binds) -> list[Row]:
        with self._cursor() as cursor:
            cursor.execute(sql, dict(binds))
            self._rows_as_dicts(cursor)
            return cursor.fetchall()

    def fetch_one(self, sql: str, binds: Binds) -> Row | None:
        with self._cursor() as cursor:
            cursor.execute(sql, dict(binds))
            self._rows_as_dicts(cursor)
            return cursor.fetchone()

    def scalar(self, sql: str, binds: Binds) -> Any:
        with self._cursor() as cursor:
            cursor.execute(sql, dict(binds))
            row = cursor.fetchone()
            return row[0] if row else None

    def close(self) -> None:
        if self._pool is not None:
            self._pool.close(force=True)
            self._pool = None


def get_db(request: Request) -> Database:
    return request.app.state.db
