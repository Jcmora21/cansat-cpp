/*
  SGP30 + ESP32-C6
  SDA → GPIO6
  SCL → GPIO7
*/

#include <Wire.h>
#include "Adafruit_SGP30.h"

#define SDA_PIN 6
#define SCL_PIN 7

Adafruit_SGP30 sgp;

void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("=== SGP30 - ESP32-C6 ===");

  Wire.begin(SDA_PIN, SCL_PIN);

  if (!sgp.begin()) {
    Serial.println("ERRO: SGP30 não encontrado!");
    Serial.println("Verifica ligações (3.3V) e endereço 0x58");
    while (1) delay(1000);
  }

  Serial.print("SGP30 encontrado. Serial: #");
  Serial.print(sgp.serialnumber[0], HEX);
  Serial.print(sgp.serialnumber[1], HEX);
  Serial.println(sgp.serialnumber[2], HEX);

  // Inicializa o algoritmo IAQ
  sgp.IAQinit();
}

void loop() {
  if (!sgp.IAQmeasure()) {
    Serial.println("Falha na medição IAQ");
    delay(1000);
    return;
  }

  Serial.print("eCO2: ");
  Serial.print(sgp.eCO2);

  Serial.print(" ppm | TVOC: ");
  Serial.print(sgp.TVOC);

  Serial.println(" ppb");

  delay(1000);
}