/*
  HMC5883L + ESP32-C6
  Várias leituras por segundo
  SDA → GPIO6 | SCL → GPIO7
*/

#include <Wire.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_HMC5883_U.h>

#define SDA_PIN 6
#define SCL_PIN 7

Adafruit_HMC5883_Unified mag = Adafruit_HMC5883_Unified(12345);

void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println("=== HMC5883L - ESP32-C6 ===");

  Wire.begin(SDA_PIN, SCL_PIN);
  Wire.setClock(400000);   // I2C a 400 kHz (mais rápido)

  if (!mag.begin()) {
    Serial.println("ERRO: HMC5883L não encontrado (0x1E)!");
    Serial.println("Pode ser um QMC5883L - diz se for o caso.");
    while (1) delay(1000);
  }

  Serial.println("HMC5883L encontrado!");
  // A biblioteca Adafruit usa por defeito modo contínuo
}

void loop() {
  sensors_event_t event;
  mag.getEvent(&event);

  // Valores em microTesla (uT)
  float x = event.magnetic.x;
  float y = event.magnetic.y;
  float z = event.magnetic.z;

  // Heading (bússola) em graus
  float heading = atan2(y, x) * 180.0 / PI;
  if (heading < 0) heading += 360.0;

  Serial.print("X: ");
  Serial.print(x, 1);
  Serial.print("  Y: ");
  Serial.print(y, 1);
  Serial.print("  Z: ");
  Serial.print(z, 1);
  Serial.print(" uT  |  Heading: ");
  Serial.print(heading, 1);
  Serial.println("°");

  delay(70);   // ~14 leituras por segundo
  // delay(50); → ~20 leituras/s
  // delay(30); → ~30 leituras/s (pode ficar mais ruidoso)
}