"""Contrato que cumple TODA vista registrada en app/routers/__init__.py (VIEW_MODULES).

Una API nueva queda cubierta automáticamente al agregarla al registro: no hace falta
escribir estos tests de nuevo para cada vista.
"""

import re
from typing import get_args

import oracledb
import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.main import create_app
from app.routers import VIEW_MODULES
from app.security import require_user
from tests.conftest import FakeDatabase, make_settings

_PATH_PARAM = re.compile(r"\{[^}]+\}")

VIEWS = pytest.mark.parametrize("module", VIEW_MODULES, ids=lambda m: m.__name__.split(".")[-1])


def _get_routes(module) -> list[APIRoute]:
    return [r for r in module.router.routes if isinstance(r, APIRoute) and "GET" in r.methods]


@VIEWS
def test_modulo_expone_lo_necesario(module):
    for name in ("router", "SPEC", "SortField", "MODEL"):
        assert hasattr(module, name), f"{module.__name__} no define {name}"


@VIEWS
def test_lista_blanca_de_orden_coincide_con_spec(module):
    assert set(get_args(module.SortField)) == set(module.SPEC.sort_columns)


@VIEWS
def test_modelo_coincide_con_columnas_de_la_vista(module):
    columnas = {column.lower() for column in module.SPEC.columns}
    assert set(module.MODEL.model_fields) == columnas


@VIEWS
def test_router_bajo_v1_y_con_autenticacion(module):
    assert module.router.prefix.startswith("/v1/")
    assert any(dep.dependency is require_user for dep in module.router.dependencies)


def test_prefijos_y_vistas_no_se_repiten():
    prefixes = [m.router.prefix for m in VIEW_MODULES]
    assert len(prefixes) == len(set(prefixes))


@VIEWS
def test_todos_los_get_exigen_token(module, client):
    for route in _get_routes(module):
        path = _PATH_PARAM.sub("1", route.path)
        assert client.get(path).status_code == 401, path


@VIEWS
def test_listado_responde_con_formato_paginado(module, client, fake_db, auth):
    # total=0: solo se ejecuta el COUNT, que ya valida que los filtros del router
    # coincidan con SPEC.filters (un filtro desconocido daría 500).
    fake_db.total = 0
    response = client.get(module.router.prefix, headers=auth)
    assert response.status_code == 200, response.text
    assert response.json() == {"page": 1, "limit": 20, "total": 0, "data": []}


@VIEWS
def test_error_de_base_no_filtra_detalles(module, users_file, auth):
    fake_db = FakeDatabase()
    fake_db.error = oracledb.DatabaseError("ORA-00942: table or view does not exist")
    client = TestClient(create_app(make_settings(users_file=str(users_file)), database=fake_db))
    for route in _get_routes(module):
        path = _PATH_PARAM.sub("1", route.path)
        response = client.get(path, headers=auth)
        assert response.status_code == 500, path
        assert "ORA-" not in response.text
        assert module.SPEC.view not in response.text
