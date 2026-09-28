"""
Módulo de validación de eventos de dominio y reglas de juego de balonmano.
"""

LANZAMIENTOS = {"LANZAMIENTO_6M", "LANZAMIENTO_9M", "LANZAMIENTO_7M", "CONTRAATAQUE"}
OFENSIVA = {"ASISTENCIA"}
DEFENSIVA = {"ROBO_BALON", "BLOQUEO", "PARADA_PORTERO"}
ERRORES = {"PERDIDA_BALON", "FALTA_TECNICA", "DOBLE", "PASOS"}
FALTAS = {"FALTA"}
DISCIPLINA = {"AMARILLA", "EXCLUSION_2MIN", "DESCALIFICACION"}

TIPO_EVENTO_VALIDOS = LANZAMIENTOS | OFENSIVA | DEFENSIVA | ERRORES | FALTAS | DISCIPLINA
RESULTADOS_VALIDOS = {"GOL", "FALLO", "PARADA", "BLOQUEADO", "POSTE"}
ZONAS_VALIDAS = {"TL", "TC", "TR", "ML", "MC", "MR", "BL", "BC", "BR"}

def evento_admite_resultado(tipo_evento: str) -> bool:
    return tipo_evento in LANZAMIENTOS

def tiempo_a_segundos(tiempo_str: str) -> int:
    """Convierte un string 'MM:SS' a segundos totales."""
    try:
        partes = str(tiempo_str).split(':')
        if len(partes) == 2:
            return int(partes[0]) * 60 + int(partes[1])
        return int(tiempo_str)
    except (ValueError, TypeError):
        return 0

def validar_evento(datos: dict) -> tuple[list[str], list[str]]:
    """
    Valida un evento contra las reglas del dominio.
    Retorna una tupla (errores, warnings).
    Si errores no está vacío, el evento no debe ser guardado (HTTP 400).
    Si warnings tiene elementos pero errores está vacío, el evento se guarda (HTTP 201).
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

    return errores, warnings

def verificar_advertencia_7m(datos: dict, eventos_previos: list) -> list[str]:
    """
    Regla 7m (BUG-10 / D4): Si es un LANZAMIENTO_7M y no hay una FALTA/FALTA_TECNICA previa
    en los últimos 60 segundos del partido, retorna warning ['7m_sin_falta'].
    Nunca bloquea el evento.
    """
    warnings = []
    if datos.get('tipo_evento') != 'LANZAMIENTO_7M':
        return warnings

    tiempo_actual = tiempo_a_segundos(datos.get('tiempo_juego', '00:00'))
    
    # Buscar si hubo una falta en los últimos 60 segundos
    falta_reciente = False
    for prev in eventos_previos:
        tipo_prev = prev.get('tipo_evento')
        if tipo_prev in {'FALTA', 'FALTA_TECNICA'}:
            t_prev = tiempo_a_segundos(prev.get('tiempo_juego', '00:00'))
            if 0 <= (tiempo_actual - t_prev) <= 60:
                falta_reciente = True
                break

    if not falta_reciente:
        warnings.append('7m_sin_falta')

    return warnings
