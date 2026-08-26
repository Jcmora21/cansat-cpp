import asyncio
import socket
import json
import websockets
import threading
import csv
import os
from datetime import datetime

# 📁 Criar/Garantir a pasta dedicada para os ficheiros CSV
LOG_DIR = "dados_voo"
os.makedirs(LOG_DIR, exist_ok=True)

# 🕒 Definir nome do ficheiro CSV com Data e Hora marcadas (ex: voo_cansat_2026-08-26_03-00-15.csv)
session_time = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
csv_filename = os.path.join(LOG_DIR, f"voo_cansat_{session_time}.csv")

latest_packet = None
flight_history = []
CONNECTED_CLIENTS = set()

# Cabeçalho completo do CSV
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

# --- THREAD UDP (Recebe dados e escreve na pasta dados_voo/) ---
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
            
            parsed = json.loads(payload)
            row = [parsed.get(h, "") for h in csv_headers]
            with open(csv_filename, mode='a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(row)
        except Exception:
            pass

# --- WEBSOCKET SERVER ---
async def ws_handler(websocket):
    CONNECTED_CLIENTS.add(websocket)
    try:
        for past_packet in flight_history:
            await websocket.send(past_packet)
            
        while True:
            if latest_packet is not None:
                await websocket.send(latest_packet)
            await asyncio.sleep(0.2)
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        CONNECTED_CLIENTS.remove(websocket)

# --- SERVIDOR WEB HTTP ---
HTML_CODE = """<!DOCTYPE html>
<html lang="pt">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CanSat Ground Station Live</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body { font-family: system-ui, -apple-system, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 12px; }
        .header { display: flex; justify-content: space-between; align-items: center; background: #1e293b; padding: 12px 20px; border-radius: 8px; margin-bottom: 12px; }
        .actions { display: flex; gap: 10px; align-items: center; }
        .status { font-weight: bold; padding: 6px 14px; border-radius: 20px; background: #334155; color: #38bdf8; font-size: 0.9em; }
        .btn { border: none; padding: 8px 14px; border-radius: 6px; font-weight: bold; cursor: pointer; font-size: 0.85em; }
        .btn-export { background: #0284c7; color: white; }
        .btn-export:hover { background: #0369a1; }
        .btn-clear { background: #ef4444; color: white; }
        .btn-clear:hover { background: #dc2626; }
        .btn-cancel { background: #64748b; color: white; }
        .btn-cancel:hover { background: #475569; }
        .grid { display: grid; grid-template-columns: 2fr 1fr; gap: 12px; }
        @media (max-width: 800px) { .grid { grid-template-columns: 1fr; } }
        .charts { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
        .card { background: #1e293b; padding: 10px; border-radius: 8px; }
        .metrics { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; max-height: 520px; overflow-y: auto; padding-right: 4px; }
        .box { background: #0f172a; padding: 6px 10px; border-radius: 4px; display: flex; justify-content: space-between; font-size: 0.85em; }
        .val { font-weight: bold; color: #38bdf8; text-align: right; }
        h3 { margin-top: 0; font-size: 1.1em; color: #cbd5e1; }

        /* Modal de Confirmação */
        .modal-overlay { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0, 0, 0, 0.7); backdrop-filter: blur(4px); z-index: 1000; justify-content: center; align-items: center; }
        .modal-box { background: #1e293b; padding: 24px; border-radius: 12px; max-width: 420px; width: 90%; box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.5); text-align: center; border: 1px solid #334155; }
        .modal-title { font-size: 1.2em; font-weight: bold; margin-bottom: 12px; color: #f8fafc; }
        .modal-desc { font-size: 0.95em; color: #94a3b8; margin-bottom: 20px; line-height: 1.4; }
        .modal-buttons { display: flex; flex-direction: column; gap: 10px; }
        .modal-buttons .btn { width: 100%; padding: 10px; font-size: 0.95em; }
    </style>
</head>
<body>

    <div class="header">
        <h2 style="margin:0; font-size: 1.2em;">📡 CANSAT GROUND STATION</h2>
        <div class="actions">
            <button class="btn btn-export" onclick="downloadCSV()">📥 Exportar CSV</button>
            <button class="btn btn-clear" onclick="openClearModal()">🗑️ Limpar Dados</button>
            <div id="status" class="status">AGUARDANDO DADOS...</div>
        </div>
    </div>

    <div class="grid">
        <div class="charts">
            <div class="card"><canvas id="chartAlt"></canvas></div>
            <div class="card"><canvas id="chartVel"></canvas></div>
            <div class="card"><canvas id="chartG"></canvas></div>
            <div class="card"><canvas id="chartCO2"></canvas></div>
            <div class="card"><canvas id="chartTemp"></canvas></div>
            <div class="card"><canvas id="chartPress"></canvas></div>
            <div class="card"><canvas id="chartHum"></canvas></div>
            <div class="card"><canvas id="chartUV"></canvas></div>
            <div class="card"><canvas id="chartLux"></canvas></div>
            <div class="card"><canvas id="chartTVOC"></canvas></div>
        </div>

        <div class="card">
            <h3>📊 Telemetria Completa ao Vivo</h3>
            <div class="metrics" id="metrics"></div>
        </div>
    </div>

    <!-- Modal de Confirmação Personalizado -->
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

    <script>
        window.addEventListener("beforeunload", function (e) {
            e.preventDefault();
            e.returnValue = "Tens a certeza que queres recarregar a página? A transmissão ao vivo será interrompida.";
        });

        let rawDataLog = [];

        function makeChart(id, label, color) {
            const ctx = document.getElementById(id).getContext('2d');
            return new Chart(ctx, {
                type: 'line',
                data: { labels: [], datasets: [{ label: label, data: [], borderColor: color, borderWidth: 2, pointRadius: 0 }] },
                options: {
                    responsive: true,
                    animation: false,
                    scales: { x: { display: false }, y: { ticks: { color: '#94a3b8' } } }
                }
            });
        }

        const charts = {
            cAlt: makeChart('chartAlt', 'Altitude (m)', '#38bdf8'),
            cVel: makeChart('chartVel', 'Velocidade (m/s)', '#fbbf24'),
            cG: makeChart('chartG', 'Força-G (g)', '#f43f5e'),
            cCO2: makeChart('chartCO2', 'eCO2 (ppm)', '#34d399'),
            cTemp: makeChart('chartTemp', 'Temperatura (°C)', '#ec4899'),
            cPress: makeChart('chartPress', 'Pressão (hPa)', '#8b5cf6'),
            cHum: makeChart('chartHum', 'Humidade (%)', '#06b6d4'),
            cUV: makeChart('chartUV', 'Índice UV', '#eab308'),
            cLux: makeChart('chartLux', 'Luminosidade (lx)', '#f97316'),
            cTVOC: makeChart('chartTVOC', 'TVOC (ppb)', '#10b981')
        };

        function pushData(chart, label, val) {
            chart.data.labels.push(label);
            chart.data.datasets[0].data.push(val);
            chart.update('none');
        }

        const ws = new WebSocket("ws://" + window.location.hostname + ":8051");

        ws.onopen = () => {
            document.getElementById('status').innerText = "CONECTADO À GROUND STATION";
        };

        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                rawDataLog.push(data);
                document.getElementById('status').innerText = "ESTADO: " + (data.estado || "N/D");
                
                const t = data.tempo + "s";
                pushData(charts.cAlt, t, data.altitude);
                pushData(charts.cVel, t, data.velocidade);
                pushData(charts.cG, t, data.forca_g);
                pushData(charts.cCO2, t, data.eco2);
                pushData(charts.cTemp, t, data.temperatura);
                pushData(charts.cPress, t, data.pressao);
                pushData(charts.cHum, t, data.humidade);
                pushData(charts.cUV, t, data.uv);
                pushData(charts.cLux, t, data.lux);
                pushData(charts.cTVOC, t, data.tvoc);

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
            } catch(e) {}
        };

        // Exportar CSV com data e hora no nome do ficheiro descarregado
        function downloadCSV() {
            if (rawDataLog.length === 0) {
                alert("Não existem dados acumulados para exportar.");
                return;
            }
            let csv = "id,tempo,estado,altitude,velocidade,forca_g,temperatura,humidade,pressao,eco2,tvoc,uv,lux\\n";
            rawDataLog.forEach(row => {
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

        function openClearModal() {
            if (rawDataLog.length === 0) {
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
            Object.values(charts).forEach(chart => {
                chart.data.labels = [];
                chart.data.datasets[0].data = [];
                chart.update('none');
            });
            document.getElementById('metrics').innerHTML = "";
            document.getElementById('status').innerText = "PAINEL LIMPO / AGUARDANDO NOVO VOO";
        }
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
    print("🌐 [Web Server] Servidor ativo em http://127.0.0.1:8050")
    server.serve_forever()

async def main():
    threading.Thread(target=udp_receiver, daemon=True).start()
    threading.Thread(target=run_http_server, daemon=True).start()
    
    print("🚀 [WebSocket Server] Ativo na porta 8051...")
    async with websockets.serve(ws_handler, "127.0.0.1", 8051):
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())
