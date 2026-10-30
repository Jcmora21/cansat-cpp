# CanSat Ground Station & Simulator

Este repositório contém uma Ground Station para telemetria de **um ou vários CanSats** e um simulador C++ multicansat. A Ground Station principal é `groundstation.py`.

## Funcionalidades

- Painel Web em tempo real com gráficos, estado de voo, indicadores e vista geral ou individual por CanSat.
- Protocolo CANSAT-TLM v1, com validação dos campos e CRC32, ACKs, identificação de pacotes duplicados/perdidos e estado de ligação.
- Compatibilidade com um CanSat ou vários. O simulador incluído gera cinco CanSats; a GS não exige que todos estejam ativos.
- Gravação automática em CSV, incluindo `cansat_id`, em `dados_voo/`; termina 30 segundos depois de todos os CanSats detetados reportarem aterragem (`SOLO` e altitude até 0,1 m).
- Depois de a gravação automática terminar, a receção e a visualização da telemetria continuam. Em modo LIVE, **Exportar CSV** descarrega o ficheiro completo da sessão, sem o limite do histórico visual.
- Botão **Pausar captura**: deixa de atualizar gráficos e CSV, mas continua a receber, validar e confirmar os pacotes com ACK. Os pacotes recebidos durante a pausa são descartados.
- Históricos de voo e gráficos limitados a 2000 amostras em memória.
- Exportação do CSV completo em modo LIVE, CSV/ZIP em modo replay e gráficos PNG; modo replay a partir de CSV.
- Transporte UDP e variante serial para APC220. A página web está separada do código do servidor em `web/index.html`.

## Campos do pacote de telemetria

A GS recebe pacotes **CANSAT-TLM v1** neste formato JSON. A tabela descreve
o pacote que o CanSat (ou o simulador) envia, antes de a GS converter os nomes
para uso interno no painel e no CSV. Os campos listados são os nomes exatos
esperados no protocolo.

Todos os campos de topo são obrigatórios. Dentro de `data`, todos os campos
indicados são obrigatórios; em `link`, `rssi` e `snr` são obrigatórios e
`packet_loss` é opcional para a GS. Os campos numéricos devem conter um número
JSON finito (inteiro ou decimal); `parachute` tem de ser booleano. O campo
`crc` também é necessário para a GS aceitar o pacote.

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
| `crc` | CRC32 do pacote sem este campo, calculado sobre JSON canónico (chaves ordenadas e sem espaços). | Texto hexadecimal, 1–8 caracteres | `"C891D935"` |
| `data.altitude` | Altitude. O simulador expressa em metros. | Número finito | `152.35` |
| `data.velocity` | Velocidade vertical. O simulador expressa em m/s. | Número finito | `32.1` |
| `data.acceleration` | Aceleração. O simulador expressa em m/s². | Número finito | `23.7` |
| `data.force_g` | Força específica / aceleração medida em unidades de g. | Número finito | `3.4` |
| `data.temperature` | Temperatura. O simulador expressa em °C. | Número finito | `18.2` |
| `data.humidity` | Humidade relativa. O simulador expressa em percentagem. | Número finito | `55.0` |
| `data.pressure` | Pressão atmosférica. O simulador expressa em hPa. | Número finito | `995.8` |
| `data.eco2` | Concentração equivalente de CO₂. O simulador expressa em ppm. | Número finito | `415` |
| `data.tvoc` | Compostos orgânicos voláteis totais. O simulador expressa em ppb. | Número finito | `10` |
| `data.uv` | Índice ultravioleta. | Número finito | `3.7` |
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
| `data.parachute` | Indica se o paraquedas está aberto. | Booleano (`true`/`false`) | `false` |
| `link.rssi` | Potência do sinal recebido. O simulador expressa em dBm. | Número finito | `-78.5` |
| `link.snr` | Relação sinal/ruído. O simulador expressa em dB. | Número finito | `9.4` |
| `link.packet_loss` | Estimativa da perda de pacotes reportada pelo emissor. O simulador envia `0.0` ou `2.5`. | Número finito; opcional | `0.0` |

`data` e `link` têm de ser objetos JSON com os respetivos campos, não texto
contendo JSON. O CRC é calculado sobre o objeto completo sem `crc`; a
representação usada para o cálculo ordena as chaves e remove espaços, e o
resultado é transmitido como hexadecimal. O ficheiro
[FORMATO_TELEMETRIA.txt](FORMATO_TELEMETRIA.txt) contém pacotes de exemplo.

## Estrutura

```text
cansat-cpp/
├── groundstation.py
├── groundstation_serial.py
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

## APC220 (serial)

Liga o APC220 do PC a uma porta USB-serial e inicia a variante que reutiliza a mesma Ground Station e o mesmo painel:

```bash
python3 groundstation_serial.py --port /dev/ttyUSB0 --baudrate 9600
```

Substitui a porta e o baudrate pelos valores do teu adaptador e dos módulos. No Windows, indica a porta COM, por exemplo `--port COM3`. O protocolo serial usa uma mensagem JSON por linha, terminada em newline (`\n`); a ligação entre os módulos tem de transportar telemetria e respostas ACK. Não inicies simultaneamente a variante UDP e a serial, pois ambas usam as mesmas portas Web e WebSocket.

## Captura, dados e encerramento

- **Pausar captura** interrompe os gráficos e a gravação CSV. A GS continua a receber e a enviar ACKs, mas não guarda os pacotes recebidos enquanto está pausada. **Retomar captura** reativa a gravação.
- Em modo LIVE, a gravação automática termina 30 segundos depois de todos os CanSats detetados reportarem estado `SOLO` e altitude igual ou inferior a 0,1 m. A GS continua a receber e a mostrar telemetria; **Exportar CSV** descarrega o ficheiro completo gravado na sessão.
- Os ficheiros da sessão são criados em `dados_voo/` com nomes como `voo_cansat_AAAA-MM-DD_HH-MM-SS.csv`. Cada linha inclui `cansat_id`; os ficheiros antigos sem essa coluna continuam a poder ser carregados no replay.
- Prime `Ctrl+C` no terminal do simulador para o parar e, depois, no terminal da GS.
- O formato do pacote e um exemplo com CRC32 estão em [FORMATO_TELEMETRIA.txt](FORMATO_TELEMETRIA.txt).

## Resolução de problemas

- **Porta ocupada:** verifica se já existe uma GS em execução. Não arranques as variantes UDP e serial em paralelo.
- **Pacotes rejeitados:** confirma que o emissor envia CANSAT-TLM v1, inclui os campos obrigatórios e calcula o CRC32 sobre o objeto sem o campo `crc`.
- **Erro ao iniciar o simulador no Windows:** usa `iniciar_simulador.bat` e confirma que g++ e as DLLs do MSYS2 estão instalados; para um MSYS2 fora de `C:\msys64`, adiciona `ucrt64\bin` ao PATH.
