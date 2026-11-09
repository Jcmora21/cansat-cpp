# Firmware integrado dos sensores

`CanSat.ino` foi preparado para a placa **ESP32-C6 Dev Module** e envia até
cinco linhas JSON CANSAT-TLM v1 por segundo pela porta USB serial a 115200
baud. A cadência pretendida é uma linha a cada 200 ms. O BME680 é lido de
forma assíncrona para não bloquear o ciclo; o SGP30 atualiza eCO₂/TVOC a 1 Hz,
mantendo o último valor nas linhas entre atualizações. A linha pode ser
recebida pela variante serial da GS. Nesta fase a câmara
HuskyLens fica intencionalmente adiada, e a ligação APC220 fica por definir.

## Bibliotecas Arduino

Instala pelo Arduino IDE > Library Manager:

- Adafruit BME680 Library
- Adafruit Unified Sensor
- Adafruit SGP30 Sensor
- Adafruit TSL2561
- Adafruit HMC5883 Unified
- Adafruit BusIO (dependência das bibliotecas Adafruit)
- ArduinoJson

O sensor Gravity SEN0465 usa `DFRobot_MultiGasSensor`. A biblioteca está no
ZIP `../Gravity O₂ SEN0465/DFRobot_MultiGasSensor-main.zip`; extrai a pasta da
biblioteca para a pasta `libraries` do Arduino IDE ou instala a biblioteca
DFRobot correspondente.

`Wire`, `SPI` e as funções ADC são fornecidas pelo core ESP32 Arduino.

## Mapa de ligações usado pelo sketch

| Sensor | Interface | Pinos/endereços |
|---|---|---|
| BME680 | SPI | SCK GPIO18, MOSI GPIO19, MISO GPIO20, CS GPIO21 |
| SGP30 | I2C | SDA GPIO6, SCL GPIO7, endereço 0x58 |
| TSL2561 | I2C | SDA GPIO6, SCL GPIO7, endereço esperado 0x39 |
| HMC5883L | I2C | SDA GPIO6, SCL GPIO7, endereço 0x1E |
| Gravity SEN0465 O2 | I2C | SDA GPIO6, SCL GPIO7, endereço 0x74 |
| GUVA-S12SD UV | Analógico | AOUT GPIO0 |
| MAX4466 | Analógico | OUT GPIO1 |

O GPIO1 foi escolhido para o MAX4466 para resolver a colisão com o UV no
GPIO0. Confirma esta ligação na placa antes de alimentar o circuito. Os
sensores I2C partilham o mesmo barramento configurado a 100 kHz.

## Dados e limitações nesta fase

- `altitude` é relativa à pressão medida no arranque; `velocity` e
  `acceleration` são derivadas de amostras de altitude barométrica. A
  telemetria é transmitida até 5 Hz; alguns sensores atualizam a uma frequência
  inferior e o pacote repete o último valor disponível.
- `oxygen_percent` representa a concentração reportada pelo SEN0465 em
  percentagem de volume; humidade e oxigénio são transmitidos arredondados a
  duas casas decimais. `gas_resistance_kohm` é a resistência do sensor de gás
  do BME680; não é uma medição de O2.
- O índice UV usa provisoriamente os pontos indicados no sketch do CanSat:
  6 mV = índice 0 e 900 mV = índice 10; o valor enviado é limitado à escala
  0–10 e arredondado a duas casas decimais. É uma estimativa, a validar contra
  uma referência UV; os sketches anteriores tinham fórmulas discordantes.
- `sound_level_dbfs` é relativo à escala ADC e não é dB SPL calibrado.
- O HMC5883L produz magnetómetro/rumo magnético; não substitui um IMU. Os
  campos de acelerómetro/giroscópio, atitude e paraquedas ficam `null` até
  existir hardware para os medir.
- `rssi`, `snr` e `packet_loss` ficam `null` enquanto o rádio não fornecer
  essas medições. Os sensores não encontrados são indicados como `missing`
  em `sensor_status`; as suas medições ficam `null`, nunca são substituídas
  por zeros.
- O estado de voo é enviado como `SENSOR`; esta versão não implementa uma
  máquina de estados de voo.

## Teste USB serial com a GS

1. Liga a placa por USB e fecha o Serial Monitor do Arduino IDE.
2. Descobre a porta COM da placa e inicia a GS serial, por exemplo:

   ```powershell
   py -3 groundstation_serial.py --port COM5 --baudrate 115200
   ```

3. Abre o painel em <http://127.0.0.1:8050>. O botão **Sensores** abre um
   widget com os sensores, as medições, unidades e estado visual. O2 e
   humidade são apresentados com duas casas decimais; o painel UV usa a escala
   0–10. O nível do microfone em dBFS é relativo e não é dB SPL calibrado.
   A HuskyLens aparece como não integrada nesta versão.

O sketch drena as respostas seriais da GS, mas ainda não implementa
retransmissão por ACK. Antes de usar o APC220, definir e validar os GPIO de
UART, baud rate e estratégia de ACK/retransmissão para o rádio.
