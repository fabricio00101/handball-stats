/**
 * Módulo de cola offline resiliente para eventos de balonmano.
 * Garantiza idempotencia (client_event_id), envío en lotes y manejo
 * de eventos inválidos sin bloquear la captura en vivo.
 */
const OfflineQueue = (() => {
    let isSyncing = false;
    let retryDelay = 1000;

    function getQueueKey(matchId) {
        return `eventosBalonmano:${matchId}`;
    }

    function getFailedKey(matchId) {
        return `eventosBalonmanoFallidos:${matchId}`;
    }

    function getQueue(matchId) {
        try {
            return JSON.parse(localStorage.getItem(getQueueKey(matchId)) || '[]');
        } catch (e) {
            console.error('Error al leer cola local:', e);
            return [];
        }
    }

    function saveQueue(matchId, queue) {
        localStorage.setItem(getQueueKey(matchId), JSON.stringify(queue));
    }

    function enqueue(matchId, eventData) {
        if (!eventData.client_event_id) {
            eventData.client_event_id = (typeof crypto !== 'undefined' && crypto.randomUUID)
                ? crypto.randomUUID()
                : Date.now().toString() + '-' + Math.random().toString(36).substr(2, 9);
        }
        
        const queue = getQueue(matchId);
        queue.push(eventData);
        saveQueue(matchId, queue);
        
        // Intentar sincronizar en segundo plano sin bloquear
        setTimeout(() => sync(matchId), 50);
        return eventData;
    }

    async function sync(matchId) {
        if (isSyncing) return;
        const queue = getQueue(matchId);
        if (queue.length === 0) return;

        isSyncing = true;
        const batchSize = 50;
        const batch = queue.slice(0, batchSize);

        try {
            const response = await fetch('/api/events', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ events: batch })
            });

            if (response.ok) {
                const data = await response.json();
                const guardadosSet = new Set(data.guardados || []);
                const rechazadosMap = new Map();
                
                (data.rechazados || []).forEach(r => {
                    rechazadosMap.set(r.client_event_id, r.error);
                });

                // Si hay rechazados (4xx de negocio), moverlos a la cola de fallidos
                if (data.rechazados && data.rechazados.length > 0) {
                    const failedQueue = JSON.parse(localStorage.getItem(getFailedKey(matchId)) || '[]');
                    batch.forEach(item => {
                        if (rechazadosMap.has(item.client_event_id)) {
                            failedQueue.push({
                                event: item,
                                error: rechazadosMap.get(item.client_event_id),
                                fecha: new Date().toISOString()
                            });
                        }
                    });
                    localStorage.setItem(getFailedKey(matchId), JSON.stringify(failedQueue));
                }

                // Filtrar de la cola los procesados (guardados o rechazados definitivamente)
                const procesadosIds = new Set([...guardadosSet, ...rechazadosMap.keys()]);
                const remainingQueue = getQueue(matchId).filter(ev => !procesadosIds.has(ev.client_event_id));
                saveQueue(matchId, remainingQueue);

                retryDelay = 1000; // Reset backoff tras éxito
                isSyncing = false;

                // Si aún quedan elementos en la cola, continuar procesando
                if (remainingQueue.length > 0) {
                    setTimeout(() => sync(matchId), 100);
                }
            } else {
                // Error de servidor (5xx): aplicar backoff exponencial
                isSyncing = false;
                scheduleRetry(matchId);
            }
        } catch (error) {
            // Error de red: aplicar backoff exponencial
            isSyncing = false;
            scheduleRetry(matchId);
        }
    }

    function scheduleRetry(matchId) {
        setTimeout(() => sync(matchId), retryDelay);
        retryDelay = Math.min(retryDelay * 2, 30000); // Máx 30 segundos
    }

    return {
        enqueue,
        sync,
        getQueue
    };
})();
