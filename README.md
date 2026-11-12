# CanSat Ground Station & Simulator

Este repositório contém uma Ground Station para telemetria de **um ou vários CanSats** e um simulador C++ multicansat. A Ground Station principal é `groundstation.py`.

## Funcionalidades

- Painel Web em tempo real com gráficos, estado de voo, indicadores e vista geral ou individual por CanSat.
- Protocolo CANSAT-TLM v1, CRC32 para emissores simples e AES-GCM no firmware novo, com validação e estado de ligação.
- Compatibilidade com um CanSat ou vários. O simulador incluído gera cinco CanSats; a GS não exige que todos estejam ativos.
- Gravação automática em CSV, incluindo `cansat_id`, em `dados_voo/`; termina 30 segundos depois de todos os CanSats detetados reportarem aterragem (`SOLO` e altitude até 0,1 m).
- Os CSV usam `;` como separador e codificação UTF-8 com BOM para abrir as colunas corretamente no Excel com configuração regional portuguesa. A telemetria enviada pelo CanSat continua no protocolo JSON CANSAT-TLM.
- Depois de a gravação automática terminar, a receção e a visualização da telemetria continuam. Em modo LIVE, **Exportar CSV** descarrega o ficheiro completo da sessão, sem o limite do histórico visual.
- Botão **Pausar captura**: deixa de atualizar gráficos e CSV, mas continua a receber, validar e confirmar os pacotes com ACK. Os pacotes recebidos durante a pausa são descartados.
- Históricos de voo e gráficos limitados a 2000 amostras em memória.
- Os eixos verticais dos gráficos ajustam-se aos dados visíveis, com margem de 20% abaixo do mínimo e acima do máximo.
- O gráfico de altitude permite calcular e mostrar regressões lineares entre dois tempos de missão escolhidos pelo utilizador.
- Exportação do CSV completo em modo LIVE, CSV/ZIP em modo replay e gráficos PNG; modo replay a partir de CSV.
- Transporte UDP e variante serial para APC220. A página web está separada do código do servidor em `web/index.html`.

## Campos do pacote de telemetria

A tabela descreve o formato JSON CANSAT-TLM usado pelo simulador e internamente
pela GS. No firmware AES-GCM, o conteúdo cifrado é uma lista posicional compacta
documentada abaixo; a GS converte essa lista para este formato interno antes de
validar, calcular derivados e atualizar o painel/CSV.

Os campos de topo do protocolo CANSAT-TLM são obrigatórios. Em pacotes simples
protegidos por CRC, os campos base em `data` e `link` são obrigatórios. No
firmware AES-GCM, `data` contém apenas as medições disponíveis após a conversão
da lista posicional, e `link` fica vazio. Pacotes simples usam o campo `crc`;
no firmware novo, AES-GCM autentica o envelope cifrado. Campos científicos
adicionais em `data` são opcionais;
os atuais incluem O₂, som, resistência do gás e magnetómetro.

| Campo | Descrição | Formato (tipo de valor) | Exemplo |
|---|---|---|---|
| `protocol` | Nome do protocolo. | Texto fixo | `"CANSAT-TLM"` |
| `version` | Versão do protocolo. | Inteiro | `1` |
| `type` | Tipo da mensagem. | Texto fixo | `"telemetry"` |
| `cansat_id` | Identificador do CanSat. | Inteiro ≥ 0 | `2` |
| `sequence` | Número sequencial do pacote desse CanSat. | Inteiro ≥ 0 | `123` |
| `mission_time_ms` | Tempo de missão em milissegundos. | Inteiro ≥ 0 | `24600` |
| `state` | Estado/fase atual do voo. | Texto não vazio | `"SUBIDA"` |
| `data` | Objeto com medições dos sensores e estado do paraquedas. | Objeto JSON | `{...}` |
| `link` | Objeto com métricas da ligação de rádio. | Objeto JSON | `{...}` |
| `crc` | CRC32 do pacote simples, sem este campo, calculado sobre JSON canónico. O pacote AES-GCM usa a tag autenticadora do envelope. | Texto hexadecimal; ausente no pacote interno cifrado | `"C891D935"` |
| `data.altitude` | Altitude. O simulador expressa em metros. | Número finito | `152.35` |
| `data.velocity` | Velocidade vertical. O simulador expressa em m/s. | Número finito | `32.1` |
| `data.acceleration` | Aceleração. O simulador expressa em m/s². | Número finito | `23.7` |
| `data.force_g` | Força específica / aceleração medida em unidades de g. | Número finito | `3.4` |
| `data.temperature` | Temperatura. O simulador expressa em °C. | Número finito | `18.2` |
| `data.humidity` | Humidade relativa. O simulador expressa em percentagem. | Número finito | `55.0` |
| `data.pressure` | Pressão atmosférica. O simulador expressa em hPa. | Número finito | `995.8` |
| `data.sea_level_pressure_hpa` | P0 configurada na GS; opcional nos pacotes recebidos. A GS acrescenta o valor usado no cálculo. | Número finito; opcional | `1013.25` |
| `data.eco2` | Concentração equivalente de CO₂. O simulador expressa em ppm. | Número finito | `415` |
| `data.tvoc` | Compostos orgânicos voláteis totais. O simulador expressa em ppb. | Número finito | `10` |
| `data.uv` | Índice ultravioleta. | Número finito | `3.7` |
| `data.uv_millivolts` | Tensão média medida no sensor UV; a GS converte para índice 0–10. | Número finito; opcional | `280.0` |
| `data.lux` | Iluminância. O simulador expressa em lux. | Número finito | `43800` |
| `data.acc_x` | Aceleração no eixo X do acelerómetro. | Número finito | `0.02` |
| `data.acc_y` | Aceleração no eixo Y do acelerómetro. | Número finito | `-0.01` |
| `data.acc_z` | Aceleração no eixo Z do acelerómetro. | Número finito | `2.4` |
| `data.gyro_x` | Velocidade angular no eixo X do giroscópio. | Número finito | `0.1` |
| `data.gyro_y` | Velocidade angular no eixo Y do giroscópio. | Número finito | `-0.2` |
| `data.gyro_z` | Velocidade angular no eixo Z do giroscópio. | Número finito | `120.0` |
| `data.pitch` | Atitude de arfagem. O simulador expressa em graus. | Número finito | `88.2` |
| `data.roll` | Atitude de rolamento. O simulador expressa em graus. | Número finito | `135.0` |
| `data.yaw` | Atitude de guinada. O simulador expressa em graus. | Número finito | `45.0` |
| `data.parachute` | Indica se o paraquedas está aberto; `null` quando não é medido. | Booleano (`true`/`false`) ou `null` | `false` |
| `data.gas_resistance_kohm` | Resistência do sensor de gás do BME680. | Número finito; opcional | `54.2` |
| `data.oxygen_percent` | Concentração de O₂ indicada pelo Gravity SEN0465, em percentagem de volume. | Número finito; opcional | `20.9` |
| `data.sound_rms_adc` | RMS do sinal do microfone em contagens ADC; não é nível acústico calibrado. | Número finito; opcional | `18.4` |
| `data.sound_adc_sum`, `data.sound_adc_sum_squares`, `data.sound_sample_count` | Estatísticas da janela ADC do microfone; a GS calcula RMS e dBFS. | Inteiros; opcionais | `204800`, `850000000`, `500` |
| `data.sound_level_dbfs` | Nível relativo ao fundo de escala digital; não é dB SPL. | Número finito; opcional | `-38.2` |
| `data.mag_x`, `data.mag_y`, `data.mag_z` | Componentes do campo magnético do HMC5883L. | Número finito; opcional | `39.4` |
| `data.heading` | Rumo magnético horizontal calculado sem compensação de inclinação. | Número finito; opcional | `12.5` |
| `data.sensor_status` | Estado de inicialização dos sensores no CanSat. | Texto; opcional | `"bme680=ok;sgp30=ok"` |
| `link.rssi` | Potência do sinal recebido. O simulador expressa em dBm; `null` se não disponível. | Número finito ou `null` | `-78.5` |
| `link.snr` | Relação sinal/ruído. O simulador expressa em dB; `null` se não disponível. | Número finito ou `null` | `9.4` |
| `link.packet_loss` | Estimativa da perda de pacotes reportada pelo emissor. O simulador envia `0.0` ou `2.5`. | Número finito; opcional | `0.0` |

`data` e `link` têm de ser objetos JSON com os respetivos campos, não texto
contendo JSON. Nos emissores sem encriptação, o CRC é calculado sobre o objeto
completo sem `crc`; a representação usada para o cálculo ordena as chaves e
remove espaços. O novo firmware envolve o pacote num envelope AES-256-GCM;
a GS autentica e decifra o envelope antes de processar os dados. O ficheiro
[FORMATO_TELEMETRIA.txt](FORMATO_TELEMETRIA.txt) contém pacotes de exemplo.

### Lista posicional cifrada do firmware

O texto decifrado pelo AES-GCM é um array JSON com exatamente 17 posições.
As posições não mudam quando uma leitura falta: nesse caso o valor é `null`.
O CanSat ID segue no envelope autenticado; `sequence` é recuperado do nonce
depois da autenticação, pelo que não ocupa uma posição no array.

| Índice | Significado | Tipo |
|---:|---|---|
| 0 | `mission_time_ms` | Inteiro |
| 1 | `sensor_status` | Texto |
| 2 | `temperature` (°C) | Número ou `null` |
| 3 | `humidity` (%) | Número ou `null` |
| 4 | `pressure` (hPa) | Número ou `null` |
| 5 | `gas_resistance_kohm` | Número ou `null` |
| 6 | `eco2` (ppm) | Número ou `null` |
| 7 | `tvoc` (ppb) | Número ou `null` |
| 8 | `lux` | Número ou `null` |
| 9 | `uv_millivolts` | Número ou `null` |
| 10 | `oxygen_percent` (%) | Número ou `null` |
| 11–13 | `mag_x`, `mag_y`, `mag_z` | Números ou `null` |
| 14 | `sound_adc_sum` | Inteiro ou `null` |
| 15 | `sound_adc_sum_squares` | Inteiro ou `null` |
| 16 | `sound_sample_count` | Inteiro ou `null` |

O array permanece cifrado; não contém nomes de campos repetidos. O envelope
exterior continua JSON para transportar protocolo, CanSat ID, nonce, texto
cifrado e tag de autenticação.

O firmware integrado atual está em [Sensores/CanSat/CanSat.ino](Sensores/CanSat/CanSat.ino).
Instruções de bibliotecas, pinos e teste por USB estão em
[Sensores/CanSat/README.md](Sensores/CanSat/README.md). Os emissores antigos
continuam aceites; os gráficos de O2 e som já estão disponíveis na GS. A
GS também inclui um widget **Sensores** com o estado e as respetivas
medições. O firmware aguarda 10 segundos após o arranque e depois agenda cinco
pacotes por segundo (200 ms), cifrados com
AES-256-GCM; o BME680 atualiza a 5 Hz e o SGP30 a 1 Hz, repetindo-se o último
valor disponível entre leituras. Configura-se uma chave partilhada em
`Sensores/CanSat/CanSatSecrets.h`, usada pela GS e pelo firmware. A GS calcula
altitude, velocidade, aceleração e outros valores derivados; o campo
**P0 ao nível do mar (hPa)** aplica-se localmente por CanSat. A HuskyLens e a
ligação APC220 do novo firmware ficam para etapas posteriores.

## Estrutura

```text
cansat-cpp/
├── groundstation.py
├── groundstation_serial.py
├── Sensores/
│   └── CanSat/
│       ├── CanSat.ino
│       └── README.md
├── web/
│   └── index.html
├── requirements.txt
├── FORMATO_TELEMETRIA.txt
├── iniciar_gs.bat
├── README.md
├── README-Linux.txt
├── README-Windows.txt
└── simulador/
    ├── simulador.cpp
    ├── compilar.sh
    └── iniciar_simulador.bat
```

## Requisitos

### Linux / Ubuntu / Termux

Instala Python 3 e as dependências Python a partir da raiz do projeto:

```bash
python3 -m pip install -r requirements.txt
```

Para compilar o simulador, instala `g++` e os cabeçalhos nlohmann-json:

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install g++ nlohmann-json3-dev

# Termux
pkg install g++ nlohmann-json
```

### Windows

- Python 3, com o launcher `py`.
- MSYS2 UCRT64 com `g++` e `nlohmann-json`:

```bash
pacman -S --needed mingw-w64-ucrt-x86_64-gcc mingw-w64-ucrt-x86_64-nlohmann-json
```

Instala a dependência da GS:

```powershell
py -3 -m pip install -r requirements.txt
```

O `pyserial` só é usado pela variante APC220; instalá-lo através do ficheiro de requisitos permite preparar ambas as variantes de uma só vez.

## Executar em Linux

Inicia primeiro a Ground Station:

```bash
python3 groundstation.py
```

Abre <http://127.0.0.1:8050>. A GS escuta UDP em `127.0.0.1:5005`, WebSocket em `127.0.0.1:8051` e disponibiliza o painel HTTP em `127.0.0.1:8050`.
O transporte UDP está limitado ao loopback (`127.0.0.1`); para a ligação por rádio/APC220, usa a variante serial descrita abaixo.

Para executar o simulador multicansat, num segundo terminal:

```bash
cd simulador
./compilar.sh
./simulador
```

O simulador gera cinco CanSats. Um único CanSat compatível com CANSAT-TLM v1 também pode enviar para a mesma GS.

## Executar em Windows

Para iniciar uma simulação, executa primeiro `iniciar_gs.bat` na pasta do projeto. O script inicia `groundstation.py` e abre o painel em <http://127.0.0.1:8050>. Depois, executa `simulador/iniciar_simulador.bat`; esse script compila o simulador e, se a compilação tiver sucesso, inicia os cinco CanSats.

O simulador deve ser iniciado depois da Ground Station. A janela do simulador permanece aberta enquanto a simulação corre; prime `Ctrl+C` nessa janela para a parar.

`iniciar_gs.bat` usa o ambiente virtual ativo ou o `.venv` do projeto, se existir. `iniciar_simulador.bat` prepara o PATH das DLLs do MSYS2. A instalação padrão esperada é `C:\msys64`; se usares outra pasta, adiciona `ucrt64\bin` ao PATH do Windows.

## Serial USB e APC220

Para ligar o ESP32 diretamente por USB, fecha primeiro o Serial Monitor do
Arduino IDE e inicia a GS na porta COM da placa:

```powershell
py -3 groundstation_serial.py --port COM5
```

O firmware integrado usa 115200 baud por omissão. Para uma ligação APC220,
usa a porta do adaptador USB-UART do kit, baud 9600, e ativa o descodificador
binário do APC220:

```bash
python3 groundstation_serial.py --port /dev/ttyUSB0 --apc220-binary
```

Pela USB direta, a GS recebe linhas JSON a 115200 baud. Pelo APC220, o
firmware transmite frames binários AES-GCM de 99 bytes a 9600 baud e 5 Hz; a
opção `--apc220-binary` sincroniza e descodifica esses frames. O rádio e o
adaptador USB-UART têm de estar configurados para parâmetros compatíveis.
Não inicies simultaneamente a variante UDP e a serial, pois ambas usam as
mesmas portas Web e WebSocket.

## Captura, dados e encerramento

- **Pausar captura** interrompe os gráficos e a gravação CSV. A GS continua a receber e a enviar ACKs, mas não guarda os pacotes recebidos enquanto está pausada. **Retomar captura** reativa a gravação.
- Em modo LIVE, a gravação automática termina 30 segundos depois de todos os CanSats detetados reportarem estado `SOLO` e altitude igual ou inferior a 0,1 m. A GS continua a receber e a mostrar telemetria; **Exportar CSV** descarrega o ficheiro completo gravado na sessão.
- Os ficheiros da sessão são criados em `dados_voo/` com nomes como `voo_cansat_AAAA-MM-DD_HH-MM-SS.csv`. Cada linha inclui `cansat_id`; os ficheiros antigos sem essa coluna continuam a poder ser carregados no replay.
- Os CSV novos usam `;` como separador para compatibilidade com o Excel em português; o Replay continua a aceitar CSVs antigos separados por vírgula.
- Prime `Ctrl+C` no terminal do simulador para o parar e, depois, no terminal da GS.
- O formato do pacote e um exemplo com CRC32 estão em [FORMATO_TELEMETRIA.txt](FORMATO_TELEMETRIA.txt).

## Resolução de problemas

- **Porta ocupada:** verifica se já existe uma GS em execução. Não arranques as variantes UDP e serial em paralelo.
- **Pacotes rejeitados:** confirma que o emissor envia CANSAT-TLM v1 e inclui os campos obrigatórios. Em pacotes simples, verifica também o CRC32; para AES-GCM, confirma que ESP e GS usam a mesma chave privada.
- **Erro ao iniciar o simulador no Windows:** usa `iniciar_simulador.bat` e confirma que g++ e as DLLs do MSYS2 estão instalados; para um MSYS2 fora de `C:\msys64`, adiciona `ucrt64\bin` ao PATH.
