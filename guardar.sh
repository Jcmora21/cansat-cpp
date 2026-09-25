#!/bin/bash
# Script para guardar e sincronizar o projeto CanSat com o GitHub via SSH

# Navegar para o diretório do projeto no Termux
cd /data/data/com.termux/files/home/cansat-cpp || exit 1

# Definir comando SSH com a localização exata da tua chave no Termux
export GIT_SSH_COMMAND="ssh -i /data/data/com.termux/files/home/.ssh/id_ed25519"

echo "🚀 A verificar o repositório Git..."

# Configurar URL remoto para SSH
if [ ! -d ".git" ]; then
    echo "📦 A inicializar repositório Git local..."
    git init
    git branch -M main
    git remote add origin git@github.com:Jcmora21/cansat-cpp.git
else
    git remote set-url origin git@github.com:Jcmora21/cansat-cpp.git
fi

# Pedir mensagem de commit
read -p "📝 Mensagem do commit (pressiona Enter para 'Atualização do projeto'): " msg
if [ -z "$msg" ]; then
    msg="Atualização do projeto CanSat C++/Qt"
fi

echo "📥 A preparar e guardar ficheiros..."
git add .
git commit -m "$msg"

echo "🔄 A sincronizar alterações com o GitHub..."
git pull origin main --rebase

echo "📤 A enviar alterações para o GitHub via SSH..."
git push -u origin main

echo "✅ Alterações guardadas com sucesso no GitHub!"
