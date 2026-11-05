
#include <SPI.h>
#include <Adafruit_Sensor.h>
#include "Adafruit_BME680.h"

#define SEALEVELPRESSURE_HPA (1013.25)

// BME680 SPI
#define BME_SCK   18
#define BME_MOSI  19   // SDI
#define BME_MISO  20   // SDO
#define BME_CS    21

// Inicialização do SPI
SPIClass *spi = &SPI;

Adafruit_BME680 bme(BME_CS, spi);

void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println(F("A inicializar o BME680 SPI no ESP32-C6..."));

  // Configurar os pinos SPI
  spi->begin(BME_SCK, BME_MISO, BME_MOSI, BME_CS);

  // Inicializar o sensor
  if (!bme.begin()) {
    Serial.println(F("Não foi possível encontrar o BME680!"));
    Serial.println(F("Verifica as ligações SPI."));
    while (1) delay(1000);
  }

  Serial.println(F("BME680 encontrado com sucesso!"));

  // Configuração dos parâmetros do sensor
  bme.setTemperatureOversampling(BME680_OS_8X);
  bme.setHumidityOversampling(BME680_OS_2X);
  bme.setPressureOversampling(BME680_OS_4X);
  bme.setIIRFilterSize(BME680_FILTER_SIZE_3);
  bme.setGasHeater(320, 150); // 320°C durante 150 ms
}

void loop() {
  if (!bme.performReading()) {
    Serial.println(F("Falha ao ler o sensor :("));
    delay(2000);
    return;
  }

  Serial.println("====================================");

  Serial.print("Temperatura: ");
  Serial.print(bme.temperature);
  Serial.println(" °C");

  Serial.print("Humidade: ");
  Serial.print(bme.humidity);
  Serial.println(" %");

  Serial.print("Pressão: ");
  Serial.print(bme.pressure / 100.0);
  Serial.println(" hPa");

  Serial.print("Resistência do Gás: ");
  Serial.print(bme.gas_resistance / 1000.0);
  Serial.println(" KOhms");

  Serial.print("Altitude Aprox.: ");
  Serial.print(bme.readAltitude(SEALEVELPRESSURE_HPA));
  Serial.println(" m");

  Serial.println("====================================");

  delay(2000);
}