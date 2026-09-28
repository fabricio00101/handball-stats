import pytest
import tempfile
import os
import sqlite3
import app as flask_app

@pytest.fixture
def client():
    db_fd, db_path = tempfile.mkstemp()
    flask_app.app.config['DATABASE_PATH'] = db_path
    flask_app.app.config['TESTING'] = True

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")
    with open('schema.sql', 'r', encoding='utf-8') as f:
        conn.executescript(f.read())
    
    cur = conn.cursor()
    cur.execute("INSERT INTO Partidos (nombre_equipo_a, nombre_equipo_b, fecha_partido) VALUES ('Equipo A', 'Equipo B', '2026-03-11')")
    cur.execute("INSERT INTO Jugadores (id_jugador, nombre, id_equipo, numero_camiseta) VALUES (1, 'Atacante A1', 'A', 10)")
    cur.execute("INSERT INTO Jugadores (id_jugador, nombre, id_equipo, numero_camiseta) VALUES (2, 'Atacante B1', 'B', 7)")
    conn.commit()
    conn.close()

    with flask_app.app.test_client() as client:
        yield client

    os.close(db_fd)
    os.unlink(db_path)

def test_estado_reconstruye_marcador_y_posesion(client):
    # Registrar 2 goles de equipo A y 1 gol de equipo B
    client.post('/api/event', json={'id_partido': 1, 'id_jugador': 1, 'tipo_evento': 'LANZAMIENTO_6M', 'resultado': 'GOL', 'tiempo_juego': '01:00', 'client_event_id': 'e1'})
    client.post('/api/event', json={'id_partido': 1, 'id_jugador': 1, 'tipo_evento': 'LANZAMIENTO_6M', 'resultado': 'GOL', 'tiempo_juego': '02:00', 'client_event_id': 'e2'})
    client.post('/api/event', json={'id_partido': 1, 'id_jugador': 2, 'tipo_evento': 'LANZAMIENTO_9M', 'resultado': 'GOL', 'tiempo_juego': '03:00', 'client_event_id': 'e3'})

    res = client.get('/api/matches/1/state')
    assert res.status_code == 200
    state = res.get_json()
    assert state['marcador_a'] == 2
    assert state['marcador_b'] == 1
    # Tras gol de B, la posesion la toma A
    assert state['posesion_actual'] == 'A'

def test_patch_match_state(client):
    res = client.patch('/api/matches/1/state', json={
        'segundos_jugados': 350,
        'periodo_actual': 1,
        'en_pausa': 0
    })
    assert res.status_code == 200

    state_res = client.get('/api/matches/1/state')
    assert state_res.get_json()['segundos_jugados'] == 350

def test_lote_con_un_invalido(client):
    lote = {
        'events': [
            {'id_partido': 1, 'id_jugador': 1, 'tipo_evento': 'ASISTENCIA', 'tiempo_juego': '05:00', 'client_event_id': 'batch-1'},
            {'id_partido': 1, 'id_jugador': 1, 'tipo_evento': 'INVENTADO', 'tiempo_juego': '05:10', 'client_event_id': 'batch-2'},
            {'id_partido': 1, 'id_jugador': 2, 'tipo_evento': 'ROBO_BALON', 'tiempo_juego': '05:20', 'client_event_id': 'batch-3'}
        ]
    }
    res = client.post('/api/events', json=lote)
    assert res.status_code == 200
    data = res.get_json()
    assert len(data['guardados']) == 2
    assert len(data['rechazados']) == 1
    assert data['rechazados'][0]['client_event_id'] == 'batch-2'
