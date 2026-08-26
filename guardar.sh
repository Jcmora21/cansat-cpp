#!/bin/bash
# Script para guardar e sincronizar com o GitHub via SSH

cd ~/cansat-cpp || exit

# Configurar URL remoto para SSH
if [ ! -d ".git" ]; then
    echo "⚙️ A inicializar repositório Git local..."
    git init
    git branch -M main
    git remote add origin git@github.com:Jcmora21/cansat-cpp.git
else
    git remote set-url origin git@github.com:Jcmora21/cansat-cpp.git
fi

# Pedir mensagem de commit
read -p "💬 Mensagem do commit (pressiona Enter para 'Atualização do projeto'): " msg
if [ -z "$msg" ]; then
    msg="Atualização do projeto CanSat C++/Qt"
fi

echo "📦 A preparar e guardar ficheiros..."
git add .
git commit -m "$msg"

echo "🔄 A sincronizar alterações do GitHub..."
git pull origin main --rebase

echo "🚀 A enviar alterações para o GitHub via SSH..."
git push -u origin main

echo "✅ Alterações guardadas com sucesso!"
