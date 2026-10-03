import sqlite3
from flask import current_app, g, has_app_context
from contextlib import contextmanager

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(
            current_app.config['DATABASE_PATH'],
            detect_types=sqlite3.PARSE_DECLTYPES
        )
        g.db.execute("PRAGMA foreign_keys = ON;")
        g.db.row_factory = sqlite3.Row
    return g.db

def close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()

@contextmanager
def get_db_connection():
    """
    Context manager seguro para obtener una conexión a la BD, 
    asegurando que se apliquen las claves foráneas y que 
    se maneje adecuadamente dentro de peticiones aisladas,
    así como scripts fuera de request context.
    """
    # Si estamos dentro de un request context de Flask
    if has_app_context():
        conn = get_db()
        try:
            yield conn
        finally:
            # En request contexts, close_db se llamará por Flask al final.
            pass
    else:
        # Uso sin context de app (e.g. init_db)
        # Importación local para evitar circularidad
        from config import Config
        conn = sqlite3.connect(Config.DATABASE_PATH)
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

def _partidos_acepta_porteria(conn):
    """¿El CHECK de tipo_partido de la tabla ya menciona PORTERIA?

    El SQL de la tabla no se expone por PRAGMA, solo sqlite_master. Un INSERT
    de prueba serviría, pero depende de en qué transacción esté la conexión y
    deja estado que limpiar; leer el texto es directo y no toca datos.
    """
    sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'Partidos'"
    ).fetchone()
    return bool(sql and sql[0] and 'PORTERIA' in sql[0])


def _reconstruir_partidos_para_porteria(conn):
    """Rehace Partidos con el CHECK ampliado a PORTERIA.

    SQLite no puede tocar un CHECK con ALTER, hay que pasar por el procedimiento
    de rebuild. Las claves foráneas se apagan antes de abrir la transacción
    (dentro de una transacción el pragma no hace nada) y se vuelven a prender al
    final, así que Jugadores y Eventos_Juego no pierden su referencia.
    """
    conn.execute("PRAGMA foreign_keys=OFF")
    try:
        conn.execute("BEGIN")
        conn.execute("""
            CREATE TABLE Partidos_nueva (
                id_partido INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre_equipo_a TEXT NOT NULL,
                nombre_equipo_b TEXT NOT NULL,
                id_equipo_a INTEGER REFERENCES Equipos(id_equipo),
                id_equipo_b INTEGER REFERENCES Equipos(id_equipo),
                competicion TEXT,
                estado TEXT DEFAULT 'PROGRAMADO',
                fecha_partido TEXT NOT NULL,
                marcador_final_a INTEGER DEFAULT 0,
                marcador_final_b INTEGER DEFAULT 0,
                segundos_jugados INTEGER NOT NULL DEFAULT 0,
                periodo_actual INTEGER NOT NULL DEFAULT 1,
                en_pausa INTEGER NOT NULL DEFAULT 0,
                tipo_partido TEXT NOT NULL DEFAULT 'MI_EQUIPO'
                    CHECK (tipo_partido IN ('MI_EQUIPO','ANALISIS','PORTERIA'))
            )
        """)
        conn.execute("""
            INSERT INTO Partidos_nueva
                (id_partido, nombre_equipo_a, nombre_equipo_b, id_equipo_a, id_equipo_b,
                 competicion, estado, fecha_partido, marcador_final_a, marcador_final_b,
                 segundos_jugados, periodo_actual, en_pausa, tipo_partido)
            SELECT
                id_partido, nombre_equipo_a, nombre_equipo_b, id_equipo_a, id_equipo_b,
                competicion, estado, fecha_partido, marcador_final_a, marcador_final_b,
                segundos_jugados, periodo_actual, en_pausa, tipo_partido
            FROM Partidos
        """)
        conn.execute("DROP TABLE Partidos")
        conn.execute("ALTER TABLE Partidos_nueva RENAME TO Partidos")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.execute("PRAGMA foreign_keys=ON")


def migrate():
    import os
    from config import Config
    if not os.path.exists(Config.DATABASE_PATH):
        return
    conn = sqlite3.connect(Config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    try:
        cols = [r['name'] for r in conn.execute("PRAGMA table_info(Partidos)")]
        if 'tipo_partido' not in cols:
            conn.execute("ALTER TABLE Partidos ADD COLUMN tipo_partido TEXT NOT NULL DEFAULT 'MI_EQUIPO'")
            conn.commit()
        elif not _partidos_acepta_porteria(conn):
            _reconstruir_partidos_para_porteria(conn)
    except sqlite3.OperationalError:
        pass
    finally:
        conn.close()

def init_app(app):
    app.teardown_appcontext(close_db)
    migrate()
