====================================================================
               CANSAT GROUND STATION & SIMULATOR
====================================================================

Este projeto contem uma Ground Station que funciona com um ou varios
CanSats, e um simulador C++ que representa cinco unidades. A Ground
Station principal e groundstation.py. A comunicacao usa CANSAT-TLM v1,
com CRC32, ACKs e retransmissoes.

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
  pasta dados_voo/. Termina 30 segundos depois de todos os CanSats
  detetados reportarem aterragem (estado SOLO e altitude ate 0,1 m).
- Botao para pausar/retomar a captura: os ACKs continuam ativos durante
  a pausa, mas graficos e CSV ignoram os pacotes recebidos nesse periodo.
- Historicos limitados a 2000 amostras.
- Depois do fim da gravacao automatica, a telemetria continua visivel.
  Em modo LIVE, Exportar CSV descarrega o ficheiro completo da sessao.
- Exportacao em modo replay: CSV/ZIP; captura em imagem .png dos graficos.
- Pagina web em web/index.html, separada do servidor Python.

--------------------------------------------------------------------
2. ESTRUTURA DO PROJETO
--------------------------------------------------------------------

cansat-cpp/
├── groundstation.py        # Ground Station UDP para um ou varios CanSats
├── groundstation_serial.py # A mesma GS atraves de serial/APC220
├── web/
│   └── index.html          # Interface Web da GS
├── requirements.txt        # Dependencias Python da GS
├── FORMATO_TELEMETRIA.txt  # Formato e exemplo CANSAT-TLM com CRC
├── dados_voo/              # CSV de cada sessao, incluindo cansat_id
└── simulador/
    ├── simulador.cpp       # Simulador de cinco CanSats
    └── compilar.sh         # Script Linux para compilacao

--------------------------------------------------------------------
3. REQUISITOS E DEPENDENCIAS
--------------------------------------------------------------------

No ambiente Linux/Ubuntu (via Termux/PROOT), garante as dependencias:

- Python 3 (dependencias da GS UDP e serial):
  python3 -m pip install -r requirements.txt

- Compilador C++ (g++) e cabecalhos nlohmann-json:
  Ubuntu/Debian: sudo apt update && sudo apt install g++ nlohmann-json3-dev
  Termux: pkg install g++ nlohmann-json

- Se for necessario criar um ambiente virtual (venv):
  [No Termux]: pkg install python python-pip
  [No Ubuntu]: sudo apt install python3-venv

  Criar e ativar o ambiente:
  python3 -m venv .venv
  source .venv/bin/activate

--------------------------------------------------------------------
4. COMO EXECUTAR O SISTEMA
--------------------------------------------------------------------

A Ground Station deve estar ativa antes de iniciar um simulador UDP.

PASSO 1: Iniciar a Estacao de Solo (Terminal 1)
-----------------------------------------------
Executa o comando:
  python3 groundstation.py

- Servidores iniciados: UDP (5005), WebSocket (8051) e Web (8050).
- O UDP escuta apenas em 127.0.0.1; para APC220, usa a variante serial.
- Acede no navegador web ao endereco: http://127.0.0.1:8050

PASSO 2: Compilar e Iniciar o Simulador (Terminal 2)
----------------------------------------------------
Abre um segundo terminal e executa:
  cd simulador
  ./compilar.sh
  ./simulador

- O simulador incluido gera cinco CanSats e envia os dados por UDP. A GS
  tambem funciona quando so um CanSat compativel esta a transmitir.
- A GS valida CRC32 e campos, confirma pacotes validos com ACK e guarda o
  identificador cansat_id no CSV.
- Acompanha os graficos em tempo real no navegador.
- Usa o botao "Pausar captura" para suspender graficos/CSV sem parar os ACKs;
  "Retomar captura" reativa a captura.
- A gravacao automatica termina 30 segundos depois da aterragem de todos os
  CanSats detetados (estado SOLO e altitude ate 0,1 m). A visualizacao
  continua; "Exportar CSV" em modo LIVE descarrega o CSV completo da sessao.
- O script simulador/compilar.sh compila a partir da pasta do proprio script,
  por isso o repositorio pode estar instalado em qualquer local.

Para usar APC220, liga a porta USB-serial e executa, por exemplo:
  python3 groundstation_serial.py --port /dev/ttyUSB0 --baudrate 9600
Indica a porta e o baudrate do teu adaptador. As mensagens, incluindo ACKs,
sao objetos JSON terminados em newline. Nao arranques em simultaneo a GS
UDP e a serial, pois partilham as portas do painel e do WebSocket.

--------------------------------------------------------------------
5. COMO PARAR A EXECUCAO
--------------------------------------------------------------------

- Parar o Simulador: No Terminal 2, prime Ctrl + C.
- Parar a Ground Station: No Terminal 1, prime Ctrl + C.
(Os dados do voo ficam gravados em seguranca na pasta dados_voo/).

--------------------------------------------------------------------
6. RESOLUCAO DE PROBLEMAS
--------------------------------------------------------------------

- Porta em uso (Address already in use):
  Se o servidor nao arrancar por porta ocupada, executa:
  fuser -k 8050/tcp 8051/tcp 5005/udp

--------------------------------------------------------------------
7. GESTAO DOS DADOS DE VOO (.CSV)
--------------------------------------------------------------------

- Ficheiros gerados no formato: voo_cansat_AAAA-MM-DD_HH-MM-SS.csv
- Cada linha inclui cansat_id para distinguir os CanSats; os ficheiros
  antigos sem esta coluna continuam compativeis com o modo Replay.
- Pasta de destino: ~/cansat-cpp/dados_voo/
