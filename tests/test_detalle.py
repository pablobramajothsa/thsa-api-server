import pytest


def test_detalle_existente(client, fake_db, auth):
    fake_db.detail = {
        "id": 5,
        "nombre": "Arandela",
        "categoria": None,
        "precio": None,
        "fecha_alta": None,
    }
    response = client.get("/v1/productos/5", headers=auth)
    sql, binds = fake_db.last("one")

    assert response.status_code == 200
    assert response.json()["id"] == 5
    assert "WHERE ID = :item_id" in sql
    assert binds == {"item_id": 5}


@pytest.mark.parametrize("path", ["/v1/productos/999", "/v1/clientes/999"])
def test_detalle_inexistente_devuelve_404(client, fake_db, auth, path):
    fake_db.detail = None
    response = client.get(path, headers=auth)
    assert response.status_code == 404
    assert response.json() == {"detail": "Not found"}


@pytest.mark.parametrize("item_id", ["0", "-1", "abc", "1.5", "1 OR 1=1"])
def test_id_invalido_devuelve_422(client, fake_db, auth, item_id):
    response = client.get(f"/v1/productos/{item_id}", headers=auth)
    assert response.status_code == 422
    assert fake_db.calls == []
