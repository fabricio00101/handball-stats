"""
Módulo de cálculo de métricas puras de balonmano.
Todas las funciones son puras (sin I/O ni dependencias de BD/Flask).
Garantizan ausencia de ZeroDivisionError y devuelven 0.0 cuando no hay lanzamientos/tiros.
"""

LANZAMIENTOS = {"LANZAMIENTO_6M", "LANZAMIENTO_9M", "LANZAMIENTO_7M", "CONTRAATAQUE"}
RESULTADOS_LANZAMIENTO = {"GOL", "FALLO", "PARADA", "BLOQUEADO", "POSTE"}

PESOS_GKI = {
    "LANZAMIENTO_6M": 1.0,   # Máxima dificultad / valor para el portero
    "LANZAMIENTO_7M": 0.85,
    "CONTRAATAQUE": 0.90,
    "LANZAMIENTO_9M": 0.60,  # Menor dificultad comparativa
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

def perdidas_por_posesion(perdidas: int, posesiones: int) -> float:
    """Calcula las pérdidas ponderadas por cada 3 posesiones estimadas."""
    if not posesiones or posesiones <= 0:
        return 0.0
    return round((perdidas / posesiones) * 3, 2)

def mas_menos(goles_favor: int, goles_contra: int) -> int:
    """Diferencia de goles (favor - contra)."""
    return goles_favor - goles_contra
