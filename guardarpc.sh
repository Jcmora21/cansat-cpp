#!/bin/bash

echo "======================================"
echo "       GUARDAR CANSAT NO GITHUB"
echo "======================================"
echo

# Ir para a pasta do projeto
cd ~/cansat-cpp || exit 1

# Garantir que o GitHub usa SSH
git remote set-url origin git@github.com:Jcmora21/cansat-cpp.git

# Iniciar SSH Agent
eval "$(ssh-agent -s)" >/dev/null 2>&1

# Adicionar a chave SSH existente
ssh-add ~/.ssh/id_ed25519 >/dev/null 2>&1

echo "[1/4] Verificando alterações..."
git status
echo

# Adicionar todas as alterações
echo "[2/4] A adicionar alterações..."
git add .

# Verificar se existem alterações para guardar
if git diff --cached --quiet; then
    echo
    echo "Não existem alterações novas para guardar."
    exit 0
fi

echo
echo "[3/4] A fazer commit..."

DATA=$(date "+%Y-%m-%d %H:%M:%S")

git commit -m "Backup $DATA"

if [ $? -ne 0 ]; then
    echo
    echo "ERRO: Não foi possível fazer o commit."
    exit 1
fi

echo
echo "[4/4] A enviar para o GitHub..."

git push origin multi-cansat

if [ $? -ne 0 ]; then
    echo
    echo "ERRO: Não foi possível fazer o push."
    echo "Verifica a ligação SSH ao GitHub."
    exit 1
fi

echo
echo "======================================"
echo "        BACKUP CONCLUIDO!"
echo "======================================"
echo
echo "Branch: multi-cansat"
echo "GitHub: Jcmora21/cansat-cpp"
echo
git status
