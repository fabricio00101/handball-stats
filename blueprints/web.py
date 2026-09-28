from flask import Blueprint, render_template, request
from db import get_db_connection

web_bp = Blueprint('web', __name__)

@web_bp.route('/')
def index():
    with get_db_connection() as conn:
        match_id = request.args.get('match', type=int)
        
        if match_id:
            partido = conn.execute('SELECT * FROM Partidos WHERE id_partido = ?', (match_id,)).fetchone()
        else:
            partido = conn.execute('SELECT * FROM Partidos ORDER BY id_partido DESC LIMIT 1').fetchone()
        
        if partido:
            jugadores_a = conn.execute('SELECT * FROM Jugadores WHERE id_equipo = ?', ('A',)).fetchall()
            jugadores_b = conn.execute('SELECT * FROM Jugadores WHERE id_equipo = ?', ('B',)).fetchall()
        else:
            jugadores_a = []
            jugadores_b = []

    return render_template('index.html', partido=partido, jugadores_a=jugadores_a, jugadores_b=jugadores_b)

@web_bp.route('/stats')
def stats():
    match_id = request.args.get('match', type=int)
    if not match_id:
        with get_db_connection() as conn:
            last = conn.execute('SELECT id_partido FROM Partidos ORDER BY id_partido DESC LIMIT 1').fetchone()
            if last:
                match_id = last['id_partido']
    return render_template('stats.html', match_id=match_id)
