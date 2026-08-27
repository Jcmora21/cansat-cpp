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

```text
cansat-cpp/
├── groundstation_clean.py   # Servidor HTTP/WebSocket da Estação de Solo em Python
├── guardar.sh              # Script auxiliar para automação
├── entrar.sh               # Script de inicialização da ponte Termux/Ubuntu
├── dados_voo/              # Pasta onde são gravados os ficheiros de telemetria .csv
└── simulador/
    ├── simulador.cpp       # Código-fonte do simulador de voo em C++
    └── compilar.sh         # Script para compilação do simulador
