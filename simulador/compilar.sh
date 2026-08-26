#!/bin/bash
# Script para compilar o simulador C++ do CanSat

cd ~/cansat-cpp/simulador || exit

echo "⚙️ A compilar simulador.cpp..."
g++ simulador.cpp -o simulador

if [ $? -eq 0 ]; then
    echo "✅ Compilação concluída com sucesso! Podes executar com './simulador'"
else
    echo "❌ Erro na compilação."
fi
