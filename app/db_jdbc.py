"""Backend JDBC: driver Oracle ojdbc8 ejecutado en una JVM embebida (JPype).

- La JVM se inicia una sola vez por proceso, en el primer uso.
- Las consultas usan PreparedStatement: los binds con nombre (`:nombre`) que arma
  app/query.py se convierten a parámetros posicionales `?`. Ningún valor del usuario
  se concatena al SQL.
- Timeout por consulta con `setQueryTimeout` y timeout de lectura de red del driver.
- Las conexiones son de solo lectura (`setReadOnly(true)`).
"""

import datetime
import decimal
import logging
import math
import re
import threading
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from app.config import Settings
from app.db import Binds, DatabaseError, Row
from app.pool import ConnectionPool, PoolTimeoutError

logger = logging.getLogger("api.db")

_BIND = re.compile(r":([a-z][a-z0-9_]*)")
_JVM_LOCK = threading.Lock()
FETCH_SIZE = 100
LOGIN_TIMEOUT_S = 10
VALIDATE_TIMEOUT_S = 2


# --- Conversión de SQL y valores (sin JVM) -----------------------------------


def to_positional(sql: str, binds: Mapping[str, Any]) -> tuple[str, list[Any]]:
    """`WHERE A = :a AND B < :b` -> (`WHERE A = ? AND B < ?`, [binds['a'], binds['b']])."""
    names = _BIND.findall(sql)
    missing = set(names) - set(binds)
    if missing:
        raise ValueError(f"missing binds: {sorted(missing)}")
    unused = set(binds) - set(names)
    if unused:
        raise ValueError(f"unused binds: {sorted(unused)}")
    return _BIND.sub("?", sql), [binds[name] for name in names]


# --- JVM ---------------------------------------------------------------------


def find_jvm(java_home: str | None) -> str:
    import jpype

    if not java_home:
        return jpype.getDefaultJVMPath()
    home = Path(java_home)
    for candidate in ("bin/server/jvm.dll", "lib/server/libjvm.so", "lib/server/libjvm.dylib"):
        path = home / candidate
        if path.exists():
            return str(path)
    raise DatabaseError(f"JVM not found under JAVA_HOME={java_home}")


def ensure_jvm(java_home: str | None, driver_jar: str) -> None:
    import jpype
    import jpype.imports  # habilita "from java.sql import ..."

    with _JVM_LOCK:
        if jpype.isJVMStarted():
            return
        jar = Path(driver_jar).resolve()
        if not jar.exists():
            raise DatabaseError(f"JDBC driver jar not found: {jar}")
        jpype.startJVM(
            find_jvm(java_home),
            "-Xrs",  # la JVM no captura Ctrl+C: lo maneja uvicorn
            "-Xmx256m",
            "-Doracle.jdbc.J2EE13Compliant=true",  # tipos estándar (Timestamp, BigDecimal)
            classpath=[str(jar)],
            convertStrings=False,
        )
        logger.info("JVM started", extra={"driver_jar": jar.name})


def _java_to_python(value: Any) -> Any:
    if value is None:
        return None
    cls = str(value.getClass().getName())
    if cls == "java.lang.String":
        return str(value)
    if cls == "java.math.BigDecimal":
        if value.signum() == 0 or value.stripTrailingZeros().scale() <= 0:
            return int(str(value.toBigInteger()))
        return decimal.Decimal(str(value.toPlainString()))
    if cls == "java.sql.Timestamp":
        ldt = value.toLocalDateTime()
        return datetime.datetime(
            ldt.getYear(),
            ldt.getMonthValue(),
            ldt.getDayOfMonth(),
            ldt.getHour(),
            ldt.getMinute(),
            ldt.getSecond(),
            ldt.getNano() // 1000,
        )
    if cls == "java.sql.Date":
        return datetime.date.fromisoformat(str(value.toString()))
    if cls in ("java.lang.Integer", "java.lang.Long", "java.lang.Short", "java.lang.Byte"):
        return int(value)
    if cls in ("java.lang.Double", "java.lang.Float"):
        return float(value)
    if cls == "java.lang.Boolean":
        return bool(value)
    from java.sql import Clob  # type: ignore[import-not-found]

    if isinstance(value, Clob):
        return str(value.getSubString(1, int(value.length())))
    return str(value.toString())


def _set_param(statement: Any, index: int, value: Any) -> None:
    from java.math import BigDecimal  # type: ignore[import-not-found]
    from java.sql import Date, Timestamp, Types  # type: ignore[import-not-found]

    if value is None:
        statement.setNull(index, Types.VARCHAR)
    elif isinstance(value, bool):
        statement.setInt(index, int(value))
    elif isinstance(value, int):
        statement.setLong(index, value)
    elif isinstance(value, float):
        statement.setDouble(index, value)
    elif isinstance(value, decimal.Decimal):
        statement.setBigDecimal(index, BigDecimal(str(value)))
    elif isinstance(value, datetime.datetime):
        statement.setTimestamp(index, Timestamp.valueOf(value.strftime("%Y-%m-%d %H:%M:%S.%f")))
    elif isinstance(value, datetime.date):
        statement.setDate(index, Date.valueOf(value.isoformat()))
    elif isinstance(value, str):
        statement.setString(index, value)
    else:
        raise TypeError(f"unsupported bind type: {type(value).__name__}")


# --- Backend -----------------------------------------------------------------


class JdbcDatabase:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._pool: ConnectionPool[Any] | None = None
        self._lock = threading.Lock()
        self._query_timeout_s = max(1, math.ceil(settings.db_call_timeout_ms / 1000))

    def _connect(self) -> Any:
        from java.sql import DriverManager  # type: ignore[import-not-found]
        from java.util import Properties  # type: ignore[import-not-found]

        s = self._settings
        props = Properties()
        props.setProperty("user", s.db_user)
        props.setProperty("password", s.db_password.get_secret_value())
        props.setProperty("oracle.net.CONNECT_TIMEOUT", str(LOGIN_TIMEOUT_S * 1000))
        # Corta lecturas de red colgadas aunque el servidor no responda al cancel.
        props.setProperty("oracle.jdbc.ReadTimeout", str(s.db_call_timeout_ms + 5000))
        DriverManager.setLoginTimeout(LOGIN_TIMEOUT_S)
        conn = DriverManager.getConnection(s.db_jdbc_url, props)
        conn.setReadOnly(True)
        return conn

    def _get_pool(self) -> ConnectionPool[Any]:
        if self._pool is None:
            with self._lock:
                if self._pool is None:
                    s = self._settings
                    try:
                        ensure_jvm(s.java_home, s.jdbc_driver_jar)
                        pool: ConnectionPool[Any] = ConnectionPool(
                            self._connect,
                            validate=lambda conn: conn.isValid(VALIDATE_TIMEOUT_S),
                            close=lambda conn: conn.close(),
                            min_size=s.db_pool_min,
                            max_size=s.db_pool_max,
                            wait_timeout_s=s.db_pool_wait_timeout_ms / 1000,
                        )
                        pool.open()
                    except DatabaseError:
                        raise
                    except Exception as exc:
                        raise DatabaseError(f"cannot open JDBC pool: {exc}") from None
                    self._pool = pool
                    logger.info(
                        "JDBC connection pool created",
                        extra={"pool_min": s.db_pool_min, "pool_max": s.db_pool_max},
                    )
        return self._pool

    @contextmanager
    def _execute(self, sql: str, binds: Binds) -> Iterator[Any]:
        positional_sql, params = to_positional(sql, binds)
        try:
            with self._get_pool().acquire() as conn:
                statement = conn.prepareStatement(positional_sql)
                try:
                    statement.setQueryTimeout(self._query_timeout_s)
                    statement.setFetchSize(FETCH_SIZE)
                    for index, value in enumerate(params, start=1):
                        _set_param(statement, index, value)
                    result = statement.executeQuery()
                    try:
                        yield result
                    finally:
                        result.close()
                finally:
                    statement.close()
        except (DatabaseError, TypeError):
            raise
        except PoolTimeoutError as exc:
            raise DatabaseError(str(exc)) from None
        except Exception as exc:
            # java.sql.SQLException y similares: el detalle (ORA-xxxxx) solo va al log.
            raise DatabaseError(f"{type(exc).__name__}: {exc}") from None

    @staticmethod
    def _columns(result: Any) -> list[str]:
        meta = result.getMetaData()
        return [str(meta.getColumnLabel(i)).lower() for i in range(1, meta.getColumnCount() + 1)]

    @staticmethod
    def _row(result: Any, columns: Sequence[str]) -> Row:
        return {
            name: _java_to_python(result.getObject(index))
            for index, name in enumerate(columns, start=1)
        }

    def fetch_all(self, sql: str, binds: Binds) -> list[Row]:
        with self._execute(sql, binds) as result:
            columns = self._columns(result)
            rows = []
            while result.next():
                rows.append(self._row(result, columns))
            return rows

    def fetch_one(self, sql: str, binds: Binds) -> Row | None:
        with self._execute(sql, binds) as result:
            columns = self._columns(result)
            return self._row(result, columns) if result.next() else None

    def scalar(self, sql: str, binds: Binds) -> Any:
        with self._execute(sql, binds) as result:
            return _java_to_python(result.getObject(1)) if result.next() else None

    def close(self) -> None:
        if self._pool is not None:
            self._pool.close()
            self._pool = None
