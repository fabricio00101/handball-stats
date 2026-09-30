"""
Módulo de cálculo de métricas puras de balonmano.
Todas las funciones son puras (sin I/O ni dependencias de BD/Flask).
Garantizan ausencia de ZeroDivisionError y devuelven 0.0 cuando no hay lanzamientos/tiros.
"""

LANZAMIENTOS = {"LANZAMIENTO", "LANZAMIENTO_6M", "LANZAMIENTO_9M", "LANZAMIENTO_7M", "CONTRAATAQUE"}
RESULTADOS_LANZAMIENTO = {"GOL", "FALLO", "PARADA", "BLOQUEADO", "POSTE"}

PESOS_GKI = {
    "6M": 1.0,   # Máxima dificultad / valor para el portero
    "7M": 0.85,
    "CONTRAATAQUE": 0.90,
    "9M": 0.60,  # Menor dificultad comparativa
    # Legacy fallbacks just in case
    "LANZAMIENTO_6M": 1.0,   
    "LANZAMIENTO_7M": 0.85,
    "LANZAMIENTO_9M": 0.60,
}

def eficiencia_tiro(goles: int, lanzamientos: int) -> float:
    """(goles / lanzamientos) * 100. Devuelve 0.0 si no hay lanzamientos."""
    if not lanzamientos or lanzamientos <= 0:
        return 0.0
    return round((goles / lanzamientos) * 100, 1)

def efectividad_portero(paradas: int, tiros_recibidos: int) -> float:
    """(paradas / tiros a puerta recibidos) * 100. Devuelve 0.0 si no hay tiros."""
    if not tiros_recibidos or tiros_recibidos <= 0:
        return 0.0
    return round((paradas / tiros_recibidos) * 100, 1)

def gki(paradas_por_tipo: dict) -> float:
    """Pondera cada parada según la dificultad de la zona del tiro que paró.
    paradas_por_tipo: {"LANZAMIENTO_6M": 3, "LANZAMIENTO_9M": 5, ...}
    """
    if not paradas_por_tipo:
        return 0.0
    total = sum(PESOS_GKI.get(tipo, 0.5) * count for tipo, count in paradas_por_tipo.items())
    return round(total, 2)

def eficacia_ataque(goles: int, ataques: int) -> float:
    """(goles / ataques) * 100. Devuelve 0.0 si no hay ataques."""
    if not ataques or ataques <= 0:
        return 0.0
    return round((goles / ataques) * 100, 1)

def frecuencia_tiro(tiros: int, ataques: int) -> float:
    """(tiros / ataques) * 100: % de ataques que terminan en tiro."""
    if not ataques or ataques <= 0:
        return 0.0
    return round((tiros / ataques) * 100, 1)

def perdidas_por_ataque(perdidas: int, ataques: int) -> float:
    """(pérdidas / ataques) * 100: % de ataques que terminan en pérdida."""
    if not ataques or ataques <= 0:
        return 0.0
    return round((perdidas / ataques) * 100, 1)

def tasa_fallados(fallos: int, tiros: int) -> float:
    """(tiros fallados [fuera+bloqueado+poste] / tiros) * 100. 0.0 si no hay tiros."""
    if not tiros or tiros <= 0:
        return 0.0
    return round((fallos / tiros) * 100, 1)

def tasa_detenidos(paradas_rival: int, tiros: int) -> float:
    """(tiros detenidos por el portero rival / tiros) * 100. 0.0 si no hay tiros."""
    if not tiros or tiros <= 0:
        return 0.0
    return round((paradas_rival / tiros) * 100, 1)

def perdidas_por_posesion(perdidas: int, posesiones: int) -> float:
    """Calcula las pérdidas ponderadas por cada 3 posesiones estimadas."""
    if not posesiones or posesiones <= 0:
        return 0.0
    return round((perdidas / posesiones) * 3, 2)

def mas_menos(goles_favor: int, goles_contra: int) -> int:
    """Diferencia de goles (favor - contra)."""
    return goles_favor - goles_contra
