import threading
import time

import pytest

from app.pool import ConnectionPool, PoolTimeoutError


class FakeConn:
    _next_id = 0

    def __init__(self) -> None:
        FakeConn._next_id += 1
        self.id = FakeConn._next_id
        self.valid = True
        self.closed = False


def make_pool(**overrides):
    created: list[FakeConn] = []

    def factory() -> FakeConn:
        conn = FakeConn()
        created.append(conn)
        return conn

    options = {
        "validate": lambda c: c.valid and not c.closed,
        "close": lambda c: setattr(c, "closed", True),
        "min_size": 1,
        "max_size": 2,
        "wait_timeout_s": 0.2,
        "validate_after_s": 0.0,
    }
    options.update(overrides)
    return ConnectionPool(factory, **options), created


def test_open_crea_minimo_y_reutiliza():
    pool, created = make_pool(min_size=2)
    pool.open()
    assert len(created) == 2
    with pool.acquire() as conn:
        assert conn in created
    with pool.acquire():
        pass
    assert len(created) == 2


def test_no_supera_el_maximo_y_espera_con_timeout():
    pool, created = make_pool(max_size=2, wait_timeout_s=0.1)
    with pool.acquire(), pool.acquire():
        started = time.monotonic()
        with pytest.raises(PoolTimeoutError), pool.acquire():
            pass
        assert time.monotonic() - started >= 0.1
    assert len(created) == 2


def test_conexion_muerta_se_descarta():
    pool, created = make_pool()
    pool.open()
    created[0].valid = False
    with pool.acquire() as conn:
        assert conn is not created[0]
    assert created[0].closed


def test_tras_error_conexion_viva_vuelve_al_pool():
    pool, _ = make_pool()
    with pytest.raises(RuntimeError), pool.acquire():
        raise RuntimeError("falla la consulta")
    assert pool.idle_count == 1


def test_tras_error_conexion_rota_se_cierra():
    pool, _ = make_pool()
    with pytest.raises(RuntimeError), pool.acquire() as conn:
        conn.valid = False
        raise RuntimeError("se cortó la red")
    assert pool.idle_count == 0
    assert conn.closed


def test_error_al_crear_conexion_libera_el_lugar():
    calls = {"n": 0}

    def flaky() -> FakeConn:
        calls["n"] += 1
        if calls["n"] <= 2:
            raise ConnectionError("base caída")
        return FakeConn()

    pool = ConnectionPool(
        flaky,
        validate=lambda c: True,
        close=lambda c: None,
        min_size=0,
        max_size=1,
        wait_timeout_s=0.1,
    )
    for _ in range(2):
        with pytest.raises(ConnectionError), pool.acquire():
            pass
    with pool.acquire() as conn:  # el lugar no quedó tomado
        assert isinstance(conn, FakeConn)


def test_close_cierra_ociosas_y_rechaza_nuevos_pedidos():
    pool, created = make_pool(min_size=2)
    pool.open()
    pool.close()
    assert all(c.closed for c in created)
    with pytest.raises(RuntimeError), pool.acquire():
        pass


def test_uso_concurrente():
    pool, created = make_pool(max_size=3, wait_timeout_s=5)
    in_use = []
    peak = []
    lock = threading.Lock()

    def worker():
        for _ in range(20):
            with pool.acquire() as conn:
                with lock:
                    in_use.append(conn)
                    peak.append(len(in_use))
                time.sleep(0.001)
                with lock:
                    in_use.remove(conn)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert max(peak) <= 3
    assert len(created) <= 3
