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

            // Notificación de fin de periodo (30 min)
            if (totalSeconds > 0 && totalSeconds % duracionPeriodo === 0) {
                periodoActual++;
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
            updateDisplay();
            syncStateWithServer();
        }
    }

    function setSeconds(secs) {
        totalSeconds = parseInt(secs) || 0;
        updateDisplay();
    }

    function getSeconds() {
        return totalSeconds;
    }

    function getCurrentTime() {
        // Corregido BUG-13: deriva de totalSeconds en vez de leer textContent del DOM
        return formatSeconds(totalSeconds);
    }

    if (startBtn) startBtn.addEventListener('click', startTimer);
    if (stopBtn) stopBtn.addEventListener('click', stopTimer);
    if (resetBtn) resetBtn.addEventListener('click', resetTimer);

    return {
        startTimer,
        stopTimer,
        resetTimer,
        getCurrentTime,
        getSeconds,
        setSeconds,
        formatSeconds
    };
})();
