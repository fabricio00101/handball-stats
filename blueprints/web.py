from flask import Blueprint, render_template, request, redirect, url_for, send_from_directory, current_app, jsonify
import os
from db import get_db_connection

web_bp = Blueprint('web', __name__)

# Versión de la app: debe coincidir con CACHE_NAME en static/sw.js.
# Hay un test que lo exige (test_version_coincide_con_sw). Bump en ambos.
APP_VERSION = 'bm-tracker-v33'

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

        # Un partido de portería se captura en su propia pantalla: la normal
        # no sabe pedir el punto del tiro ni qué arquero está en el arco. Mandarlo
        # a /porteria en vez de dejar una pantalla a medias.
        if partido and partido['tipo_partido'] == 'PORTERIA':
            return redirect(url_for('web.porteria', match=match_id))

        if partido:
            jugadores_a = conn.execute('SELECT * FROM Jugadores WHERE id_partido = ? AND id_equipo = ?', (match_id, 'A')).fetchall()
            jugadores_b = conn.execute('SELECT * FROM Jugadores WHERE id_partido = ? AND id_equipo = ?', (match_id, 'B')).fetchall()
        else:
            jugadores_a = []
            jugadores_b = []

    # En modo análisis la captura se hace por dorsal, así que el template
    # necesita poder preguntar "¿existe el dorsal 7 del equipo A?". Indexarlo
    # acá evita hacerlo en Jinja en cada celda del 1..20.
    dorsales_a = {j['numero_camiseta']: j for j in jugadores_a}
    dorsales_b = {j['numero_camiseta']: j for j in jugadores_b}

    return render_template('index.html', partido=partido, jugadores_a=jugadores_a,
                           jugadores_b=jugadores_b, dorsales_a=dorsales_a,
                           dorsales_b=dorsales_b, app_version=APP_VERSION)

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

    # Un partido de portería tiene su propio análisis, en su propia pantalla. acá
    # solo hay tiros del rival sin ningún jugador nuestro que los haya tirado, así
    # que la página de estadísticas saldría vacía. Al redirigir, un enlace viejo
    # o un marcador de página atrás siguen llevando al lugar correcto.
    if match_id:
        with get_db_connection() as conn:
            fila = conn.execute(
                'SELECT tipo_partido FROM Partidos WHERE id_partido = ?', (match_id,)
            ).fetchone()
        if fila and fila['tipo_partido'] == 'PORTERIA':
            return redirect(url_for('web.porteria', match=match_id, vista='analizar'))

    return render_template('stats.html', match_id=match_id or '')

@web_bp.route('/porteria')
def porteria():
    """Herramienta de portería: captura de media cancha y análisis, del mismo
    partido. Las dos pestañas son vistas de esta pantalla, no dos apps.

    Un partido que no es de PORTERIA no se rechaza con un redirect: se muestra
    el aviso acá adentro con el enlace para crear uno, porque redirigir sin más
    deja al operador pensando que rompió algo.

    El plantel y el reloj vienen del servidor y no de un fetch a propósito: la
    captura es la pantalla que se usa en la cancha, con una mano ocupada, y
    tiene que abrir igual aunque la red entre y salga.
    """
    match_id = request.args.get('match', type=int)
    vista = request.args.get('vista', default='capturar')
    if vista not in ('capturar', 'analizar'):
        vista = 'capturar'

    partido = None
    jugadores_a = []
    if match_id:
        with get_db_connection() as conn:
            fila = conn.execute(
                'SELECT * FROM Partidos WHERE id_partido = ?', (match_id,)
            ).fetchone()
        if fila:
            partido = dict(fila)
            if partido['tipo_partido'] == 'PORTERIA':
                # Todos los del equipo A pueden ir al arco, no solo los marcados
                # PORTERO: en un entrenamiento el campoista de turno ataja, y
                # si no está en la lista no hay forma de registrarlo.
                with get_db_connection() as conn:
                    jugadores_a_raw = [dict(j) for j in conn.execute(
                        "SELECT id_jugador, nombre, numero_camiseta, posicion "
                        "FROM Jugadores WHERE id_partido = ? AND id_equipo = 'A' "
                        "ORDER BY (posicion = 'PORTERO') DESC, numero_camiseta",
                        (match_id,)
                    ).fetchall()]
                    jugadores_a = [
                        j for j in jugadores_a_raw
                        if (j.get('posicion') or '').upper() == 'PORTERO'
                    ]
                    if not jugadores_a:
                        jugadores_a = jugadores_a_raw
                    fila_rival = conn.execute(
                        "SELECT id_jugador FROM Jugadores "
                        "WHERE id_partido = ? AND id_equipo = 'B' AND es_generico = 1 "
                        "ORDER BY id_jugador LIMIT 1",
                        (match_id,)
                    ).fetchone()
                    partido['rival_generico_id'] = fila_rival['id_jugador'] if fila_rival else None
            else:
                partido = None   # se muestra el aviso, no una pantalla a medias
        else:
            match_id = None   # el partido no existe: la pantalla lo avisa

    return render_template('porteria.html', match_id=match_id or '', partido=partido,
                           jugadores_a=jugadores_a, vista=vista, app_version=APP_VERSION)

@web_bp.route('/comparar')
def comparar():
    analisis = request.args.get('analisis', type=int)
    eq = request.args.get('eq', default='A')      # equipo del partido de análisis a comparar
    mio = request.args.get('mio', type=int)       # partido de mi equipo (opcional: se elige en la pantalla)
    
    # cargar ambos Partidos (para nombres)
    with get_db_connection() as conn:
        p_analisis = conn.execute('SELECT * FROM Partidos WHERE id_partido = ?', (analisis,)).fetchone() if analisis else None
        p_mio = conn.execute('SELECT * FROM Partidos WHERE id_partido = ?', (mio,)).fetchone() if mio else None

    # El partido de análisis es obligatorio: sin él no hay nada que comparar.
    # El de mi equipo NO: la pantalla ofrece un selector y arranca vacío.
    if not p_analisis:
        return redirect(url_for('web.partidos'))
        
    # Ignorar un 'mio' que no exista en vez de expulsar al usuario de la pantalla.
    if mio and not p_mio:
        mio = None
        p_mio = None

    # Solo MI_EQUIPO es comparable: un partido de análisis no es "mi equipo".
    if p_mio and p_mio['tipo_partido'] == 'ANALISIS':
        mio = None
        p_mio = None
        
    nombre_analisis = p_analisis['nombre_equipo_a'] if eq == 'A' else p_analisis['nombre_equipo_b']
    nombre_mio = p_mio['nombre_equipo_a'] if p_mio else ''
    
    return render_template('comparar.html', analisis=analisis, eq=eq, mio=mio,
                           nombre_analisis=nombre_analisis, nombre_eq=eq, nombre_mio=nombre_mio, app_version=APP_VERSION)

@web_bp.route('/sw.js')
def service_worker():
    return send_from_directory(os.path.join(current_app.root_path, 'static'), 'sw.js', mimetype='application/javascript')

@web_bp.route('/manifest.webmanifest')
def manifest():
    return send_from_directory(os.path.join(current_app.root_path, 'static'), 'manifest.webmanifest', mimetype='application/manifest+json')
