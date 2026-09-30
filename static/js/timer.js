// timer.js - Cronómetro único y sincronizado
const TimerModule = (() => {
    let timerInterval = null;
    let totalSeconds = 0;
    let duracionPeriodo = 1800; // 30 min por defecto
    let periodoActual = 1;
    let isRunning = false;
    let matchId = null;
    let syncInterval = null;

    const timeDisplay = document.getElementById('timer');
    const startBtn = document.getElementById('start-btn');
    const stopBtn = document.getElementById('stop-btn');
    const resetBtn = document.getElementById('reset-btn');
    const matchIdEl = document.getElementById('match-id');

    if (matchIdEl) {
        matchId = matchIdEl.value;
    }

    function periodoDesdeSegundos(secs) {
        // Regla única (espejo de periodo_desde_segundos en services/eventos.py):
        // floor(seg/1800)+1. 0–1799 → 1, 1800–3599 → 2, 3600+ → prórroga (3+).
        let s = parseInt(secs) || 0;
        if (s < 0) s = 0;
        return Math.floor(s / duracionPeriodo) + 1;
    }

    function actualizarEtiquetaPeriodo() {
        const el = document.getElementById('periodo-label');
        if (!el) return;
        el.textContent = periodoActual >= 3 ? 'PRÓRROGA' : (periodoActual === 2 ? '2ª PARTE' : '1ª PARTE');
    }
    function formatSeconds(secs) {
        const minutes = Math.floor(secs / 60);
        const seconds = secs % 60;
        return `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
    }

    function updateDisplay() {
        if (timeDisplay) {
            timeDisplay.textContent = formatSeconds(totalSeconds);
        }
    }

    function syncStateWithServer() {
        if (!matchId) return;
        fetch(`/api/matches/${matchId}/state`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                segundos_jugados: totalSeconds,
                periodo_actual: periodoActual,
                en_pausa: isRunning ? 0 : 1
            })
        }).catch(err => console.warn('Error al guardar estado de tiempo:', err));
    }

    function startTimer() {
        if (timerInterval) return;
        isRunning = true;
        timerInterval = setInterval(() => {
            totalSeconds++;
            updateDisplay();

            // Sincronizar periódicamente cada 10 segundos
            if (totalSeconds % 10 === 0) {
                syncStateWithServer();
            }

            // Período derivado de los segundos (no por evento disparado):
            // funciona aunque la sesión arranque a los 31' o se recargue.
            const derivado = periodoDesdeSegundos(totalSeconds);
            if (derivado > periodoActual) {
                periodoActual = derivado;
                actualizarEtiquetaPeriodo();
                alert(`¡Fin del periodo ${periodoActual - 1}! Comenzando periodo ${periodoActual}.`);
                syncStateWithServer();
            }
        }, 1000);
    }

    function stopTimer() {
        if (timerInterval) {
            clearInterval(timerInterval);
            timerInterval = null;
        }
        isRunning = false;
        syncStateWithServer();
    }

    function resetTimer() {
        // Corregido BUG-12: confirm ANTES de detener el reloj
        if (confirm('¿Estás seguro de reiniciar el cronómetro?')) {
            stopTimer();
            totalSeconds = 0;
            periodoActual = 1;
            updateDisplay();
            actualizarEtiquetaPeriodo();
            syncStateWithServer();
        }
    }

    function setSeconds(secs) {
        totalSeconds = parseInt(secs) || 0;
        // Recalcular período en silencio (sin alerta): restaura la verdad
        // aunque la página se recargue a mitad de la 2ª parte.
        const derivado = periodoDesdeSegundos(totalSeconds);
        if (derivado > periodoActual) {
            periodoActual = derivado;
        }
        updateDisplay();
        actualizarEtiquetaPeriodo();
    }

    function setPeriodo(p) {
        // Verdad del servidor (loadMatchState): nunca decrece por debajo
        // del derivado de los segundos.
        const n = parseInt(p) || 1;
        periodoActual = Math.max(n, periodoDesdeSegundos(totalSeconds));
        actualizarEtiquetaPeriodo();
    }

    function getSeconds() {
        return totalSeconds;
    }

    function getCurrentTime() {
        // Corregido BUG-13: deriva de totalSeconds en vez de leer textContent del DOM
        return formatSeconds(totalSeconds);
    }

    function getPeriodo() {
        return periodoActual;
    }

    if (startBtn) startBtn.addEventListener('click', startTimer);
    if (stopBtn) stopBtn.addEventListener('click', stopTimer);
    if (resetBtn) resetBtn.addEventListener('click', resetTimer);
    actualizarEtiquetaPeriodo();

    return {
        startTimer,
        stopTimer,
        resetTimer,
        getCurrentTime,
        getSeconds,
        setSeconds,
        formatSeconds,
        getPeriodo,
        setPeriodo
    };
})();
