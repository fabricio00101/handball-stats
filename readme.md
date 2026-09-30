# Handball Stats Real-Time Engine (Inspired by Handball.ai)

## 1. Objetivo del Proyecto

Desarrollar un motor de recolección de estadísticas de balonmano en tiempo real que permita registrar eventos con máxima velocidad (<3 clics por acción) y generar métricas avanzadas (Big Data) comparables a los estándares de la EHF/ASOBAL.

## 2. Modelo de Datos de Eventos (Core)

Cada evento debe capturar: `timestamp`, `periodo`, `jugador_id`, `equipo_id`, `coordenada_x`, `coordenada_y` y `tipo_evento`.

### Tipos de Eventos Obligatorios:

- **Lanzamientos:** Gol, Parada, Fallo, Bloqueado. (Poste solo existe en datos viejos: se comporta como Fallo.)
- **Zonas de Lanzamiento:** 6m, 7m, 9m, Contraataque.
- **Acciones Defensivas:** Bloqueo, Robo (Steal).
- **Errores:** Pérdida de balón (Turnover), Falta técnica, Dobles, Pasos.
- **Sanciones:** Tarjeta Amarilla, 2 Minutos, Tarjeta Roja.
- **Portería:** destino del tiro en cuadrícula 3x3 (obligatoria en Gol/Parada).

## 3. Motor de Cálculo de Métricas Avanzadas

El agente de IA debe implementar las siguientes fórmulas de procesamiento en tiempo real:

| Métrica                    | Fórmula / Lógica                                                                 |
| :------------------------- | :------------------------------------------------------------------------------- |
| **Eficiencia de Tiro**     | (Goles / Lanzamientos Totales) \* 100                                            |
| **Efectividad Portero**    | (Paradas / Tiros a Puerta Recibidos) \* 100                                      |
| **Ataques**                | Tramos de un equipo entre que recibe y pierde la posesión (replay del log)       |
| **Eficacia de Ataque**     | (Goles / Ataques) \* 100                                                         |
| **Tiros por Ataque**       | (Tiros / Ataques) \* 100                                                         |
| **Pérdidas por Ataque**    | (Pérdidas / Ataques) \* 100                                                      |
| **Tasa de fallados**       | (Fallos+bloqueados / Tiros) * 100                                               |
| **Tasa de detenidos**      | (Paradas del rival / Tiros) * 100                                               |
| **Tiros por tipo**         | Tiros/goles/eficacia en 6M, 9M, 7M, Contraataque (+ posicional vs contraataque) |
| **7 m contextual**         | Eficacia 7M global + por contexto: empatado, diferencia ≤2, 1T/2T, últimos 5'  |
| **Ventanas**               | 1T, 2T, prórroga, últimos 10' y últimos 5' (mismo replay, ataques por cierre)   |
| **Paradas por bloque**     | Paradas del equipo defensor en cada bloque de 10 minutos                        |
| **Parciales**              | Goles, tiros, ataques y pérdidas por bloque de 10 minutos (y prórroga)           |
| **GKI (Goalkeeper Index)** | Índice propio: pondera paradas por dificultad (6M ×1.0, Contra ×0.9, 7M ×0.85, 9M ×0.6). Se calcula pero no se muestra en la interfaz. |
| **Plus/Minus (+/-)**       | No se expone: requeriría seguimiento de alineación (quién está en cancha).       |

## 4. Lógica de Negocio Específica (Handball-Specific)

1. **Gestión de Exclusiones:** Cronómetro automático de 120 segundos vinculado al jugador al registrar un "2 Minutos".
2. **Estado de Posesión:** Cambio automático de equipo poseedor tras gol, pérdida o robo.
3. **Asistencias:** Solo se registra asistencia si el pase previo al gol genera una ventaja clara (estándar Handball.ai).
4. **Mapa de Calor:** Destino del tiro en la portería (cuadrícula 3x3). El origen en cancha no se registra.

## 4b. Definiciones formales (base científica v1)

- **Posesión:** equipo que tiene el balón. Arranca en el equipo propio ('A'). Solo la mueven: tiros con resultado, errores (pérdida, falta técnica, dobles, pasos) y acciones defensivas (robo, bloqueo, parada propia). Asistencias, faltas y sanciones no la mueven. Se deriva por replay completo del log (`derivar_posesiones` en `services/eventos.py`), nunca mirando solo el último evento.
- **Ataque:** tramo de un equipo entre que recibe la posesión y la pierde. Termina en tiro con resultado, error propio o acción defensiva rival. Se cuenta al abrirse, reproduciendo el log: cero clics extra en la captura.
- **Asistencia:** último pase que precede directamente al gol, a criterio del operador. Documentar el criterio reduce diferencias entre operadores.
- **Pérdida:** cualquier acción que entrega el balón al rival sin tiro: `PERDIDA_BALON`, `FALTA_TECNICA`, `DOBLE`, `PASOS`. Se cuentan juntas y por separado por tipo en el export crudo.
- **Parada:** tiro con `resultado = PARADA`, atribuido al portero del equipo defensor (`id_portero` explícito). Única forma de registrar paradas en la interfaz.

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
- `GOL`, `FALLO`, `PARADA`, `BLOQUEADO` (`POSTE` solo en datos viejos: equivale a `FALLO`)

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

1. **`id_equipo` encasillado a `'A'` / `'B'`:** El modelo actual abstrae equipos como propio ('A') y rival ('B'). El rival no tiene plantel nominal: se registra como jugador genérico.
2. **`+/-` no se expone:** requeriría tracking de alineación completa en pista (quién entra/sale y cuándo).

