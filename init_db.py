import sqlite3
import os

def init_db():
    # Remove existing db if it exists
    if os.path.exists('database.db'):
        os.remove('database.db')
        
    connection = sqlite3.connect('database.db')

    with open('schema.sql', 'r', encoding='utf-8') as f:
        connection.executescript(f.read())

    cur = connection.cursor()

    # Insert a dummy match
    cur.execute("INSERT INTO Partidos (nombre_equipo_a, nombre_equipo_b, fecha_partido) VALUES (?, ?, ?)",
                ('Los Halcones', 'Tormenta FC', '2026-03-11'))
    
    match_id = cur.lastrowid

    # Insert dummy players for Team A
    equipo_a_jugadores = [
        ('Juan Pérez', 'A', 10),
        ('Carlos Gómez', 'A', 7),
        ('Luis Rodríguez', 'A', 1), # Portero
    ]
    
    # Insert dummy players for Team B
    equipo_b_jugadores = [
        ('Pedro Sánchez', 'B', 9),
        ('Miguel Torres', 'B', 4),
        ('Jorge Vázquez', 'B', 12), # Portero
    ]

    for j in equipo_a_jugadores + equipo_b_jugadores:
        cur.execute("INSERT INTO Jugadores (nombre, id_equipo, numero_camiseta) VALUES (?, ?, ?)", j)

    connection.commit()
    connection.close()
    
    print("Base de datos inicializada correctamente con datos de prueba.")

if __name__ == '__main__':
    init_db()
