# Base científica de Balonmano Stats

## Objetivo

Esta documentación relaciona las métricas actuales de Balonmano Stats
con investigaciones científicas sobre análisis de rendimiento en
balonmano y propone una hoja de ruta para mejorar la definición de los
datos, las fórmulas y el modelo de eventos.

La revisión se centra especialmente en: - tiros y eficacia; - zonas de
lanzamiento; - porteros; - pérdidas y robos; - asistencias; - posesión y
ataques; - análisis por períodos; - rendimiento individual; - contexto
de 7 metros; - fiabilidad del registro.

## 1. Matriz de métricas

  -------------------------------------------------------------------------------------------------------
  Métrica        Definición            Fórmula / método                    Estado actual  Recomendación
  -------------- --------------------- ----------------------------------- -------------- ---------------
  Tiros          Eventos de            `count(lanzamientos)`               Implementado   Mantener
                 lanzamiento                                                              

  Goles          Lanzamientos con      `count(resultado=GOL)`              Implementado   Mantener
                 resultado GOL                                                            

  Eficiencia de  Goles respecto de     `goles / tiros × 100`               Implementado   Mantener
  tiro           tiros                                                                    

  Asistencias    Pase final que        `count(asistencias)`                Implementado   Definir con
                 conduce al gol, según                                                    precisión
                 criterio definido                                                        

  Pérdidas       Eventos de            `count(eventos)`                    Implementado   Mantener y
                 pérdida/error según                                                      documentar
                 reglas                                                                   

  Robos          Recuperaciones        `count(ROBO_BALON)`                 Implementado   Mantener
                 defensivas                                                               

  Paradas        Tiros con resultado   `count(resultado=PARADA)`           Implementado   Mantener
                 PARADA atribuidos al                                                     
                 portero                                                                  

  Eficacia de    Paradas sobre tiros   `paradas / tiros recibidos × 100`   Implementado   Mantener
  portero        recibidos                                                                

  Zonas de       Localización del tiro X/Y + zona                          Implementado   Mantener
  lanzamiento                                                                             

  Zona 3×3 de    Localización del      9 celdas                            Implementado   Mantener
  portería       destino del tiro                                                         

  Posesiones     Secuencias de control Derivación de eventos               Implementado   Formalizar
                 del balón                                                                definición

  Eficacia de    Goles por ataque      `goles / ataques × 100`             Pendiente      Alta prioridad
  ataque                                                                                  

  Pérdidas por   Pérdidas respecto de  `pérdidas / ataques × 100`          Pendiente      Alta prioridad
  ataque         ataques                                                                  

  Frecuencia de  Tiros respecto de     `tiros / ataques × 100`             Pendiente      Alta prioridad
  tiro           ataques                                                                  

  +/- real       Diferencia de goles   Requiere lineup                     Proxy actual   No llamarlo +/-
                 mientras el jugador                                                      real
                 está en cancha                                                           

  PlayerScore    Índice ponderado de   Algoritmo específico                Pendiente      Investigar
                 acciones                                                                 antes
                 positivas/negativas                                                      

  GKI            Índice propio         Pesos propios                       Implementado   Presentarlo
                 ponderado por                                                            como métrica
                 tipo/distancia                                                           propia

  7 m contextual Eficacia según tiempo `goles 7m / tiros 7m` + contexto    Parcial        Futura
                 y situación                                                              

  Rendimiento    Indicadores           Bloques temporales                  Parcial        Agregar
  por período    segmentados por                                                          
                 intervalos                                                               
  -------------------------------------------------------------------------------------------------------

## 2. Tiros y eficacia

La eficacia de tiro puede definirse como:

``` text
Eficacia de tiro = goles / tiros × 100
```

Balonmano Stats ya utiliza esta definición.

Ferrari et al. analizaron 55 partidos de Champions League masculina y 34
indicadores relacionados con el proceso ofensivo, incluyendo goles,
tiros, zonas y eficacia. La eficacia de lanzamiento fue uno de los
indicadores diferenciadores estudiados. [Ferrari et al.,
2020](https://www.frontiersin.org/journals/psychology/articles/10.3389/fpsyg.2020.547110/full)

**Recomendación:** mostrar también el volumen, por ejemplo
`5/9 — 55,6%`, y no solamente el porcentaje.

## 3. Lanzamientos por zona

Pueo et al. analizaron 6.568 lanzamientos del Campeonato Europeo
masculino de 2020, relacionando posición, zona de lanzamiento, velocidad
y eficacia. Encontraron diferencias de utilización y eficacia según
posiciones y zonas.

Fuente: [PubMed](https://pubmed.ncbi.nlm.nih.gov/37077783/)

Esto respalda que Balonmano Stats conserve: - X; - Y; - tipo de
lanzamiento; - zona 3×3; - resultado.

La estructura recomendada es:

``` text
jugador
  ↓
tipo de lanzamiento
  ↓
origen X/Y
  ↓
destino 3×3
  ↓
resultado
```

## 4. Porteros

Hansen et al. estudiaron 88 partidos del Mundial masculino de 2015, con
6.893 tiros y 2.088 paradas. La eficacia media de parada fue del 30% y
el estudio encontró una relación entre las estadísticas de los porteros
y la clasificación final.

Fuente: [PubMed](https://pubmed.ncbi.nlm.nih.gov/29472743/)

La fórmula:

``` text
Eficacia de portero =
paradas / tiros recibidos × 100
```

tiene un respaldo directo en este tipo de análisis.

Balonmano Stats debería conservar además: - paradas por tipo de
lanzamiento; - paradas por zona; - heatmap de portería.

## 5. Heatmap 3×3

Handball.ai utiliza una portería dividida en nueve ubicaciones para
estudiar los lanzamientos. Su documentación también contempla posiciones
de ejecución.

Fuente: [Handball.ai](https://handball.ai/wiki/)

La cuadrícula actual de Balonmano Stats:

``` text
TL  TC  TR
ML  MC  MR
BL  BC  BR
```

es adecuada como base de análisis.

## 6. Asistencias

El PlayerScore de Wagner et al. considera la asistencia una acción
positiva y define la asistencia como el último pase que precede al gol.

Fuente: [MDPI --- PlayerScore](https://www.mdpi.com/2076-3417/13/4/2327)

Balonmano Stats ya registra `ASISTENCIA`.

**Recomendación:** documentar exactamente qué considera asistencia el
sistema para reducir diferencias entre operadores.

## 7. Pérdidas y errores

Daza, Andrés y Tarragó analizaron 80 partidos del Mundial masculino de
Qatar 2015 y encontraron que una combinación de indicadores de ataque,
defensa y portero estaba asociada al resultado; entre ellos aparecían
faltas técnicas, robos, lanzamientos detenidos por el portero rival y
paradas del propio portero.

Fuente:
[RICYDE](https://www.cafyd.com/REVISTA/ojs/index.php/ricyde/article/view/1144)

Ferrari et al. también incluyen turnovers dentro del análisis ofensivo.

**Recomendación:** mantener separadas, cuando sea posible: - pérdidas de
balón; - dobles; - pasos; - faltas técnicas; - otras acciones que
terminan una posesión.

## 8. Posesión vs. ataque

Este es el principal punto conceptual que debería revisarse.

La investigación reciente sobre rendimiento por períodos utiliza
explícitamente: - ataques; - tiros; - pérdidas; - goles; - eficacia de
ataque; - eficacia de tiro.

Fuente: [ScienceDirect ---
2026](https://www.sciencedirect.com/science/article/pii/S3050544526000162)

El estudio analiza 290 partidos de tres Mundiales masculinos entre 2019
y 2023 y divide cada partido en seis bloques de 10 minutos.

Por ello conviene evolucionar el modelo hacia:

``` text
POSESIÓN
   ↓
ATAQUE
   ↓
ACCIÓN
   ↓
RESULTADO
```

No es necesario eliminar la posesión actual. La propuesta es distinguir
ambos conceptos.

## 9. Nuevas métricas recomendadas

### Eficacia de ataque

``` text
goles / ataques × 100
```

### Frecuencia de tiro

``` text
tiros / ataques × 100
```

### Tasa de pérdidas

``` text
pérdidas / ataques × 100
```

### Tasa de tiros fallados

``` text
fallos / tiros × 100
```

### Tasa de tiros detenidos

``` text
paradas / tiros × 100
```

Estas métricas deben implementarse después de formalizar qué es un
ataque.

## 10. Análisis por período

El estudio de 2026 muestra que el comportamiento ofensivo cambia según
el tramo del partido.

Una futura pantalla de estadísticas debería permitir:

``` text
0–10
10–20
20–30
30–40
40–50
50–60
```

y para cada bloque: - ataques; - tiros; - goles; - eficacia de tiro; -
eficacia de ataque; - pérdidas; - paradas.

También puede ofrecer: - primer tiempo; - segundo tiempo; - últimos 10
minutos; - últimos 5 minutos.

## 11. 7 metros y contexto

Gümüş et al. (2026) analizaron 38.480 eventos relacionados con 7 m de
2.978 partidos de las ligas danesas masculina y femenina entre 2017 y
2024. Estudiaron el momento del partido, diferencia de goles y
situaciones de presión.

Fuente: [Frontiers in
Psychology](https://www.frontiersin.org/journals/psychology/articles/10.3389/fpsyg.2026.1811808/full)

Para Balonmano Stats, un futuro análisis podría cruzar:

``` text
7M
+
minuto
+
período
+
diferencia de marcador
+
resultado
```

Por ejemplo: - 7 m con partido empatado; - 7 m con diferencia ≤2; - 7 m
en los últimos 5 minutos.

## 12. Rendimiento ofensivo

Ferrari et al. encontraron diferencias entre equipos ganadores y
perdedores en múltiples indicadores ofensivos, incluyendo asistencias,
goles de ataque posicional, goles de 6 m y eficacia de tiro.

Esto sugiere que Balonmano Stats debería permitir cruzar:

``` text
fase del juego
+
tipo de lanzamiento
+
zona
+
resultado
```

Ejemplo:

``` text
ATAQUE POSICIONAL
Tiros: 31
Goles: 18
Eficacia: 58,1%

CONTRAATAQUE
Tiros: 8
Goles: 7
Eficacia: 87,5%
```

## 13. PlayerScore

Wagner et al. desarrollaron y validaron PlayerScore para evaluar el
rendimiento individual. El estudio obtuvo una alta fiabilidad
intraobservador (ICC = 0,97 en los partidos repetidos analizados).

Fuente: [MDPI --- PlayerScore](https://www.mdpi.com/2076-3417/13/4/2327)

El método utiliza acciones positivas y negativas, entre ellas: - gol; -
asistencia; - robo; - bloqueo; - penal recibido; - lanzamiento
fallado; - error técnico; - pérdida; - exclusión; - tarjeta roja.

**Recomendación:** no copiar directamente sus pesos. Si Balonmano Stats
quiere un índice propio, debería desarrollar y documentar una
metodología propia.

Posible nombre:

``` text
Balonmano Stats Performance Index
```

## 14. +/- real

El +/- real requiere conocer: - quién está en cancha; - cuándo entra; -
cuándo sale; - qué goles se producen durante ese intervalo.

Por eso el indicador actual de Balonmano Stats debe seguir identificado
como:

``` text
Proxy de +/-
```

hasta implementar seguimiento de alineación.

## 15. GKI

Actualmente la aplicación usa pesos propios por tipo/distancia:

``` text
6M            × 1.0
CONTRAATAQUE  × 0.9
7M            × 0.85
9M            × 0.6
OTRO          × 0.5
```

En esta revisión no se identificó evidencia académica que valide
específicamente esta fórmula y estos pesos.

Por eso debe presentarse como:

> **GKI --- índice propio de Balonmano Stats**

y no como una estadística estándar del balonmano.

La recomendación es mostrar GKI junto a la eficacia tradicional de
portero.

## 16. Fase de juego y posición

Handball.ai incorpora variables como fases del juego y posiciones de
ejecución.

Fuente: [Handball.ai ---
investigación](https://www.mdpi.com/1424-8220/23/15/6714)

Una ampliación futura podría incorporar:

``` text
ATAQUE_POSICIONAL
CONTRAATAQUE
FAST_BREAK
```

y:

``` text
EXTREMO_IZQ
LATERAL_IZQ
CENTRAL
LATERAL_DER
EXTREMO_DER
PIVOTE
PORTERO
```

## 17. Situación numérica

Una futura dimensión contextual podría registrar:

``` text
6v6
7v6
6v5
5v6
5v5
```

Esto permitiría analizar el rendimiento en superioridad e inferioridad.

No debería implementarse antes de que el sistema de captura pueda
hacerlo sin aumentar demasiado la carga del operador.

## 18. Fiabilidad del registro

El estudio de Handball.ai validó un instrumento mediante expertos y
observadores y obtuvo buenos niveles de concordancia y fiabilidad intra
e interobservador.

Fuente: [MDPI ---
Handball.ai](https://www.mdpi.com/1424-8220/23/15/6714)

Esto tiene una consecuencia importante:

> no basta con que el software calcule correctamente; distintos
> operadores deberían poder registrar el mismo partido de forma
> consistente.

Futura prueba:

``` text
Operador A ──┐
             ├── mismo partido
Operador B ──┘
```

Comparar: - goles; - tiros; - paradas; - pérdidas; - asistencias; -
zonas; - sanciones.

Podrían utilizarse: - porcentaje de coincidencia; - Cohen's kappa; - ICC
cuando corresponda.

## 19. Arquitectura conceptual recomendada

``` text
PARTIDO
   │
   ├── PERÍODO
   │
   ├── POSESIÓN
   │      │
   │      └── ATAQUE
   │             │
   │             ├── jugador
   │             ├── acción
   │             ├── fase
   │             ├── posición
   │             ├── lanzamiento
   │             ├── zona
   │             └── resultado
   │
   └── CONTEXTO
          ├── marcador
          ├── diferencia
          ├── tiempo
          ├── superioridad/inferioridad
          └── período
```

No es necesario implementar todo inmediatamente. Esta estructura sirve
como dirección de evolución.

## 20. Roadmap científico

### Versión 1 --- Consolidación

Mantener: - goles; - tiros; - eficiencia; - asistencias; - pérdidas; -
robos; - bloqueos; - paradas; - eficacia de portero; - zonas; -
heatmap; - sanciones.

Revisar: - definición de posesión; - definición de pérdida; - definición
de asistencia; - atribución de paradas; - denominadores.

### Versión 2 --- Ataques

Agregar: - ataque; - eficacia de ataque; - tiros por ataque; - pérdidas
por ataque.

### Versión 3 --- Contexto

Agregar: - fase de juego; - posición; - situación numérica; - diferencia
de marcador; - análisis por períodos.

### Versión 4 --- Rendimiento individual

Investigar: - PlayerScore; - índice propio; - rendimiento por minuto; -
rendimiento por posición.

### Versión 5 --- Análisis avanzado

Agregar: - 7 m contextual; - secuencias; - comparación de períodos; -
tendencias; - video sincronizado.

### Versión 6 --- IA / ML

Cuando exista una base histórica grande:

``` text
miles de partidos
       ↓
base histórica
       ↓
machine learning
       ↓
modelos explicables
       ↓
análisis avanzado
```

La IA debería ser consecuencia de tener datos bien estructurados, no un
sustituto de una buena estructura de eventos.

## 21. Métricas recomendadas para /stats

### Equipo

-   Goles
-   Tiros
-   Eficacia de tiro
-   Ataques
-   Eficacia de ataque
-   Pérdidas
-   Pérdidas por ataque
-   Asistencias
-   Robos
-   Bloqueos

### Lanzamiento

-   6M
-   9M
-   7M
-   Contraataque
-   Poste
-   Bloqueado
-   Fallo
-   Parada

### Porteros

-   Paradas
-   Tiros recibidos
-   Eficacia
-   Paradas 6M
-   Paradas 9M
-   Paradas 7M
-   Paradas contraataque
-   Mapa de zonas

### Contexto

-   1T / 2T
-   0--10
-   10--20
-   20--30
-   30--40
-   40--50
-   50--60

## 22. Métricas que deben permanecer fuera del centro de captura

La pantalla de captura debe priorizar:

``` text
Jugador
↓
Acción
↓
Resultado
```

Las métricas avanzadas deben estar principalmente en `/stats` o en un
dashboard live.

## 23. Criterio para agregar nuevas métricas

Antes de implementar una métrica, comprobar:

1.  ¿Tiene una definición clara?
2.  ¿Puede calcularse de forma reproducible?
3.  ¿Puede capturarse sin ralentizar el partido?
4.  ¿Tiene utilidad práctica?
5.  ¿Existe evidencia científica?
6.  ¿La fórmula está validada?
7.  ¿Necesita nuevos eventos?

Si una métrica falla varias de estas condiciones, debería quedar fuera
del MVP.

## 24. Prioridades

  Mejora                     Prioridad
  ----------------------- ------------
  Formalizar posesión         Muy alta
  Introducir ataque           Muy alta
  Eficacia de ataque              Alta
  Pérdidas por ataque             Alta
  Tiros por ataque                Alta
  Análisis por períodos           Alta
  Posición del lanzador     Media-alta
  Fase del juego            Media-alta
  Situación numérica             Media
  Contexto de 7 m                Media
  PlayerScore                    Media
  +/- real                       Media
  GKI validado              Media-baja
  Video                         Futura
  IA/ML                         Futura

# 25. Bibliografía científica principal

### Marquina et al. (2023)

**Development and Validation of an Observational Game Analysis Tool with
Artificial Intelligence for Handball: Handball.ai.**

Sensors, 23(15), 6714. DOI: `10.3390/s23156714`

https://www.mdpi.com/1424-8220/23/15/6714

### Wagner et al. (2023)

**The PlayerScore: A Systematic Game Observation Tool to Determine
Individual Player Performance in Team Handball Competition.**

Applied Sciences, 13(4), 2327. DOI: `10.3390/app13042327`

https://www.mdpi.com/2076-3417/13/4/2327

### Ferrari et al. (2020)

**Comparative Analysis of the Offensive Effectiveness in Winner and
Losing Handball Teams.**

Frontiers in Psychology, 11, 547110. DOI: `10.3389/fpsyg.2020.547110`

https://www.frontiersin.org/journals/psychology/articles/10.3389/fpsyg.2020.547110/full

### Daza, Andrés & Tarragó (2017)

**Match Statistics as Predictors of Team's Performance in Elite
Competitive Handball.**

RICYDE, 13(48), 149--161. DOI: `10.5232/ricyde2017.04805`

https://www.cafyd.com/REVISTA/ojs/index.php/ricyde/article/view/1144

### Hansen et al. (2017)

**Performance analysis of male handball goalkeepers at the World
Handball Championship 2015.**

Biology of Sport, 34(4), 393--400. DOI: `10.5114/biolsport.2017.69828`

https://pubmed.ncbi.nlm.nih.gov/29472743/

### Pueo et al. (2023)

**On-court throwing activity of male handball players during the
European Championship 2020.**

Biology of Sport, 40(2), 531--541. DOI: `10.5114/biolsport.2023.116451`

https://pubmed.ncbi.nlm.nih.gov/37077783/

### Analysis of game performance by game period in men's elite handball (2026)

Intelligent Sports and Health, 2(2), 129--137. DOI:
`10.1016/j.ish.2026.04.001`

https://www.sciencedirect.com/science/article/pii/S3050544526000162

### Gümüş et al. (2026)

**Temporal and situational analysis of 7-m shots in elite handball: a
multi-season study.**

Frontiers in Psychology, 17, 1811808. DOI: `10.3389/fpsyg.2026.1811808`

https://www.frontiersin.org/journals/psychology/articles/10.3389/fpsyg.2026.1811808/full

### Krawczyk et al. (2024)

**Differences in performance analysis between won and lost teams in the
top handball matches in the seasons before, during, and after the
COVID-19 pandemic.**

The Journal of Sports Medicine and Physical Fitness, 64(12), 1267--1277.
DOI: `10.23736/S0022-4707.24.15981-6`

https://pubmed.ncbi.nlm.nih.gov/39264223/

# 26. Decisión técnica principal

La conclusión más importante de esta revisión es:

> **Balonmano Stats debería formalizar la diferencia entre POSESIÓN y
> ATAQUE antes de seguir agregando una gran cantidad de métricas.**

La evolución recomendada es:

``` text
EVENTOS
   ↓
POSESIONES
   ↓
ATAQUES
   ↓
ACCIONES
   ↓
RESULTADOS
   ↓
INDICADORES
   ↓
ANÁLISIS CONTEXTUAL
   ↓
RENDIMIENTO INDIVIDUAL Y COLECTIVO
```

Esto permitiría pasar de una aplicación de recolección de estadísticas a
un sistema de análisis de rendimiento basado en eventos, manteniendo la
captura rápida durante el partido.
