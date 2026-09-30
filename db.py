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

def init_app(app):
    app.teardown_appcontext(close_db)
