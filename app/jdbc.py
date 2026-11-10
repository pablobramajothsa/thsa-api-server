"""Conversión de URLs JDBC de Oracle al formato de conexión de python-oracledb.

Formatos soportados (los mismos que acepta el driver JDBC "thin"):

    jdbc:oracle:thin:@host:puerto:SID                 -> conexión por SID
    jdbc:oracle:thin:@host:puerto/servicio            -> conexión por nombre de servicio
    jdbc:oracle:thin:@//host:puerto/servicio          -> idem
    jdbc:oracle:thin:@(DESCRIPTION=...)               -> descriptor TNS completo

El driver sigue siendo python-oracledb: la URL JDBC es solo la forma de configurarlo.
Usuario y contraseña NO pueden ir dentro de la URL (van en DB_USER / DB_PASSWORD), para
que no terminen en logs ni en mensajes de error.
"""

import re

_PREFIX = re.compile(r"^jdbc:oracle:thin:", re.IGNORECASE)
_HOST = r"(?P<host>[A-Za-z0-9.\-]+|\[[0-9A-Fa-f:]+\])"
_PORT = r"(?P<port>\d{1,5})"
_SID_FORM = re.compile(rf"^@{_HOST}:{_PORT}:(?P<sid>[A-Za-z][A-Za-z0-9_$#]*)$")
_SERVICE_FORM = re.compile(rf"^@(?://)?{_HOST}:{_PORT}/(?P<service>[A-Za-z0-9_.\-]+)$")


class JdbcUrlError(ValueError):
    pass


def jdbc_url_to_dsn(url: str) -> str:
    url = url.strip()
    if not _PREFIX.match(url):
        raise JdbcUrlError("the JDBC URL must start with 'jdbc:oracle:thin:'")
    rest = _PREFIX.sub("", url, count=1)

    if not rest.startswith("@"):
        # jdbc:oracle:thin:usuario/clave@...
        raise JdbcUrlError("the JDBC URL must not contain credentials; use DB_USER and DB_PASSWORD")

    if rest.startswith("@("):
        descriptor = rest[1:]
        if descriptor.count("(") != descriptor.count(")"):
            raise JdbcUrlError("unbalanced parentheses in the TNS descriptor")
        return descriptor

    if match := _SID_FORM.fullmatch(rest):
        host, port, sid = match["host"], int(match["port"]), match["sid"]
        _check_port(port)
        return (
            f"(DESCRIPTION=(ADDRESS=(PROTOCOL=TCP)(HOST={host})(PORT={port}))"
            f"(CONNECT_DATA=(SID={sid})))"
        )

    if match := _SERVICE_FORM.fullmatch(rest):
        port = int(match["port"])
        _check_port(port)
        return f"{match['host']}:{port}/{match['service']}"

    raise JdbcUrlError(
        "unsupported JDBC URL; expected jdbc:oracle:thin:@host:port:SID, "
        "jdbc:oracle:thin:@host:port/service or jdbc:oracle:thin:@(DESCRIPTION=...)"
    )


def _check_port(port: int) -> None:
    if not 1 <= port <= 65535:
        raise JdbcUrlError("invalid port in JDBC URL")
