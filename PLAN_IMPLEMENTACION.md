# Plan de Implementación — Motor de Estadísticas de Balonmano

> **Documento para agentes de IA (o desarrolladores) que TOMEN la implementación de este plan.**
> Todo lo que sigue es ejecutable tal cual, en orden, sin ambigüedades.
> El proyecto se encuentra en la raíz de este repositorio.

---

## 0. Contexto obligatorio para quien implemente

### 0.1 Qué es el proyecto

Aplicación web de **anotación y análisis de estadísticas de balonmano en tiempo real**, inspirada
en Handball.ai. El objetivo de producto es registrar eventos con **menos de 3 clics por acción**
durante un partido en vivo y generar métricas avanzadas comparables con estándares EHF/ASOBAL.

### 0.2 Stack (NO cambiar)

- **Backend:** Python + Flask + SQLite (vía módulo `sqlite3` de la stdlib)
- **Frontend:** HTML + CSS + JavaScript **vanilla**. Sin frameworks, sin build step.
- **Restricción de red:** la app se usa en pabellones con mala señal → **todo el diseño es
  offline-first**. No introducir dependencias que requieran CDN en tiempo de ejecución.
- **No introducir frameworks de JS ni nuevas dependencias Python fuera de lo indicado en Fase 0.**

### 0.3 Arquitectura actual (arquitectura por eventos)

```
Navegador (offline-first)
  ├─ state { jugador, posesión, coords }  ──▶  cola localStorage
  ├─ timer.js (cronómetro)                     │
  └─ app.js (captura + tracker + sync) ──fetch──┘
                    ▲                          │ al hacer 'online' / al guardar
                    │                          ▼
              Flask (app.py)  ◀── SQLite (database.db)
                ├─ GET  /                        (render index)
                ├─ POST /api/event               (INSERT Eventos_Juego)
                ├─ GET  /api/matches/:id/export  (SELECT eventos)
                └─ GET  /api/stats/:id           (agrega métricas)
```

**Decisión arquitectónica central y correcta:** se registra un **log de eventos discretos**, no
contadores agregados. Cualquier métrica se deriva del log. **Esta decisión se preserva intacta
en todas las fases.** En particular, las Fases 1–2 profundizan este modelo (el estado del partido se
*deriva* de los eventos en vez de guardarse aparte) en lugar de contradecirlo.

### 0.4 Estructura de ficheros actual

```
app-balonmano/
├── venv/                                      # ignorado por git
├── .gitignore                                 # excluye venv, __pycache__, *.db
├── app.py                                     # Servidor Flask (107 líneas)
├── init_db.py                                 # Crea la BD + datos dummy (45 líneas)
├── extract.py                                 # ⚠️ RESIDUO: vuelca un .docx a requirements.txt
├── schema.sql                                 # 3 tablas (34 líneas)
├── database.db                                # SQLite (ignorado por git)
├── readme.md                                  # Objetivo y requisitos del motor
├── "Desarrollo App Balonmano_ Hoja Ruta.docx" # Doc de arquitectura original
├── requirements.txt                           # 🔴 CORRUPTO: contiene texto de arquitectura
├── templates/
│   └── index.html                             # Interfaz única (157 líneas)
└── static/
    ├── css/styles.css                         # Tema oscuro (474 líneas)
    └── js/
        ├── timer.js                           # Cronómetro IIFE (50 líneas)
        └── app.js                             # Captura + offline (314 líneas)
```

### 0.5 Contrato de datos actual (frontend ↔ backend)

`POST /api/event` recibe y `app.py` inserta en `Eventos_Juego`:
`id_partido`, `id_jugador`, `tipo_evento`, `resultado`, `tiempo_juego`, `periodo`,
`coordenada_x`, `coordenada_y`, `zona_porteria`.

**Cualquier cambio de vocabulario DEBE cambiar frontend y backend en la misma fase.**

---

## 1. Diagnóstico: los bugs concretos que hay que arreglar

Estos son los hallazgos verificados leyendo el código. Cada referencia `archivo:línea` es exacta.

### BUG-1 · Las métricas de portero son siempre 0 (CRÍTICO)

- `app.py:87` cuenta `SUM(CASE WHEN e.resultado = 'PARADA' THEN 1 ELSE 0 END) AS tiros_detenidos_portero`
- `index.html:74` define el botón de portero como `data-event-type="PARADA"` con
  `data-requires-outcome="false"` → el frontend envía `tipo_evento='PARADA'`, `resultado=None`
- **Resultado: la condición nunca se cumple.** `tiros_detenidos_portero` = 0 siempre.
- Consecuencia en cascada: `app.py:100` `data['gki'] = data['tiros_detenidos_portero'] * 2`
  → **GKI siempre 0** para todos los porteros.
- El mismo concepto (`PARADA`) existe como `tipo_evento` **y** como `resultado`
  (`index.html:122`, `data-outcome="PARADA"`). Ambigüedad que rompe el conteo.

### BUG-2 · La posesión se invierte tras una parada (ALTO)

`app.js:147-152`:
```js
if (eventData.resultado === 'GOL' || eventData.tipo_evento === 'PERDIDA_BALON' || eventData.resultado === 'PARADA') {
    updatePossession(otherTeam);          // ❌
} else if (eventData.tipo_evento === 'PARADA' || eventData.tipo_evento === 'ROBO_BALON') {
    updatePossession(currentTeam);
}
```
- Cuando el portero (equipo `currentTeam`) para un tiro, la posesión debe pasar a `currentTeam`
  (el portero tiene el balón). El código hace `updatePossession(otherTeam)` → **error**.
- La rama `else if` es **inalcanzable** cuando `resultado === 'PARADA'` (la primera condición
  ya capturó ese caso).

### BUG-3 · La cola offline se atasca para siempre y duplica eventos (ALTO)

`app.js:191-221` (`syncQueue`):
- Envía `queue[0]`. Si el servidor responde 4xx (evento inválido), `response.ok` es false →
  `throw` → `catch` → `console.warn`. **El evento no se descarta, `shift()` no ocurre, y el
  siguiente `syncQueue()` vuelve a intentar el mismo evento indefinidamente.** Toda la cola
  queda bloqueada.
- No hay idempotencia: si el `fetch` se corta **después** del `commit` en servidor pero **antes**
  de recibir la respuesta, el `shift()` no ocurre → al reintentar, **el evento se inserta dos veces**.
- `eventData.id_local = Date.now().toString()` (`app.js:132`) puede colisionar y no se usa para nada.
- Envío **uno a uno en serie**: 50 eventos pendientes = 50 requests secuenciales.

### BUG-4 · El estado del partido no se persiste (CRÍTICO para el uso real)

- Marcador: solo en el DOM (`scoreAEl.textContent`, `app.js:143-144`).
- Posesión: solo en `state.posession` (`app.js:11`).
- Cronómetro: solo en `totalSeconds` (`timer.js:4`).
- Exclusiones: solo en el objeto `exclusions` en memoria (`app.js:14`).
- **Recargar la página a mitad de partido borra todo el estado de la UI.** El log de eventos
  sobrevive en SQLite, pero la sesión de captura se pierde. Inaceptable en pabellón.

### BUG-5 · El jugador excluido sigue siendo seleccionable (MEDIO, calidad de dato)

`app.js:164-189` (`startExclusionTimer`) solo escribe un contador en el `<span class="player-excl">`.
El `.player-item` **sigue siendo clicable** → se pueden registrar eventos a un jugador que está
en el banquillo, y las métricas deminutes quedan contaminadas.
El intervalo también se pierde al recargar (ver BUG-4).

### BUG-6 · `requirements.txt` no es un archivo de dependencias (BLOQUEANTE)

`extract.py` volcó el contenido de `Desarrollo App Balonmano_ Hoja Ruta.docx` a `requirements.txt`
(257 líneas de prosa en español, incluyendo "Obras citadas").
`pip install -r requirements.txt` **no instala Flask**. El proyecto no es reproducible.
`extract.py` ya cumplió su función → es un residuo a eliminar.

### BUG-7 · Integridad referencial desactivada (MEDIO)

SQLite viene con `PRAGMA foreign_keys` en **OFF por defecto** y `app.py` no lo activa.
`record_event` acepta `id_jugador` o `id_partido` inexistentes → filas huérfanas que rompen
los `JOIN` de las métricas.

### BUG-8 · Fuga de conexiones SQLite (MEDIO)

`app.py:39-67`: si `cursor.execute` lanza `sqlite3.Error`, la `conn` no se cierra nunca
(el `conn.close()` está en la línea 62, dentro del `try` exitoso) → file handle filtrado y
posible lock sobre `database.db`.

### BUG-9 · `debug=True` incondicional (ALTO, seguridad)

`app.py:107`: `app.run(debug=True, port=5000)` → expone el **debugger interactivo de Werkzeug**,
que permite **ejecución remota de código** sin autenticación, en la red local del pabellón.
Deve ser condicional a config y por defecto `False`.

### BUG-10 · La validación de 7m es solo cliente y trivialmente evadible (MEDIO)

`app.js:72`: un `confirm()` nativo. `readme.md` §6 exige: *"No permitir registrar un gol de 7m
si no se ha marcado previamente una falta personal/penalti"*. La regla debe estar en el servidor.

### BUG-11 · El resultado `POSTE` no existe (BAJO)

`readme.md` §2 lista `Poste` entre los resultados. `index.html:118-124` solo ofrece
`GOL`, `FALLO` (etiquetado "Fallo/Poste"), `PARADA`, `BLOQUEADO`. Falta el resultado `POSTE`
para poder distinguir poste de fallo en las métricas.

### BUG-12 · `resetTimer` detiene el reloj antes de confirmar (BAJO)

`timer.js:30-36`:
```js
function resetTimer() {
    stopTimer();                              // ← se detiene ANTES de preguntar
    if (confirm('¿Estás seguro de reiniciar el cronómetro?')) { totalSeconds = 0; ... }
}
```
Si el usuario cancela el `confirm`, **el reloj queda detenido** y no se reinicia. Bug clásico de
orden de operaciones.

### BUG-13 · `getCurrentTime()` lee del DOM (BAJO, frágil)

`timer.js:38-40` devuelve `timeDisplay.textContent` en vez de derivar de `totalSeconds`.
Depende del render del DOM; si el elemento se manipula, el reloj miente.

### BUG-14 · No hay ningún tipo de evento para `FALTA` (MEDIO)

`readme.md` §2 lista "Falta técnica" y la regla de 7m requiere "falta personal/penalti"
previa, pero el vocabulario actual **no tiene ningún evento de falta**. Sin él, la regla de 7m
no se puede implementar.

### BUG-15 · El botón de estadísticas no muestra nada (MEDIO, producto)

`app.js:299-313`: el botón "📊 Calcular Estadísticas Avanzadas" hace `console.table(data)` y un
`alert()`. El readme promete un motor de métricas ("Big Data", GKI, +/-, mapa de calor) y no hay
ninguna vista de análisis. El producto no cumple su promesa.

### BUG-16 · Anti-obstrucción del flujo de captura (BAJO, UX)

Después de cada evento, `resetSelection()` (`app.js:250-257`) **deselecciona al jugador**.
En la práctica el statistician quiere encadenar acciones del mismo jugador (varios tiros seguidos).
Esto contradice el objetivo de "<3 clics por acción" de `readme.md` §5.

### BUG-17 · `periodo` siempre vale 1 (BAJO)

`app.js:237`: `periodo: 1` hardcodeado. `readme.md` §1.1 del docx indica 2 tiempos de 30 min
en mayores. No hay contador de periodos.

### BUG-18 · `id_equipo` hardcodeado a `'A'` / `'B'` (BAJO, deuda de diseño)

`app.py:20-21` y `schema.sql:17`: `id_equipo` es un texto libre con valores `'A'`/`'B'`
atados a la posición local/visitante del partido. No es un modelo de dominio real. Está fuera del
alcance de este plan (ver §7) pero debe **documentarse** como limitación conocida.

---

## 2. Decisiones tomadas (valores por defecto)

> El usuario no especificó estas preferencias. Se adoptan los valores recomendados.
> Son puntos de extensión: cambiarlos es legítimo, pero entonces actualizá esta tabla
> **y** los criterios de aceptación correspondientes.

| # | Decisión | Valor adoptado | Motivo |
|---|---|---|---|
| D1 | Alcance | **Fases 0 → 4 completas** (hasta la vista de estadísticas) | Es lo que hace que el producto cumpla su promesa |
| D2 | Chart.js | **Vendorizado local** en `static/vendor/chart.min.js` | Coherente con offline-first; un pavilion sin wifi no puede depender de un CDN |
| D3 | Idempotencia | **Sí**, añadir columna `client_event_id` | Sin ella hay duplicados silenciosos que corrompen el marcador |
| D4 | Regla 7m | **Advertir, nunca bloquear** (HTTP 200 + `warnings[]`) | Bloquear la captura en vivo por una regla de negocio es inaceptable en pista |
| D5 | Migración de BD | **Destructiva**: `init_db.py` regenera la BD con `schema.sql` v2 | La BD actual solo contiene datos dummy de `init_db.py`. No hay datos reales que preservar. No se introduce Alembic |
| D6 | Estructura del proyecto | **Paquete por capas** (blueprints / services / models) en Fase 4 | Coherente con el crecimiento previsto (temporadas, career stats) |
| D7 | Idioma | **Interfaz y código en español** (nombres de dominio, `posesion`, no `posession`) | Coherencia con el resto del proyecto. Solo las palabras clave de Python/JS van en inglés |

---

## 3. Fase 0 — Desbloqueo (≈30 min)

Sin esta fase el proyecto no se puede instalar ni reproducir. **Hacerla primero.**

### 3.1 `requirements.txt` — reemplazar contenido

El archivo está versionado con contenido corrupto. **Sobrescribir** por completo:

```
Flask>=3.0,<4.0
```

### 3.2 `requirements-dev.txt` — nuevo

```
-r requirements.txt
pytest>=8.0
```

### 3.3 `pytest.ini` — nuevo

```ini
[pytest]
testpaths = tests
python_files = test_*.py
```

### 3.4 Eliminar `extract.py`

Su única función (volcar el `.docx` a `requirements.txt`) ya se cumplió y es la causa de BUG-6.
Borrar el archivo. **No tocar el `.docx`**, que es documentación valuable.

### 3.5 `.gitignore` — ampliar

Añadir al final:
```
instance/
*.log
.idea/
.vscode/
*.egg-info/
.pytest_cache/
```

### 3.6 `.env.example` — nuevo

```ini
FLASK_DEBUG=0
SECRET_KEY=cambiar-en-produccion
DATABASE_PATH=database.db
```

### 3.7 `README.md` — añadir secciones

Mantener el contenido actual (es la especificación del producto) y **añadir al final**:

1. **Cómo ejecutar** — requisitos (Python 3.10+), `python -m venv venv`,
   `.\venv\Scripts\activate` (Windows) / `source venv/bin/activate` (Linux/macOS),
   `pip install -r requirements.txt`, `python init_db.py`, `flask run` (o `python app.py`).
2. **Estructura del proyecto** — el árbol de ficheros de §0.4.
3. **Vocabulario de eventos** — las tablas de §4.1 (es el contrato frontend↔backend).
4. **Tests** — `pip install -r requirements-dev.txt` y `python -m pytest`.
5. **Limitaciones conocidas** — la de `id_equipo ∈ {'A','B'}` (BUG-18) y la del proxy de `+/-`
   (ver §4.6), para que nadie asuma un rigor que el sistema no tiene.

### Criterio de aceptación Fase 0

Clonación limpia del repo → `pip install -r requirements.txt` → `python init_db.py` →
`flask run` → la app carga y registra eventos. Sin errores.

---

## 4. Fase 1 — Vocabulario de dominio y métricas correctas (≈3 h) · **MAYOR VALOR**

Arregla BUG-1, BUG-10, BUG-11, BUG-14, BUG-7. **Es la fase más importante del plan.**

### 4.1 Vocabulario canónico (fuente única de verdad)

El mismo concepto (`PARADA`) viviendo en dos campos distintos es la causa raíz de BUG-1. Se define un
contrato explícito y **se documenta en el README** (Fase 0.7).

**`tipo_evento`** — la acción discreta registrada:

| Categoría | Valores | Requiere `resultado` |
|---|---|---|
| Lanzamiento | `LANZAMIENTO_6M`, `LANZAMIENTO_9M`, `LANZAMIENTO_7M`, `CONTRAATAQUE` | **Sí** |
| Ofensiva | `ASISTENCIA` | No |
| Defensiva | `ROBO_BALON`, `BLOQUEO`, `PARADA_PORTERO` | No |
| Error | `PERDIDA_BALON`, `FALTA_TECNICA`, `DOBLE`, `PASOS` | No |
| Falta (nueva, BUG-14) | `FALTA` (falta personal / posible 7m) | No |
| Disciplina | `AMARILLA`, `EXCLUSION_2MIN`, `DESCALIFICACION` | No |

**`resultado`** — nullable, **exclusivamente** para lanzamientos:
`GOL`, `FALLO`, `PARADA`, `BLOQUEADO`, `POSTE`

**`zona_porteria`** — cuadrícula 3×3: `TL, TC, TR, ML, MC, MR, BL, BC, BR` (ya implementado en
`index.html:105-113`, sin cambios en el frontend).

### 4.2 Reglas de conteo (fin de la ambigüedad)

Definir estas reglas en el código y en el README. Son la clave para que las métricas sean
correctas y para que ningún agente futuro reintroduzca el bug:

1. **`lanzamientos_totales`** = eventos con `tipo_evento ∈ {LANZAMIENTO_6M, LANZAMIENTO_9M,
   LANZAMIENTO_7M, CONTRAATAQUE}` (cualquier resultado válido).
2. **`goles`** = los anteriores con `resultado = 'GOL'`.
3. **Una parada del portero se contabiliza A TRAVÉS DEL LANZAMIENTO** (`resultado = 'PARADA'`
   en el evento del tirador), **nunca** con un evento adicional → garantiza cero doble conteo.
4. **`PARADA_PORTERO`** es un evento **defensivo independiente**, para el caso excepcional de
   registrar una parada sin haber registrado el tiro. **NO cuenta como lanzamiento** y solo
   alimenta las estadísticas del portero.
5. `faltas_recibidas` (para validar el 7m) = eventos con `tipo_evento = 'FALTA'` del equipo
   defensor en los últimos 60 segundos.
6. **Tercera exclusión ⇒ descalificación automática** (regla EHF real): al registrar la tercera
   `EXCLUSION_2MIN` del mismo jugador en el mismo partido, el backend genera automáticamente
   un evento `DESCALIFICACION` para ese jugador.

> **Cambio de nomenclatura respecto al código actual:** el botón de portero pasa de
> `data-event-type="PARADA"` a `data-event-type="PARADA_PORTERO"`. Es un cambio en frontend
> y backend **en la misma fase**. Es intencionado: elimina la ambigüedad raíz.

### 4.3 Cambios de esquema (`schema.sql` v2)

Añadir a `Eventos_Juego` (comando `ALTER TABLE`, compatible con la BD existente):

```sql
ALTER TABLE Eventos_Juego ADD COLUMN lado TEXT;                 -- 'ATAQUE' | 'DEFENSA'
ALTER TABLE Eventos_Juego ADD COLUMN client_event_id TEXT UNIQUE;  -- idempotencia de sync
ALTER TABLE Eventos_Juego ADD COLUMN creado_en TEXT NOT NULL DEFAULT (datetime('now'));

CREATE INDEX idx_eventos_partido ON Eventos_Juego(id_partido, id_evento);
CREATE INDEX idx_eventos_jugador ON Eventos_Juego(id_jugador);
```

Atribución de paradas a porteros concretos (necesaria para el GKI por jugador):

```sql
ALTER TABLE Jugadores ADD COLUMN posicion TEXT NOT NULL DEFAULT 'CAMPO';
-- valores: 'PORTERO' | 'CAMPO'
```

Cuando un lanzamiento termina en `resultado = 'PARADA'`, el evento está registrado a nombre
del **lanzador**, no del portero. La atribución se hace así (documentarla en el README):
las paradas sufridas por el equipo defensor T se atribuyen al jugador de T con
`posicion = 'PORTERO'` **si hay exactamente uno**; si hay varios o ninguno, las paradas
cuentan a nivel de **equipo** (exacto) y el reparto por jugador se marca como aproximado
(`"atribucion_portero": "exacta" | "aproximada_equipo"` en el JSON de stats).
`init_db.py` debe sembrar `posicion = 'PORTERO'` en los porteros de ejemplo
(Luis Rodríguez y Jorge Vázquez).

- `lado` orienta a qué portería se lanzó (necesario para que el mapa de calor y el GKI sean
  interpretables cuando ambos equipos lanzan).
- `client_event_id` es la clave de idempotencia (decisión D3).
- `coordenada_x` / `coordenada_y` se **mantienen normalizados 0..1** (ya es así en
  `app.js:95-96`; no cambiar).

Además, en `init_db.py`:
- Activar `PRAGMA foreign_keys = ON` (BUG-7) — en la conexión de escritura **y** documentar
  que `app.py` debe hacerlo en cada conexión de lectura/escritura.
- Sembrar datos de ejemplo que **incluyan un lanzamiento con `resultado='PARADA'` y su
  `zona_porteria`**, para poder verificar el GKI a mano.

### 4.4 Nuevo `services/metrics.py` — fórmulas puras

Crear el paquete `services/` con `__init__.py`. Separar las fórmulas de la capa HTTP es lo que
las hace testeables (hoy están incrustadas en el SQL de `app.py:79-101`).

```python
LANZAMIENTOS = {"LANZAMIENTO_6M", "LANZAMIENTO_9M", "LANZAMIENTO_7M", "CONTRAATAQUE"}
RESULTADOS_LANZAMIENTO = {"GOL", "FALLO", "PARADA", "BLOQUEADO", "POSTE"}

# Peso relativo de una parada según la distancia del tiro (base: 6m = 1.0)
# Sustituye al multiplicador fijo "* 2" de app.py:100
PESOS_GKI = {
    "LANZAMIENTO_6M": 1.0,   # máxima dificultad para el portero
    "LANZAMIENTO_7M": 0.85,
    "CONTRAATAQUE":  0.90,
    "LANZAMIENTO_9M": 0.60,  # menor dificultad para el portero
}

def eficiencia_tiro(goles: int, lanzamientos: int) -> float:
    """(goles / lanzamientos) * 100. Devolver 0.0 si no hay lanzamientos."""
    if not lanzamientos:
        return 0.0
    return round(goles / lanzamientos * 100, 1)

def efectividad_portero(paradas: int, tiros_recibidos: int) -> float:
    """(paradas / tiros a puerta recibidos) * 100. Devolver 0.0 si no hay tiros."""
    if not tiros_recibidos:
        return 0.0
    return round(paradas / tiros_recibidos * 100, 1)

def gki(paradas_por_tipo: dict) -> float:
    """Pondera cada parada por la dificultad del tiro que_paró.
    paradas_por_tipo: {"LANZAMIENTO_6M": 3, "LANZAMIENTO_9M": 5, ...}"""
    return round(
        sum(PESOS_GKI.get(tipo, 0.5) * n for tipo, n in paradas_por_tipo.items()), 2
    )

def perdidas_por_posesion(perdidas: int, posesiones: int) -> float:
    return round(perdidas / posesiones * 3, 2) if posesiones else 0.0

def mas_menos(goles_favor, goles_contra) -> int:
    return goles_favor - goles_contra
```

**Invariante obligatorio:** ninguna función puede lanzar `ZeroDivisionError` ni devolver `NaN`.
`redondear a 1 decimal` en porcentajes, `a 2` en índices.

### 4.5 Nuevo `services/eventos.py` — validación de dominio

```python
TIPO_EVENTO_VALIDOS = { ... }        # la allowlist de §4.1
RESULTADOS_VALIDOS = {"GOL", "FALLO", "PARADA", "BLOQUEADO", "POSTE"}
ZONAS_VALIDAS = {"TL","TC","TR","ML","MC","MR","BL","BC","BR"}

def validar_evento(datos) -> (errores: list, warnings: list)
def evento_admite_resultado(tipo_evento) -> bool   # True solo si tipo ∈ LANZAMIENTOS
def advertencias_reglas(evento, eventos_previos) -> list   # implementa la regla 7m
```

Reglas a implementar (reemplazan la validación de `app.py:34-37`):

1. Campos obligatorios: `id_partido`, `id_jugador`, `tipo_evento`, `tiempo_juego`.
2. `tipo_evento ∈ TIPO_EVENTO_VALIDOS` → si no, **HTTP 400** (no se guardan datos basura:
   es lo que mantiene correctas las métricas).
3. `resultado` obligatorio **si y solo si** `tipo_evento ∈ LANZAMIENTOS`; prohibido en caso contrario.
4. `zona_porteria ∈ ZONAS_VALIDAS` si se envía.
5. **Regla 7m (BUG-10, decisión D4):** si `tipo_evento == 'LANZAMIENTO_7M'` y no hay una
   `FALTA` del equipo defensor en los últimos **60 segundos** → añadir
   `warnings: ["7m_sin_falta"]` a la respuesta, pero **guardar el evento y devolver 201**.
   Nunca bloquear.
6. Tercera exclusión ⇒ descalificación automática (regla 6 de §4.2): si el jugador ya tiene
   dos `EXCLUSION_2MIN` en el partido, generar un evento `DESCALIFICACION` adicional.

### 4.6 `GET /api/stats/<id>` — reescrito

Reemplazar el SQL de `app.py:79-101` por: **una** consulta que traiga los eventos del partido,
y el cálculo en Python vía `metrics.py`. Estructura de la respuesta JSON:

```json
{
  "partido": { "id": 1, "nombre_equipo_a": "...", "nombre_equipo_b": "...",
               "marcador_a": 0, "marcador_b": 0, "periodo": 1 },
  "resumen": { "posesiones_a": 0, "posesiones_b": 0, "goles_totales": 0 },
  "equipos": [
    { "id_equipo": "A", "nombre": "...", "goles": 0, "lanzamientos": 0,
      "eficiencia_tiro": 0.0, "exclusiones": 0 }
  ],
  "jugadores": [
    { "id_jugador": 1, "nombre": "...", "id_equipo": "A", "numero_camiseta": 1,
      "goles": 0, "lanzamientos_totales": 0, "eficiencia_tiro": 0.0,
      "asistencias": 0, "perdidas": 0, "robos": 0, "bloqueos": 0,
      "exclusiones_2min": 0, "sanciones": 0,
      "es_portero": false,
      "paradas": 0, "tiros_recibidos": 0, "efectividad_portero": 0.0, "gki": 0.0,
      "mas_menos": 0 }
  ]
}
```

**Transparencia sobre el `+/-`:** un `+/-` real requiere **seguimiento de pista** (saber qué
7 jugadores están en-court en cada momento), lo cual es un módulo grande fuera del alcance de
este plan. Implementar un **proxy por posesión** (goles a favor − en contra del equipo mientras el
jugador está en la posesión) y **rotularlo explícitamente en la UI y en el JSON**
(p. ej. `"mas_menos_tipo": "proxy_posesion"`). No presentar la cifra como un `+/-` real.

### 4.7 Cambios en frontend para el vocabulario

- `index.html:74`: `data-event-type="PARADA"` → **`data-event-type="PARADA_PORTERO"`**
- `index.html:118-124`: añadir un botón de resultado **`POSTE`**
  (`<button class="outcome-btn default" data-outcome="POSTE">Poste</button>`).
- `index.html:72`: el `confirm()` de 7m se **conserva** (feedback inmediato en pista) pero
  deja de ser la única defensa; ahora el backend también avisa (§4.5 regla 5).
- **Añadir** botones de `FALTA` y `FALTA_TECNICA` en el grupo de nueva "Faltas" (los necesita
  la regla 7m) → BUG-14.

### Criterio de aceptación Fase 1

1. Un evento `LANZAMIENTO_9M` con `resultado='PARADA'` y `zona_porteria` **cuenta una sola
   parada** para el portero (no dos, no cero).
2. Un portero con 3 paradas de 6m tiene **GKI estrictamente mayor** que uno con 3 paradas de 9m.
3. `eficiencia_tiro(0, 0) == 0.0` — sin excepción.
4. `POST /api/event` con `tipo_evento='INVENTADO'` → **400**, y **no** se escribe nada en la BD.
5. `POST /api/event` con `LANZAMIENTO_7M` sin falta previa → **201** + `warnings: ["7m_sin_falta"]`.
6. `python -m pytest` pasa.

---

## 5. Fase 2 — Persistencia de estado y cola offline (≈2 h)

Arregla BUG-2, BUG-3, BUG-4, BUG-5, BUG-12, BUG-13, BUG-17. **Es la fase que evita perder un
partido en directo.**

### 5.1 Reconstrucción del estado al recargar (event-sourcing) — BUG-4

El marcador y la posesión son **derivados del log de eventos** → no hace falta persistirlos por
separado. Esto refuerza la arquitectura del proyecto en vez de contradecirla.

**`GET /api/matches/<id>/state`** — deriva de `Eventos_Juego`:
- `marcador_a` / `marcador_b`: `COUNT` de `resultado='GOL'` agregado por equipo del lanzador.
- `posesion_actual`: equipo del último evento que transfiere posesión
  (gol / parada / robo / pérdida). `NULL` si no hay eventos.
- `periodo`, `segundos_jugados`: los **únicos** valores que sí se guardan (ver abajo).
- `exclusiones_activas`: jugadores con una `EXCLUSION_2MIN` sin expirar (ver §5.4).

**`PATCH /api/matches/<id>/state`** — persiste solo el reloj:
```sql
ALTER TABLE Partidos ADD COLUMN segundos_jugados INTEGER NOT NULL DEFAULT 0;
ALTER TABLE Partidos ADD COLUMN periodo_actual   INTEGER NOT NULL DEFAULT 1;
ALTER TABLE Partidos ADD COLUMN en_pausa         INTEGER NOT NULL DEFAULT 0;
```

### 5.2 Corregir `index()` para no depender del "último partido" implícito

`app.py:17` hace `SELECT * FROM Partidos ORDER BY id_partido DESC LIMIT 1` — siempre el último,
sin que el usuario pueda elegir. Cambiar a `/ ?match=<id>` con default al último, y pasar
`match_id` al JS en el campo oculto `#match-id` (`index.html:34`).

### 5.3 Corregir la lógica de posesión — BUG-2

Reemplazar `app.js:147-152` por una función con la semántica correcta y **explícita**:

```js
function resolverPosesion(equipoSeleccionado, evento) {
    const rival = equipoSeleccionado === 'A' ? 'B' : 'A';
    // Gol: saca de centro el equipo que encajó → posesión al rival del que marcó.
    if (evento.resultado === 'GOL') return rival;
    // Tiro parado: el balón queda en poder del portero → rival del lanzador.
    // (aquí equipoSeleccionado es el LANZADOR, porque el operador selecciona
    //  al lanzador antes de elegir el resultado en el modal)
    if (evento.resultado === 'PARADA') return rival;
    // Parada registrada directamente sobre el portero: se queda su equipo.
    if (evento.tipo_evento === 'PARADA_PORTERO') return equipoSeleccionado;
    // Pérdidas y faltas: posesión al rival.
    if (['PERDIDA_BALON', 'FALTA_TECNICA', 'DOBLE', 'PASOS'].includes(evento.tipo_evento))
        return rival;
    // Robo / bloqueo: el equipo del defensor recupera.
    if (['ROBO_BALON', 'BLOQUEO'].includes(evento.tipo_evento))
        return equipoSeleccionado;
    return null; // resto de eventos (asistencias, sanciones, faltas): sin cambio
}
```

> **Convención de registro que esta función asume** (documentarla también en el README):
> en un lanzamiento el operador selecciona al **lanzador** y luego elige el resultado en el
> modal; en una `PARADA_PORTERO` el operador selecciona al **portero**. La función distingue
> ambos casos por `resultado` vs `tipo_evento`, así que la convención debe respetarse.

### 5.4 Exclusión de 2 min derivada del reloj del partido — BUG-5

Hoy `startExclusionTimer` (`app.js:164-189`) usa un `setInterval` propio, que se pierde al
recargar. Cambiar a: **el estado de exclusión se deriva del reloj de partido**
(`tiempo_juego` del evento + 120 s contra `Partidos.segundos_jugados`).

Consecuencia funcional: mientras un jugador tenga una exclusión activa, su `.player-item`
recibe la clase `disabled` (`pointer-events: none` en CSS) → **no se pueden registrar eventos
a un jugador en el banquillo**. Es una garantía de calidad de dato, no solo de UI.

### 5.5 Cola offline endurecida — BUG-3

Nuevo `static/js/queue.js`, extraído de `app.js` para poder evolucionarlo de forma aislada.

- **Clave por partido:** `eventosBalonmano:{matchId}`. (Hoy `app.js:133` usa la clave global
  `'eventosBalonmano'` → al cambiar de partido se mezclan los eventos de dos partidos.)
- **Idempotencia:** `client_event_id = crypto.randomUUID()` por evento. El backend responde con
  `INSERT ... ON CONFLICT(client_event_id) DO NOTHING` → un reintento del mismo evento **no
  duplica**. Implementar también en la ruta `/api/event` individual y en `/api/events` por lotes.
- **Anti-bloqueo de la cola (el bug más grave):** clasificar la respuesta:
  - `2xx` → `shift()` y continuar.
  - `4xx` → **evento permanentemente inválido**: mover a una lista
    `eventosBalonmanoFallidos:{matchId}` (con el error y la fecha) y **continuar** con el
    siguiente. La cola nunca se bloquea.
  - `5xx` o error de red → **pausar** y reintentar con backoff exponencial
    (1 s, 2 s, 4 s, 8 s, máx. 30 s). Sin reintentos en caliente (sin espera entre intentos).
- **Lote:** nuevo endpoint `POST /api/events` que acepta un array y responde con
  `{ guardados: [...ids], rechazados: [{client_event_id, error}] }`. Enviar en lotes de hasta
  50 en vez de N requests en serie.
- **No bloquear la UI:** la sincronización corre en segundo plano. Quitar el `await syncQueue()`
  del camino de captura.
- **Al arrancar y en `online`:** disparar la sincronización (ya está en `app.js:224-226`,
  mantener y apuntar al nuevo módulo).

### 5.6 Cronómetro — BUG-12, BUG-13, BUG-17

`static/js/timer.js`:
- `getCurrentTime()` → derivar de `totalSeconds`, **no** leer `textContent` del DOM.
- `resetTimer()` → pedir el `confirm` **antes** de detener el reloj.
- Añadir `duracionPeriodo` (por defecto 1800 s = 2×30 min) y contador de periodos: al alcanzarla,
  incrementar `periodo_actual` y avisar al operador. Persistir vía `PATCH /api/matches/<id>/state`.
- Exponer `TimerModule.getSeconds()` para que las exclusiones se deriven del mismo reloj
  (**un único reloj**, no dos `setInterval` paralelos).
- Al cargar la página, inicializar desde `GET /api/matches/<id>/state`.

### 5.7 Anti-obstrucción de la captura — BUG-16

Añadir un interruptor **"fijar jugador"** (por defecto **activo**) en el panel de acciones.
Con el interruptor activo, `resetSelection()` (`app.js:250-257`) **no** deselecciona al jugador
tras un evento → se pueden encadenar 3 tiros del mismo tirador en 3 clics, que es el objetivo
de `<3 clics` de `readme.md` §5. Desactivarlo devuelve el comportamiento actual
(deseleccionar) para cuando el operador cambia de jugador constantemente.

### Criterio de aceptación Fase 2

1. Registrar 3 goles → **recargar la página** → marcador, posesión y reloj **conservados**.
2. La cola vacía 20 eventos pendientes en **1 request por lote**, no 20.
3. Un evento inválido (4xx) en mitad de la cola → los válidos siguientes **se guardan**;
   el inválido queda en `eventosFallidos` y la cola **no** se bloquea.
4. Un evento enviado dos veces con el mismo `client_event_id` → **una sola fila** en la BD.
5. La posesión tras un gol está en el **rival**; tras una parada, en el **equipo del portero**.
6. Un jugador con `EXCLUSION_2MIN` activa es **no seleccionable**, y la exclusión sobrevive a
   un F5.
7. Un jugador con el reloj a 90 s de una exclusión de 120 s → tras F5 sigue mostrando `0:30`.

---

## 6. Fase 3 — Vista de estadísticas (≈3–4 h)

Arregla BUG-15. Convierte la promesa del readme en realidad. **Requiere Fase 1.**

### 6.1 Endpoints

- `GET /api/matches/<id>/stats` → JSON de §4.6.
- `GET /api/matches/<id>/heatmap` → agregado para el mapa de calor:
  - `porteria`: matriz 3×3 con conteo de goles por `zona_porteria` (y desglose de paradas).
  - `zonas_tiro`: conteo de lanzamientos por `tipo_evento`.
  - `origen`: histograma de `coordenada_x` / `coordenada_y` (rejilla, p. ej. 8×8) normalizados.

### 6.2 Vista

Nueva `templates/stats.html`:
- Marcador final y resumen de partido.
- **Tabla por jugador**: dorsal, nombre, goles, lanzamientos, **% eficiencia**, asistencias,
  paradas, **GKI**, exclusiones, pérdidas, +/- (etiquetado como proxy, ver §4.6).
- **Gráficos con Chart.js** (vendorizado — decisión D2) desde `static/vendor/chart.min.js`:
  barras de goles por jugador, distribución de zonas de tiro, effectiveness de portería.
- **Mapa de calor 3×3** de la portería, reutilizando el estilo `.goal-map` / `.goal-zone` que ya
  existe en `static/css/styles.css:380-405`.
- Enlace "Ver estadísticas" desde `index.html` (junto a los botones existentes de
  `index.html:145-148`).

### 6.3 Vendoring de Chart.js

Descargar `chart.min.js` (v4 UMD) a `static/vendor/chart.min.js`. **Prohibido** referenciar un CDN
en el HTML: rompería el requisito offline-first y fallaría en pabellones sin salida a internet.
Si la descarga no es posible en el entorno, servir el mapa de calor con **CSS puro** (gradientes
por celda) y documentar que Chart.js es opcional.

### Criterio de aceptación Fase 3

`/stats?match=1` renderiza la tabla y los gráficos con los datos reales del partido. El GKI de los
porteros es **visible y coherente** con la regla de pesos de §4.4. La vista **funciona sin
conexión a internet**.

---

## 7. Fase 4 — Refactor y robustez (≈2 h)

**Requiere Fase 1 completa** (las métricas deben estar en `services/` antes de mover las rutas).
Arregla BUG-7, BUG-8, BUG-9, BUG-18 (parcialmente).

### 7.1 Estructura objetivo

```
app-balonmano/
├── app.py                     # factory + run; instancia la app y registra blueprints
├── config.py                  # DEBUG / SECRET_KEY / DATABASE_PATH desde env
├── db.py                      # get_db() como context manager, init_db(), PRAGMA
├── services/
│   ├── __init__.py
│   ├── eventos.py             # allowlists, validación, regla 7m
│   ├── metrics.py             # fórmulas puras (Fase 1)
│   └── export.py              # JSON compatible con reportes EHF
├── blueprints/
│   ├── __init__.py
│   ├── web.py                 # GET /, GET /stats
│   └── api.py                 # todos los /api/*
├── models/
│   ├── __init__.py
│   ├── partido.py
│   ├── jugador.py
│   └── evento.py              # acceso a datos por entidad
├── templates/
│   ├── base.html              # layout común (extraer de index.html)
│   ├── index.html
│   └── stats.html
├── static/
│   ├── css/styles.css
│   ├── js/
│   │   ├── app.js             # orquestación y estado
│   │   ├── timer.js           # reloj único
│   │   ├── queue.js           # cola offline (Fase 2)
│   │   ├── tracker.js         # mapa de pista + portería
│   │   └── stats.js           # Fase 3
│   └── vendor/chart.min.js    # Fase 3
├── tests/
│   ├── conftest.py
│   ├── test_metrics.py
│   └── test_api.py
├── migrations/                # o, equivalentemente, schema.sql v2
├── schema.sql  init_db.py
├── requirements.txt  requirements-dev.txt  pytest.ini
├── .env.example  .gitignore  README.md
```

### 7.2 Hardening obligatorio

- **`PRAGMA foreign_keys = ON` en CADA conexión** (`db.py: get_db()`) — BUG-7.
- **`get_db()` como context manager** que cierra siempre la conexión, incluso si la función
  lanzó — BUG-8 (hoy `app.py:66-67` filtra la conexión).
- **Ruta de BD absoluta** vía config (`os.path.join(app.root_path, ...)`) — hoy `'database.db'`
  es relativa al CWD y falla si el servidor se arranca desde otro directorio.
- **`debug` desde entorno, por defecto `False`** — BUG-9. `app.run(debug=app.config["DEBUG"])`.
- **`SECRET_KEY` desde entorno** con error explícito si falta en producción.
- **Manejo de errores**: un `@app.errorhandler` que devuelva JSON (no HTML de debug) para rutas
  `/api/*`.
- **`extract.py` eliminado** (Fase 0).
- **`id_equipo`**: documentar la limitación (BUG-18). El modelo correcto
  (`Equipos` + `Partido_Equipos`) queda fuera de alcance — ver §8.

### 7.3 Tests (`pytest`) — casos mínimos obligatorios

`tests/test_metrics.py`:
- `test_eficiencia_tiro`: (3, 6) == 50.0
- `test_eficiencia_tiro_sin_lanzamientos`: (0, 0) == 0.0 — **no** lanza excepción
- `test_gki_pondera_por_zona`: 3 paradas de 6m > 3 paradas de 9m
- `test_gki_ignora_tipo_desconocido`: no lanza, usa peso por defecto
- `test_efectividad_portero`: (2, 4) == 50.0 ; (0, 0) == 0.0

`tests/test_api.py` (con `conftest.py` proveendo una BD temporal por test):
- `test_registro_exitoso`: POST evento → 201, fila en la BD
- `test_tipo_evento_invalido`: → 400 y **0 filas** insertadas
- `test_lanzamiento_exige_resultado`: `LANZAMIENTO_6M` sin `resultado` → 400
- `test_7m_sin_falta_avisa_pero_guarda`: → 201 con `warnings`
- `test_7m_con_falta_previa_no_avisa`: → 201 sin warnings
- `test_idempotencia_mismo_client_event_id`: dos POST → **1 fila**
- `test_lote_con_un_invalido`: 3 eventos, 1 inválido → 2 guardados, 1 en `rechazados`
- `test_parada_contada_una_sola_vez`: un `LANZAMIENTO_9M`+`PARADA` → `paradas == 1`, `gki > 0`
- `test_atribucion_portero_unico`: un `LANZAMIENTO_6M`+`PARADA` de un jugador del equipo A →
  el único `PORTERO` del equipo B suma 1 parada y su `gki == 1.0`
- `test_estado_se_reconstruye`: 3 goles → `GET /state` devuelve marcador correcto
- `test_clave_externa_rechazada`: `id_jugador=99999` → error (FK activa)

### Criterio de aceptación Fase 4

`python -m pytest` verde. La app arranca con `FLASK_DEBUG=0`. Insertar un `id_jugador` inexistente
es rechazado. Ninguna métrica cambia de valor respecto a la Fase 1 (los tests de `test_metrics.py`
lo garantizan).

---

## 8. Fuera de alcance (registrado para el futuro)

No implementar en este plan. Documentar en el README como limitaciones conocidas:

1. **Modelo `Equipos` + `Partido_Equipos`** — elimina el hardcodeo `id_equipo ∈ {'A','B'}`
   (BUG-18). Requiere migración de datos.
2. **`+/-` real** — requiere seguimiento de pista (lineups: qué 7 jugadores hay en-court en cada
   momento). Hoy solo hay el proxy por posesión (§4.6).
3. **Temporadas y estadísticas de carrera** — el esquema ya lo soporta por las FK.
4. **Export PDF** (hoja de ruta §1.1 del `.docx`).
5. **Despliegue** — WSGI (gunicorn/waitress) en lugar de `app.run`. El `.docx` menciona
   PythonAnywhere.

---

## 9. Orden de ejecución y dependencias

```
Fase 0 ──▶ Fase 1 ──┬──▶ Fase 2  (persistencia + cola)
(bloquea    (base)   │
instalación)         ├──▶ Fase 3  (vista de stats)
                     └──▶ Fase 4  (refactor + seguridad)
```

**Secuencia recomendada de commits** (un commit por fase, cada uno ejecutable y testeable):

1. `chore: fix corrupted requirements.txt, add dev deps and run instructions` (Fase 0)
2. `feat(metrics): canonical event vocabulary + pure metrics service + tests` (Fase 1)
3. `feat(state): derive match state from event log, fix possession logic` (Fase 2.1–2.3)
4. `fix(queue): per-match queue, idempotency, batch endpoint, no poisoning` (Fase 2.4–2.5)
5. `feat(stats): statistics view with charts and heat map` (Fase 3)
6. `refactor: blueprints, services, config from env, security hardening` (Fase 4)

### Reglas de trabajo para el agente que implemente

- **Una fase por commit.** No mezclar fases: una fase debe ser revisable y reversible por separado.
- **No romper la arquitectura por eventos.** Todas las métricas se derivan del log; no introducir
  contadores agregados en `Partidos`.
- **Frontend y backend en el mismo commit** cuando cambia el vocabulario de eventos.
- **Ningún `console.log`/`console.table` como salida de producto** (eliminar el de `app.js:306`).
- **No introducir frameworks de JS, build steps ni CDNs.**
- Si un paso del plan resulta ambiguo, elegir la opción que **mantenga la captura en vivo
  funcionando** y documentar la decisión en el README.

---

## 10. Definición de "hecho"

- [ ] `pip install -r requirements.txt` desde repo limpio instala Flask
- [ ] `python init_db.py` crea la BD y `flask run` arranca sin errores
- [ ] Ninguna métrica de portero (paradas, efectividad, GKI) es 0 cuando hay paradas registradas
- [ ] La posesión cambia correctamente tras gol, parada, robo y pérdida
- [ ] Recargar la página a mitad de partido conserva marcador, posesión, reloj y exclusiones
- [ ] La cola offline no se bloquea nunca y no duplica eventos
- [ ] Un jugador excluido no es seleccionable
- [ ] La regla de 7m está validada **en el servidor** y no bloquea la captura
- [ ] `/stats?match=1` muestra tabla + gráficos + mapa de calor, **sin conexión a internet**
- [ ] `python -m pytest` pasa
- [ ] `FLASK_DEBUG=0` es el default y el debugger de Werkzeug no está expuesto
- [ ] Las claves foráneas están activas y `id_jugador` inexistente es rechazado
- [ ] El README documenta ejecución, estructura, vocabulario de eventos y limitaciones
