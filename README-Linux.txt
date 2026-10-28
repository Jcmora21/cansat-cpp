====================================================================
               CANSAT GROUND STATION & SIMULATOR
====================================================================

Este projeto contem a Ground Station multicansat e um simulador C++
que representa cinco CanSats. A comunicacao usa CANSAT-TLM v1 sobre
UDP em 127.0.0.1:5005, com CRC32, ACKs e retransmissoes.

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
  pasta dados_voo/.
- Botao para pausar/retomar a captura: os ACKs continuam ativos durante
  a pausa, mas graficos e CSV ignoram os pacotes recebidos nesse periodo.
- Historicos limitados a 2000 amostras.
- Exportacao de Dados: Descarga direta do historico em .csv ou
  captura em imagem .png dos graficos.

--------------------------------------------------------------------
2. ESTRUTURA DO PROJETO
--------------------------------------------------------------------

cansat-cpp/
├── groundstation.py         # Ground Station multicansat UDP
├── groundstation_serial.py # Variante serial/APC220 da mesma GS
├── entrar.sh               # Script de inicializacao Termux/Ubuntu
├── dados_voo/              # Pasta onde sao gravados os ficheiros .csv
└── simulador/
    ├── simulador.cpp       # Codigo-fonte do simulador em C++
    └── compilar.sh         # Script para compilacao do simulador

--------------------------------------------------------------------
3. REQUISITOS E DEPENDENCIAS
--------------------------------------------------------------------

No ambiente Linux/Ubuntu (via Termux/PROOT), garante as dependencias:

- Python 3 (com a biblioteca websockets):
  pip install websockets

- Compilador C++ (g++) e cabecalhos nlohmann-json:
  sudo apt update && sudo apt install g++ nlohmann-json3-dev -y
  No Termux: pkg install g++ nlohmann-json

- Se for necessario criar um ambiente virtual (venv):
  [No Termux]: pkg install python python-pip
  [No Ubuntu]: sudo apt install python3-venv

  Criar e ativar o ambiente:
  python3 -m venv .venv
  source .venv/bin/activate

--------------------------------------------------------------------
4. COMO EXECUTAR O SISTEMA
--------------------------------------------------------------------

A Estacao de Solo deve ser SEMPRE iniciada antes do Simulador.

PASSO 1: Iniciar a Estacao de Solo (Terminal 1)
-----------------------------------------------
Executa o comando:
  python3 groundstation.py

- Servidores iniciados: UDP (5005), WebSocket (8051) e Web (8050).
- Acede no navegador web ao endereco: http://127.0.0.1:8050

PASSO 2: Compilar e Iniciar o Simulador (Terminal 2)
----------------------------------------------------
Abre um segundo terminal e executa:
  cd simulador
  ./compilar.sh
  ./simulador

- O simulador gera os dados e envia-os via UDP para a Ground Station.
- A GS valida CRC32 e campos, confirma pacotes validos com ACK e guarda o
  identificador cansat_id no CSV.
- Acompanha os graficos em tempo real no navegador.
- Usa o botao "Pausar captura" para suspender graficos/CSV sem parar os ACKs;
  "Retomar captura" reativa a captura.

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
- Cada linha inclui cansat_id para distinguir os dados dos cinco CanSats.
- Pasta de destino: ~/cansat-cpp/dados_voo/
