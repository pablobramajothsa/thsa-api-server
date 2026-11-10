import logging

import oracledb
import pytest

ORA_MESSAGE = "ORA-00942: table or view does not exist"


@pytest.mark.parametrize("path", ["/v1/productos", "/v1/productos/1", "/v1/clientes"])
def test_error_de_oracle_no_filtra_texto_ora(client, fake_db, auth, caplog, path):
    caplog.set_level(logging.ERROR, logger="api.error")
    fake_db.error = oracledb.DatabaseError(ORA_MESSAGE)

    response = client.get(path, headers=auth)

    assert response.status_code == 500
    assert "ORA-" not in response.text
    assert "V_PRODUCTOS" not in response.text
    body = response.json()
    assert body["detail"] == "Internal server error"
    assert body["request_id"] == response.headers["X-Request-ID"]
    # El detalle queda en el log interno, asociado al mismo request id.
    logged = [r for r in caplog.records if r.name == "api.error"]
    assert logged
    assert logged[-1].request_id == body["request_id"]
    assert ORA_MESSAGE in caplog.text


def test_error_inesperado_responde_generico(client, fake_db, auth):
    fake_db.error = RuntimeError("detalle interno sensible")
    response = client.get("/v1/productos", headers=auth)

    assert response.status_code == 500
    assert "sensible" not in response.text
    assert response.json()["request_id"] == response.headers["X-Request-ID"]


def test_health_con_base_caida_no_expone_detalles(client, fake_db):
    fake_db.error = oracledb.DatabaseError("ORA-12541: TNS:no listener")
    response = client.get("/health")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}
    assert "ORA-" not in response.text
