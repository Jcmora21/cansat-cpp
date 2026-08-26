#include <iostream>
#include <fstream>
#include <string>
#include <thread>
#include <chrono>
#include <iomanip>
#include <sys/socket.h>
#include <arpa/inet.h>
#include <unistd.h>
#include <nlohmann/json.hpp>

using json = nlohmann::json;

int main() {
    int sock = socket(AF_INET, SOCK_DGRAM, 0);
    if (sock < 0) {
        std::cerr << "Erro ao criar socket UDP\n";
        return 1;
    }

    sockaddr_in serverAddr{}, clientAddr{};
    serverAddr.sin_family = AF_INET;
    serverAddr.sin_port = htons(5005);
    serverAddr.sin_addr.s_addr = INADDR_ANY;

    if (bind(sock, (struct sockaddr*)&serverAddr, sizeof(serverAddr)) < 0) {
        std::cerr << "Erro ao fazer bind na porta 5005\n";
        close(sock);
        return 1;
    }

    // Ficheiro CSV de Log
    std::ofstream csvFile("telemetria_log.csv", std::ios::app);
    if (csvFile.tellp() == 0) {
        csvFile << "id,tempo,estado,altitude,velocidade,aceleracao,pressao,temperatura,humidade,"
                << "eco2,tvoc,uv,lux,acc_x,acc_y,acc_z,forca_g,gyro_x,gyro_y,gyro_z,"
                << "pitch,roll,yaw,rssi,snr,packet_loss,paraquedas\n";
    }

    std::cout << "📡 Ground Station C++ ativa (Escutando na porta 5005)...\n\n";

    char buffer[2048];
    socklen_t addrLen = sizeof(clientAddr);

    while (true) {
        ssize_t bytesReceived = recvfrom(sock, buffer, sizeof(buffer) - 1, 0, 
                                         (struct sockaddr*)&clientAddr, &addrLen);
        if (bytesReceived < 0) continue;

        buffer[bytesReceived] = '\0';

        try {
            json packet = json::parse(buffer);

            // Registo no ficheiro CSV
            csvFile << packet["id"] << "," << packet["tempo"] << "," << packet["estado"].get<std::string>() << ","
                    << packet["altitude"] << "," << packet["velocidade"] << "," << packet["aceleracao"] << ","
                    << packet["pressao"] << "," << packet["temperatura"] << "," << packet["humidade"] << ","
                    << packet["eco2"] << "," << packet["tvoc"] << "," << packet["uv"] << "," << packet["lux"] << ","
                    << packet["acc_x"] << "," << packet["acc_y"] << "," << packet["acc_z"] << "," << packet["forca_g"] << ","
                    << packet["gyro_x"] << "," << packet["gyro_y"] << "," << packet["gyro_z"] << ","
                    << packet["pitch"] << "," << packet["roll"] << "," << packet["yaw"] << ","
                    << packet["rssi"] << "," << packet["snr"] << "," << packet["packet_loss"] << ","
                    << (packet["paraquedas"].get<bool>() ? 1 : 0) << "\n";
            csvFile.flush();

            // Apresentação na consola da Ground Station
            std::cout << "\r[RECETOR] Pacote #" << packet["id"] 
                      << " | Tempo: " << packet["tempo"] << "s"
                      << " | Estado: " << packet["estado"].get<std::string>()
                      << " | Alt: " << packet["altitude"] << "m"
                      << " | Temp: " << packet["temperatura"] << "°C"
                      << " | eCO2: " << packet["eco2"] << "ppm" << std::flush;

        } catch (const std::exception& e) {
            std::cerr << "\nErro no parse do pacote: " << e.what() << "\n";
        }
    }

    close(sock);
    csvFile.close();
    return 0;
}
