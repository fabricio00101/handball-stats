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

    # Inicializar BD de pruebas usando schema.sql
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")
    with open('schema.sql', 'r', encoding='utf-8') as f:
        conn.executescript(f.read())
    
    # Sembrar datos dummy
    cur = conn.cursor()
    cur.execute("INSERT INTO Equipos (nombre, es_propio) VALUES ('Equipo A', 1)")
    eq_a = cur.lastrowid
    cur.execute("INSERT INTO Equipos (nombre, es_propio) VALUES ('Equipo B', 0)")
    eq_b = cur.lastrowid
    
    cur.execute("INSERT INTO Plantel (id_equipo, nombre, numero_habitual, posicion_habitual) VALUES (?, 'Jugador A1', 10, 'CAMPO')", (eq_a,))
    pa1 = cur.lastrowid
    cur.execute("INSERT INTO Plantel (id_equipo, nombre, numero_habitual, posicion_habitual) VALUES (?, 'Portero B1', 12, 'PORTERO')", (eq_b,))
    pb1 = cur.lastrowid
    cur.execute("INSERT INTO Plantel (id_equipo, nombre, numero_habitual, posicion_habitual) VALUES (?, 'Portero Raro B2', 5, 'PORTERO')", (eq_b,))
    pb2 = cur.lastrowid
    
    cur.execute("INSERT INTO Partidos (nombre_equipo_a, nombre_equipo_b, id_equipo_a, id_equipo_b, fecha_partido) VALUES ('Equipo A', 'Equipo B', ?, ?, '2026-03-11')", (eq_a, eq_b))
    match_id = cur.lastrowid
    
    cur.execute("INSERT INTO Jugadores (id_partido, id_plantel, nombre, id_equipo, numero_camiseta, posicion) VALUES (?, ?, 'Jugador A1', 'A', 10, 'CAMPO')", (match_id, pa1))
    cur.execute("INSERT INTO Jugadores (id_partido, id_plantel, nombre, id_equipo, numero_camiseta, posicion) VALUES (?, ?, 'Portero B1', 'B', 12, 'PORTERO')", (match_id, pb1))
    cur.execute("INSERT INTO Jugadores (id_partido, id_plantel, nombre, id_equipo, numero_camiseta, posicion) VALUES (?, ?, 'Portero Raro B2', 'B', 5, 'PORTERO')", (match_id, pb2))
    # Arquero propio (modo tiro rival) + rival genérico dorsal 0 (actor del rival)
    cur.execute("INSERT INTO Plantel (id_equipo, nombre, numero_habitual, posicion_habitual) VALUES (?, 'Portero A1', 1, 'PORTERO')", (eq_a,))
    pa_gk = cur.lastrowid
    cur.execute("INSERT INTO Jugadores (id_partido, id_plantel, nombre, id_equipo, numero_camiseta, posicion) VALUES (?, ?, 'Portero A1', 'A', 1, 'PORTERO')", (match_id, pa_gk))
    cur.execute("INSERT INTO Jugadores (id_partido, id_plantel, nombre, id_equipo, numero_camiseta, posicion, es_generico) VALUES (?, NULL, 'Rival (sin dorsal)', 'B', 0, 'CAMPO', 1)", (match_id,))
    
    conn.commit()
    conn.close()

    with flask_app.app.test_client() as client:
        yield client

    os.close(db_fd)
    os.unlink(db_path)
