from flask import Flask, render_template, request, jsonify
import sqlite3

app = Flask(__name__)

def get_db_connection():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def index():
    # Load match and player data to pass to the template
    conn = get_db_connection()
    
    # Obtener el último partido como activo (para el prototipo asumimos el ID 1)
    partido = conn.execute('SELECT * FROM Partidos ORDER BY id_partido DESC LIMIT 1').fetchone()
    
    if partido:
        jugadores_a = conn.execute('SELECT * FROM Jugadores WHERE id_equipo = ?', ('A',)).fetchall()
        jugadores_b = conn.execute('SELECT * FROM Jugadores WHERE id_equipo = ?', ('B',)).fetchall()
    else:
        jugadores_a = []
        jugadores_b = []

    conn.close()

    return render_template('index.html', partido=partido, jugadores_a=jugadores_a, jugadores_b=jugadores_b)

@app.route('/api/event', methods=['POST'])
def record_event():
    event_data = request.get_json()
    
    # Simple validation
    required_fields = ['id_partido', 'id_jugador', 'tipo_evento', 'tiempo_juego']
    if not all(k in event_data for k in required_fields):
        return jsonify({'status': 'error', 'message': 'Faltan datos'}), 400
        
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Guardar en SQLite
        cursor.execute('''
            INSERT INTO Eventos_Juego 
            (id_partido, id_jugador, tipo_evento, resultado, tiempo_juego, periodo, coordenada_x, coordenada_y, zona_porteria) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            event_data.get('id_partido'),
            event_data.get('id_jugador'),
            event_data.get('tipo_evento'),
            event_data.get('resultado'),
            event_data.get('tiempo_juego'),
            event_data.get('periodo', 1),
            event_data.get('coordenada_x'),
            event_data.get('coordenada_y'),
            event_data.get('zona_porteria')
        ))
        
        new_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return jsonify({'status': 'success', 'event_id': new_id}), 201
        
    except sqlite3.Error as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/matches/<int:match_id>/export', methods=['GET'])
def export_match(match_id):
    conn = get_db_connection()
    eventos = conn.execute('SELECT * FROM Eventos_Juego WHERE id_partido = ? ORDER BY id_evento ASC', (match_id,)).fetchall()
    conn.close()
    return jsonify([dict(ix) for ix in eventos]), 200

@app.route('/api/stats/<int:match_id>', methods=['GET'])
def get_stats(match_id):
    conn = get_db_connection()
    stats_query = '''
        SELECT 
            j.id_jugador, j.nombre, j.id_equipo, j.numero_camiseta,
            SUM(CASE WHEN e.resultado = 'GOL' THEN 1 ELSE 0 END) as goles,
            SUM(CASE WHEN e.tipo_evento LIKE 'LANZAMIENTO_%' OR e.tipo_evento = 'CONTRAATAQUE' THEN 1 ELSE 0 END) as lanzamientos_totales,
            SUM(CASE WHEN e.tipo_evento = 'ASISTENCIA' THEN 1 ELSE 0 END) as asistencias,
            SUM(CASE WHEN e.tipo_evento = 'PERDIDA_BALON' THEN 1 ELSE 0 END) as perdidas,
            SUM(CASE WHEN e.tipo_evento = 'ROBO_BALON' THEN 1 ELSE 0 END) as robos,
            SUM(CASE WHEN e.resultado = 'PARADA' THEN 1 ELSE 0 END) as tiros_detenidos_portero
        FROM Jugadores j
        LEFT JOIN Eventos_Juego e ON j.id_jugador = e.id_jugador AND e.id_partido = ?
        GROUP BY j.id_jugador
    '''
    jugadores = conn.execute(stats_query, (match_id,)).fetchall()
    
    result = []
    for row in jugadores:
        data = dict(row)
        # Eficiencia de tiro
        data['eficiencia_tiro'] = round((data['goles'] / data['lanzamientos_totales'] * 100), 1) if data['lanzamientos_totales'] > 0 else 0
        # GKI Proxy Index (Simplified: positive logic for saves)
        data['gki'] = data['tiros_detenidos_portero'] * 2 
        result.append(data)
        
    conn.close()
    return jsonify(result), 200

if __name__ == '__main__':
    app.run(debug=True, port=5000)
