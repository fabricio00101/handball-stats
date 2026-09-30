import pytest
import tempfile
import os
import sqlite3
import app as flask_app


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

def test_posesion_tras_parada_es_del_portero(client):
    # Tiro del equipo A parado -> posesión del equipo B
    client.post('/api/event', json={'id_partido': 1, 'id_jugador': 1,
        'tipo_evento': 'LANZAMIENTO_6M', 'resultado': 'PARADA',
        'tiempo_juego': '04:00', 'client_event_id': 'p1'})
    state = client.get('/api/matches/1/state').get_json()
    assert state['posesion_actual'] == 'B'

def test_exclusiones_activas_en_state(client):
    # Insertar exclusión en 01:00 (60s)
    client.post('/api/event', json={'id_partido': 1, 'id_jugador': 1,
        'tipo_evento': 'EXCLUSION_2MIN', 'tiempo_juego': '01:00', 'client_event_id': 'excl1'})
    
    # Simular que el partido va por 150s (02:30)
    client.patch('/api/matches/1/state', json={'segundos_jugados': 150})
    
    state = client.get('/api/matches/1/state').get_json()
    activas = state['exclusiones_activas']
    
    # 150s actuales - 60s exclusión = 90s cumplidos. Restan 30s.
    assert len(activas) == 1
    assert activas[0]['id_jugador'] == 1
    assert activas[0]['segundos_restantes'] == 30
