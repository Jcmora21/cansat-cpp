import base64
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
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

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
CSV_DELIMITER = ";"
TELEMETRY_INTERVAL_MS = 200
AES_KEY_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "Sensores",
    "CanSat",
    "CanSatSecrets.h",
)
aes_telemetry_key = None
aes_key_checked = False
aes_key_error_logged = False
sea_level_pressure_by_cansat = {}

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
    "uv_millivolts",
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
    "gas_resistance_kohm",
    "oxygen_percent",
    "sound_rms_adc",
    "sound_level_dbfs",
    "sound_adc_sum",
    "sound_adc_sum_squares",
    "sound_sample_count",
    "mag_x",
    "mag_y",
    "mag_z",
    "heading",
    "sea_level_pressure_hpa",
    "sensor_status",
    "rssi",
    "snr",
]


def init_csv(filename):
    """Cria o CSV da sessão, escreve o cabeçalho e devolve ficheiro e writer."""
    output_file = open(filename, mode="w", newline="", encoding="utf-8-sig")
    writer = csv.writer(output_file, delimiter=CSV_DELIMITER)
    writer.writerow(csv_headers)
    output_file.flush()
    return output_file, writer


csv_file, csv_writer = init_csv(csv_filename)
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
    """Rejeita NaN e Infinity, que não fazem parte do padrão JSON."""
    raise ValueError(f"constante JSON nao permitida: {value}")


def is_finite_number(value):
    """Verifica se o valor é um número finito aceite pelo protocolo."""
    return (type(value) is int and value.bit_length() <= 1023) or (
        type(value) is float and math.isfinite(value)
    )


def calculate_crc32(payload):
    """Calcula o CRC32 hexadecimal usado para detetar erros em mensagens simples."""
    return format(zlib.crc32(payload.encode("utf-8")) & 0xFFFFFFFF, "08X")


def protect_control_message(message):
    """Devolve uma cópia da mensagem com CRC32 sobre o JSON canónico."""
    protected = message.copy()
    protected.pop("crc", None)
    checksum_payload = json.dumps(
        protected, separators=(",", ":"), sort_keys=True
    )
    protected["crc"] = calculate_crc32(checksum_payload)
    return protected


def validate_telemetry_packet(packet):
    """Valida estrutura, versão, campos e tipos de um pacote CANSAT-TLM."""
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
        if value is None:
            continue
        if field == "parachute":
            if type(value) is not bool:
                return False, [f"data.{field}"]
        elif not is_finite_number(value):
            return False, [f"data.{field}"]

    optional_numeric_data_fields = (
        "gas_resistance_kohm",
        "oxygen_percent",
        "sound_rms_adc",
        "sound_level_dbfs",
        "mag_x",
        "mag_y",
        "mag_z",
        "heading",
        "sea_level_pressure_hpa",
        "sound_adc_sum",
        "sound_adc_sum_squares",
        "uv_millivolts",
    )
    for field in optional_numeric_data_fields:
        if field in data and data[field] is not None and not is_finite_number(data[field]):
            return False, [f"data.{field}"]
    if "sound_sample_count" in data and data["sound_sample_count"] is not None:
        if (
            type(data["sound_sample_count"]) is not int
            or not 0 <= data["sound_sample_count"] <= 500
        ):
            return False, ["data.sound_sample_count"]
    if "sensor_status" in data and not isinstance(data["sensor_status"], str):
        return False, ["data.sensor_status"]

    for field in REQUIRED_LINK_FIELDS:
        value = link[field]
        if value is not None and not is_finite_number(value):
            return False, [f"link.{field}"]

    return True, []


def verify_packet_crc(packet):
    """Confirma o CRC32 de um pacote simples ou de controlo."""
    crc_received = packet.get("crc")
    if not isinstance(crc_received, str) or not re.fullmatch(r"[0-9A-Fa-f]{1,8}", crc_received):
        return False

    packet_without_crc = packet.copy()
    packet_without_crc.pop("crc", None)
    crc_payload = json.dumps(packet_without_crc, separators=(",", ":"), sort_keys=True)
    return crc_received.upper().zfill(8) == calculate_crc32(crc_payload)


def load_telemetry_aes_key():
    """Lê uma vez a chave AES privada partilhada pelo firmware e pela GS."""
    global aes_telemetry_key, aes_key_checked, aes_key_error_logged
    if aes_key_checked:
        return aes_telemetry_key

    aes_key_checked = True
    try:
        with open(AES_KEY_PATH, encoding="ascii") as key_file:
            contents = key_file.read()
    except (OSError, UnicodeError) as error:
        if not aes_key_error_logged:
            print(
                "[AES-GCM] Chave indisponivel. Cria CanSatSecrets.h "
                f"e reinicia a GS ({error})."
            )
            aes_key_error_logged = True
        return None

    match = re.search(
        r'^\s*#define\s+CANSAT_AES_KEY_HEX\s+"([0-9A-Fa-f]{64})"\s*$',
        contents,
        re.MULTILINE,
    )
    if match is None:
        if not aes_key_error_logged:
            print(
                "[AES-GCM] Chave invalida em CanSatSecrets.h; "
                "esperados exatamente 64 caracteres hexadecimais."
            )
            aes_key_error_logged = True
        return None

    aes_telemetry_key = bytes.fromhex(match.group(1))
    return aes_telemetry_key


def decrypt_encrypted_telemetry(envelope):
    """Autentica e decifra um envelope AES-GCM; devolve o JSON interior válido."""
    global aes_key_error_logged
    if (
        envelope.get("protocol") != "CANSAT-TLM-ENC"
        or envelope.get("version") != 1
        or envelope.get("type") != "encrypted_telemetry"
        or type(envelope.get("cansat_id")) is not int
        or envelope["cansat_id"] < 0
    ):
        return None

    key = load_telemetry_aes_key()
    if key is None:
        return None

    try:
        nonce = base64.b64decode(envelope["nonce"], validate=True)
        ciphertext = base64.b64decode(envelope["ciphertext"], validate=True)
        tag = base64.b64decode(envelope["tag"], validate=True)
        if len(nonce) != 12 or len(tag) != 16:
            raise ValueError("nonce/tag AES-GCM com tamanho invalido")
        additional_data = (
            f"CANSAT-TLM-ENC|1|{envelope['cansat_id']}".encode("ascii")
        )
        plaintext = AESGCM(key).decrypt(
            nonce, ciphertext + tag, additional_data
        )
        packet = json.loads(
            plaintext.decode("utf-8"),
            parse_constant=reject_nonstandard_json_constant,
        )
    except (KeyError, TypeError, ValueError, UnicodeDecodeError,
            json.JSONDecodeError, InvalidTag) as error:
        if not aes_key_error_logged:
            print(
                "[AES-GCM] Pacote descartado: chave incorreta ou dados "
                f"alterados ({error})."
            )
            aes_key_error_logged = True
        return None

    if (
        not isinstance(packet, dict)
        or packet.get("protocol") != "CANSAT-TLM"
        or packet.get("cansat_id") != envelope["cansat_id"]
    ):
        if not aes_key_error_logged:
            print("[AES-GCM] Pacote descartado: conteúdo desencriptado inválido.")
            aes_key_error_logged = True
        return None
    return packet


def set_cansat_sea_level_pressure(message):
    """Guarda P0 para um CanSat e reinicia as derivadas que dependem dela."""
    cansat_id = message.get("cansat_id")
    pressure = message.get("sea_level_pressure_hpa")
    if (
        type(cansat_id) is not int
        or cansat_id < 0
        or not is_finite_number(pressure)
        or not 100.0 <= pressure <= 1200.0
    ):
        return {
            "type": "p0_status",
            "status": "error",
            "reason": "invalid_p0",
            "cansat_id": cansat_id,
        }

    with cansats_lock:
        sea_level_pressure_by_cansat[cansat_id] = float(pressure)
        cansat = get_cansat_state(cansat_id)
        cansat["last_derived_time_ms"] = None
        cansat["last_derived_altitude"] = None
        cansat["last_derived_velocity"] = None
    return {
        "type": "p0_status",
        "status": "applied",
        "cansat_id": cansat_id,
        "sea_level_pressure_hpa": float(pressure),
    }


def update_ground_station_calculations(parsed):
    """Normaliza tempo e calcula na GS UV, altitude, velocidade, rumo e som."""
    cansat_id = parsed.get("cansat_id")
    raw_mission_time = parsed.get("mission_time_ms")
    sequence = parsed.get("sequence")
    if type(cansat_id) is not int or type(raw_mission_time) is not int:
        return

    with cansats_lock:
        cansat = get_cansat_state(cansat_id)
        previous_raw_time = cansat["last_raw_mission_time_ms"]
        previous_sequence = cansat["last_sequence"]
        rebooted = (
            previous_raw_time is not None
            and previous_sequence is not None
            and type(sequence) is int
            and sequence < previous_sequence
            and raw_mission_time < previous_raw_time
        )
        out_of_order = (
            previous_sequence is not None
            and type(sequence) is int
            and sequence <= previous_sequence
            and not rebooted
        )
        if rebooted:
            # Alinha o novo millis() ao último instante conhecido para manter o CSV contínuo.
            previous_normalized_time = (
                cansat["last_normalized_mission_time_ms"]
                if cansat["last_normalized_mission_time_ms"] is not None
                else previous_raw_time
            )
            cansat["mission_time_offset_ms"] = (
                previous_normalized_time + TELEMETRY_INTERVAL_MS
                - raw_mission_time
            )
            cansat["last_sequence"] = None
            cansat["seen_sequences"].clear()
            cansat["seen_sequence_order"].clear()
            cansat["lost_sequences"].clear()
            cansat["lost_sequence_order"].clear()
            cansat["incomplete_sequences"].clear()
            cansat["incomplete_sequence_order"].clear()
            cansat["last_derived_time_ms"] = None
            cansat["last_derived_altitude"] = None
            cansat["last_derived_velocity"] = None
            print(f"[Receiver] CanSat {cansat_id} reiniciou; a retomar sequencia.")

        normalized_time = (
            raw_mission_time + cansat["mission_time_offset_ms"]
        )
        if rebooted or previous_raw_time is None or raw_mission_time >= previous_raw_time:
            cansat["last_raw_mission_time_ms"] = raw_mission_time
            cansat["last_normalized_mission_time_ms"] = normalized_time
        reported_reference = parsed.get("sea_level_pressure_hpa")
        pressure_reference = sea_level_pressure_by_cansat.get(
            cansat_id,
            reported_reference
            if is_finite_number(reported_reference)
            and 100.0 <= reported_reference <= 1200.0
            else 1013.25,
        )

    parsed["mission_time_ms"] = normalized_time
    parsed["tempo"] = f"{normalized_time / 1000.0:.3f}"
    parsed["sea_level_pressure_hpa"] = pressure_reference
    if out_of_order:
        return

    uv_millivolts = parsed.get("uv_millivolts")
    if not is_finite_number(parsed.get("uv")) and is_finite_number(uv_millivolts):
        parsed["uv"] = min(
            10.0,
            max(0.0, (uv_millivolts - 6.0) * 10.0 / (900.0 - 6.0)),
        )

    pressure = parsed.get("pressao")
    if not is_finite_number(parsed.get("altitude")) and (
        is_finite_number(pressure) and pressure > 0
    ):
        # Equação barométrica; P0 é a pressão de referência configurada no painel.
        altitude = 44330.0 * (
            1.0 - (pressure / pressure_reference) ** 0.190294957
        )
        parsed["altitude"] = altitude
        parsed["velocidade"] = None
        parsed["aceleracao"] = None

        with cansats_lock:
            cansat = get_cansat_state(cansat_id)
            previous_time = cansat["last_derived_time_ms"]
            previous_altitude = cansat["last_derived_altitude"]
            previous_velocity = cansat["last_derived_velocity"]
            if previous_time is not None and previous_altitude is not None:
                delta_ms = normalized_time - previous_time
                if 0 < delta_ms <= 2000:
                    # Derivadas usam o intervalo real entre amostras, não a cadência ideal.
                    velocity = (altitude - previous_altitude) / (delta_ms / 1000.0)
                    parsed["velocidade"] = velocity
                    if previous_velocity is not None:
                        parsed["aceleracao"] = (
                            velocity - previous_velocity
                        ) / (delta_ms / 1000.0)
                    cansat["last_derived_velocity"] = velocity
                else:
                    cansat["last_derived_velocity"] = None
            else:
                cansat["last_derived_velocity"] = None
            cansat["last_derived_time_ms"] = normalized_time
            cansat["last_derived_altitude"] = altitude

    magnetic_x = parsed.get("mag_x")
    magnetic_y = parsed.get("mag_y")
    if (
        not is_finite_number(parsed.get("heading"))
        and is_finite_number(magnetic_x)
        and is_finite_number(magnetic_y)
    ):
        parsed["heading"] = math.degrees(math.atan2(magnetic_y, magnetic_x)) % 360.0

    sound_sample_count = parsed.get("sound_sample_count")
    sound_adc_sum = parsed.get("sound_adc_sum")
    sound_adc_sum_squares = parsed.get("sound_adc_sum_squares")
    if (
        type(sound_sample_count) is int
        and sound_sample_count > 0
        and is_finite_number(sound_adc_sum)
        and is_finite_number(sound_adc_sum_squares)
    ):
        # RMS AC é calculado a partir das somas transmitidas pelo firmware.
        sound_mean = sound_adc_sum / sound_sample_count
        sound_variance = (
            sound_adc_sum_squares / sound_sample_count - sound_mean * sound_mean
        )
        parsed["sound_rms_adc"] = math.sqrt(max(0.0, sound_variance))

    sound_rms = parsed.get("sound_rms_adc")
    if (
        not is_finite_number(parsed.get("sound_level_dbfs"))
        and is_finite_number(sound_rms)
        and sound_rms > 0
    ):
        full_scale_sine_rms = 2047.5 / math.sqrt(2.0)
        parsed["sound_level_dbfs"] = 20.0 * math.log10(
            sound_rms / full_scale_sine_rms
        )


def new_cansat_state():
    """Cria o estado inicial, contadores e históricos limitados de um CanSat."""
    return {
        "latest": None,
        "history": [],
        "has_telemetry": False,
        "landed_at": None,
        "last_received": time.time(),
        "status": "ONLINE",
        "last_sequence": None,
        "last_raw_mission_time_ms": None,
        "last_normalized_mission_time_ms": None,
        "mission_time_offset_ms": 0,  # Corrige o tempo quando o ESP32 reinicia.
        "last_derived_time_ms": None,
        "last_derived_altitude": None,
        "last_derived_velocity": None,
        # Sets permitem consultas rápidas; deques limitam a memória usada.
        "seen_sequences": set(),
        "seen_sequence_order": deque(),
        "lost_sequences": set(),
        "lost_sequence_order": deque(),
        "incomplete_sequences": set(),
        "incomplete_sequence_order": deque(),
        # Contadores cumulativos usados pelo painel e pelo diagnóstico da ligação.
        "lost_packets": 0,
        "incomplete_packets": 0,
        "invalid_crc_packets": 0,
        "duplicate_packets": 0,
        "received_packets": 0,
    }


def update_auto_csv_logging(parsed):
    """Encerra a gravação automática 30 s após aterrarem todos os CanSats ativos."""
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
    """Obtém o estado do CanSat, criando-o na primeira telemetria recebida."""
    with cansats_lock:
        if cansat_id not in cansats:
            cansats[cansat_id] = new_cansat_state()
        return cansats[cansat_id]


def classify_sequence(cansat, sequence):
    """Conta pacotes recebidos, duplicados e lacunas da sequência."""
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
        # Uma lacuna é provisória: o pacote em falta pode chegar mais tarde.
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
    """Regista um pacote incompleto e retira a sequência da lista de perdas."""
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
    """Guarda uma sequência sem deixar o histórico crescer além do limite."""
    values = cansat[set_key]
    order = cansat[order_key]
    if sequence in values:
        return
    if len(order) >= MAX_FLIGHT_HISTORY:
        # Descarta da fila e do set a sequência mais antiga.
        values.discard(order.popleft())
    values.add(sequence)
    order.append(sequence)


def forget_bounded_sequence(cansat, set_key, order_key, sequence):
    """Remove uma sequência de ambos os registos limitados."""
    cansat[set_key].discard(sequence)
    order = cansat[order_key]
    if sequence in order:
        order.remove(sequence)


def get_packet_counts(cansat):
    """Devolve os contadores de pacotes para o painel e eventos WebSocket."""
    return {
        "received": cansat["received_packets"],
        "lost": cansat["lost_packets"],
        "duplicate": cansat["duplicate_packets"],
        "incomplete": cansat["incomplete_packets"],
        "crc_invalid": cansat["invalid_crc_packets"],
    }


def receiving_state_event():
    """Devolve o estado de captura e gravação visível no painel."""
    with capture_state_lock:
        return {
            "type": "receiver_state",
            "enabled": capture_enabled,
            "discarded_while_paused": discarded_while_paused,
            "csv_logging_enabled": csv_logging_enabled,
        }


def append_bounded(history, payload, limit=MAX_FLIGHT_HISTORY):
    """Acrescenta um item ao histórico e descarta os mais antigos excedentes."""
    history.append(payload)
    if len(history) > limit:
        del history[:-limit]


class UDPTransport:
    """Transporte UDP para a GS, independente do protocolo de telemetria."""

    def __init__(self, host, port):
        """Abre e associa o socket UDP ao endereço local configurado."""
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind((host, port))

    def receive(self):
        """Espera e devolve um datagrama e o endereço do emissor."""
        return self.socket.recvfrom(4096)

    def send(self, payload, address):
        """Envia texto UTF-8 num datagrama para o endereço indicado."""
        self.socket.sendto(payload.encode("utf-8"), address)


def send_ack(cansat_id, sequence, address):
    """Envia confirmação CRC para pacotes simples que a suportam."""
    if transport is None:
        return
    ack = protect_control_message(
        {"type": "ack", "cansat_id": cansat_id, "sequence": sequence}
    )
    transport.send(json.dumps(ack, separators=(",", ":")), address)


def emit_event(event):
    """Agenda o envio de um evento JSON a todos os clientes WebSocket."""
    if CONNECTED_CLIENTS:
        asyncio.run_coroutine_threadsafe(broadcast(json.dumps(event)), loop)


def handle_command(message):
    """Valida e encaminha um comando para o CanSat associado ao emissor."""
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
    """Recebe, valida, calcula, conta, grava e publica pacotes de telemetria."""
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

        if packet.get("type") == "telemetry_error":
            print(
                f"[CanSat] Erro no firmware: "
                f"{packet.get('error', 'erro desconhecido')}"
            )
            continue

        is_encrypted_packet = packet.get("type") == "encrypted_telemetry"
        if is_encrypted_packet:
            packet = decrypt_encrypted_telemetry(packet)
            if packet is None:
                continue

        if packet.get("type") == "command_ack":
            if verify_packet_crc(packet):
                emit_event({
                    "type": "command_ack",
                    "cansat_id": packet.get("cansat_id"),
                    "command": packet.get("command"),
                    "status": packet.get("status"),
                })
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

            if not is_encrypted_packet and not verify_packet_crc(packet):
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
                "uv_millivolts": data_block.get("uv_millivolts"),
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
                "gas_resistance_kohm": data_block.get("gas_resistance_kohm"),
                "oxygen_percent": data_block.get("oxygen_percent"),
                "sound_rms_adc": data_block.get("sound_rms_adc"),
                "sound_level_dbfs": data_block.get("sound_level_dbfs"),
                "sound_adc_sum": data_block.get("sound_adc_sum"),
                "sound_adc_sum_squares": data_block.get(
                    "sound_adc_sum_squares"
                ),
                "sound_sample_count": data_block.get("sound_sample_count"),
                "mag_x": data_block.get("mag_x"),
                "mag_y": data_block.get("mag_y"),
                "mag_z": data_block.get("mag_z"),
                "heading": data_block.get("heading"),
                "sea_level_pressure_hpa": data_block.get(
                    "sea_level_pressure_hpa"
                ),
                "sensor_status": data_block.get("sensor_status"),
                "rssi": link_block.get("rssi"),
                "snr": link_block.get("snr"),
            }
        else:
            parsed = packet

        if is_protocol_packet:
            update_ground_station_calculations(parsed)

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
                if is_protocol_packet and not is_encrypted_packet:
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
                    csv_writer.writerow(row)
                    csv_file.flush()

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
    """Marca como offline CanSats sem pacotes recentes e publica a alteração."""
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
    """Envia uma mensagem a todos os clientes e remove ligações com erro."""
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
    """Serve um cliente WebSocket, envia o histórico e processa ações do painel."""
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
            elif data.get("type") == "set_p0":
                result = set_cansat_sea_level_pressure(data)
                await websocket.send(json.dumps(result))
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
        """Serve a página da GS ou o CSV completo da sessão."""
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
        """Desativa logs HTTP padrão para evitar ruído no terminal."""
        return


def run_http_server():
    """Inicia o servidor HTTP local que apresenta a página da GS."""
    server = HTTPServer(("127.0.0.1", 8050), SimpleHTTPHandler)
    print("🌐 [Web Server] Aceda ao site em: http://127.0.0.1:8050")
    server.serve_forever()


loop = None


async def main(transport_factory=UDPTransport):
    """Inicia receção, monitorização, HTTP e WebSocket da Ground Station."""
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
