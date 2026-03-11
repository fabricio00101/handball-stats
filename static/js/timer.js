// timer.js
const TimerModule = (() => {
    let timerInterval = null;
    let totalSeconds = 0;
    
    const timeDisplay = document.getElementById('timer');
    const startBtn = document.getElementById('start-btn');
    const stopBtn = document.getElementById('stop-btn');
    const resetBtn = document.getElementById('reset-btn');

    function updateDisplay() {
        const minutes = Math.floor(totalSeconds / 60);
        const seconds = totalSeconds % 60;
        timeDisplay.textContent = `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
    }

    function startTimer() {
        if (timerInterval) return; // Ya está corriendo
        timerInterval = setInterval(() => {
            totalSeconds++;
            updateDisplay();
        }, 1000);
    }

    function stopTimer() {
        clearInterval(timerInterval);
        timerInterval = null;
    }

    function resetTimer() {
        stopTimer();
        if (confirm('¿Estás seguro de reiniciar el cronómetro?')) {
            totalSeconds = 0;
            updateDisplay();
        }
    }

    function getCurrentTime() {
        return timeDisplay.textContent;
    }

    // Bind events
    startBtn.addEventListener('click', startTimer);
    stopBtn.addEventListener('click', stopTimer);
    resetBtn.addEventListener('click', resetTimer);

    return {
        getCurrentTime: getCurrentTime
    };
})();
