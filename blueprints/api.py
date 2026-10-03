from flask import Blueprint, request, jsonify, Response
import csv
import sqlite3
from io import StringIO
from db import get_db_connection
from services.eventos import validar_evento, verificar_advertencia_7m, tiempo_a_segundos, recalcular_disciplina, normalizar_evento_legacy, derivar_posesiones, subtipo_lanzamiento, derivar_contexto_7m
from services.metrics import (
    eficiencia_tiro, efectividad_portero, gki, mas_menos, LANZAMIENTOS,
    eficacia_ataque, frecuencia_tiro, perdidas_por_ataque,
    tasa_fallados, tasa_detenidos
)

api_bp = Blueprint('api', __name__, url_prefix='/api')

# Nombre que se le pone al dorsal capturado a mano (sin plantilla de origen).
# Vive acá y no suelto en dos lugares porque /stats tiene que reconocerlo para
# saber si el jugador tiene un nombre real o solo el dorsal.
PREFIJO_NOMBRE_AD_HOC = 'N.º '


def _nombre_mostrable(nombre):
    """(tiene_nombre, apellido) a partir del nombre guardado en Jugadores.

    El placeholder de la captura ad-hoc ("N.º 21") no es un nombre real: ese
    jugador se identifica solo por su dorsal.

    Para la etiqueta corta (el eje de las barras) se usa el APELLIDO, que
    disambigua mejor que el nombre de pila: en Ballester hay dos "Marco" (#3 y
    #22) y en Maipu dos "Lautaro" (#16 y #99), ambos indistinguibles en la barra.

    Las plantillas vienen como "Apellido, Nombre" ("Sidoti, Marco Felipe"), así
    que el apellido es lo que va antes de la coma. Sin coma se aplica la misma
    convención de la convocatoria propia, que es "Apellido Nombre"
    ("Martinez Lautaro" -> "Martinez"). Con una sola palabra esa palabra ya es
    el apellido y no hay nada que acortar.
    """
    n = (nombre or '').strip()
    if not n or n.startswith(PREFIJO_NOMBRE_AD_HOC):
        return False, ''
    if ',' in n:
        apellido = n.split(',', 1)[0].strip()
        # Coma al principio (", Marco"): no hay apellido, se devuelve entero.
        return (True, apellido) if apellido else (True, n)
    return True, n.split()[0]


# Columnas que un PATCH de evento puede tocar.
_CAMPOS_EDITABLES_EVENTO = [
    'id_jugador', 'tipo_evento', 'resultado', 'periodo', 'segundo_absoluto',
    'zona_porteria', 'zona_origen', 'coordenada_x', 'coordenada_y', 'distancia',
    'es_7m', 'es_contraataque', 'id_portero',
]
# Las que NO son dato propio del tiro sino derivadas del punto. Si un patch
# mueve el tiro hay que rederivarlas aunque el cliente no las mande: si no, la
# columna queda diciendo dónde se lanzó un tiro que ya no está ahí.
_CAMPOS_DERIVADOS_DEL_PUNTO = ('zona_origen', 'distancia')


def _armar_actualizaciones(data, normalizado):
    """(updates, params) para el UPDATE de un PATCH de evento.

    `data` es lo que mandaron y `normalizado` el mismo payload ya pasado por
    normalizar_evento_legacy, que es de donde salen los derivados correctos.
    Cuando viene el punto, lo derivado pisa a lo que haya mandado el cliente:
    el servidor es la fuente, no el botón.

    Marcar o sacar el 7m también rederiva: la franja del penalti no depende solo
    del punto sino del tipo de tiro, así que apagar el flag tiene que devolver
    la distancia a su banda real.
    """
    mueve_el_tiro = ('coordenada_x' in data or 'coordenada_y' in data
                     or 'es_7m' in data)
    updates, params = [], []
    for field in _CAMPOS_EDITABLES_EVENTO:
        if mueve_el_tiro and field in _CAMPOS_DERIVADOS_DEL_PUNTO:
            valor = normalizado.get(field)
        elif field in data:
            valor = data[field]
        else:
            continue
        updates.append(f'{field} = ?')
        params.append(valor)
    return updates, params


@api_bp.route('/version', methods=['GET'])
def app_version():
    # Versión para el handshake anti-caché del frontend. Debe coincidir con
    # window.APP_VERSION (inyectado en index.html) y CACHE_NAME (sw.js).
    from blueprints.web import APP_VERSION
    resp = jsonify({'version': APP_VERSION})
    resp.headers['Cache-Control'] = 'no-store'
    return resp

@api_bp.route('/event', methods=['POST'])
def record_event():
    event_data = request.get_json() or {}
    event_data = normalizar_evento_legacy(event_data)
    
    errores, warnings_val = validar_evento(event_data)
    if errores:
        return jsonify({'status': 'error', 'errors': errores}), 400

    try:
        with get_db_connection() as conn:
            previos = conn.execute(
                'SELECT tipo_evento, tiempo_juego FROM Eventos_Juego WHERE id_partido = ? ORDER BY id_evento DESC LIMIT 50',
                (event_data['id_partido'],)
            ).fetchall()
            eventos_previos_list = [dict(row) for row in previos]
            
            warnings_reglas = verificar_advertencia_7m(event_data, eventos_previos_list)
            all_warnings = warnings_val + warnings_reglas

            cursor = conn.cursor()
            client_event_id = event_data.get('client_event_id')
            
            cursor.execute('''
                INSERT INTO Eventos_Juego 
                (id_partido, id_jugador, tipo_evento, resultado, tiempo_juego, periodo, segundo_absoluto, coordenada_x, coordenada_y, zona_porteria, zona_origen, lado, client_event_id, distancia, es_7m, es_contraataque, id_portero, anulado) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                ON CONFLICT(client_event_id) DO NOTHING
            ''', (
                event_data.get('id_partido'),
                event_data.get('id_jugador'),
                event_data.get('tipo_evento'),
                event_data.get('resultado'),
                event_data.get('tiempo_juego'),
                event_data.get('periodo', 1),
                event_data.get('segundo_absoluto'),
                event_data.get('coordenada_x'),
                event_data.get('coordenada_y'),
                event_data.get('zona_porteria'),
                event_data.get('zona_origen'),
                event_data.get('lado', 'ATAQUE'),
                client_event_id,
                event_data.get('distancia'),
                event_data.get('es_7m', 0),
                event_data.get('es_contraataque', 0),
                event_data.get('id_portero')
            ))
            
            new_id = cursor.lastrowid
            inserted = (cursor.rowcount > 0)
            
            auto_descalificacion = False
            if inserted and event_data.get('tipo_evento') == 'EXCLUSION_2MIN':
                recalcular_disciplina(conn, event_data.get('id_partido'), event_data.get('id_jugador'), client_event_id)
                # Informar si este evento disparó la descalificación automática
                auto_desc = conn.execute(
                    "SELECT 1 FROM Eventos_Juego WHERE id_partido = ? AND id_jugador = ? "
                    "AND tipo_evento = 'DESCALIFICACION' AND generado_por IS NOT NULL AND anulado = 0",
                    (event_data.get('id_partido'), event_data.get('id_jugador'))
                ).fetchone()
                auto_descalificacion = auto_desc is not None

            conn.commit()
            
            if not inserted and client_event_id:
                existing = conn.execute('SELECT id_evento FROM Eventos_Juego WHERE client_event_id = ?', (client_event_id,)).fetchone()
                existing_id = existing['id_evento'] if existing else None
                return jsonify({'status': 'success', 'event_id': existing_id, 'duplicate': True, 'warnings': all_warnings}), 200

            resp_data = {'status': 'success', 'event_id': new_id, 'warnings': all_warnings}
            if auto_descalificacion:
                resp_data['auto_descalificacion'] = True
            return jsonify(resp_data), 201

    except sqlite3.IntegrityError as e:
        return jsonify({'status': 'error', 'message': f'Error de integridad referencial: {str(e)}'}), 400
    except sqlite3.Error as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@api_bp.route('/events', methods=['POST'])
def record_events_batch():
    payload = request.get_json() or {}
    if isinstance(payload, list):
        lista_eventos = payload
    else:
        lista_eventos = payload.get('events', [])

    guardados = []
    rechazados = []

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            for event_data in lista_eventos:
                op = event_data.get('op', 'create')
                client_event_id = event_data.get('client_event_id')
                
                try:
                    if op == 'void':
                        ev = conn.execute('SELECT id_partido, id_jugador, tipo_evento, anulado FROM Eventos_Juego WHERE client_event_id = ?', (client_event_id,)).fetchone()
                        if ev and ev['anulado'] == 0:
                            conn.execute('UPDATE Eventos_Juego SET anulado = 1, anulado_en = CURRENT_TIMESTAMP WHERE client_event_id = ?', (client_event_id,))
                            if ev['tipo_evento'] == 'EXCLUSION_2MIN':
                                recalcular_disciplina(conn, ev['id_partido'], ev['id_jugador'], client_event_id)
                        guardados.append(client_event_id)
                        continue
                        
                    elif op == 'restore':
                        ev = conn.execute('SELECT id_partido, id_jugador, tipo_evento, anulado FROM Eventos_Juego WHERE client_event_id = ?', (client_event_id,)).fetchone()
                        if ev and ev['anulado'] == 1:
                            conn.execute('UPDATE Eventos_Juego SET anulado = 0, anulado_en = NULL WHERE client_event_id = ?', (client_event_id,))
                            if ev['tipo_evento'] == 'EXCLUSION_2MIN':
                                recalcular_disciplina(conn, ev['id_partido'], ev['id_jugador'], client_event_id)
                        guardados.append(client_event_id)
                        continue

                    # For create or patch:
                    event_data = normalizar_evento_legacy(event_data)
                    errores, warnings_val = validar_evento(event_data)
                    if errores:
                        rechazados.append({'client_event_id': client_event_id, 'error': ', '.join(errores)})
                        continue

                    if op == 'patch':
                        ev = conn.execute('SELECT * FROM Eventos_Juego WHERE client_event_id = ?', (client_event_id,)).fetchone()
                        if not ev:
                            rechazados.append({'client_event_id': client_event_id, 'error': 'not found'})
                            continue
                        updates, params = _armar_actualizaciones(event_data, event_data)
                        if updates:
                            params.append(client_event_id)
                            conn.execute(f"UPDATE Eventos_Juego SET {', '.join(updates)} WHERE client_event_id = ?", params)
                            recalcular_disciplina(conn, event_data.get('id_partido', ev['id_partido']), event_data.get('id_jugador', ev['id_jugador']), client_event_id)
                            if event_data.get('id_jugador') and event_data.get('id_jugador') != ev['id_jugador']:
                                recalcular_disciplina(conn, ev['id_partido'], ev['id_jugador'], client_event_id)
                        guardados.append(client_event_id)
                        continue

                    # Default: create
                    cursor.execute('''
                        INSERT INTO Eventos_Juego 
                        (id_partido, id_jugador, tipo_evento, resultado, tiempo_juego, periodo, segundo_absoluto, coordenada_x, coordenada_y, zona_porteria, zona_origen, lado, client_event_id, distancia, es_7m, es_contraataque, id_portero, anulado) 
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                        ON CONFLICT(client_event_id) DO NOTHING
                    ''', (
                        event_data.get('id_partido'),
                        event_data.get('id_jugador'),
                        event_data.get('tipo_evento'),
                        event_data.get('resultado'),
                        event_data.get('tiempo_juego'),
                        event_data.get('periodo', 1),
                        event_data.get('segundo_absoluto'),
                        event_data.get('coordenada_x'),
                        event_data.get('coordenada_y'),
                        event_data.get('zona_porteria'),
                        event_data.get('zona_origen'),
                        event_data.get('lado', 'ATAQUE'),
                        client_event_id,
                        event_data.get('distancia'),
                        event_data.get('es_7m', 0),
                        event_data.get('es_contraataque', 0),
                        event_data.get('id_portero')
                    ))
                    
                    if cursor.rowcount > 0 and event_data.get('tipo_evento') == 'EXCLUSION_2MIN':
                        recalcular_disciplina(conn, event_data.get('id_partido'), event_data.get('id_jugador'), client_event_id)
                        
                    guardados.append(client_event_id)
                except sqlite3.Error as e:
                    rechazados.append({
                        'client_event_id': client_event_id,
                        'error': str(e)
                    })

            conn.commit()

        return jsonify({
            'status': 'success',
            'guardados': guardados,
            'rechazados': rechazados
        }), 200
    except sqlite3.Error as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@api_bp.route('/matches/<int:match_id>/state', methods=['GET'])
def get_match_state(match_id):
    with get_db_connection() as conn:
        partido_row = conn.execute('SELECT * FROM Partidos WHERE id_partido = ?', (match_id,)).fetchone()
        if not partido_row:
            return jsonify({'status': 'error', 'message': 'Partido no encontrado'}), 404

        partido = dict(partido_row)
        
        goles_a = conn.execute('''
            SELECT COUNT(*) as c FROM Eventos_Juego e
            JOIN Jugadores j ON e.id_jugador = j.id_jugador
            WHERE e.id_partido = ? AND j.id_equipo = 'A' AND e.resultado = 'GOL' AND e.anulado = 0
        ''', (match_id,)).fetchone()['c']

        goles_b = conn.execute('''
            SELECT COUNT(*) as c FROM Eventos_Juego e
            JOIN Jugadores j ON e.id_jugador = j.id_jugador
            WHERE e.id_partido = ? AND j.id_equipo = 'B' AND e.resultado = 'GOL' AND e.anulado = 0
        ''', (match_id,)).fetchone()['c']

        # Posesión por replay completo del log (definición formal v1): mirar solo
        # el último evento falla cuando este es neutro (amarilla, asistencia…).
        eventos_state = [dict(r) for r in conn.execute('''
            SELECT e.tipo_evento, e.resultado, e.segundo_absoluto, e.tiempo_juego, j.id_equipo
            FROM Eventos_Juego e
            JOIN Jugadores j ON e.id_jugador = j.id_jugador
            WHERE e.id_partido = ? AND e.anulado = 0
            ORDER BY e.id_evento ASC
        ''', (match_id,)).fetchall()]
        posesion_actual = derivar_posesiones(eventos_state)['posesion_actual']

        seg_actuales = partido.get('segundos_jugados', 0)
        exclusiones_rows = conn.execute('''
            SELECT e.id_jugador, e.tiempo_juego FROM Eventos_Juego e
            WHERE e.id_partido = ? AND e.tipo_evento = 'EXCLUSION_2MIN' AND e.anulado = 0
        ''', (match_id,)).fetchall()

        exclusiones_activas = []
        for ex in exclusiones_rows:
            jid = ex['id_jugador']
            seg_excl = tiempo_a_segundos(ex['tiempo_juego'])
            restante = 120 - (seg_actuales - seg_excl)
            if restante > 0:
                exclusiones_activas.append({
                    'id_jugador': jid,
                    'segundos_restantes': restante
                })

        # Expulsados (roja directa o automática por 3ª exclusión): bloqueo permanente
        descalificados = [r['id_jugador'] for r in conn.execute('''
            SELECT DISTINCT id_jugador FROM Eventos_Juego
            WHERE id_partido = ? AND tipo_evento = 'DESCALIFICACION' AND anulado = 0
        ''', (match_id,)).fetchall()]

        # Rival genérico (dorsal 0, equipo B): actor de todo lo que hace el rival.
        # Fuente de verdad del frontend. Se autocrea si falta para que ningún
        # partido, viejo o nuevo, pueda quedar sin él (pantallas con HTML
        # cacheado o convocatorias editadas no pueden romper la captura).
        if partido.get('tipo_partido') == 'ANALISIS':
            rival_generico_id = None
        else:
            gen = conn.execute('''
                SELECT id_jugador FROM Jugadores
                WHERE id_partido = ? AND id_equipo = 'B' AND numero_camiseta = 0 AND es_generico = 1
                LIMIT 1
            ''', (match_id,)).fetchone()
            if not gen:
                cur = conn.cursor()
                cur.execute('''
                    INSERT INTO Jugadores (id_partido, id_plantel, nombre, id_equipo, numero_camiseta, posicion, es_generico)
                    VALUES (?, NULL, 'Rival (sin dorsal)', 'B', 0, 'CAMPO', 1)
                ''', (match_id,))
                conn.commit()
                rival_generico_id = cur.lastrowid
            else:
                rival_generico_id = gen['id_jugador']

        return jsonify({
            'id_partido': match_id,
            'marcador_a': goles_a,
            'marcador_b': goles_b,
            'posesion_actual': posesion_actual,
            'rival_generico_id': rival_generico_id,
            'segundos_jugados': seg_actuales,
            'periodo_actual': partido.get('periodo_actual', 1),
            'en_pausa': partido.get('en_pausa', 0),
            'exclusiones_activas': exclusiones_activas,
            'descalificados': descalificados
        }), 200


@api_bp.route('/matches/<int:match_id>/state', methods=['PATCH'])
def update_match_state(match_id):
    data = request.get_json() or {}
    
    segundos_jugados = data.get('segundos_jugados')
    periodo_actual = data.get('periodo_actual')
    en_pausa = data.get('en_pausa')
    estado = data.get('estado')
    marcador_final_a = data.get('marcador_final_a')
    marcador_final_b = data.get('marcador_final_b')

    updates = []
    params = []
    if segundos_jugados is not None:
        updates.append("segundos_jugados = ?")
        params.append(int(segundos_jugados))
    if periodo_actual is not None:
        # El servidor es la verdad: un cliente viejo/buggy nunca puede hacer
        # retroceder el período (p. ej. recarga con periodoActual=1 en la 2ª parte).
        with get_db_connection() as conn:
            row = conn.execute('SELECT periodo_actual FROM Partidos WHERE id_partido = ?', (match_id,)).fetchone()
            actual = (dict(row).get('periodo_actual') or 1) if row else 1
        if int(periodo_actual) >= int(actual):
            updates.append("periodo_actual = ?")
            params.append(int(periodo_actual))
    if en_pausa is not None:
        updates.append("en_pausa = ?")
        params.append(int(en_pausa))
    if estado is not None:
        updates.append("estado = ?")
        params.append(estado)
    if marcador_final_a is not None:
        updates.append("marcador_final_a = ?")
        params.append(int(marcador_final_a))
    if marcador_final_b is not None:
        updates.append("marcador_final_b = ?")
        params.append(int(marcador_final_b))

    if not updates:
        return jsonify({'status': 'error', 'message': 'No hay datos para actualizar'}), 400

    params.append(match_id)
    query = f"UPDATE Partidos SET {', '.join(updates)} WHERE id_partido = ?"
    
    with get_db_connection() as conn:
        conn.execute(query, tuple(params))
        conn.commit()

    return jsonify({'status': 'success'}), 200


@api_bp.route('/matches/<int:match_id>/export', methods=['GET'])
def export_match(match_id):
    with get_db_connection() as conn:
        eventos = conn.execute('SELECT * FROM Eventos_Juego WHERE id_partido = ? ORDER BY id_evento ASC', (match_id,)).fetchall()
    return jsonify([dict(ix) for ix in eventos]), 200


@api_bp.route('/stats/<int:match_id>', methods=['GET'])
@api_bp.route('/matches/<int:match_id>/stats', methods=['GET'])
def get_stats(match_id):
    with get_db_connection() as conn:
        partido_row = conn.execute('SELECT * FROM Partidos WHERE id_partido = ?', (match_id,)).fetchone()
        if not partido_row:
            return jsonify({'status': 'error', 'message': 'Partido no encontrado'}), 404
            
        partido = dict(partido_row)
        jugadores_rows = conn.execute('SELECT * FROM Jugadores WHERE id_partido = ? AND id_equipo IN ("A", "B") ORDER BY id_equipo, numero_camiseta', (match_id,)).fetchall()
        jugadores_list = [dict(j) for j in jugadores_rows]
        
        eventos_rows = conn.execute('SELECT e.*, j.id_equipo FROM Eventos_Juego e JOIN Jugadores j ON e.id_jugador = j.id_jugador WHERE e.id_partido = ? AND e.anulado = 0 ORDER BY e.id_evento ASC', (match_id,)).fetchall()
        eventos = [dict(ev) for ev in eventos_rows]

    # Map players
    jugadores_dict = {}
    for j in jugadores_list:
        jid = j['id_jugador']
        tiene_nombre, nombre_corto = _nombre_mostrable(j['nombre'])
        jugadores_dict[jid] = {
            'id_jugador': jid,
            'nombre': j['nombre'],
            # Cómo debe mostrarlo stats.js: con nombre si lo tiene, y solo el
            # dorsal si el nombre es el placeholder de la captura ad-hoc.
            'tiene_nombre': tiene_nombre,
            'nombre_corto': nombre_corto,
            'id_equipo': j['id_equipo'],
            'numero_camiseta': j['numero_camiseta'],
            'es_generico': j.get('es_generico', 0),
            'goles': 0,
            'lanzamientos_totales': 0,
            'eficiencia_tiro': 0.0,
            'asistencias': 0,
            'perdidas': 0,
            'robos': 0,
            'bloqueos': 0,
            'exclusiones_2min': 0,
            'sanciones': 0,
            'es_portero': (j.get('posicion', 'CAMPO') == 'PORTERO'),
            'atribucion_portero': 'exacta',
            'paradas': 0,
            'goles_recibidos': 0,
            'tiros_recibidos': 0,
            'efectividad_portero': 0.0,
            'paradas_por_tipo': {},
            'gki': 0.0
        }

    # Contadores de equipo y partido
    goles_a = 0
    goles_b = 0
    lanz_a = 0
    lanz_b = 0
    perd_a = 0
    perd_b = 0
    excl_a = 0
    excl_b = 0
    asist_a = 0
    asist_b = 0
    robos_a = 0
    robos_b = 0
    bloq_a = 0
    bloq_b = 0
    fall_a = 0   # tiros fallados: FALLO + BLOQUEADO + POSTE (legacy)
    fall_b = 0
    det_a = 0    # tiros detenidos por el portero rival: PARADA
    det_b = 0
    TIPOS_TIRO = ('6M', '9M', '7M', 'CONTRAATAQUE', 'OTRO')
    lanz_tipo_a = {t: {'tiros': 0, 'goles': 0} for t in TIPOS_TIRO}
    lanz_tipo_b = {t: {'tiros': 0, 'goles': 0} for t in TIPOS_TIRO}

    for ev in eventos:
        jid = ev['id_jugador']
        equipo = ev['id_equipo']
        tipo = ev['tipo_evento']
        res = ev['resultado']

        if jid in jugadores_dict:
            jstats = jugadores_dict[jid]
            
            if tipo in LANZAMIENTOS:
                jstats['lanzamientos_totales'] += 1
                if equipo == 'A': lanz_a += 1
                else: lanz_b += 1

                subt = subtipo_lanzamiento(ev)
                tabla_tipo = lanz_tipo_a if equipo == 'A' else lanz_tipo_b
                tabla_tipo[subt]['tiros'] += 1

                if res == 'GOL':
                    jstats['goles'] += 1
                    tabla_tipo[subt]['goles'] += 1
                    if equipo == 'A': goles_a += 1
                    else: goles_b += 1
                elif res == 'PARADA':
                    if equipo == 'A': det_a += 1
                    else: det_b += 1
                elif res in ('FALLO', 'BLOQUEADO', 'POSTE'):
                    if equipo == 'A': fall_a += 1
                    else: fall_b += 1

            elif tipo == 'ASISTENCIA':
                jstats['asistencias'] += 1
                if equipo == 'A': asist_a += 1
                else: asist_b += 1
            elif tipo in {'PERDIDA_BALON', 'FALTA_TECNICA', 'DOBLE', 'PASOS'}:
                jstats['perdidas'] += 1
                if equipo == 'A': perd_a += 1
                else: perd_b += 1
            elif tipo == 'ROBO_BALON':
                jstats['robos'] += 1
                if equipo == 'A': robos_a += 1
                else: robos_b += 1
            elif tipo == 'BLOQUEO':
                jstats['bloqueos'] += 1
                if equipo == 'A': bloq_a += 1
                else: bloq_b += 1
            elif tipo == 'EXCLUSION_2MIN':
                jstats['exclusiones_2min'] += 1
                if equipo == 'A': excl_a += 1
                else: excl_b += 1
            elif tipo in {'AMARILLA', 'DESCALIFICACION'}:
                jstats['sanciones'] += 1
            elif tipo == 'PARADA_PORTERO':
                jstats['paradas'] += 1
                jstats['paradas_por_tipo']['PARADA_PORTERO'] = jstats['paradas_por_tipo'].get('PARADA_PORTERO', 0) + 1

        if tipo in LANZAMIENTOS and res == 'PARADA':
            subtipo = subtipo_lanzamiento(ev)
                
            equipo_rival = 'B' if equipo == 'A' else 'A'
            porteros_rivales = [pj for pj in jugadores_dict.values() if pj['id_equipo'] == equipo_rival and pj['es_portero']]
            
            port = None
            # id_portero manda sobre el 🧤: es el que sabe a quién se le
            # atribuyó el evento. Se valida que sea del lado que defiende, si
            # no un id venuado contaminaría el agregado de portería.
            if (ev.get('id_portero') and ev['id_portero'] in jugadores_dict
                    and jugadores_dict[ev['id_portero']]['id_equipo'] == equipo_rival):
                port = jugadores_dict[ev['id_portero']]
                port['atribucion_portero'] = 'exacta'
            elif len(porteros_rivales) == 1:
                port = porteros_rivales[0]
            elif len(porteros_rivales) > 1:
                port = porteros_rivales[0]
                for p in porteros_rivales:
                    p['atribucion_portero'] = 'aproximada_equipo'
                    
            if port:
                port['paradas'] += 1
                port['paradas_por_tipo'][subtipo] = port['paradas_por_tipo'].get(subtipo, 0) + 1

        # Goles recibidos por portero (base del % de paradas). Solo se atribuye
        # con id_portero explícito o arquero único: con varios porteros y sin
        # atribución el gol queda en el pozo común del equipo (ver no_atrib).
        if tipo in LANZAMIENTOS and res == 'GOL':
            equipo_rival = 'B' if equipo == 'A' else 'A'
            porteros_rivales = [pj for pj in jugadores_dict.values() if pj['id_equipo'] == equipo_rival and pj['es_portero']]

            port = None
            # id_portero manda sobre el 🧤: es el que sabe a quién se le
            # atribuyó el evento. Se valida que sea del lado que defiende, si
            # no un id venuado contaminaría el agregado de portería.
            if (ev.get('id_portero') and ev['id_portero'] in jugadores_dict
                    and jugadores_dict[ev['id_portero']]['id_equipo'] == equipo_rival):
                port = jugadores_dict[ev['id_portero']]
                port['atribucion_portero'] = 'exacta'
            elif len(porteros_rivales) == 1:
                port = porteros_rivales[0]

            if port:
                port['goles_recibidos'] += 1

    # Goles del equipo contrario sin portero asignado (datos previos al fix):
    # se suman al denominador de cada portero para no achicarlo (comportamiento previo).
    #
    # Cuenta TODO lo que se atribuyó, no solo lo de los marcados con 🧤. El 🧤
    # dice quién es arquero, pero el que atribuye es el evento (id_portero): un
    # jugador puede tener goles encajados sin estar marcado. Contar solo los
    # marcados dejaba esos goles en el pozo común, que después se sumaba al
    # denominador de cada arquero: los encajados quedaban contados dos veces
    # (una en su fila, otra en la de todos los marcados).
    atrib_por_equipo = {'A': 0, 'B': 0}
    for jstats in jugadores_dict.values():
        atrib_por_equipo[jstats['id_equipo']] += jstats['goles_recibidos']
    no_atrib = {
        'A': goles_b - atrib_por_equipo['A'],
        'B': goles_a - atrib_por_equipo['B'],
    }

    stats_jugadores = []
    for jstats in jugadores_dict.values():
        jstats['eficiencia_tiro'] = eficiencia_tiro(jstats['goles'], jstats['lanzamientos_totales'])

        if jstats['es_portero'] or jstats['paradas'] > 0:
            jstats['tiros_recibidos'] = jstats['paradas'] + jstats['goles_recibidos'] + max(0, no_atrib[jstats['id_equipo']])
            jstats['efectividad_portero'] = efectividad_portero(jstats['paradas'], jstats['tiros_recibidos'])
            jstats['gki'] = gki(jstats['paradas_por_tipo'])
        # Rival eliminado de la pantalla: en MI_EQUIPO los genéricos son relleno
        # ("Rival 1..16" y "Rival (sin dorsal)"); sus stats ya sumaron a los
        # contadores de equipo (goles_a/b, lanz_a/b) y no van a la tabla.
        #
        # En ANÁLISIS es_generico=1 NO significa relleno: son los dorsales que
        # capturó el operador, que no tienen Plantel de origen. Aplicar el mismo
        # filtro ahí se comía a todos los goleadores y dejaba las barras de
        # "Goles — <equipo>" y la tabla de jugadores vacías.
        # Un partido de análisis nunca crea relleno: /state devuelve
        # rival_generico_id=None y POST /api/matches no inserta los "Rival N".
        if partido.get('tipo_partido', 'MI_EQUIPO') == 'MI_EQUIPO' and jstats.get('es_generico', 0) == 1:
            continue
            
        stats_jugadores.append(jstats)

    # Posesión/ataques por replay del log (definición formal v1, sin clics extra)
    replay = derivar_posesiones(eventos)
    ataq_a = replay['ataques']['A']
    ataq_b = replay['ataques']['B']

    def resumen_porteria(eq, goles_rival):
        """Bloque de portería de un lado: lo que hizo la defensa, no lo que hizo
        un jugador puntual.

        Cuenta todos los que atajaron, no solo los marcados con 🧤: el 🧤 dice
        quién es arquero, pero el que tiene paradas y goles encajados es el que
        recibió los eventos. Filtrar por es_portero dejaba fuera a quien atajó
        sin estar marcado.

        "Goles encajados" es todo lo que marcó el rival, atribuido o no: es el
        número real, y hace que paradas + goles encajados dé el tiro recibido
        sin depender de a quién se le atribuyó cada tiro.
        """
        con_actividad = [j for j in stats_jugadores
                         if j['id_equipo'] == eq
                         and (j['paradas'] > 0 or j['goles_recibidos'] > 0)]
        # Sin nadie con actividad no hay portería que mostrar. Se lo distingue de
        # "paradas 0" porque un lado sin porteros (el rival genérico de
        # MI_EQUIPO) no es un equipo que no paró: es un lado del que no hay data.
        if not con_actividad:
            return {'porteros': 0}

        paradas = sum(j['paradas'] for j in con_actividad)
        # El GKI se calcula una vez sobre los tipos sumados. Sumar los GKI
        # individuales no significa nada: es un índice, no un contador.
        tipos = {}
        for j in con_actividad:
            for t, n in (j['paradas_por_tipo'] or {}).items():
                tipos[t] = tipos.get(t, 0) + n
        recibidos = paradas + goles_rival
        return {
            'porteros': len(con_actividad),
            'paradas': paradas,
            'goles_recibidos': goles_rival,
            'tiros_recibidos': recibidos,
            'efectividad_portero': efectividad_portero(paradas, recibidos),
            'gki': gki(tipos),
        }

    def resumen_equipo(id_equipo, nombre, goles, lanz, excl, perd, ataq,
                       asist, robos, bloq, fall, det, lanz_tipo, porteria):
        return {
            "id_equipo": id_equipo,
            "nombre": nombre,
            "goles": goles,
            "lanzamientos": lanz,
            "eficiencia_tiro": eficiencia_tiro(goles, lanz),
            "exclusiones": excl,
            "perdidas": perd,
            "ataques": ataq,
            "eficacia_ataque": eficacia_ataque(goles, ataq),
            "tiros_por_ataque": frecuencia_tiro(lanz, ataq),
            "perdidas_por_ataque": perdidas_por_ataque(perd, ataq),
            "asistencias": asist,
            "robos": robos,
            "bloqueos": bloq,
            "tiros_fallados": fall,
            "tiros_detenidos": det,
            "tasa_fallados": tasa_fallados(fall, lanz),
            "tasa_detenidos": tasa_detenidos(det, lanz),
            "lanzamientos_por_tipo": lanz_tipo,
            "porteria": porteria,
        }

    resumen_equipos = [
        # Los goles encajados por A son los que marcó B, y al revés.
        resumen_equipo("A", partido.get('nombre_equipo_a', 'Equipo A'),
                       goles_a, lanz_a, excl_a, perd_a, ataq_a,
                       asist_a, robos_a, bloq_a, fall_a, det_a, lanz_tipo_a,
                       resumen_porteria("A", goles_b)),
        resumen_equipo("B", partido.get('nombre_equipo_b', 'Equipo B'),
                       goles_b, lanz_b, excl_b, perd_b, ataq_b,
                       asist_b, robos_b, bloq_b, fall_b, det_b, lanz_tipo_b,
                       resumen_porteria("B", goles_a)),
    ]

    # 7 m en contexto (§11 doc): marcador reconstruido, sin clics extra
    ctx7m = derivar_contexto_7m(eventos)
    contexto_7m = {}
    for eq in ('A', 'B'):
        c = ctx7m[eq]
        contexto_7m[eq] = {
            'tiros': c['tiros'],
            'goles': c['goles'],
            'eficacia': eficiencia_tiro(c['goles'], c['tiros']),
            'contextos': {
                k: {'tiros': v['tiros'], 'goles': v['goles'],
                    'eficacia': eficiencia_tiro(v['goles'], v['tiros'])}
                for k, v in c['contextos'].items()
            },
        }

    response = {
        "partido": {
            "id": partido['id_partido'],
            "nombre_equipo_a": partido['nombre_equipo_a'],
            "nombre_equipo_b": partido['nombre_equipo_b'],
            "marcador_a": goles_a,
            "marcador_b": goles_b,
            "periodo": partido.get('periodo_actual', 1),
            # El frontend lo necesita para saber si los jugadores tienen nombre
            # real o solo dorsal (en ANÁLISIS el dorsal ES la identidad).
            "tipo_partido": partido.get('tipo_partido', 'MI_EQUIPO')
        },
        "resumen": {
            "goles_totales": goles_a + goles_b,
            "lanzamientos_totales": lanz_a + lanz_b
        },
        "equipos": resumen_equipos,
        "bloques": replay['bloques'],
        "ventanas": replay['ventanas'],
        "contexto_7m": contexto_7m,
        "jugadores": stats_jugadores
    }

    return jsonify(response), 200

@api_bp.route('/matches/<int:match_id>/heatmap', methods=['GET'])
def get_heatmap(match_id):
    ZONAS_PORTERIA = ['TL', 'TC', 'TR', 'ML', 'MC', 'MR', 'BL', 'BC', 'BR']

    def _agregado_vacio():
        return {
            'porteria': {z: {'goles': 0, 'paradas': 0, 'fallos': 0, 'total': 0} for z in ZONAS_PORTERIA},
            'zonas_tiro': {},
        }

    def _acumular(ag, ev, tipo):
        zona = ev['zona_porteria']
        res = ev['resultado']
        if zona in ag['porteria']:
            ag['porteria'][zona]['total'] += 1
            if res == 'GOL': ag['porteria'][zona]['goles'] += 1
            elif res == 'PARADA': ag['porteria'][zona]['paradas'] += 1
            else: ag['porteria'][zona]['fallos'] += 1
        ag['zonas_tiro'][tipo] = ag['zonas_tiro'].get(tipo, 0) + 1

    with get_db_connection() as conn:
        eventos_rows = conn.execute('''
            SELECT e.tipo_evento, e.resultado, e.zona_porteria, e.coordenada_x, e.coordenada_y, e.es_7m, e.es_contraataque, e.distancia, j.id_equipo 
            FROM Eventos_Juego e
            JOIN Jugadores j ON e.id_jugador = j.id_jugador
            WHERE e.id_partido = ? AND e.tipo_evento IN ('LANZAMIENTO', 'LANZAMIENTO_6M', 'LANZAMIENTO_9M', 'LANZAMIENTO_7M', 'CONTRAATAQUE') AND e.anulado = 0
        ''', (match_id,)).fetchall()

    ag_global = _agregado_vacio()
    ag_equipos = {'A': _agregado_vacio(), 'B': _agregado_vacio()}

    for ev in eventos_rows:
        tipo = ev['tipo_evento']
        if tipo == 'LANZAMIENTO':
            if ev['es_7m']: tipo = 'LANZAMIENTO_7M'
            elif ev['es_contraataque']: tipo = 'CONTRAATAQUE'
            elif ev['distancia']: tipo = f"LANZAMIENTO_{ev['distancia']}"
        # Los tipos legacy (LANZAMIENTO_6M/9M/7M/CONTRAATAQUE) se usan tal cual

        _acumular(ag_global, ev, tipo)
        eq = ev['id_equipo']
        if eq in ag_equipos:
            _acumular(ag_equipos[eq], ev, tipo)

    return jsonify({
        'porteria': ag_global['porteria'],
        'zonas_tiro': ag_global['zonas_tiro'],
        'por_equipo': ag_equipos
    }), 200


# ==========================================
# BLOQUE: HERRAMIENTA DE PORTERÍA
# ==========================================
# Un partido de PORTERIA defiende un solo arco: el nuestro. Por eso el análisis
# no espeja nada entre A y B, cosa que sí tiene que hacer /heatmap (donde se
# juntan los tiros a los dos arcos en la misma grilla). Acá todo es relativo a
# nuestro arco y el punto del tiro nunca es ambiguo de qué lado es.
ZONAS_PORTERIA = ['TL', 'TC', 'TR', 'ML', 'MC', 'MR', 'BL', 'BC', 'BR']

# Etiquetas de la grilla de la media cancha. La fila es la distancia y la
# columna la lateral, igual que en el arco: los dos 3x3 se leen como un solo
# dibujo y el vocabulario del que captura no se duplica.
FILAS_ORIGEN = [('T', 'Más de 9 m'), ('M', 'Entre 6 y 9 m'), ('B', 'Cerca del arco (0-6 m)')]
COLS_ORIGEN = [('L', 'Izquierda'), ('C', 'Centro'), ('R', 'Derecha')]

# Cómo se llama cada resultado dentro de los contadores. FALLO y BLOQUEADO se
# distinguen en las celdas (una cosa se le fue, la otra nunca llegó al arco) y
# en los totales van juntos como lo que no llegó a puerta.
_CLAVE_RESULTADO = {'GOL': 'goles', 'PARADA': 'paradas', 'BLOQUEADO': 'bloqueados'}


@api_bp.route('/matches/<int:match_id>/porteria', methods=['GET'])
def get_porteria(match_id):
    """Análisis de portería de un partido de PORTERIA: los dos 3x3, el punto
    de cada tiro para el mapa de calor y los números por arquero.

    Los tiros son los del rival (equipo B): en esta herramienta siempre
    defendemos el mismo arco, así que todo lanzamiento del rival es un tiro a
    nuestro arco y no hay que adivinar la dirección.
    """
    portero_id = request.args.get('portero', type=int)

    with get_db_connection() as conn:
        partido = conn.execute('SELECT * FROM Partidos WHERE id_partido = ?', (match_id,)).fetchone()
        if not partido:
            return jsonify({'error': 'Partido no encontrado'}), 404
        if partido['tipo_partido'] != 'PORTERIA':
            return jsonify({
                'error': 'Este partido no es de portería',
                'tipo_partido': partido['tipo_partido'],
            }), 400

        # El filtro por arquero se aplica en SQL, no después: el mapa de calor
        # tiene que venir con los puntos del arquero elegido y no con los de
        # todos recortados en el navegador.
        cond = "AND e.id_portero = ?" if portero_id else ""
        params = [match_id] + ([portero_id] if portero_id else [])

        eventos = conn.execute(f'''
            SELECT e.resultado, e.zona_porteria, e.zona_origen,
                   e.coordenada_x, e.coordenada_y,
                   e.es_7m, e.es_contraataque, e.distancia,
                   e.id_portero
            FROM Eventos_Juego e
            JOIN Jugadores j ON e.id_jugador = j.id_jugador
            WHERE e.id_partido = ?
              AND e.tipo_evento IN ('LANZAMIENTO','LANZAMIENTO_6M','LANZAMIENTO_9M','LANZAMIENTO_7M','CONTRAATAQUE')
              AND e.anulado = 0
              AND j.id_equipo = 'B'
              {cond}
        ''', params).fetchall()

        # Quiénes fueron arqueros sale de los propios datos: estuvo en el arco el que
        # tenga al menos un tiro atribuido, y no un rol guardado en una casilla.
        # La columna posicion no sirve para armar la tabla porque admite un solo
        # PORTERO por partido y en un partido Defenderían dos o tres: el que
        # entró en el minuto 20 tiene que figurar igual. Al revés, un portero de
        # la plantilla que nunca entró al arco no aparece: una fila en cero no
        # informa nada y hace creer que estuvo.
        filas_porteros = conn.execute('''
            SELECT j.id_jugador, j.numero_camiseta, j.nombre
            FROM Jugadores j
            WHERE j.id_partido = ? AND j.id_equipo = 'A'
              AND j.id_jugador IN (
                    SELECT DISTINCT id_portero FROM Eventos_Juego
                    WHERE id_partido = ? AND id_portero IS NOT NULL AND anulado = 0
              )
            ORDER BY j.numero_camiseta
        ''', (match_id, match_id)).fetchall()

        # Los tiros sin arquero se cuentan sin filtro: con el filtro puesto en
        # un arquero, el total ya viene recortado y el aviso del hueco
        # desaparecería justo cuando el usuario está mirando a un solo arquero.
        sin_arquero = conn.execute('''
            SELECT COUNT(*) FROM Eventos_Juego e
            JOIN Jugadores j ON e.id_jugador = j.id_jugador
            WHERE e.id_partido = ?
              AND e.tipo_evento IN ('LANZAMIENTO','LANZAMIENTO_6M','LANZAMIENTO_9M','LANZAMIENTO_7M','CONTRAATAQUE')
              AND e.anulado = 0 AND j.id_equipo = 'B'
              AND e.id_portero IS NULL
        ''', (match_id,)).fetchone()[0]

    def _vacia():
        return {'goles': 0, 'paradas': 0, 'fallos': 0, 'bloqueados': 0, 'total': 0}

    origen = {f + c: _vacia() for f, _ in FILAS_ORIGEN for c, _ in COLS_ORIGEN}
    arco = {z: _vacia() for z in ZONAS_PORTERIA}
    totales = {'tiros': 0, 'goles': 0, 'paradas': 0, 'fallos': 0, 'bloqueados': 0,
               'sin_punto': 0, 'sin_zona': 0, 'sin_portero': 0}
    puntos = []
    tipos = {}
    por_portero = {}

    for ev in eventos:
        res = ev['resultado']
        totales['tiros'] += 1
        # La clave del desglose sale del mapa, no del resultado crudo: el mismo
        # nombre que usa el contador y que lee el frontend.
        clave = _CLAVE_RESULTADO.get(res, 'fallos')
        totales[clave] += 1

        if ev['id_portero'] is None:
            totales['sin_portero'] += 1
        else:
            por_portero.setdefault(ev['id_portero'], []).append(ev)

        for grilla, zona in ((origen, ev['zona_origen']), (arco, ev['zona_porteria'])):
            if zona in grilla:
                grilla[zona][clave] += 1
                grilla[zona]['total'] += 1

        # El punto es lo que alimenta el mapa de calor por pixel. Sin él, el
        # tiro cuenta igual pero no tiene dónde dibujarse.
        if ev['coordenada_x'] is not None and ev['coordenada_y'] is not None:
            puntos.append({
                'x': ev['coordenada_x'],
                'y': ev['coordenada_y'],
                'r': res,
                'z': ev['zona_porteria'],
                'o': ev['zona_origen'],
                'p': ev['id_portero'],
            })
        else:
            totales['sin_punto'] += 1

        if ev['zona_porteria'] is None:
            totales['sin_zona'] += 1

        # El reparto por tipo es lo que alimenta el GKI: en /stats vive dentro
        # de la fórmula y no se puede leer. Acá se ve.
        if ev['es_7m']:
            tipo = '7M'
        elif ev['es_contraataque']:
            tipo = 'CONTRAATAQUE'
        elif ev['distancia']:
            tipo = ev['distancia']
        else:
            tipo = 'OTRO'
        tipos[tipo] = tipos.get(tipo, 0) + 1

    porteros = []
    for j in filas_porteros:
        suyos = por_portero.get(j['id_jugador'], [])
        paradas = sum(1 for e in suyos if e['resultado'] == 'PARADA')
        # "Goles encajados" es todo lo que marcó el rival con este arquero en el
        # arco, atribuido o no: paradas + goles da el tiro recibido real y no
        # depende de a quién se le cargó cada gol.
        encajados = sum(1 for e in suyos if e['resultado'] == 'GOL')
        recibidos = paradas + encajados
        tiene_nombre, nombre_corto = _nombre_mostrable(j['nombre'])
        porteros.append({
            'id': j['id_jugador'],
            'numero': j['numero_camiseta'],
            'nombre': j['nombre'],
            'nombre_corto': nombre_corto,
            'tiene_nombre': tiene_nombre,
            'paradas': paradas,
            'goles_encajados': encajados,
            'tiros_recibidos': recibidos,
            'fallos': sum(1 for e in suyos if e['resultado'] == 'FALLO'),
            'bloqueados': sum(1 for e in suyos if e['resultado'] == 'BLOQUEADO'),
            'tiros': len(suyos),
            'efectividad': efectividad_portero(paradas, recibidos),
        })

    return jsonify({
        'partido': {
            'id': match_id,
            'equipo': partido['nombre_equipo_a'],
            'rival': partido['nombre_equipo_b'],
            'estado': partido['estado'],
            'marcador': [partido['marcador_final_a'], partido['marcador_final_b']],
        },
        'filtro_portero': portero_id,
        'totales': totales,
        # Sin filtro: el hueco no puede desaparecer justo cuando se está
        # mirando a un solo arquero.
        'tiros_sin_arquero': sin_arquero,
        'origen': origen,
        'arco': arco,
        'puntos': puntos,
        'tipos': tipos,
        'porteros': porteros,
        'grilla': {
            'filas': FILAS_ORIGEN,
            'cols': COLS_ORIGEN,
            'zonas_arco': ZONAS_PORTERIA,
        },
    }), 200



# ==========================================
# BLOQUE B: GESTIÓN DE EQUIPOS Y PARTIDOS
# ==========================================

@api_bp.route('/equipos', methods=['GET', 'POST'])
def handle_equipos():
    with get_db_connection() as conn:
        if request.method == 'GET':
            equipos = conn.execute('SELECT * FROM Equipos ORDER BY nombre').fetchall()
            return jsonify([dict(e) for e in equipos])
        
        elif request.method == 'POST':
            data = request.get_json()
            nombre = data.get('nombre')
            es_propio = int(data.get('es_propio', 0))
            if not nombre:
                return jsonify({'error': 'Nombre es requerido'}), 400
            try:
                cursor = conn.cursor()
                cursor.execute('INSERT INTO Equipos (nombre, es_propio) VALUES (?, ?)', (nombre, es_propio))
                conn.commit()
                return jsonify({'id_equipo': cursor.lastrowid, 'nombre': nombre, 'es_propio': es_propio}), 201
            except sqlite3.IntegrityError:
                return jsonify({'error': 'Ya existe un equipo con ese nombre'}), 400

@api_bp.route('/equipos/<int:id_equipo>', methods=['PATCH'])
def update_equipo(id_equipo):
    data = request.get_json()
    with get_db_connection() as conn:
        updates = []
        params = []
        if 'nombre' in data:
            updates.append('nombre = ?')
            params.append(data['nombre'])
        if 'activo' in data:
            updates.append('activo = ?')
            params.append(int(data['activo']))
            
        if not updates:
            return jsonify({'error': 'No data to update'}), 400
            
        params.append(id_equipo)
        query = f"UPDATE Equipos SET {', '.join(updates)} WHERE id_equipo = ?"
        conn.execute(query, params)
        conn.commit()
        return jsonify({'status': 'success'})

@api_bp.route('/equipos/<int:id_equipo>', methods=['DELETE'])
def delete_equipo(id_equipo):
    with get_db_connection() as conn:
        eq = conn.execute('SELECT * FROM Equipos WHERE id_equipo = ?', (id_equipo,)).fetchone()
        if not eq:
            return jsonify({'error': 'Equipo no encontrado'}), 404

        # Proteger el historial: un equipo con partidos no se borra
        # (borrar primero los partidos desde /partidos si es lo que se quiere)
        n_partidos = conn.execute(
            'SELECT COUNT(*) AS c FROM Partidos WHERE id_equipo_a = ? OR id_equipo_b = ?',
            (id_equipo, id_equipo)
        ).fetchone()['c']
        if n_partidos:
            return jsonify({'error': f'No se puede borrar: el equipo tiene {n_partidos} partido(s) asociado(s)'}), 409

        try:
            conn.execute('DELETE FROM Plantel WHERE id_equipo = ?', (id_equipo,))
            conn.execute('DELETE FROM Equipos WHERE id_equipo = ?', (id_equipo,))
            conn.commit()
        except sqlite3.IntegrityError:
            return jsonify({'error': 'No se puede borrar: el equipo tiene datos asociados'}), 409
    return jsonify({'status': 'success'}), 200

@api_bp.route('/equipos/<int:id_equipo>/plantel', methods=['GET', 'POST'])
def handle_plantel(id_equipo):
    with get_db_connection() as conn:
        if request.method == 'GET':
            plantel = conn.execute('SELECT * FROM Plantel WHERE id_equipo = ? ORDER BY numero_habitual', (id_equipo,)).fetchall()
            return jsonify([dict(p) for p in plantel])
            
        elif request.method == 'POST':
            data = request.get_json()
            nombre = data.get('nombre')
            numero = data.get('numero_habitual')
            posicion = data.get('posicion_habitual', 'CAMPO')
            if not nombre:
                return jsonify({'error': 'Nombre es requerido'}), 400
            
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO Plantel (id_equipo, nombre, numero_habitual, posicion_habitual)
                VALUES (?, ?, ?, ?)
            ''', (id_equipo, nombre, numero, posicion))
            conn.commit()
            return jsonify({'id_plantel': cursor.lastrowid, 'nombre': nombre, 'numero_habitual': numero, 'posicion_habitual': posicion}), 201

@api_bp.route('/plantel/<int:id_plantel>', methods=['PATCH'])
def update_jugador_plantel(id_plantel):
    data = request.get_json()
    with get_db_connection() as conn:
        updates = []
        params = []
        for field in ['nombre', 'numero_habitual', 'posicion_habitual', 'activo']:
            if field in data:
                updates.append(f'{field} = ?')
                params.append(data[field])
                
        if not updates:
            return jsonify({'error': 'No data to update'}), 400
            
        params.append(id_plantel)
        query = f"UPDATE Plantel SET {', '.join(updates)} WHERE id_plantel = ?"
        conn.execute(query, params)
        conn.commit()
        return jsonify({'status': 'success'})


@api_bp.route('/matches/<int:match_id>/jugadores/<int:id_jugador>/posicion', methods=['POST'])
def marcar_posicion_jugador(match_id, id_jugador):
    """Fija la posición (PORTERO/CAMPO) de un jugador YA CAPTURADO en el partido.

    En ANÁLISIS los jugadores ad-hoc nacen CAMPO: nadie es portero hasta que el
    operador lo marca con el guante. Sin persistirlo, /stats no lo reconoce como
    arquero, la atribución de paradas pierde su denominador, y la designación se
    pierde al cambiar de dispositivo (solo vivía en localStorage).

    Solo actúa sobre el jugador de ESTE partido: la plantilla del equipo no se
    toca, porque "en este partido el 7 fue el arquero" no significa que el 7
    sea portero del club.
    """
    data = request.get_json() or {}
    posicion = (data.get('posicion') or '').upper()

    if posicion not in ('PORTERO', 'CAMPO'):
        return jsonify({'error': 'Posición inválida: usar PORTERO o CAMPO'}), 400

    with get_db_connection() as conn:
        p = conn.execute('SELECT tipo_partido FROM Partidos WHERE id_partido = ?', (match_id,)).fetchone()
        if not p:
            return jsonify({'error': 'Partido no encontrado'}), 404
        if p['tipo_partido'] != 'ANALISIS':
            return jsonify({'error': 'Solo en partidos de análisis'}), 409

        j = conn.execute(
            'SELECT id_jugador, id_equipo FROM Jugadores WHERE id_jugador = ? AND id_partido = ?',
            (id_jugador, match_id)
        ).fetchone()
        if not j:
            return jsonify({'error': 'El jugador no pertenece a este partido'}), 404

        if posicion == 'PORTERO':
            # Un solo arquero en cancha por lado: el anterior vuelve a CAMPO.
            conn.execute(
                "UPDATE Jugadores SET posicion = 'CAMPO' WHERE id_partido = ? AND id_equipo = ? AND posicion = 'PORTERO' AND id_jugador != ?",
                (match_id, j['id_equipo'], id_jugador)
            )

        conn.execute('UPDATE Jugadores SET posicion = ? WHERE id_jugador = ?', (posicion, id_jugador))
        conn.commit()

    return jsonify({'status': 'success', 'id_jugador': id_jugador, 'posicion': posicion})


def _sincronizar_plantel(conn, id_partido, id_equipo, lado):
    """Copia la Plantel del equipo a los Jugadores del partido.

    Idempotente: solo agrega los dorsales que faltan, nunca pisa los que ya
    estan (pueden tener posicion cambiada o eventos cargados). Los jugadores
    de plantilla no son genericos: son los reales, con nombre y dorsal.
    """
    if not id_equipo:
        return 0

    ya_en_partido = {
        r['numero_camiseta'] for r in conn.execute(
            'SELECT numero_camiseta FROM Jugadores WHERE id_partido = ? AND id_equipo = ?',
            (id_partido, lado)
        )
    }

    n = 0
    for p in conn.execute(
        'SELECT id_plantel, nombre, numero_habitual, posicion_habitual FROM Plantel '
        'WHERE id_equipo = ? AND activo = 1 ORDER BY numero_habitual',
        (id_equipo,)
    ):
        numero = p['numero_habitual']
        # Sin dorsal no hay celda en el panel: se ignora en vez de romper el indice.
        if numero is None or numero in ya_en_partido:
            continue
        conn.execute('''
            INSERT INTO Jugadores (id_partido, id_plantel, nombre, id_equipo, numero_camiseta, posicion, es_generico)
            VALUES (?, ?, ?, ?, ?, ?, 0)
        ''', (id_partido, p['id_plantel'], p['nombre'], lado, numero,
              p['posicion_habitual'] or 'CAMPO'))
        ya_en_partido.add(numero)
        n += 1
    return n


@api_bp.route('/matches', methods=['GET', 'POST'])
def handle_matches():
    with get_db_connection() as conn:
        if request.method == 'GET':
            partidos = conn.execute('''
                SELECT p.*, 
                       COALESCE(ea.nombre, p.nombre_equipo_a) as nombre_a, 
                       COALESCE(eb.nombre, p.nombre_equipo_b) as nombre_b
                FROM Partidos p
                LEFT JOIN Equipos ea ON p.id_equipo_a = ea.id_equipo
                LEFT JOIN Equipos eb ON p.id_equipo_b = eb.id_equipo
                ORDER BY p.fecha_partido DESC, p.id_partido DESC
            ''').fetchall()
            return jsonify([dict(p) for p in partidos])
            
        elif request.method == 'POST':
            data = request.get_json()
            tipo_partido = data.get('tipo_partido', 'MI_EQUIPO')
            
            if tipo_partido == 'ANALISIS':
                id_eq_a = data.get('id_equipo_a')
                id_eq_b = data.get('id_equipo_b')
                fecha = data.get('fecha_partido')
                competicion = data.get('competicion')
                
                eq_a = conn.execute('SELECT nombre FROM Equipos WHERE id_equipo = ?', (id_eq_a,)).fetchone()
                eq_b = conn.execute('SELECT nombre FROM Equipos WHERE id_equipo = ?', (id_eq_b,)).fetchone()
                
                if not eq_a or not eq_b or not fecha:
                    return jsonify({'error': 'Datos incompletos'}), 400
                
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO Partidos (id_equipo_a, id_equipo_b, nombre_equipo_a, nombre_equipo_b, fecha_partido, competicion, tipo_partido)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (id_eq_a, id_eq_b, eq_a['nombre'], eq_b['nombre'], fecha, competicion, 'ANALISIS'))
                
                id_partido = cursor.lastrowid

                # El panel de captura muestra la plantilla real del equipo, asi que
                # el partido nace con ella. Sin esto el panel cae en el grid de
                # dorsales 1..20 y aparecen jugadores que no jugaron.
                n_a = _sincronizar_plantel(conn, id_partido, id_eq_a, 'A')
                n_b = _sincronizar_plantel(conn, id_partido, id_eq_b, 'B')

                conn.commit()
                return jsonify({'id_partido': id_partido, 'convocados_a': n_a, 'convocados_b': n_b}), 201

            else:
                id_eq_a = data.get('id_equipo_a')
                nombre_rival = data.get('rival', 'Rival')
                fecha = data.get('fecha_partido')
                competicion = data.get('competicion')
                convocatoria = data.get('convocatoria', [])
                
                eq_a = conn.execute('SELECT nombre FROM Equipos WHERE id_equipo = ?', (id_eq_a,)).fetchone()
                if not eq_a or not fecha:
                    return jsonify({'error': 'Datos incompletos'}), 400
                
                # Validar convocatoria A
                if len(convocatoria) > 16:
                    return jsonify({'error': 'Máximo 16 jugadores'}), 400
                
                dorsales = [j['numero_camiseta'] for j in convocatoria]
                if len(dorsales) != len(set(dorsales)):
                    return jsonify({'error': 'Dorsales repetidos'}), 400
                    
                if not any(j.get('posicion') == 'PORTERO' for j in convocatoria):
                    return jsonify({'error': 'El equipo propio debe tener al menos un portero'}), 400
                    
                cursor = conn.cursor()
                
                # Crear partido (equipo B no está en Equipos, id_equipo_b = NULL)
                cursor.execute('''
                    INSERT INTO Partidos (id_equipo_a, id_equipo_b, nombre_equipo_a, nombre_equipo_b, fecha_partido, competicion, tipo_partido)
                    VALUES (?, NULL, ?, ?, ?, ?, ?)
                ''', (id_eq_a, eq_a['nombre'], nombre_rival, fecha, competicion, tipo_partido))
                
                id_partido = cursor.lastrowid
                
                # Insertar equipo A
                for j in convocatoria:
                    cursor.execute('''
                        INSERT INTO Jugadores (id_partido, id_plantel, nombre, id_equipo, numero_camiseta, posicion, es_generico)
                        VALUES (?, ?, ?, ?, ?, ?, 0)
                    ''', (
                        id_partido,
                        j.get('id_plantel'),
                        j.get('nombre'),
                        'A',
                        j.get('numero_camiseta', 0),
                        j.get('posicion', 'CAMPO')
                    ))
                
                # Insertar equipo B generico (Rival)
                # Dorsal 1 = Portero, 2-16 = Campo
                # En PORTERIA no hace falta: la herramienta registra los tiros
                # contra nuestro arco al rival genérico y nunca reparte
                # dorsales. Crear 16 jugadores que no existen solo ensucia la
                # lista de la portería.
                if tipo_partido == 'MI_EQUIPO':
                    for num in range(1, 17):
                        cursor.execute('''
                            INSERT INTO Jugadores (id_partido, id_plantel, nombre, id_equipo, numero_camiseta, posicion, es_generico)
                            VALUES (?, NULL, ?, ?, ?, ?, 1)
                        ''', (
                            id_partido,
                            f"Rival {num}",
                            'B',
                            num,
                            'PORTERO' if num == 1 else 'CAMPO'
                        ))
                    
                # Insertar "Rival (sin dorsal)" con dorsal 0
                cursor.execute('''
                    INSERT INTO Jugadores (id_partido, id_plantel, nombre, id_equipo, numero_camiseta, posicion, es_generico)
                    VALUES (?, NULL, ?, ?, ?, ?, 1)
                ''', (id_partido, "Rival (sin dorsal)", 'B', 0, 'CAMPO'))
                    
                conn.commit()
                return jsonify({'id_partido': id_partido}), 201

@api_bp.route('/matches/<int:id_partido>/sincronizar-plantel', methods=['POST'])
def sincronizar_plantel_partido(id_partido):
    """Carga la Plantel de ambos equipos en un partido de analisis ya creado.

    Para los partidos que se crearon antes de que el panel usara la plantilla
    real (o que se crearon con los equipos sin plantel cargado). Idempotente.
    """
    with get_db_connection() as conn:
        p = conn.execute(
            'SELECT id_partido, tipo_partido, id_equipo_a, id_equipo_b FROM Partidos WHERE id_partido = ?',
            (id_partido,)
        ).fetchone()
        if not p:
            return jsonify({'error': 'Partido no encontrado'}), 404
        if p['tipo_partido'] != 'ANALISIS':
            return jsonify({'error': 'Solo en partidos de análisis'}), 409

        n_a = _sincronizar_plantel(conn, id_partido, p['id_equipo_a'], 'A')
        n_b = _sincronizar_plantel(conn, id_partido, p['id_equipo_b'], 'B')
        conn.commit()

    return jsonify({'status': 'success', 'agregados_a': n_a, 'agregados_b': n_b})


@api_bp.route('/matches/<int:id_partido>', methods=['GET', 'PATCH'])
def update_match_detail(id_partido):
    with get_db_connection() as conn:
        if request.method == 'GET':
            p = conn.execute('SELECT * FROM Partidos WHERE id_partido = ?', (id_partido,)).fetchone()
            if not p:
                return jsonify({'error': 'Not found'}), 404
            return jsonify(dict(p))
            
        elif request.method == 'PATCH':
            data = request.get_json()
            updates = []
            params = []
            for field in ['estado', 'fecha_partido', 'competicion', 'marcador_final_a', 'marcador_final_b']:
                if field in data:
                    updates.append(f'{field} = ?')
                    params.append(data[field])
            
            if not updates:
                return jsonify({'error': 'No data'}), 400
                
            params.append(id_partido)
            conn.execute(f"UPDATE Partidos SET {', '.join(updates)} WHERE id_partido = ?", params)
            conn.commit()
            return jsonify({'status': 'success'})

@api_bp.route('/matches/<int:match_id>/jugadores/rapido', methods=['POST'])
def crear_jugador_rapido(match_id):
    data = request.get_json() or {}
    equipo = data.get('equipo')
    numero = data.get('numero')
    
    if equipo not in ('A', 'B'):
        return jsonify({'error': 'Equipo inválido'}), 400
    try:
        numero = int(numero)
        if numero < 1 or numero > 99:
            raise ValueError()
    except (TypeError, ValueError):
        return jsonify({'error': 'Número inválido'}), 400

    with get_db_connection() as conn:
        # El partido debe existir y ser de análisis: los jugadores ad-hoc por
        # dorsal son un mecanismo de la captura de terceros, no de MI_EQUIPO
        # (que tiene convocatoria propia ya validada al crear el partido).
        p = conn.execute('SELECT id_partido, tipo_partido FROM Partidos WHERE id_partido = ?', (match_id,)).fetchone()
        if not p:
            return jsonify({'error': 'Partido no encontrado'}), 404
        if p['tipo_partido'] != 'ANALISIS':
            return jsonify({'error': 'Solo en partidos de análisis'}), 409

        # Check if player exists
        j = conn.execute('SELECT id_jugador, nombre FROM Jugadores WHERE id_partido = ? AND id_equipo = ? AND numero_camiseta = ?', 
                         (match_id, equipo, numero)).fetchone()
        
        if j:
            return jsonify({'id_jugador': j['id_jugador'], 'nombre': j['nombre'], 'creado': False}), 200

        try:
            cur = conn.cursor()
            nombre = f'{PREFIJO_NOMBRE_AD_HOC}{numero}'
            cur.execute('''
                INSERT INTO Jugadores (id_partido, id_plantel, nombre, id_equipo, numero_camiseta, posicion, es_generico)
                VALUES (?, NULL, ?, ?, ?, 'CAMPO', 1)
            ''', (match_id, nombre, equipo, numero))
            conn.commit()
            return jsonify({'id_jugador': cur.lastrowid, 'nombre': nombre, 'creado': True}), 201
        except sqlite3.IntegrityError:
            # Race condition, fetch again
            j = conn.execute('SELECT id_jugador, nombre FROM Jugadores WHERE id_partido = ? AND id_equipo = ? AND numero_camiseta = ?', 
                             (match_id, equipo, numero)).fetchone()
            if j:
                return jsonify({'id_jugador': j['id_jugador'], 'nombre': j['nombre'], 'creado': False}), 200
            return jsonify({'error': 'Error de concurrencia'}), 409

@api_bp.route('/matches/<int:id_partido>/convocatoria', methods=['PUT'])
def update_convocatoria(id_partido):
    data = request.get_json()
    jugadores = data.get('jugadores', [])
    
    # Validaciones: max 16 per team
    equipo_a_jugs = [j for j in jugadores if j['id_equipo'] == 'A']
    equipo_b_jugs = [j for j in jugadores if j['id_equipo'] == 'B']
    
    if len(equipo_a_jugs) > 16 or len(equipo_b_jugs) > 16:
        return jsonify({'error': 'Máximo 16 jugadores por equipo'}), 400
        
    # Dorsales únicos
    for equipo_jugs in [equipo_a_jugs, equipo_b_jugs]:
        dorsales = [j['numero_camiseta'] for j in equipo_jugs if not j.get('es_generico')]
        if len(dorsales) != len(set(dorsales)):
            return jsonify({'error': 'Dorsales repetidos en un mismo equipo'}), 400
            
    # Al menos un portero (excepto generico)
    for eq_name, equipo_jugs in [('A', equipo_a_jugs), ('B', equipo_b_jugs)]:
        if not any(j.get('es_generico') for j in equipo_jugs):
            if not any(j.get('posicion') == 'PORTERO' for j in equipo_jugs):
                return jsonify({'error': f'El equipo {eq_name} debe tener al menos un portero'}), 400

    with get_db_connection() as conn:
        # La convocatoria no puede reescribirse si ya hay eventos: los DELETE
        # romperían las FK de Eventos_Juego (id_jugador). Bloqueo explícito.
        n_ev = conn.execute(
            'SELECT COUNT(*) AS c FROM Eventos_Juego WHERE id_partido = ?',
            (id_partido,)
        ).fetchone()['c']
        if n_ev > 0:
            return jsonify({'error': 'La convocatoria no puede modificarse porque el partido ya tiene eventos registrados'}), 400

        cursor = conn.cursor()
        # Eliminar actuales
        cursor.execute('DELETE FROM Jugadores WHERE id_partido = ?', (id_partido,))
        
        # Insertar nuevos
        for j in jugadores:
            cursor.execute('''
                INSERT INTO Jugadores (id_partido, id_plantel, nombre, id_equipo, numero_camiseta, posicion, es_generico)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                id_partido,
                j.get('id_plantel'),
                j.get('nombre', 'Generico'),
                j['id_equipo'],
                j.get('numero_camiseta', 0),
                j.get('posicion', 'CAMPO'),
                1 if j.get('es_generico') else 0
            ))
        conn.commit()
    return jsonify({'status': 'success'})

# ==========================================
# BLOQUE C: DESHACER, ANULAR Y CORREGIR
# ==========================================

@api_bp.route('/events/<client_event_id>/void', methods=['POST'])
def void_event(client_event_id):
    with get_db_connection() as conn:
        ev = conn.execute('SELECT id_partido, id_jugador, tipo_evento, anulado FROM Eventos_Juego WHERE client_event_id = ?', (client_event_id,)).fetchone()
        if not ev:
            return jsonify({'status': 'success', 'message': 'ignored'}), 200 # Could be pending or rejected earlier
            
        if ev['anulado'] == 0:
            conn.execute('UPDATE Eventos_Juego SET anulado = 1, anulado_en = CURRENT_TIMESTAMP WHERE client_event_id = ?', (client_event_id,))
            if ev['tipo_evento'] == 'EXCLUSION_2MIN':
                recalcular_disciplina(conn, ev['id_partido'], ev['id_jugador'], client_event_id)
            conn.commit()
            
    return jsonify({'status': 'success'})

@api_bp.route('/events/<client_event_id>/restore', methods=['POST'])
def restore_event(client_event_id):
    with get_db_connection() as conn:
        ev = conn.execute('SELECT id_partido, id_jugador, tipo_evento, anulado FROM Eventos_Juego WHERE client_event_id = ?', (client_event_id,)).fetchone()
        if not ev:
            return jsonify({'status': 'success', 'message': 'ignored'}), 200
            
        if ev['anulado'] == 1:
            conn.execute('UPDATE Eventos_Juego SET anulado = 0, anulado_en = NULL WHERE client_event_id = ?', (client_event_id,))
            if ev['tipo_evento'] == 'EXCLUSION_2MIN':
                recalcular_disciplina(conn, ev['id_partido'], ev['id_jugador'], client_event_id)
            conn.commit()
            
    return jsonify({'status': 'success'})

@api_bp.route('/events/<client_event_id>', methods=['PATCH'])
def patch_event(client_event_id):
    data = request.get_json()
    with get_db_connection() as conn:
        ev = conn.execute('SELECT * FROM Eventos_Juego WHERE client_event_id = ?', (client_event_id,)).fetchone()
        if not ev:
            return jsonify({'error': 'Event not found'}), 404
            
        # Revalidate
        merged = dict(ev)
        for k, v in data.items():
            merged[k] = v
        # El cuadrante y la distancia son derivados del punto: si el patch mueve
        # el tiro hay que volver a derivarlos, o la columna queda diciendo dónde
        # se lanzó un tiro que ya no está ahí.
        merged = normalizar_evento_legacy(merged)

        errores, warnings = validar_evento(merged)
        if errores:
            return jsonify({'error': errores}), 400
            
        updates, params = _armar_actualizaciones(data, merged)
                
        if not updates:
            return jsonify({'status': 'success'}), 200

        params.append(client_event_id)
        conn.execute(f"UPDATE Eventos_Juego SET {', '.join(updates)} WHERE client_event_id = ?", params)
        
        # Recalculate discipline just in case
        recalcular_disciplina(conn, merged['id_partido'], merged['id_jugador'], client_event_id)
        if merged['id_jugador'] != ev['id_jugador']:
            recalcular_disciplina(conn, ev['id_partido'], ev['id_jugador'], client_event_id)
            
        conn.commit()
    return jsonify({'status': 'success'})

@api_bp.route('/equipos/<int:id_equipo>/temporada', methods=['GET'])
def get_temporada_stats(id_equipo):
    # desde = request.args.get('desde')
    # hasta = request.args.get('hasta')
    
    with get_db_connection() as conn:
        plantel_rows = conn.execute('SELECT * FROM Plantel WHERE id_equipo = ?', (id_equipo,)).fetchall()
        
        # Solo jugadores con identidad de plantel (id_plantel NOT NULL).
        partidos_jugados = conn.execute('''
            SELECT j.id_plantel, COUNT(DISTINCT j.id_partido) as pj
            FROM Jugadores j
            JOIN Partidos p ON j.id_partido = p.id_partido
            WHERE j.id_plantel IS NOT NULL AND (p.id_equipo_a = ? OR p.id_equipo_b = ?) AND p.estado = 'FINALIZADO'
            GROUP BY j.id_plantel
        ''', (id_equipo, id_equipo)).fetchall()
        
        pj_dict = {row['id_plantel']: row['pj'] for row in partidos_jugados}
        
        # Sumar los eventos de esos jugadores en los partidos
        eventos = conn.execute('''
            SELECT e.tipo_evento, e.resultado, j.id_plantel 
            FROM Eventos_Juego e
            JOIN Jugadores j ON e.id_jugador = j.id_jugador
            JOIN Partidos p ON j.id_partido = p.id_partido
            WHERE j.id_plantel IS NOT NULL 
              AND (p.id_equipo_a = ? OR p.id_equipo_b = ?)
              AND p.estado = 'FINALIZADO'
              AND e.anulado = 0
        ''', (id_equipo, id_equipo)).fetchall()
        
        # Paradas de portero: solo las registradas con id_portero explícito.
        # Las atribuidas por aproximación en get_stats no se persisten y no se incluyen aquí.
        
        stats = {}
        for p in plantel_rows:
            pid = p['id_plantel']
            stats[pid] = {
                'id_plantel': pid,
                'nombre': p['nombre'],
                'posicion': p['posicion_habitual'],
                'partidos_jugados': pj_dict.get(pid, 0),
                'goles': 0,
                'tiros': 0,
                'asistencias': 0,
                'perdidas': 0,
                'robos': 0,
                'bloqueos': 0,
                'exclusiones': 0,
                'amarillas': 0,
                'rojas': 0,
                'paradas': 0
            }
            
        for ev in eventos:
            pid = ev['id_plantel']
            if pid not in stats: continue
            
            tipo = ev['tipo_evento']
            res = ev['resultado']
            
            if tipo in LANZAMIENTOS:
                stats[pid]['tiros'] += 1
                if res == 'GOL': stats[pid]['goles'] += 1
            elif tipo == 'ASISTENCIA': stats[pid]['asistencias'] += 1
            elif tipo in {'PERDIDA_BALON', 'FALTA_TECNICA', 'DOBLE', 'PASOS'}: stats[pid]['perdidas'] += 1
            elif tipo == 'ROBO_BALON': stats[pid]['robos'] += 1
            elif tipo == 'BLOQUEO': stats[pid]['bloqueos'] += 1
            elif tipo == 'EXCLUSION_2MIN': stats[pid]['exclusiones'] += 1
            elif tipo == 'AMARILLA': stats[pid]['amarillas'] += 1
            elif tipo in {'DESCALIFICACION', 'DESCALIFICACION_INFORME'}: stats[pid]['rojas'] += 1
            elif tipo == 'PARADA_PORTERO': stats[pid]['paradas'] += 1
        
        # To do goalkeepers paradas correctly we would need to check `id_portero` in Eventos_Juego.
        # Let's count them:
        paradas_porteros = conn.execute('''
            SELECT j.id_plantel, COUNT(*) as c
            FROM Eventos_Juego e
            JOIN Jugadores j ON e.id_portero = j.id_jugador
            JOIN Partidos p ON j.id_partido = p.id_partido
            WHERE e.resultado = 'PARADA' AND e.anulado = 0 AND p.estado = 'FINALIZADO'
            GROUP BY j.id_plantel
        ''').fetchall()
        
        for pp in paradas_porteros:
            pid = pp['id_plantel']
            if pid in stats:
                stats[pid]['paradas'] += pp['c']
                
        # Calculate % and avgs
        res = []
        for pid, s in stats.items():
            if s['tiros'] > 0:
                s['efic'] = round((s['goles'] / s['tiros']) * 100, 1)
            else:
                s['efic'] = 0.0
                
            res.append(s)
            
    return jsonify(res), 200


# ==========================================
# EXPORT & DELETE ENDPOINTS
# ==========================================

@api_bp.route('/matches/<int:match_id>', methods=['DELETE'])
def delete_match(match_id):
    with get_db_connection() as conn:
        # Check if exists
        p = conn.execute('SELECT * FROM Partidos WHERE id_partido = ?', (match_id,)).fetchone()
        if not p:
            return jsonify({'error': 'Partido no encontrado'}), 404
        
        # Delete dependencies
        conn.execute('DELETE FROM Eventos_Juego WHERE id_partido = ?', (match_id,))
        conn.execute('DELETE FROM Jugadores WHERE id_partido = ?', (match_id,))
        conn.execute('DELETE FROM Partidos WHERE id_partido = ?', (match_id,))
        
        conn.commit()
    return jsonify({'status': 'success'}), 200

@api_bp.route('/matches/<int:match_id>/export/json', methods=['GET'])
def export_match_json(match_id):
    with get_db_connection() as conn:
        eventos = conn.execute('''
            SELECT e.*, j.nombre as jugador_nombre, j.numero_camiseta, j.id_equipo
            FROM Eventos_Juego e
            LEFT JOIN Jugadores j ON e.id_jugador = j.id_jugador
            WHERE e.id_partido = ?
            ORDER BY e.id_evento ASC
        ''', (match_id,)).fetchall()
        
    data = [dict(row) for row in eventos]
    return jsonify(data)

@api_bp.route('/matches/<int:match_id>/export/csv', methods=['GET'])
def export_match_csv(match_id):
    with get_db_connection() as conn:
        eventos = conn.execute('''
            SELECT e.*, j.nombre as jugador_nombre, j.numero_camiseta, j.id_equipo
            FROM Eventos_Juego e
            LEFT JOIN Jugadores j ON e.id_jugador = j.id_jugador
            WHERE e.id_partido = ?
            ORDER BY e.id_evento ASC
        ''', (match_id,)).fetchall()

    if not eventos:
        return "No hay eventos para exportar", 404

    si = StringIO()
    writer = csv.writer(si)
    
    # Escribir cabeceras
    keys = list(dict(eventos[0]).keys())
    writer.writerow(keys)
    
    for row in eventos:
        writer.writerow([dict(row)[k] for k in keys])

    output = si.getvalue()
    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-disposition": f"attachment; filename=partido_{match_id}_eventos.csv"}
    )
