#!/bin/bash
# Script para guardar e sincronizar com o novo repositório Git

cd ~/cansat-cpp || exit

# Verificar se o Git já está inicializado
if [ ! -d ".git" ]; then
    echo "⚙️ A inicializar repositório Git local..."
    git init
    git branch -M main
    
    read -p "🔗 Cole o URL do NOVO repositório GitHub (ex: https://github.com/utilizador/cansat-cpp.git): " repo_url
    git remote add origin "$repo_url"
fi

# Pedir mensagem de commit
read -p "💬 Mensagem do commit (pressiona Enter para 'Atualização do projeto'): " msg
if [ -z "$msg" ]; then
    msg="Atualização do projeto CanSat C++/Qt"
fi

echo "📦 A preparar e guardar ficheiros..."
git add .
git commit -m "$msg"

echo "🚀 A enviar alterações para o GitHub..."
git push -u origin main

echo "✅ Alterações guardadas com sucesso no novo repositório!"
