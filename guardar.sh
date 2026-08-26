#!/bin/bash
# Script para guardar e sincronizar com o repositório Git

cd ~/cansat-cpp || exit

# Verificar se o Git já está inicializado
if [ ! -d ".git" ]; then
    echo "⚙️ A inicializar repositório Git local..."
    git init
    git branch -M main
    git remote add origin https://github.com/Jcmora21/cansat-cpp.git
else
    # Garante que o remote está correto mesmo se já existir .git
    git remote set-url origin https://github.com/Jcmora21/cansat-cpp.git
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

echo "✅ Alterações guardadas com sucesso no repositório!"
