document.addEventListener('DOMContentLoaded', () => {
    // Handshake anti-caché: si este HTML no es de la misma versión que el
    // servidor (página vieja cacheada + JS nuevo), purga todo y recarga una
    // vez. Solo actúa online (si /api/version responde) y nunca bloquea.
    (function versionHandshake() {
        try {
            const htmlVer = window.APP_VERSION || 'desconocida';
            if (sessionStorage.getItem('bm-version-fix') === htmlVer) return;
            fetch('/api/version', { cache: 'no-store' }).then(r => {
                if (!r.ok) throw new Error('sin version');
                return r.json();
            }).then(d => {
                if (d.version && d.version !== htmlVer && 'caches' in window) {
                    sessionStorage.setItem('bm-version-fix', htmlVer);
                    caches.keys()
                        .then(keys => Promise.all(keys.map(k => caches.delete(k))))
                        .then(() => window.location.reload());
                }
            }).catch(() => { /* offline: no se puede autoreparar, se sigue */ });
        } catch (e) { /* nunca bloquear la captura */ }
    })();

    // ESTADO DE LA APLICACIÓN
    const state = {
        selectedPlayerId: null,
        selectedTeam: null,
        matchId: document.getElementById('match-id') ? document.getElementById('match-id').value : 1,
        pendingAction: null,
        coordenada_x: null,
        coordenada_y: null,
        zona_porteria: null,
        posesion: 'A',
        activeKeeper: { A: null, B: null },
        // Modo tiro rival: el seleccionado es tu arquero → te están atacando.
        // Los tiros se registran al rival genérico con tu arquero como id_portero.
        tiroRival: false,
        rivalGenericoId: document.getElementById('generic-rival-id') ? document.getElementById('generic-rival-id').value : null
    };
    
    const exclusions = {}; // Timers de 2 min
    const expulsados = {}; // Roja directa o 3ª exclusión: id -> 'manual' | 'auto'

    // Historial de sesión para DESHACER (el servidor es la verdad ante F5)
    const history = [];

    // REFERENCIAS UI
    // Solo queda la plantilla propia (.player-card).
    const PLAYER_SELECTOR = '.player-card';
    const playerItems = document.querySelectorAll(PLAYER_SELECTOR);
    const actionFeedback = document.getElementById('action-feedback');
    const actionFeedbackText = document.getElementById('action-feedback-text');
    const actionsContainer = document.getElementById('actions-container');
    const actionBtns = document.querySelectorAll('.action-btn');
    const toast = document.getElementById('toast');
    const lockPlayerToggle = document.getElementById('lock-player-toggle');
    
    const outcomeModal = document.getElementById('outcome-modal');
    const outcomeBtns = document.querySelectorAll('.outcome-btn');
    const golOutcomeBtn = document.querySelector('.outcome-btn[data-outcome="GOL"]');
    const cancelOutcomeBtn = document.getElementById('cancel-outcome');

    const scoreAEl = document.getElementById('score-a');
    const scoreBEl = document.getElementById('score-b');
    
    const courtMap = document.getElementById('court-map');
    const goalZones = document.querySelectorAll('.goal-zone');
    const markerCourt = document.getElementById('shot-marker-court');

    // Inicializar posesión y estado desde el servidor al cargar (Event Sourcing - BUG-4)
    // El servidor garantiza y entrega el rival genérico (se autocrea si falta).
    async function loadMatchState() {
        if (!state.matchId) return;
        try {
            const resp = await fetch(`/api/matches/${state.matchId}/state`);
            if (resp.ok) {
                const data = await resp.json();
                scoreAEl.textContent = data.marcador_a || 0;
                scoreBEl.textContent = data.marcador_b || 0;
                updatePossession(data.posesion_actual || 'A');
                if (data.rival_generico_id) {
                    state.rivalGenericoId = String(data.rival_generico_id);
                }

                if (typeof TimerModule !== 'undefined' && data.segundos_jugados !== undefined) {
                    TimerModule.setSeconds(data.segundos_jugados);
                }
                // Restaurar verdad del servidor: el período nunca queda clavado en 1
                // tras recargar a mitad de la 2ª parte.
                if (typeof TimerModule !== 'undefined' && data.periodo_actual !== undefined && TimerModule.setPeriodo) {
                    TimerModule.setPeriodo(data.periodo_actual);
                }

                // Restaurar exclusiones activas (BUG-5)
                (data.exclusiones_activas || []).forEach(ex => {
                    startExclusionTimer(ex.id_jugador, ex.segundos_restantes);
                });

                // Restaurar expulsados (roja directa o 3ª exclusión): bloqueo permanente
                (data.descalificados || []).forEach(jid => {
                    expulsarJugador(jid, 'auto', false);
                });
                
                // Guardar backup local
                saveLocalState();
            } else {
                throw new Error("Server error");
            }
        } catch (e) {
            console.warn('Error al cargar estado del partido, usando backup local:', e);
            restoreLocalState();
        }
    }

    function saveLocalState() {
        if (!state.matchId) return;
        const localState = {
            marcador_a: scoreAEl.textContent,
            marcador_b: scoreBEl.textContent,
            posesion_actual: state.posesion,
            segundos_jugados: TimerModule ? TimerModule.getSeconds() : 0,
            periodo_actual: (typeof TimerModule !== 'undefined' && TimerModule.getPeriodo) ? TimerModule.getPeriodo() : 1,
            exclusiones: exclusions
        };
        localStorage.setItem(`gameState:${state.matchId}`, JSON.stringify(localState));
    }

    function restoreLocalState() {
        if (!state.matchId) return;
        try {
            const localState = JSON.parse(localStorage.getItem(`gameState:${state.matchId}`));
            if (localState) {
                scoreAEl.textContent = localState.marcador_a || 0;
                scoreBEl.textContent = localState.marcador_b || 0;
                updatePossession(localState.posesion_actual || 'A');
                if (typeof TimerModule !== 'undefined' && localState.segundos_jugados !== undefined) {
                    TimerModule.setSeconds(localState.segundos_jugados);
                }
                if (typeof TimerModule !== 'undefined' && localState.periodo_actual !== undefined && TimerModule.setPeriodo) {
                    TimerModule.setPeriodo(localState.periodo_actual);
                }
                if (localState.exclusiones) {
                    const currentSeconds = TimerModule ? TimerModule.getSeconds() : 0;
                    for (const [playerId, excl] of Object.entries(localState.exclusiones)) {
                        const remaining = excl.fin - currentSeconds;
                        if (remaining > 0) {
                            startExclusionTimer(playerId, remaining);
                        }
                    }
                }
            }
        } catch(e) {
            console.warn('No se pudo restaurar estado local', e);
        }
    }
    
    // Inicializar posesión visual
    function updatePossession(team) {
        state.posesion = team;
        const posA = document.getElementById('possession-a');
        const posB = document.getElementById('possession-b');
        if (posA) posA.classList.toggle('hidden', team !== 'A');
        if (posB) posB.classList.toggle('hidden', team !== 'B');
    }

    // Lógica correcta de posesión (BUG-2)
    // Lógica correcta de posesión (BUG-2)
    // Tras cualquier tiro con resultado el balón queda en la defensa,
    // sea gol, parada, fallo o bloqueo: la posesión es del rival del tirador.
    function actualizarPosesionInteligente(equipoActor, evento) {
        const rival = equipoActor === 'A' ? 'B' : 'A';
        const res = evento.resultado;
        const tipo = evento.tipo_evento;
        const ES_TIRO = ['LANZAMIENTO', 'LANZAMIENTO_6M', 'LANZAMIENTO_9M', 'LANZAMIENTO_7M', 'CONTRAATAQUE'];

        if ((ES_TIRO.includes(tipo) && res) || ['PERDIDA_BALON', 'FALTA_TECNICA', 'DOBLE', 'PASOS'].includes(tipo)) {
            updatePossession(rival);
        } else if (['PARADA_PORTERO', 'ROBO_BALON', 'BLOQUEO'].includes(tipo)) {
            updatePossession(equipoActor);
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

            // Modo tiro rival: tu arquero seleccionado = te están atacando.
            // Se recalcula en cada selección, nunca queda pegado.
            state.tiroRival = clickedItem.dataset.team === 'A' && clickedItem.dataset.posicion === 'PORTERO';

            // Nombre a prueba de markup: rivales con dorsal no tienen .player-name
            const nameEl = clickedItem.querySelector('.player-name');
            const numEl = clickedItem.querySelector('.player-num');
            const playerName = nameEl ? nameEl.textContent
                : ('#' + (numEl ? numEl.textContent.trim() : clickedItem.dataset.id));
            state.selectedName = playerName;
            actionFeedbackText.textContent = '';
            const strong = document.createElement('strong');
            if (state.tiroRival) {
                // Anti-error: que quede claro que los tiros van EN CONTRA
                actionFeedbackText.appendChild(document.createTextNode('Arquero '));
                strong.textContent = playerName;
                actionFeedbackText.appendChild(strong);
                actionFeedbackText.appendChild(document.createTextNode(' → te atacan: los tiros van contra tu equipo.'));
                actionFeedback.style.borderColor = 'var(--warning)';
                if (golOutcomeBtn) golOutcomeBtn.textContent = 'Gol en contra';
            } else {
                actionFeedbackText.appendChild(document.createTextNode('Jugador seleccionado: '));
                strong.textContent = playerName;
                actionFeedbackText.appendChild(strong);
                actionFeedbackText.appendChild(document.createTextNode('. Elige una acción.'));
                actionFeedback.style.borderColor = state.selectedTeam === 'A' ? 'var(--team-a-color)' : 'var(--team-b-color)';
                if (golOutcomeBtn) golOutcomeBtn.textContent = 'Gol';
            }
            actionsContainer.classList.remove('disabled');
        });
    });

    // 2. CAPTURA DE EVENTOS (ACCIONES)
    actionBtns.forEach(btn => {
        btn.addEventListener('click', (e) => {
            const eventType = e.currentTarget.dataset.eventType;
            const requiresOutcome = e.currentTarget.dataset.requiresOutcome === 'true';

            // Botones del rival (2 min / pérdida / roja): van directo al
            // rival genérico, sin exigir selección previa.
            if (e.currentTarget.dataset.rival === 'true') {
                if (!state.rivalGenericoId) {
                    showToast('Este partido no tiene rival genérico configurado', true);
                    return;
                }
                state.selectedName = 'Rival';
                sendEvent(eventType, null, null, state.rivalGenericoId);
                return;
            }

            if (!state.selectedPlayerId) return;

            // Blindaje: el seleccionado pudo ser sancionado sin re-seleccionar
            // (modo fijar jugador). Un sancionado nunca registra acciones.
            const sel = document.querySelector(`.player-card[data-id="${state.selectedPlayerId}"]`);
            if (sel && sel.classList.contains('disabled')) {
                showToast('Jugador no disponible (sancionado)', true);
                resetSelection(true);
                return;
            }

            if (requiresOutcome) {
                state.coordenada_x = null;
                state.coordenada_y = null;
                state.zona_porteria = null;
                state.pendingAction = eventType;
                disarmZone();

                outcomeModal.classList.remove('hidden');
            } else {
                sendEvent(eventType, null);
            }
        });
    });

    // 3. MANEJO DEL MODAL DE RESULTADO + ZONA OBLIGATORIA (GOL/PARADA)
    // Flujo: resultado directo (FALLO/BLOQUEADO) o resultado + zona (GOL/PARADA).
    const ZONE_REQUIRED = ['GOL', 'PARADA'];
    let armedOutcome = null; // 'GOL' | 'PARADA' cuando se espera el toque en la zona

    function setZoneHint(text, armed) {
        const hint = document.getElementById('zone-hint');
        if (!hint) return;
        hint.textContent = text;
        hint.classList.toggle('armed-hint', !!armed);
    }

    function disarmZone() {
        armedOutcome = null;
        goalZones.forEach(z => z.classList.remove('selected'));
        outcomeBtns.forEach(b => b.classList.remove('armed'));
        const gm = document.getElementById('goal-map');
        if (gm) gm.classList.remove('armed');
        setZoneHint('1. Tocá el resultado · 2. Si es Gol o Parada, tocá la zona del arco', false);
    }

    outcomeBtns.forEach(btn => {
        btn.addEventListener('click', (e) => {
            const outcome = e.currentTarget.dataset.outcome;
            if (ZONE_REQUIRED.includes(outcome)) {
                // Armar: la zona es obligatoria, el evento se guarda al tocar el arco
                disarmZone();
                armedOutcome = outcome;
                e.currentTarget.classList.add('armed');
                const gm = document.getElementById('goal-map');
                if (gm) gm.classList.add('armed');
                setZoneHint(outcome === 'GOL'
                    ? 'Gol: ¿en qué zona entró? Tocá el arco'
                    : 'Parada: ¿en qué zona la atajó? Tocá el arco', true);
            } else {
                // FALLO/BLOQUEADO: guardado inmediato, sin zona
                const action = state.pendingAction;
                closeModal();
                sendEvent(action, outcome);
            }
        });
    });

    goalZones.forEach(zone => {
        zone.addEventListener('click', (e) => {
            if (!armedOutcome || !state.pendingAction) {
                setZoneHint('Primero tocá Gol o Parada arriba');
                return;
            }
            goalZones.forEach(z => z.classList.remove('selected'));
            e.currentTarget.classList.add('selected');
            state.zona_porteria = e.currentTarget.dataset.zone;
            const action = state.pendingAction;
            const outcome = armedOutcome;
            // Arquero defensor en todo tiro a puerta (GOL o PARADA): sin goles
            // recibidos por portero no hay denominador para su % de paradas.
            // FALLO/BLOQUEADO no van a puerta: no atribuyen portero.
            // (En modo tiro rival sendEvent reasigna actor y arquero.)
            let keeperId = null;
            if (outcome === 'GOL' || outcome === 'PARADA') {
                const rival = state.selectedTeam === 'A' ? 'B' : 'A';
                keeperId = arqueroVigente(rival);
            }
            closeModal();
            sendEvent(action, outcome, keeperId);
        });
    });

    // Arqueros disponibles del equipo (excluye suspendidos). Para atribución exacta.
    function porterosDe(equipo) {
        const lista = [];
        document.querySelectorAll(`.player-card[data-team="${equipo}"]`).forEach(el => {
            if (el.dataset.posicion !== 'PORTERO' || el.classList.contains('disabled')) return;
            const nameEl = el.querySelector('.player-name');
            const numEl = el.querySelector('.player-num');
            lista.push({
                id: el.dataset.id,
                nombre: nameEl ? nameEl.textContent : ('#' + (numEl ? numEl.textContent.trim() : el.dataset.id))
            });
        });
        return lista;
    }

    // Arquero designado en cancha por equipo. Devuelve su id o null.
    // Si el designado ya no está disponible (exclusión), auto-corrige al primero.
    function arqueroVigente(equipo) {
        const disp = porterosDe(equipo).map(p => String(p.id));
        let keeperId = state.activeKeeper[equipo] != null ? String(state.activeKeeper[equipo]) : null;
        if (!disp.includes(keeperId)) {
            keeperId = disp.length ? disp[0] : null;
            state.activeKeeper[equipo] = keeperId;
            persistKeeper();
            refreshKeeperToggles();
        }
        return keeperId;
    }

    function persistKeeper() {
        try {
            localStorage.setItem(`keeper:${state.matchId}`, JSON.stringify(state.activeKeeper));
        } catch (e) { /* almacenamiento no disponible: se sigue sin persistir */ }
    }

    function refreshKeeperToggles() {
        document.querySelectorAll('.keeper-toggle').forEach(b => {
            b.classList.toggle('active', String(state.activeKeeper[b.dataset.keeperTeam]) === String(b.dataset.keeperId));
        });
    }

    function setActiveKeeper(equipo, idJugador, avisar) {
        state.activeKeeper[equipo] = idJugador;
        persistKeeper();
        refreshKeeperToggles();
        if (avisar) {
            const p = porterosDe(equipo).find(x => String(x.id) === String(idJugador));
            showToast(`Arquero en cancha: ${p ? p.nombre : '#' + idJugador}`);
        }
    }

    // Restaurar designación guardada (o primer arquero) y cablear los toggles 🧤
    (function initKeeper() {
        try {
            const saved = JSON.parse(localStorage.getItem(`keeper:${state.matchId}`) || 'null');
            if (saved) state.activeKeeper = saved;
        } catch (e) { /* arrancar con valores por defecto */ }
        arqueroVigente('A');
        refreshKeeperToggles();
        document.querySelectorAll('.keeper-toggle').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation(); // no seleccionar al jugador al tocar el guante
                setActiveKeeper(btn.dataset.keeperTeam, btn.dataset.keeperId, true);
            });
        });
    })();

    if (cancelOutcomeBtn) {
        cancelOutcomeBtn.addEventListener('click', () => {
            closeModal();
        });
    }

    function closeModal() {
        if (outcomeModal) outcomeModal.classList.add('hidden');
        disarmZone();
        state.pendingAction = null;
    }

    // 4. ALMACENAMIENTO Y SINCRONIZACIÓN OFFLINE
    // actorTeam: equipo real del actor (difiere del seleccionado en modo tiro
    // rival y en los botones rápidos del rival genérico).
    function saveEventToQueue(eventData, actorTeam) {
        // Guardar mediante módulo resiliente (Fase 2)
        OfflineQueue.enqueue(state.matchId, eventData);

        // --- 4.1 LÓGICA EN TIEMPO REAL --- //
        const currentTeam = actorTeam || state.selectedTeam;
        const prevPossession = state.posesion;

        // Marcador
        if (eventData.resultado === 'GOL') {
            if (currentTeam === 'A') scoreAEl.textContent = parseInt(scoreAEl.textContent) + 1;
            else if (currentTeam === 'B') scoreBEl.textContent = parseInt(scoreBEl.textContent) + 1;
        }

        // Posesión corregida
        actualizarPosesionInteligente(currentTeam, eventData);

        // Exclusión: bloqueo 2 min + deselección forzada del sancionado
        if (eventData.tipo_evento === 'EXCLUSION_2MIN') {
            startExclusionTimer(eventData.id_jugador, 120);
            if (String(eventData.id_jugador) === String(state.rivalGenericoId)) {
                showToast('2 min al rival registrado');
            }
            // 3ª exclusión = descalificación automática (espejo de recalcular_disciplina)
            const previas = history.filter(h => h.tipo === 'EXCLUSION_2MIN' && String(h.playerId) === String(eventData.id_jugador)).length;
            if (previas + 1 >= 3) {
                expulsarJugador(eventData.id_jugador, 'auto', true);
            } else if (String(state.selectedPlayerId) === String(eventData.id_jugador)) {
                resetSelection(true);
            }
        }

        // Roja directa: bloqueo permanente + deselección forzada
        if (eventData.tipo_evento === 'DESCALIFICACION') {
            expulsarJugador(eventData.id_jugador, 'manual', true);
        }
        
        showToast(describirEvento(eventData, currentTeam));

        // Historial para DESHACER + tira de últimos eventos (visual, nunca bloquea)
        history.push({
            id: eventData.client_event_id,
            tipo: eventData.tipo_evento,
            resultado: eventData.resultado,
            team: currentTeam,
            playerId: eventData.id_jugador,
            hora: eventData.tiempo_juego,
            nombre: nombreHistorial(eventData, currentTeam),
            prevPossession
        });
        renderTimeline();

        resetSelection();
    }

    // Etiquetas honestas: un tiro del rival se lee como lo que es (en contra),
    // nunca como si tu arquero hubiera marcado.
    function esTiroRival(eventData) {
        return String(eventData.id_jugador) === String(state.rivalGenericoId);
    }

    function describirEvento(eventData, actorTeam) {
        const ES_TIRO = ['LANZAMIENTO', 'LANZAMIENTO_6M', 'LANZAMIENTO_9M', 'LANZAMIENTO_7M', 'CONTRAATAQUE'];
        if (esTiroRival(eventData) && ES_TIRO.includes(eventData.tipo_evento)) {
            const gk = nombrePortero(eventData.id_portero);
            if (eventData.resultado === 'GOL') return gk ? `Gol en contra (vs ${gk})` : 'Gol en contra';
            if (eventData.resultado === 'PARADA') return gk ? `Parada de ${gk}` : 'Parada registrada';
            if (eventData.resultado === 'FALLO') return 'Tiro rival fallado';
            if (eventData.resultado === 'BLOQUEADO') return 'Tiro rival bloqueado';
        }
        return `Registrado: ${eventData.tipo_evento.replace('_', ' ')}`;
    }

    function nombrePortero(idPortero) {
        if (!idPortero) return '';
        const el = document.querySelector(`.player-card[data-id="${idPortero}"] .player-name`);
        return el ? el.textContent : '';
    }

    function nombreHistorial(eventData, actorTeam) {
        if (esTiroRival(eventData)) {
            const gk = nombrePortero(eventData.id_portero);
            return actorTeam === 'B' && eventData.resultado === 'GOL'
                ? (gk ? `Gol en contra · contra ${gk}` : 'Gol en contra')
                : 'Rival';
        }
        return state.selectedName || '';
    }

    function renderTimeline() {
        const lastEv = document.getElementById('last-events');
        if (!lastEv) return;
        lastEv.innerHTML = '';
        history.slice(-4).reverse().forEach(h => {
            const tag = document.createElement('span');
            tag.className = 'tl-item';
            const label = document.createElement('span');
            label.textContent = `${h.hora ? h.hora + ' · ' : ''}${h.tipo.replace(/_/g, ' ')}${h.resultado ? ' (' + h.resultado + ')' : ''}${h.nombre ? ' · ' + h.nombre : ''}`;
            const undo = document.createElement('button');
            undo.className = 'tl-undo';
            undo.textContent = '↶';
            undo.title = 'Deshacer este evento';
            undo.addEventListener('click', () => undoEvent(h.id));
            tag.appendChild(label);
            tag.appendChild(undo);
            lastEv.appendChild(tag);
        });
    }

    function undoEvent(clientId) {
        const idx = history.findIndex(h => h.id === clientId);
        if (idx === -1) {
            showToast('Evento ya deshecho o no disponible', true);
            return;
        }
        const h = history[idx];
        history.splice(idx, 1);

        // Reversión optimista local (el servidor recalcula al sincronizar)
        if (h.resultado === 'GOL') {
            const el = h.team === 'A' ? scoreAEl : scoreBEl;
            el.textContent = Math.max(0, parseInt(el.textContent || '0', 10) - 1);
        }
        if (h.tipo === 'EXCLUSION_2MIN') {
            delete exclusions[h.playerId];
            revisarExpulsion(h.playerId); // ¿sigue vigente alguna expulsión?
            if (!expulsados[String(h.playerId)]) {
                const item = document.querySelector(`.player-card[data-id="${h.playerId}"]`);
                if (item) {
                    item.classList.remove('disabled', 'expelled');
                    const s = item.querySelector('.player-excl');
                    if (s) s.classList.add('hidden');
                }
            }
        }
        if (h.tipo === 'DESCALIFICACION') {
            // Se levanta la roja manual (la automática la maneja revisarExpulsion)
            delete expulsados[String(h.playerId)];
            if (!exclusions[String(h.playerId)]) {
                const item = document.querySelector(`.player-card[data-id="${h.playerId}"]`);
                if (item) {
                    item.classList.remove('disabled', 'expelled');
                    const s = item.querySelector('.player-excl');
                    if (s) s.classList.add('hidden');
                }
            }
        }
        updatePossession(h.prevPossession);
        saveLocalState();

        // Anular en servidor vía cola (funciona offline; si el create aún no
        // sincronizó, el void viaja detrás en orden y lo alcanza)
        OfflineQueue.enqueue(state.matchId, { op: 'void', client_event_id: h.id });
        renderTimeline();
        showToast('Evento deshecho ↶');
    }

    window.deshacerUltimo = function() {
        const h = history[history.length - 1];
        if (h) undoEvent(h.id);
        else showToast('Nada que deshacer', true);
    };

    // Expulsión permanente (roja directa o 3ª exclusión). Nunca vuelve en el partido,
    // salvo que se deshaga la sanción que la originó.
    function expulsarJugador(playerId, origen, avisar) {
        const key = String(playerId);
        expulsados[key] = origen;
        const item = document.querySelector(`.player-card[data-id="${playerId}"]`);
        if (item) {
            item.classList.add('disabled', 'expelled');
            const s = item.querySelector('.player-excl');
            if (s) {
                s.textContent = '✕';
                s.classList.remove('hidden');
            }
        }
        if (String(state.selectedPlayerId) === key) resetSelection(true);
        if (avisar) showToast(origen === 'auto' ? 'Descalificado: 3ª exclusión' : 'Jugador expulsado (roja)');
    }

    // Tras deshacer una exclusión: si la expulsión era automática y ya no hay
    // 3 exclusiones vigentes, se levanta (respetando un posible timer activo).
    function revisarExpulsion(playerId) {
        const key = String(playerId);
        if (expulsados[key] !== 'auto') return;
        const nExc = history.filter(h => h.tipo === 'EXCLUSION_2MIN' && String(h.playerId) === key).length;
        if (nExc >= 3) return;
        delete expulsados[key];
        const item = document.querySelector(`.player-card[data-id="${playerId}"]`);
        if (!item) return;
        if (exclusions[key]) return; // sigue con timer activo: mantiene disabled
        item.classList.remove('disabled', 'expelled');
        const s = item.querySelector('.player-excl');
        if (s) s.classList.add('hidden');
    }

    // Exclusión con bloqueo de jugador (P5-4: Reloj global)
    function startExclusionTimer(playerId, durationSeconds = 120) {
        const playerItem = document.querySelector(`.player-card[data-id="${playerId}"]`);
        if (!playerItem) return;
        
        playerItem.classList.add('disabled'); // Deshabilitar selección mientras esté excluido
        const exclSpan = playerItem.querySelector('.player-excl');
        if (exclSpan) {
            exclSpan.classList.remove('hidden');
            // La visualización inicial se actualizará en el próximo tick del setInterval global
        }
        
        exclusions[playerId] = { fin: TimerModule.getSeconds() + durationSeconds };
    }

    // Ticker único global para exclusiones
    setInterval(() => {
        if (typeof TimerModule === 'undefined') return;
        const currentSeconds = TimerModule.getSeconds();
        
        for (const [playerId, excl] of Object.entries(exclusions)) {
            const remaining = excl.fin - currentSeconds;
            const playerItem = document.querySelector(`.player-card[data-id="${playerId}"]`);
            const exclSpan = playerItem ? playerItem.querySelector('.player-excl') : null;

            if (remaining <= 0) {
                delete exclusions[playerId];
                if (expulsados[playerId]) continue; // expulsado: sigue bloqueado
                if (playerItem) playerItem.classList.remove('disabled');
                if (exclSpan) exclSpan.classList.add('hidden');
            } else if (exclSpan) {
                const m = Math.floor(remaining / 60);
                const s = remaining % 60;
                exclSpan.textContent = `${m}:${s.toString().padStart(2, '0')}`;
            }
        }
        
        saveLocalState();
    }, 1000);

    // 5. MANEJO DE ENVÍO DE EVENTO
    // actorId: botones rápidos del rival (fuerzan al rival genérico, equipo B).
    // Modo tiro rival (tu arquero + botón de tiro): actor = rival genérico,
    // id_portero = tu arquero, en los 4 resultados (GOL/PARADA/FALLO/BLOQUEADO).
    // Cualquier otro botón con el arquero seleccionado se registra al arquero.
    // El id del rival genérico es dato del servidor: si falta (HTML cacheado de
    // una versión vieja), se reintenta contra /state antes de rendirse. El evento
    // nunca se descarta por falta de ese dato.
    async function rivalGenerico() {
        if (state.rivalGenericoId) return state.rivalGenericoId;
        try {
            const resp = await fetch(`/api/matches/${state.matchId}/state`);
            if (resp.ok) {
                const data = await resp.json();
                if (data.rival_generico_id) {
                    state.rivalGenericoId = String(data.rival_generico_id);
                    return state.rivalGenericoId;
                }
            }
        } catch (e) { /* sin red: se informa abajo */ }
        return null;
    }

    async function sendEvent(eventType, outcome, idPortero, actorId) {
        const ES_TIRO = ['LANZAMIENTO', 'LANZAMIENTO_6M', 'LANZAMIENTO_9M', 'LANZAMIENTO_7M', 'CONTRAATAQUE'];
        const esTiro = ES_TIRO.includes(eventType);
        const modoRival = !actorId && state.tiroRival && esTiro;
        let actor = actorId || (modoRival ? (state.rivalGenericoId || await rivalGenerico()) : state.selectedPlayerId);
        if (!actor && !modoRival && !actorId) {
            showToast('Seleccioná un jugador', true);
            return;
        }
        if (!actor) {
            actor = await rivalGenerico();
        }
        if (!actor) {
            showToast('No se pudo obtener el rival genérico: recargá la página con internet y reintentá', true);
            return;
        }
        const actorTeam = (actorId || modoRival) ? 'B' : state.selectedTeam;
        const keeper = modoRival ? state.selectedPlayerId : (idPortero || null);
        const eventData = {
            id_partido: parseInt(state.matchId),
            id_jugador: parseInt(actor),
            tipo_evento: eventType,
            resultado: outcome,
            tiempo_juego: TimerModule ? TimerModule.getCurrentTime() : '00:00',
            periodo: (typeof TimerModule !== 'undefined') ? TimerModule.getPeriodo() : 1,
            coordenada_x: state.coordenada_x, 
            coordenada_y: state.coordenada_y,
            // La zona solo pertenece a tiros: nunca arrastrar la del evento anterior
            zona_porteria: esTiro ? state.zona_porteria : null,
            id_portero: keeper ? parseInt(keeper) : null
        };
        state.zona_porteria = null;

        saveEventToQueue(eventData, actorTeam);
    }

    function resetSelection(force) {
        // BUG-16 / Modo Fijar Jugador (<3 clics por acción)
        // force=true: la sanción del seleccionado rompe el fijado
        if (!force && lockPlayerToggle && lockPlayerToggle.checked && state.selectedPlayerId) {
            // Mantener jugador activo para encadenar tiro/asistencia
            return;
        }

        playerItems.forEach(p => p.classList.remove('active'));
        state.selectedPlayerId = null;
        state.selectedTeam = null;
        state.tiroRival = false;
        if (golOutcomeBtn) golOutcomeBtn.textContent = 'Gol';
        actionFeedbackText.textContent = 'Selecciona un jugador para continuar...';
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

    // Navbar automática: retraída por defecto, baja al acercar el mouse
    // (en táctil el tap sobre la zona sensora la alterna)
    (function initAutoNav() {
        const nav = document.querySelector('.top-navbar');
        const sensor = document.getElementById('nav-sensor');
        if (!nav || !sensor) return;
        let timer = null;
        const tactil = window.matchMedia && window.matchMedia('(pointer: coarse)').matches;
        function expandir() {
            clearTimeout(timer);
            nav.classList.remove('retraida');
        }
        function retraer(delay) {
            clearTimeout(timer);
            timer = setTimeout(() => nav.classList.add('retraida'), delay);
        }
        sensor.addEventListener('mouseenter', expandir);
        sensor.addEventListener('click', () => nav.classList.toggle('retraida'));
        if (!tactil) nav.addEventListener('mouseleave', () => retraer(400));
        retraer(2000); // arranca visible y se guarda sola
    })();

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

    // Finalizar Partido (Bloque E)
    window.finalizarPartido = function() {
        if (!confirm('¿Estás seguro de finalizar el partido? No podrás agregar más eventos.')) return;
        
        const scoreA = document.getElementById('score-a').textContent;
        const scoreB = document.getElementById('score-b').textContent;
        
        fetch(`/api/matches/${state.matchId}/state`, {
            method: 'PATCH',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                estado: 'FINALIZADO',
                marcador_final_a: parseInt(scoreA),
                marcador_final_b: parseInt(scoreB)
            })
        }).then(res => res.json()).then(data => {
            if (data.status === 'success') {
                if(typeof TimerModule !== 'undefined') TimerModule.stopTimer();
                window.location.href = `/stats?match=${state.matchId}`;
            } else {
                showToast('Error al finalizar el partido', true);
            }
        }).catch(() => {
            showToast('Error de red al finalizar', true);
        });
    };

    // UI Sincronización y Respaldo (Bloque H)
    const syncStatus = document.getElementById('sync-status');
    const btnSyncNow = document.getElementById('btn-sync-now');
    const failedContainer = document.getElementById('failed-events-container');
    const failedList = document.getElementById('failed-events-list');

    if (btnSyncNow) {
        btnSyncNow.addEventListener('click', () => {
            OfflineQueue.sync(state.matchId);
        });
    }

    setInterval(() => {
        if (!syncStatus) return;
        const q = OfflineQueue.getQueue(state.matchId);
        if (q.length === 0) {
            syncStatus.textContent = '🟢 Sincronizado';
            syncStatus.style.background = 'rgba(46, 204, 113, 0.5)';
            if (btnSyncNow) btnSyncNow.style.display = 'none';
        } else {
            syncStatus.textContent = `🟡 Sincronizando (${q.length} pendientes)`;
            syncStatus.style.background = 'rgba(241, 196, 15, 0.5)';
            if (btnSyncNow) btnSyncNow.style.display = 'block';
        }

        const failed = OfflineQueue.getFailed ? OfflineQueue.getFailed(state.matchId) : [];
        if (failed.length > 0 && failedContainer) {
            failedContainer.classList.remove('hidden');
            failedList.innerHTML = failed.map(f => `<li>${f.event.tipo_evento} - ${f.error}</li>`).join('');
        } else if (failedContainer) {
            failedContainer.classList.add('hidden');
        }
    }, 1000);

    window.limpiarFallidos = function() {
        if (OfflineQueue.clearFailed) OfflineQueue.clearFailed(state.matchId);
        if (failedContainer) failedContainer.classList.add('hidden');
    };

    window.descargarBackupLocal = function() {
        const q = OfflineQueue.getQueue(state.matchId);
        const blob = new Blob([JSON.stringify(q, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `backup_local_${state.matchId}_pendientes.json`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    };

    window.addEventListener('beforeunload', (e) => {
        const q = OfflineQueue.getQueue(state.matchId);
        if (q.length > 0) {
            e.preventDefault();
            e.returnValue = 'Tienes eventos sin sincronizar. ¿Seguro que quieres salir?';
        }
    });

});
