#include "Wire.h"
#include "Adafruit_Sensor.h"
#include "Adafruit_BME680.h"
#include "Adafruit_SGP30.h"
#include "Adafruit_TSL2561_U.h"
#include "Adafruit_HMC5883_U.h"
#include "HUSKYLENS.h"

// ===================== PINOS ESP32-C6 =====================
#define SDA_PIN           6
#define SCL_PIN           7

#define PINO_MIC          0     // ADC
#define PINO_O2           1     // ADC
#define PINO_UV           2     // ADC

// HuskyLens - Serial2
#define HUSKY_RX          17    // ESP RX  ← Husky TX
#define HUSKY_TX          16    // ESP TX  → Husky RX

// APC220 - Serial1
#define APC_RX            20    // ESP RX  ← APC TXD
#define APC_TX            21    // ESP TX  → APC RXD
#define APC_SET           22    // HIGH = normal, LOW = config

// ===================== OBJETOS =====================
Adafruit_BME680 bme;
Adafruit_SGP30 sgp;
Adafruit_TSL2561_Unified tsl = Adafruit_TSL2561_Unified(TSL2561_ADDR_FLOAT, 12345);
Adafruit_HMC5883_Unified mag = Adafruit_HMC5883_Unified(12345);
HUSKYLENS huskylens;

// ===================== TEMPOS =====================
unsigned long tempoAnteriorBME  = 0;
unsigned long tempoAnteriorSGP  = 0;
unsigned long tempoAnteriorTX   = 0;

const long intervaloBME = 200;    // 5 Hz
const long intervaloSGP = 1000;   // 1 Hz
const long intervaloTX  = 333;    // ~3 Hz

// ===================== VARIÁVEIS =====================
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
  delay(500);
  Serial.println("\n=== ESP32-C6 + APC220 + Sensores ===");

  // Serial da HuskyLens
  Serial2.begin(9600, SERIAL_8N1, HUSKY_RX, HUSKY_TX);

  // Serial do APC220
  Serial1.begin(9600, SERIAL_8N1, APC_RX, APC_TX);

  // Pino SET do APC220 em modo normal
  pinMode(APC_SET, OUTPUT);
  digitalWrite(APC_SET, HIGH);   // HIGH = funcionamento normal

  // ADC 12-bit
  analogReadResolution(12);

  // I2C
  Wire.begin(SDA_PIN, SCL_PIN);

  // --- Inicialização dos sensores ---
  if (!bme.begin()) {
    Serial.println("AVISO: BME680 nao encontrado!");
  } else {
    Serial.println("BME680 OK");
  }

  if (!sgp.begin()) {
    Serial.println("AVISO: SGP30 nao encontrado!");
  } else {
    Serial.println("SGP30 OK");
  }

  if (!tsl.begin()) {
    Serial.println("AVISO: TSL2561 nao encontrado!");
  } else {
    tsl.enableAutoRange(true);
    tsl.setIntegrationTime(TSL2561_INTEGRATIONTIME_13MS);
    Serial.println("TSL2561 OK");
  }

  if (!mag.begin()) {
    Serial.println("AVISO: HMC5883L nao encontrado!");
  } else {
    Serial.println("HMC5883L OK");
  }

  // HuskyLens
  while (!huskylens.begin(Serial2)) {
    Serial.println("A aguardar HuskyLens...");
    delay(500);
  }
  Serial.println("HuskyLens OK");

  Serial.println("Sistema pronto!\n");
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

    // --- Sensores analógicos ---
    valorMic = analogRead(PINO_MIC);
    
    int leituraO2 = analogRead(PINO_O2);
    valorO2 = (leituraO2 / 4095.0) * 25.0;

    int leituraUV = analogRead(PINO_UV);
    float voltageUV = (leituraUV / 4095.0) * 3.3;
    uvIndex = voltageUV / 0.1;          // aproximação comum

    // --- TSL2561 ---
    sensors_event_t event;
    tsl.getEvent(&event);
    lux = event.light ? event.light : 0;

    // --- HMC5883L ---
    mag.getEvent(&event);
    magX = event.magnetic.x;
    magY = event.magnetic.y;
    magZ = event.magnetic.z;

    // --- HuskyLens ---
    id_ia = 0;
    if (huskylens.request() && huskylens.available()) {
      HUSKYLENSResult result = huskylens.read();
      id_ia = result.ID;
    }

    // --- Payload CSV ---
    // tempo,temp,press,hum,alt,eco2,tvoc,O2,mic,UV,lux,magX,magY,magZ,id_ia
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

    // Debug no Serial USB
    Serial.print("TX → ");
    Serial.println(payload);
  }
}