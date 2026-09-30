import pytest
import tempfile
import os
import sqlite3
import app as flask_app
from init_db import init_db


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

def test_tercera_exclusion_genera_descalificacion(client):
    payload = {'id_partido': 1, 'id_jugador': 1, 'tipo_evento': 'EXCLUSION_2MIN', 'tiempo_juego': '01:00'}
    
    # 1ra
    res1 = client.post('/api/event', json={**payload, 'tiempo_juego': '01:00'})
    assert res1.status_code == 201
    assert not res1.get_json().get('auto_descalificacion')

    # 2da
    res2 = client.post('/api/event', json={**payload, 'tiempo_juego': '05:00'})
    assert res2.status_code == 201
    assert not res2.get_json().get('auto_descalificacion')

    # 3ra
    res3 = client.post('/api/event', json={**payload, 'tiempo_juego': '09:00'})
    assert res3.status_code == 201
    assert res3.get_json().get('auto_descalificacion') is True

    # Check export for DESCALIFICACION
    export_res = client.get('/api/matches/1/export').get_json()
    desc_events = [e for e in export_res if e['tipo_evento'] == 'DESCALIFICACION' and e['id_jugador'] == 1]
    assert len(desc_events) == 1

def test_segunda_exclusion_no_genera_nada(client):
    payload = {'id_partido': 1, 'id_jugador': 2, 'tipo_evento': 'EXCLUSION_2MIN'}
    client.post('/api/event', json={**payload, 'tiempo_juego': '01:00'})
    client.post('/api/event', json={**payload, 'tiempo_juego': '05:00'})
    
    export_res = client.get('/api/matches/1/export').get_json()
    desc_events = [e for e in export_res if e['tipo_evento'] == 'DESCALIFICACION' and e['id_jugador'] == 2]
    assert len(desc_events) == 0

def test_portero_con_dorsal_no_estandar(client):
    # Tiro de Jugador 1 (A) parado -> Portero 3 (B) que tiene dorsal 5 debe recibir paradas y GKI
    client.post('/api/event', json={
        'id_partido': 1,
        'id_jugador': 1,
        'tipo_evento': 'LANZAMIENTO_6M',
        'resultado': 'PARADA',
        'tiempo_juego': '10:00'
    })
    
    stats_res = client.get('/api/matches/1/stats')
    assert stats_res.status_code == 200
    
    jugadores = stats_res.get_json()['jugadores']
    portero = next((j for j in jugadores if j['id_jugador'] == 3), None)
    
    assert portero is not None
    assert portero['es_portero'] is True
    # If there are 2 goalkeepers in Team B (id=2 and id=3), it is assigned approximately to one of them
    assert portero['paradas'] == 1 or next(j for j in jugadores if j['id_jugador'] == 2)['paradas'] == 1
    # Check that atribucion is aproximada since there are 2 goalies
    assert portero['atribucion_portero'] == 'aproximada_equipo'

def test_periodo_se_persiste(client):
    # Simular periodo 2
    client.patch('/api/matches/1/state', json={'periodo_actual': 2, 'segundos_jugados': 1805})
    
    # Mandar evento con periodo explícito
    client.post('/api/event', json={
        'id_partido': 1,
        'id_jugador': 1,
        'tipo_evento': 'AMARILLA',
        'tiempo_juego': '30:05',
        'periodo': 2
    })
    
    # Verify the event has periodo 2
    export_res = client.get('/api/matches/1/export').get_json()
    ev = next(e for e in export_res if e['tipo_evento'] == 'AMARILLA')
    assert ev['periodo'] == 2
    
    stats_res = client.get('/api/matches/1/stats').get_json()
    assert stats_res['partido']['periodo'] == 2

def test_stats_incluye_gki_con_pesos(client):
    # Regresión: /stats debe exponer 'gki' en todos los jugadores y ponderar por distancia.
    # Una parada de 6M (peso 1.0) sobre tiro de A la ataja un portero de B.
    client.post('/api/event', json={
        'id_partido': 1, 'id_jugador': 1, 'tipo_evento': 'LANZAMIENTO_6M',
        'resultado': 'PARADA', 'tiempo_juego': '04:00', 'zona_porteria': 'TC',
        'client_event_id': 'gki-1'
    })
    jugadores = client.get('/api/matches/1/stats').get_json()['jugadores']
    assert all('gki' in j for j in jugadores)
    porteros_b = [j for j in jugadores if j['id_equipo'] == 'B' and j['es_portero']]
    assert sum(p['paradas'] for p in porteros_b) == 1
    con_parada = next(p for p in porteros_b if p['paradas'] == 1)
    assert con_parada['gki'] == 1.0  # peso 6M

def test_void_excluye_evento_completo(client):
    # Anular un gol lo borra del conteo (tiros y goles), no solo el tanto.
    client.post('/api/event', json={
        'id_partido': 1, 'id_jugador': 1, 'tipo_evento': 'LANZAMIENTO_6M',
        'resultado': 'GOL', 'tiempo_juego': '02:00', 'client_event_id': 'v-1'
    })
    j1 = next(j for j in client.get('/api/matches/1/stats').get_json()['jugadores'] if j['id_jugador'] == 1)
    assert (j1['goles'], j1['lanzamientos_totales']) == (1, 1)
    assert client.post('/api/events/v-1/void').status_code == 200
    j1 = next(j for j in client.get('/api/matches/1/stats').get_json()['jugadores'] if j['id_jugador'] == 1)
    assert (j1['goles'], j1['lanzamientos_totales']) == (0, 0)

def test_batch_void_restore_deshacer_frontend(client):
    # Contrato que usa el DESHACER del frontend: viaja como op void/restore
    # dentro del batch del OfflineQueue (funciona offline).
    client.post('/api/event', json={
        'id_partido': 1, 'id_jugador': 1, 'tipo_evento': 'LANZAMIENTO_6M',
        'resultado': 'GOL', 'tiempo_juego': '02:00', 'client_event_id': 'u-1'
    })
    r = client.post('/api/events', json={'events': [{'op': 'void', 'client_event_id': 'u-1'}]})
    assert r.status_code == 200
    assert 'u-1' in r.get_json()['guardados']
    j1 = next(j for j in client.get('/api/matches/1/stats').get_json()['jugadores'] if j['id_jugador'] == 1)
    assert (j1['goles'], j1['lanzamientos_totales']) == (0, 0)
    marc = client.get('/api/matches/1/state').get_json()
    assert (marc['marcador_a'], marc['marcador_b']) == (0, 0)
    # Revertir el deshacer también viaja por el mismo batch
    r = client.post('/api/events', json={'events': [{'op': 'restore', 'client_event_id': 'u-1'}]})
    assert 'u-1' in r.get_json()['guardados']
    j1 = next(j for j in client.get('/api/matches/1/stats').get_json()['jugadores'] if j['id_jugador'] == 1)
    assert (j1['goles'], j1['lanzamientos_totales']) == (1, 1)

def test_state_reporta_descalificados(client):
    # La roja (manual o automática) debe aparecer en el state para bloquear al jugador
    client.post('/api/event', json={
        'id_partido': 1, 'id_jugador': 1, 'tipo_evento': 'DESCALIFICACION',
        'tiempo_juego': '05:00', 'client_event_id': 'd-1'
    })
    state = client.get('/api/matches/1/state').get_json()
    assert 1 in state['descalificados']
    # Al anularla desaparece del state
    assert client.post('/api/events/d-1/void').status_code == 200
    state = client.get('/api/matches/1/state').get_json()
    assert 1 not in state['descalificados']

def test_gol_atribuye_portero_y_denominador(client):
    # El GOL con id_portero cuenta como gol recibido de ESE arquero (base del %).
    # Semilla: jugador 1 (A, campo), 2 y 3 (B, porteros).
    client.post('/api/event', json={
        'id_partido': 1, 'id_jugador': 1, 'tipo_evento': 'LANZAMIENTO_6M',
        'resultado': 'GOL', 'tiempo_juego': '02:00', 'zona_porteria': 'TC',
        'id_portero': 2, 'client_event_id': 'gk-1'
    })
    jugadores = client.get('/api/matches/1/stats').get_json()['jugadores']
    p2 = next(j for j in jugadores if j['id_jugador'] == 2)
    p3 = next(j for j in jugadores if j['id_jugador'] == 3)
    assert p2['goles_recibidos'] == 1
    assert (p2['tiros_recibidos'], p2['efectividad_portero']) == (1, 0.0)
    assert (p3['goles_recibidos'], p3['tiros_recibidos']) == (0, 0)
    # Una parada del mismo arquero: denominador 2, efectividad 50%
    client.post('/api/event', json={
        'id_partido': 1, 'id_jugador': 1, 'tipo_evento': 'LANZAMIENTO_9M',
        'resultado': 'PARADA', 'tiempo_juego': '03:00', 'zona_porteria': 'ML',
        'id_portero': 2, 'client_event_id': 'gk-2'
    })
    jugadores = client.get('/api/matches/1/stats').get_json()['jugadores']
    p2 = next(j for j in jugadores if j['id_jugador'] == 2)
    assert (p2['paradas'], p2['tiros_recibidos'], p2['efectividad_portero']) == (1, 2, 50.0)

def test_goles_sin_atribucion_mantienen_denominador(client):
    # Datos previos al fix (GOL sin id_portero): el denominador no se achica.
    client.post('/api/event', json={
        'id_partido': 1, 'id_jugador': 1, 'tipo_evento': 'LANZAMIENTO_6M',
        'resultado': 'GOL', 'tiempo_juego': '02:00', 'client_event_id': 'lg-1'
    })
    jugadores = client.get('/api/matches/1/stats').get_json()['jugadores']
    p2 = next(j for j in jugadores if j['id_jugador'] == 2)
    assert p2['goles_recibidos'] == 0
    assert p2['tiros_recibidos'] == 1  # pozo común del equipo, como antes

def test_zona_no_tiro_se_normaliza_a_null(client):
    # Un no-tiro que arrastra zona (bug del cliente) se guarda con NULL.
    client.post('/api/event', json={
        'id_partido': 1, 'id_jugador': 1, 'tipo_evento': 'PERDIDA_BALON',
        'tiempo_juego': '04:00', 'zona_porteria': 'TC', 'client_event_id': 'z-1'
    })
    client.post('/api/events', json={'events': [{
        'id_partido': 1, 'id_jugador': 1, 'tipo_evento': 'EXCLUSION_2MIN',
        'tiempo_juego': '05:00', 'zona_porteria': 'BR',
        'client_event_id': 'z-2'
    }]})
    conn = sqlite3.connect(flask_app.app.config['DATABASE_PATH'])
    conn.row_factory = sqlite3.Row
    zonas = [r['zona_porteria'] for r in conn.execute(
        "SELECT zona_porteria FROM Eventos_Juego WHERE client_event_id IN ('z-1', 'z-2') ORDER BY client_event_id")]
    conn.close()
    assert zonas == [None, None]

def _rival_generico_id():
    conn = sqlite3.connect(flask_app.app.config['DATABASE_PATH'])
    conn.row_factory = sqlite3.Row
    r = conn.execute(
        "SELECT id_jugador FROM Jugadores WHERE id_partido = 1 AND es_generico = 1 AND numero_camiseta = 0").fetchone()
    conn.close()
    return r['id_jugador']

def _arquero_a_id():
    conn = sqlite3.connect(flask_app.app.config['DATABASE_PATH'])
    conn.row_factory = sqlite3.Row
    r = conn.execute(
        "SELECT id_jugador FROM Jugadores WHERE id_partido = 1 AND id_equipo = 'A' AND posicion = 'PORTERO'").fetchone()
    conn.close()
    return r['id_jugador']

def test_tiro_rival_suma_gol_b_y_atribuye_arquero(client):
    # Modo tiro rival: actor = rival genérico, id_portero = tu arquero.
    gen, gk = _rival_generico_id(), _arquero_a_id()
    r = client.post('/api/event', json={
        'id_partido': 1, 'id_jugador': gen, 'tipo_evento': 'LANZAMIENTO_6M',
        'resultado': 'GOL', 'tiempo_juego': '06:00', 'zona_porteria': 'TC',
        'id_portero': gk, 'client_event_id': 'rv-1'
    })
    assert r.status_code == 201
    data = client.get('/api/matches/1/stats').get_json()
    eq = {e['id_equipo']: e for e in data['equipos']}
    assert (eq['A']['goles'], eq['B']['goles']) == (0, 1)
    pa = next(j for j in data['jugadores'] if j['id_jugador'] == gk)
    assert (pa['goles_recibidos'], pa['tiros_recibidos'], pa['efectividad_portero']) == (1, 1, 0.0)
    # El genérico suma al equipo pero no aparece en la tabla
    assert all(not (j.get('es_generico') == 1 and j.get('numero_camiseta') == 0) for j in data['jugadores'])

def test_fallo_cede_posesion_a_defensa(client):
    # Tras un tiro fallado el balón queda en la defensa (antes se quedaba clavada)
    client.post('/api/event', json={
        'id_partido': 1, 'id_jugador': 1, 'tipo_evento': 'LANZAMIENTO_9M',
        'resultado': 'FALLO', 'tiempo_juego': '07:00', 'client_event_id': 'rv-2'
    })
    assert client.get('/api/matches/1/state').get_json()['posesion_actual'] == 'B'

def test_botones_rival_sin_seleccion(client):
    # 2 min, pérdida y roja del rival van al genérico sin selección previa
    gen = _rival_generico_id()
    assert client.post('/api/event', json={
        'id_partido': 1, 'id_jugador': gen, 'tipo_evento': 'EXCLUSION_2MIN',
        'tiempo_juego': '08:00', 'client_event_id': 'rv-3'
    }).status_code == 201
    assert client.post('/api/event', json={
        'id_partido': 1, 'id_jugador': gen, 'tipo_evento': 'PERDIDA_BALON',
        'tiempo_juego': '09:00', 'client_event_id': 'rv-4'
    }).status_code == 201
    # La pérdida del rival nos da la posesión
    assert client.get('/api/matches/1/state').get_json()['posesion_actual'] == 'A'
    assert client.post('/api/event', json={
        'id_partido': 1, 'id_jugador': gen, 'tipo_evento': 'DESCALIFICACION',
        'tiempo_juego': '10:00', 'client_event_id': 'rv-5'
    }).status_code == 201
    assert gen in client.get('/api/matches/1/state').get_json()['descalificados']

def test_version_coincide_con_sw(client):
    # APP_VERSION (HTML + /api/version) y CACHE_NAME (sw.js) van en lockstep:
    # el handshake anti-caché depende de que sean el mismo string.
    import re
    v = client.get('/api/version').get_json()['version']
    with open('static/sw.js', 'r', encoding='utf-8') as f:
        m = re.search(r"CACHE_NAME\s*=\s*['\"]([^'\"]+)['\"]", f.read())
    assert m and m.group(1) == v
    html = client.get('/?match=1').get_data(as_text=True)
    assert f'window.APP_VERSION = "{v}"' in html

def test_state_crea_rival_generico_si_falta(client):
    # Partido sin dorsal 0: /state lo autocrea y no lo duplica al reintentar
    conn = sqlite3.connect(flask_app.app.config['DATABASE_PATH'])
    conn.execute("DELETE FROM Jugadores WHERE id_partido = 1 AND es_generico = 1 AND numero_camiseta = 0")
    conn.commit()
    conn.close()
    d1 = client.get('/api/matches/1/state').get_json()
    assert d1['rival_generico_id']
    d2 = client.get('/api/matches/1/state').get_json()
    assert d2['rival_generico_id'] == d1['rival_generico_id']

def test_stats_no_devuelve_ningun_generico(client):
    # Ni el dorsal 0 ni los 16 "Rival N": el rival no existe en /stats.
    # (El seed conserva 2 arqueros B no genéricos para los tests de atribución.)
    data = client.get('/api/matches/1/stats').get_json()
    assert all(j.get('es_generico', 0) == 0 for j in data['jugadores'])
    assert not any((j.get('nombre') or '').startswith('Rival') for j in data['jugadores'])

def test_gol_en_contra_deja_posesion_propia(client):
    # Tiro del rival (actor = genérico): el balón queda en la defensa (A)
    gen, gk = _rival_generico_id(), _arquero_a_id()
    client.post('/api/event', json={
        'id_partido': 1, 'id_jugador': gen, 'tipo_evento': 'LANZAMIENTO_6M',
        'resultado': 'GOL', 'tiempo_juego': '11:00', 'zona_porteria': 'TC',
        'id_portero': gk, 'client_event_id': 'rv-6'
    })
    assert client.get('/api/matches/1/state').get_json()['posesion_actual'] == 'A'

def _ev(eq, tipo, res=None, seg=0):
    return {'id_equipo': eq, 'tipo_evento': tipo, 'resultado': res, 'segundo_absoluto': seg}

def test_periodo_desde_segundos():
    from services.eventos import periodo_desde_segundos
    assert periodo_desde_segundos(0) == 1
    assert periodo_desde_segundos(1799) == 1
    assert periodo_desde_segundos(1800) == 2
    assert periodo_desde_segundos(3340) == 2
    assert periodo_desde_segundos(3599) == 2
    assert periodo_desde_segundos(3600) == 3
    assert periodo_desde_segundos(None) == 1

def test_patch_no_decrece_periodo(client):
    # Servidor en 2: un cliente stale mandando 1 no lo puede pisar
    client.patch('/api/matches/1/state', json={'periodo_actual': 2, 'segundos_jugados': 1805})
    client.patch('/api/matches/1/state', json={'periodo_actual': 1, 'segundos_jugados': 100})
    st = client.get('/api/matches/1/state').get_json()
    assert st['periodo_actual'] == 2

def test_evento_corrige_periodo_desde_tiempo(client):
    # Cliente con período clavado en 1 pero tiempo de 2ª parte: el servidor deriva 2
    # y el segundo_absoluto queda absoluto (sin doble offset de 1800).
    client.post('/api/event', json={
        'id_partido': 1, 'id_jugador': 1, 'tipo_evento': 'LANZAMIENTO_9M',
        'resultado': 'GOL', 'tiempo_juego': '32:01', 'periodo': 1,
        'client_event_id': 'per-1'
    })
    export_res = client.get('/api/matches/1/export').get_json()
    ev = next(e for e in export_res if e.get('client_event_id') == 'per-1')
    assert ev['periodo'] == 2
    assert ev['segundo_absoluto'] == 1921

def test_replay_vacio():
    from services.eventos import derivar_posesiones
    r = derivar_posesiones([])
    assert r['posesion_actual'] == 'A'
    assert r['ataques'] == {'A': 0, 'B': 0}
    assert r['bloques'] == []
    assert [v['etiqueta'] for v in r['ventanas']] == ['1T', '2T', 'Prórroga', "Últimos 10'", "Últimos 5'"]

def test_replay_ataques_y_posesion():
    from services.eventos import derivar_posesiones
    # A marca -> B falla -> A pierde -> B marca: 3 ataques A, 2 ataques B
    evs = [
        _ev('A', 'LANZAMIENTO_6M', 'GOL', 60),
        _ev('B', 'LANZAMIENTO_9M', 'FALLO', 120),
        _ev('A', 'PERDIDA_BALON', None, 180),
        _ev('B', 'LANZAMIENTO_7M', 'GOL', 240),
    ]
    r = derivar_posesiones(evs)
    assert r['posesion_actual'] == 'A'
    assert r['ataques'] == {'A': 3, 'B': 2}
    b = r['bloques'][0]
    assert b['etiqueta'] == '0–10'
    assert (b['A']['goles'], b['A']['tiros'], b['A']['perdidas'], b['A']['ataques']) == (1, 1, 1, 3)
    assert (b['B']['goles'], b['B']['tiros'], b['B']['perdidas'], b['B']['ataques']) == (1, 2, 0, 2)

def test_replay_evento_neutro_no_mueve_posesion(client):
    # Gol de A (posesión B) + amarilla a A: /state debe seguir en B
    # (con "mirar el último evento" devolvería A por defecto: el bug viejo)
    client.post('/api/event', json={
        'id_partido': 1, 'id_jugador': 1, 'tipo_evento': 'LANZAMIENTO_9M',
        'resultado': 'GOL', 'tiempo_juego': '12:00', 'client_event_id': 'rp-1'
    })
    client.post('/api/event', json={
        'id_partido': 1, 'id_jugador': 1, 'tipo_evento': 'AMARILLA',
        'tiempo_juego': '12:30', 'client_event_id': 'rp-2'
    })
    assert client.get('/api/matches/1/state').get_json()['posesion_actual'] == 'B'

def test_stats_trae_ataques_y_bloques(client):
    data = client.get('/api/matches/1/stats').get_json()
    eq = {e['id_equipo']: e for e in data['equipos']}
    for e in eq.values():
        for k in ('ataques', 'eficacia_ataque', 'tiros_por_ataque', 'perdidas_por_ataque', 'perdidas'):
            assert k in e, k
    assert 'bloques' in data
    tot_ataques = sum(b['A']['ataques'] + b['B']['ataques'] for b in data['bloques'])
    assert tot_ataques == eq['A']['ataques'] + eq['B']['ataques']
    tot_goles = sum(b['A']['goles'] + b['B']['goles'] for b in data['bloques'])
    assert tot_goles == eq['A']['goles'] + eq['B']['goles']

def test_replay_paradas_y_ventanas():
    from services.eventos import derivar_posesiones
    # Tiro parado en 2T: la parada suma al equipo defensor; ventanas agregan
    evs = [
        {'id_equipo': 'A', 'tipo_evento': 'LANZAMIENTO_6M', 'resultado': 'GOL', 'segundo_absoluto': 60},
        {'id_equipo': 'B', 'tipo_evento': 'LANZAMIENTO_9M', 'resultado': 'PARADA', 'segundo_absoluto': 1900},
        {'id_equipo': 'B', 'tipo_evento': 'PARADA_PORTERO', 'resultado': None, 'segundo_absoluto': 2000},
    ]
    r = derivar_posesiones(evs)
    t2 = next(v for v in r['ventanas'] if v['etiqueta'] == '2T')
    assert t2['A']['paradas'] == 1   # paró el tiro de B
    assert t2['B']['paradas'] == 1   # PARADA_PORTERO propia
    assert t2['B']['tiros'] == 1
    t1 = next(v for v in r['ventanas'] if v['etiqueta'] == '1T')
    assert (t1['A']['goles'], t1['A']['tiros']) == (1, 1)
    u10 = next(v for v in r['ventanas'] if v['etiqueta'] == "Últimos 10'")
    assert u10['B']['tiros'] == 1 and u10['A']['goles'] == 0  # gol@60 fuera de ventana
    pro = next(v for v in r['ventanas'] if v['etiqueta'] == 'Prórroga')
    assert pro['A']['ataques'] == 0 and pro['B']['ataques'] == 0

def test_subtipo_lanzamiento():
    from services.eventos import subtipo_lanzamiento as st
    assert st({'tipo_evento': 'LANZAMIENTO', 'es_contraataque': 1}) == 'CONTRAATAQUE'
    assert st({'tipo_evento': 'LANZAMIENTO', 'es_7m': 1}) == '7M'
    assert st({'tipo_evento': 'LANZAMIENTO', 'distancia': '9M'}) == '9M'
    assert st({'tipo_evento': 'LANZAMIENTO'}) == 'OTRO'
    assert st({'tipo_evento': 'LANZAMIENTO_6M'}) == '6M'
    assert st({'tipo_evento': 'LANZAMIENTO_7M'}) == '7M'
    assert st({'tipo_evento': 'CONTRAATAQUE'}) == 'CONTRAATAQUE'
    assert st({'tipo_evento': 'LANZAMIENTO', 'es_7m': '0', 'distancia': None}) == 'OTRO'

def test_stats_nivel_a(client):
    # Claves nuevas de equipo + ventanas + tipos en /stats
    client.post('/api/event', json={
        'id_partido': 1, 'id_jugador': 1, 'tipo_evento': 'LANZAMIENTO',
        'resultado': 'GOL', 'tiempo_juego': '05:00', 'distancia': '6M',
        'client_event_id': 'na-1'
    })
    client.post('/api/event', json={
        'id_partido': 1, 'id_jugador': 1, 'tipo_evento': 'LANZAMIENTO',
        'resultado': 'FALLO', 'tiempo_juego': '06:00', 'distancia': '9M',
        'client_event_id': 'na-2'
    })
    client.post('/api/event', json={
        'id_partido': 1, 'id_jugador': 1, 'tipo_evento': 'ASISTENCIA',
        'tiempo_juego': '06:30', 'client_event_id': 'na-3'
    })
    data = client.get('/api/matches/1/stats').get_json()
    eq = {e['id_equipo']: e for e in data['equipos']}
    a = eq['A']
    for k in ('asistencias', 'robos', 'bloqueos', 'tiros_fallados',
              'tiros_detenidos', 'tasa_fallados', 'tasa_detenidos',
              'lanzamientos_por_tipo'):
        assert k in a, k
    assert a['asistencias'] == 1
    assert a['tiros_fallados'] == 1 and a['tasa_fallados'] == 50.0
    assert a['lanzamientos_por_tipo']['6M'] == {'tiros': 1, 'goles': 1}
    assert a['lanzamientos_por_tipo']['9M'] == {'tiros': 1, 'goles': 0}
    assert [v['etiqueta'] for v in data['ventanas']] == ['1T', '2T', 'Prórroga', "Últimos 10'", "Últimos 5'"]
    t1 = next(v for v in data['ventanas'] if v['etiqueta'] == '1T')
    assert t1['A']['goles'] == 1 and t1['A']['tiros'] == 2

def test_contexto_7m_unitario():
    from services.eventos import derivar_contexto_7m as f
    evs = [
        {'id_equipo': 'A', 'tipo_evento': 'LANZAMIENTO_6M', 'resultado': 'GOL', 'segundo_absoluto': 60},
        {'id_equipo': 'B', 'tipo_evento': 'LANZAMIENTO_9M', 'resultado': 'GOL', 'segundo_absoluto': 120},
        {'id_equipo': 'A', 'tipo_evento': 'LANZAMIENTO', 'resultado': 'GOL', 'es_7m': 1, 'segundo_absoluto': 300},
        {'id_equipo': 'B', 'tipo_evento': 'LANZAMIENTO_7M', 'resultado': 'FALLO', 'segundo_absoluto': 1900},
    ]
    r = f(evs)
    assert (r['A']['tiros'], r['A']['goles']) == (1, 1)
    assert r['A']['contextos']['empatado'] == {'tiros': 1, 'goles': 1}  # 1-1 previo
    assert r['B']['contextos']['empatado'] == {'tiros': 0, 'goles': 0}  # 1-2 previo
    assert r['B']['contextos']['ajustado'] == {'tiros': 1, 'goles': 0}  # |−1| ≤ 2
    assert r['B']['contextos']['2T'] == {'tiros': 1, 'goles': 0}
    assert r['A']['contextos']['1T'] == {'tiros': 1, 'goles': 1}
    assert f([])['A']['contextos']['ajustado'] == {'tiros': 0, 'goles': 0}

def test_stats_contexto_7m(client):
    client.post('/api/event', json={
        'id_partido': 1, 'id_jugador': 1, 'tipo_evento': 'LANZAMIENTO',
        'resultado': 'GOL', 'tiempo_juego': '05:00', 'es_7m': 1,
        'client_event_id': 'c7-1'
    })
    client.post('/api/event', json={
        'id_partido': 1, 'id_jugador': 1, 'tipo_evento': 'LANZAMIENTO_7M',
        'resultado': 'FALLO', 'tiempo_juego': '06:00',
        'client_event_id': 'c7-2'
    })
    data = client.get('/api/matches/1/stats').get_json()
    c7 = data['contexto_7m']['A']
    assert (c7['tiros'], c7['goles'], c7['eficacia']) == (2, 1, 50.0)
    assert c7['contextos']['empatado'] == {'tiros': 1, 'goles': 1, 'eficacia': 100.0}  # 0-0 previo
    assert c7['contextos']['ajustado']['tiros'] == 2
    assert c7['contextos']['1T']['tiros'] == 2
    assert set(c7['contextos']) == {'empatado', 'ajustado', '1T', '2T', 'Prórroga', "últimos 5'"}

def test_borrar_equipo_sin_partidos(client):
    # Crear -> borrar (200) -> ya no lista -> segundo DELETE 404
    r = client.post('/api/equipos', json={'nombre': 'Equipo Temporal', 'es_propio': 0})
    assert r.status_code == 201
    eid = r.get_json()['id_equipo']
    assert any(e['id_equipo'] == eid for e in client.get('/api/equipos').get_json())
    assert client.delete(f'/api/equipos/{eid}').status_code == 200
    assert not any(e['id_equipo'] == eid for e in client.get('/api/equipos').get_json())
    assert client.delete(f'/api/equipos/{eid}').status_code == 404
    assert client.delete('/api/equipos/99999').status_code == 404

def test_borrar_equipo_con_partidos_bloqueado(client):
    # El fixture tiene el partido 1 con 'Equipo A': el borrado debe bloquearse
    eq_a = next(e for e in client.get('/api/equipos').get_json() if e['nombre'] == 'Equipo A')
    r = client.delete(f"/api/equipos/{eq_a['id_equipo']}")
    assert r.status_code == 409
    assert 'partido' in r.get_json()['error']
    # El equipo y su plantel siguen intactos
    assert any(e['id_equipo'] == eq_a['id_equipo'] for e in client.get('/api/equipos').get_json())
    assert len(client.get(f"/api/equipos/{eq_a['id_equipo']}/plantel").get_json()) > 0

