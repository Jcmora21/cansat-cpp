#!/bin/bash

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

SOCKET_LIBS=()
case "$(uname -s)" in
    MINGW*|MSYS*|CYGWIN*) SOCKET_LIBS=(-lws2_32) ;;
esac

echo "A compilar simulador.cpp..."

if g++ -std=c++17 -O2 -Wall -Wextra simulador.cpp -o simulador -pthread "${SOCKET_LIBS[@]}"; then
    echo "Compilacao concluida. Executa com './simulador'."
else
    echo "Erro na compilacao."
    exit 1
fi
