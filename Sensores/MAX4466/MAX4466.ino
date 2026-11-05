#define MIC_PIN 0

void setup() {
  Serial.begin(115200);
  analogReadResolution(12);
}

void loop() {
  const int samples = 500;

  double sum = 0;
  double sumSquares = 0;

  for (int i = 0; i < samples; i++) {
    int value = analogRead(MIC_PIN);
    sum += value;
    sumSquares += (double)value * value;
    delayMicroseconds(200);
  }

  double mean = sum / samples;
  double rms = sqrt((sumSquares / samples) - (mean * mean));

  // Valor relativo em dB
  double dB = 20.0 * log10(max(rms, 0.000001));

  Serial.println(dB, 1);

  delay(100);
}