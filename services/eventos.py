"""
Módulo de validación de eventos de dominio y reglas de juego de balonmano.
"""

LANZAMIENTOS = {"LANZAMIENTO", "LANZAMIENTO_6M", "LANZAMIENTO_9M", "LANZAMIENTO_7M", "CONTRAATAQUE"}
OFENSIVA = {"ASISTENCIA"}
DEFENSIVA = {"ROBO_BALON", "BLOQUEO", "PARADA_PORTERO"}
ERRORES = {"PERDIDA_BALON", "FALTA_TECNICA", "DOBLE", "PASOS"}
FALTAS = {"FALTA"}
DISCIPLINA = {"AMARILLA", "EXCLUSION_2MIN", "DESCALIFICACION"}

# Eventos que cambian la posesión (espejo de actualizarPosesionInteligente en app.js):
# el tiro con resultado y el error entregan el balón a la defensa; la acción
# defensiva se lo da a quien la ejecuta. El resto no mueve la posesión.
FIN_ATAQUE = ERRORES
ACCION_DEFENSIVA = DEFENSIVA

TIPO_EVENTO_VALIDOS = LANZAMIENTOS | OFENSIVA | DEFENSIVA | ERRORES | FALTAS | DISCIPLINA
RESULTADOS_VALIDOS = {"GOL", "FALLO", "PARADA", "BLOQUEADO", "POSTE"}
ZONAS_VALIDAS = {"TL", "TC", "TR", "ML", "MC", "MR", "BL", "BC", "BR"}

# Media cancha defensiva, en metros. El arco propio es el origen: y es la
# distancia a la línea de fondo y x la lateral desde el centro del arco,
# positiva hacia la derecha de quien ataca. Una cancha de balonmano mide
# 20 x 40, así que la media es un cuadrado de 20 x 20.
ANCHO_MEDIA_CANCHA = 10.0
LARGO_MEDIA_CANCHA = 20.0
FRANJA_ARCO = 6.0     # borde del área de portería
FRANJA_9M = 9.0       # línea de los 9 metros
# Un tercio del ancho: reparte las columnas en tres tramos iguales de la
# franja defensiva completa, no del arco (que son 3 m y no divide en tres).
TERCIO_ANCHO = ANCHO_MEDIA_CANCHA / 3.0

# El cuadrante de origen usa los MISMOS 9 códigos que la zona de portería, con
# la misma lectura: la fila es la distancia (B pegada al arco, T más allá de
# 9 m) y la columna es la lateral (L/C/R). Reutilizar el vocabulario hace que
# los dos 3x3 se lean como un solo dibujo continuo y que las consultas por
# fila o columna sean las mismas para el origen y para el arco.
ZONAS_ORIGEN_VALIDAS = ZONAS_VALIDAS


def zona_origen_desde_coordenada(x, y):
    """Cuadrante de la media cancha desde el punto del tiro, o None.

    Delega en las franjas reales (6 m y 9 m) en vez de en el ancho de la celda:
    el corte entre franjas tiene que caer donde el jugador vio la línea, no
    donde al Dividió el grid.
    """
    if x < -TERCIO_ANCHO:
        col = 'L'
    elif x > TERCIO_ANCHO:
        col = 'R'
    else:
        col = 'C'

    if y < FRANJA_ARCO:
        fila = 'B'
    elif y < FRANJA_9M:
        fila = 'M'
    else:
        fila = 'T'

    return fila + col


def distancia_desde_coordenada(y, es_7m=False):
    """'6M' / '7M' / '9M' desde la distancia al arco; None más allá de los 9 m.

    Es el mismo criterio que usa el botón de 6 m y el de 9 m de la captura
    normal, para que el GKI y /stats no cambien de significado.

    El penalti es el único caso donde la franja no alcanza: sale siempre a 7 m,
    o sea dentro de la franja de 9, y sin esto la columna guardaría '9M' en un
    tiro que no salió a 9 m. PESOS_GKI ya tiene el peso propio del 7 m (0.85),
    así que con esto la columna y el peso cuentan la misma historia.
    """
    if es_7m:
        return '7M'
    if y < FRANJA_ARCO:
        return '6M'
    if y < FRANJA_9M:
        return '9M'
    return None

def evento_admite_resultado(tipo_evento: str) -> bool:
    return tipo_evento in LANZAMIENTOS

def periodo_desde_segundos(segundo_absoluto) -> int:
    """Regla única de período: floor(seg/1800)+1 (1 y 2 = partido, 3+ = prórroga).
    Misma regla en servidor y cliente; nunca depende de eventos disparados."""
    try:
        seg = int(segundo_absoluto or 0)
    except (ValueError, TypeError):
        seg = 0
    if seg < 0:
        seg = 0
    return seg // 1800 + 1

def tiempo_a_segundos(tiempo_str: str) -> int:
    """Convierte un string 'MM:SS' a segundos totales."""
    try:
        partes = str(tiempo_str).split(':')
        if len(partes) == 2:
            return int(partes[0]) * 60 + int(partes[1])
        return int(tiempo_str)
    except (ValueError, TypeError):
        return 0

def normalizar_evento_legacy(datos: dict) -> dict:
    """
    Convierte tipos de evento antiguos (LANZAMIENTO_6M, CONTRAATAQUE, etc.)
    al nuevo esquema v3: tipo 'LANZAMIENTO' + campos de distancia.
    """
    tipo = datos.get('tipo_evento')
    if tipo == 'LANZAMIENTO_6M':
        datos['tipo_evento'] = 'LANZAMIENTO'
        datos['distancia'] = '6M'
    elif tipo == 'LANZAMIENTO_9M':
        datos['tipo_evento'] = 'LANZAMIENTO'
        datos['distancia'] = '9M'
    elif tipo == 'LANZAMIENTO_7M':
        datos['tipo_evento'] = 'LANZAMIENTO'
        datos['es_7m'] = 1
        datos['coordenada_x'] = None
        datos['coordenada_y'] = None
    elif tipo == 'CONTRAATAQUE':
        datos['tipo_evento'] = 'LANZAMIENTO'
        datos['es_contraataque'] = 1
        datos['coordenada_x'] = None
        datos['coordenada_y'] = None
    
    # segundo_absoluto es tiempo ABSOLUTO acumulado (el cronómetro frontend nunca
    # se reinicia en el entretiempo: '32:01' = segundo 1921). El offset por
    # período solo aplica si el tiempo viniera por-período (legacy).
    if 'segundo_absoluto' not in datos or datos.get('segundo_absoluto') is None:
        if 'tiempo_juego' in datos:
            periodo = int(datos.get('periodo', 1) or 1)
            t_seg = tiempo_a_segundos(datos['tiempo_juego'])
            if periodo > 1 and t_seg < 1800 * (periodo - 1):
                datos['segundo_absoluto'] = t_seg + (1800 * (periodo - 1))
            else:
                datos['segundo_absoluto'] = t_seg
    # El período es autoridad del servidor: deriva del absoluto, nunca del
    # cliente (un cliente con el período clavado en 1 no contamina más).
    try:
        datos['periodo'] = periodo_desde_segundos(datos.get('segundo_absoluto'))
    except (ValueError, TypeError):
        pass

    # La zona de portería y el punto del tiro solo pertenecen a lanzamientos:
    # cualquier otro evento que los arrastre (valor stale del cliente) se
    # normaliza a NULL en vez de rechazar, para no bloquear nunca la captura
    # en vivo.
    if datos.get('tipo_evento') != 'LANZAMIENTO':
        datos['zona_porteria'] = None
        datos['zona_origen'] = None
        datos['coordenada_x'] = None
        datos['coordenada_y'] = None
        return datos

    # El punto del tiro es la fuente de verdad: el cuadrante de origen y la
    # distancia se derivan de ahí. Se guardan igual como columnas para que las
    # consultas por franja y columna sigan siendo un GROUP BY de texto y no
    # una cuenta de flotantes en cada consulta.
    x, y = datos.get('coordenada_x'), datos.get('coordenada_y')
    if x is not None and y is not None:
        try:
            fx, fy = float(x), float(y)
        except (TypeError, ValueError):
            pass    # validar_evento lo rechaza con un mensaje claro
        else:
            datos['zona_origen'] = zona_origen_desde_coordenada(fx, fy)
            datos['distancia'] = distancia_desde_coordenada(fy, _es_verdad(datos.get('es_7m')))

    return datos

def validar_evento(datos: dict) -> tuple[list[str], list[str]]:
    """
    Valida un evento contra las reglas del dominio.
    Retorna una tupla (errores, warnings).
    """
    errores = []
    warnings = []

    if not isinstance(datos, dict):
        return ["El cuerpo de la petición debe ser un objeto JSON"], []

    # Campos obligatorios
    campos_obligatorios = ['id_partido', 'id_jugador', 'tipo_evento', 'tiempo_juego']
    for campo in campos_obligatorios:
        if datos.get(campo) is None or datos.get(campo) == '':
            errores.append(f"El campo '{campo}' es obligatorio.")

    if errores:
        return errores, warnings

    tipo_evento = datos.get('tipo_evento')
    resultado = datos.get('resultado')
    zona = datos.get('zona_porteria')

    # Validar tipo de evento permitidos
    if tipo_evento not in TIPO_EVENTO_VALIDOS:
        errores.append(f"El tipo de evento '{tipo_evento}' no es válido.")

    # Validar resultado según tipo_evento
    if evento_admite_resultado(tipo_evento):
        if not resultado:
            errores.append(f"El evento '{tipo_evento}' requiere un 'resultado'.")
        elif resultado not in RESULTADOS_VALIDOS:
            errores.append(f"El resultado '{resultado}' no es válido.")
    else:
        if resultado is not None and resultado != '':
            errores.append(f"El evento '{tipo_evento}' no admite el campo 'resultado'.")

    # Validar zona de portería
    if zona and zona not in ZONAS_VALIDAS:
        errores.append(f"La zona de portería '{zona}' no es válida.")

    # El cuadrante de origen comparte vocabulario con la zona de portería.
    origen = datos.get('zona_origen')
    if origen and origen not in ZONAS_ORIGEN_VALIDAS:
        errores.append(f"El cuadrante de origen '{origen}' no es válido.")

    # Punto del tiro: dentro de la media cancha y de a pares. Se rechaza en vez
    # de recortar, porque un punto fuera del arco no es un tiro mal apretado:
    # es un evento con otro origen, y recortarlo inventa un lugar.
    cx, cy = datos.get('coordenada_x'), datos.get('coordenada_y')
    if (cx is None) != (cy is None):
        errores.append("'coordenada_x' y 'coordenada_y' van de a pares: o hay punto o no hay.")
    elif cx is not None:
        try:
            fx, fy = float(cx), float(cy)
        except (TypeError, ValueError):
            errores.append("El punto del tiro debe ser numérico.")
        else:
            if not (-ANCHO_MEDIA_CANCHA <= fx <= ANCHO_MEDIA_CANCHA):
                errores.append(
                    f"El tiro está a {fx:g}m del centro del arco, fuera de la media cancha "
                    f"({-ANCHO_MEDIA_CANCHA:g}m a {ANCHO_MEDIA_CANCHA:g}m)."
                )
            if not (0.0 <= fy <= LARGO_MEDIA_CANCHA):
                errores.append(
                    f"El tiro está a {fy:g}m de la línea de fondo, fuera de la media cancha "
                    f"(0 a {LARGO_MEDIA_CANCHA:g}m)."
                )

    return errores, warnings

def verificar_advertencia_7m(datos: dict, eventos_previos: list) -> list[str]:
    """
    Regla 7m (BUG-10 / D4): Si es un LANZAMIENTO_7M y no hay una FALTA/FALTA_TECNICA previa
    en los últimos 60 segundos del partido, retorna warning ['7m_sin_falta'].
    """
    warnings = []
    
    # Compatibilidad con legacy y nuevo modelo
    es_7m = datos.get('tipo_evento') == 'LANZAMIENTO_7M' or str(datos.get('es_7m', '0')) == '1'
    if not es_7m:
        return warnings

    tiempo_actual = datos.get('segundo_absoluto', tiempo_a_segundos(datos.get('tiempo_juego', '00:00')))
    
    # Buscar si hubo una falta en los últimos 60 segundos
    falta_reciente = False
    for prev in eventos_previos:
        tipo_prev = prev.get('tipo_evento')
        if tipo_prev in {'FALTA', 'FALTA_TECNICA'}:
            t_prev = prev.get('segundo_absoluto', tiempo_a_segundos(prev.get('tiempo_juego', '00:00')))
            if 0 <= (tiempo_actual - t_prev) <= 60:
                falta_reciente = True
                break

    if not falta_reciente:
        warnings.append('7m_sin_falta')

    return warnings

def bloque_de_minuto(segundo_absoluto: int) -> int:
    """Bloque de 10 minutos (0-5) para segundo_absoluto; 6 = prórroga (>=60')."""
    try:
        seg = int(segundo_absoluto or 0)
    except (ValueError, TypeError):
        seg = 0
    if seg < 0:
        seg = 0
    return min(seg // 600, 5) if seg < 3600 else 6

ETIQUETAS_BLOQUE = ['0–10', '10–20', '20–30', '30–40', '40–50', '50–60', 'Prórroga']

def _es_7m(ev: dict) -> bool:
    """Tiro de 7 m: legacy LANZAMIENTO_7M o LANZAMIENTO con es_7m."""
    ev = ev or {}
    if ev.get('tipo_evento') == 'LANZAMIENTO_7M':
        return True
    return ev.get('tipo_evento') in LANZAMIENTOS and _es_verdad(ev.get('es_7m'))

ETIQUETAS_7M = ['empatado', 'ajustado', '1T', '2T', 'Prórroga', "últimos 5'"]

def derivar_contexto_7m(eventos: list) -> dict:
    """Eficacia de 7 m por equipo con contexto reconstruido del log (§11 doc).

    Reconstruye el marcador en cada momento (orden cronológico del log) y
    clasifica cada 7 m propio por: partido empatado, diferencia ajustada
    (|dif| ≤ 2), período (1T/2T/Prórroga) y últimos 5' del partido.
    La diferencia es la previa al lanzamiento (contexto en que se tira).
    Devuelve {'A': {'tiros','goles','contextos': {...}}, 'B': {...}} donde
    cada contexto es {'tiros','goles'}. Sin 7 m: todo en cero.
    """
    cuad = {eq: {'tiros': 0, 'goles': 0,
                 'contextos': {c: {'tiros': 0, 'goles': 0} for c in ETIQUETAS_7M}}
            for eq in ('A', 'B')}

    cron = [ev for ev in (eventos or []) if (ev.get('id_equipo') in ('A', 'B'))]
    seg_fin = 0
    for ev in cron:
        seg_fin = max(seg_fin, seg_de_evento(ev))

    goles = {'A': 0, 'B': 0}
    for ev in cron:
        eq = ev['id_equipo']
        tipo = ev.get('tipo_evento')
        res = ev.get('resultado')
        seg = seg_de_evento(ev)
        if _es_7m(ev) and res:
            dif = goles[eq] - goles['B' if eq == 'A' else 'A']
            cuad[eq]['tiros'] += 1
            es_gol = 1 if res == 'GOL' else 0
            cuad[eq]['goles'] += es_gol
            ctx = cuad[eq]['contextos']
            if dif == 0:
                _sumar_7m(ctx['empatado'], es_gol)
            if abs(dif) <= 2:
                _sumar_7m(ctx['ajustado'], es_gol)
            _sumar_7m(ctx['1T' if seg < 1800 else ('2T' if seg < 3600 else 'Prórroga')], es_gol)
            if seg >= seg_fin - 300:
                _sumar_7m(ctx["últimos 5'"], es_gol)
        if tipo in LANZAMIENTOS and res == 'GOL':
            goles[eq] += 1
    return cuad

def _sumar_7m(dest: dict, es_gol: int):
    dest['tiros'] += 1
    dest['goles'] += es_gol

def seg_de_evento(ev: dict) -> int:
    """Segundo absoluto de un evento (columna o derivado de tiempo_juego)."""
    seg = (ev or {}).get('segundo_absoluto')
    if seg is None:
        seg = tiempo_a_segundos((ev or {}).get('tiempo_juego', '00:00'))
    try:
        seg = int(seg)
    except (ValueError, TypeError):
        seg = 0
    return max(0, seg)

def _es_verdad(valor) -> bool:
    """Truthiness tolerante a 0/1 como int o str (viene de SQLite/JSON)."""
    if valor is None or valor is False:
        return False
    return str(valor) not in ('0', '', 'False', 'false')

MAPA_SUBTIPO_LEGACY = {
    'LANZAMIENTO_6M': '6M',
    'LANZAMIENTO_9M': '9M',
    'LANZAMIENTO_7M': '7M',
    'CONTRAATAQUE': 'CONTRAATAQUE',
    'LANZAMIENTO': 'OTRO',
}

def subtipo_lanzamiento(ev: dict) -> str:
    """Clasifica un tiro en 6M/9M/7M/CONTRAATAQUE/OTRO (normaliza legacy).
    Misma clave para paradas_por_tipo (GKI) y lanzamientos_por_tipo (/stats)."""
    tipo = (ev or {}).get('tipo_evento')
    if tipo == 'LANZAMIENTO':
        if _es_verdad(ev.get('es_contraataque')):
            return 'CONTRAATAQUE'
        if _es_verdad(ev.get('es_7m')):
            return '7M'
        if ev.get('distancia') in ('6M', '9M'):
            return ev['distancia']
        return 'OTRO'
    return MAPA_SUBTIPO_LEGACY.get(tipo, 'OTRO')

def _nuevo_conteo():
    return {'ataques': 0, 'goles': 0, 'tiros': 0, 'perdidas': 0, 'paradas': 0}

def derivar_posesiones(eventos: list) -> dict:
    """
    Replay completo del log: deriva la posesión actual, los ataques por equipo
    y los parciales por bloque de 10 minutos.

    Definiciones (base científica v1):
    - Posesión: equipo que tiene el balón. Arranca en 'A'; solo la mueven los
      tiros con resultado, los errores y las acciones defensivas.
    - Ataque: tramo de un equipo entre que recibe la posesión y la pierde.
      Termina en tiro con resultado, error propio o acción defensiva rival.
      Se cuenta al abrirse (reproduciendo el log, sin clics extra).

    Cada evento: {'id_equipo': 'A'/'B', 'tipo_evento', 'resultado',
    'segundo_absoluto' (puede faltar: se deriva de 'tiempo_juego')}.
    Devuelve {'posesion_actual', 'ataques': {'A','B'}, 'bloques': [...],
    'ventanas': [...]}.
    Cada bloque/ventana: {'etiqueta', 'A': {ataques,goles,tiros,perdidas,paradas},
    'B': {...}}. Los ataques se cuentan por CIERRE (mismo criterio en bloques
    y ventanas, reproducible). Las paradas se atribuyen al equipo DEFENSOR:
    tiro con PARADA suma al rival del lanzador; PARADA_PORTERO suma a quien
    la ejecuta. Ventanas: 1T (0–30'), 2T (30–60'), Prórroga (60'+),
    Últimos 10' y Últimos 5' (relativos al último evento del log).
    """
    posesion = None
    ataques = {'A': 0, 'B': 0}
    abierta = {'A': False, 'B': False}
    ultimo_seg = {'A': 0, 'B': 0}
    movimientos = []  # (categoria, equipo, seg): goles/tiros/perdidas/paradas
    cierres = []      # (equipo, seg_cierre)

    def seg_de(ev):
        return seg_de_evento(ev)

    def rival(eq):
        return 'B' if eq == 'A' else 'A'

    def abrir(eq, seg):
        if not abierta[eq]:
            abierta[eq] = True
            ataques[eq] += 1
        ultimo_seg[eq] = seg

    def cerrar(eq, seg):
        if abierta[eq]:
            abierta[eq] = False
            cierres.append((eq, seg))
        ultimo_seg[eq] = seg

    for ev in eventos or []:
        eq = ev.get('id_equipo')
        if eq not in ('A', 'B'):
            continue
        tipo = ev.get('tipo_evento')
        res = ev.get('resultado')
        seg = seg_de(ev)

        es_tiro = tipo in LANZAMIENTOS and res
        if es_tiro or tipo in FIN_ATAQUE:
            # El balón queda en la defensa: cierra el ataque propio y abre el rival
            if posesion is None:
                posesion = eq
                abrir(eq, seg)
            cerrar(eq, seg)
            posesion = rival(eq)
            abrir(posesion, seg)
            movimientos.append(('tiros' if es_tiro else 'perdidas', eq, seg))
            if es_tiro and res == 'GOL':
                movimientos.append(('goles', eq, seg))
            elif es_tiro and res == 'PARADA':
                movimientos.append(('paradas', rival(eq), seg))
        elif tipo in ACCION_DEFENSIVA:
            # Robo/bloqueo/parada propia: el balón es mío
            if posesion is None:
                posesion = eq
            if posesion != eq:
                cerrar(posesion, seg)
            posesion = eq
            abrir(eq, seg)
            if tipo == 'PARADA_PORTERO':
                movimientos.append(('paradas', eq, seg))
        else:
            # Asistencias, sanciones, faltas: continúan el ataque abierto
            if posesion is None:
                posesion = eq
                abrir(eq, seg)
            elif posesion == eq and abierta[eq]:
                ultimo_seg[eq] = seg

    # Ataques que quedaron abiertos al final: se cierran en la última
    # intervención de cada equipo (misma semántica que antes del refactor)
    seg_fin = 0
    for ev in eventos or []:
        if (ev.get('id_equipo') in ('A', 'B')):
            seg_fin = max(seg_fin, seg_de(ev))
    for eq in ('A', 'B'):
        if abierta[eq]:
            abierta[eq] = False
            cierres.append((eq, ultimo_seg[eq]))

    def agregar(dest, categoria, eq, seg, pred):
        if pred(seg):
            dest[eq][categoria] += 1

    def resumir(pred):
        cuad = {'A': _nuevo_conteo(), 'B': _nuevo_conteo()}
        for categoria, eq, seg in movimientos:
            agregar(cuad, categoria, eq, seg, pred)
        for eq, seg in cierres:
            agregar(cuad, 'ataques', eq, seg, pred)
        return cuad

    bloques = [{'etiqueta': ETIQUETAS_BLOQUE[b],
                **resumir(lambda s, b=b: bloque_de_minuto(s) == b)}
               for b in range(7)]
    bloques = [b for b in bloques
               if any(b[eq][k] for eq in ('A', 'B')
                      for k in ('ataques', 'goles', 'tiros', 'perdidas', 'paradas'))]

    ventanas = [
        {'etiqueta': '1T', **resumir(lambda s: s < 1800)},
        {'etiqueta': '2T', **resumir(lambda s: 1800 <= s < 3600)},
        {'etiqueta': 'Prórroga', **resumir(lambda s: s >= 3600)},
        {'etiqueta': "Últimos 10'", **resumir(lambda s: s >= seg_fin - 600)},
        {'etiqueta': "Últimos 5'", **resumir(lambda s: s >= seg_fin - 300)},
    ]

    return {
        'posesion_actual': posesion or 'A',
        'ataques': ataques,
        'bloques': bloques,
        'ventanas': ventanas,
    }

def recalcular_disciplina(conn, id_partido: int, id_jugador: int, client_event_id: str = None):
    """
    Recalcula la descalificación automática por tercera exclusión.
    Si tiene >= 3 exclusiones activas y no tiene descalificación automática, la crea.
    Si tiene < 3 exclusiones activas y tiene descalificación automática activa, la anula.
    """
    jugador = conn.execute("SELECT numero_camiseta, es_generico FROM Jugadores WHERE id_jugador = ?", (id_jugador,)).fetchone()
    if jugador and jugador['es_generico'] == 1 and jugador['numero_camiseta'] == 0:
        return  # "Rival (sin dorsal)" no se descalifica nunca.
    row = conn.execute(
        "SELECT COUNT(*) AS c FROM Eventos_Juego "
        "WHERE id_partido = ? AND id_jugador = ? AND tipo_evento = 'EXCLUSION_2MIN' AND anulado = 0",
        (id_partido, id_jugador)
    ).fetchone()
    exclusiones = row['c'] if row else 0

    # Buscar descalificación automática (generado_por no es nulo)
    desc_auto = conn.execute(
        "SELECT id_evento, anulado FROM Eventos_Juego "
        "WHERE id_partido = ? AND id_jugador = ? AND tipo_evento = 'DESCALIFICACION' AND generado_por IS NOT NULL",
        (id_partido, id_jugador)
    ).fetchone()

    if exclusiones >= 3:
        if not desc_auto or desc_auto['anulado'] == 1:
            # Crear o restaurar
            if desc_auto and desc_auto['anulado'] == 1:
                conn.execute("UPDATE Eventos_Juego SET anulado = 0, anulado_en = NULL WHERE id_evento = ?", (desc_auto['id_evento'],))
            else:
                # client_event_id determinista por jugador+partido: idempotente sin colisionar entre jugadores
                desc_client_id = f"{client_event_id}:auto-descalificacion" if client_event_id else f"auto-descalificacion:{id_partido}:{id_jugador}"
                conn.execute('''
                    INSERT INTO Eventos_Juego 
                    (id_partido, id_jugador, tipo_evento, tiempo_juego, periodo, segundo_absoluto, lado, client_event_id, generado_por, anulado) 
                    VALUES (?, ?, 'DESCALIFICACION', '00:00', 1, 0, 'ATAQUE', ?, ?, 0)
                    ON CONFLICT(client_event_id) DO UPDATE SET anulado = 0
                ''', (id_partido, id_jugador, desc_client_id, client_event_id or 'batch'))
                
    else:
        if desc_auto and desc_auto['anulado'] == 0:
            # Anular
            conn.execute("UPDATE Eventos_Juego SET anulado = 1, anulado_en = CURRENT_TIMESTAMP WHERE id_evento = ?", (desc_auto['id_evento'],))

