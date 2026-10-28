# CanSat Ground Station & Simulator

Este repositório contém uma Ground Station para telemetria de **um ou vários CanSats** e um simulador C++ multicansat. A Ground Station principal é `groundstation.py`.

## Funcionalidades

- Painel Web em tempo real com gráficos, estado de voo, indicadores e vista geral ou individual por CanSat.
- Protocolo CANSAT-TLM v1, com validação dos campos e CRC32, ACKs, identificação de pacotes duplicados/perdidos e estado de ligação.
- Compatibilidade com um CanSat ou vários. O simulador incluído gera cinco CanSats; a GS não exige que todos estejam ativos.
- Gravação automática em CSV, incluindo `cansat_id`, em `dados_voo/`.
- Botão **Pausar captura**: deixa de atualizar gráficos e CSV, mas continua a receber, validar e confirmar os pacotes com ACK. Os pacotes recebidos durante a pausa são descartados.
- Históricos de voo e gráficos limitados a 2000 amostras em memória.
- Exportação de CSV/ZIP e de gráficos PNG; modo replay a partir de CSV.
- Transporte UDP e variante serial para APC220.

## Estrutura

```text
cansat-cpp/
├── groundstation.py
├── groundstation_serial.py
├── FORMATO_TELEMETRIA.txt
├── iniciar_cansat.bat
├── README.md
├── README-Linux.txt
├── README-Windows.txt
└── simulador/
    ├── simulador.cpp
    ├── compilar.sh
    ├── compilar.bat
    └── iniciar_simulador.bat
```

## Requisitos

### Linux / Ubuntu / Termux

Instala Python 3 e as dependências:

```bash
python3 -m pip install websockets pyserial
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
py -3 -m pip install websockets
```

Para APC220 no Windows, instala também `pyserial` com `py -3 -m pip install pyserial`.

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

O método automatizado recomendado é executar `iniciar_cansat.bat` na pasta do projeto. O script compila o simulador, inicia `groundstation.py`, abre o painel e pergunta se queres iniciar os cinco CanSats simulados.

Para iniciar os componentes manualmente, executa `py -3 groundstation.py`; depois, num segundo terminal:

```bat
cd simulador
compilar.bat
iniciar_simulador.bat
```

`iniciar_simulador.bat` prepara o PATH das DLLs do MSYS2. A instalação padrão esperada é `C:\msys64`; se usares outra pasta, adiciona `ucrt64\bin` ao PATH do Windows.

## APC220 (serial)

Liga o APC220 do PC a uma porta USB-serial e inicia a variante que reutiliza a mesma Ground Station e o mesmo painel:

```bash
python3 groundstation_serial.py --port /dev/ttyUSB0 --baudrate 9600
```

Substitui a porta e o baudrate pelos valores do teu adaptador e dos módulos. No Windows, indica a porta COM, por exemplo `--port COM3`. O protocolo serial usa uma mensagem JSON por linha, terminada em newline (`\n`); a ligação entre os módulos tem de transportar telemetria e respostas ACK. Não inicies simultaneamente a variante UDP e a serial, pois ambas usam as mesmas portas Web e WebSocket.

## Captura, dados e encerramento

- **Pausar captura** interrompe os gráficos e a gravação CSV. A GS continua a receber e a enviar ACKs, mas não guarda os pacotes recebidos enquanto está pausada. **Retomar captura** reativa a gravação.
- Os ficheiros da sessão são criados em `dados_voo/` com nomes como `voo_cansat_AAAA-MM-DD_HH-MM-SS.csv`. Cada linha inclui `cansat_id`; os ficheiros antigos sem essa coluna continuam a poder ser carregados no replay.
- Prime `Ctrl+C` no terminal do simulador para o parar e, depois, no terminal da GS.
- O formato do pacote e um exemplo com CRC32 estão em [FORMATO_TELEMETRIA.txt](FORMATO_TELEMETRIA.txt).

## Resolução de problemas

- **Porta ocupada:** verifica se já existe uma GS em execução. Não arranques as variantes UDP e serial em paralelo.
- **Pacotes rejeitados:** confirma que o emissor envia CANSAT-TLM v1, inclui os campos obrigatórios e calcula o CRC32 sobre o objeto sem o campo `crc`.
- **Erro ao iniciar o simulador no Windows:** usa `iniciar_simulador.bat` e confirma que g++ e as DLLs do MSYS2 estão instalados; para um MSYS2 fora de `C:\msys64`, adiciona `ucrt64\bin` ao PATH.
