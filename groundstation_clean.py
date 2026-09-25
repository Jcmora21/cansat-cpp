import asyncio
import socket
import json
import websockets
import threading
import csv
import os
from datetime import datetime

# 📁 Criar pasta para logs
LOG_DIR = "dados_voo"
os.makedirs(LOG_DIR, exist_ok=True)

session_time = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
csv_filename = os.path.join(LOG_DIR, f"voo_cansat_{session_time}.csv")

latest_packet = None
flight_history = []
CONNECTED_CLIENTS = set()

csv_headers = [
    "id", "tempo", "estado", "altitude", "velocidade", "forca_g", "aceleracao",
    "temperatura", "humidade", "pressao", "eco2", "tvoc", "uv", "lux",
    "paraquedas", "acc_x", "acc_y", "acc_z", "gyro_x", "gyro_y", "gyro_z",
    "pitch", "roll", "yaw", "rssi", "snr"
]

def init_csv(filename):
    with open(filename, mode='w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(csv_headers)

init_csv(csv_filename)
print(f"💾 [Logger] Gravação automática de dados ativa em: {csv_filename}")

# --- THREAD UDP ---
def udp_receiver():
    global latest_packet, flight_history
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 5005))
    print("📡 [UDP Receiver] Escutando na porta 5005...")
    
    while True:
        try:
            data, _ = sock.recvfrom(2048)
            payload = data.decode('utf-8')
            latest_packet = payload
            flight_history.append(payload)
            
            if CONNECTED_CLIENTS:
                asyncio.run_coroutine_threadsafe(broadcast(payload), loop)

            parsed = json.loads(payload)
            row = [parsed.get(h, "") for h in csv_headers]
            with open(csv_filename, mode='a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(row)
        except Exception:
            pass

async def broadcast(message):
    if CONNECTED_CLIENTS:
        await asyncio.gather(*(client.send(message) for client in CONNECTED_CLIENTS), return_exceptions=True)

# --- WEBSOCKET SERVER ---
async def ws_handler(websocket):
    global flight_history, latest_packet
    CONNECTED_CLIENTS.add(websocket)
    try:
        for past_packet in flight_history:
            await websocket.send(past_packet)
            
        async for message in websocket:
            try:
                data = json.loads(message)
                if data.get("action") == "clear":
                    flight_history = []
                    latest_packet = None
                    print("🗑️ [Server] Histórico de voo limpo a pedido do cliente.")
            except Exception:
                pass
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        CONNECTED_CLIENTS.remove(websocket)

# --- SERVIDOR WEB HTTP ---
HTML_CODE = r"""<!DOCTYPE html>
<html lang="pt">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CanSat Ground Station Live</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-annotation@2.2.1"></script>
    <style>
        body { font-family: system-ui, -apple-system, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 12px; }
        .header { display: flex; justify-content: space-between; align-items: center; background: #1e293b; padding: 12px 20px; border-radius: 8px; margin-bottom: 12px; flex-wrap: wrap; gap: 10px; }
        .actions { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
        .status { font-weight: bold; padding: 6px 14px; border-radius: 20px; background: #334155; color: #38bdf8; font-size: 0.9em; }
        .btn { border: none; padding: 8px 14px; border-radius: 6px; font-weight: bold; cursor: pointer; font-size: 0.85em; }
        .btn-export { background: #0284c7; color: white; }
        .btn-export:hover { background: #0369a1; }
        .btn-img { background: #8b5cf6; color: white; }
        .btn-img:hover { background: #7c3aed; }
        .btn-clear { background: #ef4444; color: white; }
        .btn-clear:hover { background: #dc2626; }
        .btn-cancel { background: #64748b; color: white; }
        .btn-cancel:hover { background: #475569; }
        .btn-mode { background: #0ea5e9; color: white; }
        .btn-mode.active { background: #22c55e; }
        .btn-mode:hover { filter: brightness(1.1); }

        /* Painel de Telemetria no Topo */
        .telemetry-card { background: #1e293b; padding: 12px; border-radius: 8px; margin-bottom: 12px; }
        .telemetry-card h3 { margin-top: 0; margin-bottom: 8px; font-size: 1.05em; color: #cbd5e1; }
        .metrics { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 6px; max-height: 220px; overflow-y: auto; padding-right: 4px; }
        .box { background: #0f172a; padding: 6px 10px; border-radius: 4px; display: flex; justify-content: space-between; font-size: 0.85em; }
        .val { font-weight: bold; color: #38bdf8; text-align: right; }

        /* Grelha de Gráficos (2 por linha) */
        .charts-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
        @media (max-width: 900px) { .charts-grid { grid-template-columns: 1fr; } }

        /* Card do Gráfico com Indicadores KPI */
        .card { background: #1e293b; padding: 12px; border-radius: 8px; display: flex; flex-direction: column; justify-content: space-between; }
        .card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
        .card-title { font-weight: bold; font-size: 0.95em; color: #e2e8f0; }
        .kpi-container { display: flex; gap: 8px; font-size: 0.75em; background: #0f172a; padding: 3px 8px; border-radius: 4px; border: 1px solid #334155; }
        .kpi-item { color: #94a3b8; }
        .kpi-val { font-weight: bold; color: #38bdf8; }

        /* Modal de Confirmação */
        .modal-overlay { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0, 0, 0, 0.7); backdrop-filter: blur(4px); z-index: 1000; justify-content: center; align-items: center; }
        .modal-box { background: #1e293b; padding: 24px; border-radius: 12px; max-width: 420px; width: 90%; box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.5); text-align: center; border: 1px solid #334155; }
        .modal-title { font-size: 1.2em; font-weight: bold; margin-bottom: 12px; color: #f8fafc; }
        .modal-desc { font-size: 0.95em; color: #94a3b8; margin-bottom: 20px; line-height: 1.4; }
        .modal-buttons { display: flex; flex-direction: column; gap: 10px; }
        .modal-buttons .btn { width: 100%; padding: 10px; font-size: 0.95em; }

        /* ========== FASE 1: Paraquedas (widget compacto) ========== */
        .phase-row { display: grid; grid-template-columns: auto 1.5fr 0.85fr; gap: 12px; margin-bottom: 12px; align-items: stretch; }
        @media (max-width: 900px) { .phase-row { grid-template-columns: 1fr; } }
        .widget-card { background: #1e293b; padding: 12px 14px; border-radius: 8px; }
        .widget-title { font-size: 0.85em; color: #94a3b8; margin-bottom: 8px; font-weight: 600; letter-spacing: 0.03em; text-transform: uppercase; }
        .para-card { min-width: 170px; max-width: 210px; padding: 10px 12px; }
        .para-status { display: flex; align-items: center; gap: 10px; }
        .para-dot { width: 16px; height: 16px; border-radius: 50%; background: #64748b; flex-shrink: 0; transition: background 0.2s; }
        .para-dot.green { background: #22c55e; box-shadow: 0 0 8px #22c55e88; }
        .para-dot.yellow { background: #eab308; box-shadow: 0 0 8px #eab30888; }
        .para-dot.red { background: #ef4444; box-shadow: 0 0 10px #ef4444aa; animation: blink 0.6s infinite; }
        @keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0.25; } }
        .para-text { font-size: 0.9em; font-weight: 700; }
        .para-sub { font-size: 0.72em; color: #94a3b8; margin-top: 1px; }
        .alert-banner { display: none; margin-top: 8px; padding: 5px 8px; background: #7f1d1d; border: 1px solid #ef4444; border-radius: 4px; color: #fecaca; font-weight: 700; font-size: 0.75em; animation: blink 0.8s infinite; }

        /* ========== FASE 2: Vento e LoRa (retângulos separados) ========== */
        .wind-wrap { display: flex; align-items: center; gap: 14px; }
        #windRose { width: 120px; height: 120px; background: #0f172a; border-radius: 50%; border: 2px solid #334155; flex-shrink: 0; }
        .wind-info { min-width: 90px; }
        .wind-dir { font-size: 1.15em; font-weight: 800; color: #38bdf8; }
        .wind-spd { font-size: 0.85em; color: #e2e8f0; margin-top: 3px; }
        .lora-card .metrics { max-height: none; grid-template-columns: 1fr; gap: 6px; }
        .lora-card .box { padding: 6px 10px; font-size: 0.85em; }

        /* ========== FASE 3: Gauges (Cockpit) ========== */
        .gauges-row { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 12px; }
        @media (max-width: 900px) { .gauges-row { grid-template-columns: 1fr; } }
        .gauge-card { background: #1e293b; padding: 12px; border-radius: 8px; text-align: center; }
        .gauge-card canvas { display: block; margin: 0 auto; max-width: 100%; }
        .gauge-label { font-size: 0.8em; color: #94a3b8; margin-top: 4px; }
        .gauge-value { font-size: 1.05em; font-weight: 700; color: #38bdf8; margin-top: 6px; font-variant-numeric: tabular-nums; }

        /* ========== FASE 4: Replay ========== */
        .replay-bar { background: #1e293b; padding: 12px 16px; border-radius: 8px; margin-bottom: 12px; display: none; flex-wrap: wrap; gap: 10px; align-items: center; }
        .replay-bar.visible { display: flex; }
        .replay-controls { display: flex; gap: 6px; flex-wrap: wrap; align-items: center; }
        .replay-controls button { min-width: 42px; }
        .replay-speed { background: #0f172a; color: #e2e8f0; border: 1px solid #334155; border-radius: 4px; padding: 6px 8px; font-size: 0.85em; }
        .replay-scrub { flex: 1; min-width: 160px; }
        .replay-time { font-variant-numeric: tabular-nums; font-size: 0.9em; color: #94a3b8; min-width: 90px; text-align: center; }
        .mode-badge { font-size: 0.75em; padding: 3px 8px; border-radius: 4px; background: #334155; color: #94a3b8; }
        .mode-badge.live { background: #14532d; color: #86efac; }
        .mode-badge.replay { background: #4c1d95; color: #c4b5fd; }
        input[type="file"] { font-size: 0.8em; color: #94a3b8; }
        input[type="range"] { width: 100%; accent-color: #38bdf8; }

        /* Footer */
        .dev-footer { margin-top: 20px; padding: 10px 14px; background: #0f172a; border: 1px solid #1e293b; border-radius: 6px; font-size: 0.8em; color: #94a3b8; text-align: center; letter-spacing: 0.03em; }

        /* Comparação Terra / Habitabilidade */
        .btn-hab { background: #0d9488; color: white; }
        .btn-hab.open { background: #059669; }
        .hab-panel { display: none; background: #1e293b; border-radius: 8px; padding: 14px; margin-bottom: 12px; border: 1px solid #334155; }
        .hab-panel.open { display: block; }
        .hab-top { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; margin-bottom: 12px; }
        .hab-score-box { text-align: right; }
        .hab-score-num { font-size: 2.2em; font-weight: 800; color: #38bdf8; font-variant-numeric: tabular-nums; line-height: 1; }
        .hab-score-label { font-size: 0.8em; color: #94a3b8; margin-top: 2px; }
        .hab-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 8px; }
        .hab-item { background: #0f172a; border-radius: 6px; padding: 10px 12px; border-left: 4px solid #64748b; }
        .hab-item.green { border-left-color: #22c55e; }
        .hab-item.yellow { border-left-color: #eab308; }
        .hab-item.red { border-left-color: #ef4444; }
        .hab-item-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; }
        .hab-item-name { font-size: 0.85em; font-weight: 700; color: #e2e8f0; }
        .hab-dot { width: 12px; height: 12px; border-radius: 50%; background: #64748b; flex-shrink: 0; }
        .hab-dot.green { background: #22c55e; box-shadow: 0 0 8px #22c55e88; }
        .hab-dot.yellow { background: #eab308; box-shadow: 0 0 8px #eab30888; }
        .hab-dot.red { background: #ef4444; box-shadow: 0 0 8px #ef444488; }
        .hab-item-val { font-size: 1.05em; font-weight: 700; color: #38bdf8; font-variant-numeric: tabular-nums; }
        .hab-item-ref { font-size: 0.72em; color: #64748b; margin-top: 3px; line-height: 1.3; }
        .hab-note { font-size: 0.75em; color: #64748b; margin-top: 10px; line-height: 1.4; }
    </style>
</head>
<body>

    <div class="header">
        <h2 style="margin:0; font-size: 1.2em;">📡 CANSAT GROUND STATION</h2>
        <div class="actions">
            <button class="btn btn-mode active" id="btnLive" onclick="setMode('live')">🔴 LIVE</button>
            <button class="btn btn-mode" id="btnReplay" onclick="setMode('replay')">▶️ REPLAY</button>
            <button class="btn btn-hab" id="btnHab" onclick="toggleHabPanel()">🌍 vs Terra</button>
            <button class="btn btn-export" onclick="downloadCSV()">📥 Exportar CSV</button>
            <button class="btn btn-img" onclick="downloadChartsAsImages()">📸 Baixar Gráficos (PNG)</button>
            <button class="btn btn-clear" onclick="openClearModal()">🗑️ Limpar Dados</button>
            <div id="status" class="status">AGUARDANDO DADOS...</div>
            <span id="modeBadge" class="mode-badge live">MODO LIVE</span>
        </div>
    </div>

    <!-- ========== Comparação Terra / Habitabilidade ========== -->
    <div id="habPanel" class="hab-panel">
        <div class="hab-top">
            <div>
                <div class="widget-title" style="margin:0">Comparação com valores da Terra · Habitabilidade</div>
                <div style="font-size:0.8em;color:#94a3b8;margin-top:4px">Verde = ok · Amarelo = marginal · Vermelho = hostil para vida (heurística de missão)</div>
            </div>
            <div class="hab-score-box">
                <div class="hab-score-num" id="habScoreNum">—</div>
                <div class="hab-score-label" id="habScoreLabel">Nota final / 100</div>
            </div>
        </div>
        <div class="hab-grid" id="habGrid"></div>
        <div class="hab-note">
            Referências aproximadas de superfície terrestre / zona compatível com água líquida e baixa hostilidade.
            Não é um veredito científico — é uma nota de missão para comparar voos e ler os dados depressa.
        </div>
    </div>

    <!-- ========== FASE 4: Barra de Replay ========== -->
    <div id="replayBar" class="replay-bar">
        <input type="file" id="csvFile" accept=".csv" onchange="loadCSVFile(event)">
        <div class="replay-controls">
            <button class="btn btn-cancel" onclick="replaySeek(-10)">-10s</button>
            <button class="btn btn-export" id="btnPlayPause" onclick="togglePlay()">▶ Play</button>
            <button class="btn btn-cancel" onclick="replaySeek(10)">+10s</button>
            <select class="replay-speed" id="replaySpeed" onchange="onSpeedChange()">
                <option value="0.25">x0.25</option>
                <option value="0.5">x0.5</option>
                <option value="0.75">x0.75</option>
                <option value="1" selected>x1</option>
                <option value="1.5">x1.5</option>
                <option value="2">x2</option>
                <option value="4">x4</option>
            </select>
        </div>
        <div class="replay-scrub">
            <input type="range" id="scrubber" min="0" max="0" value="0" step="1" oninput="onScrub(this.value)">
        </div>
        <div class="replay-time" id="replayTime">00:00 / 00:00</div>
    </div>

    <!-- ========== FASE 1 + 2: Paraquedas | Vento | LoRa ========== -->
    <div class="phase-row">
        <div class="widget-card para-card">
            <div class="widget-title">🪂 Paraquedas</div>
            <div class="para-status">
                <div id="paraDot" class="para-dot"></div>
                <div>
                    <div class="para-text" id="paraLabel">—</div>
                    <div class="para-sub" id="paraSub">Aguardando…</div>
                </div>
            </div>
            <div id="freefallAlert" class="alert-banner">⚠ QUEDA-LIVRE > 12 m/s</div>
        </div>

        <div class="widget-card">
            <div class="widget-title">🌬️ Estimativa de Vento</div>
            <div class="wind-wrap">
                <canvas id="windRose" width="120" height="120"></canvas>
                <div class="wind-info">
                    <div class="wind-dir" id="windDir">—</div>
                    <div class="wind-spd" id="windSpd">— km/h</div>
                </div>
            </div>
        </div>

        <div class="widget-card lora-card">
            <div class="widget-title">📡 Link LoRa</div>
            <div class="metrics">
                <div class="box"><span>RSSI</span><span class="val" id="liveRssi">—</span></div>
                <div class="box"><span>SNR</span><span class="val" id="liveSnr">—</span></div>
            </div>
        </div>
    </div>

    <!-- ========== FASE 3: Cockpit Gauges ========== -->
    <div class="gauges-row">
        <div class="gauge-card">
            <canvas id="gaugeAlt" width="200" height="200"></canvas>
            <div class="gauge-value" id="valAlt">— m</div>
            <div class="gauge-label">Altímetro</div>
        </div>
        <div class="gauge-card">
            <canvas id="gaugeVSI" width="200" height="200"></canvas>
            <div class="gauge-value" id="valVSI">— m/s</div>
            <div class="gauge-label">Velocímetro</div>
        </div>
        <div class="gauge-card">
            <canvas id="gaugeAI" width="200" height="200"></canvas>
            <div class="gauge-value" id="valAI">P: —°  R: —°</div>
            <div class="gauge-label">Horizonte Artificial</div>
        </div>
    </div>

    <!-- Painel de Telemetria Completa no Topo -->
    <div class="telemetry-card">
        <h3>📊 Telemetria Completa ao Vivo</h3>
        <div class="metrics" id="metrics"></div>
    </div>

    <!-- Grelha de Gráficos (2 por linha) -->
    <div class="charts-grid" id="chartsContainer"></div>

    <!-- Modal de Confirmação -->
    <div id="clearModal" class="modal-overlay">
        <div class="modal-box">
            <div class="modal-title">⚠️ Desejas Guardar os Dados?</div>
            <div class="modal-desc">Gostarias de fazer o download do ficheiro CSV da telemetria antes de limpar o painel?</div>
            <div class="modal-buttons">
                <button class="btn btn-export" onclick="confirmClear(true)">📥 Sim (Descarregar e Limpar)</button>
                <button class="btn btn-clear" onclick="confirmClear(false)">🗑️ Não (Apenas Limpar)</button>
                <button class="btn btn-cancel" onclick="closeClearModal()">❌ Cancelar</button>
            </div>
        </div>
    </div>

    <div class="dev-footer">© CanSat - Eagles</div>

    <script>
        window.addEventListener("beforeunload", function (e) {
            e.preventDefault();
            e.returnValue = "Tens a certeza que queres recarregar a página? A transmissão ao vivo será interrompida.";
        });

        let rawDataLog = [];
        let currentState = null;
        let lastPhaseTime = -999; 
        let lastPhaseLabelTime = ""; 

        // ---- Mode / Replay state ----
        let currentMode = 'live'; // 'live' | 'replay'
        let replayData = [];
        let replayIndex = 0;
        let replayPlaying = false;
        let replayTimer = null;
        let replaySpeed = 1;
        let lastAlt = null;
        let lastTempo = null;
        let windSamples = []; // {dx, dy, dt} approx during descent

        const chartConfigs = [
            { id: 'chartAlt', key: 'altitude', label: 'Altitude (m)', color: '#38bdf8' },
            { id: 'chartVel', key: 'velocidade', label: 'Velocidade (m/s)', color: '#fbbf24' },
            { id: 'chartG', key: 'forca_g', label: 'Força-G (g)', color: '#f43f5e' },
            { id: 'chartCO2', key: 'eco2', label: 'eCO2 (ppm)', color: '#34d399' },
            { id: 'chartTemp', key: 'temperatura', label: 'Temperatura (°C)', color: '#ec4899' },
            { id: 'chartPress', key: 'pressao', label: 'Pressão (hPa)', color: '#8b5cf6' },
            { id: 'chartHum', key: 'humidade', label: 'Humidade (%)', color: '#06b6d4' },
            { id: 'chartUV', key: 'uv', label: 'Índice UV', color: '#eab308' }
        ];

        // Construir HTML dos Cartões dos Gráficos com Indicadores: Mín, Máx, Méd
        const container = document.getElementById('chartsContainer');
        chartConfigs.forEach(cfg => {
            container.innerHTML += `
                <div class="card">
                    <div class="card-header">
                        <span class="card-title" style="color: ${cfg.color}">${cfg.label}</span>
                        <div class="kpi-container">
                            <span class="kpi-item">Mín: <span class="kpi-val" id="min-${cfg.id}">-</span></span>
                            <span class="kpi-item">Máx: <span class="kpi-val" id="max-${cfg.id}">-</span></span>
                            <span class="kpi-item">Méd: <span class="kpi-val" id="avg-${cfg.id}">-</span></span>
                        </div>
                    </div>
                    <canvas id="${cfg.id}"></canvas>
                </div>
            `;
        });

        function makeChart(id, label, color) {
            const ctx = document.getElementById(id).getContext('2d');
            return new Chart(ctx, {
                type: 'line',
                data: { labels: [], datasets: [{ label: label, data: [], borderColor: color, borderWidth: 2, pointRadius: 0 }] },
                options: {
                    responsive: true,
                    animation: false,
                    scales: { 
                        x: { 
                            display: true,
                            grid: { color: '#334155' },
                            ticks: { 
                                color: '#94a3b8',
                                font: { size: 10 },
                                autoSkip: true,
                                maxTicksLimit: 10,
                                maxRotation: 0,
                                minRotation: 0,
                                callback: function(value) {
                                    const rawLabel = this.getLabelForValue(value);
                                    if (!rawLabel) return '';
                                    const num = Math.round(parseFloat(rawLabel.toString().replace('s', '')));
                                    return isNaN(num) ? rawLabel : num + 's';
                                }
                            }
                        }, 
                        y: { 
                            grid: { color: '#334155' },
                            ticks: { color: '#94a3b8' } 
                        } 
                    },
                    plugins: {
                        legend: { display: false },
                        annotation: {
                            annotations: {}
                        }
                    }
                }
            });
        }

        const charts = {};
        chartConfigs.forEach(cfg => {
            charts[cfg.id] = makeChart(cfg.id, cfg.label, cfg.color);
        });

        function updateKPIs(cfgId, dataArray) {
            const validData = dataArray.filter(v => v !== undefined && v !== null && !isNaN(v));
            if (validData.length === 0) return;

            const min = Math.min(...validData);
            const max = Math.max(...validData);
            const avg = validData.reduce((a, b) => a + b, 0) / validData.length;

            document.getElementById(`min-${cfgId}`).innerText = Number.isInteger(min) ? min : min.toFixed(1);
            document.getElementById(`max-${cfgId}`).innerText = Number.isInteger(max) ? max : max.toFixed(1);
            document.getElementById(`avg-${cfgId}`).innerText = avg.toFixed(1);
        }

        function addPhaseLine(label, timeLabel, numericTime) {
            const annotationId = 'line_' + Date.now();
            
            let labelPosition = 'start';
            let targetXLabel = timeLabel;

            if (Math.abs(numericTime - lastPhaseTime) <= 2 && lastPhaseLabelTime !== "") {
                targetXLabel = lastPhaseLabelTime;
                labelPosition = 'end';
            } else {
                lastPhaseLabelTime = timeLabel;
            }
            lastPhaseTime = numericTime;

            chartConfigs.forEach(cfg => {
                const chart = charts[cfg.id];
                chart.options.plugins.annotation.annotations[annotationId] = {
                    type: 'line',
                    xMin: targetXLabel,
                    xMax: targetXLabel,
                    borderColor: '#f59e0b',
                    borderWidth: 2,
                    borderDash: [4, 4],
                    label: {
                        display: true,
                        content: label,
                        position: labelPosition,
                        backgroundColor: 'rgba(245, 158, 11, 0.85)',
                        color: '#0f172a',
                        font: { size: 9, weight: 'bold' },
                        padding: 2
                    }
                };
                chart.update('none');
            });
        }

        // ========== Comparação Terra / Habitabilidade ==========
        // Regras: green=2 pts, yellow=1, red=0 → score = 100 * soma / (2*N)
        // Intervalos heurísticos tipo Terra / zona amiga de vida à superfície
        const HAB_PARAMS = [
            {
                key: 'temperatura', name: 'Temperatura', unit: '°C', weight: 1.2,
                ref: 'Terra típica: ~0 a 35 °C (água líquida / conforto relativo)',
                score(v) {
                    if (v >= 0 && v <= 35) return 'green';
                    if ((v >= -15 && v < 0) || (v > 35 && v <= 50)) return 'yellow';
                    return 'red';
                }
            },
            {
                key: 'pressao', name: 'Pressão', unit: 'hPa', weight: 1.3,
                ref: 'Terra: ~1013 hPa · água líquida precisa ≫ 6 hPa',
                score(v) {
                    if (v >= 300 && v <= 1100) return 'green';
                    if ((v >= 50 && v < 300) || (v > 1100 && v <= 1500)) return 'yellow';
                    return 'red';
                }
            },
            {
                key: 'humidade', name: 'Humidade', unit: '%', weight: 0.8,
                ref: 'Terra útil: ~20–80 % RH',
                score(v) {
                    if (v >= 20 && v <= 80) return 'green';
                    if ((v >= 5 && v < 20) || (v > 80 && v <= 95)) return 'yellow';
                    return 'red';
                }
            },
            {
                key: 'uv', name: 'Índice UV', unit: '', weight: 1.2,
                ref: 'OMS: baixo 0–2 · moderado 3–5 · alto ≥6',
                score(v) {
                    if (v >= 0 && v <= 3) return 'green';
                    if (v > 3 && v <= 7) return 'yellow';
                    return 'red';
                }
            },
            {
                key: 'eco2', name: 'eCO₂', unit: 'ppm', weight: 1.0,
                ref: 'Terra exterior ~400 ppm · interior ok até ~1000 ppm',
                score(v) {
                    if (v >= 300 && v <= 1000) return 'green';
                    if ((v >= 150 && v < 300) || (v > 1000 && v <= 5000)) return 'yellow';
                    return 'red';
                }
            },
            {
                key: 'tvoc', name: 'TVOC', unit: 'ppb', weight: 0.9,
                ref: 'Ar limpo: tipicamente &lt; 200–300 ppb (ordem de grandeza)',
                score(v) {
                    if (v >= 0 && v <= 300) return 'green';
                    if (v > 300 && v <= 1000) return 'yellow';
                    return 'red';
                }
            },
            {
                key: 'lux', name: 'Luminosidade', unit: 'lx', weight: 0.7,
                ref: 'Dia nublado–sol: ~1000–100000 lx · noite ~0',
                score(v) {
                    // Energia para processos tipo fotossíntese: luz de dia é positiva; escuridão total é marginal
                    if (v >= 1000 && v <= 120000) return 'green';
                    if ((v >= 50 && v < 1000) || (v > 120000 && v <= 200000)) return 'yellow';
                    return 'red';
                }
            }
        ];

        function toggleHabPanel() {
            const panel = document.getElementById('habPanel');
            const btn = document.getElementById('btnHab');
            const open = !panel.classList.contains('open');
            panel.classList.toggle('open', open);
            btn.classList.toggle('open', open);
        }

        function habVerdict(score) {
            if (score === null) return 'Aguardando dados…';
            if (score >= 80) return 'Fortemente promissor';
            if (score >= 60) return 'Moderadamente promissor';
            if (score >= 40) return 'Marginal';
            return 'Hostil / pouco favorável';
        }

        function updateHabitability(data) {
            const grid = document.getElementById('habGrid');
            if (!grid) return;

            let weightedPts = 0;
            let weightedMax = 0;
            let html = '';

            HAB_PARAMS.forEach(p => {
                const raw = data[p.key];
                const v = raw !== undefined && raw !== null && raw !== '' ? parseFloat(raw) : NaN;
                let level = null;
                let valText = '—';

                if (!isNaN(v)) {
                    level = p.score(v);
                    valText = (Number.isInteger(v) ? v : v.toFixed(1)) + (p.unit ? ' ' + p.unit : '');
                    const pts = level === 'green' ? 2 : (level === 'yellow' ? 1 : 0);
                    weightedPts += pts * p.weight;
                    weightedMax += 2 * p.weight;
                }

                const cls = level || '';
                html += `<div class="hab-item ${cls}">
                    <div class="hab-item-head">
                        <span class="hab-item-name">${p.name}</span>
                        <span class="hab-dot ${cls}"></span>
                    </div>
                    <div class="hab-item-val">${valText}</div>
                    <div class="hab-item-ref">${p.ref}</div>
                </div>`;
            });

            grid.innerHTML = html;

            const numEl = document.getElementById('habScoreNum');
            const labEl = document.getElementById('habScoreLabel');
            if (weightedMax > 0) {
                const score = Math.round(100 * weightedPts / weightedMax);
                numEl.textContent = score;
                numEl.style.color = score >= 60 ? '#22c55e' : (score >= 40 ? '#eab308' : '#ef4444');
                labEl.textContent = habVerdict(score) + ' · / 100';
            } else {
                numEl.textContent = '—';
                numEl.style.color = '#38bdf8';
                labEl.textContent = 'Nota final / 100';
            }
        }

        // ========== FASE 1: Paraquedas & Queda-livre ==========
        function updateParachute(data) {
            const v = data.velocidade !== undefined && data.velocidade !== null
                ? parseFloat(data.velocidade)
                : null;
            const alt = data.altitude !== undefined ? parseFloat(data.altitude) : null;
            const tempo = data.tempo !== undefined ? parseFloat(data.tempo) : null;
            const paraFlag = data.paraquedas;

            // Vertical speed: prefer provided velocidade; else derive from altitude delta
            let vVert = v;
            if ((vVert === null || isNaN(vVert)) && lastAlt !== null && lastTempo !== null && alt !== null && tempo !== null) {
                const dt = tempo - lastTempo;
                if (dt > 0) vVert = (alt - lastAlt) / dt;
            }
            if (alt !== null) lastAlt = alt;
            if (tempo !== null) lastTempo = tempo;

            const dot = document.getElementById('paraDot');
            const label = document.getElementById('paraLabel');
            const sub = document.getElementById('paraSub');
            const alertEl = document.getElementById('freefallAlert');

            dot.className = 'para-dot';
            alertEl.style.display = 'none';

            if (vVert === null || isNaN(vVert)) {
                label.textContent = 'Sem dados de velocidade';
                sub.textContent = 'Aguardando…';
                return;
            }

            // Convention: positive velocidade often means downward in many CanSat firmwares; we treat magnitude
            const speedDown = Math.abs(vVert);
            // Heuristic: if altitude increasing → ascent
            const ascending = (lastAlt !== null && alt !== null && alt > lastAlt + 0.3) || (vVert > 0.5 && (data.estado || '').toLowerCase().includes('subi'));

            if (ascending || (data.estado || '').toLowerCase().match(/descol|ascent|subida|launch/)) {
                dot.classList.add('yellow');
                label.textContent = 'Em Descolagem / Subida';
                sub.textContent = `Vel. vertical ≈ ${vVert.toFixed(1)} m/s`;
            } else if (speedDown > 12) {
                dot.classList.add('red');
                label.textContent = 'QUEDA-LIVRE';
                sub.textContent = `Velocidade ≈ ${speedDown.toFixed(1)} m/s  (> 12 m/s)`;
                alertEl.style.display = 'block';
            } else {
                // Normal descent / parachute regime
                const open = paraFlag === true || paraFlag === 1 || paraFlag === '1' || String(paraFlag).toLowerCase() === 'true' || String(paraFlag).toLowerCase() === 'aberto';
                dot.classList.add('green');
                label.textContent = open ? 'Paraquedas ABERTO' : 'Descida controlada';
                sub.textContent = `Vel. vertical ≈ ${speedDown.toFixed(1)} m/s` + (open ? ' (regime pára-quedas)' : '');
            }
        }

        // ========== FASE 2: Rosa dos Ventos ==========
        function drawWindRose(degrees, speedKmh) {
            const canvas = document.getElementById('windRose');
            const ctx = canvas.getContext('2d');
            const cx = canvas.width / 2, cy = canvas.height / 2, r = 52;
            ctx.clearRect(0, 0, canvas.width, canvas.height);

            // Outer ring
            ctx.beginPath();
            ctx.arc(cx, cy, r, 0, Math.PI * 2);
            ctx.strokeStyle = '#475569';
            ctx.lineWidth = 2;
            ctx.stroke();

            // Cardinal ticks
            const labels = ['N', 'E', 'S', 'W'];
            const angles = [0, 90, 180, 270];
            ctx.fillStyle = '#94a3b8';
            ctx.font = 'bold 11px system-ui';
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            angles.forEach((a, i) => {
                const rad = (a - 90) * Math.PI / 180;
                const lx = cx + Math.cos(rad) * (r - 14);
                const ly = cy + Math.sin(rad) * (r - 14);
                ctx.fillText(labels[i], lx, ly);
                // tick
                const tx1 = cx + Math.cos(rad) * (r - 4);
                const ty1 = cy + Math.sin(rad) * (r - 4);
                const tx2 = cx + Math.cos(rad) * r;
                const ty2 = cy + Math.sin(rad) * r;
                ctx.beginPath();
                ctx.moveTo(tx1, ty1);
                ctx.lineTo(tx2, ty2);
                ctx.strokeStyle = '#64748b';
                ctx.stroke();
            });

            // Arrow (wind FROM direction)
            if (degrees !== null && !isNaN(degrees)) {
                const rad = (degrees - 90) * Math.PI / 180;
                ctx.save();
                ctx.translate(cx, cy);
                ctx.rotate(rad);
                ctx.beginPath();
                ctx.moveTo(0, -r + 10);
                ctx.lineTo(-8, -r + 28);
                ctx.lineTo(0, -r + 22);
                ctx.lineTo(8, -r + 28);
                ctx.closePath();
                ctx.fillStyle = '#f59e0b';
                ctx.fill();
                // shaft
                ctx.beginPath();
                ctx.moveTo(0, -r + 24);
                ctx.lineTo(0, r - 18);
                ctx.strokeStyle = '#f59e0b';
                ctx.lineWidth = 3;
                ctx.stroke();
                ctx.restore();
            }

            // Center
            ctx.beginPath();
            ctx.arc(cx, cy, 4, 0, Math.PI * 2);
            ctx.fillStyle = '#e2e8f0';
            ctx.fill();
        }

        function cardinalFromDeg(d) {
            const dirs = ['N','NNE','NE','ENE','E','ESE','SE','SSE','S','SSW','SW','WSW','W','WNW','NW','NNW'];
            const i = Math.round(((d % 360) / 22.5)) % 16;
            return dirs[i];
        }

        function updateWind(data) {
            // Approximate: use yaw as heading; during descent accumulate crude horizontal drift
            // using integrated accel (very rough) or simply show heading as "wind from"
            const yaw = data.yaw !== undefined ? parseFloat(data.yaw) : null;
            const v = data.velocidade !== undefined ? Math.abs(parseFloat(data.velocidade)) : 0;
            const estado = (data.estado || '').toLowerCase();
            const descending = estado.match(/desc|queda|paraq|land|descida/) || (v > 1 && !estado.match(/subi|asc|launch/));

            let windDeg = yaw;
            let windKmh = null;

            if (descending && yaw !== null && !isNaN(yaw)) {
                // Rough speed estimate: assume horizontal component related to residual velocity
                // Typical CanSat under chute drifts 5–20 km/h; scale with |v - 5|
                const residual = Math.max(0, v - 4.5);
                windKmh = Math.min(40, residual * 3.6 * 1.2 + 3); // m/s → km/h-ish
                windSamples.push({ yaw, v, t: data.tempo });
                if (windSamples.length > 30) windSamples.shift();
            }

            if (windDeg !== null && !isNaN(windDeg)) {
                const card = cardinalFromDeg(windDeg);
                document.getElementById('windDir').textContent = `${card} ${windDeg.toFixed(0)}°`;
                document.getElementById('windSpd').textContent = windKmh !== null
                    ? `${windKmh.toFixed(0)}–${(windKmh + 2).toFixed(0)} km/h (est.)`
                    : '— km/h';
                drawWindRose(windDeg, windKmh);
            } else {
                document.getElementById('windDir').textContent = '—';
                document.getElementById('windSpd').textContent = '— km/h';
                drawWindRose(null, null);
            }
        }

        // ========== FASE 3: Gauges ==========
        function drawAltimeter(alt) {
            const canvas = document.getElementById('gaugeAlt');
            const ctx = canvas.getContext('2d');
            const cx = 100, cy = 100, r = 85;
            ctx.clearRect(0, 0, 200, 200);

            ctx.beginPath();
            ctx.arc(cx, cy, r, 0, Math.PI * 2);
            ctx.fillStyle = '#0f172a';
            ctx.fill();
            ctx.strokeStyle = '#475569';
            ctx.lineWidth = 3;
            ctx.stroke();

            const maxAlt = 1000;
            for (let i = 0; i <= 10; i++) {
                const a = (i / 10) * Math.PI * 2 - Math.PI / 2;
                const x1 = cx + Math.cos(a) * (r - 8);
                const y1 = cy + Math.sin(a) * (r - 8);
                const x2 = cx + Math.cos(a) * (r - 18);
                const y2 = cy + Math.sin(a) * (r - 18);
                ctx.beginPath();
                ctx.moveTo(x1, y1);
                ctx.lineTo(x2, y2);
                ctx.strokeStyle = '#94a3b8';
                ctx.lineWidth = 2;
                ctx.stroke();
                const lx = cx + Math.cos(a) * (r - 28);
                const ly = cy + Math.sin(a) * (r - 28);
                ctx.fillStyle = '#e2e8f0';
                ctx.font = '10px system-ui';
                ctx.textAlign = 'center';
                ctx.textBaseline = 'middle';
                ctx.fillText(String(i * 100), lx, ly);
            }

            const val = Math.max(0, Math.min(maxAlt, alt || 0));
            const ang = (val / maxAlt) * Math.PI * 2 - Math.PI / 2;
            ctx.beginPath();
            ctx.moveTo(cx, cy);
            ctx.lineTo(cx + Math.cos(ang) * (r - 25), cy + Math.sin(ang) * (r - 25));
            ctx.strokeStyle = '#38bdf8';
            ctx.lineWidth = 3;
            ctx.stroke();
            ctx.beginPath();
            ctx.arc(cx, cy, 5, 0, Math.PI * 2);
            ctx.fillStyle = '#38bdf8';
            ctx.fill();

            const el = document.getElementById('valAlt');
            if (el) el.textContent = (alt !== null && !isNaN(alt) ? alt.toFixed(0) : '—') + ' m';
        }

        function drawVSI(vs) {
            const canvas = document.getElementById('gaugeVSI');
            const ctx = canvas.getContext('2d');
            const cx = 100, cy = 100, r = 85;
            ctx.clearRect(0, 0, 200, 200);

            ctx.beginPath();
            ctx.arc(cx, cy, r, 0, Math.PI * 2);
            ctx.fillStyle = '#0f172a';
            ctx.fill();
            ctx.strokeStyle = '#475569';
            ctx.lineWidth = 3;
            ctx.stroke();

            const maxVS = 25;
            for (let i = -20; i <= 20; i += 10) {
                const frac = i / maxVS;
                const a = frac * (Math.PI * 0.85) - Math.PI / 2;
                const x1 = cx + Math.cos(a) * (r - 6);
                const y1 = cy + Math.sin(a) * (r - 6);
                const x2 = cx + Math.cos(a) * (r - 16);
                const y2 = cy + Math.sin(a) * (r - 16);
                ctx.beginPath();
                ctx.moveTo(x1, y1);
                ctx.lineTo(x2, y2);
                ctx.strokeStyle = i === 0 ? '#22c55e' : '#94a3b8';
                ctx.lineWidth = 2;
                ctx.stroke();
                const lx = cx + Math.cos(a) * (r - 26);
                const ly = cy + Math.sin(a) * (r - 26);
                ctx.fillStyle = '#e2e8f0';
                ctx.font = '9px system-ui';
                ctx.textAlign = 'center';
                ctx.textBaseline = 'middle';
                ctx.fillText(String(i), lx, ly);
            }

            const v = Math.max(-maxVS, Math.min(maxVS, vs || 0));
            const ang = (v / maxVS) * (Math.PI * 0.85) - Math.PI / 2;
            ctx.beginPath();
            ctx.moveTo(cx, cy);
            ctx.lineTo(cx + Math.cos(ang) * (r - 22), cy + Math.sin(ang) * (r - 22));
            ctx.strokeStyle = v > 0 ? '#22c55e' : (v < -8 ? '#ef4444' : '#fbbf24');
            ctx.lineWidth = 3;
            ctx.stroke();
            ctx.beginPath();
            ctx.arc(cx, cy, 5, 0, Math.PI * 2);
            ctx.fillStyle = '#e2e8f0';
            ctx.fill();

            const el = document.getElementById('valVSI');
            if (el) el.textContent = (vs !== null && !isNaN(vs) ? vs.toFixed(1) : '—') + ' m/s';
        }

        function drawAttitude(pitch, roll) {
            const canvas = document.getElementById('gaugeAI');
            const ctx = canvas.getContext('2d');
            const cx = 100, cy = 100, r = 85;
            ctx.clearRect(0, 0, 200, 200);

            ctx.save();
            ctx.beginPath();
            ctx.arc(cx, cy, r, 0, Math.PI * 2);
            ctx.clip();

            const p = pitch || 0;
            const ro = roll || 0;
            ctx.translate(cx, cy);
            ctx.rotate(-ro * Math.PI / 180);
            const pitchPx = p * 1.8;
            ctx.fillStyle = '#0ea5e9';
            ctx.fillRect(-120, -120 + pitchPx, 240, 120);
            ctx.fillStyle = '#854d0e';
            ctx.fillRect(-120, 0 + pitchPx, 240, 120);
            ctx.beginPath();
            ctx.moveTo(-120, pitchPx);
            ctx.lineTo(120, pitchPx);
            ctx.strokeStyle = '#f8fafc';
            ctx.lineWidth = 2;
            ctx.stroke();

            ctx.restore();

            ctx.beginPath();
            ctx.arc(cx, cy, r, 0, Math.PI * 2);
            ctx.strokeStyle = '#475569';
            ctx.lineWidth = 3;
            ctx.stroke();

            ctx.strokeStyle = '#fbbf24';
            ctx.lineWidth = 3;
            ctx.beginPath();
            ctx.moveTo(cx - 40, cy);
            ctx.lineTo(cx - 10, cy);
            ctx.moveTo(cx + 10, cy);
            ctx.lineTo(cx + 40, cy);
            ctx.moveTo(cx, cy);
            ctx.lineTo(cx, cy + 12);
            ctx.stroke();
            ctx.beginPath();
            ctx.arc(cx, cy, 5, 0, Math.PI * 2);
            ctx.stroke();

            const el = document.getElementById('valAI');
            if (el) el.textContent = `P: ${(pitch||0).toFixed(0)}°  R: ${(roll||0).toFixed(0)}°`;
        }

        function updateGauges(data) {
            const alt = data.altitude !== undefined ? parseFloat(data.altitude) : null;
            let vs = data.velocidade !== undefined ? parseFloat(data.velocidade) : null;
            if (lastAlt !== null && alt !== null && data.tempo !== undefined && lastTempo !== null) {
                const dt = parseFloat(data.tempo) - lastTempo;
                if (dt > 0.05) vs = (alt - lastAlt) / dt;
            }
            const pitch = data.pitch !== undefined ? parseFloat(data.pitch) : 0;
            const roll = data.roll !== undefined ? parseFloat(data.roll) : 0;

            drawAltimeter(alt);
            drawVSI(vs);
            drawAttitude(pitch, roll);
        }

        // ========== Core packet handler (shared by live + replay) ==========
        function processPacket(data, fromReplay = false) {
            if (!fromReplay && currentMode === 'replay') return; // ignore live while in replay
            if (!fromReplay) rawDataLog.push(data);

            document.getElementById('status').innerText = "ESTADO: " + (data.estado || "N/D");
            if (data.rssi !== undefined) document.getElementById('liveRssi').textContent = data.rssi + ' dBm';
            if (data.snr !== undefined) document.getElementById('liveSnr').textContent = data.snr + ' dB';

            const numTime = data.tempo !== undefined ? parseFloat(data.tempo) : 0;
            const t = numTime + "s";

            if (data.estado && data.estado !== currentState) {
                currentState = data.estado;
                addPhaseLine(currentState, t, numTime);
            }

            chartConfigs.forEach(cfg => {
                const chart = charts[cfg.id];
                const val = data[cfg.key];
                if (val !== undefined && val !== null) {
                    chart.data.labels.push(t);
                    chart.data.datasets[0].data.push(val);
                    // Keep charts from growing forever in long replay
                    if (chart.data.labels.length > 2000) {
                        chart.data.labels.shift();
                        chart.data.datasets[0].data.shift();
                    }
                    chart.update('none');
                    updateKPIs(cfg.id, chart.data.datasets[0].data);
                }
            });

            // FASE 1–3
            updateParachute(data);
            updateWind(data);
            updateGauges(data);
            updateHabitability(data);

            const fields = {
                "Pacote ID": data.id,
                "Tempo": data.tempo !== undefined ? data.tempo + " s" : undefined,
                "Estado Voo": data.estado,
                "Altitude": data.altitude !== undefined ? data.altitude + " m" : undefined,
                "Velocidade": data.velocidade !== undefined ? data.velocidade + " m/s" : undefined,
                "Força-G": data.forca_g !== undefined ? data.forca_g + " g" : undefined,
                "Aceleração": data.aceleracao !== undefined ? data.aceleracao + " m/s²" : undefined,
                "Temperatura": data.temperatura !== undefined ? data.temperatura + " °C" : undefined,
                "Humidade": data.humidade !== undefined ? data.humidade + " %" : undefined,
                "Pressão": data.pressao !== undefined ? data.pressao + " hPa" : undefined,
                "eCO2": data.eco2 !== undefined ? data.eco2 + " ppm" : undefined,
                "TVOC": data.tvoc !== undefined ? data.tvoc + " ppb" : undefined,
                "Índice UV": data.uv,
                "Luminosidade": data.lux !== undefined ? data.lux + " lx" : undefined,
                "Paraquedas": data.paraquedas !== undefined ? (data.paraquedas ? "ABERTO" : "FECHADO") : undefined,
                "Accel X": data.acc_x !== undefined ? data.acc_x + " g" : undefined,
                "Accel Y": data.acc_y !== undefined ? data.acc_y + " g" : undefined,
                "Accel Z": data.acc_z !== undefined ? data.acc_z + " g" : undefined,
                "Gyro X": data.gyro_x !== undefined ? data.gyro_x + " °/s" : undefined,
                "Gyro Y": data.gyro_y !== undefined ? data.gyro_y + " °/s" : undefined,
                "Gyro Z": data.gyro_z !== undefined ? data.gyro_z + " °/s" : undefined,
                "Pitch": data.pitch !== undefined ? data.pitch + "°" : undefined,
                "Roll": data.roll !== undefined ? data.roll + "°" : undefined,
                "Yaw": data.yaw !== undefined ? data.yaw + "°" : undefined,
                "RSSI LoRa": data.rssi !== undefined ? data.rssi + " dBm" : undefined,
                "SNR LoRa": data.snr !== undefined ? data.snr + " dB" : undefined
            };

            let html = "";
            for (const [k, v] of Object.entries(fields)) {
                if (v !== undefined && v !== null && !String(v).includes("undefined")) {
                    html += `<div class="box"><span>${k}</span><span class="val">${v}</span></div>`;
                }
            }
            document.getElementById('metrics').innerHTML = html;
        }

        // ========== WebSocket (LIVE) ==========
        const ws = new WebSocket("ws://" + window.location.hostname + ":8051");

        ws.onopen = () => {
            if (currentMode === 'live') {
                document.getElementById('status').innerText = "CONECTADO À GROUND STATION";
            }
        };

        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                processPacket(data, false);
            } catch(e) {}
        };

        // ========== FASE 4: Replay ==========
        function setMode(mode) {
            currentMode = mode;
            document.getElementById('btnLive').classList.toggle('active', mode === 'live');
            document.getElementById('btnReplay').classList.toggle('active', mode === 'replay');
            document.getElementById('replayBar').classList.toggle('visible', mode === 'replay');
            const badge = document.getElementById('modeBadge');
            if (mode === 'live') {
                badge.textContent = 'MODO LIVE';
                badge.className = 'mode-badge live';
                stopReplay();
                document.getElementById('status').innerText = "MODO LIVE — Aguardando dados…";
            } else {
                badge.textContent = 'MODO REPLAY';
                badge.className = 'mode-badge replay';
                document.getElementById('status').innerText = "MODO REPLAY — Carrega um CSV";
            }
        }

        function parseCSV(text) {
            const lines = text.trim().split(/\r?\n/);
            if (lines.length < 2) return [];
            const headers = lines[0].split(',').map(h => h.trim().toLowerCase());
            const rows = [];
            for (let i = 1; i < lines.length; i++) {
                const cols = lines[i].split(',');
                const obj = {};
                headers.forEach((h, idx) => {
                    let v = cols[idx] !== undefined ? cols[idx].trim() : '';
                    if (v === '') { obj[h] = null; return; }
                    const num = parseFloat(v);
                    obj[h] = isNaN(num) ? v : num;
                });
                // Normalize boolean-ish
                if (obj.paraquedas === 1 || obj.paraquedas === '1' || obj.paraquedas === 'true') obj.paraquedas = true;
                if (obj.paraquedas === 0 || obj.paraquedas === '0' || obj.paraquedas === 'false') obj.paraquedas = false;
                rows.push(obj);
            }
            // Sort by tempo if present
            rows.sort((a, b) => (a.tempo || 0) - (b.tempo || 0));
            return rows;
        }

        function loadCSVFile(ev) {
            const file = ev.target.files[0];
            if (!file) return;
            const reader = new FileReader();
            reader.onload = (e) => {
                replayData = parseCSV(e.target.result);
                replayIndex = 0;
                document.getElementById('scrubber').max = Math.max(0, replayData.length - 1);
                document.getElementById('scrubber').value = 0;
                updateReplayTimeLabel();
                clearDashboardChartsOnly();
                if (replayData.length) {
                    processPacket(replayData[0], true);
                    document.getElementById('status').innerText = `REPLAY: ${replayData.length} amostras carregadas`;
                } else {
                    alert('CSV inválido ou vazio.');
                }
            };
            reader.readAsText(file);
        }

        function clearDashboardChartsOnly() {
            currentState = null;
            lastPhaseTime = -999;
            lastPhaseLabelTime = "";
            lastAlt = null;
            lastTempo = null;
            windSamples = [];
            chartConfigs.forEach(cfg => {
                const chart = charts[cfg.id];
                chart.data.labels = [];
                chart.data.datasets[0].data = [];
                chart.options.plugins.annotation.annotations = {};
                chart.update('none');
                document.getElementById(`min-${cfg.id}`).innerText = "-";
                document.getElementById(`max-${cfg.id}`).innerText = "-";
                document.getElementById(`avg-${cfg.id}`).innerText = "-";
            });
            document.getElementById('metrics').innerHTML = "";
        }

        function formatMMSS(sec) {
            sec = Math.max(0, Math.floor(sec || 0));
            const m = Math.floor(sec / 60);
            const s = sec % 60;
            return String(m).padStart(2, '0') + ':' + String(s).padStart(2, '0');
        }

        function updateReplayTimeLabel() {
            if (!replayData.length) {
                document.getElementById('replayTime').textContent = '00:00 / 00:00';
                return;
            }
            const cur = replayData[replayIndex]?.tempo || 0;
            const end = replayData[replayData.length - 1]?.tempo || 0;
            document.getElementById('replayTime').textContent = formatMMSS(cur) + ' / ' + formatMMSS(end);
            document.getElementById('scrubber').value = replayIndex;
        }

        function replayTick() {
            if (!replayPlaying || currentMode !== 'replay') return;
            if (replayIndex >= replayData.length - 1) {
                stopReplay();
                return;
            }
            const cur = replayData[replayIndex];
            const next = replayData[replayIndex + 1];
            const dtReal = Math.max(0.05, (next.tempo || 0) - (cur.tempo || 0));
            const delay = (dtReal * 1000) / replaySpeed;

            replayIndex++;
            processPacket(replayData[replayIndex], true);
            updateReplayTimeLabel();

            replayTimer = setTimeout(replayTick, delay);
        }

        function togglePlay() {
            if (!replayData.length) {
                alert('Carrega primeiro um ficheiro CSV.');
                return;
            }
            if (replayPlaying) {
                stopReplay();
            } else {
                replayPlaying = true;
                document.getElementById('btnPlayPause').textContent = '⏸ Pause';
                replayTick();
            }
        }

        function stopReplay() {
            replayPlaying = false;
            if (replayTimer) { clearTimeout(replayTimer); replayTimer = null; }
            document.getElementById('btnPlayPause').textContent = '▶ Play';
        }

        function onSpeedChange() {
            replaySpeed = parseFloat(document.getElementById('replaySpeed').value) || 1;
        }

        function onScrub(val) {
            stopReplay();
            replayIndex = parseInt(val, 10) || 0;
            clearDashboardChartsOnly();
            // Rebuild charts up to this point (lightweight: only last packet UI + full series)
            for (let i = 0; i <= replayIndex; i++) {
                const d = replayData[i];
                const numTime = d.tempo !== undefined ? parseFloat(d.tempo) : 0;
                const t = numTime + "s";
                if (d.estado && d.estado !== currentState) {
                    currentState = d.estado;
                    addPhaseLine(currentState, t, numTime);
                }
                chartConfigs.forEach(cfg => {
                    const chart = charts[cfg.id];
                    const v = d[cfg.key];
                    if (v !== undefined && v !== null) {
                        chart.data.labels.push(t);
                        chart.data.datasets[0].data.push(v);
                    }
                });
            }
            chartConfigs.forEach(cfg => {
                charts[cfg.id].update('none');
                updateKPIs(cfg.id, charts[cfg.id].data.datasets[0].data);
            });
            if (replayData[replayIndex]) processPacket(replayData[replayIndex], true);
            updateReplayTimeLabel();
        }

        function replaySeek(deltaSec) {
            if (!replayData.length) return;
            stopReplay();
            const curT = replayData[replayIndex]?.tempo || 0;
            const target = curT + deltaSec;
            // Find nearest index
            let best = replayIndex;
            let bestDiff = Infinity;
            for (let i = 0; i < replayData.length; i++) {
                const diff = Math.abs((replayData[i].tempo || 0) - target);
                if (diff < bestDiff) { bestDiff = diff; best = i; }
            }
            onScrub(best);
        }

        // ========== Export / Clear (original) ==========
        function downloadCSV() {
            if (rawDataLog.length === 0 && currentMode === 'live') {
                alert("Não existem dados acumulados para exportar.");
                return;
            }
            const source = currentMode === 'replay' && replayData.length ? replayData : rawDataLog;
            if (!source.length) {
                alert("Não existem dados acumulados para exportar.");
                return;
            }
            let csv = "id,tempo,estado,altitude,velocidade,forca_g,temperatura,humidade,pressao,eco2,tvoc,uv,lux\\n";
            source.forEach(row => {
                csv += `${row.id},${row.tempo},${row.estado},${row.altitude},${row.velocidade},${row.forca_g},${row.temperatura},${row.humidade},${row.pressao},${row.eco2},${row.tvoc},${row.uv},${row.lux}\\n`;
            });
            const blob = new Blob([csv], { type: 'text/csv' });
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            
            const now = new Date();
            const timestamp = now.toISOString().replace('T', '_').replace(/:/g, '-').slice(0, 19);
            
            a.setAttribute('href', url);
            a.setAttribute('download', `voo_cansat_${timestamp}.csv`);
            a.click();
        }

        async function downloadChartsAsImages() {
            if (rawDataLog.length === 0 && !(currentMode === 'replay' && replayData.length)) {
                alert("Não existem dados para gerar imagens dos gráficos.");
                return;
            }

            const now = new Date();
            const timestamp = now.toISOString().replace('T', '_').replace(/:/g, '-').slice(0, 19);

            for (let i = 0; i < chartConfigs.length; i++) {
                const cfg = chartConfigs[i];
                const canvas = document.getElementById(cfg.id);
                
                const tempCanvas = document.createElement('canvas');
                tempCanvas.width = canvas.width;
                tempCanvas.height = canvas.height;
                const ctx = tempCanvas.getContext('2d');
                ctx.fillStyle = '#1e293b';
                ctx.fillRect(0, 0, tempCanvas.width, tempCanvas.height);
                ctx.drawImage(canvas, 0, 0);

                const link = document.createElement('a');
                link.download = `grafico_${i + 1}_${cfg.id}_${timestamp}.png`;
                link.href = tempCanvas.toDataURL('image/png');
                link.click();

                await new Promise(r => setTimeout(r, 200));
            }

            const firstCanvas = document.getElementById(chartConfigs[0].id);
            const singleW = firstCanvas.width;
            const singleH = firstCanvas.height;
            const padding = 20;

            const combinedCanvas = document.createElement('canvas');
            combinedCanvas.width = (singleW * 2) + (padding * 3);
            combinedCanvas.height = (singleH * 4) + (padding * 5);
            const cCtx = combinedCanvas.getContext('2d');

            cCtx.fillStyle = '#0f172a';
            cCtx.fillRect(0, 0, combinedCanvas.width, combinedCanvas.height);

            chartConfigs.forEach((cfg, index) => {
                const srcCanvas = document.getElementById(cfg.id);
                const col = index % 2;
                const row = Math.floor(index / 2);

                const x = padding + col * (singleW + padding);
                const y = padding + row * (singleH + padding);

                cCtx.fillStyle = '#1e293b';
                cCtx.fillRect(x, y, singleW, singleH);
                cCtx.drawImage(srcCanvas, x, y);
            });

            const combinedLink = document.createElement('a');
            combinedLink.download = `graficos_todos_combinados_${timestamp}.png`;
            combinedLink.href = combinedCanvas.toDataURL('image/png');
            combinedLink.click();
        }

        function openClearModal() {
            if (rawDataLog.length === 0 && !(currentMode === 'replay' && replayData.length)) {
                alert("O painel já se encontra sem dados.");
                return;
            }
            document.getElementById('clearModal').style.display = 'flex';
        }

        function closeClearModal() {
            document.getElementById('clearModal').style.display = 'none';
        }

        function confirmClear(shouldDownload) {
            if (shouldDownload) {
                downloadCSV();
            }
            clearDashboard();
            closeClearModal();
        }

        function clearDashboard() {
            rawDataLog = [];
            currentState = null;
            lastPhaseTime = -999;
            lastPhaseLabelTime = "";
            lastAlt = null;
            lastTempo = null;
            windSamples = [];
            stopReplay();
            replayData = [];
            replayIndex = 0;
            document.getElementById('scrubber').max = 0;
            document.getElementById('scrubber').value = 0;
            updateReplayTimeLabel();
            chartConfigs.forEach(cfg => {
                const chart = charts[cfg.id];
                chart.data.labels = [];
                chart.data.datasets[0].data = [];
                chart.options.plugins.annotation.annotations = {};
                chart.update('none');

                document.getElementById(`min-${cfg.id}`).innerText = "-";
                document.getElementById(`max-${cfg.id}`).innerText = "-";
                document.getElementById(`avg-${cfg.id}`).innerText = "-";
            });
            document.getElementById('metrics').innerHTML = "";
            document.getElementById('status').innerText = "PAINEL LIMPO / AGUARDANDO NOVO VOO";
            document.getElementById('paraDot').className = 'para-dot';
            document.getElementById('paraLabel').textContent = '—';
            document.getElementById('paraSub').textContent = 'Aguardando telemetria…';
            document.getElementById('freefallAlert').style.display = 'none';
            drawWindRose(null, null);
            drawAltimeter(null);
            drawVSI(null);
            drawAttitude(0, 0);
            updateHabitability({});

            if (ws.readyState === WebSocket.OPEN && currentMode === 'live') {
                ws.send(JSON.stringify({ action: "clear" }));
            }
        }

        // Initial empty gauges
        drawWindRose(null, null);
        drawAltimeter(null);
        drawVSI(null);
        drawAttitude(0, 0);
        updateHabitability({});
    </script>
</body>
</html>
"""

from http.server import HTTPServer, BaseHTTPRequestHandler

class SimpleHTTPHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(HTML_CODE.encode('utf-8'))
    def log_message(self, format, *args):
        return

def run_http_server():
    server = HTTPServer(('127.0.0.1', 8050), SimpleHTTPHandler)
    print("🌐 [Web Server] Aceda ao site em: http://127.0.0.1:8050")
    server.serve_forever()

loop = None

async def main():
    global loop
    loop = asyncio.get_running_loop()
    
    threading.Thread(target=udp_receiver, daemon=True).start()
    threading.Thread(target=run_http_server, daemon=True).start()
    
    print("🚀 [WebSocket Server] Ativo na porta 8051...")
    async with websockets.serve(ws_handler, "127.0.0.1", 8051):
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())
