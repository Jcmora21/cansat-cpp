# 🚀 CanSat Ground Station & Simulator

Este repositório contém a **Estação de Solo (Ground Station)** e o **Simulador de Voo** desenvolvidos em Python e C++ para monitorização de telemetria em tempo real de um projeto CanSat/Minifoguete.

---

## 📋 Funcionalidades

* **Painel Web em Tempo Real:** Interface desenvolvida em HTML5/JavaScript com gráficos dinâmicos (*Chart.js*) organizados em grelha responsiva (2 por linha).
* **Gestão Inteligente de Fases de Voo:** Deteção de transições de estado (*Espera*, *Subida*, *Apogeu*, *Descida*) com etiquetagem automática e sobreposição inteligente de rótulos na mesma linha vertical.
* **Métricas de Voo e KPIs:** Exibição automática dos valores Mínimo, Máximo e Média no topo de cada gráfico, com painel completo de telemetria em tempo real.
* **Gravação Automática em CSV:** Salvamento instantâneo (*append mode*) de todos os pacotes recebidos na pasta `dados_voo/`, garantindo a persistência contra falhas do sistema.
* **Exportação de Dados:** Descarga direta do histórico em `.csv` ou captura em imagem `.png` de todos os gráficos combinados através do painel.

---

## 📁 Estrutura do Projeto

cansat-cpp/
├── groundstation_clean.py   # Servidor HTTP/WebSocket da Estação de Solo em Python
├── guardar.sh              # Script auxiliar para automação
├── entrar.sh               # Script de inicialização da ponte Termux/Ubuntu
├── dados_voo/              # Pasta onde são gravados os ficheiros de telemetria .csv
└── simulador/
    ├── simulador.cpp       # Código-fonte do simulador de voo em C++
    └── compilar.sh         # Script para compilação do simulador

---

## 🛠️ Requisitos e Dependências

No ambiente Linux/Ubuntu (via Termux/PROOT), garante que tens instaladas as seguintes dependências:

* **Python 3** (com a biblioteca `websockets`):
  pip install websockets
* **Compilador C++ (g++)**:
  apt update && apt install g++ -y

---

## 🚀 Como Executar o Sistema

Para que a telemetria funcione corretamente, **a Estação de Solo deve ser sempre iniciada antes do Simulador**.

### 1. Iniciar a Estação de Solo (Ground Station)
Abre o terminal e executa o servidor da estação de solo:

python3 groundstation_clean.py

* **O que acontece:** O servidor UDP (porta 5005), o servidor WebSocket (porta 8051) e o servidor Web HTTP (porta 8050) são iniciados.
* **Aceder à Interface:** Abre o navegador Web do teu dispositivo e acede ao endereço:
  http://127.0.0.1:8050

---

### 2. Compilar e Iniciar o Simulador de Voo
Abre um **segundo terminal** (mantendo a Ground Station a correr no primeiro) e entra na pasta do simulador:

cd simulador
./compilar.sh
./simulador

* **O que acontece:** O simulador começa a gerar dados físicos de voo (altitude, velocidade, aceleração, pressão, sensores ambientais) e a enviá-los via UDP para a estação de solo.
* **Visualização:** Acompanha os gráficos a serem desenhados em tempo real na página web.

---

## 📖 Guia Prático de Utilização

### Passo a Passo do Teste de Voo:

1. **Abrir dois terminais** (ou duas abas do Termux/Ubuntu).
2. **No Terminal 1:** Arranca a Ground Station (`python3 groundstation_clean.py`).
3. **No Navegador:** Abre a página `http://127.0.0.1:8050`. Vais ver os painéis a zeros, à espera de pacotes.
4. **No Terminal 2:** Vai à pasta `simulador` e executa `./simulador`.
5. **Acompanhar o Voo:**
   * Os gráficos começam a desenhar as curvas em tempo real.
   * As etiquetas das fases do voo (**Subida**, **Apogeu**, **Descida**) aparecem automaticamente nos gráficos à medida que ocorrem as transições.
   * Os KPIs (Máx, Mín, Média) atualizam-se no topo de cada gráfico.
6. **Encerrar a Simulação:**
   * Assim que o CanSat aterrar (ou quando quiseres parar), vai ao **Terminal 2** e clica em `Ctrl + C`.
   * Vai ao **Terminal 1** e clica em `Ctrl + C` para fechar o servidor.
7. **Ver os Dados:** Acede à pasta `dados_voo/` para encontrares o ficheiro `.csv` completo criado durante essa sessão.

---

## 🛑 Como Parar a Execução

### Parar o Simulador
No terminal do simulador, prime `Ctrl + C` para interromper o envio UDP.

### Parar a Estação de Solo
No terminal da Ground Station, prime `Ctrl + C` para fechar os servidores. Os dados gravados no `.csv` continuam salvos em segurança na pasta `dados_voo/`.

---

## 🔧 Resolução de Problemas Rápidos

* **Porta em uso (Address already in use):**
  Se o servidor não arrancar por causa de uma porta ocupada, fecha outros processos em segundo plano com:
  fuser -k 8050/tcp 8051/tcp 5005/udp

---

## 💾 Gestão dos Dados de Voo (.csv)

* Todos os ficheiros gerados são nomeados no formato com carimbo de data/hora:
  `voo_cansat_AAAA-MM-DD_HH-MM-SS.csv`
* Se usas o script `./entrar.sh` a partir do Termux, esta pasta encontra-se sincronizada diretamente com a memória do Termux em `~/cansat-cpp/dados_voo/`.
