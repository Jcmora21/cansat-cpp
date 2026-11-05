/*
  CanSat - ESP32-C6
  Sensores: BME680 (SPI) + SGP30 + TSL2561 + HMC5883L + UV
*/

#include <Wire.h>
#include <SPI.h>
#include <Adafruit_Sensor.h>
#include "Adafruit_BME680.h"
#include "Adafruit_SGP30.h"
#include <Adafruit_TSL2561_U.h>
#include <Adafruit_HMC5883_U.h>

// ===== PINOS =====
#define SDA_PIN   6
#define SCL_PIN   7
#define UV_PIN    0

// BME680 SPI
#define BME_SCK   18
#define BME_MOSI  19   // SDI
#define BME_MISO  20   // SDO
#define BME_CS    21

// ===== CONSTANTES UV =====
const float VREF    = 3.3;
const int   ADC_MAX = 4095;
const float V_ZERO  = 0.006;
const float V_MAX   = 0.900;

#define SEALEVELPRESSURE_HPA (1013.25)

// ===== OBJETOS =====
Adafruit_BME680 bme(BME_CS, BME_MOSI, BME_MISO, BME_SCK);  // SPI
Adafruit_SGP30 sgp;
Adafruit_TSL2561_Unified tsl = Adafruit_TSL2561_Unified(TSL2561_ADDR_FLOAT, 12345);
Adafruit_HMC5883_Unified mag = Adafruit_HMC5883_Unified(12345);

// ===== TELEMETRIA =====
struct Telemetria {
  unsigned long tempo;
  float temperatura;
  float humidade;
  float pressao;
  float altitude;
  float gas_kohm;
  uint16_t eco2;
  uint16_t tvoc;
  float lux;
  float uv;
  float heading;
  float mag_x, mag_y, mag_z;
};

Telemetria dados;

void setup() {
  Serial.begin(115200);
  delay(1500);

  // I2C para os outros sensores
  Wire.begin(SDA_PIN, SCL_PIN);
  Wire.setClock(400000);

  // BME680 (SPI)
  if (!bme.begin()) {
    // silencioso
  } else {
    bme.setTemperatureOversampling(BME680_OS_8X);
    bme.setHumidityOversampling(BME680_OS_2X);
    bme.setPressureOversampling(BME680_OS_4X);
    bme.setIIRFilterSize(BME680_FILTER_SIZE_3);
    bme.setGasHeater(320, 150);
  }

  // SGP30
  if (sgp.begin()) {
    sgp.IAQinit();
  }

  // TSL2561
  if (tsl.begin()) {
    tsl.enableAutoRange(true);
    tsl.setIntegrationTime(TSL2561_INTEGRATIONTIME_13MS);
  }

  // HMC5883L
  mag.begin();

  // UV
  analogReadResolution(12);
}

void loop() {
  dados.tempo = millis();

  // BME680
  if (bme.performReading()) {
    dados.temperatura = bme.temperature;
    dados.humidade    = bme.humidity;
    dados.pressao     = bme.pressure / 100.0;
    dados.altitude    = bme.readAltitude(SEALEVELPRESSURE_HPA);
    dados.gas_kohm    = bme.gas_resistance / 1000.0;
  }

  // SGP30
  if (sgp.IAQmeasure()) {
    dados.eco2 = sgp.eCO2;
    dados.tvoc = sgp.TVOC;
  }

  // TSL2561
  sensors_event_t eventLux;
  tsl.getEvent(&eventLux);
  dados.lux = eventLux.light;

  // Magnetómetro
  sensors_event_t eventMag;
  mag.getEvent(&eventMag);
  dados.mag_x = eventMag.magnetic.x;
  dados.mag_y = eventMag.magnetic.y;
  dados.mag_z = eventMag.magnetic.z;

  float heading = atan2(dados.mag_y, dados.mag_x) * 180.0 / PI;
  if (heading < 0) heading += 360.0;
  dados.heading = heading;

  // UV
  long soma = 0;
  for (int i = 0; i < 20; i++) {
    soma += analogRead(UV_PIN);
    delay(1);
  }
  float v = ((soma / 20.0) * VREF) / ADC_MAX;
  float uv = 0.0;
  if (v > V_ZERO) {
    uv = ((v - V_ZERO) * 10.0) / (V_MAX - V_ZERO);
  }
  if (uv < 0) uv = 0;
  if (uv > 11) uv = 11;
  dados.uv = uv;

  // Telemetria CSV (sem cabeçalho)
  Serial.print(dados.tempo);          Serial.print(",");
  Serial.print(dados.temperatura, 2); Serial.print(",");
  Serial.print(dados.humidade, 1);    Serial.print(",");
  Serial.print(dados.pressao, 2);     Serial.print(",");
  Serial.print(dados.altitude, 1);    Serial.print(",");
  Serial.print(dados.gas_kohm, 1);    Serial.print(",");
  Serial.print(dados.eco2);           Serial.print(",");
  Serial.print(dados.tvoc);           Serial.print(",");
  Serial.print(dados.lux, 1);         Serial.print(",");
  Serial.print(dados.uv, 1);          Serial.print(",");
  Serial.print(dados.heading, 1);     Serial.print(",");
  Serial.print(dados.mag_x, 1);       Serial.print(",");
  Serial.print(dados.mag_y, 1);       Serial.print(",");
  Serial.println(dados.mag_z, 1);

  delay(1000);
}