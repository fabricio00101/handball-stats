"""
Herramienta de portería: el punto del tiro, el cuadrante que se deriva de él y
el tipo de partido que sostiene la captura.

El punto del tiro (coordenada_x/y) es la fuente de verdad. zona_origen y
distancia son derivados: se guardan igual como columnas para que las consultas
por franja sigan siendo un GROUP BY de texto y no una cuenta de flotantes.
"""
import pytest

from services.eventos import (
    zona_origen_desde_coordenada,
    distancia_desde_coordenada,
    normalizar_evento_legacy,
    validar_evento,
    ANCHO_MEDIA_CANCHA,
    LARGO_MEDIA_CANCHA,
)


def _partido_porteria(client, nombre='San Roque', rival='ABC'):
    """Partido de portería con un portero propio y el rival genérico."""
    eq = client.post('/api/equipos', json={'nombre': nombre, 'es_propio': 1}).get_json()['id_equipo']
    r = client.post('/api/matches', json={
        'tipo_partido': 'PORTERIA',
        'id_equipo_a': eq,
        'rival': rival,
        'fecha_partido': '2024-01-01',
        'convocatoria': [
            {'nombre': 'Arquero Uno', 'numero_camiseta': 1, 'posicion': 'PORTERO'},
            {'nombre': 'Arquero Dos', 'numero_camiseta': 12, 'posicion': 'PORTERO'},
        ]
    })
    assert r.status_code == 201, r.get_json()
    return r.get_json()['id_partido']


def _ids(client, id_partido):
    """(id del portero 1, id del portero 12, id del rival genérico)."""
    import app as flask_app
    with flask_app.app.app_context():
        from db import get_db_connection
        with get_db_connection() as c:
            filas = c.execute(
                'SELECT id_jugador, numero_camiseta FROM Jugadores WHERE id_partido = ? ORDER BY numero_camiseta',
                (id_partido,)
            ).fetchall()
    portero1 = next(f['id_jugador'] for f in filas if f['numero_camiseta'] == 1)
    portero12 = next(f['id_jugador'] for f in filas if f['numero_camiseta'] == 12)
    rival = next(f['id_jugador'] for f in filas if f['numero_camiseta'] == 0)
    return portero1, portero12, rival


# --------------------------------------------------------------------------
# La grilla: los mismos 9 códigos del arco, leídos como distancia + lateral
# --------------------------------------------------------------------------

@pytest.mark.parametrize('x, y, esperado', [
    (0.0, 1.0, 'BC'),      # pegado al arco, al medio
    (-5.0, 4.0, 'BL'),     # pegado al arco, extremo izquierdo
    (5.0, 4.0, 'BR'),      # pegado al arco, extremo derecho
    (0.0, 7.0, 'MC'),      # entre 6 y 9
    (-7.0, 8.5, 'ML'),     # entre 6 y 9, izquierda
    (0.0, 12.0, 'TC'),     # más de 9
    (-8.0, 18.0, 'TL'),    # extremo izquierdo, al fondo
    (8.0, 15.0, 'TR'),     # extremo derecho, al fondo
])
def test_zona_origen_desde_coordenada(x, y, esperado):
    assert zona_origen_desde_coordenada(x, y) == esperado


@pytest.mark.parametrize('y, esperado', [
    (0.0, '6M'),
    (5.9, '6M'),
    (6.0, '9M'),
    (8.99, '9M'),
    (9.0, None),      # más de 9 no es 6 ni 9: el tiro viene de otra parte
    (20.0, None),
])
def test_distancia_desde_coordenada(y, esperado):
    assert distancia_desde_coordenada(y) == esperado


def test_los_cortes_de_franja_caen_en_6_y_9():
    """El corte entre franjas tiene que estar en la línea, no en el medio de la celda.

    Un punto a 5,99 m y otro a 6,01 m dan cuadrantes distintos; si el corte
    estuviera a 4,5 m estaríamos metiendo en la franja de 9 m lo que el jugador
    vio como zona de 6.
    """
    assert zona_origen_desde_coordenada(0, 5.99) != zona_origen_desde_coordenada(0, 6.01)
    assert zona_origen_desde_coordenada(0, 8.99) != zona_origen_desde_coordenada(0, 9.01)


def test_las_columnas_se_cortan_en_un_tercio_del_ancho():
    """El ancho de la franja defensiva, no el del arco (3 m no divide en tres)."""
    assert zona_origen_desde_coordenada(-9.0, 15.0) == 'TL'
    assert zona_origen_desde_coordenada(-3.4, 15.0) == 'TL'    # el tercio es 3,33
    assert zona_origen_desde_coordenada(-3.2, 15.0) == 'TC'
    assert zona_origen_desde_coordenada(3.4, 15.0) == 'TR'


# --------------------------------------------------------------------------
# Normalización: el punto manda, loderivado no se inventa
# --------------------------------------------------------------------------

def test_normalizar_deriva_cuadrante_y_distancia():
    d = normalizar_evento_legacy({
        'id_partido': 1, 'id_jugador': 1, 'tipo_evento': 'LANZAMIENTO',
        'resultado': 'PARADA', 'tiempo_juego': '05:00',
        'coordenada_x': -7.5, 'coordenada_y': 3.2,
    })
    assert d['zona_origen'] == 'BL'
    assert d['distancia'] == '6M'


def test_normalizar_el_punto_manda_sobre_lo_que_viene_del_cliente():
    """Si el cliente manda un cuadrante que no corresponde al punto, manda el punto."""
    d = normalizar_evento_legacy({
        'id_partido': 1, 'id_jugador': 1, 'tipo_evento': 'LANZAMIENTO',
        'resultado': 'GOL', 'tiempo_juego': '05:00',
        'coordenada_x': 8.0, 'coordenada_y': 14.0,
        'zona_origen': 'BC', 'distancia': '6M',
    })
    assert d['zona_origen'] == 'TR'
    assert d['distancia'] is None


def test_normalizar_sin_punto_no_inventa_cuadrante():
    d = normalizar_evento_legacy({
        'id_partido': 1, 'id_jugador': 1, 'tipo_evento': 'LANZAMIENTO',
        'resultado': 'GOL', 'tiempo_juego': '05:00',
        'zona_porteria': 'TC',
    })
    # Sin punto no hay de dónde sacar el cuadrante: la clave ni se toca.
    assert d.get('zona_origen') is None
    assert d.get('distancia') is None


def test_normalizar_borra_el_punto_en_un_evento_que_no_es_lanzamiento():
    """Un robo no sale de un punto de la media cancha. Se limpia, no se rechaza:
    la captura en vivo nunca se bloquea por un valor stale."""
    d = normalizar_evento_legacy({
        'id_partido': 1, 'id_jugador': 1, 'tipo_evento': 'ROBO_BALON',
        'tiempo_juego': '05:00',
        'coordenada_x': -7.0, 'coordenada_y': 4.0, 'zona_origen': 'BL',
        'zona_porteria': 'TC',
    })
    assert d['coordenada_x'] is None
    assert d['coordenada_y'] is None
    assert d['zona_origen'] is None
    assert d['zona_porteria'] is None


def test_normalizar_7m_conserva_el_punto():
    """El penalti sí sale de un punto, y es siempre el mismo: 7 m al medio."""
    d = normalizar_evento_legacy({
        'id_partido': 1, 'id_jugador': 1, 'tipo_evento': 'LANZAMIENTO',
        'es_7m': 1, 'resultado': 'PARADA', 'tiempo_juego': '05:00',
        'coordenada_x': 0.0, 'coordenada_y': 7.0,
    })
    assert d['es_7m'] == 1
    assert d['zona_origen'] == 'MC'


def test_normalizar_7m_no_guarda_9m_en_un_penalti():
    """Un penalti cae dentro de la franja de 9, pero no salió a 9 m.

    Sin esto la columna distancia dice '9M' de un tiro a 7 m, y el peso del GKI
    (PESOS_GKI) queda contando un penalti como si fuera un tiro de media.
    """
    d = normalizar_evento_legacy({
        'id_partido': 1, 'id_jugador': 1, 'tipo_evento': 'LANZAMIENTO',
        'es_7m': 1, 'resultado': 'PARADA', 'tiempo_juego': '05:00',
        'coordenada_x': 0.0, 'coordenada_y': 7.0,
    })
    assert d['distancia'] == '7M'


def test_normalizar_7m_acepta_el_flag_como_uno_en_texto():
    """La captura manda 1 como número, pero un cliente viejo o un reenvío de la
    cola pueden mandarlo como '1'. Es el mismo tiro."""
    d = normalizar_evento_legacy({
        'id_partido': 1, 'id_jugador': 1, 'tipo_evento': 'LANZAMIENTO',
        'es_7m': '1', 'resultado': 'PARADA', 'tiempo_juego': '05:00',
        'coordenada_x': 0.0, 'coordenada_y': 7.0,
    })
    assert d['distancia'] == '7M'


def test_normalizar_sacar_el_7m_devuelve_la_franja_real():
    """Apagar el flag tiene que devolver el tiro a su banda por punto."""
    d = normalizar_evento_legacy({
        'id_partido': 1, 'id_jugador': 1, 'tipo_evento': 'LANZAMIENTO',
        'es_7m': 0, 'resultado': 'PARADA', 'tiempo_juego': '05:00',
        'coordenada_x': 0.0, 'coordenada_y': 7.0,
    })
    assert d['distancia'] == '9M'


def test_sin_punto_no_hay_franja_aunque_sea_7m():
    """Sin punto no se inventa nada, tampoco la franja del penalti."""
    d = normalizar_evento_legacy({
        'id_partido': 1, 'id_jugador': 1, 'tipo_evento': 'LANZAMIENTO',
        'es_7m': 1, 'resultado': 'PARADA', 'tiempo_juego': '05:00',
    })
    assert d.get('distancia') is None


# --------------------------------------------------------------------------
# Validación: el punto tiene que estar en la cancha
# --------------------------------------------------------------------------

def _evento(**extra):
    base = {'id_partido': 1, 'id_jugador': 1, 'tipo_evento': 'LANZAMIENTO',
            'resultado': 'GOL', 'tiempo_juego': '05:00'}
    base.update(extra)
    return normalizar_evento_legacy(base)


def test_valida_punto_dentro_de_la_cancha():
    errores, _ = validar_evento(_evento(coordenada_x=0.0, coordenada_y=20.0))
    assert errores == []


@pytest.mark.parametrize('x, y', [
    (10.5, 5.0),    # más de 10 m del eje: no hay cancha ahí
    (-10.5, 5.0),
    (0.0, -0.1),    # detrás de la línea de fondo
    (0.0, 20.5),    # del otro lado del medio
])
def test_valida_rechaza_punto_fuera_de_la_cancha(x, y):
    errores, _ = validar_evento(_evento(coordenada_x=x, coordenada_y=y))
    assert errores
    assert 'fuera de la media cancha' in errores[0]


def test_valida_rechaza_coordenadas_sueltas():
    """Medio punto no es un punto: es un dato que no se sabe de dónde salió."""
    errores, _ = validar_evento(_evento(coordenada_x=4.0, coordenada_y=None))
    assert errores
    assert 'de a pares' in errores[0]


def test_valida_rechaza_cuadrante_inventado():
    errores, _ = validar_evento(_evento(zona_origen='ZZ'))
    assert errores
    assert 'cuadrante de origen' in errores[0]


# --------------------------------------------------------------------------
# Punta a punta: el cuadrante derivado llega a la base por los dos caminos
# --------------------------------------------------------------------------

def test_evento_guarda_el_cuadrante_derivado(client):
    id_partido = _partido_porteria(client)
    portero, _, rival = _ids(client, id_partido)

    r = client.post('/api/event', json={
        'id_partido': id_partido,
        'id_jugador': rival,
        'tipo_evento': 'LANZAMIENTO',
        'resultado': 'PARADA',
        'tiempo_juego': '05:00',
        'id_portero': portero,
        'coordenada_x': -7.5,
        'coordenada_y': 3.2,
        'zona_porteria': 'ML',
        'client_event_id': 'pt-1',
    })
    assert r.status_code == 201, r.get_json()

    import app as flask_app
    with flask_app.app.app_context():
        from db import get_db_connection
        with get_db_connection() as c:
            ev = c.execute(
                'SELECT * FROM Eventos_Juego WHERE client_event_id = ?', ('pt-1',)
            ).fetchone()
    assert ev['zona_origen'] == 'BL'
    assert ev['distancia'] == '6M'
    assert ev['coordenada_x'] == -7.5
    assert ev['id_portero'] == portero


def test_lote_offline_guarda_el_cuadrante(client):
    """El camino del lote es el que usa la cola cuando no hay red. Si el
    cuadrante no estuviera en su INSERT, se perdería al sincronizar."""
    id_partido = _partido_porteria(client)
    _, _, rival = _ids(client, id_partido)

    r = client.post('/api/events', json={'events': [{
        'id_partido': id_partido,
        'id_jugador': rival,
        'tipo_evento': 'LANZAMIENTO',
        'resultado': 'FALLO',
        'tiempo_juego': '06:00',
        'coordenada_x': 2.0,
        'coordenada_y': 11.0,
        'client_event_id': 'pt-lote-1',
    }]})
    assert r.status_code == 200, r.get_json()
    assert r.get_json()['rechazados'] == []

    import app as flask_app
    with flask_app.app.app_context():
        from db import get_db_connection
        with get_db_connection() as c:
            ev = c.execute(
                'SELECT * FROM Eventos_Juego WHERE client_event_id = ?', ('pt-lote-1',)
            ).fetchone()
    assert ev['zona_origen'] == 'TC'


def test_patch_que_mueve_el_tiro_recalcula_el_cuadrante(client):
    """Si se corrige el punto, el cuadrante no puede quedar diciendo dónde
    estaba el tiro antes del arreglo."""
    id_partido = _partido_porteria(client)
    _, _, rival = _ids(client, id_partido)

    client.post('/api/event', json={
        'id_partido': id_partido, 'id_jugador': rival,
        'tipo_evento': 'LANZAMIENTO', 'resultado': 'GOL',
        'tiempo_juego': '05:00',
        'coordenada_x': 0.0, 'coordenada_y': 4.0,
        'client_event_id': 'pt-2',
    })

    r = client.patch('/api/events/pt-2', json={'coordenada_x': -8.0, 'coordenada_y': 15.0})
    assert r.status_code == 200, r.get_json()

    import app as flask_app
    with flask_app.app.app_context():
        from db import get_db_connection
        with get_db_connection() as c:
            ev = c.execute(
                'SELECT * FROM Eventos_Juego WHERE client_event_id = ?', ('pt-2',)
            ).fetchone()
    assert ev['zona_origen'] == 'TL'
    assert ev['distancia'] is None


def test_patch_rechaza_mover_el_tiro_fuera_de_la_cancha(client):
    id_partido = _partido_porteria(client)
    _, _, rival = _ids(client, id_partido)

    client.post('/api/event', json={
        'id_partido': id_partido, 'id_jugador': rival,
        'tipo_evento': 'LANZAMIENTO', 'resultado': 'GOL',
        'tiempo_juego': '05:00',
        'coordenada_x': 0.0, 'coordenada_y': 4.0,
        'client_event_id': 'pt-3',
    })

    r = client.patch('/api/events/pt-3', json={'coordenada_x': 40.0, 'coordenada_y': 4.0})
    assert r.status_code == 400


# --------------------------------------------------------------------------
# El endpoint de analisis
# --------------------------------------------------------------------------

def _tiro(client, id_partido, rival, portero, resultado, x, y, zona_arco, n, **extra):
    payload = {
        'id_partido': id_partido, 'id_jugador': rival,
        'tipo_evento': 'LANZAMIENTO', 'resultado': resultado,
        'tiempo_juego': '05:00', 'id_portero': portero,
        'coordenada_x': x, 'coordenada_y': y, 'zona_porteria': zona_arco,
        'client_event_id': f'ev-{n}',
    }
    payload.update(extra)
    r = client.post('/api/event', json=payload)
    assert r.status_code == 201, r.get_json()


def test_analisis_rechaza_un_partido_que_no_es_de_porteria(client):
    id_partido = _partido_analisis(client)
    r = client.get(f'/api/matches/{id_partido}/porteria')
    assert r.status_code == 400
    assert 'no es de porter' in r.get_json()['error']


def _partido_analisis(client):
    """Partido de análisis, que NO debe servir para la herramienta de portería."""
    eq_a = client.post('/api/equipos', json={'nombre': 'A', 'es_propio': 0}).get_json()['id_equipo']
    eq_b = client.post('/api/equipos', json={'nombre': 'B', 'es_provio': 0}).get_json()['id_equipo']
    r = client.post('/api/matches', json={
        'tipo_partido': 'ANALISIS',
        'id_equipo_a': eq_a, 'id_equipo_b': eq_b,
        'fecha_partido': '2024-01-01',
    })
    return r.get_json()['id_partido']


def _partido_mi_equipo(client):
    eq = client.post('/api/equipos', json={'nombre': 'San Roque', 'es_propio': 1}).get_json()['id_equipo']
    r = client.post('/api/matches', json={
        'id_equipo_a': eq, 'rival': 'ABC',
        'fecha_partido': '2024-01-01',
        'convocatoria': [
            {'nombre': 'Arquero Uno', 'numero_camiseta': 1, 'posicion': 'PORTERO'},
        ],
    })
    return r.get_json()['id_partido']


# --------------------------------------------------------------------------
# Las rutas: la herramienta solo corre sobre partidos de portería
# --------------------------------------------------------------------------

def test_la_herramienta_abre_sobre_un_partido_de_porteria(client):
    id_partido = _partido_porteria(client, nombre='San Roque', rival='ABC')
    r = client.get(f'/porteria?match={id_partido}')
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    # Las dos pestañas, y con esto el partido listo para capturar
    assert 'id="vista-capturar"' in html
    assert 'id="vista-analizar"' in html
    assert 'San Roque' in html
    # El reloj y el estado vienen del servidor, no de un fetch
    assert 'id="pt-estado"' in html


def test_la_herramienta_ofrece_crear_uno_si_el_partido_no_es_de_porteria(client):
    """No se redirige: redirigir deja al operador pensando que rompió algo."""
    id_partido = _partido_mi_equipo(client)
    r = client.get(f'/porteria?match={id_partido}')
    assert r.status_code == 200      # 200 y no 302: el aviso va en la pantalla
    html = r.get_data(as_text=True)
    assert 'no es de porter' in html
    assert '/nuevo_partido?tipo=PORTERIA' in html
    # Y no monta la herramienta a medias
    assert 'id="vista-capturar"' not in html


def test_la_herramienta_avisa_si_no_hay_partido(client):
    r = client.get('/porteria')
    assert r.status_code == 200
    assert 'Eleg' in r.get_data(as_text=True)


def test_la_herramienta_avisa_si_el_partido_no_existe(client):
    r = client.get('/porteria?match=99999')
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert 'Eleg' in html
    assert 'id="vista-capturar"' not in html


def test_la_captura_normal_manda_a_la_herramienta_ante_un_partido_de_porteria(client):
    """Las dos herramientas son excluyentes por construcción: / no puede
    capturar un partido de portería porque no sabe pedir el punto del tiro."""
    id_partido = _partido_porteria(client)
    r = client.get(f'/?match={id_partido}')
    assert r.status_code == 302
    assert f'/porteria?match={id_partido}' in r.headers['Location']


def test_la_captura_normal_no_se_mezcla_con_los_partidos_normales(client):
    for id_partido in (_partido_mi_equipo(client), _partido_analisis(client)):
        r = client.get(f'/?match={id_partido}')
        assert r.status_code == 200
        assert 'id="scoreboard"' in r.get_data(as_text=True)


def test_las_estadisticas_ceden_el_paso_a_la_herramienta(client):
    """/stats de un partido de portería saldría vacía: solo hay tiros del rival.
    Al redirigir, un enlace viejo o el botón atrás siguen llevando al análisis."""
    id_partido = _partido_porteria(client)
    r = client.get(f'/stats?match={id_partido}')
    assert r.status_code == 302
    assert f'/porteria?match={id_partido}' in r.headers['Location']
    assert 'vista=analizar' in r.headers['Location']


def test_las_estadisticas_de_los_partidos_normales_no_se_mueven(client):
    for id_partido in (_partido_mi_equipo(client), _partido_analisis(client)):
        r = client.get(f'/stats?match={id_partido}')
        assert r.status_code == 200
        assert 'class="stats-container"' in r.get_data(as_text=True)


def test_la_pestana_analizar_llega_por_url(client):
    id_partido = _partido_porteria(client)
    r = client.get(f'/porteria?match={id_partido}&vista=analizar')
    assert r.status_code == 200
    assert 'data-vista="analizar"' in r.get_data(as_text=True)


def test_la_herramienta_trae_el_plantel_para_elegir_arquero(client):
    id_partido = _partido_porteria(client)
    html = client.get(f'/porteria?match={id_partido}').get_data(as_text=True)
    assert 'Arquero Uno' in html
    assert 'Arquero Dos' in html


def test_la_captura_no_necesita_red_para_saber_quien_tira(client):
    """El id del rival genérico tiene que estar en el HTML.

    Hace falta para armar cada evento, así que si la pantalla lo pidiera por fetch,
    el primer tiro en una cancha sin señal no se podría registrar: que es justo
    cuando más hace falta.
    """
    id_partido = _partido_porteria(client)
    html = client.get(f'/porteria?match={id_partido}').get_data(as_text=True)

    import app as flask_app
    with flask_app.app.app_context():
        from db import get_db_connection
        with get_db_connection() as c:
            rival = c.execute(
                "SELECT id_jugador FROM Jugadores WHERE id_partido = ? "
                "AND id_equipo = 'B' AND es_generico = 1", (id_partido,)
            ).fetchone()['id_jugador']

    assert 'id="pt-estado"' in html
    assert f'data-rival="{rival}"' in html


def test_la_herramienta_avisa_si_no_hay_ningun_portero(client):
    """Sin nadie en el arco no hay a quién cargarle los tiros: el selector vacío
    tiene que decirlo, no esperar a fallar en el primer toque.

    Un partido de portería no se puede crear sin convocatoria, así que el estado
    se arma borrando los jugadores: sirve para fijar que el texto existe y que la
    pantalla no se rompe."""
    id_partido = _partido_porteria(client)

    import app as flask_app
    with flask_app.app.app_context():
        from db import get_db_connection
        with get_db_connection() as c:
            c.execute('DELETE FROM Jugadores WHERE id_partido = ?', (id_partido,))
            c.commit()

    r = client.get(f'/porteria?match={id_partido}')
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert 'no tiene ningún jugador en el equipo A' in html
    # El selector vacío no inventa un arquero: el JS no tiene a quién cargarle el tiro
    assert 'data-keeper-id' not in html


def test_la_lista_de_partidos_distingue_el_tipo_para_el_badge(client):
    """La lista se arma en el navegador: lo que tiene que volver de la API es el
    tipo, que es lo que permite pintar el badge y elegir el botón principal."""
    id_partido = _partido_porteria(client)
    partidos = client.get('/api/matches').get_json()
    mio = next(p for p in partidos if p['id_partido'] == id_partido)
    assert mio['tipo_partido'] == 'PORTERIA'


def test_el_partido_de_porteria_no_se_muestra_como_analisis(client):
    _partido_porteria(client)
    _partido_analisis(client)
    partidos = client.get('/api/matches').get_json()
    tipos = {p['tipo_partido'] for p in partidos}
    assert 'PORTERIA' in tipos
    assert 'ANALISIS' in tipos


def test_nuevo_partido_tiene_el_tercer_radio(client):
    html = client.get('/nuevo_partido?tipo=PORTERIA').get_data(as_text=True)
    assert 'id="radio-tipo-porteria"' in html
    assert 'value="PORTERIA"' in html


def test_analipsis_partidas_de_porteria(client):
    id_partido = _partido_porteria(client, nombre='San Roque', rival='ABC')
    portero, _, rival = _ids(client, id_partido)

    # 4 de la franja pegada al arco por la izquierda, 2 de la derecha lejana
    for i in range(4):
        _tiro(client, id_partido, rival, portero, 'PARADA', -8.0, 4.0, 'ML', 100 + i)
    for i in range(2):
        _tiro(client, id_partido, rival, portero, 'GOL', 8.0, 13.0, 'TR', 200 + i)

    r = client.get(f'/api/matches/{id_partido}/porteria')
    assert r.status_code == 200
    d = r.get_json()

    assert d['partido']['equipo'] == 'San Roque'
    assert d['partido']['rival'] == 'ABC'
    assert d['totales']['tiros'] == 6
    assert d['totales']['paradas'] == 4
    assert d['totales']['goles'] == 2
    assert d['totales']['sin_punto'] == 0

    # La grilla de origen reparte por fila (distancia) y columna (lateral)
    assert d['origen']['BL']['total'] == 4
    assert d['origen']['BL']['paradas'] == 4
    assert d['origen']['TR']['total'] == 2
    assert d['origen']['TR']['goles'] == 2

    # Y la del arco, que es el 3x3 de siempre
    assert d['arco']['ML']['paradas'] == 4
    assert d['arco']['TR']['goles'] == 2

    # Los puntos vienen crudos para el mapa de calor por pixel
    assert len(d['puntos']) == 6
    assert d['puntos'][0]['x'] == -8.0

    p = d['porteros'][0]
    assert p['numero'] == 1
    assert p['paradas'] == 4
    assert p['goles_encajados'] == 2
    assert p['tiros_recibidos'] == 6
    assert p['efectividad'] == 66.7   # redondeado a un decimal, como en /stats


def test_analisis_filtrado_por_arquero(client):
    id_partido = _partido_porteria(client)
    portero1, portero12, rival = _ids(client, id_partido)

    _tiro(client, id_partido, rival, portero1, 'PARADA', -8.0, 4.0, 'ML', 1)
    _tiro(client, id_partido, rival, portero12, 'GOL', 8.0, 13.0, 'TR', 2)

    todo = client.get(f'/api/matches/{id_partido}/porteria').get_json()
    assert todo['totales']['tiros'] == 2
    assert len(todo['porteros']) == 2

    solo1 = client.get(f'/api/matches/{id_partido}/porteria?portero={portero1}').get_json()
    assert solo1['filtro_portero'] == portero1
    assert solo1['totales']['tiros'] == 1
    assert solo1['totales']['paradas'] == 1
    assert solo1['origen']['BL']['total'] == 1
    # El mapa del otro arquero no puede filtrarse para el primero
    assert solo1['origen']['TR']['total'] == 0
    assert len(solo1['puntos']) == 1


def test_analisis_avisa_cuantos_tiros_no_tienen_punto(client):
    """Un tiro sin punto cuenta igual, pero el mapa de calor no lo puede
    dibujar. Ocultarlo sería mostrar un mapa incompleto sin decirlo."""
    id_partido = _partido_porteria(client)
    portero, _, rival = _ids(client, id_partido)

    _tiro(client, id_partido, rival, portero, 'PARADA', -8.0, 4.0, 'ML', 1)
    # este sin coordenadas: entra por el camino viejo
    client.post('/api/event', json={
        'id_partido': id_partido, 'id_jugador': rival,
        'tipo_evento': 'LANZAMIENTO', 'resultado': 'FALLO',
        'tiempo_juego': '05:00', 'id_portero': portero,
        'client_event_id': 'ev-sin-punto',
    })

    d = client.get(f'/api/matches/{id_partido}/porteria').get_json()
    assert d['totales']['tiros'] == 2
    assert d['totales']['sin_punto'] == 1
    assert len(d['puntos']) == 1


def test_analisis_reparte_por_tipo_para_el_gki(client):
    """El reparto por tipo es lo que alimenta el GKI: en /stats vive dentro de
    la fórmula y no se puede leer."""
    id_partido = _partido_porteria(client)
    portero, _, rival = _ids(client, id_partido)

    _tiro(client, id_partido, rival, portero, 'PARADA', 0.0, 4.0, 'BC', 1)
    _tiro(client, id_partido, rival, portero, 'PARADA', 0.0, 7.0, 'MC', 2)
    _tiro(client, id_partido, rival, portero, 'GOL', 0.0, 7.0, 'TC', 3, es_7m=1)
    _tiro(client, id_partido, rival, portero, 'FALLO', -8.0, 15.0, None, 4, es_contraataque=1)

    d = client.get(f'/api/matches/{id_partido}/porteria').get_json()
    assert d['tipos'] == {'6M': 1, '9M': 1, '7M': 1, 'CONTRAATAQUE': 1}


def test_el_7m_se_guarda_con_su_fraccion_y_su_punto(client):
    """El chip de 7m no es una etiqueta suelta: el tiro sale de 7 m al medio.

    Si se guardara como un tiro más, el reparto por tipo lo contaría como 7 m
    pero la columna de distancia diría 9 m, y las dos cosas no pueden ser
    ciertas a la vez.
    """
    import app as flask_app
    from db import get_db_connection

    id_partido = _partido_porteria(client)
    portero, _, rival = _ids(client, id_partido)
    _tiro(client, id_partido, rival, portero, 'PARADA', 0.0, 7.0, 'MC', 1, es_7m=1)

    with flask_app.app.app_context():
        with get_db_connection() as c:
            fila = c.execute(
                'SELECT coordenada_x, coordenada_y, zona_origen, distancia, es_7m '
                'FROM Eventos_Juego WHERE id_partido = ?', (id_partido,)
            ).fetchone()
    assert fila['coordenada_x'] == 0.0
    assert fila['coordenada_y'] == 7.0
    assert fila['zona_origen'] == 'MC'
    assert fila['distancia'] == '7M'


def test_el_contraataque_no_toca_el_punto(client):
    """El contraataque puede salir de cualquier lado, así que el punto sigue siendo
    el que tocó el operador: la etiqueta y el punto cuentan cosas distintas."""
    import app as flask_app
    from db import get_db_connection

    id_partido = _partido_porteria(client)
    portero, _, rival = _ids(client, id_partido)
    _tiro(client, id_partido, rival, portero, 'GOL', 8.0, 15.0, 'TC', 1, es_contraataque=1)

    with flask_app.app.app_context():
        with get_db_connection() as c:
            fila = c.execute(
                'SELECT coordenada_x, coordenada_y, zona_origen, distancia, es_contraataque '
                'FROM Eventos_Juego WHERE id_partido = ?', (id_partido,)
            ).fetchone()
    assert fila['zona_origen'] == 'TR'
    # A 15 m no hay franja de 6 ni de 9: el tiro no salió de una de esas dos.
    assert fila['distancia'] is None

    d = client.get(f'/api/matches/{id_partido}/porteria').get_json()
    assert d['tipos'] == {'CONTRAATAQUE': 1}


def test_marcar_7m_con_un_patch_rederiva_la_distancia(client):
    """Si el 7m se enciende o apaga sin mover el punto, la distancia tiene que
    seguir a la regla: 7 m con el flag, la franja del punto sin él."""
    id_partido = _partido_porteria(client)
    portero, _, rival = _ids(client, id_partido)
    _tiro(client, id_partido, rival, portero, 'PARADA', 0.0, 7.0, 'MC', 1)

    r = client.patch('/api/events/ev-1', json={'es_7m': 1})
    assert r.status_code == 200, r.get_json()
    d = client.get(f'/api/matches/{id_partido}/porteria').get_json()
    assert d['tipos'] == {'7M': 1}

    r = client.patch('/api/events/ev-1', json={'es_7m': 0})
    assert r.status_code == 200, r.get_json()
    d = client.get(f'/api/matches/{id_partido}/porteria').get_json()
    assert d['tipos'] == {'9M': 1}


def test_analisis_no_mete_a_los_porteros_del_rival(client):
    """En un partido de portería el arco es el nuestro. Si un día se squepea un
    tiro del rival al arco de ellos, no puede ensuciar nuestra defensa."""
    id_partido = _partido_porteria(client)
    portero, _, rival = _ids(client, id_partido)
    _tiro(client, id_partido, rival, portero, 'PARADA', -8.0, 4.0, 'ML', 1)

    d = client.get(f'/api/matches/{id_partido}/porteria').get_json()
    assert d['totales']['paradas'] == 1
    assert d['porteros'][0]['paradas'] == 1


def test_analipsis_partidas_de_porteria(client):
    id_partido = _partido_porteria(client, nombre='San Roque', rival='ABC')
    portero, _, rival = _ids(client, id_partido)

    # 4 de la franja pegada al arco por la izquierda, 2 de la derecha lejana
    for i in range(4):
        _tiro(client, id_partido, rival, portero, 'PARADA', -8.0, 4.0, 'ML', 100 + i)
    for i in range(2):
        _tiro(client, id_partido, rival, portero, 'GOL', 8.0, 13.0, 'TR', 200 + i)

    r = client.get(f'/api/matches/{id_partido}/porteria')
    assert r.status_code == 200
    d = r.get_json()

    assert d['partido']['equipo'] == 'San Roque'
    assert d['partido']['rival'] == 'ABC'
    assert d['totales']['tiros'] == 6
    assert d['totales']['paradas'] == 4
    assert d['totales']['goles'] == 2
    assert d['totales']['sin_punto'] == 0

    # La grilla de origen reparte por fila (distancia) y columna (lateral)
    assert d['origen']['BL']['total'] == 4
    assert d['origen']['BL']['paradas'] == 4
    assert d['origen']['TR']['total'] == 2
    assert d['origen']['TR']['goles'] == 2

    # Y la del arco, que es el 3x3 de siempre
    assert d['arco']['ML']['paradas'] == 4
    assert d['arco']['TR']['goles'] == 2

    # Los puntos vienen crudos para el mapa de calor por pixel
    assert len(d['puntos']) == 6
    assert d['puntos'][0]['x'] == -8.0

    p = d['porteros'][0]
    assert p['numero'] == 1
    assert p['paradas'] == 4
    assert p['goles_encajados'] == 2
    assert p['tiros_recibidos'] == 6
    assert p['efectividad'] == 66.7   # redondeado a un decimal, como en /stats


def test_analisis_incluye_al_arquero_que_entro_despues(client):
    """En un partido hay dos o tres porteros y la columna posicion solo admite
    uno. Si la tabla saliera de ahi, el que entro en el minuto 20 no existiria,
    y es justo el que hace falta ver cuando se esta pensando cambiar."""
    id_partido = _partido_porteria(client)
    portero1, portero12, rival = _ids(client, id_partido)

    _tiro(client, id_partido, rival, portero1, 'PARADA', -8.0, 4.0, 'ML', 1)
    _tiro(client, id_partido, rival, portero12, 'PARADA', 0.0, 5.0, 'BC', 2)

    d = client.get(f'/api/matches/{id_partido}/porteria').get_json()
    assert [p['numero'] for p in d['porteros']] == [1, 12]
    assert [p['paradas'] for p in d['porteros']] == [1, 1]


def test_analisis_no_inventa_porteros_sin_tiros(client):
    """Un portero de la plantilla que nunca entró al arco no figura: una fila en
    cero no informa nada y hace creer que estuvo."""
    id_partido = _partido_porteria(client)
    portero, _, rival = _ids(client, id_partido)
    _tiro(client, id_partido, rival, portero, 'PARADA', -8.0, 4.0, 'ML', 1)

    d = client.get(f'/api/matches/{id_partido}/porteria').get_json()
    assert len(d['porteros']) == 1
    assert d['porteros'][0]['id'] == portero


def test_analisis_avisa_los_tiros_sin_arquero_aunque_haya_filtro(client):
    """Un tiro sin arquero es un hueco, no un cero. Con el filtro puesto tiene
    que seguir viéndose, porque es justo el hueco del arquero que se mira."""
    id_partido = _partido_porteria(client)
    portero, _, rival = _ids(client, id_partido)

    _tiro(client, id_partido, rival, portero, 'PARADA', -8.0, 4.0, 'ML', 1)
    client.post('/api/event', json={
        'id_partido': id_partido, 'id_jugador': rival,
        'tipo_evento': 'LANZAMIENTO', 'resultado': 'GOL',
        'tiempo_juego': '07:00',
        'client_event_id': 'ev-sin-arquero',
    })

    sin_filtro = client.get(f'/api/matches/{id_partido}/porteria').get_json()
    assert sin_filtro['tiros_sin_arquero'] == 1

    # El total filtrado viene limpio, pero el aviso del hueco sobrevive
    con_filtro = client.get(f'/api/matches/{id_partido}/porteria?portero={portero}').get_json()
    assert con_filtro['totales']['tiros'] == 1
    assert con_filtro['tiros_sin_arquero'] == 1


def test_analisis_anula_un_tiro_y_lo_saca_de_los_numeros(client):
    """El tiro anulado no puede seguir sumando ni en el mapa de calor."""
    id_partido = _partido_porteria(client)
    portero, _, rival = _ids(client, id_partido)

    _tiro(client, id_partido, rival, portero, 'PARADA', -8.0, 4.0, 'ML', 1)
    _tiro(client, id_partido, rival, portero, 'GOL', 8.0, 13.0, 'TR', 2)

    r = client.post('/api/events', json={'events': [
        {'op': 'void', 'client_event_id': 'ev-2'}
    ]})
    assert r.status_code == 200

    d = client.get(f'/api/matches/{id_partido}/porteria').get_json()
    assert d['totales']['tiros'] == 1
    assert d['totales']['paradas'] == 1
    assert d['totales']['goles'] == 0
    assert d['arco']['TR']['total'] == 0
    assert len(d['puntos']) == 1
