document.addEventListener('DOMContentLoaded', async () => {
    const matchId = document.getElementById('match-id').value;
    if (!matchId) return;

    try {
        // Fetch data
        const [statsRes, heatmapRes] = await Promise.all([
            fetch(`/api/stats/${matchId}`),
            fetch(`/api/matches/${matchId}/heatmap`)
        ]);

        if (!statsRes.ok || !heatmapRes.ok) throw new Error('Error fetching data');

        const statsData = await statsRes.json();
        const heatmapData = await heatmapRes.json();

        renderTitle(statsData);
        renderTable(statsData.jugadores);
        renderCharts(statsData.jugadores, heatmapData.zonas_tiro);
        renderHeatmap(heatmapData.porteria);

    } catch (error) {
        console.error(error);
        alert('Error cargando estadísticas.');
    }
});

function renderTitle(data) {
    const p = data.partido;
    document.getElementById('match-title').textContent = 
        `${p.nombre_equipo_a} ${p.marcador_a} - ${p.marcador_b} ${p.nombre_equipo_b}`;
}

function renderTable(jugadores) {
    const tbody = document.querySelector('#players-table tbody');
    let html = '';

    // Sort by team, then number
    jugadores.sort((a, b) => {
        if (a.id_equipo !== b.id_equipo) return a.id_equipo.localeCompare(b.id_equipo);
        return a.numero_camiseta - b.numero_camiseta;
    });

    jugadores.forEach(j => {
        html += `
            <tr>
                <td>${j.id_equipo}</td>
                <td>${j.numero_camiseta}</td>
                <td style="text-align: left;">${j.nombre} ${j.es_portero ? '(P)' : ''}</td>
                <td>${j.goles} / ${j.lanzamientos_totales}</td>
                <td>${j.eficiencia_tiro}%</td>
                <td>${j.asistencias}</td>
                <td>${j.paradas}</td>
                <td>${j.gki > 0 ? j.gki : '-'}</td>
                <td>${j.exclusiones_2min}</td>
                <td>${j.perdidas}</td>
                <td style="color: ${j.mas_menos > 0 ? 'var(--success)' : (j.mas_menos < 0 ? 'var(--warning)' : 'inherit')}">
                    ${j.mas_menos > 0 ? '+' : ''}${j.mas_menos}
                </td>
            </tr>
        `;
    });
    tbody.innerHTML = html;
}

function renderCharts(jugadores, zonasTiro) {
    // Chart 1: Goles por jugador (Top 10)
    const goleadores = jugadores.filter(j => j.goles > 0).sort((a, b) => b.goles - a.goles).slice(0, 10);
    
    new Chart(document.getElementById('chartGoles'), {
        type: 'bar',
        data: {
            labels: goleadores.map(j => j.nombre),
            datasets: [{
                label: 'Goles',
                data: goleadores.map(j => j.goles),
                backgroundColor: 'rgba(52, 152, 219, 0.7)',
                borderColor: 'rgba(52, 152, 219, 1)',
                borderWidth: 1
            }]
        },
        options: {
            responsive: true,
            scales: {
                y: { beginAtZero: true, ticks: { stepSize: 1, color: '#ccc' } },
                x: { ticks: { color: '#ccc' } }
            },
            plugins: {
                legend: { labels: { color: '#ccc' } }
            }
        }
    });

    // Chart 2: Zonas de tiro (Pie)
    const labels = Object.keys(zonasTiro).map(k => k.replace('LANZAMIENTO_', '').replace('_', ' '));
    const dataVals = Object.values(zonasTiro);

    new Chart(document.getElementById('chartZonas'), {
        type: 'doughnut',
        data: {
            labels: labels,
            datasets: [{
                data: dataVals,
                backgroundColor: [
                    '#e74c3c', '#3498db', '#f1c40f', '#2ecc71', '#9b59b6'
                ],
                borderWidth: 0
            }]
        },
        options: {
            responsive: true,
            plugins: {
                legend: { position: 'bottom', labels: { color: '#ccc' } }
            }
        }
    });
}

function renderHeatmap(porteria) {
    const container = document.getElementById('goal-heatmap');
    const order = ['TL', 'TC', 'TR', 'ML', 'MC', 'MR', 'BL', 'BC', 'BR'];
    
    let html = '';
    order.forEach(zona => {
        const stats = porteria[zona] || {goles: 0, paradas: 0, fallos: 0, total: 0};
        let bg = 'rgba(255, 255, 255, 0.1)';
        
        if (stats.total > 0) {
            const pGoles = stats.goles / stats.total;
            const pParadas = stats.paradas / stats.total;
            
            if (pGoles >= pParadas && stats.goles > 0) {
                // Dominio Goles -> Rojo
                bg = `rgba(231, 76, 60, ${0.2 + (pGoles * 0.8)})`;
            } else if (pParadas > pGoles && stats.paradas > 0) {
                // Dominio Paradas -> Azul
                bg = `rgba(52, 152, 219, ${0.2 + (pParadas * 0.8)})`;
            }
        }

        html += `
            <div class="goal-zone heatmap-cell" style="background-color: ${bg}; pointer-events: none; outline: 1px solid rgba(255,255,255,0.2);">
                <div style="font-weight: bold; margin-bottom: 2px;">${stats.total} tiros</div>
                ${stats.goles > 0 ? `<div style="color: #ffcccc;">${stats.goles} G</div>` : ''}
                ${stats.paradas > 0 ? `<div style="color: #cce5ff;">${stats.paradas} P</div>` : ''}
            </div>
        `;
    });
    
    container.innerHTML = html;
}
