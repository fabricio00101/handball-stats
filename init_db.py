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

    # Insert a dummy match
    cur.execute("INSERT INTO Partidos (nombre_equipo_a, nombre_equipo_b, fecha_partido) VALUES (?, ?, ?)",
                ('Los Halcones', 'Tormenta FC', '2026-03-11'))
    
    match_id = cur.lastrowid

    # Insert dummy players for Team A (Los Halcones)
    equipo_a_jugadores = [
        ('Juan Pérez', 'A', 10),
        ('Carlos Gómez', 'A', 7),
        ('Luis Rodríguez', 'A', 1), # Portero
    ]
    
    # Insert dummy players for Team B (Tormenta FC)
    equipo_b_jugadores = [
        ('Pedro Sánchez', 'B', 9),
        ('Miguel Torres', 'B', 4),
        ('Jorge Vázquez', 'B', 12), # Portero
    ]

    for j in equipo_a_jugadores + equipo_b_jugadores:
        cur.execute("INSERT INTO Jugadores (nombre, id_equipo, numero_camiseta) VALUES (?, ?, ?)", j)

    # Insert dummy seed events for testing metrics and GKI
    # Event 1: Team A player (Juan Pérez, id=1) shoots 6m, outcome GOL
    cur.execute("""
        INSERT INTO Eventos_Juego 
        (id_partido, id_jugador, tipo_evento, resultado, tiempo_juego, periodo, coordenada_x, coordenada_y, zona_porteria, lado, client_event_id)
        VALUES (?, ?, 'LANZAMIENTO_6M', 'GOL', '02:15', 1, 0.45, 0.20, 'TR', 'ATAQUE', 'seed-event-1')
    """, (match_id, 1))

    # Event 2: Team A player (Carlos Gómez, id=2) shoots 6m, outcome PARADA by goalkeeper
    cur.execute("""
        INSERT INTO Eventos_Juego 
        (id_partido, id_jugador, tipo_evento, resultado, tiempo_juego, periodo, coordenada_x, coordenada_y, zona_porteria, lado, client_event_id)
        VALUES (?, ?, 'LANZAMIENTO_6M', 'PARADA', '05:30', 1, 0.50, 0.15, 'TC', 'ATAQUE', 'seed-event-2')
    """, (match_id, 2))

    # Event 3: Team B player (Pedro Sánchez, id=4) shoots 9m, outcome PARADA
    cur.execute("""
        INSERT INTO Eventos_Juego 
        (id_partido, id_jugador, tipo_evento, resultado, tiempo_juego, periodo, coordenada_x, coordenada_y, zona_porteria, lado, client_event_id)
        VALUES (?, ?, 'LANZAMIENTO_9M', 'PARADA', '08:10', 1, 0.60, 0.35, 'BC', 'ATAQUE', 'seed-event-3')
    """, (match_id, 4))

    connection.commit()
    connection.close()
    
    print("Base de datos inicializada correctamente con esquema v2 y datos de prueba.")

if __name__ == '__main__':
    init_db()
