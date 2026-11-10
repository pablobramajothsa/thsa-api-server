"""Pool de conexiones genérico y thread-safe (usado por el backend JDBC).

JDBC no trae pool propio (Oracle UCP sería otro .jar), así que se implementa uno simple:
- nunca hay más de `max_size` conexiones en uso,
- las conexiones devueltas quedan ociosas para reutilizarse (LIFO),
- antes de reutilizar una conexión que estuvo ociosa más de `validate_after_s` segundos,
  se valida (p. ej. `Connection.isValid`) y se descarta si se cortó.
"""

import logging
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Generic, TypeVar

logger = logging.getLogger("api.db")

C = TypeVar("C")


class PoolTimeoutError(Exception):
    """No hubo una conexión libre dentro del tiempo de espera."""


class ConnectionPool(Generic[C]):
    def __init__(
        self,
        factory: Callable[[], C],
        *,
        validate: Callable[[C], bool],
        close: Callable[[C], None],
        min_size: int,
        max_size: int,
        wait_timeout_s: float,
        validate_after_s: float = 60.0,
    ) -> None:
        if not 0 <= min_size <= max_size or max_size < 1:
            raise ValueError("invalid pool size")
        self._factory = factory
        self._validate = validate
        self._close = close
        self._min_size = min_size
        self._wait_timeout_s = wait_timeout_s
        self._validate_after_s = validate_after_s
        self._slots = threading.BoundedSemaphore(max_size)
        self._lock = threading.Lock()
        self._idle: list[tuple[C, float]] = []  # (conexión, momento en que quedó ociosa)
        self._closed = False

    def open(self) -> None:
        """Crea las conexiones mínimas. Lanza la excepción del factory si no puede conectar."""
        created = [self._factory() for _ in range(self._min_size)]
        now = time.monotonic()
        with self._lock:
            self._idle.extend((conn, now) for conn in created)

    @contextmanager
    def acquire(self) -> Iterator[C]:
        if self._closed:
            raise RuntimeError("pool is closed")
        if not self._slots.acquire(timeout=self._wait_timeout_s):
            raise PoolTimeoutError("no free connection in the pool")
        conn: C | None = None
        healthy = False
        try:
            conn = self._take_idle() or self._factory()
            yield conn
            healthy = True
        finally:
            if conn is not None:
                self._release(conn, healthy)
            self._slots.release()

    def close(self) -> None:
        with self._lock:
            self._closed = True
            idle, self._idle = self._idle, []
        for conn, _ in idle:
            self._safe_close(conn)

    @property
    def idle_count(self) -> int:
        with self._lock:
            return len(self._idle)

    def _take_idle(self) -> C | None:
        while True:
            with self._lock:
                if not self._idle:
                    return None
                conn, since = self._idle.pop()
            if time.monotonic() - since < self._validate_after_s or self._is_valid(conn):
                return conn
            logger.info("discarding dead pooled connection")
            self._safe_close(conn)

    def _release(self, conn: C, healthy: bool) -> None:
        # Tras un error, la conexión solo vuelve al pool si sigue viva.
        if not self._closed and (healthy or self._is_valid(conn)):
            with self._lock:
                self._idle.append((conn, time.monotonic()))
        else:
            self._safe_close(conn)

    def _is_valid(self, conn: C) -> bool:
        try:
            return bool(self._validate(conn))
        except Exception:
            return False

    def _safe_close(self, conn: C) -> None:
        try:
            self._close(conn)
        except Exception:
            logger.warning("error closing connection", exc_info=True)
