# Profundizaciones recomendadas para Handball Stats

## Objetivo general

Esta etapa no busca agregar muchas funciones nuevas, sino profundizar el análisis a partir de los datos que la aplicación ya registra.

La prioridad es construir estadísticas:
- fáciles de registrar;
- fáciles de interpretar;
- útiles para entrenadores y jugadores;
- respaldadas por investigación de análisis de rendimiento en handball;
- compatibles con la arquitectura actual;
- sin depender de IA, video tracking o sensores.

Modelo recomendado:

**POSESIÓN → ATAQUE → ACCIÓN → RESULTADO**

---

## 1. Estadísticas de ataque

### 1.1 Ataques totales

Incorporar el concepto de **ataque** como unidad estadística.

Indicador:

`Ataques totales`

Esto permitirá relacionar goles, lanzamientos y pérdidas con la cantidad de ataques realizados.

### 1.2 Eficacia de ataque

`Eficacia de ataque = Goles / Ataques × 100`

Ejemplo: 25 goles en 50 ataques = 50 %.

Debe coexistir con la eficacia de lanzamiento:

- eficacia de ataque: qué tan bien termina el equipo sus ataques;
- eficacia de lanzamiento: qué tan bien convierte los lanzamientos.

### 1.3 Lanzamientos por ataque

`Lanzamientos por ataque = Lanzamientos / Ataques`

También puede expresarse como:

`Frecuencia de lanzamiento = Lanzamientos / Ataques × 100`

### 1.4 Pérdidas por ataque

`Tasa de pérdidas = Pérdidas / Ataques × 100`

Esto permite distinguir entre baja eficacia causada por malos lanzamientos y baja eficacia causada por pérdidas antes de lanzar.

---

## 2. Resultado de los lanzamientos

Convertir los resultados ya registrados en una estadística visible:

- GOL
- PARADA
- FALLO
- POSTE
- BLOQUEADO

### Tabla recomendada

| Resultado | Cantidad | % de lanzamientos |
|---|---:|---:|
| Gol | 25 | 52,1 % |
| Parada | 12 | 25,0 % |
| Fallo | 7 | 14,6 % |
| Poste | 2 | 4,2 % |
| Bloqueado | 2 | 4,2 % |

Los valores son ilustrativos.

Esto permite saber **por qué no entraron los lanzamientos**.

---

## 3. Eficacia por tipo de lanzamiento

Priorizar:

- 6 metros;
- 9 metros;
- 7 metros;
- contraataque;
- otros tipos ya contemplados.

Para cada tipo mostrar:

- lanzamientos;
- goles;
- paradas;
- fallos;
- eficacia;
- porcentaje sobre el total.

Ejemplo:

| Tipo | Lanz. | Goles | Eficacia |
|---|---:|---:|---:|
| 6 m | 12 | 8 | 66,7 % |
| 9 m | 20 | 8 | 40 % |
| 7 m | 5 | 5 | 100 % |
| Contraataque | 6 | 4 | 66,7 % |

---

## 4. Profundizar los parciales de 10 minutos

La sección **“Parciales cada 10 minutos”** debería pasar de mostrar principalmente la evolución del marcador a mostrar rendimiento.

Por intervalo:

- goles;
- lanzamientos;
- eficacia de lanzamiento;
- ataques;
- eficacia de ataque;
- pérdidas;
- lanzamientos por ataque;
- eventualmente paradas del arquero.

Ejemplo:

| Período | Ataques | Goles | Lanz. | Ef. ataque | Ef. lanzamiento | Pérdidas |
|---|---:|---:|---:|---:|---:|---:|
| 0–10 | 15 | 6 | 12 | 40 % | 50 % | 2 |
| 10–20 | 14 | 5 | 11 | 35,7 % | 45,5 % | 3 |
| 20–30 | 16 | 8 | 14 | 50 % | 57,1 % | 1 |

Esto permite detectar cuándo cambia el rendimiento.

---

## 5. Últimos minutos y situaciones cerradas

Ampliar el análisis que ya existe para 7 metros.

### Últimos 5 minutos

Mostrar:

- goles;
- ataques;
- lanzamientos;
- eficacia;
- pérdidas;
- exclusiones;
- diferencia de marcador.

### Situaciones cerradas

Puede analizarse el rendimiento cuando:

`|diferencia de goles| ≤ 2`

No hace falta convertir esto en un sistema complejo.

---

## 6. Profundizar los 7 metros

Mantener **“7 metros en contexto”** y convertirlo progresivamente en una estadística específica.

Mostrar:

- 7 m lanzados;
- 7 m convertidos;
- 7 m fallados;
- eficacia;
- 7 m recibidos;
- paradas del arquero en 7 m;
- contexto del marcador;
- período;
- últimos 5 minutos.

---

## 7. Estadísticas defensivas

La aplicación ya registra:

- robos;
- bloqueos;
- pérdidas;
- exclusiones;
- tarjetas;
- paradas.

Crear un resumen defensivo con:

- robos;
- bloqueos;
- paradas;
- pérdidas provocadas, solamente cuando puedan determinarse de forma fiable;
- exclusiones provocadas;
- tarjetas;
- goles recibidos.

### Importante

Evitar el doble conteo. No asumir automáticamente que cada acción defensiva representa una recuperación de posesión.

---

## 8. Análisis de arqueros

Mantener el GKI como **métrica complementaria**, no como indicador principal.

### Estadísticas principales

- lanzamientos recibidos;
- paradas;
- goles recibidos;
- porcentaje de paradas;
- paradas por tipo;
- 7 m enfrentados;
- 7 m atajados;
- contraataques enfrentados;
- contraataques atajados.

### Por tipo

Comparar:

- 6 m;
- 9 m;
- 7 m;
- contraataque;
- extremos u otras categorías disponibles.

---

## 9. Estadísticas individuales

Mantener:

- goles;
- lanzamientos;
- eficacia;
- asistencias;
- pérdidas;
- robos;
- bloqueos;
- exclusiones;
- tarjetas;
- paradas cuando corresponda.

Agregar progresivamente:

- participación en lanzamientos;
- goles por lanzamiento;
- pérdidas por ataque, si el modelo permite asignarlas;
- asistencias por partido;
- participación porcentual en los goles.

### Participación goleadora

`Participación goleadora = Goles del jugador / Goles del equipo × 100`

---

## 10. Análisis por zonas

La aplicación ya tiene mapas de calor 3×3.

Complementarlos con:

- lanzamientos;
- goles;
- paradas;
- fallos;
- eficacia.

Ejemplo:

| Zona | Lanzamientos | Goles | Eficacia |
|---|---:|---:|---:|
| Superior izquierda | 8 | 5 | 62,5 % |
| Superior centro | 10 | 4 | 40 % |
| Superior derecha | 7 | 5 | 71,4 % |

El mapa sirve para visualizar y la tabla para analizar.

---

## 11. Comparación entre equipos

La vista `/comparar` debería utilizar indicadores equivalentes.

Comparar:

- goles;
- ataques;
- eficacia de ataque;
- lanzamientos;
- eficacia de lanzamiento;
- pérdidas;
- pérdidas por ataque;
- robos;
- bloqueos;
- paradas;
- eficacia de portero;
- 7 m;
- contraataques.

Objetivo: responder rápidamente **por qué ganó un equipo**.

---

## 12. Resumen estadístico automático

Como evolución posterior, generar un resumen mediante reglas transparentes, sin IA.

Ejemplo:

> San Roque convirtió el 52 % de sus lanzamientos frente al 48 % del rival, pero realizó menos ataques efectivos y registró una mayor tasa de pérdidas.

Debe construirse exclusivamente con datos disponibles.

---

## 13. Estadísticas de temporada

La vista `/temporada` ya existe.

Ampliar progresivamente con:

- ataques;
- eficacia de ataque;
- lanzamientos por ataque;
- pérdidas por ataque;
- goles por partido;
- lanzamientos por partido;
- eficacia por tipo;
- evolución partido a partido.

---

## 14. Evolución individual durante la temporada

Crear una vista de evolución.

Ejemplo:

| Partido | Goles | Lanz. | Eficacia | Pérdidas |
|---|---:|---:|---:|---:|
| 1 | 5 | 9 | 55,6 % | 2 |
| 2 | 7 | 11 | 63,6 % | 1 |
| 3 | 4 | 8 | 50 % | 3 |

Esto permite observar tendencias sin crear rankings artificiales.

---

## 15. Estadísticas normalizadas por 60 minutos

En una etapa posterior pueden calcularse:

- goles por 60 min;
- lanzamientos por 60 min;
- pérdidas por 60 min;
- asistencias por 60 min.

**Condición:** solo utilizarlas cuando la aplicación registre correctamente el tiempo de participación individual.

---

## 16. Qué NO implementar todavía

No recomiendo priorizar:

- inteligencia artificial;
- análisis automático de video;
- tracking de jugadores;
- distancia recorrida;
- velocidad;
- mapas de movimiento;
- xG complejo;
- machine learning;
- predicción de resultados;
- ratings individuales extremadamente complejos;
- PlayerScore propietario como métrica principal;
- sensores externos.

La aplicación puede convertirse en una herramienta sólida sin estas funciones.

---

## 17. Prioridad de implementación

### Fase 1 — Ataque

1. Definir ataques consistentemente.
2. Ataques totales.
3. Eficacia de ataque.
4. Lanzamientos por ataque.
5. Pérdidas por ataque.
6. Integración en `/stats`.

### Fase 2 — Lanzamientos

7. GOL / PARADA / FALLO / POSTE / BLOQUEADO.
8. Eficacia por tipo.
9. Cantidad y porcentaje por tipo.
10. Integración con mapas de calor.

### Fase 3 — Períodos

11. Mejorar parciales de 10 minutos.
12. Ataques y pérdidas por período.
13. Eficacia de ataque por período.
14. Eficacia de lanzamiento por período.
15. Últimos 5 minutos.

### Fase 4 — Defensa y portería

16. Resumen defensivo.
17. Paradas por tipo.
18. Eficacia del arquero por tipo.
19. 7 m del arquero.
20. Contraataques enfrentados y detenidos.

### Fase 5 — Individual

21. Participación goleadora.
22. Estadísticas individuales normalizadas.
23. Evolución del jugador.
24. Comparaciones individuales.

### Fase 6 — Temporada

25. Ataques acumulados.
26. Eficacia de ataque acumulada.
27. Pérdidas por ataque.
28. Eficacia por tipo.
29. Evolución partido a partido.

---

## 18. Cambios recomendados en `/stats`

### Bloque 1 — Resultado
- marcador;
- período;
- diferencia.

### Bloque 2 — Ataque
- ataques;
- goles;
- eficacia de ataque;
- lanzamientos;
- eficacia de lanzamiento;
- pérdidas;
- pérdidas por ataque.

### Bloque 3 — Lanzamientos
- tabla por tipo;
- resultado de lanzamiento;
- eficacia.

### Bloque 4 — Períodos
- 0–10;
- 10–20;
- 20–30;
- etc.

### Bloque 5 — Defensa
- robos;
- bloqueos;
- paradas;
- exclusiones.

### Bloque 6 — Jugadores
Mantener la tabla actual y ampliarla gradualmente.

### Bloque 7 — Zonas
- mapas de calor;
- tabla numérica.

---

## 19. Principio fundamental: no aumentar la carga de captura

Una fortaleza de Handball Stats es que muchas estadísticas pueden calcularse **después del partido a partir de los eventos existentes**.

Estrategia:

**Registrar pocos eventos bien definidos → derivar muchas estadísticas después.**

No conviene obligar al operador a registrar manualmente posesiones, métricas avanzadas o posiciones adicionales si pueden derivarse.

---

## 20. Calidad de datos antes de agregar más métricas

Antes de profundizar, revisar:

### Períodos
Verificar correctamente:
- primer tiempo;
- segundo tiempo;
- prórrogas, si existen.

### Coordenadas
Los mapas de calor deben calcularse solamente cuando existan coordenadas suficientes.

### Jugadores rivales
Mantener identificados los jugadores cuando sea posible, especialmente para:
- estadísticas individuales;
- arqueros;
- pérdidas;
- análisis de temporada.

### Arqueros
Diferenciar las pérdidas del arquero de las pérdidas de jugadores de campo cuando el dato lo permita.

---

## 21. Principio científico

Priorizar indicadores utilizados en análisis de rendimiento de handball:

- eficacia de ataque;
- eficacia de lanzamiento;
- frecuencia de lanzamiento;
- pérdidas;
- eficacia de porteros;
- análisis por períodos;
- rendimiento según tipo de lanzamiento;
- asistencias;
- bloqueos;
- robos;
- exclusiones.

Una estadística simple y bien definida es preferible a una métrica compleja difícil de interpretar.

---

## 22. Arquitectura recomendada

La aplicación ya separa razonablemente:

- captura;
- API;
- métricas;
- estadísticas;
- portería;
- temporada.

Mantener esta estructura.

### Backend

Centralizar fórmulas en `services/metrics.py`.

Ejemplos:

- `eficacia_ataque()`
- `frecuencia_tiro()`
- `perdidas_por_ataque()`
- `eficiencia_tiro()`
- `efectividad_portero()`

### API

Exponer indicadores calculados mediante endpoints de estadísticas.

### Frontend

Mostrar solamente los indicadores relevantes y fáciles de interpretar.

---

## 23. Las diez mejoras prioritarias

Si hubiera que elegir solamente diez:

1. **Definir ataques de manera consistente.**
2. **Agregar ataques totales.**
3. **Agregar eficacia de ataque.**
4. **Agregar lanzamientos por ataque.**
5. **Agregar pérdidas por ataque.**
6. **Desglosar los resultados de los lanzamientos.**
7. **Agregar eficacia por tipo de lanzamiento.**
8. **Mejorar los parciales de 10 minutos.**
9. **Profundizar estadísticas de arquero por tipo de lanzamiento.**
10. **Mejorar comparación entre equipos con estos indicadores.**

---

## 24. Resultado esperado

Con estas profundizaciones, Handball Stats pasaría de ser principalmente una herramienta para **registrar lo ocurrido durante el partido** a una herramienta capaz de explicar **cómo y por qué se produjo el resultado**.

La aplicación debería poder responder:

- ¿Cuántos ataques tuvo cada equipo?
- ¿Qué equipo fue más eficaz atacando?
- ¿Quién perdió más posesiones?
- ¿Quién lanzó más?
- ¿Quién lanzó mejor?
- ¿Desde qué zonas fue más efectivo?
- ¿Qué tipos de lanzamiento funcionaron mejor?
- ¿Cuándo cambió el partido?
- ¿Qué arquero tuvo mayor eficacia?
- ¿Por qué ganó un equipo y perdió el otro?
- ¿Qué jugadores tuvieron mayor impacto?
- ¿El rendimiento se mantiene durante la temporada?

El siguiente salto lógico es:

**más profundidad analítica sin aumentar innecesariamente la complejidad de captura.**

---

## Fundamento

Estas recomendaciones se basan en la revisión realizada sobre análisis de rendimiento en handball, especialmente en indicadores como eficacia de ataque, eficacia de lanzamiento, frecuencia de lanzamiento, pérdidas, eficacia de porteros, análisis por períodos, rendimiento por tipo de lanzamiento, asistencias y acciones defensivas.

La prioridad debe ser adaptar esas métricas a los datos que Handball Stats realmente puede capturar, manteniendo fórmulas transparentes y fáciles de interpretar.
