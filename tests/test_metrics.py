"""
Pruebas unitarias para las fórmulas de métricas puras de balonmano.
"""
import pytest
from services.metrics import (
    eficiencia_tiro,
    efectividad_portero,
    gki,
    perdidas_por_posesion,
    mas_menos,
    PESOS_GKI
)

def test_eficiencia_tiro_normal():
    assert eficiencia_tiro(3, 6) == 50.0

def test_eficiencia_tiro_sin_lanzamientos():
    assert eficiencia_tiro(0, 0) == 0.0
    assert eficiencia_tiro(5, 0) == 0.0

def test_efectividad_portero_normal():
    assert efectividad_portero(2, 4) == 50.0

def test_efectividad_portero_sin_tiros():
    assert efectividad_portero(0, 0) == 0.0

def test_gki_pondera_por_zona():
    paradas_6m = {"LANZAMIENTO_6M": 3}
    paradas_9m = {"LANZAMIENTO_9M": 3}
    
    assert gki(paradas_6m) > gki(paradas_9m)
    assert gki(paradas_6m) == 3.0  # 3 * 1.0
    assert gki(paradas_9m) == 1.8  # 3 * 0.60

def test_gki_ignora_tipo_desconocido():
    paradas_unknown = {"DESCONOCIDO": 2}
    assert gki(paradas_unknown) == 1.0  # 2 * 0.5 por defecto

def test_gki_vacio():
    assert gki({}) == 0.0

def test_perdidas_por_posesion():
    assert perdidas_por_posesion(6, 30) == 0.6
    assert perdidas_por_posesion(0, 0) == 0.0

def test_mas_menos():
    assert mas_menos(25, 20) == 5
    assert mas_menos(18, 22) == -4
