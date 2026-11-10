import datetime
import decimal
from pathlib import Path

import pytest

from app.db import DatabaseError
from app.db_jdbc import JdbcDatabase, to_positional
from app.main import create_app
from tests.conftest import make_settings

# --- Conversión de binds con nombre a posicionales (sin JVM) ------------------


def test_binds_con_nombre_a_posicionales():
    sql, params = to_positional(
        "SELECT * FROM V WHERE A = :a AND B < :fecha_hasta AND ROWNUM <= :max_row",
        {"max_row": 20, "a": "x", "fecha_hasta": datetime.date(2024, 1, 1)},
    )
    assert sql == "SELECT * FROM V WHERE A = ? AND B < ? AND ROWNUM <= ?"
    assert params == ["x", datetime.date(2024, 1, 1), 20]


def test_bind_repetido_se_pasa_dos_veces():
    sql, params = to_positional("SELECT 1 FROM DUAL WHERE :x = 1 OR :x = 2", {"x": 5})
    assert sql.count("?") == 2
    assert params == [5, 5]


def test_valor_del_usuario_nunca_entra_al_sql():
    sql, params = to_positional("SELECT 1 FROM V WHERE C = :c", {"c": "' OR 1=1 --"})
    assert "OR 1=1" not in sql
    assert params == ["' OR 1=1 --"]


@pytest.mark.parametrize(
    ("sql", "binds"),
    [("SELECT 1 FROM V WHERE A = :a", {}), ("SELECT 1 FROM V", {"sobra": 1})],
)
def test_binds_faltantes_o_sobrantes_fallan(sql, binds):
    with pytest.raises(ValueError):
        to_positional(sql, binds)


# --- Integración con la app (sin conectar) ------------------------------------


def test_driver_jdbc_es_el_backend_por_defecto(tmp_path):
    app = create_app(
        make_settings(db_jdbc_url="jdbc:oracle:thin:@h:1521:S", users_file=str(tmp_path / "u"))
    )
    assert isinstance(app.state.db, JdbcDatabase)


def test_jdbc_no_acepta_db_dsn():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        make_settings(db_driver="jdbc", db_dsn="h:1521/s")


def test_database_error_responde_500_generico(client, fake_db, auth):
    fake_db.error = DatabaseError("java.sql.SQLSyntaxErrorException: ORA-00942: tabla no existe")
    response = client.get("/v1/campos", headers=auth)

    assert response.status_code == 500
    assert "ORA-" not in response.text
    assert "java" not in response.text
    assert response.json()["request_id"] == response.headers["X-Request-ID"]


def test_jar_inexistente_da_error_de_base(tmp_path):
    db = JdbcDatabase(
        make_settings(
            db_jdbc_url="jdbc:oracle:thin:@h:1521:S", jdbc_driver_jar=str(tmp_path / "no.jar")
        )
    )
    jpype = pytest.importorskip("jpype")
    if jpype.isJVMStarted():
        pytest.skip("la JVM ya está iniciada en este proceso")
    with pytest.raises(DatabaseError):
        db.scalar("SELECT 1 FROM DUAL", {})


# --- Conversión de tipos Java <-> Python (requiere Java) ----------------------

JAR = Path(make_settings().jdbc_driver_jar)


@pytest.fixture(scope="module")
def jvm():
    jpype = pytest.importorskip("jpype")
    from app.db_jdbc import ensure_jvm, find_jvm

    try:
        find_jvm(None)
    except Exception:
        pytest.skip("no hay Java disponible")
    if not JAR.exists():
        pytest.skip(f"no está el driver {JAR}")
    ensure_jvm(None, str(JAR))
    return jpype


class RecordingStatement:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        return lambda *args: self.calls.append((name, args))


def test_tipos_java_a_python(jvm):
    from java.lang import Integer, String  # type: ignore[import-not-found]
    from java.math import BigDecimal  # type: ignore[import-not-found]
    from java.sql import Date, Timestamp  # type: ignore[import-not-found]

    from app.db_jdbc import _java_to_python

    assert _java_to_python(None) is None
    assert _java_to_python(String("hola")) == "hola"
    assert _java_to_python(BigDecimal("100449")) == 100449
    assert _java_to_python(BigDecimal("1.50E+2")) == 150
    assert _java_to_python(BigDecimal("0")) == 0
    assert _java_to_python(BigDecimal("12.345")) == decimal.Decimal("12.345")
    assert _java_to_python(Integer(7)) == 7
    assert _java_to_python(Timestamp.valueOf("2024-03-05 10:20:30.123456789")) == (
        datetime.datetime(2024, 3, 5, 10, 20, 30, 123456)
    )
    assert _java_to_python(Date.valueOf("2024-03-05")) == datetime.date(2024, 3, 5)


def test_tipos_python_a_parametros_jdbc(jvm):
    from app.db_jdbc import _set_param

    statement = RecordingStatement()
    values = [
        None,
        True,
        42,
        1.5,
        decimal.Decimal("9.99"),
        "texto",
        datetime.date(2024, 1, 31),
        datetime.datetime(2024, 1, 31, 23, 59, 59),
    ]
    for index, value in enumerate(values, start=1):
        _set_param(statement, index, value)

    methods = [name for name, _ in statement.calls]
    assert methods == [
        "setNull",
        "setInt",
        "setLong",
        "setDouble",
        "setBigDecimal",
        "setString",
        "setDate",
        "setTimestamp",
    ]
    assert str(statement.calls[6][1][1]) == "2024-01-31"
    assert str(statement.calls[7][1][1]).startswith("2024-01-31 23:59:59")


def test_tipo_no_soportado(jvm):
    from app.db_jdbc import _set_param

    with pytest.raises(TypeError):
        _set_param(RecordingStatement(), 1, object())
