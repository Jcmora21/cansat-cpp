/*
  CanSat sensor integration for ESP32-C6 Dev Module.
  USB serial outputs five AES-GCM encrypted sensor packets per second.
*/

#include <Wire.h>
#include <SPI.h>
#include <Preferences.h>
#include <Adafruit_Sensor.h>
#include "Adafruit_BME680.h"
#include "Adafruit_SGP30.h"
#include <Adafruit_TSL2561_U.h>
#include <Adafruit_HMC5883_U.h>
#include "DFRobot_MultiGasSensor.h"
#include <ArduinoJson.h>
#include <mbedtls/base64.h>
#include <mbedtls/gcm.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

#if __has_include("CanSatSecrets.h")
#include "CanSatSecrets.h"
#else
#error "Copy CanSatSecrets.example.h to CanSatSecrets.h and set a private AES key."
#endif

constexpr uint8_t CANSAT_ID = 1;
constexpr uint8_t SDA_PIN = 6;
constexpr uint8_t SCL_PIN = 7;
constexpr uint8_t UV_PIN = 0;
constexpr uint8_t MIC_PIN = 1;

constexpr uint8_t BME_SCK = 18;
constexpr uint8_t BME_MOSI = 19;
constexpr uint8_t BME_MISO = 20;
constexpr uint8_t BME_CS = 21;

constexpr uint8_t O2_I2C_ADDRESS = 0x74;
constexpr uint32_t BME680_INTERVAL_MS = 200;
constexpr uint32_t SGP30_INTERVAL_MS = 1000;
constexpr uint32_t TELEMETRY_START_DELAY_MS = 10000;
constexpr uint32_t TELEMETRY_INTERVAL_MS = 200;
constexpr uint32_t AUXILIARY_SENSOR_INTERVAL_MS = 200;
constexpr uint16_t MIC_SAMPLE_COUNT = 500;
constexpr uint16_t MIC_SAMPLE_INTERVAL_US = 200;
constexpr size_t AES_KEY_SIZE = 32;
constexpr size_t AES_GCM_NONCE_SIZE = 12;
constexpr size_t AES_GCM_TAG_SIZE = 16;
constexpr size_t MAX_TELEMETRY_JSON_SIZE = 2048;
constexpr size_t MAX_TELEMETRY_BASE64_SIZE =
    ((MAX_TELEMETRY_JSON_SIZE + 2) / 3) * 4 + 1;

// Estados de disponibilidade e temporizadores dos sensores/cadência de envio.
Adafruit_BME680 bme(BME_CS, BME_MOSI, BME_MISO, BME_SCK);
Adafruit_SGP30 sgp;
Adafruit_TSL2561_Unified tsl(TSL2561_ADDR_FLOAT, 12345);
Adafruit_HMC5883_Unified magnetometer(12345);
DFRobot_GAS_I2C oxygenSensor(&Wire, O2_I2C_ADDRESS);

bool bmeAvailable = false;
bool sgpAvailable = false;
bool tslAvailable = false;
bool magnetometerAvailable = false;
bool oxygenAvailable = false;
bool bmeReadingPending = false;
uint32_t sequenceNumber = 0;  // Identifica pacotes e completa lacunas de envio.
uint32_t nextTelemetryTime = 0;
uint32_t previousBmeStartTime = 0;
uint32_t previousSgp30Time = 0;
uint32_t previousAuxiliarySensorTime = 0;
uint32_t bmeReadingReadyAt = 0;
uint32_t nextUvSampleTime = 0;
uint8_t uvSampleCount = 0;
uint32_t uvMillivoltsSum = 0;
uint32_t nextMicSampleTime = 0;
uint16_t micSampleCount = 0;
double micSum = 0.0;
double micSumSquares = 0.0;
uint8_t aesKey[AES_KEY_SIZE];
uint64_t bootCounter = 0;  // Persistido na NVS para não repetir nonces após reinício.
Preferences noncePreferences;
mbedtls_gcm_context aesGcm;
bool encryptionReady = false;
char telemetryJson[MAX_TELEMETRY_JSON_SIZE];
uint8_t encryptedTelemetry[MAX_TELEMETRY_JSON_SIZE];
char encryptedTelemetryBase64[MAX_TELEMETRY_BASE64_SIZE];
char sensorStatusText[128];
StaticJsonDocument<2048> telemetryPacket;
StaticJsonDocument<4096> encryptedEnvelope;

struct TelemetrySample {
  // Últimas leituras válidas; NAN significa que o sensor ainda não forneceu valor.
  float temperature = NAN;
  float humidity = NAN;
  float pressure = NAN;
  float gasResistanceKohm = NAN;
  float eco2 = NAN;
  float tvoc = NAN;
  float lux = NAN;
  float uvMillivolts = NAN;
  float oxygenPercent = NAN;
  uint32_t soundAdcSum = 0;
  uint64_t soundAdcSumSquares = 0;
  uint16_t soundSampleCount = 0;
  float magX = NAN;
  float magY = NAN;
  float magZ = NAN;
};

TelemetrySample latestTelemetrySample;

// Acrescenta uma leitura na sua posição fixa; null mantém o alinhamento se faltar.
void addNullable(JsonArray values, float value) {
  if (isfinite(value)) {
    values.add(value);
  } else {
    values.add(nullptr);
  }
}

// Converte um carácter hexadecimal num nibble; -1 indica carácter inválido.
int hexDigit(char value) {
  if (value >= '0' && value <= '9') return value - '0';
  if (value >= 'a' && value <= 'f') return value - 'a' + 10;
  if (value >= 'A' && value <= 'F') return value - 'A' + 10;
  return -1;
}

// Lê a chave, incrementa o contador persistente de arranques e prepara AES-GCM.
bool initializeEncryption() {
  static_assert(sizeof(CANSAT_AES_KEY_HEX) == AES_KEY_SIZE * 2 + 1,
                "CANSAT_AES_KEY_HEX must contain exactly 64 hex characters.");
  for (size_t index = 0; index < AES_KEY_SIZE; ++index) {
    const int high = hexDigit(CANSAT_AES_KEY_HEX[index * 2]);
    const int low = hexDigit(CANSAT_AES_KEY_HEX[index * 2 + 1]);
    if (high < 0 || low < 0) return false;
    aesKey[index] = static_cast<uint8_t>((high << 4) | low);
  }

  if (!noncePreferences.begin("cansat", false)) return false;
  const uint64_t previousBootCounter =
      noncePreferences.getULong64("boot", 0);
  if (previousBootCounter == UINT64_MAX) {
    noncePreferences.end();
    return false;
  }
  bootCounter = previousBootCounter + 1;
  if (noncePreferences.putULong64("boot", bootCounter) != sizeof(bootCounter)) {
    noncePreferences.end();
    return false;
  }
  noncePreferences.end();

  mbedtls_gcm_init(&aesGcm);
  return mbedtls_gcm_setkey(&aesGcm, MBEDTLS_CIPHER_ID_AES, aesKey,
                            AES_KEY_SIZE * 8) == 0;
}

// Inicializa os barramentos, deteta sensores e prepara as suas configurações.
void initializeSensors() {
  Wire.begin(SDA_PIN, SCL_PIN);
  Wire.setClock(100000);
  Wire.setTimeOut(50);

  SPI.begin(BME_SCK, BME_MISO, BME_MOSI, BME_CS);
  bmeAvailable = bme.begin();
  if (bmeAvailable) {
    bme.setTemperatureOversampling(BME680_OS_8X);
    bme.setHumidityOversampling(BME680_OS_2X);
    bme.setPressureOversampling(BME680_OS_4X);
    bme.setIIRFilterSize(BME680_FILTER_SIZE_3);
    bme.setGasHeater(320, 150);
    if (bme.performReading() && bme.pressure > 0.0f) {
      latestTelemetrySample.pressure = bme.pressure / 100.0f;
      latestTelemetrySample.temperature = bme.temperature;
      latestTelemetrySample.humidity = bme.humidity;
      latestTelemetrySample.gasResistanceKohm = bme.gas_resistance / 1000.0f;
    } else {
      bmeAvailable = false;
    }
  }

  sgpAvailable = sgp.begin();
  if (sgpAvailable) {
    sgp.IAQinit();
  }

  tslAvailable = tsl.begin();
  if (tslAvailable) {
    tsl.enableAutoRange(true);
    tsl.setIntegrationTime(TSL2561_INTEGRATIONTIME_13MS);
  }

  magnetometerAvailable = magnetometer.begin();

  oxygenAvailable = oxygenSensor.begin();
  if (oxygenAvailable) {
    oxygenSensor.setTempCompensation(oxygenSensor.OFF);
    oxygenSensor.changeAcquireMode(oxygenSensor.INITIATIVE);
  }

  analogReadResolution(12);
  analogSetPinAttenuation(UV_PIN, ADC_11db);
  analogSetPinAttenuation(MIC_PIN, ADC_11db);
  snprintf(
      sensorStatusText, sizeof(sensorStatusText),
      "bme680=%s;sgp30=%s;tsl2561=%s;hmc5883l=%s;sen0465=%s;"
      "max4466=configured;uv=configured",
      bmeAvailable ? "ok" : "missing", sgpAvailable ? "ok" : "missing",
      tslAvailable ? "ok" : "missing",
      magnetometerAvailable ? "ok" : "missing",
      oxygenAvailable ? "ok" : "missing");
}

// Faz a leitura BME680 sem bloquear à espera do fim da conversão.
void updateBme680(TelemetrySample &sample, uint32_t now) {
  if (!bmeAvailable) {
    return;
  }

  if (bmeReadingPending &&
      static_cast<int32_t>(now - bmeReadingReadyAt) >= 0) {
    if (bme.endReading() && bme.pressure > 0.0f) {
      sample.temperature = bme.temperature;
      sample.humidity = bme.humidity;
      sample.pressure = bme.pressure / 100.0f;
      sample.gasResistanceKohm = bme.gas_resistance / 1000.0f;
    }
    bmeReadingPending = false;
  }

  if (!bmeReadingPending &&
      now - previousBmeStartTime >= BME680_INTERVAL_MS) {
    bmeReadingReadyAt = bme.beginReading();
    bmeReadingPending = bmeReadingReadyAt != 0;
    previousBmeStartTime = now;
  }
}

// Atualiza eCO2/TVOC a 1 Hz; entre leituras mantém os últimos valores em cache.
void readSgp30(TelemetrySample &sample, uint32_t now) {
  if (!sgpAvailable || now - previousSgp30Time < SGP30_INTERVAL_MS) {
    return;
  }
  previousSgp30Time = now;

  if (sgp.IAQmeasure()) {
    sample.eco2 = sgp.eCO2;
    sample.tvoc = sgp.TVOC;
  }
}

// Lê a iluminância do TSL2561 quando o sensor foi detetado.
void readTsl2561(TelemetrySample &sample) {
  if (!tslAvailable) {
    return;
  }
  sensors_event_t event;
  tsl.getEvent(&event);
  if (isfinite(event.light) && event.light >= 0.0f) {
    sample.lux = event.light;
  }
}

// Lê os três eixos magnéticos; a GS calcula o rumo a partir deles.
void readMagnetometer(TelemetrySample &sample) {
  if (!magnetometerAvailable) {
    return;
  }
  sensors_event_t event;
  magnetometer.getEvent(&event);
  sample.magX = event.magnetic.x;
  sample.magY = event.magnetic.y;
  sample.magZ = event.magnetic.z;
}

// Acumula 20 amostras de tensão UV e publica a média em milivolts.
void updateUv(TelemetrySample &sample, uint32_t now) {
  if (static_cast<int32_t>(now - nextUvSampleTime) < 0) return;
  nextUvSampleTime = now + 2;
  uvMillivoltsSum += analogReadMilliVolts(UV_PIN);
  if (++uvSampleCount < 20) return;

  sample.uvMillivolts =
      uvMillivoltsSum / static_cast<float>(uvSampleCount);
  uvMillivoltsSum = 0;
  uvSampleCount = 0;
}

// Copia a concentração de oxigénio quando o sensor indica dados disponíveis.
void readOxygen(TelemetrySample &sample) {
  if (oxygenAvailable && oxygenSensor.dataIsAvailable()) {
    sample.oxygenPercent = AllDataAnalysis.gasconcentration;
  }
}

// Recolhe 500 amostras ADC e guarda soma/soma dos quadrados para a GS calcular RMS.
void updateMicrophone(TelemetrySample &sample, uint32_t nowMicros) {
  if (static_cast<int32_t>(nowMicros - nextMicSampleTime) < 0) return;
  nextMicSampleTime = nowMicros + MIC_SAMPLE_INTERVAL_US;

  const uint16_t reading = analogRead(MIC_PIN);
  micSum += reading;
  micSumSquares += static_cast<double>(reading) * reading;
  if (++micSampleCount < MIC_SAMPLE_COUNT) return;

  sample.soundAdcSum = static_cast<uint32_t>(micSum);
  sample.soundAdcSumSquares = static_cast<uint64_t>(micSumSquares);
  sample.soundSampleCount = MIC_SAMPLE_COUNT;
  micSum = 0.0;
  micSumSquares = 0.0;
  micSampleCount = 0;
}

// Monta uma lista posicional de telemetria, cifra-a e escreve o envelope pela USB.
void sendTelemetry(const TelemetrySample &sample, uint32_t now) {
  telemetryPacket.clear();
  // Cada transmissão consome uma sequência; slots perdidos também são contados no loop.
  const uint32_t sequence = sequenceNumber++;

  // Ordem fixa: tempo, estado dos sensores, temperatura, humidade, pressão,
  // resistência do gás, eCO2, TVOC, lux, tensão UV, O2, mag X/Y/Z,
  // soma ADC, soma dos quadrados ADC e quantidade de amostras do microfone.
  JsonArray packet = telemetryPacket.to<JsonArray>();
  packet.add(now);
  packet.add(sensorStatusText);
  addNullable(packet, sample.temperature);
  addNullable(packet, sample.humidity);
  addNullable(packet, sample.pressure);
  addNullable(packet, sample.gasResistanceKohm);
  addNullable(packet, sample.eco2);
  addNullable(packet, sample.tvoc);
  addNullable(packet, sample.lux);
  addNullable(packet, sample.uvMillivolts);
  addNullable(packet, sample.oxygenPercent);
  addNullable(packet, sample.magX);
  addNullable(packet, sample.magY);
  addNullable(packet, sample.magZ);
  if (sample.soundSampleCount > 0) {
    packet.add(sample.soundAdcSum);
    packet.add(sample.soundAdcSumSquares);
    packet.add(sample.soundSampleCount);
  } else {
    packet.add(nullptr);
    packet.add(nullptr);
    packet.add(nullptr);
  }

  const size_t expectedJsonLength = measureJson(packet);
  const size_t jsonLength =
      serializeJson(packet, telemetryJson, sizeof(telemetryJson));
  if (expectedJsonLength == 0 ||
      expectedJsonLength >= sizeof(telemetryJson) ||
      jsonLength != expectedJsonLength) {
    Serial.println("{\"type\":\"telemetry_error\",\"error\":\"json_overflow\"}");
    return;
  }

  // Nonce único por chave: contador de arranques persistido + sequência do pacote.
  uint8_t nonce[AES_GCM_NONCE_SIZE];
  for (uint8_t index = 0; index < 8; ++index) {
    nonce[index] = static_cast<uint8_t>(bootCounter >> (56 - index * 8));
  }
  nonce[8] = static_cast<uint8_t>(sequence >> 24);
  nonce[9] = static_cast<uint8_t>(sequence >> 16);
  nonce[10] = static_cast<uint8_t>(sequence >> 8);
  nonce[11] = static_cast<uint8_t>(sequence);

  // AAD não é cifrada, mas fica autenticada para vincular protocolo, versão e CanSat.
  char additionalData[40];
  const int aadLength = snprintf(additionalData, sizeof(additionalData),
                                "CANSAT-TLM-ENC|1|%u",
                                static_cast<unsigned>(CANSAT_ID));
  uint8_t tag[AES_GCM_TAG_SIZE];
  if (aadLength <= 0 ||
      mbedtls_gcm_crypt_and_tag(
          &aesGcm, MBEDTLS_GCM_ENCRYPT, jsonLength, nonce, sizeof(nonce),
          reinterpret_cast<const uint8_t *>(additionalData), aadLength,
          reinterpret_cast<const uint8_t *>(telemetryJson),
          encryptedTelemetry, sizeof(tag), tag) != 0) {
    Serial.println("{\"type\":\"telemetry_error\",\"error\":\"encryption_failed\"}");
    return;
  }

  size_t ciphertextLength = 0;
  if (mbedtls_base64_encode(
          reinterpret_cast<unsigned char *>(encryptedTelemetryBase64),
          sizeof(encryptedTelemetryBase64), &ciphertextLength,
          encryptedTelemetry, jsonLength) != 0) {
    Serial.println("{\"type\":\"telemetry_error\",\"error\":\"encoding_failed\"}");
    return;
  }

  char nonceBase64[17];
  char tagBase64[25];
  size_t nonceLength = 0;
  size_t tagLength = 0;
  if (mbedtls_base64_encode(
          reinterpret_cast<unsigned char *>(nonceBase64), sizeof(nonceBase64),
          &nonceLength, nonce, sizeof(nonce)) != 0 ||
      mbedtls_base64_encode(
          reinterpret_cast<unsigned char *>(tagBase64), sizeof(tagBase64),
          &tagLength, tag, sizeof(tag)) != 0) {
    Serial.println("{\"type\":\"telemetry_error\",\"error\":\"encoding_failed\"}");
    return;
  }

  encryptedEnvelope.clear();
  JsonDocument &envelope = encryptedEnvelope;
  envelope["cansat_id"] = CANSAT_ID;
  envelope["ciphertext"] = encryptedTelemetryBase64;
  envelope["nonce"] = nonceBase64;
  envelope["protocol"] = "CANSAT-TLM-ENC";
  envelope["tag"] = tagBase64;
  envelope["type"] = "encrypted_telemetry";
  envelope["version"] = 1;
  if (encryptedEnvelope.overflowed()) {
    Serial.println("{\"type\":\"telemetry_error\",\"error\":\"envelope_overflow\"}");
    return;
  }
  serializeJson(envelope, Serial);
  Serial.println();
}

// Arranque: configura a serial, valida AES e inicializa sensores e temporizadores.
void setup() {
  Serial.begin(115200);
  if (!initializeEncryption()) {
    Serial.println("{\"type\":\"telemetry_error\",\"error\":\"invalid_aes_key\"}");
    return;
  }
  encryptionReady = true;
  initializeSensors();
  const uint32_t now = millis();
  previousBmeStartTime = now - BME680_INTERVAL_MS;
  previousSgp30Time = now - SGP30_INTERVAL_MS;
  previousAuxiliarySensorTime = now - AUXILIARY_SENSOR_INTERVAL_MS;
  // Dá 10 s para estabilização antes do primeiro pacote; depois mantém slots de 200 ms.
  nextTelemetryTime = now + TELEMETRY_START_DELAY_MS;
  nextUvSampleTime = now;
  nextMicSampleTime = micros();
}

// Ciclo cooperativo: atualiza sensores em cache e transmite após a espera inicial, a cada 200 ms.
void loop() {
  if (!encryptionReady) {
    delay(1000);
    return;
  }

  const uint32_t now = millis();
  updateBme680(latestTelemetrySample, now);
  readSgp30(latestTelemetrySample, now);
  updateUv(latestTelemetrySample, now);
  updateMicrophone(latestTelemetrySample, micros());

  if (now - previousAuxiliarySensorTime >= AUXILIARY_SENSOR_INTERVAL_MS) {
    previousAuxiliarySensorTime = now;
    readTsl2561(latestTelemetrySample);
    readMagnetometer(latestTelemetrySample);
    readOxygen(latestTelemetrySample);
  }

  const uint32_t telemetryNow = millis();
  if (static_cast<int32_t>(telemetryNow - nextTelemetryTime) >= 0) {
    sendTelemetry(latestTelemetrySample, nextTelemetryTime);
    nextTelemetryTime += TELEMETRY_INTERVAL_MS;
    const uint32_t afterSend = millis();
    // Se o processamento atrasou, salta slots e avança o contador sem enviar em rajada.
    while (static_cast<int32_t>(afterSend - nextTelemetryTime) >= 0) {
      ++sequenceNumber;
      nextTelemetryTime += TELEMETRY_INTERVAL_MS;
    }
  }
  delayMicroseconds(20);
}
