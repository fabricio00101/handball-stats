document.addEventListener('DOMContentLoaded', () => {
    // ESTADO DE LA APLICACIÓN
    const state = {
        selectedPlayerId: null,
        selectedTeam: null,
        matchId: document.getElementById('match-id') ? document.getElementById('match-id').value : 1,
        pendingAction: null,
        coordenada_x: null,
        coordenada_y: null,
        zona_porteria: null,
        posession: 'A'
    };
    
    const exclusions = {}; // Timers de 2 min

    // REFERENCIAS UI
    const playerItems = document.querySelectorAll('.player-item');
    const actionFeedback = document.getElementById('action-feedback');
    const actionsContainer = document.getElementById('actions-container');
    const actionBtns = document.querySelectorAll('.action-btn');
    const toast = document.getElementById('toast');
    const lockPlayerToggle = document.getElementById('lock-player-toggle');
    
    const outcomeModal = document.getElementById('outcome-modal');
    const outcomeBtns = document.querySelectorAll('.outcome-btn');
    const cancelOutcomeBtn = document.getElementById('cancel-outcome');

    const scoreAEl = document.getElementById('score-a');
    const scoreBEl = document.getElementById('score-b');
    
    const courtMap = document.getElementById('court-map');
    const goalZones = document.querySelectorAll('.goal-zone');
    const markerCourt = document.getElementById('shot-marker-court');

    // Inicializar posesión y estado desde el servidor al cargar (Event Sourcing - BUG-4)
    async function loadMatchState() {
        if (!state.matchId) return;
        try {
            const resp = await fetch(`/api/matches/${state.matchId}/state`);
            if (resp.ok) {
                const data = await resp.json();
                scoreAEl.textContent = data.marcador_a || 0;
                scoreBEl.textContent = data.marcador_b || 0;
                updatePossession(data.posesion_actual || 'A');

                if (typeof TimerModule !== 'undefined' && data.segundos_jugados !== undefined) {
                    TimerModule.setSeconds(data.segundos_jugados);
                }

                // Restaurar exclusiones activas (BUG-5)
                (data.exclusiones_activas || []).forEach(ex => {
                    startExclusionTimer(ex.id_jugador, ex.segundos_restantes);
                });
            }
        } catch (e) {
            console.warn('Error al cargar estado del partido:', e);
        }
    }
    
    // Inicializar posesión visual
    function updatePossession(team) {
        state.posession = team;
        const posA = document.getElementById('possession-a');
        const posB = document.getElementById('possession-b');
        if (posA) posA.classList.toggle('hidden', team !== 'A');
        if (posB) posB.classList.toggle('hidden', team !== 'B');
    }

    // Lógica correcta de posesión (BUG-2)
    function actualizarPosesionInteligente(equipoLanzador, evento) {
        const rival = equipoLanzador === 'A' ? 'B' : 'A';
        const res = evento.resultado;
        const tipo = evento.tipo_evento;

        if (res === 'GOL' || ['PERDIDA_BALON', 'FALTA_TECNICA', 'DOBLE', 'PASOS'].includes(tipo)) {
            updatePossession(rival);
        } else if (res === 'PARADA' || ['PARADA_PORTERO', 'ROBO_BALON', 'BLOQUEO'].includes(tipo)) {
            updatePossession(equipoLanzador);
        }
    }

    // 1. SELECCIÓN DE JUGADOR
    playerItems.forEach(item => {
        item.addEventListener('click', (e) => {
            const clickedItem = e.currentTarget;
            if (clickedItem.classList.contains('disabled')) return; // Jugador en banquillo por exclusión

            playerItems.forEach(p => p.classList.remove('active'));
            clickedItem.classList.add('active');
            
            state.selectedPlayerId = clickedItem.dataset.id;
            state.selectedTeam = clickedItem.dataset.team;
            
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
                state.coordenada_x = null;
                state.coordenada_y = null;
                state.zona_porteria = null;
                if (markerCourt) markerCourt.classList.add('hidden');
                goalZones.forEach(z => z.classList.remove('selected'));
                
                state.pendingAction = eventType;
                outcomeModal.classList.remove('hidden');
            } else {
                sendEvent(eventType, null);
            }
        });
    });

    // 2.5 TRACKER INTERACTIVO
    if (courtMap) {
        courtMap.addEventListener('click', (e) => {
            const rect = courtMap.getBoundingClientRect();
            state.coordenada_x = parseFloat(((e.clientX - rect.left) / rect.width).toFixed(4));
            state.coordenada_y = parseFloat(((e.clientY - rect.top) / rect.height).toFixed(4));
            
            if (markerCourt) {
                markerCourt.style.left = `${state.coordenada_x * 100}%`;
                markerCourt.style.top = `${state.coordenada_y * 100}%`;
                markerCourt.classList.remove('hidden');
            }
        });
    }

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

    if (cancelOutcomeBtn) {
        cancelOutcomeBtn.addEventListener('click', () => {
            state.pendingAction = null;
            closeModal();
        });
    }

    function closeModal() {
        if (outcomeModal) outcomeModal.classList.add('hidden');
        state.pendingAction = null;
    }

    // 4. ALMACENAMIENTO Y SINCRONIZACIÓN OFFLINE
    function saveEventToQueue(eventData) {
        // Guardar mediante módulo resiliente (Fase 2)
        OfflineQueue.enqueue(state.matchId, eventData);
        
        // --- 4.1 LÓGICA EN TIEMPO REAL --- //
        const currentTeam = state.selectedTeam;
        
        // Marcador
        if (eventData.resultado === 'GOL') {
            if (currentTeam === 'A') scoreAEl.textContent = parseInt(scoreAEl.textContent) + 1;
            else if (currentTeam === 'B') scoreBEl.textContent = parseInt(scoreBEl.textContent) + 1;
        }

        // Posesión corregida
        actualizarPosesionInteligente(currentTeam, eventData);

        // Exclusión
        if (eventData.tipo_evento === 'EXCLUSION_2MIN') {
            startExclusionTimer(eventData.id_jugador, 120);
        }
        
        showToast(`Registrado: ${eventData.tipo_evento.replace('_', ' ')}`);
        resetSelection();
    }

    // Exclusión con bloqueo de jugador (BUG-5)
    function startExclusionTimer(playerId, durationSeconds = 120) {
        if (exclusions[playerId]) clearInterval(exclusions[playerId].interval);
        
        let remaining = durationSeconds;
        const playerItem = document.querySelector(`.player-item[data-id="${playerId}"]`);
        if (!playerItem) return;
        
        playerItem.classList.add('disabled'); // Deshabilitar selección mientras esté excluido
        const exclSpan = playerItem.querySelector('.player-excl');
        if (exclSpan) {
            exclSpan.classList.remove('hidden');
            const m = Math.floor(remaining / 60);
            const s = remaining % 60;
            exclSpan.textContent = `${m}:${s.toString().padStart(2, '0')}`;
        }
        
        exclusions[playerId] = {
            interval: setInterval(() => {
                remaining--;
                if (remaining <= 0) {
                    clearInterval(exclusions[playerId].interval);
                    delete exclusions[playerId];
                    playerItem.classList.remove('disabled');
                    if (exclSpan) exclSpan.classList.add('hidden');
                } else if (exclSpan) {
                    const m = Math.floor(remaining / 60);
                    const s = remaining % 60;
                    exclSpan.textContent = `${m}:${s.toString().padStart(2, '0')}`;
                }
            }, 1000)
        };
    }

    // 5. MANEJO DE ENVÍO DE EVENTO
    function sendEvent(eventType, outcome) {
        const eventData = {
            id_partido: parseInt(state.matchId),
            id_jugador: parseInt(state.selectedPlayerId),
            tipo_evento: eventType,
            resultado: outcome,
            tiempo_juego: TimerModule ? TimerModule.getCurrentTime() : '00:00',
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
        // BUG-16 / Modo Fijar Jugador (<3 clics por acción)
        if (lockPlayerToggle && lockPlayerToggle.checked && state.selectedPlayerId) {
            // Mantener jugador activo para encadenar tiro/asistencia
            return;
        }

        playerItems.forEach(p => p.classList.remove('active'));
        state.selectedPlayerId = null;
        state.selectedTeam = null;
        actionFeedback.innerHTML = 'Selecciona un jugador para continuar...';
        actionFeedback.style.borderColor = 'var(--bg-card-hover)';
        actionsContainer.classList.add('disabled');
    }

    function showToast(message, isError = false) {
        if (!toast) return;
        toast.textContent = message;
        toast.style.backgroundColor = isError ? 'var(--warning)' : 'var(--success)';
        toast.classList.remove('hidden');
        
        setTimeout(() => {
            toast.classList.add('hidden');
        }, 3000);
    }

    // Eventos de sincronización offline
    window.addEventListener('online', () => OfflineQueue.sync(state.matchId));
    OfflineQueue.sync(state.matchId);
    loadMatchState();

    // Exportación JSON
    const btnExport = document.getElementById('btn-export-json');
    if (btnExport) {
        btnExport.addEventListener('click', async () => {
            try {
                await OfflineQueue.sync(state.matchId);
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
});
