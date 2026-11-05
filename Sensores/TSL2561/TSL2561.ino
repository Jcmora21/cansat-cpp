/*
  TSL2561 + ESP32-C6
  SDA → GPIO6
  SCL → GPIO7
*/

#include <Wire.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_TSL2561_U.h>

#define SDA_PIN 6
#define SCL_PIN 7

// Tenta os 3 endereços possíveis
Adafruit_TSL2561_Unified tsl = Adafruit_TSL2561_Unified(TSL2561_ADDR_FLOAT, 12345);
// Alternativas:
//Adafruit_TSL2561_Unified tsl = Adafruit_TSL2561_Unified(TSL2561_ADDR_LOW, 12345);   // 0x29
//Adafruit_TSL2561_Unified tsl = Adafruit_TSL2561_Unified(TSL2561_ADDR_HIGH, 12345);  // 0x49

void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("=== TSL2561 - ESP32-C6 ===");

  Wire.begin(SDA_PIN, SCL_PIN);

  if (!tsl.begin()) {
    Serial.println("ERRO: TSL2561 não encontrado em 0x39");
    Serial.println("Tenta mudar o endereço no código (0x29 ou 0x49)");
    while (1) delay(1000);
  }

  Serial.println("TSL2561 encontrado!");

  // Configuração
  tsl.enableAutoRange(true);                          // Ajuste automático de ganho
  tsl.setIntegrationTime(TSL2561_INTEGRATIONTIME_13MS); // Rápido (13 ms)
  // Outras opções: TSL2561_INTEGRATIONTIME_101MS ou _402MS (mais precisos, mais lentos)

  Serial.println("Sensor configurado.");
}

void loop() {
  sensors_event_t event;
  tsl.getEvent(&event);

  if (event.light) {
    Serial.print("Luminosidade: ");
    Serial.print(event.light);
    Serial.println(" lux");
  } else {
    Serial.println("Sensor saturado ou sem luz (0 lux)");
  }

  delay(1000);
}