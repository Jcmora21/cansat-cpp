import time
import asyncio
import socket
import json
import websockets
import threading
import csv
import os
import math
import re
import sys
import zlib
from collections import deque
from datetime import datetime

# Keep diagnostic output from terminating the Windows process on non-UTF-8 consoles.
for output_stream in (sys.stdout, sys.stderr):
    reconfigure = getattr(output_stream, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(errors="backslashreplace")

# 📁 Criar pasta para logs
LOG_DIR = "dados_voo"
os.makedirs(LOG_DIR, exist_ok=True)

session_time = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
csv_filename = os.path.join(LOG_DIR, f"voo_cansat_{session_time}.csv")

latest_packet = None
flight_history = []

cansats = {}

CONNECTED_CLIENTS = set()
transport = None
peer_addresses = {}
cansats_lock = threading.RLock()
capture_state_lock = threading.RLock()
capture_enabled = True
csv_logging_enabled = True
discarded_while_paused = 0
MAX_FLIGHT_HISTORY = 2000

csv_headers = [
    "id",
    "cansat_id",
    "tempo",
    "estado",
    "altitude",
    "velocidade",
    "aceleracao",
    "temperatura",
    "humidade",
    "pressao",
    "eco2",
    "tvoc",
    "uv",
    "lux",
    "paraquedas",
    "acc_x",
    "acc_y",
    "acc_z",
    "gyro_x",
    "gyro_y",
    "gyro_z",
    "pitch",
    "roll",
    "yaw",
    "rssi",
    "snr",
]


def init_csv(filename):
    with open(filename, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(csv_headers)


init_csv(csv_filename)
print(f"💾 [Logger] Gravação automática de dados ativa em: {csv_filename}")


REQUIRED_TOP_LEVEL_FIELDS = [
    "protocol",
    "version",
    "type",
    "cansat_id",
    "sequence",
    "mission_time_ms",
    "state",
    "data",
    "link",
]

REQUIRED_DATA_FIELDS = [
    "altitude",
    "velocity",
    "acceleration",
    "force_g",
    "temperature",
    "humidity",
    "pressure",
    "eco2",
    "tvoc",
    "uv",
    "lux",
    "acc_x",
    "acc_y",
    "acc_z",
    "gyro_x",
    "gyro_y",
    "gyro_z",
    "pitch",
    "roll",
    "yaw",
    "parachute",
]

REQUIRED_LINK_FIELDS = ["rssi", "snr"]


def reject_nonstandard_json_constant(value):
    raise ValueError(f"constante JSON nao permitida: {value}")


def is_finite_number(value):
    return (type(value) is int and value.bit_length() <= 1023) or (
        type(value) is float and math.isfinite(value)
    )


def calculate_crc32(payload):
    return format(zlib.crc32(payload.encode("utf-8")) & 0xFFFFFFFF, "08X")


def protect_control_message(message):
    protected = message.copy()
    protected.pop("crc", None)
    checksum_payload = json.dumps(
        protected, separators=(",", ":"), sort_keys=True
    )
    protected["crc"] = calculate_crc32(checksum_payload)
    return protected


def validate_telemetry_packet(packet):
    if not isinstance(packet, dict):
        return False, ["packet"]

    missing = []

    for field in REQUIRED_TOP_LEVEL_FIELDS:
        if field not in packet:
            missing.append(field)

    data = packet.get("data")

    if isinstance(data, dict):
        for field in REQUIRED_DATA_FIELDS:
            if field not in data:
                missing.append(f"data.{field}")
    else:
        missing.append("data")

    link = packet.get("link")

    if isinstance(link, dict):
        for field in REQUIRED_LINK_FIELDS:
            if field not in link:
                missing.append(f"link.{field}")
    else:
        missing.append("link")

    if missing:
        return False, missing

    if packet.get("protocol") != "CANSAT-TLM":
        return False, ["protocol"]
    if type(packet.get("version")) is not int or packet["version"] != 1:
        return False, ["version"]
    if packet.get("type") != "telemetry":
        return False, ["type"]
    for field in ("cansat_id", "sequence", "mission_time_ms"):
        if (
            type(packet.get(field)) is not int
            or packet[field] < 0
            or packet[field] > 2**63 - 1
        ):
            return False, [field]
    if not isinstance(packet.get("state"), str) or not packet["state"].strip():
        return False, ["state"]

    for field in REQUIRED_DATA_FIELDS:
        value = data[field]
        if field == "parachute":
            if type(value) is not bool:
                return False, [f"data.{field}"]
        elif not is_finite_number(value):
            return False, [f"data.{field}"]

    for field in REQUIRED_LINK_FIELDS:
        value = link[field]
        if not is_finite_number(value):
            return False, [f"link.{field}"]

    return True, []


def verify_packet_crc(packet):
    crc_received = packet.get("crc")
    if not isinstance(crc_received, str) or not re.fullmatch(r"[0-9A-Fa-f]{1,8}", crc_received):
        return False

    packet_without_crc = packet.copy()
    packet_without_crc.pop("crc", None)
    crc_payload = json.dumps(packet_without_crc, separators=(",", ":"), sort_keys=True)
    return crc_received.upper().zfill(8) == calculate_crc32(crc_payload)


def new_cansat_state():
    return {
        "latest": None,
        "history": [],
        "has_telemetry": False,
        "landed_at": None,
        "last_received": time.time(),
        "status": "ONLINE",
        "last_sequence": None,
        "seen_sequences": set(),
        "seen_sequence_order": deque(),
        "lost_sequences": set(),
        "lost_sequence_order": deque(),
        "incomplete_sequences": set(),
        "incomplete_sequence_order": deque(),
        "lost_packets": 0,
        "incomplete_packets": 0,
        "invalid_crc_packets": 0,
        "duplicate_packets": 0,
        "received_packets": 0,
    }


def update_auto_csv_logging(parsed):
    global csv_logging_enabled

    cansat_id = parsed.get("cansat_id")
    altitude = parsed.get("altitude")
    state = parsed.get("estado")
    landed_states = {"SOLO", "LANDED", "ATERRADO", "ATERRAGEM"}

    if (
        cansat_id is None
        or not is_finite_number(altitude)
        or not isinstance(state, str)
    ):
        return

    now = time.time()
    is_landed = state.strip().upper() in landed_states and altitude <= 0.1
    with cansats_lock:
        cansat = get_cansat_state(cansat_id)
        cansat["has_telemetry"] = True
        if is_landed and cansat["landed_at"] is None:
            cansat["landed_at"] = now
            print(f"[Logger] CanSat {cansat_id} aterrou; a aguardar 30 segundos.")

        active_cansats = [
            item for item in cansats.values() if item["has_telemetry"]
        ]
        all_cansats_landed = bool(active_cansats) and all(
            item["landed_at"] is not None for item in active_cansats
        )
        last_landing = max(
            (
                item["landed_at"]
                for item in active_cansats
                if item["landed_at"] is not None
            ),
            default=None,
        )

    if not all_cansats_landed or last_landing is None or now - last_landing < 30:
        return

    with capture_state_lock:
        if not csv_logging_enabled:
            return
        csv_logging_enabled = False

    print("[Logger] Gravacao automatica CSV terminada; telemetria continua ativa.")
    emit_event({
        "type": "csv_logging_state",
        "enabled": False,
    })


def get_cansat_state(cansat_id):
    with cansats_lock:
        if cansat_id not in cansats:
            cansats[cansat_id] = new_cansat_state()
        return cansats[cansat_id]


def classify_sequence(cansat, sequence):
    if sequence in cansat["seen_sequences"]:
        cansat["duplicate_packets"] += 1
        return "duplicate", []

    if sequence in cansat["lost_sequences"]:
        forget_bounded_sequence(cansat, "lost_sequences", "lost_sequence_order", sequence)
        cansat["lost_packets"] -= 1

    forget_bounded_sequence(
        cansat, "incomplete_sequences", "incomplete_sequence_order", sequence
    )
    last_sequence = cansat["last_sequence"]
    newly_lost = []

    if last_sequence is not None and sequence > last_sequence + 1:
        for missing_sequence in range(last_sequence + 1, sequence):
            if (
                missing_sequence not in cansat["seen_sequences"]
                and missing_sequence not in cansat["incomplete_sequences"]
                and missing_sequence not in cansat["lost_sequences"]
            ):
                remember_bounded_sequence(
                    cansat,
                    "lost_sequences",
                    "lost_sequence_order",
                    missing_sequence,
                )
                newly_lost.append(missing_sequence)

    if newly_lost:
        cansat["lost_packets"] += len(newly_lost)

    remember_bounded_sequence(
        cansat, "seen_sequences", "seen_sequence_order", sequence
    )
    if last_sequence is None or sequence > last_sequence:
        cansat["last_sequence"] = sequence
    cansat["received_packets"] += 1
    return "received", newly_lost


def record_incomplete_packet(cansat, sequence):
    cansat["incomplete_packets"] += 1
    if sequence is not None:
        if sequence in cansat["lost_sequences"]:
            forget_bounded_sequence(
                cansat, "lost_sequences", "lost_sequence_order", sequence
            )
            cansat["lost_packets"] -= 1
        remember_bounded_sequence(
            cansat,
            "incomplete_sequences",
            "incomplete_sequence_order",
            sequence,
        )


def remember_bounded_sequence(cansat, set_key, order_key, sequence):
    values = cansat[set_key]
    order = cansat[order_key]
    if sequence in values:
        return
    if len(order) >= MAX_FLIGHT_HISTORY:
        values.discard(order.popleft())
    values.add(sequence)
    order.append(sequence)


def forget_bounded_sequence(cansat, set_key, order_key, sequence):
    cansat[set_key].discard(sequence)
    order = cansat[order_key]
    if sequence in order:
        order.remove(sequence)


def get_packet_counts(cansat):
    return {
        "received": cansat["received_packets"],
        "lost": cansat["lost_packets"],
        "duplicate": cansat["duplicate_packets"],
        "incomplete": cansat["incomplete_packets"],
        "crc_invalid": cansat["invalid_crc_packets"],
    }


def receiving_state_event():
    with capture_state_lock:
        return {
            "type": "receiver_state",
            "enabled": capture_enabled,
            "discarded_while_paused": discarded_while_paused,
            "csv_logging_enabled": csv_logging_enabled,
        }


def append_bounded(history, payload, limit=MAX_FLIGHT_HISTORY):
    history.append(payload)
    if len(history) > limit:
        del history[:-limit]


class UDPTransport:
    """Adaptador de transporte; o protocolo nao depende do radio utilizado."""

    def __init__(self, host, port):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind((host, port))

    def receive(self):
        return self.socket.recvfrom(4096)

    def send(self, payload, address):
        self.socket.sendto(payload.encode("utf-8"), address)


def send_ack(cansat_id, sequence, address):
    if transport is None:
        return
    ack = protect_control_message(
        {"type": "ack", "cansat_id": cansat_id, "sequence": sequence}
    )
    transport.send(json.dumps(ack, separators=(",", ":")), address)


def emit_event(event):
    if CONNECTED_CLIENTS:
        asyncio.run_coroutine_threadsafe(broadcast(json.dumps(event)), loop)


def handle_command(message):
    cansat_id = message.get("cansat_id")
    command = message.get("command")
    if type(cansat_id) is not int or not isinstance(command, str) or not command:
        return {"type": "command_status", "status": "error", "reason": "invalid_command"}

    address = peer_addresses.get(cansat_id)
    if transport is None or address is None:
        return {"type": "command_status", "cansat_id": cansat_id, "status": "error", "reason": "cansat_unavailable"}

    command_payload = protect_control_message({
        "type": "command",
        "cansat_id": cansat_id,
        "command": command,
    })
    try:
        transport.send(json.dumps(command_payload, separators=(",", ":")), address)
    except OSError:
        return {"type": "command_status", "cansat_id": cansat_id, "status": "error", "reason": "transport_error"}
    return {"type": "command_status", "cansat_id": cansat_id, "status": "sent"}


# --- RECEIVER DO TRANSPORTE ---
def transport_receiver(transport_factory=UDPTransport):
    global latest_packet, flight_history, transport, discarded_while_paused

    transport = transport_factory("127.0.0.1", 5005)

    print("[Receiver] A escutar telemetria pelo transporte configurado...")

    while True:
        try:
            data, address = transport.receive()
        except OSError as error:
            print(f"[Receiver] Falha no transporte: {error}")
            return

        try:
            payload = data.decode("utf-8")
            packet = json.loads(
                payload,
                parse_constant=reject_nonstandard_json_constant,
            )
        except UnicodeDecodeError as error:
            print(f"Pacote ignorado: codificacao UTF-8 invalida ({error})")
            continue
        except (json.JSONDecodeError, ValueError, RecursionError) as error:
            print(f"Pacote ignorado: JSON invalido ({error})")
            continue

        if not isinstance(packet, dict):
            print("Pacote ignorado: JSON nao e um objeto")
            continue

        if packet.get("type") == "command_ack":
            if verify_packet_crc(packet):
                print(
                    f"Resposta de comando recebida (CanSat "
                    f"{packet.get('cansat_id', '?')}, "
                    f"status={packet.get('status', '?')})"
                )
            else:
                print("Resposta de comando descartada: CRC invalido")
            continue

        is_protocol_packet = packet.get("protocol") == "CANSAT-TLM"
        if is_protocol_packet:
            if packet.get("version") != 1 or packet.get("type") != "telemetry":
                print("Pacote CANSAT-TLM ignorado: versao ou tipo nao suportado.")
                continue

            if not verify_packet_crc(packet):
                cansat_id = packet.get("cansat_id")
                if type(cansat_id) is int and cansat_id >= 0:
                    with cansats_lock:
                        cansat = get_cansat_state(cansat_id)
                        cansat["invalid_crc_packets"] += 1
                        packet_counts = get_packet_counts(cansat)
                    emit_event({
                        "type": "packet_status",
                        "packet_status": "crc_invalid",
                        "cansat_id": cansat_id,
                        "sequence": packet.get("sequence"),
                        "packet_counts": packet_counts,
                    })
                print(
                    f"CRC invalido (CanSat {cansat_id}, "
                    f"seq {packet.get('sequence', '?')})"
                )
                continue

            valid, missing_fields = validate_telemetry_packet(packet)
            if not valid:
                cansat_id = packet.get("cansat_id")
                sequence = packet.get("sequence")
                if type(cansat_id) is int and cansat_id >= 0:
                    with cansats_lock:
                        cansat = get_cansat_state(cansat_id)
                        sequence = sequence if type(sequence) is int and sequence >= 0 else None
                        record_incomplete_packet(cansat, sequence)
                        packet_counts = get_packet_counts(cansat)
                    emit_event({
                        "type": "packet_status",
                        "packet_status": "incomplete",
                        "cansat_id": cansat_id,
                        "sequence": sequence,
                        "packet_counts": packet_counts,
                    })
                print(
                    f"Pacote incompleto (CanSat {cansat_id}, "
                    f"seq {sequence}): {', '.join(missing_fields)}"
                )
                continue

            cansat_id = packet["cansat_id"]
            sequence = packet["sequence"]
            mission_time_ms = packet["mission_time_ms"]
            state = packet["state"]

            data_block = packet["data"]
            link_block = packet["link"]
            parsed = {
                "id": sequence,
                "cansat_id": cansat_id,
                "sequence": sequence,
                "mission_time_ms": mission_time_ms,
                "tempo": mission_time_ms / 1000.0,
                "estado": state,
                "altitude": data_block.get("altitude"),
                "velocidade": data_block.get("velocity"),
                "aceleracao": data_block.get("acceleration"),
                "forca_g": data_block.get("force_g"),
                "temperatura": data_block.get("temperature"),
                "humidade": data_block.get("humidity"),
                "pressao": data_block.get("pressure"),
                "eco2": data_block.get("eco2"),
                "tvoc": data_block.get("tvoc"),
                "uv": data_block.get("uv"),
                "lux": data_block.get("lux"),
                "acc_x": data_block.get("acc_x"),
                "acc_y": data_block.get("acc_y"),
                "acc_z": data_block.get("acc_z"),
                "gyro_x": data_block.get("gyro_x"),
                "gyro_y": data_block.get("gyro_y"),
                "gyro_z": data_block.get("gyro_z"),
                "pitch": data_block.get("pitch"),
                "roll": data_block.get("roll"),
                "yaw": data_block.get("yaw"),
                "paraquedas": data_block.get("parachute", False),
                "rssi": link_block.get("rssi"),
                "snr": link_block.get("snr"),
            }
        else:
            parsed = packet

        cansat_id = parsed.get("cansat_id")
        if cansat_id is not None and (type(cansat_id) is not int or cansat_id < 0):
            print(f"Pacote ignorado: cansat_id invalido ({cansat_id!r})")
            continue

        if cansat_id is not None:
            peer_addresses[cansat_id] = address
            with cansats_lock:
                cansat = get_cansat_state(cansat_id)
                was_offline = cansat["status"] == "OFFLINE"
                cansat["last_received"] = time.time()
                cansat["status"] = "ONLINE"

                if was_offline:
                    print(
                        f"CanSat {cansat_id} ONLINE novamente "
                        f"(seq={parsed.get('sequence', '?')})"
                    )
                    online_event = {
                        "type": "cansat_status",
                        "cansat_id": cansat_id,
                        "status": "ONLINE",
                        "sequence": parsed.get("sequence"),
                        "mission_time_ms": parsed.get("mission_time_ms"),
                        "lost_packets": cansat["lost_packets"],
                        "packet_counts": get_packet_counts(cansat),
                    }
                else:
                    online_event = None

            if online_event is not None:
                emit_event(online_event)

            current_sequence = parsed.get("sequence")
            if type(current_sequence) is int and current_sequence >= 0:
                if is_protocol_packet:
                    try:
                        send_ack(cansat_id, current_sequence, address)
                    except OSError as error:
                        print(f"Falha ao enviar ACK (CanSat {cansat_id}): {error}")

                with cansats_lock:
                    cansat = get_cansat_state(cansat_id)
                    packet_status, newly_lost = classify_sequence(cansat, current_sequence)
                    packet_counts = get_packet_counts(cansat)
                    lost_packets = cansat["lost_packets"]

                if packet_status == "duplicate":
                    if is_protocol_packet:
                        emit_event({
                            "type": "packet_status",
                            "packet_status": "duplicate",
                            "cansat_id": cansat_id,
                            "sequence": current_sequence,
                            "packet_counts": packet_counts,
                        })
                    continue

                for lost_sequence in newly_lost:
                    emit_event({
                        "type": "packet_status",
                        "packet_status": "lost",
                        "cansat_id": cansat_id,
                        "sequence": lost_sequence,
                        "lost_packets": lost_packets,
                        "packet_counts": packet_counts,
                    })

                parsed["packet_status"] = "received"

        update_auto_csv_logging(parsed)
        normalized_payload = json.dumps(parsed, separators=(",", ":"), allow_nan=False)

        try:
            with capture_state_lock:
                if not capture_enabled:
                    discarded_while_paused += 1
                    continue

                if csv_logging_enabled:
                    row = [parsed.get(header, "") for header in csv_headers]
                    with open(csv_filename, mode="a", newline="", encoding="utf-8") as file:
                        csv.writer(file).writerow(row)

                if cansat_id is not None:
                    with cansats_lock:
                        cansat = get_cansat_state(cansat_id)
                        cansat["latest"] = normalized_payload
                        append_bounded(cansat["history"], normalized_payload)

                latest_packet = normalized_payload
                append_bounded(flight_history, normalized_payload)
        except OSError as error:
            print(f"[Logger] Falha ao guardar pacote no CSV: {error}")
            continue

        if CONNECTED_CLIENTS:
            with cansats_lock:
                cansat = cansats.get(cansat_id, {}) if cansat_id is not None else {}
                cansat_status = cansat.get("status", "ONLINE")
                lost_packets = cansat.get("lost_packets", 0)
                packet_counts = get_packet_counts(cansat) if cansat else {}

            emit_event({
                "type": "telemetry",
                "data": parsed,
                "cansat_status": cansat_status,
                "lost_packets": lost_packets,
                "packet_status": parsed.get("packet_status", "received"),
                "packet_counts": packet_counts,
            })
def check_cansat_status():
    while True:
        try:
            agora = time.time()

            offline_events = []
            with cansats_lock:
                for cansat_id, cansat in cansats.items():
                    if agora - cansat["last_received"] >= 2.0:
                        if cansat["status"] != "OFFLINE":
                            cansat["status"] = "OFFLINE"
                            offline_events.append({
                                "type": "cansat_status",
                                "cansat_id": cansat_id,
                                "status": "OFFLINE",
                                "sequence": cansat["last_sequence"],
                                "lost_packets": cansat["lost_packets"],
                                "packet_counts": get_packet_counts(cansat),
                            })
                            print(f"🔴 CanSat {cansat_id} OFFLINE")

            for status_payload in offline_events:
                emit_event(status_payload)

            time.sleep(0.5)

        except Exception as e:
            print(f"⚠️ [Status] Erro: {e}")


async def broadcast(message):
    if CONNECTED_CLIENTS:
        clients = tuple(CONNECTED_CLIENTS)
        results = await asyncio.gather(
            *(client.send(message) for client in clients),
            return_exceptions=True,
        )
        for client, result in zip(clients, results):
            if isinstance(result, Exception):
                print(f"[WebSocket] Falha ao enviar evento: {result}")
                CONNECTED_CLIENTS.discard(client)


# --- WEBSOCKET SERVER ---
async def ws_handler(websocket):
    global capture_enabled, discarded_while_paused, flight_history, latest_packet
    CONNECTED_CLIENTS.add(websocket)
    try:
        with capture_state_lock:
            past_packets = flight_history[:]
            state_event = receiving_state_event()
        await websocket.send(json.dumps(state_event))
        for past_packet in past_packets:
            await websocket.send(past_packet)

        async for message in websocket:
            try:
                data = json.loads(
                    message,
                    parse_constant=reject_nonstandard_json_constant,
                )
            except (json.JSONDecodeError, ValueError, RecursionError) as error:
                print(f"[WebSocket] Mensagem JSON invalida: {error}")
                continue

            if not isinstance(data, dict):
                print("[WebSocket] Mensagem ignorada: esperado um objeto JSON.")
                continue

            if data.get("action") == "clear":
                with capture_state_lock:
                    flight_history = []
                    latest_packet = None
                    print("🗑️ [Server] Histórico de voo limpo a pedido do cliente.")
            elif data.get("action") == "set_capture":
                enabled = data.get("enabled")
                if type(enabled) is not bool:
                    await websocket.send(json.dumps({
                        "type": "command_status",
                        "status": "error",
                        "reason": "invalid_capture_state",
                    }))
                    continue
                with capture_state_lock:
                    capture_enabled = enabled
                await broadcast(json.dumps(receiving_state_event()))
            elif data.get("type") == "command":
                result = handle_command(data)
                await websocket.send(json.dumps(result))
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        CONNECTED_CLIENTS.discard(websocket)


# --- SERVIDOR WEB HTTP ---
HTML_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web", "index.html")
with open(HTML_FILE, encoding="utf-8") as page_file:
    HTML_CODE = page_file.read()


from http.server import HTTPServer, BaseHTTPRequestHandler


class SimpleHTTPHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/download_csv":
            try:
                with capture_state_lock:
                    with open(csv_filename, "rb") as file:
                        contents = file.read()
            except FileNotFoundError:
                self.send_error(404, "CSV de voo nao encontrado")
                return
            except OSError as error:
                print(f"[Logger] Falha ao preparar o CSV para exportacao: {error}")
                self.send_error(500, "Nao foi possivel ler o CSV de voo")
                return

            filename = os.path.basename(csv_filename)
            self.send_response(200)
            self.send_header("Content-Type", "text/csv; charset=utf-8")
            self.send_header(
                "Content-Disposition",
                f'attachment; filename="{filename}"',
            )
            self.send_header("Content-Length", str(len(contents)))
            self.end_headers()
            self.wfile.write(contents)
            return

        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(HTML_CODE.encode("utf-8"))

    def log_message(self, format, *args):
        return


def run_http_server():
    server = HTTPServer(("127.0.0.1", 8050), SimpleHTTPHandler)
    print("🌐 [Web Server] Aceda ao site em: http://127.0.0.1:8050")
    server.serve_forever()


loop = None


async def main(transport_factory=UDPTransport):
    global loop
    loop = asyncio.get_running_loop()

    threading.Thread(
        target=transport_receiver,
        args=(transport_factory,),
        daemon=True,
    ).start()
    threading.Thread(target=check_cansat_status, daemon=True).start()
    threading.Thread(target=run_http_server, daemon=True).start()

    print("🚀 [WebSocket Server] Ativo na porta 8051...")
    async with websockets.serve(
        ws_handler,
        "127.0.0.1",
        8051,
        ping_interval=20,
        ping_timeout=60,
    ):
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
