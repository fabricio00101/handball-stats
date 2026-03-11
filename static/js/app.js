document.addEventListener('DOMContentLoaded', () => {
    // ESTADO DE LA APLICACIÓN
    const state = {
        selectedPlayerId: null,
        selectedTeam: null,
        matchId: document.getElementById('match-id').value,
        pendingAction: null,
        coordenada_x: null,
        coordenada_y: null,
        zona_porteria: null,
        posession: 'A'
    };
    
    const exclusions = {}; // Para timers de 2 min

    // REFERENCIAS UI
    const playerItems = document.querySelectorAll('.player-item');
    const actionFeedback = document.getElementById('action-feedback');
    const actionsContainer = document.getElementById('actions-container');
    const actionBtns = document.querySelectorAll('.action-btn');
    const toast = document.getElementById('toast');
    
    const outcomeModal = document.getElementById('outcome-modal');
    const outcomeBtns = document.querySelectorAll('.outcome-btn');
    const cancelOutcomeBtn = document.getElementById('cancel-outcome');

    const scoreAEl = document.getElementById('score-a');
    const scoreBEl = document.getElementById('score-b');
    
    const courtMap = document.getElementById('court-map');
    const goalZones = document.querySelectorAll('.goal-zone');
    const markerCourt = document.getElementById('shot-marker-court');
    
    // Inicializar posesión
    function updatePossession(team) {
        state.posession = team;
        document.getElementById('possession-a').classList.toggle('hidden', team !== 'A');
        document.getElementById('possession-b').classList.toggle('hidden', team !== 'B');
    }
    updatePossession(state.posession);

    // 1. SELECCIÓN DE JUGADOR
    playerItems.forEach(item => {
        item.addEventListener('click', (e) => {
            // Deseleccionar todos
            playerItems.forEach(p => p.classList.remove('active'));
            
            // Seleccionar el actual
            const clickedItem = e.currentTarget;
            clickedItem.classList.add('active');
            
            // Actualizar estado
            state.selectedPlayerId = clickedItem.dataset.id;
            state.selectedTeam = clickedItem.dataset.team;
            
            // Habilitar panel de acciones
            const playerName = clickedItem.querySelector('.player-name').textContent;
            actionFeedback.innerHTML = `Jugador seleccionado: <strong>${playerName}</strong>. Elige una acción.`;
            actionFeedback.style.borderColor = state.selectedTeam === 'A' ? 'var(--team-a-color)' : 'var(--team-b-color)';
            actionsContainer.classList.remove('disabled');
        });
    });

    // 2. CAPTURA DE EVENTOS (ACCIONES)
    actionBtns.forEach(btn => {
        btn.addEventListener('click', (e) => {
            if (!state.selectedPlayerId) return;

            const eventType = e.currentTarget.dataset.eventType;
            const requiresOutcome = e.currentTarget.dataset.requiresOutcome === 'true';

            if (eventType === 'LANZAMIENTO_7M' && !confirm('Aviso de Validación: ¿Estás seguro de registrar un 7m? (Generalmente requiere una falta previa)')) {
                return;
            }

            if (requiresOutcome) {
                // Reset tracker modal states
                state.coordenada_x = null;
                state.coordenada_y = null;
                state.zona_porteria = null;
                markerCourt.classList.add('hidden');
                goalZones.forEach(z => z.classList.remove('selected'));
                
                state.pendingAction = eventType;
                outcomeModal.classList.remove('hidden');
            } else {
                sendEvent(eventType, null);
            }
        });
    });

    // 2.5 TRACKER INTERACTIVO (PISTA Y PORTERÍA)
    courtMap.addEventListener('click', (e) => {
        const rect = courtMap.getBoundingClientRect();
        state.coordenada_x = parseFloat(((e.clientX - rect.left) / rect.width).toFixed(4));
        state.coordenada_y = parseFloat(((e.clientY - rect.top) / rect.height).toFixed(4));
        
        markerCourt.style.left = `${state.coordenada_x * 100}%`;
        markerCourt.style.top = `${state.coordenada_y * 100}%`;
        markerCourt.classList.remove('hidden');
    });

    goalZones.forEach(zone => {
        zone.addEventListener('click', (e) => {
            goalZones.forEach(z => z.classList.remove('selected'));
            e.currentTarget.classList.add('selected');
            state.zona_porteria = e.currentTarget.dataset.zone;
        });
    });

    // 3. MANEJO DEL MODAL DE RESULTADO
    outcomeBtns.forEach(btn => {
        btn.addEventListener('click', (e) => {
            const outcome = e.currentTarget.dataset.outcome;
            sendEvent(state.pendingAction, outcome);
            closeModal();
        });
    });

    cancelOutcomeBtn.addEventListener('click', () => {
        state.pendingAction = null;
        closeModal();
    });

    function closeModal() {
        outcomeModal.classList.add('hidden');
        state.pendingAction = null;
    }

    // 4. ALMACENAMIENTO Y SINCRONIZACIÓN (Offline First)
    function saveEventToQueue(eventData) {
        eventData.id_local = Date.now().toString(); 
        const queue = JSON.parse(localStorage.getItem('eventosBalonmano') || '[]');
        queue.push(eventData);
        localStorage.setItem('eventosBalonmano', JSON.stringify(queue));
        
        // --- 4.1 LÓGICA DE NEGOCIO EN TIEMPO REAL --- //
        const currentTeam = state.selectedTeam;
        const otherTeam = currentTeam === 'A' ? 'B' : 'A';
        
        // Actualizar Marcador
        if (eventData.resultado === 'GOL') {
            if (currentTeam === 'A') scoreAEl.textContent = parseInt(scoreAEl.textContent) + 1;
            else if (currentTeam === 'B') scoreBEl.textContent = parseInt(scoreBEl.textContent) + 1;
        }

        // Cambio Inteligente de Posesión
        if (eventData.resultado === 'GOL' || eventData.tipo_evento === 'PERDIDA_BALON' || eventData.resultado === 'PARADA') {
            updatePossession(otherTeam);
        } else if (eventData.tipo_evento === 'PARADA' || eventData.tipo_evento === 'ROBO_BALON') {
            updatePossession(currentTeam);
        }

        // Cronómetro Exclusión
        if (eventData.tipo_evento === 'EXCLUSION_2MIN') {
            startExclusionTimer(eventData.id_jugador);
        }
        
        showToast(`Registrado: ${eventData.tipo_evento.replace('_', ' ')}`);
        resetSelection();
        syncQueue();
    }

    function startExclusionTimer(playerId) {
        if (exclusions[playerId]) clearInterval(exclusions[playerId].interval);
        
        let remaining = 120;
        const playerItem = document.querySelector(`.player-item[data-id="${playerId}"]`);
        if (!playerItem) return;
        
        const exclSpan = playerItem.querySelector('.player-excl');
        exclSpan.classList.remove('hidden');
        exclSpan.textContent = '2:00';
        
        exclusions[playerId] = {
            interval: setInterval(() => {
                remaining--;
                if (remaining <= 0) {
                    clearInterval(exclusions[playerId].interval);
                    delete exclusions[playerId];
                    exclSpan.classList.add('hidden');
                } else {
                    const m = Math.floor(remaining / 60);
                    const s = remaining % 60;
                    exclSpan.textContent = `${m}:${s.toString().padStart(2, '0')}`;
                }
            }, 1000)
        };
    }

    async function syncQueue() {
        let queue = JSON.parse(localStorage.getItem('eventosBalonmano') || '[]');
        if (queue.length === 0) return;

        const eventData = queue[0];

        try {
            const response = await fetch('/api/event', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(eventData)
            });

            if (!response.ok) throw new Error('Error al enviar al servidor');

            // Evento enviado correctamente, lo sacamos de la cola
            queue = JSON.parse(localStorage.getItem('eventosBalonmano') || '[]');
            queue.shift();
            localStorage.setItem('eventosBalonmano', JSON.stringify(queue));
            
            console.log('Sincronizado:', eventData.tipo_evento);
            
            // Seguir sincronizando si hay más
            if (queue.length > 0) {
                syncQueue();
            }
        } catch (error) {
            console.warn('Sin conexión. Sincronización pausada.', error);
            showToast('Offline: Guardado localmente', true);
        }
    }

    // Intentar sincronizar al recuperar la conexión
    window.addEventListener('online', syncQueue);
    // Intentar sincronizar al arrancar la página por si quedaron eventos
    syncQueue();

    // 5. MANEJO DE ENVÍO DE EVENTO
    function sendEvent(eventType, outcome) {
        // Empaquetar datos incluyendo coordenadas si las hay
        const eventData = {
            id_partido: parseInt(state.matchId),
            id_jugador: parseInt(state.selectedPlayerId),
            tipo_evento: eventType,
            resultado: outcome,
            tiempo_juego: TimerModule.getCurrentTime(),
            periodo: 1, 
            coordenada_x: state.coordenada_x, 
            coordenada_y: state.coordenada_y,
            zona_porteria: state.zona_porteria
        };

        if ((eventType.includes('LANZAMIENTO_') || eventType === 'CONTRAATAQUE') && state.coordenada_x === null) {
            if (!confirm('No has marcado el origen del tiro en la pista. ¿Guardar de todos modos?')) return;
        }

        saveEventToQueue(eventData);
    }

    function resetSelection() {
        playerItems.forEach(p => p.classList.remove('active'));
        state.selectedPlayerId = null;
        state.selectedTeam = null;
        actionFeedback.innerHTML = 'Selecciona un jugador para continuar...';
        actionFeedback.style.borderColor = 'var(--bg-card-hover)';
        actionsContainer.classList.add('disabled');
    }

    function showToast(message, isError = false) {
        toast.textContent = message;
        toast.style.backgroundColor = isError ? 'var(--warning)' : 'var(--success)';
        toast.classList.remove('hidden');
        
        setTimeout(() => {
            toast.classList.add('hidden');
        }, 3000);
    }

    // 6. MÓDULO DE EXPORTACIÓN Y REPORTES BIG DATA
    const btnExport = document.getElementById('btn-export-json');
    const btnStats = document.getElementById('btn-view-stats');

    if (btnExport) {
        btnExport.addEventListener('click', async () => {
            try {
                // Ensure everything is synced before export
                await syncQueue();
                const resp = await fetch(`/api/matches/${state.matchId}/export`);
                if (!resp.ok) throw new Error('Error al generar JSON');
                const data = await resp.json();
                
                const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `registro_partido_${state.matchId}.json`;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                URL.revokeObjectURL(url);
                showToast('Archivo JSON descargado correctamente');
            } catch(e) {
                console.error(e);
                showToast('Error al exportar, intenta de nuevo', true);
            }
        });
    }

    if (btnStats) {
        btnStats.addEventListener('click', async () => {
            try {
                await syncQueue();
                const resp = await fetch(`/api/stats/${state.matchId}`);
                if (!resp.ok) throw new Error('Error al calcular stats');
                const data = await resp.json();
                console.table(data);
                alert('Métricas calculadas exitosamente.\n\nSe han impreso en formato tabla en la consola del navegador (F12) para que puedas ver el GKI, Eficiencia de tiro, y aportaciones por jugador.');
            } catch(e) {
                console.error(e);
                showToast('Error al cargar analíticas', true);
            }
        });
    }
});
