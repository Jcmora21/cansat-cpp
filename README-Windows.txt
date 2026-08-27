====================================================================
               CANSAT GROUND STATION & SIMULATOR (WINDOWS)
====================================================================

Este projeto contem a Estacao de Solo (Ground Station) e o Simulador
de Voo desenvolvidos em Python e C++ para monitorizacao de telemetria
em tempo real de um projeto CanSat/Minifoguete.

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
- Exportacao de Dados: Descarga direta do historico em .csv ou
  captura em imagem .png dos graficos.

--------------------------------------------------------------------
2. ESTRUTURA DO PROJETO
--------------------------------------------------------------------

cansat-cpp\
├── groundstation_clean.py   # Servidor HTTP/WebSocket da Ground Station
├── guardar.bat             # Script auxiliar para automacao (Windows)
├── dados_voo\              # Pasta onde sao gravados os ficheiros .csv
└── simulador\
    ├── simulador.cpp       # Codigo-fonte do simulador em C++
    └── compilar.bat        # Script para compilacao no Windows (g++)

--------------------------------------------------------------------
3. REQUISITOS E DEPENDENCIAS (WINDOWS)
--------------------------------------------------------------------

No Windows (PowerShell ou CMD), garante que tens instalado:

1. Python (marcar a opcao "Add Python to PATH" na instalacao):
   https://www.python.org/downloads/

2. Compilador C++ (g++ via MinGW / w64devkit):
   Garante que o comando g++ esta acessivel no terminal.

Instalacao de dependencias Python:
  pip install websockets

Se for necessario criar um ambiente virtual (venv):
  python -m venv .venv
  .venv\Scripts\activate

--------------------------------------------------------------------
4. COMO EXECUTAR O SISTEMA
--------------------------------------------------------------------

A Estacao de Solo deve ser SEMPRE iniciada antes do Simulador.

PASSO 1: Iniciar a Estacao de Solo (Terminal 1 - PowerShell/CMD)
-----------------------------------------------------------------
Executa o comando:
  python groundstation_clean.py

- Servidores iniciados: UDP (5005), WebSocket (8051) e Web (8050).
- Acede no navegador web ao endereco: http://127.0.0.1:8050

PASSO 2: Compilar e Iniciar o Simulador (Terminal 2 - PowerShell/CMD)
----------------------------------------------------------------------
Abre um segundo terminal e executa:
  cd simulador
  g++ simulador.cpp -o simulador.exe -lws2_32
  .\simulador.exe

(Nota: No Windows, para sockets em C++, e necessario compilar com -lws2_32).

- O simulador gera os dados e envia-os via UDP para a Ground Station.
- Acompanha os graficos em tempo real no navegador.

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
- Pasta de destino: .\dados_voo\
