# Firmware integrado dos sensores

`CanSat.ino` foi preparado para a placa **ESP32-C6 Dev Module**. Após ligar,
aguarda 10 segundos antes do primeiro pacote. Depois envia cinco pacotes por
segundo pela USB serial a 115200 baud e pelo APC220 a 9600 baud.
Os valores dos sensores ficam em cache entre leituras: o BME680 atualiza a
200 ms e o SGP30 a 1000 ms. O envio usa AES-256-GCM; a GS aceita também
pacotes CANSAT-TLM antigos protegidos apenas por CRC.

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
Cada pacote usa um nonce novo e a autenticação AES-GCM; pela USB, o nonce,
ciphertext e tag aparecem em Base64 no envelope JSON. Pelo APC220, seguem
como bytes no frame binário. O contador de arranques guardado na NVS impede
reutilizar nonces após um reinício normal; não apagues a NVS mantendo a mesma
chave AES.

## Formato compacto da telemetria

O conteúdo cifrado é um array JSON posicional de 17 valores, sem nomes de
campos. A ordem é fixa: `[mission_time_ms, sensor_status, temperature,
humidity, pressure, gas_resistance_kohm, eco2, tvoc, lux, uv_millivolts,
oxygen_percent, mag_x, mag_y, mag_z, sound_adc_sum,
sound_adc_sum_squares, sound_sample_count]`. Uma medição indisponível aparece
como `null`, sem deslocar as posições seguintes. O CanSat ID está no envelope
autenticado; a GS obtém o número de sequência a partir do nonce autenticado.
USB e APC220 mantêm sequências independentes e prefixos de nonce distintos,
para que pacotes recebidos por ligações diferentes não reutilizem nonces.
Pela USB, o conteúdo AES-GCM é o array JSON. Pelo APC220, a mesma telemetria
é codificada num frame binário compacto de 99 bytes, abaixo do buffer de
256 bytes indicado para o módulo.

O frame APC220 tem esta estrutura: `C3 5A` (sincronização), versão `01`,
CanSat ID (1 byte), nonce (12 bytes), ciphertext (67 bytes) e tag AES-GCM
(16 bytes). O plaintext binário é little-endian: `mission_time_ms` uint32,
estado dos sensores (1 byte; bits 0–4 para BME680, SGP30, TSL2561, HMC5883L
e SEN0465; bits 5–6 para MAX4466 e UV configurados), 12 valores float32
(`temperature`, `humidity`, `pressure`, `gas_resistance_kohm`, `eco2`,
`tvoc`, `lux`, `uv_millivolts`, `oxygen_percent`, `mag_x`, `mag_y`, `mag_z`),
`sound_adc_sum` uint32, `sound_adc_sum_squares` uint64 e
`sound_sample_count` uint16. NaN significa uma leitura indisponível; zero
amostras significa que as estatísticas do som não estão disponíveis.

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
| APC220 | UART1 | ESP TX GPIO16, ESP RX GPIO17 |

O GPIO1 foi escolhido para o MAX4466 para resolver a colisão com o UV no
GPIO0. Confirma esta ligação na placa antes de alimentar o circuito. Os
sensores I2C partilham o mesmo barramento configurado a 100 kHz.

## Ligação e receção pelo APC220

Liga o APC220 ao ESP32-C6 com UART cruzada:

| APC220 | ESP32-C6 |
|---|---|
| TXD | RX GPIO17 |
| RXD | TX GPIO16 |
| GND | GND |
| VCC | Alimentação especificada para a versão do teu módulo |

Confirma no manual do módulo a tensão de alimentação e os níveis lógicos;
GPIOs do ESP32-C6 são de 3,3 V e não toleram 5 V. O sketch e a GS usam UART
a 9600 baud, 8N1; confirma/configura ambos os módulos e o dongle USB para
essa velocidade. Usa antena adequada e configura os dois módulos com
parâmetros RF compatíveis (canal, taxa de ar e endereço, se aplicável). A
taxa UART não é a taxa de transmissão pelo ar.

No computador, liga o segundo APC220 a um adaptador USB-UART com lógica de
3,3 V: TXD do rádio ao RX do adaptador, RXD ao TX, e GND comum. O adaptador
USB-UART tem de ser uma interface serial TTL; não ligues sinais UART
diretamente aos pinos USB do computador. Fecha o Serial Monitor do Arduino
IDE e inicia a GS no modo binário APC220:

```powershell
py -3 groundstation_serial.py --port COM8 --apc220-binary
```

O rádio transmite cinco frames binários AES-GCM de 99 bytes por segundo. O
produto indica buffer de 256 bytes e alcance especificado a 9600 bps; o
formato compacto cabe no buffer e reduz o débito do payload para cerca de
4,95 kbit/s na UART a 9600 baud (8N1). O desempenho RF real depende da
configuração dos módulos e deve ser confirmado em teste.

## Dados e limitações nesta fase

- O ESP envia as leituras medidas numa lista posicional fixa. Leituras
  indisponíveis ocupam o respetivo índice como `null`; não envia campos
  derivados. A GS calcula altitude, velocidade, aceleração, rumo, índice UV e
  métricas do som. P0 é configurado na GS e mantém-se por CanSat durante a
  sessão.
- `oxygen_percent` representa a concentração reportada pelo SEN0465 em
  percentagem de volume; humidade e oxigénio são transmitidos arredondados a
  duas casas decimais. `gas_resistance_kohm` é a resistência do sensor de gás
  do BME680; não é uma medição de O2.
- O índice UV é convertido pela GS a partir de tensão: 6 mV = índice 0 e
  900 mV = índice 10, limitado à escala 0–10. É uma estimativa a validar
  contra uma referência UV.
- `sound_level_dbfs` é relativo à escala ADC e não é dB SPL calibrado.
- O HMC5883L produz magnetómetro/rumo magnético; não substitui um IMU.
  Acelerómetro, giroscópio, atitude, paraquedas e métricas de rádio não são
  incluídos porque esta versão não os mede. Os sensores não encontrados são
  indicados como `missing` em `sensor_status`; os respetivos índices levam
  `null`.
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

O agendamento USB e APC220 usa intervalos nominais de 200 ms; o tempo do
pacote regista o instante do slot que originou a amostra. Se o sensor, a
serial ou o processador atrasar um slot, a GS mantém a lacuna no tempo/na
sequência em vez de inventar uma leitura. O SGP30 continua a atualizar a 1 Hz,
pelo que o seu último valor é repetido nos pacotes intermédios.
