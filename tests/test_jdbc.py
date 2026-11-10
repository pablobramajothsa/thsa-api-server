import pytest
from pydantic import ValidationError

from app.jdbc import JdbcUrlError, jdbc_url_to_dsn
from tests.conftest import make_settings


@pytest.mark.parametrize(
    ("url", "dsn"),
    [
        (
            "jdbc:oracle:thin:@192.168.16.248:1521:BASE",
            "(DESCRIPTION=(ADDRESS=(PROTOCOL=TCP)(HOST=192.168.16.248)(PORT=1521))"
            "(CONNECT_DATA=(SID=BASE)))",
        ),
        ("jdbc:oracle:thin:@db.ejemplo.local:1522/SERVICIO", "db.ejemplo.local:1522/SERVICIO"),
        (
            "jdbc:oracle:thin:@//db.ejemplo.local:1521/srv.dominio",
            "db.ejemplo.local:1521/srv.dominio",
        ),
        (
            "JDBC:ORACLE:THIN:@host:1521:ORCL",
            "(DESCRIPTION=(ADDRESS=(PROTOCOL=TCP)(HOST=host)(PORT=1521))(CONNECT_DATA=(SID=ORCL)))",
        ),
        (
            "jdbc:oracle:thin:@(DESCRIPTION=(ADDRESS=(PROTOCOL=TCP)(HOST=h)(PORT=1521))"
            "(CONNECT_DATA=(SERVICE_NAME=s)))",
            "(DESCRIPTION=(ADDRESS=(PROTOCOL=TCP)(HOST=h)(PORT=1521))(CONNECT_DATA=(SERVICE_NAME=s)))",
        ),
    ],
)
def test_formatos_soportados(url, dsn):
    assert jdbc_url_to_dsn(url) == dsn


@pytest.mark.parametrize(
    "url",
    [
        "jdbc:mysql://host:3306/db",
        "oracle:thin:@host:1521:SID",
        "jdbc:oracle:thin:usuario/clave@host:1521:SID",
        "jdbc:oracle:thin:@host:99999:SID",
        "jdbc:oracle:thin:@host:1521",
        "jdbc:oracle:thin:@host:1521:SID)(INYECCION=1",
        "jdbc:oracle:thin:@(DESCRIPTION=(ADDRESS=(HOST=h)",
    ],
)
def test_formatos_invalidos(url):
    with pytest.raises(JdbcUrlError):
        jdbc_url_to_dsn(url)


def test_settings_usa_la_url_jdbc_como_dsn():
    settings = make_settings(db_jdbc_url="jdbc:oracle:thin:@10.0.0.1:1521:BASE")
    assert settings.dsn.endswith("(CONNECT_DATA=(SID=BASE)))")


def test_settings_usa_db_dsn_si_no_hay_url():
    assert make_settings(db_driver="oracledb", db_dsn="h:1521/s").dsn == "h:1521/s"


def test_no_se_pueden_configurar_ambas():
    with pytest.raises(ValidationError):
        make_settings(db_jdbc_url="jdbc:oracle:thin:@h:1521:S", db_dsn="h:1521/s")


def test_error_de_url_no_muestra_credenciales():
    with pytest.raises(ValidationError) as info:
        make_settings(db_jdbc_url="jdbc:oracle:thin:usuario/clave-secreta@h:1521:S")
    assert "clave-secreta" not in str(info.value)
