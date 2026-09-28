from flask import Blueprint, request, jsonify
import sqlite3
from db import get_db_connection
from services.eventos import validar_evento, verificar_advertencia_7m, tiempo_a_segundos
from services.metrics import (
    eficiencia_tiro, efectividad_portero, gki, mas_menos, LANZAMIENTOS
)

api_bp = Blueprint('api', __name__, url_prefix='/api')

@api_bp.route('/event', methods=['POST'])
def record_event():
    event_data = request.get_json() or {}
    
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
                (id_partido, id_jugador, tipo_evento, resultado, tiempo_juego, periodo, coordenada_x, coordenada_y, zona_porteria, lado, client_event_id) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(client_event_id) DO NOTHING
            ''', (
                event_data.get('id_partido'),
                event_data.get('id_jugador'),
                event_data.get('tipo_evento'),
                event_data.get('resultado'),
                event_data.get('tiempo_juego'),
                event_data.get('periodo', 1),
                event_data.get('coordenada_x'),
                event_data.get('coordenada_y'),
                event_data.get('zona_porteria'),
                event_data.get('lado', 'ATAQUE'),
                client_event_id
            ))
            
            new_id = cursor.lastrowid
            conn.commit()
            
            if cursor.rowcount == 0 and client_event_id:
                existing = conn.execute('SELECT id_evento FROM Eventos_Juego WHERE client_event_id = ?', (client_event_id,)).fetchone()
                existing_id = existing['id_evento'] if existing else None
                return jsonify({'status': 'success', 'event_id': existing_id, 'duplicate': True, 'warnings': all_warnings}), 200

            return jsonify({'status': 'success', 'event_id': new_id, 'warnings': all_warnings}), 201

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
                client_event_id = event_data.get('client_event_id')
                errores, warnings_val = validar_evento(event_data)

                if errores:
                    rechazados.append({
                        'client_event_id': client_event_id,
                        'error': ', '.join(errores)
                    })
                    continue

                try:
                    cursor.execute('''
                        INSERT INTO Eventos_Juego 
                        (id_partido, id_jugador, tipo_evento, resultado, tiempo_juego, periodo, coordenada_x, coordenada_y, zona_porteria, lado, client_event_id) 
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(client_event_id) DO NOTHING
                    ''', (
                        event_data.get('id_partido'),
                        event_data.get('id_jugador'),
                        event_data.get('tipo_evento'),
                        event_data.get('resultado'),
                        event_data.get('tiempo_juego'),
                        event_data.get('periodo', 1),
                        event_data.get('coordenada_x'),
                        event_data.get('coordenada_y'),
                        event_data.get('zona_porteria'),
                        event_data.get('lado', 'ATAQUE'),
                        client_event_id
                    ))
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
            WHERE e.id_partido = ? AND j.id_equipo = 'A' AND e.resultado = 'GOL'
        ''', (match_id,)).fetchone()['c']

        goles_b = conn.execute('''
            SELECT COUNT(*) as c FROM Eventos_Juego e
            JOIN Jugadores j ON e.id_jugador = j.id_jugador
            WHERE e.id_partido = ? AND j.id_equipo = 'B' AND e.resultado = 'GOL'
        ''', (match_id,)).fetchone()['c']

        ultimo_evento = conn.execute('''
            SELECT e.*, j.id_equipo FROM Eventos_Juego e
            JOIN Jugadores j ON e.id_jugador = j.id_jugador
            WHERE e.id_partido = ?
            ORDER BY e.id_evento DESC LIMIT 1
        ''', (match_id,)).fetchone()

        posesion_actual = 'A'
        if ultimo_evento:
            ev = dict(ultimo_evento)
            eq = ev['id_equipo']
            res = ev['resultado']
            tipo = ev['tipo_evento']

            if res == 'GOL' or tipo in {'PERDIDA_BALON', 'FALTA_TECNICA', 'DOBLE', 'PASOS'}:
                posesion_actual = 'B' if eq == 'A' else 'A'
            elif res == 'PARADA' or tipo in {'PARADA_PORTERO', 'ROBO_BALON', 'BLOQUEO'}:
                posesion_actual = eq

        seg_actuales = partido.get('segundos_jugados', 0)
        exclusiones_rows = conn.execute('''
            SELECT e.id_jugador, e.tiempo_juego FROM Eventos_Juego e
            WHERE e.id_partido = ? AND e.tipo_evento = 'EXCLUSION_2MIN'
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

        return jsonify({
            'id_partido': match_id,
            'marcador_a': goles_a,
            'marcador_b': goles_b,
            'posesion_actual': posesion_actual,
            'segundos_jugados': seg_actuales,
            'periodo_actual': partido.get('periodo_actual', 1),
            'en_pausa': partido.get('en_pausa', 0),
            'exclusiones_activas': exclusiones_activas
        }), 200


@api_bp.route('/matches/<int:match_id>/state', methods=['PATCH'])
def update_match_state(match_id):
    data = request.get_json() or {}
    
    segundos_jugados = data.get('segundos_jugados')
    periodo_actual = data.get('periodo_actual')
    en_pausa = data.get('en_pausa')

    updates = []
    params = []
    if segundos_jugados is not None:
        updates.append("segundos_jugados = ?")
        params.append(int(segundos_jugados))
    if periodo_actual is not None:
        updates.append("periodo_actual = ?")
        params.append(int(periodo_actual))
    if en_pausa is not None:
        updates.append("en_pausa = ?")
        params.append(int(en_pausa))

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
        jugadores_rows = conn.execute('SELECT * FROM Jugadores WHERE id_equipo IN ("A", "B") ORDER BY id_equipo, numero_camiseta').fetchall()
        jugadores_list = [dict(j) for j in jugadores_rows]
        
        eventos_rows = conn.execute('SELECT e.*, j.id_equipo FROM Eventos_Juego e JOIN Jugadores j ON e.id_jugador = j.id_jugador WHERE e.id_partido = ? ORDER BY e.id_evento ASC', (match_id,)).fetchall()
        eventos = [dict(ev) for ev in eventos_rows]

    # Map players
    jugadores_dict = {}
    for j in jugadores_list:
        jid = j['id_jugador']
        jugadores_dict[jid] = {
            'id_jugador': jid,
            'nombre': j['nombre'],
            'id_equipo': j['id_equipo'],
            'numero_camiseta': j['numero_camiseta'],
            'goles': 0,
            'lanzamientos_totales': 0,
            'eficiencia_tiro': 0.0,
            'asistencias': 0,
            'perdidas': 0,
            'robos': 0,
            'bloqueos': 0,
            'exclusiones_2min': 0,
            'sanciones': 0,
            'es_portero': (j['numero_camiseta'] in (1, 12, 16)),
            'paradas': 0,
            'tiros_recibidos': 0,
            'efectividad_portero': 0.0,
            'paradas_por_tipo': {},
            'gki': 0.0,
            'mas_menos': 0,
            'mas_menos_tipo': 'proxy_posesion'
        }

    # Contadores de equipo y partido
    goles_a = 0
    goles_b = 0
    lanz_a = 0
    lanz_b = 0
    excl_a = 0
    excl_b = 0

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
                
                if res == 'GOL':
                    jstats['goles'] += 1
                    if equipo == 'A': goles_a += 1
                    else: goles_b += 1

            elif tipo == 'ASISTENCIA':
                jstats['asistencias'] += 1
            elif tipo in {'PERDIDA_BALON', 'FALTA_TECNICA', 'DOBLE', 'PASOS'}:
                jstats['perdidas'] += 1
            elif tipo == 'ROBO_BALON':
                jstats['robos'] += 1
            elif tipo == 'BLOQUEO':
                jstats['bloqueos'] += 1
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
            equipo_rival = 'B' if equipo == 'A' else 'A'
            porteros_rivales = [pj for pj in jugadores_dict.values() if pj['id_equipo'] == equipo_rival and pj['es_portero']]
            if porteros_rivales:
                port = porteros_rivales[0]
                port['paradas'] += 1
                port['paradas_por_tipo'][tipo] = port['paradas_por_tipo'].get(tipo, 0) + 1

    stats_jugadores = []
    for jstats in jugadores_dict.values():
        jstats['eficiencia_tiro'] = eficiencia_tiro(jstats['goles'], jstats['lanzamientos_totales'])
        
        if jstats['es_portero'] or jstats['paradas'] > 0:
            goles_rivales = goles_b if jstats['id_equipo'] == 'A' else goles_a
            jstats['tiros_recibidos'] = jstats['paradas'] + goles_rivales
            jstats['efectividad_portero'] = efectividad_portero(jstats['paradas'], jstats['tiros_recibidos'])
            jstats['gki'] = gki(jstats['paradas_por_tipo'])

        jstats['mas_menos'] = mas_menos(
            goles_a if jstats['id_equipo'] == 'A' else goles_b,
            goles_b if jstats['id_equipo'] == 'A' else goles_a
        )
        stats_jugadores.append(jstats)

    resumen_equipos = [
        {
            "id_equipo": "A",
            "nombre": partido.get('nombre_equipo_a', 'Equipo A'),
            "goles": goles_a,
            "lanzamientos": lanz_a,
            "eficiencia_tiro": eficiencia_tiro(goles_a, lanz_a),
            "exclusiones": excl_a
        },
        {
            "id_equipo": "B",
            "nombre": partido.get('nombre_equipo_b', 'Equipo B'),
            "goles": goles_b,
            "lanzamientos": lanz_b,
            "eficiencia_tiro": eficiencia_tiro(goles_b, lanz_b),
            "exclusiones": excl_b
        }
    ]

    response = {
        "partido": {
            "id": partido['id_partido'],
            "nombre_equipo_a": partido['nombre_equipo_a'],
            "nombre_equipo_b": partido['nombre_equipo_b'],
            "marcador_a": goles_a,
            "marcador_b": goles_b,
            "periodo": 1
        },
        "resumen": {
            "goles_totales": goles_a + goles_b,
            "lanzamientos_totales": lanz_a + lanz_b
        },
        "equipos": resumen_equipos,
        "jugadores": stats_jugadores
    }

    return jsonify(response), 200

@api_bp.route('/matches/<int:match_id>/heatmap', methods=['GET'])
def get_heatmap(match_id):
    with get_db_connection() as conn:
        eventos_rows = conn.execute('''
            SELECT tipo_evento, resultado, zona_porteria, coordenada_x, coordenada_y 
            FROM Eventos_Juego 
            WHERE id_partido = ? AND tipo_evento IN (
                'LANZAMIENTO_6M', 'LANZAMIENTO_9M', 'LANZAMIENTO_7M', 'CONTRAATAQUE'
            )
        ''', (match_id,)).fetchall()

    porteria = {z: {'goles': 0, 'paradas': 0, 'fallos': 0, 'total': 0} for z in 
                ['TL', 'TC', 'TR', 'ML', 'MC', 'MR', 'BL', 'BC', 'BR']}
    zonas_tiro = {}
    origen = []

    for ev in eventos_rows:
        zona = ev['zona_porteria']
        res = ev['resultado']
        tipo = ev['tipo_evento']
        x = ev['coordenada_x']
        y = ev['coordenada_y']

        if zona in porteria:
            porteria[zona]['total'] += 1
            if res == 'GOL': porteria[zona]['goles'] += 1
            elif res == 'PARADA': porteria[zona]['paradas'] += 1
            else: porteria[zona]['fallos'] += 1
        
        zonas_tiro[tipo] = zonas_tiro.get(tipo, 0) + 1

        if x is not None and y is not None:
            origen.append({'x': x, 'y': y, 'resultado': res})

    return jsonify({
        'porteria': porteria,
        'zonas_tiro': zonas_tiro,
        'origen': origen
    }), 200
