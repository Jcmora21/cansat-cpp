#include <iostream>
#include <string>
#include <thread>
#include <chrono>
#include <cmath>
#include <random>
#include <iomanip>
#include <vector>
#include <sys/socket.h>
#include <arpa/inet.h>
#include <unistd.h>
#include <nlohmann/json.hpp>

using json = nlohmann::json;

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

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

    // --------------------------------------------------------
    // CONSTRUTOR
    // --------------------------------------------------------

    CanSat(int id)
        : cansat_id(id),
          gen(
              static_cast<unsigned>(
                  std::chrono::system_clock::now()
                      .time_since_epoch()
                      .count()
              ) + id * 1000
          )
    {
    }
};


// ============================================================
// FUNÇÃO PRINCIPAL
// ============================================================

int main() {

    // ========================================================
    // CONFIGURAÇÃO
    // ========================================================

    const int NUM_CANSATS = 5;

    // ========================================================
    // SOCKET UDP
    // ========================================================

    int sock = socket(AF_INET, SOCK_DGRAM, 0);

    if (sock < 0) {
        std::cerr << "Erro ao criar socket UDP\n";
        return 1;
    }

    sockaddr_in destAddr{};

    destAddr.sin_family = AF_INET;
    destAddr.sin_port = htons(5005);

    if (inet_pton(
            AF_INET,
            "127.0.0.1",
            &destAddr.sin_addr
        ) <= 0) {

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

    // ========================================================
    // LIMPAR ECRÃ
    // ========================================================

    std::cout << "\033[2J\033[1;1H";

    // ========================================================
    // LOOP PRINCIPAL
    // ========================================================

    while (true) {

        // ====================================================
        // PROCESSAR CADA CANSAT
        // ====================================================

        for (auto& cansat : cansats) {

            // ------------------------------------------------
            // SEQUENCE
            // ------------------------------------------------

            cansat.sequence++;

            // ------------------------------------------------
            // TEMPO DE MISSÃO
            // ------------------------------------------------

            cansat.tempo += cansat.dt;

            long long mission_time_ms =
                static_cast<long long>(
                    std::round(
                        cansat.tempo * 1000.0
                    )
                );

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

            else if (
                cansat.tempo > 10.0 &&
                cansat.tempo <= 13.5
            ) {

                cansat.estado = "SUBIDA";

                cansat.empuxo = 45.0;

            }

            else if (
                cansat.tempo > 13.5 &&
                cansat.velocidade > 0.0
            ) {

                cansat.estado = "SUBIDA";

                cansat.empuxo = 0.0;

            }

            else if (
                cansat.velocidade <= 0.0 &&
                cansat.estado == "SUBIDA"
            ) {

                cansat.estado = "APOGEU";

                cansat.empuxo = 0.0;

            }

            else if (
                cansat.estado == "APOGEU" ||
                (
                    cansat.estado == "SUBIDA" &&
                    cansat.velocidade <= -2.0
                )
            ) {

                cansat.estado = "DESCIDA";

                cansat.paraquedas_aberto = true;

                cansat.empuxo = 0.0;
            }

            // =================================================
            // FÍSICA
            // =================================================

            double area_atual =
                cansat.paraquedas_aberto
                    ? cansat.area_paraquedas
                    : cansat.area_cansat;

            double cd_atual =
                cansat.paraquedas_aberto
                    ? cansat.cd_paraquedas
                    : cansat.cd_cansat;

            double densidade_ar =
                1.225 *
                std::exp(
                    -cansat.altitude / 8500.0
                );

            double arrasto =
                0.5 *
                densidade_ar *
                std::pow(
                    cansat.velocidade,
                    2
                ) *
                cd_atual *
                area_atual;

            if (cansat.velocidade > 0)
                arrasto = -arrasto;

            double força_liquida =
                cansat.empuxo -
                (
                    cansat.massa *
                    cansat.gravidade
                ) +
                arrasto;

            double aceleracao_real =
                força_liquida /
                cansat.massa;

            if (
                cansat.estado != "ESPERA" &&
                cansat.estado != "SOLO"
            ) {

                cansat.velocidade +=
                    aceleracao_real *
                    cansat.dt;

                cansat.altitude +=
                    cansat.velocidade *
                    cansat.dt;
            }

            // =================================================
            // ATERRAGEM
            // =================================================

            if (
                cansat.altitude <= 0.1 &&
                cansat.tempo > 15.0
            ) {

                cansat.altitude = 0.0;

                cansat.velocidade = 0.0;

                aceleracao_real = 0.0;

                cansat.estado = "SOLO";
            }

            // =================================================
            // SENSORES
            // =================================================

            double alt_medida =
                std::max(
                    0.0,
                    cansat.altitude +
                    cansat.noise_sensor(cansat.gen)
                );

            double pressao =
                1013.25 *
                std::pow(
                    1.0 -
                    (
                        alt_medida /
                        44330.0
                    ),
                    5.255
                );

            double temperatura =
                22.0 -
                (
                    alt_medida *
                    0.0065
                ) +
                (
                    cansat.noise_sensor(
                        cansat.gen
                    ) * 0.02
                );

            double humidade =
                std::min(
                    100.0,
                    std::max(
                        15.0,
                        60.0 -
                        (
                            alt_medida *
                            0.01
                        ) +
                        cansat.noise_sensor(
                            cansat.gen
                        )
                    )
                );

            double az_imu =
                (
                    aceleracao_real +
                    cansat.gravidade
                ) /
                cansat.gravidade;

            double ax_imu =
                cansat.noise_imu(
                    cansat.gen
                );

            double ay_imu =
                cansat.noise_imu(
                    cansat.gen
                );

            double força_g =
                std::sqrt(
                    ax_imu * ax_imu +
                    ay_imu * ay_imu +
                    az_imu * az_imu
                );

            double pitch =
                (
                    cansat.estado == "SUBIDA"
                )
                ? 88.0 +
                  cansat.noise_imu(
                      cansat.gen
                  ) * 5.0

                : (
                    cansat.paraquedas_aberto
                    ? cansat.noise_imu(
                          cansat.gen
                      ) * 10.0
                    : 0.0
                );

            double roll =
                (
                    cansat.estado == "SUBIDA"
                )
                ? (
                    cansat.tempo *
                    120.0
                )
                : cansat.noise_imu(
                      cansat.gen
                  ) * 15.0;

            roll =
                std::fmod(
                    roll,
                    360.0
                );

            double yaw =
                45.0 +
                cansat.noise_imu(
                    cansat.gen
                ) * 5.0;

            double gx =
                (
                    cansat.estado == "DESCIDA"
                    ? 12.0
                    : 2.0
                ) *
                cansat.noise_imu(
                    cansat.gen
                );

            double gy =
                (
                    cansat.estado == "DESCIDA"
                    ? 8.0
                    : 2.0
                ) *
                cansat.noise_imu(
                    cansat.gen
                );

            double gz =
                (
                    cansat.estado == "SUBIDA"
                    ? 120.0
                    : 3.0
                ) *
                cansat.noise_imu(
                    cansat.gen
                );

            double uv_index =
                std::max(
                    0.0,
                    3.2 +
                    (
                        alt_medida *
                        0.003
                    ) +
                    (
                        cansat.noise_sensor(
                            cansat.gen
                        ) * 0.1
                    )
                );

            double lux =
                std::max(
                    0.0,
                    42000.0 +
                    (
                        alt_medida *
                        12.0
                    ) +
                    (
                        cansat.noise_sensor(
                            cansat.gen
                        ) * 200
                    )
                );

            double eco2 =
                std::max(
                    400.0,
                    412.0 +
                    (
                        alt_medida *
                        0.015
                    ) +
                    (
                        cansat.noise_sensor(
                            cansat.gen
                        ) * 3
                    )
                );

            double tvoc =
                std::max(
                    0.0,
                    10.0 +
                    (
                        cansat.noise_sensor(
                            cansat.gen
                        ) * 1.5
                    )
                );

            double rssi =
                cansat.noise_rssi(
                    cansat.gen
                ) -
                (
                    alt_medida *
                    0.005
                );

            double snr =
                9.5 +
                cansat.noise_sensor(
                    cansat.gen
                );

            double packet_loss =
                (
                    rssi < -100.0
                )
                ? 2.5
                : 0.0;

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

                {
                    "cansat_id",
                    cansat.cansat_id
                },

                // ---------------------------------------------
                // CONTROLO DE PACOTES
                // ---------------------------------------------

                {
                    "sequence",
                    cansat.sequence
                },

                // ---------------------------------------------
                // TEMPO DA MISSÃO
                // ---------------------------------------------

                {
                    "mission_time_ms",
                    mission_time_ms
                },

                // ---------------------------------------------
                // ESTADO
                // ---------------------------------------------

                {
                    "state",
                    cansat.estado
                },

                // ---------------------------------------------
                // DADOS
                // ---------------------------------------------

                {
                    "data",
                    {

                        {
                            "altitude",
                            std::round(
                                alt_medida * 100.0
                            ) / 100.0
                        },

                        {
                            "velocity",
                            std::round(
                                cansat.velocidade * 100.0
                            ) / 100.0
                        },

                        {
                            "acceleration",
                            std::round(
                                aceleracao_real * 100.0
                            ) / 100.0
                        },

                        {
                            "force_g",
                            std::round(
                                força_g * 100.0
                            ) / 100.0
                        },

                        {
                            "temperature",
                            std::round(
                                temperatura * 100.0
                            ) / 100.0
                        },

                        {
                            "humidity",
                            std::round(
                                humidade * 100.0
                            ) / 100.0
                        },

                        {
                            "pressure",
                            std::round(
                                pressao * 100.0
                            ) / 100.0
                        },

                        {
                            "eco2",
                            std::round(eco2)
                        },

                        {
                            "tvoc",
                            std::round(tvoc)
                        },

                        {
                            "uv",
                            std::round(
                                uv_index * 10.0
                            ) / 10.0
                        },

                        {
                            "lux",
                            std::round(lux)
                        },

                        {
                            "acc_x",
                            std::round(
                                ax_imu * 100.0
                            ) / 100.0
                        },

                        {
                            "acc_y",
                            std::round(
                                ay_imu * 100.0
                            ) / 100.0
                        },

                        {
                            "acc_z",
                            std::round(
                                az_imu * 100.0
                            ) / 100.0
                        },

                        {
                            "gyro_x",
                            std::round(
                                gx * 100.0
                            ) / 100.0
                        },

                        {
                            "gyro_y",
                            std::round(
                                gy * 100.0
                            ) / 100.0
                        },

                        {
                            "gyro_z",
                            std::round(
                                gz * 100.0
                            ) / 100.0
                        },

                        {
                            "pitch",
                            std::round(
                                pitch * 10.0
                            ) / 10.0
                        },

                        {
                            "roll",
                            std::round(
                                roll * 10.0
                            ) / 10.0
                        },

                        {
                            "yaw",
                            std::round(
                                yaw * 10.0
                            ) / 10.0
                        },

                        {
                            "parachute",
                            cansat.paraquedas_aberto
                        }
                    }
                },

                // ---------------------------------------------
                // LINK
                // ---------------------------------------------

                {
                    "link",
                    {

                        {
                            "rssi",
                            std::round(
                                rssi * 10.0
                            ) / 10.0
                        },

                        {
                            "snr",
                            std::round(
                                snr * 10.0
                            ) / 10.0
                        },

                        {
                            "packet_loss",
                            std::round(
                                packet_loss * 10.0
                            ) / 10.0
                        }
                    }
                }
            };

            // =================================================
            // ENVIO UDP
            // =================================================

            std::string msg =
                packet.dump();

            sendto(
                sock,
                msg.c_str(),
                msg.size(),
                0,
                (struct sockaddr*)&destAddr,
                sizeof(destAddr)
            );
        }

        // ====================================================
        // INTERFACE DO TERMINAL
        // ====================================================

        std::cout << "\033[1;1H";

        std::cout
            << "============================================================\n";

        std::cout
            << "        🚀 SIMULADOR MULTI-CANSAT - 5 UNIDADES\n";

        std::cout
            << "============================================================\n\n";

        for (const auto& cansat : cansats) {

            std::cout
                << "CanSat "
                << cansat.cansat_id
                << " | "
                << std::left
                << std::setw(9)
                << cansat.estado
                << " | Seq: "
                << std::setw(6)
                << cansat.sequence
                << " | Tempo: "
                << std::fixed
                << std::setprecision(1)
                << std::setw(6)
                << cansat.tempo
                << " s"
                << " | Alt: "
                << std::setw(6)
                << std::setprecision(1)
                << cansat.altitude
                << " m"
                << " | Vel: "
                << std::setw(7)
                << cansat.velocidade
                << " m/s"
                << "\n";
        }

        std::cout
            << "\n============================================================\n";

        std::cout
            << " UDP -> 127.0.0.1:5005"
            << " | 5 CanSats | 5 Hz cada"
            << "\n";

        std::cout
            << "============================================================\n";

        // ====================================================
        // 5 HZ
        // ====================================================

        std::this_thread::sleep_for(
            std::chrono::milliseconds(200)
        );
    }

    close(sock);

    return 0;
}
