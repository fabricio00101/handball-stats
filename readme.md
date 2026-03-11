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
