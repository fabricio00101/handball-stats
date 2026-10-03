/**
 * Herramienta de portería: capturar y analizar los tiros contra nuestro arco.
 *
 * La contraparte de la captura normal. Acá el dato central es el PUNTO de donde
 * salió el tiro (coordenada_x/y en metros) y el cuadrante de origen lo deriva el
 * servidor a partir de ese punto: el botón nunca manda un cuadrante.
 *
 * El arco de destino sigue siendo el 3×3 de siempre. Son 3 metros de ancho y no
 * se apunta con precisión desde un teléfono; en cambio la media cancha mide
 * 20×20 y a 460 px de ancho hay unos 23 px por metro, así que un toque sí cae
 * donde uno lo quiso.
 */
const Porteria = (() => {

    // --- La media cancha en metros ---------------------------------------
    // x: lateral desde el centro del arco, -10 (izq) a 10 (der), desde la
    //    mirada de quien ataca.
    // y: distancia a la línea de fondo, 0 en la línea, 20 en el medio.
    const MEDIO = 10;            // |x| <= 10
    const FONDO = 20;            // 0 <= y <= 20
    const TERCIO = MEDIO / 3;    // el corte de columna está a 3,33 m
    const FRANJA_6M = 6;
    const FRANJA_9M = 9;

    const SIGMA_M = 2.0;         // radio del kernel, fijo en metros y no en
                                 // píxeles: con 8 tiros o con 200, el círculo
                                 // tiene que medir lo mismo en la cancha
    const ZONAS_ARCO = ['TL', 'TC', 'TR', 'ML', 'MC', 'MR', 'BL', 'BC', 'BR'];

    // Un punto por tiro, con su color de resultado. La densidad del fondo va
    // en violeta para no competir con estos cuatro.
    const COLOR_PUNTO = {
        GOL: '#dc2626',
        PARADA: '#0051d5',
        FALLO: '#94a3b8',
        BLOQUEADO: '#d97706'
    };

    const FILA_TXT = { B: 'la franja de 0-6 m', M: 'la franja de 6-9 m', T: 'más de 9 m' };
    const COL_TXT = { L: 'izquierda', C: 'el centro', R: 'derecha' };
    const COL_TXT_ARCO = { L: 'izquierda', C: 'el centro', R: 'derecha' };

    const estado = {
        matchId: null,
        vista: 'capturar',
        keeperId: null,
        origen: null,        // {x, y}
        resultado: null,
        zona: null,
        es7m: false,
        contraataque: false,
        ultimo: null,        // {client_event_id, ...} para poder anular
        filtro: '',          // arquero del análisis
        rivalId: null        // rival genérico, lo manda el servidor (ver init)
    };

    // =====================================================================
    // Geometría
    // =====================================================================

    function svgX(x) { return x + MEDIO; }
    function svgY(y) { return FONDO - y; }

    /** Cuadrante de origen, espejo de services/eventos.py.
     *
     *  Se calcula acá solo para el texto que se muestra mientras se toca: el
     *  que se guarda es el del servidor, y los dos cortan en el mismo lado de
     *  las líneas, así que nunca se contradicen.
     */
    function zonaOrigen(x, y) {
        const col = x < -TERCIO ? 'L' : (x > TERCIO ? 'R' : 'C');
        const fila = y < FRANJA_6M ? 'B' : (y < FRANJA_9M ? 'M' : 'T');
        return fila + col;
    }

    function distancia(y, es_7m) {
        // Misma regla que distancia_desde_coordenada en services/eventos.py: el
        // penalti va a 7 m aunque caiga dentro de la franja de 9.
        if (es_7m) return '7M';
        if (y < FRANJA_6M) return '6M';
        if (y < FRANJA_9M) return '9M';
        return null;
    }

    function metrosEnChispa(ev, rect) {
        const cliente = (ev.touches && ev.touches[0]) || ev;
        const sx = (cliente.clientX - rect.left) / rect.width * FONDO;
        const sy = (cliente.clientY - rect.top) / rect.height * FONDO;
        // Un toque en el borde es un tiro desde el borde: se recorta en vez de
        // dejarlo fuera, que el servidor lo rechazaría por error de redondeo.
        const x = Math.max(-MEDIO, Math.min(MEDIO, sx - MEDIO));
        const y = Math.max(0, Math.min(FONDO, FONDO - sy));
        return { x: Math.round(x * 10) / 10, y: Math.round(y * 10) / 10 };
    }

    // =====================================================================
    // La cancha
    // =====================================================================

    // Un solo lugar donde vive el dibujo, montado en los dos lienzos (el de
    // captura y el del mapa). Los cortes de fila no se dibujan aparte: la línea
    // de 9 m y el arco de 6 m YA son los cortes, así que se ven las líneas
    // verdaderas en vez de una grilla inventada encima.
    const CANCHA_SVG = `
        <rect x="0" y="0" width="20" height="20" fill="none" stroke="#cbd5e1" stroke-width="0.18"/>
        <line x1="0" y1="0" x2="20" y2="0" stroke="#cbd5e1" stroke-width="0.18"/>
        <line x1="0" y1="0" x2="0" y2="20" stroke="#cbd5e1" stroke-width="0.18"/>
        <line x1="20" y1="0" x2="20" y2="20" stroke="#cbd5e1" stroke-width="0.18"/>
        <line x1="0" y1="20" x2="20" y2="20" stroke="#dc2626" stroke-width="0.35"/>
        <rect x="8.5" y="19" width="3" height="1" fill="#dc2626" fill-opacity="0.16"
              stroke="#dc2626" stroke-width="0.2"/>
        <path d="M 7,20 A 3,3 0 0 0 13,20" fill="none" stroke="#0051d5"
              stroke-width="0.22" opacity="0.55"/>
        <line x1="0" y1="13" x2="20" y2="13" stroke="#94a3b8" stroke-width="0.12"
              stroke-dasharray="0.7 0.5"/>
        <line x1="0" y1="11" x2="20" y2="11" stroke="#94a3b8" stroke-width="0.12"
              stroke-dasharray="0.7 0.5"/>
        <line x1="6.6667" y1="0" x2="6.6667" y2="20" stroke="rgba(11,28,48,0.16)"
              stroke-width="0.1" stroke-dasharray="0.4 0.35"/>
        <line x1="13.3333" y1="0" x2="13.3333" y2="20" stroke="rgba(11,28,48,0.16)"
              stroke-width="0.1" stroke-dasharray="0.4 0.35"/>
    `;

    function montarCanchas() {
        document.querySelectorAll('[data-plantilla-cancha]').forEach(svg => {
            svg.innerHTML = CANCHA_SVG;
        });
    }

    /** Pinta los puntitos de un svg de 20×20 (los dos tienen el mismo viewBox).
     *
     *  Un punto sin resultado todavía (el que se está por registrar) se dibuja
     *  como un aro vacío, no como un puntito de color: si se pintara con el rojo
     *  del gol parecería que ya se registró un gol.
     */
    function pintarPuntos(svg, puntos) {
        if (!svg) return;
        svg.innerHTML = puntos.map(p => {
            const cx = svgX(p.x).toFixed(2);
            const cy = svgY(p.y).toFixed(2);
            if (p.r === 'PUNTO') {
                return `<circle cx="${cx}" cy="${cy}" r="0.42" fill="none" `
                     + `stroke="#0b1c30" stroke-width="0.16"/>`;
            }
            const color = COLOR_PUNTO[p.r] || COLOR_PUNTO.FALLO;
            return `<circle class="pt-dot" cx="${cx}" cy="${cy}" r="0.34" fill="${color}"/>`;
        }).join('');
    }

    // =====================================================================
    // Mapa de calor (KDE sobre canvas, sin librerías)
    // =====================================================================

    const RAMPA = [
        { a: 0.00, c: [237, 233, 254] },
        { a: 0.22, c: [196, 181, 253] },
        { a: 0.48, c: [147, 110, 255] },
        { a: 0.74, c: [91, 63, 214] },
        { a: 1.00, c: [49, 26, 149] }
    ];

    function colorRampa(t) {
        t = Math.max(0, Math.min(1, t));
        for (let i = 0; i < RAMPA.length - 1; i++) {
            const lo = RAMPA[i], hi = RAMPA[i + 1];
            if (t <= hi.a) {
                const f = (t - lo.a) / (hi.a - lo.a || 1);
                return [
                    Math.round(lo.c[0] + (hi.c[0] - lo.c[0]) * f),
                    Math.round(lo.c[1] + (hi.c[1] - lo.c[1]) * f),
                    Math.round(lo.c[2] + (hi.c[2] - lo.c[2]) * f)
                ];
            }
        }
        return RAMPA[RAMPA.length - 1].c;
    }

    /**
     * Dibuja la densidad de los puntos.
     *
     * Un kernel gaussiano por tiro, sumado en modo aditivo ('lighter'): el alfa
     * acumulado ES la densidad. Después se pasa getImageData y el alfa se
     * convierte en color. Se normaliza contra el alfa máximo para que el mapa
     * se lea siempre, aunque eso haga que la escala sea relativa al tiro más
     * caliente y no absoluta.
     */
    function pintarCalor(canvas, puntos) {
        if (!canvas) return;
        const caja = canvas.parentElement.getBoundingClientRect();
        if (!caja.width) return;

        const dpr = window.devicePixelRatio || 1;
        canvas.width = Math.round(caja.width * dpr);
        canvas.height = Math.round(caja.height * dpr);

        const ctx = canvas.getContext('2d');
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        ctx.clearRect(0, 0, caja.width, caja.height);
        if (!puntos.length) return;

        const pxPorM = caja.width / FONDO;
        const radio = SIGMA_M * pxPorM;

        ctx.globalCompositeOperation = 'lighter';
        for (const p of puntos) {
            const cx = svgX(p.x) * pxPorM;
            const cy = svgY(p.y) * pxPorM;
            const g = ctx.createRadialGradient(cx, cy, 0, cx, cy, radio);
            g.addColorStop(0, 'rgba(255,255,255,0.55)');
            g.addColorStop(0.5, 'rgba(255,255,255,0.16)');
            g.addColorStop(1, 'rgba(255,255,255,0)');
            ctx.fillStyle = g;
            // El cuadrado del kernel: alcanza con cubrir su diámetro.
            ctx.fillRect(cx - radio, cy - radio, radio * 2, radio * 2);
        }
        ctx.globalCompositeOperation = 'source-over';

        const img = ctx.getImageData(0, 0, canvas.width, canvas.height);
        const d = img.data;
        let max = 0;
        for (let i = 3; i < d.length; i += 4) if (d[i] > max) max = d[i];
        if (!max) return;

        // El alfa acumulado ES la densidad: se convierte en color y el píxel
        // queda opaco, porque la intensidad ya la lleva el color y no la
        // transparencia (si no, las zonas claras se verían desvaídas sobre
        // la tarjeta blanca en vez de como un violeta claro).
        for (let i = 0; i < d.length; i += 4) {
            const [r, g, b] = colorRampa(d[i + 3] / max);
            d[i] = r;
            d[i + 1] = g;
            d[i + 2] = b;
            d[i + 3] = d[i + 3] > 0 ? 255 : 0;
        }
        ctx.putImageData(img, 0, 0);
    }

    // Un penalti se tira siempre desde el mismo sitio: 7 m, sobre el centro del
    // arco. Por eso el chip de 7m no es una etiqueta más, sino que FIJA el
    // punto. Si se dejaran independientes se podría guardar un tiro marcado 7m
    // con el punto a 12 m, y esos dos datos se contradicen sin que nada lo avise:
    // el reparto por tipo lo contaría como 7 m y el mapa lo dibujaría lejos.
    // Es la misma razón por la que un LANZAMIENTO_7M legacy no guarda punto
    // (ver normalizar_evento_legacy en services/eventos.py).
    const PUNTO_7M = { x: 0, y: 7 };

    function esPunto7M(p) {
        return !!p && p.x === PUNTO_7M.x && p.y === PUNTO_7M.y;
    }

    /** Activa o desactiva el chip de 7m, con el punto que corresponde. */
    function cambiar7m(encendido) {
        if (encendido) {
            estado.es7m = true;
            estado.origen = { ...PUNTO_7M };
            pintarPuntoElegido();
            pintarLectura();
            return;
        }
        estado.es7m = false;
        // Solo se borra el punto si es el que puso el chip. Si el operador había
        // tocado la cancha a propósito, no se le roba: si no, al apagar el chip
        // le quedaría un tiro de 7 m rotulado como si fuera de 6 m.
        if (esPunto7M(estado.origen)) {
            estado.origen = null;
            pintarPuntoElegido();
            pintarLectura();
        }
    }

    // =====================================================================
    // Captura
    // =====================================================================

    function pintarLectura() {
        const el = document.getElementById('pt-readout');
        if (!el) return;
        if (!estado.origen) {
            el.innerHTML = '<span style="color: var(--text-muted);">Sin punto: tocá la cancha.</span>';
            return;
        }
        const { x, y } = estado.origen;
        const cod = zonaOrigen(x, y);
        const dist = distancia(y, estado.es7m);
        el.innerHTML =
            `<span>📍 <b>${x.toFixed(1)} m</b> del eje, <b>${y.toFixed(1)} m</b> de la línea</span>` +
            `<span class="pt-chip">${cod} · ${FILA_TXT[cod[0]]}, ${COL_TXT[cod[1]]}</span>` +
            (dist ? `<span class="pt-chip">${dist}</span>` : '<span class="pt-chip">más de 9 m</span>') +
            // Si el 7m puso el punto, que se note: de lo contrario el operador
            // busca con el dedo un 7m que ya está elegido y no lo encuentra.
            (estado.es7m ? '<span class="pt-chip">🎯 penalti (punto fijo)</span>' : '');
    }

    function pintarZonaHabilitada() {
        const cajaArco = document.getElementById('pt-arco');
        if (!cajaArco) return;
        // Gol y parada necesitan dónde entró; fallo y bloqueado no.
        const haceFalta = estado.resultado === 'GOL' || estado.resultado === 'PARADA';
        cajaArco.classList.toggle('armed', haceFalta);
        const hint = document.getElementById('pt-zona-hint');
        if (hint) {
            hint.textContent = haceFalta
                ? 'Ahora sí: tocá la zona del arco.'
                : 'No hace falta para fallo o bloqueado.';
        }
    }

    function pintarPuntoElegido() {
        pintarPuntos(document.getElementById('pt-puntos-capturar'),
                     estado.origen ? [{ ...estado.origen, r: 'PUNTO' }] : []);
    }

    function marcarZonaEnDOM() {
        document.querySelectorAll('#pt-arco .goal-zone').forEach(z => {
            z.classList.toggle('selected', z.dataset.zona === estado.zona);
        });
        const readout = document.getElementById('pt-readout-arco');
        if (readout) {
            readout.innerHTML = estado.zona
                ? `<span class="pt-chip">${estado.zona} · ${COL_TXT_ARCO[estado.zona[1]]}, `
                  + `${estado.zona[0] === 'B' ? 'abajo' : estado.zona[0] === 'M' ? 'media' : 'arriba'}</span>`
                : '<span style="color: var(--text-muted);">Sin zona de arco.</span>';
        }
    }

    function marcarResultadoEnDOM() {
        document.querySelectorAll('#pt-resultados [data-outcome]').forEach(b => {
            b.classList.toggle('selected', b.dataset.outcome === estado.resultado);
        });
    }

    function decirUltimo(ev) {
        const t = document.getElementById('pt-ultimo-titulo');
        const d = document.getElementById('pt-ultimo-detalle');
        const btn = document.getElementById('pt-anular');
        if (!t || !d) return;
        if (!ev) {
            t.textContent = 'Todavía no registraste ningún tiro';
            d.textContent = 'Empezá tocando la cancha.';
            if (btn) btn.disabled = true;
            return;
        }
        const ETIQUETA = { GOL: '⚽ Gol', PARADA: '🧤 Parada', FALLO: '✗ Fallo', BLOQUEADO: '🛑 Bloqueado' };
        t.textContent = `${ETIQUETA[ev.resultado] || ev.resultado} · ${ev.tiempo_juego}`;
        const partes = [];
        if (ev.origen) partes.push(`${ev.origen} (${ev.origen_txt})`);
        if (ev.zona) partes.push(`arco ${ev.zona}`);
        if (ev.es_7m) partes.push('7m');
        if (ev.contraataque) partes.push('contraataque');
        d.textContent = partes.length ? partes.join(' · ') : 'sin punto';
        if (btn) btn.disabled = false;
    }

    function avisar(texto, malo) {
        const previo = document.getElementById('pt-toast');
        if (previo) previo.remove();
        const t = document.createElement('div');
        t.id = 'pt-toast';
        t.className = 'toast';
        t.style.backgroundColor = malo ? 'var(--fail)' : 'var(--success)';
        t.textContent = texto;
        document.body.appendChild(t);
        setTimeout(() => t.remove(), 2600);
    }

    function guardar() {
        if (!estado.keeperId) {
            avisar('Elegí quién está en el arco primero', true);
            return;
        }
        if (!estado.origen) {
            avisar('Tocá la cancha para decir de dónde salió el tiro', true);
            return;
        }
        // La zona del arco se puede tocar sin haber pasado por los botones: sin
        // esto se guardaría un lanzamiento sin resultado, que en el análisis
        // cuenta como tiro pero no como parada ni gol ni fallo, y termina
        // inflando el total sin explicar nada.
        if (!estado.resultado) {
            avisar('Elegí primero qué pasó con el tiro', true);
            return;
        }
        const necesitaZona = estado.resultado === 'GOL' || estado.resultado === 'PARADA';
        if (necesitaZona && !estado.zona) {
            avisar('Gol y parada necesitan la zona del arco', true);
            return;
        }

        // El tiro se le carga al rival generico, no a un jugador del rival: en
        // la captura de porteria no hay un lanzador identificado, hay un arco.
        if (!estado.rivalId) {
            avisar('Este partido no tiene rival genérico', true);
            return;
        }

        const cod = zonaOrigen(estado.origen.x, estado.origen.y);
        const payload = {
            id_partido: estado.matchId,
            id_jugador: estado.rivalId,
            tipo_evento: 'LANZAMIENTO',
            resultado: estado.resultado,
            tiempo_juego: (typeof TimerModule !== 'undefined') ? TimerModule.getCurrentTime() : '00:00',
            periodo: (typeof TimerModule !== 'undefined') ? TimerModule.getPeriodo() : 1,
            id_portero: estado.keeperId,
            coordenada_x: estado.origen.x,
            coordenada_y: estado.origen.y,
            zona_porteria: estado.zona,
            es_7m: estado.es7m ? 1 : 0,
            es_contraataque: estado.contraataque ? 1 : 0
        };

        const guardado = OfflineQueue.enqueue(estado.matchId, payload);

        // Se arma el registro de lo último con el punto ya derivado, para que
        // el operador pueda verificar el toque sin esperar al servidor.
        estado.ultimo = {
            client_event_id: guardado.client_event_id,
            resultado: estado.resultado,
            tiempo_juego: payload.tiempo_juego,
            origen: cod,
            origen_txt: `${estado.origen.x.toFixed(1)}m / ${estado.origen.y.toFixed(1)}m`,
            zona: estado.zona,
            es_7m: estado.es7m,
            contraataque: estado.contraataque
        };
        decirUltimo(estado.ultimo);

        avisar(`${estado.resultado} guardado`, false);

        // Solo se limpia lo que ya se usó: el punto y el resultado se consumen,
        // la zona también, y los chips vuelven a cero para no arrastrarlos.
        estado.origen = null;
        estado.resultado = null;
        estado.zona = null;
        estado.es7m = false;
        estado.contraataque = false;
        pintarPuntoElegido();
        pintarLectura();
        marcarZonaEnDOM();
        marcarResultadoEnDOM();
        pintarZonaHabilitada();
        document.querySelectorAll('#pt-toggles .pt-toggle').forEach(b => b.classList.remove('on'));
        const panelAcciones = document.getElementById('pt-panel-acciones');
        if (panelAcciones) panelAcciones.style.display = 'none';
        const panelArco = document.getElementById('pt-panel-arco');
        if (panelArco) panelArco.style.display = 'none';
    }

    async function anularUltimo() {
        if (!estado.ultimo) return;
        const id = estado.ultimo.client_event_id;
        OfflineQueue.enqueue(estado.matchId, { op: 'void', client_event_id: id });
        estado.ultimo = null;
        decirUltimo(null);
        avisar('Tiro anulado', false);
    }

    // =====================================================================
    // Análisis
    // =====================================================================

    function kpi(titulo, valor, color, nota) {
        return `<div class="chart-box" style="margin:0; min-width:150px;">
            <div style="font-size:0.72rem; text-transform:uppercase; letter-spacing:0.05em;
                        color: var(--text-muted);">${titulo}</div>
            <div style="font-family: var(--font-mono); font-weight:700; font-size:1.7rem;
                        color: ${color};">${valor}</div>
            ${nota ? `<div style="font-size:0.72rem; color: var(--text-muted);">${nota}</div>` : ''}
        </div>`;
    }

    function pintarKpis(d) {
        const t = d.totales;
        const aPuerta = t.goles + t.paradas;
        const pct = aPuerta ? Math.round(t.paradas / aPuerta * 100) : 0;
        document.getElementById('pt-kpis').innerHTML = [
            kpi('Tiros', t.tiros, 'var(--text-main)', 'contra nuestro arco'),
            kpi('Paradas', t.paradas, 'var(--accent-blue)', `${t.fallos} fallos · ${t.bloqueados} bloqueados`),
            kpi('% Paradas', pct + '%', 'var(--accent-blue)', `de ${aPuerta} a puerta`),
            kpi('Goles', t.goles, 'var(--fail)', 'del rival, contra nosotros'),
            kpi('Sin punto', t.sin_punto, t.sin_punto ? 'var(--warning)' : 'var(--text-muted)',
                'no entran al mapa de calor')
        ].join('');
    }

    function celda(c) {
        if (!c.total) {
            return `<div class="pt-cell" style="background: var(--bg-main);">
                        <div class="pt-cell-vacio">—</div></div>`;
        }
        return `<div class="pt-cell" style="background: var(--bg-card-highest);">
                    <div class="pt-cell-tot">${c.total}</div>
                    ${c.goles ? `<div class="pt-cell-gol">${c.goles} gol${c.goles > 1 ? 'es' : ''}</div>` : ''}
                    ${c.paradas ? `<div class="pt-cell-parada">${c.paradas} parada${c.paradas > 1 ? 's' : ''}</div>` : ''}
                    ${(c.fallos + c.bloqueados) ? `<div class="pt-cell-vacio">${c.fallos + c.bloqueados} fuera</div>` : ''}
                </div>`;
    }

    function pintarGrillaArco(d) {
        document.getElementById('pt-grilla-arco').innerHTML =
            ZONAS_ARCO.map(z => celda(d.arco[z] || {})).join('');
    }

    function pintarGrillaOrigen(d) {
        // Filas de lejos hacia cerca para que "arriba" sea más lejos, igual que
        // en la cancha. Las columnas L, C, R como en el arco.
        const filas = ['T', 'M', 'B'];
        const cols = ['L', 'C', 'R'];
        document.getElementById('pt-grilla-origen').innerHTML =
            filas.flatMap(f => cols.map(c => celda(d.origen[f + c] || {}))).join('');
    }

    function pintarMapa(d) {
        pintarCalor(document.getElementById('pt-heat'), d.puntos);
        pintarPuntos(document.getElementById('pt-puntos'), d.puntos);
    }

    function pintarTipos(d) {
        const ETIQUETA = { '6M': '🎯 6 m', '9M': '🎯 9 m', '7M': '🎯 7 m (penalti)',
                           'CONTRAATAQUE': '⚡ Contraataque', 'OTRO': 'Sin distancia' };
        const claves = Object.keys(d.tipos || {});
        const cont = document.getElementById('pt-tipos');
        if (!claves.length) {
            cont.innerHTML = '<span style="color: var(--text-muted); font-size:0.85rem;">Todavía no hay tiros.</span>';
            return;
        }
        cont.innerHTML = claves.map(k => {
            const n = d.tipos[k];
            const pct = Math.round(n / d.totales.tiros * 100);
            return `<span class="pt-chip">${ETIQUETA[k] || k}: <b>${n}</b> (${pct}%)</span>`;
        }).join('');
    }

    function pintarTabla(d) {
        const cuerpo = document.getElementById('pt-tbody-porteros');
        if (!d.porteros.length) {
            cuerpo.innerHTML = `<tr><td colspan="9" style="color: var(--text-muted); padding:20px;">
                Todavía ningún tiro tiene arquero asignado. Registrá uno en la pestaña
                <b>Capturar</b> y aparece acá.</td></tr>`;
            return;
        }
        cuerpo.innerHTML = d.porteros.map(p => `
            <tr>
                <td style="font-family: var(--font-mono);">${p.numero}</td>
                <td style="text-align:left;">${p.tiene_nombre ? escapeHtml(p.nombre_corto) : '—'}</td>
                <td style="color: var(--accent-blue); font-weight:700;">${p.paradas}</td>
                <td>${p.tiros_recibidos}</td>
                <td style="font-weight:700;">${p.efectividad}%</td>
                <td style="color: var(--fail); font-weight:700;">${p.goles_encajados}</td>
                <td>${p.fallos}</td>
                <td>${p.bloqueados}</td>
                <td>${p.tiros}</td>
            </tr>`).join('');
    }

    function escapeHtml(s) {
        return String(s == null ? '' : s).replace(/[&<>"']/g, c => (
            { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
        ));
    }

    /**
     * La lectura en crudo.
     *
     * Sale de las coordenadas y no de un nombre de cuadrante preescrito: se
     * busca el punto más cargado y se cuenta qué pasó ahí. Es el mismo dato que
     * está en la grilla de arriba, dicho en una frase que se pueda repetir de
     * memoria en la charla del lunes.
     */
    function pintarLecturaAnalisis(d) {
        const el = document.getElementById('pt-lectura');
        const total = d.totales.tiros;
        if (!total) {
            el.innerHTML = 'Todavía no hay tiros en este partido.';
            return;
        }

        let mejor = null;
        for (const cod of Object.keys(d.origen)) {
            const c = d.origen[cod];
            if (c.total && (!mejor || c.total > mejor.c.total)) mejor = { cod, c };
        }

        const lineas = [];
        if (mejor) {
            const pct = Math.round(mejor.c.total / total * 100);
            const aPuerta = mejor.c.goles + mejor.c.paradas;
            lineas.push(`El <b>${pct}%</b> de los tiros sale de <b>${FILA_TXT[mejor.cod[0]]}</b> `
                      + `por la <b>${COL_TXT[mejor.cod[1]]}</b>.`);
            if (aPuerta) {
                lineas.push(`Ahí para <b>${mejor.c.paradas} de ${aPuerta}</b> `
                          + `(${Math.round(mejor.c.paradas / aPuerta * 100)}%).`);
            } else {
                lineas.push('Ahí no llegó ninguno a puerta.');
            }
        } else {
            lineas.push(`Hay <b>${total}</b> tiros, pero ninguno tiene el punto de origen anotado, `
                      + `así que no se puede decir de dónde salen.`);
        }

        // Y dónde se encaja el arco, que es la otra mitad del trabajo.
        let peorZona = null;
        for (const z of ZONAS_ARCO) {
            const c = d.arco[z];
            if (c && c.goles && (!peorZona || c.goles > peorZona.c.goles)) peorZona = { z, c };
        }
        if (peorZona) {
            lineas.push(`Al arco, la zona que más Encajó es la <b>${peorZona.z}</b> `
                      + `(${peorZona.z[1] === 'L' ? 'izquierda' : peorZona.z[1] === 'R' ? 'derecha' : 'al medio'}, `
                      + `${peorZona.z[0] === 'T' ? 'arriba' : peorZona.z[0] === 'M' ? 'media altura' : 'bajo'}): `
                      + `<b>${peorZona.c.goles}</b> gol${peorZona.c.goles > 1 ? 'es' : ''}.`);
        }

        el.innerHTML = lineas.join(' ');
    }

    function pintarAvisos(d) {
        const cont = document.getElementById('pt-avisos');
        const avisos = [];
        if (d.tiros_sin_arquero) {
            avisos.push(`<div class="pt-aviso">⚠️ <b>${d.tiros_sin_arquero}</b> `
                + `${d.tiros_sin_arquero === 1 ? 'tiro quedó' : 'tiros quedaron'} sin arquero: `
                + `no entran en la tabla de porteros. Volvé a <b>Capturar</b> y anulalos si `
                + `no corresponden.</div>`);
        }
        if (d.totales.sin_punto) {
            avisos.push(`<div class="pt-aviso">📍 <b>${d.totales.sin_punto}</b> `
                + `${d.totales.sin_punto === 1 ? 'tiro no tiene' : 'tiros no tienen'} anotado `
                + `de dónde salieron: cuenta en los números pero no aparece en el mapa de calor.</div>`);
        }
        if (!d.puntos.length && d.totales.sin_zona && !d.totales.sin_punto) {
            avisos.push('<div class="pt-aviso">Sin datos de origen ni de arco: los tiros se '
                + 'registraron sin la zona.</div>');
        }
        cont.innerHTML = avisos.join('');
    }

    function pintarFiltro(d) {
        const sel = document.getElementById('pt-filtro');
        const actual = estado.filtro;
        sel.innerHTML = '<option value="">Todos los que estuvieron en el arco</option>'
            + d.porteros.map(p => {
                const et = p.tiene_nombre ? escapeHtml(p.nombre_corto) : `#${p.numero}`;
                return `<option value="${p.id}">${et} · ${p.paradas} paradas</option>`;
            }).join('');
        sel.value = d.porteros.some(p => String(p.id) === String(actual)) ? actual : '';
    }

    async function cargarAnalisis() {
        try {
            const url = estado.filtro
                ? `/api/matches/${estado.matchId}/porteria?portero=${estado.filtro}`
                : `/api/matches/${estado.matchId}/porteria`;
            const r = await fetch(url);
            if (!r.ok) {
                const err = await r.json().catch(() => ({}));
                throw new Error(err.error || `Error ${r.status}`);
            }
            const d = await r.json();
            pintarKpis(d);
            pintarMapa(d);
            pintarGrillaArco(d);
            pintarGrillaOrigen(d);
            pintarLecturaAnalisis(d);
            pintarTipos(d);
            pintarTabla(d);
            pintarAvisos(d);
            pintarFiltro(d);
        } catch (e) {
            // El aviso va en su caja y no reemplazando la sección entera: si
            // fallara un fetch, el selector de arquero y el resto tienen que
            // seguir ahí para poder reintentar.
            document.getElementById('pt-avisos').innerHTML =
                `<div class="pt-aviso">No se pudo cargar el análisis: ${escapeHtml(e.message)}</div>`;
        }
    }

    // =====================================================================
    // Pestañas
    // =====================================================================

    function mostrar(vista) {
        estado.vista = vista;
        document.getElementById('tab-capturar').classList.toggle('active', vista === 'capturar');
        document.getElementById('tab-analizar').classList.toggle('active', vista === 'analizar');
        document.getElementById('tab-capturar').setAttribute('aria-selected', vista === 'capturar');
        document.getElementById('tab-analizar').setAttribute('aria-selected', vista === 'analizar');
        document.getElementById('vista-capturar').hidden = vista !== 'capturar';
        document.getElementById('vista-analizar').hidden = vista !== 'analizar';

        // La URL cambia sin recargar: la vista queda en el historial y se puede
        // mandar por WhatsApp, pero sin volver a pedir nada al servidor.
        const u = new URL(window.location.href);
        u.searchParams.set('vista', vista);
        window.history.replaceState(null, '', u);

        if (vista === 'analizar') cargarAnalisis();
        else pintarPuntoElegido();
    }

    // =====================================================================
    // Arranque
    // =====================================================================

    /**
     * Quién está en el arco se recuerda entre recargas.
     *
     * Sin esto, cargar la pantalla en el minuto 25 (justo después de que entró
     * el suplente) vuelve al primero de la lista y todos los tiros siguientes se
     * le cargan al arquero equivocado. Es el peor tipo de falla posible acá: los
     * datos quedan mal y nada en la pantalla lo avisa, porque el tiro se
     * registra igual y con la misma seguridad que los demás.
     */
    function recordarArquero() {
        try {
            localStorage.setItem(`porteriaArquero:${estado.matchId}`, String(estado.keeperId));
        } catch (e) { /* modo privado: se pierde al recargar, no es grave */ }
    }

    function arqueroRecordado() {
        try {
            return localStorage.getItem(`porteriaArquero:${estado.matchId}`);
        } catch (e) {
            return null;
        }
    }

    function cablear() {
        document.getElementById('tab-capturar').addEventListener('click', () => mostrar('capturar'));
        document.getElementById('tab-analizar').addEventListener('click', () => mostrar('analizar'));

        // El punto del tiro
        const cancha = document.getElementById('pt-court-capturar');
        const tocar = ev => {
            ev.preventDefault();
            estado.origen = metrosEnChispa(ev, cancha.getBoundingClientRect());
            // Tocar la cancha es decir "salió de acá". Si estaba puesto el 7m y el
            // dedo cae en otro punto, el 7m se apaga: el punto manda, y dejarlo
            // prendido volvería a inventarse un penalti en otro sitio.
            if (estado.es7m && !esPunto7M(estado.origen)) {
                cambiar7m(false);
                const chip = document.querySelector('#pt-toggles [data-toggle="es7m"]');
                if (chip) chip.classList.remove('on');
            }
            pintarPuntoElegido();
            pintarLectura();
            const panelAcciones = document.getElementById('pt-panel-acciones');
            if (panelAcciones) panelAcciones.style.display = 'block';
            const panelArco = document.getElementById('pt-panel-arco');
            if (panelArco) panelArco.style.display = 'none';
            estado.resultado = null;
            estado.zona = null;
            marcarResultadoEnDOM();
            marcarZonaEnDOM();
            pintarZonaHabilitada();
        };
        cancha.addEventListener('pointerdown', tocar);

        document.querySelectorAll('#pt-resultados [data-outcome]').forEach(b => {
            b.addEventListener('click', () => {
                estado.resultado = b.dataset.outcome;
                marcarResultadoEnDOM();
                pintarZonaHabilitada();
                const panelArco = document.getElementById('pt-panel-arco');
                if (panelArco) {
                    const necesitaZona = estado.resultado === 'GOL' || estado.resultado === 'PARADA';
                    panelArco.style.display = necesitaZona ? 'block' : 'none';
                }
                // Si no necesita zona, guardar directamente
                const necesitaZona = estado.resultado === 'GOL' || estado.resultado === 'PARADA';
                if (!necesitaZona) {
                    guardar();
                    const panelAcciones = document.getElementById('pt-panel-acciones');
                    if (panelAcciones) panelAcciones.style.display = 'none';
                    const panelArco2 = document.getElementById('pt-panel-arco');
                    if (panelArco2) panelArco2.style.display = 'none';
                }
            });
        });

        // El 3x3 del arco
        document.querySelectorAll('#pt-arco .goal-zone').forEach(z => {
            z.addEventListener('click', () => {
                estado.zona = z.dataset.zona;
                marcarZonaEnDOM();
                guardar();
                const panelAcciones = document.getElementById('pt-panel-acciones');
                if (panelAcciones) panelAcciones.style.display = 'none';
                const panelArco2 = document.getElementById('pt-panel-arco');
                if (panelArco2) panelArco2.style.display = 'none';
            });
        });

        // Los chips opcionales
        document.querySelectorAll('#pt-toggles .pt-toggle').forEach(b => {
            b.addEventListener('click', () => {
                const campo = b.dataset.toggle;
                if (campo === 'es7m') {
                    cambiar7m(!estado.es7m);
                } else {
                    estado[campo] = !estado[campo];
                }
                b.classList.toggle('on', !!estado[campo]);
            });
        });

        // El arquero del arco
        document.querySelectorAll('#pt-keepers [data-keeper-id]').forEach(b => {
            b.addEventListener('click', () => {
                document.querySelectorAll('#pt-keepers .pt-keeper').forEach(x => x.classList.remove('active'));
                b.classList.add('active');
                estado.keeperId = parseInt(b.dataset.keeperId, 10);
                recordarArquero();
            });
        });

        document.getElementById('pt-anular').addEventListener('click', anularUltimo);

        document.getElementById('pt-filtro').addEventListener('change', e => {
            estado.filtro = e.target.value;
            cargarAnalisis();
        });

        // Redibujar el mapa cuando cambia el tamaño: el canvas está en píxeles
        // reales y sin esto el mapa queda estirado con cualquier rotación de pantalla.
        let demora;
        window.addEventListener('resize', () => {
            clearTimeout(demora);
            demora = setTimeout(() => {
                if (estado.vista === 'analizar') cargarAnalisis();
                else pintarPuntoElegido();
            }, 180);
        });
    }

    function init() {
        const elId = document.getElementById('match-id');
        const estadoEl = document.getElementById('pt-estado');
        if (!elId || !estadoEl) return;   // la pantalla de aviso, no hay nada que hacer

        estado.matchId = parseInt(elId.value, 10);
        // Viene del servidor y no de un fetch: hace falta para armar cada evento,
        // así que si se pidiera por red el primer tiro sin señal no se podría
        // registrar, que es justo cuando más hace falta.
        estado.rivalId = estadoEl.dataset.rival ? parseInt(estadoEl.dataset.rival, 10) : null;

        // El primero de la lista viene marcado por el servidor, pero si hay uno
        // recordado se elige ese. Si el recordado ya no está en la lista (no
        // fue convocado a este partido), cae al primero.
        const recordado = arqueroRecordado();
        const keepers = document.querySelectorAll('#pt-keepers [data-keeper-id]');
        const elegido = (recordado && document.querySelector(`#pt-keepers [data-keeper-id="${recordado}"]`))
            || document.querySelector('#pt-keepers .pt-keeper.active')
            || keepers[0];
        if (elegido) {
            keepers.forEach(x => x.classList.toggle('active', x === elegido));
            estado.keeperId = parseInt(elegido.dataset.keeperId, 10);
        }

        montarCanchas();
        cablear();
        pintarPuntoElegido();
        pintarLectura();
        marcarZonaEnDOM();
        pintarZonaHabilitada();

        // El reloj arranca donde quedó, no en cero: si se recarga la pantalla en
        // el minuto 12, tiene que decir 12.
        if (typeof TimerModule !== 'undefined') {
            TimerModule.setSeconds(estadoEl.dataset.segundos || 0);
            TimerModule.setPeriodo(parseInt(estadoEl.dataset.periodo, 10) || 1);
        }

        mostrar(estadoEl.dataset.vista === 'analizar' ? 'analizar' : 'capturar');
    }

    return { init, zonaOrigen, distancia };
})();

document.addEventListener('DOMContentLoaded', Porteria.init);