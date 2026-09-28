import pytest
import tempfile
import os
import sqlite3
import app as flask_app
from init_db import init_db

@pytest.fixture
def client():
    db_fd, db_path = tempfile.mkstemp()
    flask_app.app.config['DATABASE_PATH'] = db_path
    flask_app.app.config['TESTING'] = True

    # Inicializar BD de pruebas usando schema.sql
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")
    with open('schema.sql', 'r', encoding='utf-8') as f:
        conn.executescript(f.read())
    
    # Sembrar datos dummy
    cur = conn.cursor()
    cur.execute("INSERT INTO Partidos (nombre_equipo_a, nombre_equipo_b, fecha_partido) VALUES ('Equipo A', 'Equipo B', '2026-03-11')")
    match_id = cur.lastrowid
    cur.execute("INSERT INTO Jugadores (id_jugador, nombre, id_equipo, numero_camiseta) VALUES (1, 'Jugador A1', 'A', 10)")
    cur.execute("INSERT INTO Jugadores (id_jugador, nombre, id_equipo, numero_camiseta) VALUES (2, 'Portero B1', 'B', 12)")
    conn.commit()
    conn.close()

    with flask_app.app.test_client() as client:
        yield client

    os.close(db_fd)
    os.unlink(db_path)

def test_registro_exitoso(client):
    res = client.post('/api/event', json={
        'id_partido': 1,
        'id_jugador': 1,
        'tipo_evento': 'LANZAMIENTO_6M',
        'resultado': 'GOL',
        'tiempo_juego': '05:00',
        'client_event_id': 'evt-test-1'
    })
    assert res.status_code == 201
    json_data = res.get_json()
    assert json_data['status'] == 'success'
    assert 'event_id' in json_data

def test_tipo_evento_invalido(client):
    res = client.post('/api/event', json={
        'id_partido': 1,
        'id_jugador': 1,
        'tipo_evento': 'INVENTADO',
        'tiempo_juego': '05:00'
    })
    assert res.status_code == 400
    assert 'errors' in res.get_json()

def test_lanzamiento_exige_resultado(client):
    res = client.post('/api/event', json={
        'id_partido': 1,
        'id_jugador': 1,
        'tipo_evento': 'LANZAMIENTO_6M',
        'tiempo_juego': '05:00'
    })
    assert res.status_code == 400

def test_7m_sin_falta_avisa_pero_guarda(client):
    res = client.post('/api/event', json={
        'id_partido': 1,
        'id_jugador': 1,
        'tipo_evento': 'LANZAMIENTO_7M',
        'resultado': 'GOL',
        'tiempo_juego': '05:00',
        'client_event_id': 'evt-7m-1'
    })
    assert res.status_code == 201
    json_data = res.get_json()
    assert '7m_sin_falta' in json_data['warnings']

def test_idempotencia_mismo_client_event_id(client):
    payload = {
        'id_partido': 1,
        'id_jugador': 1,
        'tipo_evento': 'ASISTENCIA',
        'tiempo_juego': '05:00',
        'client_event_id': 'evt-unico-123'
    }
    res1 = client.post('/api/event', json=payload)
    assert res1.status_code == 201

    res2 = client.post('/api/event', json=payload)
    assert res2.status_code == 200
    assert res2.get_json().get('duplicate') is True

def test_clave_externa_rechazada(client):
    res = client.post('/api/event', json={
        'id_partido': 1,
        'id_jugador': 99999,
        'tipo_evento': 'ASISTENCIA',
        'tiempo_juego': '05:00'
    })
    assert res.status_code == 400
