#include <iostream>
#include <string>
#include <thread>
#include <chrono>
#include <cmath>
#include <random>
#include <iomanip>
#include <sys/socket.h>
#include <arpa/inet.h>
#include <unistd.h>
#include <nlohmann/json.hpp>

using json = nlohmann::json;

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

int main() {
    int sock = socket(AF_INET, SOCK_DGRAM, 0);
    if (sock < 0) {
        std::cerr << "Erro ao criar socket UDP\n";
        return 1;
    }

    sockaddr_in destAddr{};
    destAddr.sin_family = AF_INET;
    destAddr.sin_port = htons(5005);
    inet_pton(AF_INET, "127.0.0.1", &destAddr.sin_addr);

    int id_pacote = 0;
    double tempo = 0.0;
    double dt = 0.2; // 5 Hz

    // Parâmetros Físicos Realistas
    double massa = 0.350;        
    double cd_cansat = 0.45;     
    double cd_paraquedas = 1.30; 
    double area_cansat = 0.0035; 
    double area_paraquedas = 0.12; 
    double gravidade = 9.81;

    // Estado do Voo
    double altitude = 0.0;
    double velocidade = 0.0;
    double empuxo = 0.0;
    std::string estado = "ESPERA";
    bool paraquedas_aberto = false;

    // Geradores de ruído
    std::default_random_engine gen;
    std::normal_distribution<double> noise_sensor(0.0, 0.08);
    std::normal_distribution<double> noise_imu(0.0, 0.02);
    std::normal_distribution<double> noise_rssi(-75.0, 3.0);

    // Limpar o ecrã no arranque
    std::cout << "\033[2J\033[1;1H";

    while (true) {
        id_pacote++;
        tempo += dt;

        // --- MÁQUINA DE ESTADOS E FÍSICA ---
        if (tempo <= 10.0) {
            estado = "ESPERA";
            altitude = 0.0;
            velocidade = 0.0;
            empuxo = 0.0;
            paraquedas_aberto = false;
        } else if (tempo > 10.0 && tempo <= 13.5) {
            estado = "SUBIDA";
            empuxo = 45.0; 
        } else if (tempo > 13.5 && velocidade > 0.0) {
            estado = "SUBIDA";
            empuxo = 0.0; 
        } else if (velocidade <= 0.0 && estado == "SUBIDA") {
            estado = "APOGEU";
            empuxo = 0.0;
        } else if (estado == "APOGEU" || (estado == "SUBIDA" && velocidade <= -2.0)) {
            estado = "DESCIDA";
            paraquedas_aberto = true;
            empuxo = 0.0;
        }

        double area_atual = paraquedas_aberto ? area_paraquedas : area_cansat;
        double cd_atual = paraquedas_aberto ? cd_paraquedas : cd_cansat;
        double densidade_ar = 1.225 * std::exp(-altitude / 8500.0);
        double arrasto = 0.5 * densidade_ar * std::pow(velocidade, 2) * cd_atual * area_atual;
        if (velocidade > 0) arrasto = -arrasto;

        double força_liquida = empuxo - (massa * gravidade) + arrasto;
        double aceleracao_real = força_liquida / massa;

        if (estado != "ESPERA" && estado != "SOLO") {
            velocidade += aceleracao_real * dt;
            altitude += velocidade * dt;
        }

        if (altitude <= 0.1 && tempo > 15.0) {
            altitude = 0.0;
            velocidade = 0.0;
            aceleracao_real = 0.0;
            estado = "SOLO";
        }

        // --- SENSORES ---
        double alt_medida = std::max(0.0, altitude + noise_sensor(gen));
        double pressao = 1013.25 * std::pow(1.0 - (alt_medida / 44330.0), 5.255);
        double temperatura = 22.0 - (alt_medida * 0.0065) + (noise_sensor(gen) * 0.02);
        double humidade = std::min(100.0, std::max(15.0, 60.0 - (alt_medida * 0.01) + noise_sensor(gen)));

        double az_imu = (aceleracao_real + gravidade) / gravidade;
        double ax_imu = noise_imu(gen);
        double ay_imu = noise_imu(gen);
        double força_g = std::sqrt(ax_imu * ax_imu + ay_imu * ay_imu + az_imu * az_imu);

        double pitch = (estado == "SUBIDA") ? 88.0 + noise_imu(gen) * 5.0 : (paraquedas_aberto ? noise_imu(gen) * 10.0 : 0.0);
        double roll = (estado == "SUBIDA") ? (tempo * 120.0) : noise_imu(gen) * 15.0;
        roll = std::fmod(roll, 360.0);
        double yaw = 45.0 + noise_imu(gen) * 5.0;

        double gx = (estado == "DESCIDA" ? 12.0 : 2.0) * noise_imu(gen);
        double gy = (estado == "DESCIDA" ? 8.0 : 2.0) * noise_imu(gen);
        double gz = (estado == "SUBIDA" ? 120.0 : 3.0) * noise_imu(gen);

        double uv_index = std::max(0.0, 3.2 + (alt_medida * 0.003) + noise_sensor(gen) * 0.1);
        double lux = std::max(0.0, 42000.0 + (alt_medida * 12.0) + noise_sensor(gen) * 200);
        double eco2 = std::max(400.0, 412.0 + (alt_medida * 0.015) + noise_sensor(gen) * 3);
        double tvoc = std::max(0.0, 10.0 + noise_sensor(gen) * 1.5);

        double rssi = noise_rssi(gen) - (alt_medida * 0.005);
        double snr = 9.5 + noise_sensor(gen);
        double packet_loss = (rssi < -100.0) ? 2.5 : 0.0;

        // PACOTE UDP JSON
        json packet = {
            {"id", id_pacote}, {"tempo", std::round(tempo * 10.0) / 10.0}, {"estado", estado},
            {"altitude", std::round(alt_medida * 100.0) / 100.0}, {"velocidade", std::round(velocidade * 100.0) / 100.0},
            {"aceleracao", std::round(aceleracao_real * 100.0) / 100.0}, {"pressao", std::round(pressao * 100.0) / 100.0},
            {"temperatura", std::round(temperatura * 100.0) / 100.0}, {"humidade", std::round(humidade * 100.0) / 100.0},
            {"eco2", std::round(eco2)}, {"tvoc", std::round(tvoc)},
            {"uv", std::round(uv_index * 10.0) / 10.0}, {"lux", std::round(lux)},
            {"acc_x", std::round(ax_imu * 100.0) / 100.0}, {"acc_y", std::round(ay_imu * 100.0) / 100.0},
            {"acc_z", std::round(az_imu * 100.0) / 100.0}, {"forca_g", std::round(força_g * 100.0) / 100.0},
            {"gyro_x", std::round(gx * 100.0) / 100.0}, {"gyro_y", std::round(gy * 100.0) / 100.0},
            {"gyro_z", std::round(gz * 100.0) / 100.0}, {"pitch", std::round(pitch * 10.0) / 10.0},
            {"roll", std::round(roll * 10.0) / 10.0}, {"yaw", std::round(yaw * 10.0) / 10.0},
            {"rssi", std::round(rssi * 10.0) / 10.0}, {"snr", std::round(snr * 10.0) / 10.0},
            {"packet_loss", std::round(packet_loss * 10.0) / 10.0}, {"paraquedas", paraquedas_aberto}
        };

        std::string msg = packet.dump();
        sendto(sock, msg.c_str(), msg.size(), 0, (struct sockaddr*)&destAddr, sizeof(destAddr));

        // --- IMPRESSÃO FORMATADA ---
        std::cout << "\033[1;1H";
        std::cout << "==================================================================================\n";
        std::cout << " 🚀 TELEMETRIA CANSAT EM TEMPO REAL | Pacote #" << std::setw(5) << id_pacote 
                  << " | Tempo: " << std::fixed << std::setprecision(1) << tempo << "s\n";
        std::cout << "==================================================================================\n";

        std::cout << std::left 
                  << std::setw(28) << "[ SISTEMA & VOO ]" 
                  << std::setw(28) << "[ CLIMA & BARÓMETRO ]" 
                  << std::setw(28) << "[ GASES & RADIAÇÃO ]" << "\n";

        std::cout << std::setw(28) << ("Estado: " + estado) 
                  << std::setw(28) << ("Alt:  " + std::to_string((int)alt_medida) + " m") 
                  << std::setw(28) << ("eCO2: " + std::to_string((int)eco2) + " ppm") << "\n";

        std::cout << std::setw(28) << ("Vel:    " + std::to_string((int)velocidade) + " m/s") 
                  << std::setw(28) << ("Pres: " + std::to_string((int)pressao) + " hPa") 
                  << std::setw(28) << ("TVOC: " + std::to_string((int)tvoc) + " ppb") << "\n";

        std::cout << std::setw(28) << ("Acel:   " + std::to_string((int)aceleracao_real) + " m/s2") 
                  << std::setw(28) << ("Temp: " + std::to_string((int)temperatura) + " C") 
                  << std::setw(28) << ("UV:   " + std::to_string((int)uv_index)) << "\n";

        std::cout << std::setw(28) << ("Paraquedas: " + std::string(paraquedas_aberto ? "ABERTO" : "FECHADO")) 
                  << std::setw(28) << ("Hum:  " + std::to_string((int)humidade) + " %") 
                  << std::setw(28) << ("Lux:  " + std::to_string((int)lux) + " lx") << "\n";

        std::cout << "----------------------------------------------------------------------------------\n";
        std::cout << std::setw(28) << "[ ATITUDE (ORIENTAÇÃO) ]" 
                  << std::setw(28) << "[ ACELERÓMETRO (G) ]" 
                  << std::setw(28) << "[ RÁDIO LORA ]" << "\n";

        std::cout << std::setw(28) << ("Pitch: " + std::to_string((int)pitch) + " deg") 
                  << std::setw(28) << ("AccX: " + std::to_string((int)ax_imu) + " g") 
                  << std::setw(28) << ("RSSI: " + std::to_string((int)rssi) + " dBm") << "\n";

        std::cout << std::setw(28) << ("Roll:  " + std::to_string((int)roll) + " deg") 
                  << std::setw(28) << ("AccY: " + std::to_string((int)ay_imu) + " g") 
                  << std::setw(28) << ("SNR:  " + std::to_string((int)snr) + " dB") << "\n";

        std::cout << std::setw(28) << ("Yaw:   " + std::to_string((int)yaw) + " deg") 
                  << std::setw(28) << ("AccZ: " + std::to_string((int)az_imu) + " g") 
                  << std::setw(28) << ("Loss: " + std::to_string((int)packet_loss) + " %") << "\n";

        std::cout << std::setw(28) << ("G-GyroX: " + std::to_string((int)gx)) 
                  << std::setw(28) << ("Forca-G: " + std::to_string((int)força_g) + " g") 
                  << std::setw(28) << "" << "\n";

        std::cout << "==================================================================================\n";

        std::this_thread::sleep_for(std::chrono::milliseconds(200));
    }

    close(sock);
    return 0;
}
