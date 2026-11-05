/*
  Sensor UV Waveshare (GUVA-S12SD) + ESP32-C6
  Arduino IDE

  Ligação:
    VCC  → 3.3V
    GND  → GND
    AOUT → GPIO0
*/

const int UV_PIN = 0;
const float VREF = 3.3;
const int ADC_MAX = 4095;

const float V_ZERO = 0.006;   // Volts = UV Index 0
const float V_MAX  = 0.900;   // Volts = UV Index 10

void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println("=== Sensor UV Waveshare - ESP32-C6 ===");
  analogReadResolution(12);
}

void loop() {
  // Media de 20 leituras
  long soma = 0;
  for (int i = 0; i < 20; i++) {
    soma += analogRead(UV_PIN);
    delay(2);
  }
  int adc_val = soma / 20;

  float v = (adc_val * VREF) / ADC_MAX;

  float uv = 0.0;
  if (v > V_ZERO) {
    uv = ((v - V_ZERO) * 100) / (V_MAX - V_ZERO);
  }
  if (uv < 0.0) uv = 0.0;
  if (uv > 11.0) uv = 11.0;

  Serial.print("ADC: ");
  Serial.print(adc_val);
  Serial.print(" | ");
  Serial.print(v, 3);
  Serial.print(" V | UV: ");
  Serial.println(uv, 1);

  delay(1000);
}