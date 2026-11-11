"""Registro de routers.

Para publicar una vista nueva, agregar su módulo a VIEW_MODULES (ver docs/GUIA_NUEVA_API.md).
Todo módulo de VIEW_MODULES se registra en la app y pasa por los tests de contrato de
tests/test_contratos.py (lista blanca de orden, modelo alineado con la vista, autenticación).

Cada módulo de vista debe exponer:
    router     APIRouter con prefix "/v1/<recurso>" y dependencies=[Depends(require_user)]
    SPEC       ViewSpec con la vista, columnas, id, orden y filtros
    SortField  Literal con los nombres públicos de SPEC.sort_columns
    MODEL      modelo Pydantic de una fila (campos = columnas en minúsculas)
"""

from types import ModuleType

from app.routers import (
    auth,
    campos,
    campos_plantas_distancias,
    campos_productores,
    catac,
    choferes,
    choferes_activos,
    choferes_no_activos,
    clientes,
    compras_pendientes_facturas,
    compras_pendientes_ncnd,
    empresas_transporte,
    health,
    impuestos_regimenes,
    plantas,
    productores,
    productos,
)

# Routers sin vista (no pasan por los tests de contrato de vistas).
BASE_MODULES: tuple[ModuleType, ...] = (health, auth)

# Una entrada por vista publicada, en el orden en que aparecen en /docs.
VIEW_MODULES: tuple[ModuleType, ...] = (
    campos,
    productos,
    clientes,
    campos_plantas_distancias,
    campos_productores,
    catac,
    choferes,
    choferes_activos,
    choferes_no_activos,
    compras_pendientes_facturas,
    compras_pendientes_ncnd,
    empresas_transporte,
    impuestos_regimenes,
    plantas,
    productores,
)
