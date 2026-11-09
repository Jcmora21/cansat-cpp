/*
  CanSat sensor integration for ESP32-C6 Dev Module.
  USB serial outputs three CANSAT-TLM v1 JSON packets per second.
*/

#include <Wire.h>
#include <SPI.h>
#include <Adafruit_Sensor.h>
#include "Adafruit_BME680.h"
#include "Adafruit_SGP30.h"
#include <Adafruit_TSL2561_U.h>
#include <Adafruit_HMC5883_U.h>
#include "DFRobot_MultiGasSensor.h"
#include <ArduinoJson.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

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
constexpr uint32_t TELEMETRY_INTERVAL_MS = 333;
constexpr float UV_ZERO_MV = 6.0f;
constexpr float UV_TEN_MV = 900.0f;
constexpr uint16_t MIC_SAMPLE_COUNT = 500;
constexpr uint16_t MIC_SAMPLE_INTERVAL_US = 200;

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
float seaLevelPressureHpa = 1013.25f;
uint32_t sequenceNumber = 0;
uint32_t previousSampleTime = 0;
uint32_t previousBmeStartTime = 0;
uint32_t previousSgp30Time = 0;
uint32_t bmeReadingReadyAt = 0;
uint32_t previousAltitudeTime = 0;
float previousAltitude = 0.0f;
float previousVelocity = 0.0f;
bool previousAltitudeValid = false;
bool previousVelocityValid = false;

struct TelemetrySample {
  float temperature = NAN;
  float humidity = NAN;
  float pressure = NAN;
  float altitude = NAN;
  float velocity = NAN;
  float acceleration = NAN;
  float gasResistanceKohm = NAN;
  float eco2 = NAN;
  float tvoc = NAN;
  float lux = NAN;
  float uvIndex = NAN;
  float oxygenPercent = NAN;
  float soundRmsAdc = NAN;
  float soundLevelDbfs = NAN;
  float magX = NAN;
  float magY = NAN;
  float magZ = NAN;
  float heading = NAN;
};

TelemetrySample latestTelemetrySample;
char serialCommandBuffer[256];
size_t serialCommandLength = 0;

uint32_t crc32(const char *text) {
  uint32_t crc = 0xFFFFFFFFUL;
  while (*text != '\0') {
    crc ^= static_cast<uint8_t>(*text++);
    for (uint8_t bit = 0; bit < 8; ++bit) {
      crc = (crc & 1U) ? (crc >> 1U) ^ 0xEDB88320UL : crc >> 1U;
    }
  }
  return crc ^ 0xFFFFFFFFUL;
}

void setNullable(JsonObject object, const char *key, float value) {
  if (isfinite(value)) {
    object[key] = value;
  } else {
    object[key] = nullptr;
  }
}

float roundToTwoDecimals(float value) {
  return roundf(value * 100.0f) / 100.0f;
}

bool isSafeCommand(const char *command) {
  constexpr char prefix[] = "set_p0:";
  if (strncmp(command, prefix, sizeof(prefix) - 1) != 0) {
    return false;
  }
  if (command[sizeof(prefix) - 1] == '\0') {
    return false;
  }
  for (const char *character = command + sizeof(prefix) - 1;
       *character != '\0'; ++character) {
    if (!((*character >= '0' && *character <= '9') || *character == '.' ||
          *character == '-' || *character == '+')) {
      return false;
    }
  }
  return true;
}

bool verifySerialCommand(JsonDocument &message, int cansatId,
                         const char *command) {
  if (!isSafeCommand(command)) {
    return false;
  }

  char canonical[256];
  const int length = snprintf(canonical, sizeof(canonical),
                              "{\"cansat_id\":%d,\"command\":\"%s\","
                              "\"type\":\"command\"}",
                              cansatId, command);
  if (length <= 0 || static_cast<size_t>(length) >= sizeof(canonical)) {
    return false;
  }

  const char *crcText = message["crc"] | "";
  if (*crcText == '\0' || strlen(crcText) > 8) {
    return false;
  }
  char *end = nullptr;
  const unsigned long receivedCrc = strtoul(crcText, &end, 16);
  return end != crcText && *end == '\0' &&
         receivedCrc == static_cast<unsigned long>(crc32(canonical));
}

void sendCommandAck(int cansatId, const char *command, const char *status) {
  char canonical[320];
  const int length = snprintf(
      canonical, sizeof(canonical),
      "{\"cansat_id\":%d,\"command\":\"%s\",\"status\":\"%s\","
      "\"type\":\"command_ack\"}",
      cansatId, command, status);
  if (length <= 0 || static_cast<size_t>(length) >= sizeof(canonical)) {
    return;
  }

  StaticJsonDocument<384> response;
  response["type"] = "command_ack";
  response["cansat_id"] = cansatId;
  response["command"] = command;
  response["status"] = status;
  char crcText[9];
  snprintf(crcText, sizeof(crcText), "%08lX",
           static_cast<unsigned long>(crc32(canonical)));
  response["crc"] = crcText;
  serializeJson(response, Serial);
  Serial.println();
}

void processSerialCommand(const char *line) {
  StaticJsonDocument<384> message;
  const DeserializationError error = deserializeJson(message, line);
  if (error || message["type"] != "command" ||
      !message["cansat_id"].is<int>() ||
      !message["command"].is<const char *>()) {
    return;
  }

  const int cansatId = message["cansat_id"].as<int>();
  const char *command = message["command"].as<const char *>();
  if (cansatId != CANSAT_ID ||
      !verifySerialCommand(message, cansatId, command)) {
    return;
  }

  constexpr char prefix[] = "set_p0:";
  char *end = nullptr;
  const float requestedPressure =
      strtof(command + sizeof(prefix) - 1, &end);
  if (end == command + sizeof(prefix) - 1 || *end != '\0' ||
      !isfinite(requestedPressure) || requestedPressure < 100.0f ||
      requestedPressure > 1200.0f) {
    sendCommandAck(cansatId, command, "rejected");
    return;
  }

  seaLevelPressureHpa = requestedPressure;
  latestTelemetrySample.altitude =
      isfinite(latestTelemetrySample.pressure)
          ? bme.readAltitude(seaLevelPressureHpa)
          : NAN;
  latestTelemetrySample.velocity = NAN;
  latestTelemetrySample.acceleration = NAN;
  previousAltitudeValid = false;
  previousVelocityValid = false;
  sendCommandAck(cansatId, command, "applied");
}

void readSerialCommands() {
  while (Serial.available() > 0) {
    const char character = static_cast<char>(Serial.read());
    if (character == '\n') {
      serialCommandBuffer[serialCommandLength] = '\0';
      processSerialCommand(serialCommandBuffer);
      serialCommandLength = 0;
    } else if (character != '\r') {
      if (serialCommandLength + 1 < sizeof(serialCommandBuffer)) {
        serialCommandBuffer[serialCommandLength++] = character;
      } else {
        serialCommandLength = 0;
      }
    }
  }
}

void initializeSensors() {
  Wire.begin(SDA_PIN, SCL_PIN);
  Wire.setClock(100000);

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
      latestTelemetrySample.humidity = roundToTwoDecimals(bme.humidity);
      latestTelemetrySample.gasResistanceKohm = bme.gas_resistance / 1000.0f;
      latestTelemetrySample.altitude =
          bme.readAltitude(seaLevelPressureHpa);
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
}

void updateBme680(TelemetrySample &sample, uint32_t now) {
  if (!bmeAvailable) {
    return;
  }

  if (bmeReadingPending &&
      static_cast<int32_t>(now - bmeReadingReadyAt) >= 0) {
    if (bme.endReading() && bme.pressure > 0.0f) {
      sample.temperature = bme.temperature;
      sample.humidity = roundToTwoDecimals(bme.humidity);
      sample.pressure = bme.pressure / 100.0f;
      sample.altitude = bme.readAltitude(seaLevelPressureHpa);
      sample.gasResistanceKohm = bme.gas_resistance / 1000.0f;

      if (previousAltitudeValid) {
        const uint32_t elapsedMs = now - previousAltitudeTime;
        if (elapsedMs > 0) {
          const float elapsedSeconds = elapsedMs / 1000.0f;
          sample.velocity = (sample.altitude - previousAltitude) / elapsedSeconds;
          if (previousVelocityValid) {
            sample.acceleration =
                (sample.velocity - previousVelocity) / elapsedSeconds;
          }
          previousVelocity = sample.velocity;
          previousVelocityValid = true;
        }
      }

      previousAltitude = sample.altitude;
      previousAltitudeTime = now;
      previousAltitudeValid = true;
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

void readMagnetometer(TelemetrySample &sample) {
  if (!magnetometerAvailable) {
    return;
  }
  sensors_event_t event;
  magnetometer.getEvent(&event);
  sample.magX = event.magnetic.x;
  sample.magY = event.magnetic.y;
  sample.magZ = event.magnetic.z;
  float heading = atan2f(sample.magY, sample.magX) * 180.0f / PI;
  if (heading < 0.0f) {
    heading += 360.0f;
  }
  sample.heading = heading;
}

void readUv(TelemetrySample &sample) {
  uint32_t millivoltsSum = 0;
  constexpr uint8_t samples = 20;
  for (uint8_t index = 0; index < samples; ++index) {
    millivoltsSum += analogReadMilliVolts(UV_PIN);
    delay(2);
  }

  const float voltageMv = millivoltsSum / static_cast<float>(samples);
  const float uv = (voltageMv - UV_ZERO_MV) * 10.0f /
                   (UV_TEN_MV - UV_ZERO_MV);
  sample.uvIndex = roundToTwoDecimals(constrain(uv, 0.0f, 10.0f));
}

void readOxygen(TelemetrySample &sample) {
  if (oxygenAvailable && oxygenSensor.dataIsAvailable()) {
    sample.oxygenPercent =
        roundToTwoDecimals(AllDataAnalysis.gasconcentration);
  }
}

void readMicrophone(TelemetrySample &sample) {
  double sum = 0.0;
  double sumSquares = 0.0;
  for (uint16_t index = 0; index < MIC_SAMPLE_COUNT; ++index) {
    const uint16_t reading = analogRead(MIC_PIN);
    sum += reading;
    sumSquares += static_cast<double>(reading) * reading;
    delayMicroseconds(MIC_SAMPLE_INTERVAL_US);
  }

  const double mean = sum / MIC_SAMPLE_COUNT;
  const double variance = sumSquares / MIC_SAMPLE_COUNT - mean * mean;
  sample.soundRmsAdc = sqrtf(static_cast<float>(variance > 0.0 ? variance : 0.0));

  constexpr float FULL_SCALE_SINE_RMS = 2047.5f / 1.41421356f;
  if (sample.soundRmsAdc > 0.0f) {
    sample.soundLevelDbfs =
        20.0f * log10f(sample.soundRmsAdc / FULL_SCALE_SINE_RMS);
  }
}

String sensorStatus() {
  String status;
  status.reserve(64);
  status += "bme680=";
  status += bmeAvailable ? "ok" : "missing";
  status += ";sgp30=";
  status += sgpAvailable ? "ok" : "missing";
  status += ";tsl2561=";
  status += tslAvailable ? "ok" : "missing";
  status += ";hmc5883l=";
  status += magnetometerAvailable ? "ok" : "missing";
  status += ";sen0465=";
  status += oxygenAvailable ? "ok" : "missing";
  status += ";max4466=configured";
  status += ";uv=configured";
  return status;
}

void sendTelemetry(const TelemetrySample &sample, uint32_t now) {
  StaticJsonDocument<2048> packet;
  packet["cansat_id"] = CANSAT_ID;

  JsonObject data = packet.createNestedObject("data");
  setNullable(data, "acc_x", NAN);
  setNullable(data, "acc_y", NAN);
  setNullable(data, "acc_z", NAN);
  setNullable(data, "acceleration", sample.acceleration);
  setNullable(data, "altitude", sample.altitude);
  setNullable(data, "eco2", sample.eco2);
  setNullable(data, "force_g", NAN);
  setNullable(data, "gas_resistance_kohm", sample.gasResistanceKohm);
  setNullable(data, "gyro_x", NAN);
  setNullable(data, "gyro_y", NAN);
  setNullable(data, "gyro_z", NAN);
  setNullable(data, "heading", sample.heading);
  setNullable(data, "humidity", sample.humidity);
  setNullable(data, "lux", sample.lux);
  setNullable(data, "mag_x", sample.magX);
  setNullable(data, "mag_y", sample.magY);
  setNullable(data, "mag_z", sample.magZ);
  setNullable(data, "oxygen_percent", sample.oxygenPercent);
  data["parachute"] = nullptr;
  setNullable(data, "pitch", NAN);
  setNullable(data, "pressure", sample.pressure);
  data["sea_level_pressure_hpa"] = seaLevelPressureHpa;
  setNullable(data, "roll", NAN);
  data["sensor_status"] = sensorStatus();
  setNullable(data, "sound_level_dbfs", sample.soundLevelDbfs);
  setNullable(data, "sound_rms_adc", sample.soundRmsAdc);
  setNullable(data, "temperature", sample.temperature);
  setNullable(data, "tvoc", sample.tvoc);
  setNullable(data, "uv", sample.uvIndex);
  setNullable(data, "velocity", sample.velocity);
  setNullable(data, "yaw", NAN);

  JsonObject link = packet.createNestedObject("link");
  link["packet_loss"] = nullptr;
  link["rssi"] = nullptr;
  link["snr"] = nullptr;

  packet["mission_time_ms"] = now;
  packet["protocol"] = "CANSAT-TLM";
  packet["sequence"] = sequenceNumber++;
  packet["state"] = "SENSOR";
  packet["type"] = "telemetry";
  packet["version"] = 1;

  String canonical;
  serializeJson(packet, canonical);
  char crcText[9];
  snprintf(crcText, sizeof(crcText), "%08lX",
           static_cast<unsigned long>(crc32(canonical.c_str())));
  packet["crc"] = crcText;

  serializeJson(packet, Serial);
  Serial.println();
}

void setup() {
  Serial.begin(115200);
  initializeSensors();
  previousSampleTime = millis() - TELEMETRY_INTERVAL_MS;
  previousBmeStartTime = millis() - BME680_INTERVAL_MS;
  previousSgp30Time = millis() - SGP30_INTERVAL_MS;
}

void loop() {
  readSerialCommands();
  const uint32_t now = millis();
  updateBme680(latestTelemetrySample, now);
  readSgp30(latestTelemetrySample, now);

  if (now - previousSampleTime < TELEMETRY_INTERVAL_MS) {
    delay(1);
    return;
  }
  previousSampleTime = now;

  readTsl2561(latestTelemetrySample);
  readMagnetometer(latestTelemetrySample);
  readUv(latestTelemetrySample);
  readOxygen(latestTelemetrySample);
  readMicrophone(latestTelemetrySample);
  sendTelemetry(latestTelemetrySample, now);
}
