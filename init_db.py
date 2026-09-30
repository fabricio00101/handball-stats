import sqlite3
import os

def init_db():
    if os.path.exists('database.db'):
        os.remove('database.db')
        
    connection = sqlite3.connect('database.db')
    connection.execute("PRAGMA foreign_keys = ON;")

    with open('schema.sql', 'r', encoding='utf-8') as f:
        connection.executescript(f.read())

    cur = connection.cursor()

    # 1. Equipos
    cur.execute("INSERT INTO Equipos (nombre, es_propio) VALUES ('Los Halcones', 1)")
    eq_a = cur.lastrowid
    cur.execute("INSERT INTO Equipos (nombre, es_propio) VALUES ('Tormenta FC', 0)")
    eq_b = cur.lastrowid
    
    cur.execute("INSERT INTO Equipos (nombre, es_propio) VALUES ('Rival Genérico', 0)")
    eq_rival = cur.lastrowid

    # 2. Plantel
    jugadores_a = [
        ('Juan Pérez', 10, 'CAMPO'),
        ('Carlos Gómez', 7, 'CAMPO'),
        ('Luis Rodríguez', 1, 'PORTERO'),
    ]
    jugadores_b = [
        ('Pedro Sánchez', 9, 'CAMPO'),
        ('Miguel Torres', 4, 'CAMPO'),
        ('Jorge Vázquez', 12, 'PORTERO'),
    ]
    
    plantel_a_ids = []
    for nombre, num, pos in jugadores_a:
        cur.execute("INSERT INTO Plantel (id_equipo, nombre, numero_habitual, posicion_habitual) VALUES (?, ?, ?, ?)", 
                    (eq_a, nombre, num, pos))
        plantel_a_ids.append((cur.lastrowid, nombre, num, pos))
        
    plantel_b_ids = []
    for nombre, num, pos in jugadores_b:
        cur.execute("INSERT INTO Plantel (id_equipo, nombre, numero_habitual, posicion_habitual) VALUES (?, ?, ?, ?)", 
                    (eq_b, nombre, num, pos))
        plantel_b_ids.append((cur.lastrowid, nombre, num, pos))

    # 3. Partido
    cur.execute("INSERT INTO Partidos (nombre_equipo_a, nombre_equipo_b, id_equipo_a, id_equipo_b, fecha_partido) VALUES (?, ?, ?, ?, ?)",
                ('Los Halcones', 'Tormenta FC', eq_a, eq_b, '2026-03-11'))
    match_id = cur.lastrowid

    # 4. Jugadores (Convocatoria)
    for p_id, nombre, num, pos in plantel_a_ids:
        cur.execute("INSERT INTO Jugadores (id_partido, id_plantel, nombre, id_equipo, numero_camiseta, posicion) VALUES (?, ?, ?, 'A', ?, ?)",
                    (match_id, p_id, nombre, num, pos))
                    
    for p_id, nombre, num, pos in plantel_b_ids:
        cur.execute("INSERT INTO Jugadores (id_partido, id_plantel, nombre, id_equipo, numero_camiseta, posicion) VALUES (?, ?, ?, 'B', ?, ?)",
                    (match_id, p_id, nombre, num, pos))

    # Rival genérico dorsal 0: actor de todo lo que hace el rival (modo sin dorsales)
    cur.execute("INSERT INTO Jugadores (id_partido, id_plantel, nombre, id_equipo, numero_camiseta, posicion, es_generico) VALUES (?, NULL, 'Rival (sin dorsal)', 'B', 0, 'CAMPO', 1)",
                (match_id,))

    # 5. Eventos v3
    # Event 1: Team A player (Juan Pérez, id_jugador=1) shoots 6m, outcome GOL
    cur.execute("""
        INSERT INTO Eventos_Juego 
        (id_partido, id_jugador, tipo_evento, resultado, tiempo_juego, periodo, segundo_absoluto, coordenada_x, coordenada_y, zona_porteria, lado, distancia, client_event_id)
        VALUES (?, ?, 'LANZAMIENTO', 'GOL', '02:15', 1, 135, 0.45, 0.20, 'TR', 'ATAQUE', '6M', 'seed-event-1')
    """, (match_id, 1))

    # Event 2: Team A player (Carlos Gómez, id_jugador=2) shoots 6m, outcome PARADA by goalkeeper (id_portero=6)
    cur.execute("""
        INSERT INTO Eventos_Juego 
        (id_partido, id_jugador, tipo_evento, resultado, tiempo_juego, periodo, segundo_absoluto, coordenada_x, coordenada_y, zona_porteria, lado, distancia, id_portero, client_event_id)
        VALUES (?, ?, 'LANZAMIENTO', 'PARADA', '05:30', 1, 330, 0.50, 0.15, 'TC', 'ATAQUE', '6M', 6, 'seed-event-2')
    """, (match_id, 2))

    # Event 3: Team B player (Pedro Sánchez, id_jugador=4) shoots 9m, outcome PARADA
    cur.execute("""
        INSERT INTO Eventos_Juego 
        (id_partido, id_jugador, tipo_evento, resultado, tiempo_juego, periodo, segundo_absoluto, coordenada_x, coordenada_y, zona_porteria, lado, distancia, id_portero, client_event_id)
        VALUES (?, ?, 'LANZAMIENTO', 'PARADA', '08:10', 1, 490, 0.60, 0.35, 'BC', 'ATAQUE', '9M', 3, 'seed-event-3')
    """, (match_id, 4))

    connection.execute("PRAGMA user_version = 3;")
    connection.commit()
    connection.close()
    
    print("Base de datos inicializada correctamente con esquema v3 y datos de prueba.")

if __name__ == '__main__':
    init_db()
