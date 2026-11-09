#include <SPI.h>
#include <Wire.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_BME680.h>
#include <Adafruit_SGP30.h>
#include <Adafruit_TSL2561_U.h>
#include <Adafruit_HMC5883_U.h>
#include "HUSKYLENS.h"

// ======================== PINOS ESP32-C6 ========================
#define BME_SCK     18
#define BME_MISO    23      // SDO do BME680
#define BME_MOSI    19      // SDI do BME680
#define BME_CS      15

#define SDA_PIN     6
#define SCL_PIN     7

#define PINO_MIC    0
#define PINO_O2     1
#define PINO_UV     2

// HuskyLens - Serial2
#define HUSKY_RX    17
#define HUSKY_TX    16

// APC220 - Serial1
#define APC_RX      20
#define APC_TX      21
#define APC_SET     22

// ======================== OBJETOS ========================
Adafruit_BME680 bme(BME_CS, BME_MOSI, BME_MISO, BME_SCK);  // SPI software
Adafruit_SGP30 sgp;
Adafruit_TSL2561_Unified tsl = Adafruit_TSL2561_Unified(TSL2561_ADDR_FLOAT, 12345);
Adafruit_HMC5883_Unified mag = Adafruit_HMC5883_Unified(12345);
HUSKYLENS huskylens;

// ======================== TEMPOS ========================
unsigned long tempoAnteriorBME = 0;
unsigned long tempoAnteriorSGP = 0;
unsigned long tempoAnteriorTX  = 0;

const long intervaloBME = 200;   // 5 Hz
const long intervaloSGP = 1000;  // 1 Hz
const long intervaloTX  = 333;   // ~3 Hz

// ======================== VARIÁVEIS ========================
float temp = 0.0, press = 0.0, hum = 0.0, alt = 0.0;
uint16_t eco2 = 400, tvoc = 0;
int valorMic = 0;
float valorO2 = 20.9;
float uvIndex = 0.0;
float lux = 0.0;
float magX = 0.0, magY = 0.0, magZ = 0.0;
int id_ia = 0;

void setup() {
  Serial.begin(115200);
  delay(800);
  Serial.println("\n=================================");
  Serial.println("  ESP32-C6 + APC220 + Sensores");
  Serial.println("=================================\n");

  // Serials
  Serial2.begin(9600, SERIAL_8N1, HUSKY_RX, HUSKY_TX);   // HuskyLens
  Serial1.begin(9600, SERIAL_8N1, APC_RX, APC_TX);       // APC220

  // APC220 em modo normal
  pinMode(APC_SET, OUTPUT);
  digitalWrite(APC_SET, HIGH);

  // ADC 12-bit
  analogReadResolution(12);

  // I2C
  Wire.begin(SDA_PIN, SCL_PIN);

  // ========== BME680 (SPI) ==========
  if (!bme.begin()) {
    Serial.println("ERRO: BME680 nao encontrado!");
  } else {
    Serial.println("BME680 (SPI) OK");
    bme.setTemperatureOversampling(BME680_OS_8X);
    bme.setHumidityOversampling(BME680_OS_2X);
    bme.setPressureOversampling(BME680_OS_4X);
    bme.setIIRFilterSize(BME680_FILTER_SIZE_3);
    bme.setGasHeater(320, 150); // 320°C durante 150 ms
  }

  // ========== SGP30 ==========
  if (!sgp.begin()) {
    Serial.println("AVISO: SGP30 nao encontrado!");
  } else {
    Serial.println("SGP30 OK");
  }

  // ========== TSL2561 ==========
  if (!tsl.begin()) {
    Serial.println("AVISO: TSL2561 nao encontrado!");
  } else {
    tsl.enableAutoRange(true);
    tsl.setIntegrationTime(TSL2561_INTEGRATIONTIME_13MS);
    Serial.println("TSL2561 OK");
  }

  // ========== HMC5883L ==========
  if (!mag.begin()) {
    Serial.println("AVISO: HMC5883L nao encontrado!");
  } else {
    Serial.println("HMC5883L OK");
  }

  // ========== HuskyLens ==========
  while (!huskylens.begin(Serial2)) {
    Serial.println("A aguardar HuskyLens...");
    delay(400);
  }
  Serial.println("HuskyLens OK");

  Serial.println("\nSistema pronto para transmitir!\n");
}

void loop() {
  unsigned long agora = millis();

  // ========== BME680 ==========
  if (agora - tempoAnteriorBME >= intervaloBME) {
    tempoAnteriorBME = agora;
    if (bme.performReading()) {
      temp  = bme.temperature;
      press = bme.pressure / 100.0;
      hum   = bme.humidity;
      alt   = bme.readAltitude(1013.25);
    }
  }

  // ========== SGP30 ==========
  if (agora - tempoAnteriorSGP >= intervaloSGP) {
    tempoAnteriorSGP = agora;
    if (sgp.IAQmeasure()) {
      eco2 = sgp.eCO2;
      tvoc = sgp.TVOC;
    }
  }

  // ========== TRANSMISSÃO ==========
  if (agora - tempoAnteriorTX >= intervaloTX) {
    tempoAnteriorTX = agora;

    // Sensores analógicos
    valorMic = analogRead(PINO_MIC);

    int leituraO2 = analogRead(PINO_O2);
    valorO2 = (leituraO2 / 4095.0) * 25.0;

    int leituraUV = analogRead(PINO_UV);
    float voltageUV = (leituraUV / 4095.0) * 3.3;
    uvIndex = voltageUV / 0.1;

    // TSL2561
    sensors_event_t event;
    tsl.getEvent(&event);
    lux = event.light ? event.light : 0;

    // HMC5883L
    mag.getEvent(&event);
    magX = event.magnetic.x;
    magY = event.magnetic.y;
    magZ = event.magnetic.z;

    // HuskyLens
    id_ia = 0;
    if (huskylens.request() && huskylens.available()) {
      HUSKYLENSResult result = huskylens.read();
      id_ia = result.ID;
    }

    // Payload CSV
    String payload = String(agora) + "," +
                     String(temp, 1) + "," +
                     String(press, 1) + "," +
                     String(hum, 1) + "," +
                     String(alt, 1) + "," +
                     String(eco2) + "," +
                     String(tvoc) + "," +
                     String(valorO2, 1) + "," +
                     String(valorMic) + "," +
                     String(uvIndex, 1) + "," +
                     String(lux, 1) + "," +
                     String(magX, 2) + "," +
                     String(magY, 2) + "," +
                     String(magZ, 2) + "," +
                     String(id_ia);

    // Enviar pelo APC220
    Serial1.println(payload);

    // Debug
    Serial.print("TX → ");
    Serial.println(payload);
  }
}