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
        renderKpis(statsData.equipos);
        renderBloques(statsData.bloques, statsData.ventanas);
        renderTipos(statsData.equipos);
        renderContexto7m(statsData.contexto_7m);
        renderTeamNames(statsData);
        renderTable(statsData.jugadores);
        const porEquipo = heatmapData.por_equipo || { A: null, B: null };
        renderCharts(statsData.jugadores, porEquipo);
        if (porEquipo.A) {
            renderHeatmap('goal-heatmap-a', porEquipo.A.porteria);
            renderHeatmap('goal-heatmap-b', porEquipo.B.porteria);
        }

    } catch (error) {
        console.error(error);
        alert('Error cargando estadísticas.');
    }
});

// Cómo se muestra un jugador depende del jugador, no del tipo de partido: en
// ANÁLISIS la plantilla ya trae nombres reales, y el dorsal solo se usa para
// los que el operador capturó a mano (el backend los marca con tiene_nombre
// en false porque su nombre es el placeholder "N.º 21").

// Etiqueta para el eje de las barras: dorsal adelante y, si hay, el apellido
// (lo decide el backend en nombre_corto). El apellido y no el nombre de pila
// porque los nombres se repiten dentro de un mismo equipo: Ballester tiene dos
// "Marco" (#3 y #22) y Maipu dos "Lautaro" (#16 y #99).
function etiquetaBarra(j) {
    return j.nombre_corto ? `#${j.numero_camiseta} ${j.nombre_corto}` : `#${j.numero_camiseta}`;
}

// Etiqueta para la columna de nombre de la tabla: nombre completo, y el dorsal
// si el jugador no tiene uno.
function etiquetaNombre(j) {
    return j.tiene_nombre ? j.nombre : `#${j.numero_camiseta}`;
}

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
        const esPort = j.es_portero || j.paradas > 0;
        const subtipos = [];
        const pt = j.paradas_por_tipo || {};
        if (pt['6M']) subtipos.push(`6M:${pt['6M']}`);
        if (pt['9M']) subtipos.push(`9M:${pt['9M']}`);
        if (pt['7M']) subtipos.push(`7M:${pt['7M']}`);
        if (pt['CONTRAATAQUE']) subtipos.push(`CA:${pt['CONTRAATAQUE']}`);
        if (pt['OTRO']) subtipos.push(`OT:${pt['OTRO']}`);
        const detallePar = !esPort ? '-' : (subtipos.length ? subtipos.join(' · ') : `${j.paradas} (s/tipo)`);
        html += `
            <tr>
                <td>${j.id_equipo}</td>
                <td>${j.numero_camiseta}</td>
                <td style="text-align: left;">${etiquetaNombre(j)} ${j.es_portero ? '(P)' : ''}</td>
                <td>${j.goles} / ${j.lanzamientos_totales}</td>
                <td>${j.eficiencia_tiro}%</td>
                <td>${j.asistencias}</td>
                <td>${esPort ? j.paradas + ' / ' + (j.tiros_recibidos || 0) : '-'}</td>
                <td>${esPort ? j.efectividad_portero + '%' : '-'}</td>
                <td style="font-size: 0.85rem;">${detallePar}</td>
                <td>${esPort ? j.gki : '-'}</td>
                <td>${j.exclusiones_2min}</td>
                <td>${j.perdidas}</td>
            </tr>
        `;
    });
    tbody.innerHTML = html;
}

function renderKpis(equipos) {
    (equipos || []).forEach(eq => {
        const suf = eq.id_equipo === 'A' ? 'a' : 'b';
        const box = document.getElementById(`kpi-${suf}`);
        if (!box) return;
        box.innerHTML = `
            <div><div class="kpi-val">${eq.goles}</div><div class="kpi-label">Goles</div></div>
            <div><div class="kpi-val">${eq.lanzamientos}</div><div class="kpi-label">Tiros</div></div>
            <div><div class="kpi-val">${eq.eficiencia_tiro}%</div><div class="kpi-label">Eficacia (${eq.goles}/${eq.lanzamientos})</div></div>
            <div><div class="kpi-val">${eq.ataques ?? 0}</div><div class="kpi-label">Ataques</div></div>
            <div><div class="kpi-val">${eq.eficacia_ataque ?? 0}%</div><div class="kpi-label">Efic. ataque</div></div>
            <div><div class="kpi-val">${eq.perdidas ?? 0}</div><div class="kpi-label">Pérdidas</div></div>
            <div><div class="kpi-val">${eq.asistencias ?? 0}</div><div class="kpi-label">Asistencias</div></div>
            <div><div class="kpi-val">${eq.robos ?? 0}</div><div class="kpi-label">Robos</div></div>
            <div><div class="kpi-val">${eq.bloqueos ?? 0}</div><div class="kpi-label">Bloqueos</div></div>
            <div><div class="kpi-val">${eq.tiros_fallados ?? 0}/${eq.tiros_detenidos ?? 0}</div><div class="kpi-label">Fallados/Detenidos</div></div>
            <div><div class="kpi-val">${eq.exclusiones}</div><div class="kpi-label">Excl. 2m</div></div>
        `;
    });
}

function filaVentana(b, etiqueta, fuerte) {
    const efic = eq => eq.tiros ? Math.round(eq.goles / eq.tiros * 1000) / 10 : 0;
    const eficAt = eq => eq.ataques ? Math.round(eq.goles / eq.ataques * 1000) / 10 : 0;
    const celda = v => fuerte ? `<td><strong>${v}</strong></td>` : `<td>${v}</td>`;
    return `<tr${fuerte ? ' style="background: var(--bg-card-hover);"' : ''}>
        <td><strong>${etiqueta}</strong></td>
        ${celda(b.A.goles)}<td>–</td>${celda(b.B.goles)}
        ${celda(b.A.tiros)}<td>–</td>${celda(b.B.tiros)}
        ${celda(efic(b.A) + '%')}<td>–</td>${celda(efic(b.B) + '%')}
        ${celda(b.A.ataques)}<td>–</td>${celda(b.B.ataques)}
        ${celda(eficAt(b.A) + '%')}<td>–</td>${celda(eficAt(b.B) + '%')}
        ${celda(b.A.perdidas)}<td>–</td>${celda(b.B.perdidas)}
        ${celda(b.A.paradas)}<td>–</td>${celda(b.B.paradas)}
    </tr>`;
}

function renderBloques(bloques, ventanas) {
    const box = document.getElementById('bloques-tabla');
    if (!box) return;
    if ((!bloques || !bloques.length) && (!ventanas || !ventanas.length)) {
        box.innerHTML = '<p style="color: var(--text-muted);">Todavía no hay eventos.</p>';
        return;
    }
    let html = `<table class="stats-table"><thead><tr>
        <th>Bloque</th><th colspan="3">Goles (A – B)</th><th colspan="3">Tiros (A – B)</th>
        <th colspan="3">Efic. tiro (A – B)</th><th colspan="3">Ataques (A – B)</th>
        <th colspan="3">Efic. ataque (A – B)</th><th colspan="3">Pérdidas (A – B)</th>
        <th colspan="3">Paradas (A – B)</th>
    </tr></thead><tbody>`;
    (bloques || []).forEach(b => { html += filaVentana(b, `${b.etiqueta}'`, false); });
    (ventanas || []).forEach(v => {
        const hay = ['ataques', 'goles', 'tiros', 'perdidas', 'paradas']
            .some(k => (v.A && v.A[k]) || (v.B && v.B[k]));
        if (v.etiqueta === 'Prórroga' && !hay) return; // no mostrar prórroga vacía
        html += filaVentana(v, v.etiqueta, true);
    });
    box.innerHTML = html + '</tbody></table>';
}

function renderContexto7m(ctx) {
    const box = document.getElementById('contexto7m-tabla');
    if (!box) return;
    if (!ctx || !ctx.A || !ctx.B || (ctx.A.tiros + ctx.B.tiros) === 0) {
        box.innerHTML = '<p style="color: var(--text-muted); text-align: center;">Sin lanzamientos de 7 m registrados.</p>';
        return;
    }
    const filas = [
        ['Global', null],
        ['Empatado', 'empatado'],
        ['Diferencia ≤ 2', 'ajustado'],
        ['1T', '1T'],
        ['2T', '2T'],
        ['Prórroga', 'Prórroga'],
        ["Últimos 5'", "últimos 5'"],
    ];
    const val = (eq, clave) => clave ? (ctx[eq].contextos || {})[clave] || { tiros: 0, goles: 0, eficacia: 0 }
                                     : ctx[eq];
    let html = `<table class="stats-table"><thead><tr>
        <th>Contexto 7M</th><th colspan="3">Tiros (A – B)</th><th colspan="3">Goles (A – B)</th>
        <th colspan="3">Eficacia (A – B)</th>
    </tr></thead><tbody>`;
    filas.forEach(([nombre, clave]) => {
        if (clave === 'Prórroga' && (val('A', clave).tiros + val('B', clave).tiros) === 0) return;
        const a = val('A', clave), b = val('B', clave);
        const fuerte = clave === null ? ' style="background: var(--bg-card-hover);"' : '';
        const cel = v => clave === null ? `<td><strong>${v}</strong></td>` : `<td>${v}</td>`;
        html += `<tr${fuerte}>
            <td><strong>${nombre}</strong></td>
            ${cel(a.tiros)}<td>–</td>${cel(b.tiros)}
            ${cel(a.goles)}<td>–</td>${cel(b.goles)}
            ${cel(a.eficacia + '%')}<td>–</td>${cel(b.eficacia + '%')}
        </tr>`;
    });
    box.innerHTML = html + '</tbody></table>';
}

function renderTipos(equipos) {
    const box = document.getElementById('tipos-tabla');
    if (!box) return;
    const eq = {};
    (equipos || []).forEach(e => { eq[e.id_equipo] = e; });
    if (!eq.A || !eq.B || !eq.A.lanzamientos_por_tipo) {
        box.innerHTML = '<p style="color: var(--text-muted);">Todavía no hay tiros.</p>';
        return;
    }
    const filas = [
        ['6 metros', '6M'],
        ['9 metros', '9M'],
        ['7 metros', '7M'],
        ['Contraataque', 'CONTRAATAQUE'],
        ['Otro', 'OTRO'],
    ];
    const efic = (t, g) => t ? Math.round(g / t * 1000) / 10 : 0;
    let html = `<table class="stats-table"><thead><tr>
        <th>Tipo</th><th colspan="3">Tiros (A – B)</th><th colspan="3">Goles (A – B)</th>
        <th colspan="3">Eficacia (A – B)</th>
    </tr></thead><tbody>`;
    const suma = (e, tipos) => tipos.reduce((acc, t) => {
        const c = (e.lanzamientos_por_tipo || {})[t] || { tiros: 0, goles: 0 };
        acc.tiros += c.tiros || 0; acc.goles += c.goles || 0;
        return acc;
    }, { tiros: 0, goles: 0 });
    filas.forEach(([nombre, clave]) => {
        const a = (eq.A.lanzamientos_por_tipo || {})[clave] || { tiros: 0, goles: 0 };
        const b = (eq.B.lanzamientos_por_tipo || {})[clave] || { tiros: 0, goles: 0 };
        html += `<tr>
            <td><strong>${nombre}</strong></td>
            <td>${a.tiros}</td><td>–</td><td>${b.tiros}</td>
            <td>${a.goles}</td><td>–</td><td>${b.goles}</td>
            <td>${efic(a.tiros, a.goles)}%</td><td>–</td><td>${efic(b.tiros, b.goles)}%</td>
        </tr>`;
    });
    // Ataque posicional = todo lo que no es contraataque (formato del doc científico)
    const posA = suma(eq.A, ['6M', '9M', '7M', 'OTRO']);
    const posB = suma(eq.B, ['6M', '9M', '7M', 'OTRO']);
    html += `<tr style="background: var(--bg-card-hover);">
        <td><strong>Ataque posicional</strong></td>
        <td><strong>${posA.tiros}</strong></td><td>–</td><td><strong>${posB.tiros}</strong></td>
        <td><strong>${posA.goles}</strong></td><td>–</td><td><strong>${posB.goles}</strong></td>
        <td><strong>${efic(posA.tiros, posA.goles)}%</strong></td><td>–</td><td><strong>${efic(posB.tiros, posB.goles)}%</strong></td>
    </tr>`;
    box.innerHTML = html + '</tbody></table>';
}

function renderTeamNames(data) {
    const nombres = {};
    (data.equipos || []).forEach(eq => { nombres[eq.id_equipo] = eq.nombre; });
    const a = nombres['A'] || data.partido.nombre_equipo_a || 'Equipo A';
    const b = nombres['B'] || data.partido.nombre_equipo_b || 'Equipo B';
    ['goles-a-nombre', 'zonas-a-nombre', 'heat-a-nombre', 'kpi-a-nombre'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.textContent = a;
    });
    ['goles-b-nombre', 'zonas-b-nombre', 'heat-b-nombre', 'kpi-b-nombre'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.textContent = b;
    });
}

const COLORES_EQUIPO = { A: 'rgba(0, 81, 213, 0.8)', B: 'rgba(124, 58, 237, 0.8)' };
const BORDES_EQUIPO = { A: 'rgba(0, 81, 213, 1)', B: 'rgba(124, 58, 237, 1)' };
// Orden canónico para que ambas donas usen siempre los mismos colores por zona
const ORDEN_ZONAS = [
    ['6M', '#e74c3c'],
    ['9M', '#3498db'],
    ['7M', '#f1c40f'],
    ['CONTRAATAQUE', '#2ecc71'],
    ['S/D', '#9b59b6']
];

function etiquetaZona(k) {
    if (k === 'CONTRAATAQUE') return 'CONTRAATAQUE';
    if (k === 'LANZAMIENTO') return 'S/D';
    return k.replace('LANZAMIENTO_', '').replace('_', ' ');
}

function renderCharts(jugadores, porEquipo) {
    ['A', 'B'].forEach(eq => {
        // Barras: top 5 goleadores del equipo
        const goleadores = jugadores
            .filter(j => j.id_equipo === eq && j.goles > 0)
            .sort((a, b) => b.goles - a.goles)
            .slice(0, 5);

        new Chart(document.getElementById(eq === 'A' ? 'chartGolesA' : 'chartGolesB'), {
            type: 'bar',
            data: {
                labels: goleadores.map(j => etiquetaBarra(j)),
                datasets: [{
                    label: 'Goles',
                    data: goleadores.map(j => j.goles),
                    backgroundColor: COLORES_EQUIPO[eq],
                    borderColor: BORDES_EQUIPO[eq],
                    borderWidth: 1
                }]
            },
            options: {
                responsive: true,
                color: '#0b1c30',
                scales: {
                    y: { beginAtZero: true, ticks: { stepSize: 1, color: '#64748b' }, grid: { color: '#e2e8f0' } },
                    x: { ticks: { color: '#64748b' }, grid: { color: '#f1f5f9' } }
                },
                plugins: {
                    legend: { labels: { color: '#0b1c30' } }
                }
            }
        });

        // Dona: distribución de zonas del equipo (colores estables por zona)
        const conteo = {};
        const zt = (porEquipo[eq] && porEquipo[eq].zonas_tiro) || {};
        Object.entries(zt).forEach(([k, v]) => {
            const et = etiquetaZona(k);
            conteo[et] = (conteo[et] || 0) + v;
        });

        new Chart(document.getElementById(eq === 'A' ? 'chartZonasA' : 'chartZonasB'), {
            type: 'doughnut',
            data: {
                labels: ORDEN_ZONAS.map(([et]) => et),
                datasets: [{
                    data: ORDEN_ZONAS.map(([et]) => conteo[et] || 0),
                    backgroundColor: ORDEN_ZONAS.map(([, c]) => c),
                    borderWidth: 0
                }]
            },
            options: {
                responsive: true,
                color: '#0b1c30',
                plugins: {
                    legend: { position: 'bottom', labels: { color: '#0b1c30' } }
                }
            }
        });
    });
}

function renderHeatmap(containerId, porteria) {
    const container = document.getElementById(containerId);
    if (!container) return;
    const order = ['TL', 'TC', 'TR', 'ML', 'MC', 'MR', 'BL', 'BC', 'BR'];
    
    let html = '';
    order.forEach(zona => {
        const stats = porteria[zona] || {goles: 0, paradas: 0, fallos: 0, total: 0};
        let bg = 'rgba(0, 81, 213, 0.06)';
        
        if (stats.total > 0) {
            const pGoles = stats.goles / stats.total;
            const pParadas = stats.paradas / stats.total;
            
            if (pGoles >= pParadas && stats.goles > 0) {
                // Dominio Goles -> Rojo
                bg = `rgba(220, 38, 38, ${0.15 + (pGoles * 0.65)})`;
            } else if (pParadas > pGoles && stats.paradas > 0) {
                // Dominio Paradas -> Azul
                bg = `rgba(0, 81, 213, ${0.15 + (pParadas * 0.65)})`;
            }
        }

        html += `
            <div class="goal-zone heatmap-cell" style="background-color: ${bg}; pointer-events: none; outline: 1px solid rgba(11,28,48,0.15);">
                <div style="font-weight: bold; margin-bottom: 2px;">${stats.total} tiros</div>
                ${stats.goles > 0 ? `<div style="color: #93000a;">${stats.goles} G</div>` : ''}
                ${stats.paradas > 0 ? `<div style="color: #003ea8;">${stats.paradas} P</div>` : ''}
            </div>
        `;
    });
    
    container.innerHTML = html;
}
