#include <Wire.h>
#include "DFRobot_MultiGasSensor.h"

#define I2C_ADDRESS 0x74

DFRobot_GAS_I2C gas(&Wire, I2C_ADDRESS);

void setup() {
  Serial.begin(115200);

  Wire.begin(6, 7); // SDA, SCL

  while (!gas.begin()) {
    delay(1000);
  }

  gas.setTempCompensation(gas.OFF);
  gas.changeAcquireMode(gas.INITIATIVE);

  delay(1000);
}

void loop() {
  if (gas.dataIsAvailable()) {
    Serial.println(AllDataAnalysis.gasconcentration, 2);
  }

  delay(1000);
}