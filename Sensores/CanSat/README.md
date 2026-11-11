# Firmware integrado dos sensores

`CanSat.ino` foi preparado para a placa **ESP32-C6 Dev Module** e agenda cinco
pacotes por segundo, um a cada 200 ms, pela porta USB serial a 115200 baud.
Os valores dos sensores ficam em cache entre leituras: o BME680 atualiza a
200 ms e o SGP30 a 1000 ms. O envio usa AES-256-GCM; a GS aceita também
pacotes CANSAT-TLM antigos protegidos apenas por CRC. A câmara HuskyLens e a
ligação APC220 continuam adiadas.

## Chave AES-GCM

1. Se ainda não existir `CanSatSecrets.h`, copia `CanSatSecrets.example.h`
   para esse nome nesta pasta. Não substituas um ficheiro existente: a mesma
   chave tem de ser usada pelo ESP32 e pela GS.
2. Só se acabaste de copiar o exemplo, gera uma chave aleatória de 32 bytes:

   ```powershell
   py -3 -c "import secrets; print(secrets.token_hex(32))"
   ```

3. Coloca os 64 caracteres gerados no valor de `CANSAT_AES_KEY_HEX` em
   `CanSatSecrets.h`. Esta cópia local já tem uma chave privada configurada,
   por isso não a regeneres. A GS lê a chave do mesmo ficheiro. Não a
   partilhes nem a commits; o ficheiro real está no `.gitignore`.
4. Instala as dependências da GS, se necessário, com
   `py -3 -m pip install -r requirements.txt`. Só depois compila e carrega o
   firmware.

O firmware não transmite telemetria se a chave estiver ausente ou inválida.
Cada pacote usa um nonce novo e a autenticação AES-GCM; dados, nonce e tag
aparecem codificados em Base64 no envelope serial, mas as medições ficam
cifradas. O contador de arranques guardado na NVS impede reutilizar nonces
após um reinício normal; não apagues a NVS mantendo a mesma chave AES.

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

- O ESP envia pressão e outros valores medidos, deixando `altitude`,
  `velocity`, `acceleration`, `heading` e `sound_level_dbfs` nulos. A GS
  calcula esses campos a partir da pressão, P0, tempo de missão, magnetómetro
  e estatísticas ADC do microfone. O firmware envia a tensão UV média; a GS
  converte-a para o índice UV de 0–10. P0 é configurado na GS e mantém-se por
  CanSat durante a sessão da GS.
- `oxygen_percent` representa a concentração reportada pelo SEN0465 em
  percentagem de volume; humidade e oxigénio são transmitidos arredondados a
  duas casas decimais. `gas_resistance_kohm` é a resistência do sensor de gás
  do BME680; não é uma medição de O2.
- O índice UV é convertido pela GS a partir de tensão: 6 mV = índice 0 e
  900 mV = índice 10, limitado à escala 0–10. É uma estimativa a validar
  contra uma referência UV.
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

1. Configura a chave conforme a secção anterior, liga a placa por USB e fecha
   o Serial Monitor do Arduino IDE.
2. Descobre a porta COM da placa e inicia a GS serial:

   ```powershell
   py -3 groundstation_serial.py --port COM5
   ```

3. Abre o painel em <http://127.0.0.1:8050>. O botão **Sensores** abre um
   widget com os sensores, as medições, unidades e estado visual. O2 e
   humidade são apresentados com duas casas decimais; o painel UV usa a escala
   0–10. O nível do microfone em dBFS é calculado na GS e é relativo; não é
   dB SPL calibrado.
   A HuskyLens aparece como não integrada nesta versão.
4. No painel **Referência de pressão para altitude**, introduz P0 em hPa e
   clica **Aplicar P0**. Com um CanSat selecionado, a referência fica
   associada a esse ID; sem seleção, é usada para o último CanSat que
   transmitiu. Altitude, velocidade e aceleração passam a ser calculadas pela
   GS e guardadas no CSV.

O agendamento usa intervalos nominais de 200 ms; o tempo do pacote regista o
instante do slot. Se o sensor, o USB ou o processador atrasar um slot, a GS
mantém a lacuna no tempo/na sequência em vez de inventar uma leitura. O SGP30
continua a atualizar a 1 Hz, pelo que o seu último valor é repetido nos
pacotes intermédios.
