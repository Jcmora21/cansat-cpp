#include <arpa/inet.h>
#include <algorithm>
#include <cerrno>
#include <cctype>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <iomanip>
#include <iostream>
#include <map>
#include <nlohmann/json.hpp>
#include <random>
#include <sstream>
#include <stdexcept>
#include <string>
#include <sys/socket.h>
#include <sys/select.h>
#include <thread>
#include <unistd.h>
#include <utility>
#include <vector>

using json = nlohmann::json;

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

struct PendingPacket {
  std::string payload;
  std::chrono::steady_clock::time_point last_attempt{};
  int retries = 0;
  bool attempted = false;
  bool drop_permanently = false;
};

struct SimulationOptions {
  int ack_timeout_ms = 600;
  int max_retries = 3;
  int drop_every = 0;
  int drop_first_every = 0;
  int duplicate_every = 0;
  int reorder_every = 0;
  bool cansat2_offline_window = false;
};

// ============================================================
// ESTRUTURA DE CADA CANSAT
// ============================================================

struct CanSat {

  // --------------------------------------------------------
  // IDENTIDADE
  // --------------------------------------------------------

  int cansat_id;

  // --------------------------------------------------------
  // CONTADORES DE MISSÃO
  // --------------------------------------------------------

  int sequence = 0;
  double tempo = 0.0;

  // Cada CanSat corre a 5 Hz
  double dt = 0.2;

  // --------------------------------------------------------
  // PARÂMETROS FÍSICOS
  // --------------------------------------------------------

  double massa = 0.350;
  double cd_cansat = 0.45;
  double cd_paraquedas = 1.30;
  double area_cansat = 0.0035;
  double area_paraquedas = 0.12;
  double gravidade = 9.81;

  // --------------------------------------------------------
  // ESTADO DO VOO
  // --------------------------------------------------------

  double altitude = 0.0;
  double velocidade = 0.0;
  double empuxo = 0.0;

  std::string estado = "ESPERA";

  bool paraquedas_aberto = false;

  // --------------------------------------------------------
  // GERADORES DE RUÍDO
  // --------------------------------------------------------

  std::default_random_engine gen;

  std::normal_distribution<double> noise_sensor{0.0, 0.08};
  std::normal_distribution<double> noise_imu{0.0, 0.02};
  std::normal_distribution<double> noise_rssi{-75.0, 3.0};

  std::map<int, PendingPacket> pending_packets;
  int held_sequence = -1;
  int permanently_lost_packets = 0;

  // --------------------------------------------------------
  // CONSTRUTOR
  // --------------------------------------------------------

  CanSat(int id)
      : cansat_id(id),
        gen(static_cast<unsigned>(
                std::chrono::system_clock::now().time_since_epoch().count()) +
            id * 1000) {}
};

// ============================================================
// FUNÇÃO PRINCIPAL
// ============================================================

uint32_t crc32(const std::string &data) {
  uint32_t crc = 0xFFFFFFFF;

  for (unsigned char c : data) {
    crc ^= c;

    for (int i = 0; i < 8; i++) {
      if (crc & 1) {
        crc = (crc >> 1) ^ 0xEDB88320;
      } else {
        crc >>= 1;
      }
    }
  }

  return crc ^ 0xFFFFFFFF;
}

std::string canonical_json(const json &message) {
  return message.dump(-1, ' ', true);
}

std::string format_crc(uint32_t checksum) {
  std::stringstream stream;
  stream << std::uppercase << std::hex << std::setw(8) << std::setfill('0')
         << checksum;
  return stream.str();
}

json protect_message(json message) {
  message.erase("crc");
  message["crc"] = format_crc(crc32(canonical_json(message)));
  return message;
}

bool verify_message_crc(json message) {
  auto crc_field = message.find("crc");
  if (crc_field == message.end() || !crc_field->is_string()) {
    return false;
  }

  const std::string received = crc_field->get<std::string>();
  if (received.empty() || received.size() > 8 ||
      !std::all_of(received.begin(), received.end(), [](unsigned char value) {
        return std::isxdigit(value) != 0;
      })) {
    return false;
  }

  uint32_t received_crc;
  try {
    received_crc = static_cast<uint32_t>(std::stoul(received, nullptr, 16));
  } catch (const std::exception &) {
    return false;
  }

  message.erase("crc");
  return received_crc == crc32(canonical_json(message));
}

int parse_option_value(const std::string &option, const std::string &value,
                       bool allow_zero) {
  size_t parsed_length = 0;
  const int parsed = std::stoi(value, &parsed_length);
  if (parsed_length != value.size() || parsed < (allow_zero ? 0 : 1)) {
    throw std::invalid_argument("valor invalido para " + option);
  }
  return parsed;
}

SimulationOptions parse_options(int argc, char **argv) {
  SimulationOptions options;
  for (int index = 1; index < argc; ++index) {
    const std::string option = argv[index];
    if (option == "--cansat2-offline-window") {
      options.cansat2_offline_window = true;
      continue;
    }
    if (index + 1 >= argc) {
      throw std::invalid_argument("falta valor para " + option);
    }

    const std::string value = argv[++index];
    if (option == "--ack-timeout-ms") {
      options.ack_timeout_ms = parse_option_value(option, value, false);
    } else if (option == "--max-retries") {
      options.max_retries = parse_option_value(option, value, true);
    } else if (option == "--drop-every") {
      options.drop_every = parse_option_value(option, value, false);
    } else if (option == "--drop-first-every") {
      options.drop_first_every = parse_option_value(option, value, false);
    } else if (option == "--duplicate-every") {
      options.duplicate_every = parse_option_value(option, value, false);
    } else if (option == "--reorder-every") {
      options.reorder_every = parse_option_value(option, value, false);
    } else {
      throw std::invalid_argument("opcao desconhecida: " + option);
    }
  }
  return options;
}

bool is_selected_sequence(int interval, int sequence) {
  return interval > 0 && sequence % interval == 0;
}

void send_pending_packet(int sock, const sockaddr_in &destination,
                         CanSat &cansat, int sequence,
                         const SimulationOptions &options,
                         bool first_attempt) {
  PendingPacket &pending = cansat.pending_packets.at(sequence);
  pending.attempted = true;
  pending.last_attempt = std::chrono::steady_clock::now();

  const bool drop_first =
      first_attempt && is_selected_sequence(options.drop_first_every, sequence);
  if (pending.drop_permanently || drop_first) {
    if (first_attempt) {
      std::cout << "[Teste] seq=" << sequence << " CanSat "
                << cansat.cansat_id << " omitida nesta tentativa\n";
    }
    return;
  }

  const std::string &payload = pending.payload;
  sendto(sock, payload.c_str(), payload.size(), 0,
         reinterpret_cast<const sockaddr *>(&destination), sizeof(destination));

  if (first_attempt &&
      is_selected_sequence(options.duplicate_every, sequence)) {
    sendto(sock, payload.c_str(), payload.size(), 0,
           reinterpret_cast<const sockaddr *>(&destination),
           sizeof(destination));
    std::cout << "[Teste] duplicado enviado: CanSat " << cansat.cansat_id
              << " seq=" << sequence << '\n';
  }
}

void process_incoming_messages(int sock, std::vector<CanSat> &cansats) {
  while (true) {
    fd_set read_set;
    FD_ZERO(&read_set);
    FD_SET(sock, &read_set);
    timeval timeout{};
    const int ready = select(sock + 1, &read_set, nullptr, nullptr, &timeout);
    if (ready <= 0) {
      if (ready < 0 && errno == EINTR) {
        continue;
      }
      return;
    }

    char buffer[4096];
    sockaddr_in source{};
    socklen_t source_length = sizeof(source);
    const ssize_t received = recvfrom(
        sock, buffer, sizeof(buffer), 0,
        reinterpret_cast<sockaddr *>(&source), &source_length);
    if (received <= 0) {
      continue;
    }

    json message = json::parse(buffer, buffer + received, nullptr, false);
    if (message.is_discarded() || !message.is_object() ||
        !verify_message_crc(message)) {
      std::cerr << "Mensagem de controlo descartada: CRC/formato invalido\n";
      continue;
    }

    try {
      const std::string type = message.value("type", "");
      if (type == "ack") {
        if (!message.contains("cansat_id") || !message.contains("sequence") ||
            !message["cansat_id"].is_number_integer() ||
            !message["sequence"].is_number_integer()) {
          continue;
        }
        const int cansat_id = message["cansat_id"].get<int>();
        const int sequence = message["sequence"].get<int>();
        for (CanSat &cansat : cansats) {
          if (cansat.cansat_id == cansat_id) {
            if (cansat.pending_packets.erase(sequence) > 0) {
              std::cout << "ACK recebido: CanSat " << cansat_id
                        << " seq=" << sequence << '\n';
            }
            break;
          }
        }
      } else if (type == "command") {
        if (!message.contains("cansat_id") || !message.contains("command") ||
            !message["cansat_id"].is_number_integer() ||
            !message["command"].is_string()) {
          continue;
        }
        const int cansat_id = message["cansat_id"].get<int>();
        const std::string command = message["command"].get<std::string>();
        const bool known_cansat = std::any_of(
            cansats.begin(), cansats.end(), [cansat_id](const CanSat &cansat) {
              return cansat.cansat_id == cansat_id;
            });
        if (!known_cansat) {
          continue;
        }

        json response = protect_message({
            {"type", "command_ack"},
            {"cansat_id", cansat_id},
            {"command", command},
            {"status", "received"},
        });
        const std::string response_payload = response.dump();
        sendto(sock, response_payload.c_str(), response_payload.size(), 0,
               reinterpret_cast<const sockaddr *>(&source), source_length);
        std::cout << "Comando recebido: CanSat " << cansat_id << " -> "
                  << command << '\n';
      }
    } catch (const std::exception &error) {
      std::cerr << "Mensagem de controlo invalida: " << error.what() << '\n';
    }
  }
}

void retry_or_expire_packets(int sock, const sockaddr_in &destination,
                             std::vector<CanSat> &cansats,
                             const SimulationOptions &options) {
  const auto now = std::chrono::steady_clock::now();
  for (CanSat &cansat : cansats) {
    auto pending = cansat.pending_packets.begin();
    while (pending != cansat.pending_packets.end()) {
      PendingPacket &packet = pending->second;
      if (!packet.attempted ||
          now - packet.last_attempt <
              std::chrono::milliseconds(options.ack_timeout_ms)) {
        ++pending;
        continue;
      }

      if (packet.retries < options.max_retries) {
        ++packet.retries;
        const int sequence = pending->first;
        std::cout << "Retransmissao " << packet.retries << "/"
                  << options.max_retries << ": CanSat " << cansat.cansat_id
                  << " seq=" << sequence << '\n';
        send_pending_packet(sock, destination, cansat, sequence, options, false);
        ++pending;
      } else {
        std::cout << "Perda definitiva: CanSat " << cansat.cansat_id
                  << " seq=" << pending->first << '\n';
        ++cansat.permanently_lost_packets;
        pending = cansat.pending_packets.erase(pending);
      }
    }
  }
}

int main(int argc, char **argv) {

  // ========================================================
  // CONFIGURAÇÃO
  // ========================================================

  const int NUM_CANSATS = 5;
  if (argc == 2 && std::string(argv[1]) == "--help") {
    std::cout
        << "Uso: ./simulador [opcoes]\n"
        << "  --ack-timeout-ms N       Timeout de ACK (default: 600)\n"
        << "  --max-retries N          Retransmissoes apos envio inicial (default: 3)\n"
        << "  --drop-every N           Perder definitivamente sequencias multiplas de N\n"
        << "  --drop-first-every N     Omitir primeiro envio; retry pode chegar\n"
        << "  --duplicate-every N      Enviar duplicados para sequencias multiplas de N\n"
        << "  --reorder-every N        Enviar a sequencia seguinte antes das multiplas de N\n"
        << "  --cansat2-offline-window Perder CanSat 2 entre 10s e 20s\n";
    return 0;
  }
  SimulationOptions options;
  try {
    options = parse_options(argc, argv);
  } catch (const std::exception &error) {
    std::cerr << error.what()
              << "\nUso: ./simulador [--ack-timeout-ms N] [--max-retries N] "
                 "[--drop-every N] [--drop-first-every N] "
                 "[--duplicate-every N] [--reorder-every N] "
                 "[--cansat2-offline-window]\n";
    return 1;
  }

  // ========================================================
  // SOCKET UDP
  // ========================================================

  int sock = socket(AF_INET, SOCK_DGRAM, 0);

  if (sock < 0) {
    std::cerr << "Erro ao criar socket UDP\n";
    return 1;
  }

  sockaddr_in localAddr{};
  localAddr.sin_family = AF_INET;
  localAddr.sin_addr.s_addr = htonl(INADDR_ANY);
  localAddr.sin_port = htons(0);
  if (bind(sock, reinterpret_cast<const sockaddr *>(&localAddr),
           sizeof(localAddr)) < 0) {
    std::cerr << "Erro ao associar socket UDP local\n";
    close(sock);
    return 1;
  }

  sockaddr_in destAddr{};

  destAddr.sin_family = AF_INET;
  destAddr.sin_port = htons(5005);

  if (inet_pton(AF_INET, "127.0.0.1", &destAddr.sin_addr) <= 0) {

    std::cerr << "Erro ao configurar endereço UDP\n";
    close(sock);
    return 1;
  }

  // ========================================================
  // CRIAR OS 5 CANSATS
  // ========================================================

  std::vector<CanSat> cansats;

  for (int id = 1; id <= NUM_CANSATS; id++) {
    cansats.emplace_back(id);
  }

  std::cout << "ACK timeout=" << options.ack_timeout_ms
            << "ms, max retries=" << options.max_retries
            << ", drop-every=" << options.drop_every
            << ", drop-first-every=" << options.drop_first_every
            << ", duplicate-every=" << options.duplicate_every
            << ", reorder-every=" << options.reorder_every << '\n';

  // ========================================================
  // LIMPAR ECRÃ
  // ========================================================

  std::cout << "\033[2J\033[1;1H";

  // ========================================================
  // LOOP PRINCIPAL
  // ========================================================

  while (true) {

    process_incoming_messages(sock, cansats);
    retry_or_expire_packets(sock, destAddr, cansats, options);

    // ====================================================
    // PROCESSAR CADA CANSAT
    // ====================================================

    for (auto &cansat : cansats) {

      // ------------------------------------------------
      // SEQUENCE
      // ------------------------------------------------

      cansat.sequence++;

      // ------------------------------------------------
      // TEMPO DE MISSÃO
      // ------------------------------------------------

      cansat.tempo += cansat.dt;

      long long mission_time_ms =
          static_cast<long long>(std::round(cansat.tempo * 1000.0));

      // =================================================
      // MÁQUINA DE ESTADOS
      // =================================================

      if (cansat.tempo <= 10.0) {

        cansat.estado = "ESPERA";

        cansat.altitude = 0.0;
        cansat.velocidade = 0.0;
        cansat.empuxo = 0.0;

        cansat.paraquedas_aberto = false;

      }

      else if (cansat.tempo > 10.0 && cansat.tempo <= 13.5) {

        cansat.estado = "SUBIDA";

        cansat.empuxo = 45.0;

      }

      else if (cansat.tempo > 13.5 && cansat.velocidade > 0.0) {

        cansat.estado = "SUBIDA";

        cansat.empuxo = 0.0;

      }

      else if (cansat.velocidade <= 0.0 && cansat.estado == "SUBIDA") {

        cansat.estado = "APOGEU";

        cansat.empuxo = 0.0;

      }

      else if (cansat.estado == "APOGEU" ||
               (cansat.estado == "SUBIDA" && cansat.velocidade <= -2.0)) {

        cansat.estado = "DESCIDA";

        cansat.paraquedas_aberto = true;

        cansat.empuxo = 0.0;
      }

      // =================================================
      // FÍSICA
      // =================================================

      double area_atual = cansat.paraquedas_aberto ? cansat.area_paraquedas
                                                   : cansat.area_cansat;

      double cd_atual =
          cansat.paraquedas_aberto ? cansat.cd_paraquedas : cansat.cd_cansat;

      double densidade_ar = 1.225 * std::exp(-cansat.altitude / 8500.0);

      double arrasto = 0.5 * densidade_ar * std::pow(cansat.velocidade, 2) *
                       cd_atual * area_atual;

      if (cansat.velocidade > 0)
        arrasto = -arrasto;

      double força_liquida =
          cansat.empuxo - (cansat.massa * cansat.gravidade) + arrasto;

      double aceleracao_real = força_liquida / cansat.massa;

      if (cansat.estado != "ESPERA" && cansat.estado != "SOLO") {

        cansat.velocidade += aceleracao_real * cansat.dt;

        cansat.altitude += cansat.velocidade * cansat.dt;
      }

      // =================================================
      // ATERRAGEM
      // =================================================

      if (cansat.altitude <= 0.1 && cansat.tempo > 15.0) {

        cansat.altitude = 0.0;

        cansat.velocidade = 0.0;

        aceleracao_real = 0.0;

        cansat.estado = "SOLO";
      }

      // =================================================
      // SENSORES
      // =================================================

      double alt_medida =
          std::max(0.0, cansat.altitude + cansat.noise_sensor(cansat.gen));

      double pressao = 1013.25 * std::pow(1.0 - (alt_medida / 44330.0), 5.255);

      double temperatura = 22.0 - (alt_medida * 0.0065) +
                           (cansat.noise_sensor(cansat.gen) * 0.02);

      double humidade =
          std::min(100.0, std::max(15.0, 60.0 - (alt_medida * 0.01) +
                                             cansat.noise_sensor(cansat.gen)));

      double az_imu = (aceleracao_real + cansat.gravidade) / cansat.gravidade;

      double ax_imu = cansat.noise_imu(cansat.gen);

      double ay_imu = cansat.noise_imu(cansat.gen);

      double força_g =
          std::sqrt(ax_imu * ax_imu + ay_imu * ay_imu + az_imu * az_imu);

      double pitch =
          (cansat.estado == "SUBIDA")
              ? 88.0 + cansat.noise_imu(cansat.gen) * 5.0

              : (cansat.paraquedas_aberto ? cansat.noise_imu(cansat.gen) * 10.0
                                          : 0.0);

      double roll = (cansat.estado == "SUBIDA")
                        ? (cansat.tempo * 120.0)
                        : cansat.noise_imu(cansat.gen) * 15.0;

      roll = std::fmod(roll, 360.0);

      double yaw = 45.0 + cansat.noise_imu(cansat.gen) * 5.0;

      double gx = (cansat.estado == "DESCIDA" ? 12.0 : 2.0) *
                  cansat.noise_imu(cansat.gen);

      double gy = (cansat.estado == "DESCIDA" ? 8.0 : 2.0) *
                  cansat.noise_imu(cansat.gen);

      double gz = (cansat.estado == "SUBIDA" ? 120.0 : 3.0) *
                  cansat.noise_imu(cansat.gen);

      double uv_index =
          std::max(0.0, 3.2 + (alt_medida * 0.003) +
                            (cansat.noise_sensor(cansat.gen) * 0.1));

      double lux = std::max(0.0, 42000.0 + (alt_medida * 12.0) +
                                     (cansat.noise_sensor(cansat.gen) * 200));

      double eco2 = std::max(400.0, 412.0 + (alt_medida * 0.015) +
                                        (cansat.noise_sensor(cansat.gen) * 3));

      double tvoc =
          std::max(0.0, 10.0 + (cansat.noise_sensor(cansat.gen) * 1.5));

      double rssi = cansat.noise_rssi(cansat.gen) - (alt_medida * 0.005);

      double snr = 9.5 + cansat.noise_sensor(cansat.gen);

      double packet_loss = (rssi < -100.0) ? 2.5 : 0.0;

      // =================================================
      // PROTOCOLO CANSAT-TLM v1
      // =================================================

      json packet = {

          {"protocol", "CANSAT-TLM"},
          {"version", 1},
          {"type", "telemetry"},

          // ---------------------------------------------
          // IDENTIFICAÇÃO DO CANSAT
          // ---------------------------------------------

          {"cansat_id", cansat.cansat_id},

          // ---------------------------------------------
          // CONTROLO DE PACOTES
          // ---------------------------------------------

          {"sequence", cansat.sequence},

          // ---------------------------------------------
          // TEMPO DA MISSÃO
          // ---------------------------------------------

          {"mission_time_ms", mission_time_ms},

          // ---------------------------------------------
          // ESTADO
          // ---------------------------------------------

          {"state", cansat.estado},

          // ---------------------------------------------
          // DADOS
          // ---------------------------------------------

          {"data",
           {

               {"altitude", std::round(alt_medida * 100.0) / 100.0},

               {"velocity", std::round(cansat.velocidade * 100.0) / 100.0},

               {"acceleration", std::round(aceleracao_real * 100.0) / 100.0},

               {"force_g", std::round(força_g * 100.0) / 100.0},

               {"temperature", std::round(temperatura * 100.0) / 100.0},

               {"humidity", std::round(humidade * 100.0) / 100.0},

               {"pressure", std::round(pressao * 100.0) / 100.0},

               {"eco2", std::round(eco2)},

               {"tvoc", std::round(tvoc)},

               {"uv", std::round(uv_index * 10.0) / 10.0},

               {"lux", std::round(lux)},

               {"acc_x", std::round(ax_imu * 100.0) / 100.0},

               {"acc_y", std::round(ay_imu * 100.0) / 100.0},

               {"acc_z", std::round(az_imu * 100.0) / 100.0},

               {"gyro_x", std::round(gx * 100.0) / 100.0},

               {"gyro_y", std::round(gy * 100.0) / 100.0},

               {"gyro_z", std::round(gz * 100.0) / 100.0},

               {"pitch", std::round(pitch * 10.0) / 10.0},

               {"roll", std::round(roll * 10.0) / 10.0},

               {"yaw", std::round(yaw * 10.0) / 10.0},

               {"parachute", cansat.paraquedas_aberto}}},

          // ---------------------------------------------
          // LINK
          // ---------------------------------------------

          {"link",
           {

               {"rssi", std::round(rssi * 10.0) / 10.0},

               {"snr", std::round(snr * 10.0) / 10.0},

               {"packet_loss", std::round(packet_loss * 10.0) / 10.0}}}};

      // =================================================
      // ENVIO COM ACK E RETRANSMISSAO
      // =================================================

      packet = protect_message(packet);
      PendingPacket pending;
      pending.payload = packet.dump();
      pending.drop_permanently =
          is_selected_sequence(options.drop_every, cansat.sequence) ||
          (options.cansat2_offline_window && cansat.cansat_id == 2 &&
           cansat.tempo >= 10.0 && cansat.tempo < 20.0);
      cansat.pending_packets.emplace(cansat.sequence, std::move(pending));

      const bool hold_for_reorder =
          !cansat.pending_packets.at(cansat.sequence).drop_permanently &&
          is_selected_sequence(options.reorder_every, cansat.sequence) &&
          cansat.held_sequence < 0;

      if (hold_for_reorder) {
        cansat.held_sequence = cansat.sequence;
      } else {
        send_pending_packet(sock, destAddr, cansat, cansat.sequence, options,
                            true);
        if (cansat.held_sequence >= 0) {
          const int held_sequence = cansat.held_sequence;
          send_pending_packet(sock, destAddr, cansat, held_sequence, options,
                              true);
          cansat.held_sequence = -1;
        }
      }
    }
    // ====================================================
    // INTERFACE DO TERMINAL
    // ====================================================

    std::cout << "\033[1;1H";

    std::cout
        << "============================================================\n";

    std::cout << "        🚀 SIMULADOR MULTI-CANSAT - 5 UNIDADES\n";

    std::cout
        << "============================================================\n\n";

    for (const auto &cansat : cansats) {

      std::cout << "CanSat " << cansat.cansat_id << " | " << std::left
                << std::setw(9) << cansat.estado << " | Seq: " << std::setw(6)
                << cansat.sequence << " | Tempo: " << std::fixed
                << std::setprecision(1) << std::setw(6) << cansat.tempo << " s"
                << " | Alt: " << std::setw(6) << std::setprecision(1)
                << cansat.altitude << " m"
                << " | Vel: " << std::setw(7) << cansat.velocidade << " m/s"
                << " | ACK pendentes: " << cansat.pending_packets.size()
                << " | Perdidos: " << cansat.permanently_lost_packets
                << "\n";
    }

    std::cout
        << "\n============================================================\n";

    std::cout << " UDP -> 127.0.0.1:5005"
              << " | 5 CanSats | 5 Hz cada"
              << "\n";

    std::cout
        << "============================================================\n";

    // ====================================================
    // 5 HZ
    // ====================================================

    std::this_thread::sleep_for(std::chrono::milliseconds(200));
  }

  close(sock);

  return 0;
}
