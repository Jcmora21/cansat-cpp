====================================================================
               CANSAT GROUND STATION & SIMULATOR (WINDOWS)
====================================================================

Este projeto contem uma Ground Station que funciona com um ou varios
CanSats e um simulador C++ que representa cinco unidades. A Ground Station
principal e groundstation.py. A comunicacao usa CANSAT-TLM v1, com CRC32,
ACKs e retransmissoes.

--------------------------------------------------------------------
1. FUNCIONALIDADES
--------------------------------------------------------------------

- Painel Web em Tempo Real: Interface desenvolvida em HTML5/JavaScript
  com graficos dinamicos (Chart.js) organizados em grelha responsiva.
- Gestao Inteligente de Fases de Voo: Detecao de transicoes de estado
  (Espera, Subida, Apogeu, Descida) com etiquetagem automatica.
- Metricas de Voo e KPIs: Exibicao automatica dos valores Minimo,
  Maximo e Media no topo de cada grafico.
- Gravacao Automatica em CSV: Salvamento instantaneo dos pacotes na
  pasta dados_voo\. Termina 30 segundos depois de todos os CanSats
  detetados reportarem aterragem (estado SOLO e altitude ate 0,1 m).
- Pausa da captura: suspende graficos e CSV, mas mantem a rececao,
  validacao e os ACKs ativos. Os pacotes recebidos durante a pausa
  nao sao guardados.
- Historico limitado a 2000 amostras para controlar o uso de memoria.
- Depois do fim da gravacao automatica, a telemetria continua visivel.
  Em modo LIVE, Exportar CSV descarrega o ficheiro completo da sessao.
- Exportacao de Dados em modo replay: CSV/ZIP; captura em imagem .png
  dos graficos.

--------------------------------------------------------------------
2. ESTRUTURA DO PROJETO
--------------------------------------------------------------------

cansat-cpp\
├── groundstation.py        # Ground Station UDP para um ou varios CanSats
├── groundstation_serial.py # A mesma GS atraves de serial/APC220
├── web\
│   └── index.html          # Interface Web da GS
├── requirements.txt        # Dependencias Python da GS
├── iniciar_gs.bat          # Inicia a Ground Station e abre o painel Web
├── FORMATO_TELEMETRIA.txt  # Estrutura e exemplo CANSAT-TLM v1
├── dados_voo\              # CSV de cada sessao, com cansat_id
└── simulador\
    ├── simulador.cpp       # Simulador multicansat com ACK/retransmissao
    └── iniciar_simulador.bat # Compila e inicia; configura as DLLs do MSYS2

--------------------------------------------------------------------
3. REQUISITOS E DEPENDENCIAS (WINDOWS)
--------------------------------------------------------------------

No Windows (PowerShell ou CMD), garante que tens instalado:

1. Python (marcar a opcao "Add Python to PATH" na instalacao):
   https://www.python.org/downloads/

2. MSYS2 UCRT64 com g++ e nlohmann-json. No terminal UCRT64:
   pacman -S --needed mingw-w64-ucrt-x86_64-gcc mingw-w64-ucrt-x86_64-nlohmann-json
   O script reconhece a instalacao padrao em C:\msys64; para outra pasta,
   adiciona a pasta ucrt64\bin do MSYS2 ao PATH do Windows.

Instalacao das dependencias Python:
  py -3 -m pip install -r requirements.txt

Se for necessario criar um ambiente virtual (venv):
  py -3 -m venv .venv
  .venv\Scripts\activate
  python -m pip install -r requirements.txt
O iniciar_gs.bat usa o venv ativo ou .venv\ automaticamente, se existir.

--------------------------------------------------------------------
4. COMO EXECUTAR O SISTEMA
--------------------------------------------------------------------

A Ground Station deve estar ativa antes de iniciar o simulador. O arranque e
feito em duas etapas: primeiro iniciar a GS e depois compilar/iniciar o
simulador.

PASSO 1: Iniciar a Ground Station, a partir da pasta do projeto:
  iniciar_gs.bat

O script abre uma janela para a GS e o painel Web em
  http://127.0.0.1:8050

PASSO 2: Compilar e iniciar os cinco CanSats simulados:
  simulador\iniciar_simulador.bat

O script compila sempre simulador.cpp e so arranca a simulacao se a
compilacao terminar com sucesso. A janela permanece aberta durante o voo.

Para controlo manual, tambem podes iniciar a GS com:
  py -3 groundstation.py

- Servidores da GS: UDP (5005), WebSocket (8051) e Web (8050).
- O UDP escuta apenas em 127.0.0.1; para APC220, usa a variante serial.
- O simulador incluido gera cinco CanSats e envia os dados via UDP. A GS
  tambem funciona se apenas um CanSat compativel estiver a transmitir.
- A Ground Station valida o CRC32, confirma cada pacote valido com ACK,
  deteta duplicados/pacotes em falta e exporta o cansat_id para o CSV.
- Acompanha os graficos em tempo real no navegador.
- O botao "Pausar captura" suspende graficos e CSV sem interromper os ACKs;
  "Retomar captura" reativa a captura.
- A gravacao automatica termina 30 segundos depois de todos os CanSats
  detetados reportarem estado SOLO e altitude ate 0,1 m. A visualizacao
  continua; "Exportar CSV" em modo LIVE guarda o CSV completo da sessao.

Para usar APC220, liga o adaptador USB-serial e indica a porta COM e o
baudrate configurado nos modulos, por exemplo:
  py -3 groundstation_serial.py --port COM3 --baudrate 9600
As mensagens, incluindo ACKs, sao objetos JSON terminados em newline.
Nao inicies a GS UDP e a serial ao mesmo tempo: partilham as portas
do painel Web e do WebSocket.

--------------------------------------------------------------------
5. COMO PARAR A EXECUCAO
--------------------------------------------------------------------

- Parar o Simulador: No Terminal 2, prime Ctrl + C.
- Parar a Ground Station: No Terminal 1, prime Ctrl + C.
(Os dados do voo ficam gravados em seguranca na pasta dados_voo\).

--------------------------------------------------------------------
6. RESOLUCAO DE PROBLEMAS (WINDOWS)
--------------------------------------------------------------------

- Porta em uso (Address already in use):
  Se a porta estiver ocupada no Windows, descobre e termina o processo:
  
  No PowerShell:
  Get-NetTCPConnection -LocalPort 8050, 8051 | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }

  No CMD:
  netstat -ano | findstr :8050
  taskkill /F /PID <NUMERO_DO_PID>

--------------------------------------------------------------------
7. GESTAO DOS DADOS DE VOO (.CSV)
--------------------------------------------------------------------

- Ficheiros gerados no formato: voo_cansat_AAAA-MM-DD_HH-MM-SS.csv
- Cada linha inclui cansat_id para distinguir os CanSats; ficheiros antigos
  sem essa coluna continuam compativeis com o modo Replay.
- Pasta de destino: .\dados_voo\
