from flask import Blueprint, render_template, request, redirect, url_for, send_from_directory, current_app, jsonify
import os
from db import get_db_connection

web_bp = Blueprint('web', __name__)

# Versión de la app: debe coincidir con CACHE_NAME en static/sw.js.
# Hay un test que lo exige (test_version_coincide_con_sw). Bump en ambos.
APP_VERSION = 'bm-tracker-v27'

@web_bp.route('/')
def index():
    match_id = request.args.get('match', type=int)
    
    # Si no se pasó match_id, intentar cargar el último partido disponible
    if not match_id:
        with get_db_connection() as conn:
            last = conn.execute('SELECT id_partido FROM Partidos ORDER BY id_partido DESC LIMIT 1').fetchone()
            if last:
                match_id = last['id_partido']
    
    # Si sigue sin haber match_id (no hay partidos creados), ir a partidos
    if not match_id:
        return redirect(url_for('web.partidos'))
        
    with get_db_connection() as conn:
        partido = conn.execute('SELECT * FROM Partidos WHERE id_partido = ?', (match_id,)).fetchone()
        
        if partido:
            jugadores_a = conn.execute('SELECT * FROM Jugadores WHERE id_partido = ? AND id_equipo = ?', (match_id, 'A')).fetchall()
            jugadores_b = conn.execute('SELECT * FROM Jugadores WHERE id_partido = ? AND id_equipo = ?', (match_id, 'B')).fetchall()
        else:
            jugadores_a = []
            jugadores_b = []

    return render_template('index.html', partido=partido, jugadores_a=jugadores_a, jugadores_b=jugadores_b, app_version=APP_VERSION)

@web_bp.route('/partidos')
def partidos():
    return render_template('partidos.html')

@web_bp.route('/equipos')
def equipos():
    return render_template('equipos.html')

@web_bp.route('/nuevo_partido')
def nuevo_partido():
    return render_template('nuevo_partido.html')

@web_bp.route('/temporada')
def temporada():
    return render_template('temporada.html')

@web_bp.route('/stats')
def stats():
    match_id = request.args.get('match', type=int)
    if not match_id:
        with get_db_connection() as conn:
            last = conn.execute('SELECT id_partido FROM Partidos ORDER BY id_partido DESC LIMIT 1').fetchone()
            if last:
                match_id = last['id_partido']
    return render_template('stats.html', match_id=match_id or '')

@web_bp.route('/sw.js')
def service_worker():
    return send_from_directory(os.path.join(current_app.root_path, 'static'), 'sw.js', mimetype='application/javascript')

@web_bp.route('/manifest.webmanifest')
def manifest():
    return send_from_directory(os.path.join(current_app.root_path, 'static'), 'manifest.webmanifest', mimetype='application/manifest+json')
