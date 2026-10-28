====================================================================
               CANSAT GROUND STATION & SIMULATOR (WINDOWS)
====================================================================

Este projeto contem a Ground Station multicansat e um simulador C++
que representa cinco CanSats. A comunicacao usa o protocolo CANSAT-TLM
v1 sobre UDP em 127.0.0.1:5005, com CRC32, ACKs e retransmissoes.

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
  pasta dados_voo\.
- Pausa da captura: suspende graficos e CSV, mas mantem a rececao,
  validacao e os ACKs ativos. Os pacotes recebidos durante a pausa
  nao sao guardados.
- Historico limitado a 2000 amostras para controlar o uso de memoria.
- Exportacao de Dados: Descarga direta do historico em .csv ou
  captura em imagem .png dos graficos.

--------------------------------------------------------------------
2. ESTRUTURA DO PROJETO
--------------------------------------------------------------------

cansat-cpp\
├── groundstation.py        # Ground Station multicansat UDP
├── iniciar_cansat.bat      # Compila, inicia a GS e pergunta quando iniciar o simulador
├── FORMATO_TELEMETRIA.txt  # Estrutura e exemplo CANSAT-TLM v1
├── dados_voo\              # CSV de cada sessao, com cansat_id
└── simulador\
    ├── simulador.cpp       # Simulador multicansat com ACK/retransmissao
    ├── compilar.bat        # Compilacao Windows (g++ / Winsock)
    └── iniciar_simulador.bat # Arranque com as DLLs do MSYS2 no PATH

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

Instalacao da dependencia Python:
  py -3 -m pip install websockets

Se for necessario criar um ambiente virtual (venv):
  py -3 -m venv .venv
  .venv\Scripts\activate
  python -m pip install websockets
O iniciar_cansat.bat usa o venv ativo ou .venv\ automaticamente, se existir.

--------------------------------------------------------------------
4. COMO EXECUTAR O SISTEMA
--------------------------------------------------------------------

A Ground Station deve estar ativa antes de iniciar o simulador. O ficheiro
iniciar_cansat.bat compila o simulador, inicia groundstation.py, abre o painel
e pergunta quando queres arrancar os cinco CanSats.

Opcao automatica (recomendada), a partir da pasta do projeto:
  iniciar_cansat.bat

Para controlar cada etapa manualmente:

PASSO 1: Iniciar a Estacao de Solo (Terminal 1 - PowerShell/CMD)
-----------------------------------------------------------------
Executa o comando:
  py -3 groundstation.py

- Servidores iniciados: UDP (5005), WebSocket (8051) e Web (8050).
- Acede no navegador web ao endereco: http://127.0.0.1:8050

PASSO 2: Compilar e Iniciar o Simulador (Terminal 2 - PowerShell/CMD)
----------------------------------------------------------------------
Abre um segundo terminal e executa:
  cd simulador
  compilar.bat
  iniciar_simulador.bat

(O script de compilacao liga automaticamente a biblioteca Winsock -lws2_32.)

- O simulador gera dados para cinco CanSats e envia-os via UDP.
- A Ground Station valida o CRC32, confirma cada pacote valido com ACK,
  deteta duplicados/pacotes em falta e exporta o cansat_id para o CSV.
- Acompanha os graficos em tempo real no navegador.
- O botao "Pausar captura" suspende graficos e CSV sem interromper os ACKs;
  "Retomar captura" reativa a captura.

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
- Cada linha inclui cansat_id para distinguir os dados dos cinco CanSats.
- Pasta de destino: .\dados_voo\
