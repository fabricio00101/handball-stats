# Handball Stats Real-Time Engine (Inspired by Handball.ai)

## 1. Objetivo del Proyecto

Desarrollar un motor de recolección de estadísticas de balonmano en tiempo real que permita registrar eventos con máxima velocidad (<3 clics por acción) y generar métricas avanzadas (Big Data) comparables a los estándares de la EHF/ASOBAL.

## 2. Modelo de Datos de Eventos (Core)

Cada evento debe capturar: `timestamp`, `periodo`, `jugador_id`, `equipo_id`, `coordenada_x`, `coordenada_y` y `tipo_evento`.

### Tipos de Eventos Obligatorios:

- **Lanzamientos:** Gol, Parada, Fuera, Poste, Bloqueado.
- **Zonas de Lanzamiento:** 6m, 7m, 9m, Extremo Izquierdo/Derecho, Contraataque.
- **Acciones Defensivas:** Bloqueo, Robo (Steal), Falta Técnica provocada.
- **Errores:** Pérdida de balón (Turnover), Falta técnica, Dobles, Pasos.
- **Sanciones:** Tarjeta Amarilla, 2 Minutos, Tarjeta Roja, Tarjeta Azul.
- **Portería:** Parada de 6m, 7m, 9m, Extremo y Contraataque.

## 3. Motor de Cálculo de Métricas Avanzadas

El agente de IA debe implementar las siguientes fórmulas de procesamiento en tiempo real:

| Métrica                    | Fórmula / Lógica                                                                 |
| :------------------------- | :------------------------------------------------------------------------------- |
| **Eficiencia de Tiro**     | (Goles / Lanzamientos Totales) \* 100                                            |
| **Efectividad Portero**    | (Paradas / Tiros a Puerta Recibidos) \* 100                                      |
| **Plus/Minus (+/-)**       | Diferencia de goles del equipo mientras el jugador está en pista.                |
| **Pérdidas por Posesión**  | Total de pérdidas / (Total posesiones estimadas).                                |
| **GKI (Goalkeeper Index)** | Ponderación de paradas según zona (ej: una parada de 6m vale más que una de 9m). |

## 4. Lógica de Negocio Específica (Handball-Specific)

1. **Gestión de Exclusiones:** Cronómetro automático de 120 segundos vinculado al jugador al registrar un "2 Minutos".
2. **Estado de Posesión:** Cambio automático de equipo poseedor tras gol, pérdida o robo.
3. **Asistencias:** Solo se registra asistencia si el pase previo al gol genera una ventaja clara (estándar Handball.ai).
4. **Mapa de Calor:** Registro de coordenadas (x,y) para origen del tiro y destino en la portería (cuadrícula 3x3).

## 5. Requisitos de Interfaz para el Agente (UX Flow)

Para replicar la eficiencia de Handball.ai, la implementación debe seguir este flujo:

1. Selección de Jugador (o número de dorsal).
2. Selección de Acción (Botón principal).
3. Selección de Zona/Resultado (Si aplica).
   _Nota: El sistema debe inferir el equipo contrario y el estado del partido por el contexto del evento previo._

## 6. Instrucciones de Implementación para la IA

- **Validación:** No permitir registrar un gol de 7m si no se ha marcado previamente una falta personal/penalti.
- **Exportación:** Generar estructura JSON compatible para reportes PDF de fin de partido.
- **Sincronización:** Priorizar la persistencia local (Local Storage/IndexedDB) para evitar pérdida de datos por mala conexión en pabellones.

---

## 7. Cómo Ejecutar

1. Requisitos: Python 3.10+
2. Crear y activar entorno virtual:
   - Windows: `python -m venv venv` y `.\venv\Scripts\activate`
   - Linux/macOS: `python3 -m venv venv` y `source venv/bin/activate`
3. Instalar dependencias: `pip install -r requirements.txt`
4. Inicializar Base de Datos: `python init_db.py`
5. Ejecutar la aplicación: `flask run` (o `python app.py`)

---

## 8. Estructura del Proyecto

```
app-balonmano/
├── .env.example
├── .gitignore
├── app.py                      # Servidor Flask principal
├── database.db                 # Base de datos SQLite (ignorado en git)
├── init_db.py                  # Script de creación e inicialización de BD
├── PLAN_IMPLEMENTACION.md      # Plan maestro de implementación
├── pytest.ini                  # Configuración de Pytest
├── readme.md                   # Especificación y documentación del proyecto
├── requirements.txt            # Dependencias de producción
├── requirements-dev.txt        # Dependencias de desarrollo y tests
├── schema.sql                  # Esquema de tablas SQLite
├── static/
│   ├── css/styles.css          # Estilos Vanilla CSS (Tema Oscuro)
│   └── js/
│       ├── app.js              # Captura de eventos, sincronización offline
│       └── timer.js            # Cronómetro de partido
└── templates/
    └── index.html              # Interfaz de captura de partidos
```

---

## 9. Vocabulario de Eventos (Contrato Frontend <-> Backend)

### `tipo_evento`
- **Lanzamientos:** `LANZAMIENTO_6M`, `LANZAMIENTO_9M`, `LANZAMIENTO_7M`, `CONTRAATAQUE` (requieren `resultado`)
- **Ofensiva:** `ASISTENCIA`
- **Defensiva:** `ROBO_BALON`, `BLOQUEO`, `PARADA_PORTERO`
- **Error:** `PERDIDA_BALON`, `FALTA_TECNICA`, `DOBLE`, `PASOS`
- **Falta:** `FALTA`, `FALTA_TECNICA`
- **Disciplina:** `AMARILLA`, `EXCLUSION_2MIN`, `DESCALIFICACION`

### `resultado` (Solo para Lanzamientos)
- `GOL`, `FALLO`, `PARADA`, `BLOQUEADO`, `POSTE`

### `zona_porteria`
- Cuadrícula 3x3: `TL`, `TC`, `TR`, `ML`, `MC`, `MR`, `BL`, `BC`, `BR`

---

## 10. Tests y Verificación

Instalar dependencias de desarrollo y ejecutar la suite de pruebas:

```bash
pip install -r requirements-dev.txt
python -m pytest
```

---

## 11. Limitaciones Conocidas

1. **`id_equipo` encasillado a `'A'` / `'B'`:** El modelo actual abstrae equipos como Local ('A') y Visitante ('B'). El modelo relacional `Equipos` + `Partido_Equipos` se implementará en una fase futura.
2. **`+/-` (Plus/Minus) como Proxy por Posesión:** Al no contar con tracking de alineación completa en pista (lineup de 7 jugadores), la métrica `+/-` refleja los goles a favor − en contra de su equipo durante las posesiones activas del jugador.

