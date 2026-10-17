#!/usr/bin/env bash
# ============================================================================
# Ева — установка на сервер.
#
# Запускать из корня распакованного архива (релиза):
#   curl -L -o eva.tar.xz <url>
#   tar -xJf eva.tar.xz && cd eva && ./install.sh
#
# Что делает: ставит окружение (python/uv/ffmpeg/node через pm), создаёт
# лаунчер `eva`, кладёт шаблоны PERSONA.md / config.yaml / .env в дом.
# Повторный запуск безопасен — существующие файлы не перезаписываются.
# ============================================================================
set -euo pipefail

EVA_HOME="${EVA_HOME:-$HOME/eva-home}"
RUNTIME_DIR="${EVA_RUNTIME_DIR:-$EVA_HOME/tools}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

GREEN='\033[0;32m'; CYAN='\033[0;36m'; YELLOW='\033[0;33m'; RED='\033[0;31m'; NC='\033[0m'

echo ""
echo -e "${CYAN}☤ Ева — установка${NC}"
echo ""
echo -e "  дом персоны:  ${GREEN}$EVA_HOME${NC}"
echo -e "  тулчейн:      ${GREEN}$RUNTIME_DIR${NC}"
echo ""

# 1. Зависимости
for bin in git curl tar; do
    if ! command -v "$bin" >/dev/null 2>&1; then
        echo -e "${RED}✗ нет $bin — поставь сначала (apt install git curl tar)${NC}" >&2
        exit 1
    fi
done

# 2. Окружение (python, uv, ffmpeg, node + зависимости через pm).
#    Первый прогон на свежем сервере качает ~2 ГБ, занимает 1–5 минут.
echo -e "${CYAN}→${NC} Собираю окружение (первый раз — несколько минут)..."
HERMES_HOME="$EVA_HOME" HERMES_RUNTIME_DIR="$RUNTIME_DIR" ./setup-hermes.sh

# 3. Лаунчер `eva`. Ищем бинарь hermes: сначала в форке, потом общий.
HERMES_BIN=""
for cand in "$SCRIPT_DIR/.hermes/bin/hermes" "$HOME/.local/bin/hermes"; do
    if [ -x "$cand" ]; then HERMES_BIN="$cand"; break; fi
done
if [ -z "$HERMES_BIN" ]; then
    echo -e "${RED}✗ не нашёл бинарь hermes после установки${NC}" >&2
    exit 1
fi
mkdir -p "$HOME/.local/bin"
cat > "$HOME/.local/bin/eva" <<EOF
#!/bin/sh
export HERMES_HOME="$EVA_HOME"
exec "$HERMES_BIN" "\$@"
EOF
chmod +x "$HOME/.local/bin/eva"
echo -e "${GREEN}✓${NC} лаунчер создан: $HOME/.local/bin/eva"

# 4. Шаблоны персоны в дом (существующие не трогаем).
mkdir -p "$EVA_HOME"
if [ ! -f "$EVA_HOME/PERSONA.md" ]; then
    cp examples/persona.example.md "$EVA_HOME/PERSONA.md"
    echo -e "${GREEN}✓${NC} PERSONA.md создан из шаблона"
fi
if [ ! -f "$EVA_HOME/config.yaml" ]; then
    cp examples/config.example.yaml "$EVA_HOME/config.yaml"
    echo -e "${GREEN}✓${NC} config.yaml создан из шаблона"
fi
if [ ! -f "$EVA_HOME/.env" ]; then
    cp .env.example "$EVA_HOME/.env"
    chmod 600 "$EVA_HOME/.env" 2>/dev/null || true
    echo -e "${GREEN}✓${NC} .env создан из шаблона (заполни ключи!)"
fi

# 5. Проверка
echo ""
echo -e "${CYAN}→${NC} Проверка..."
if "$HOME/.local/bin/eva" --version >/dev/null 2>&1; then
    echo -e "${GREEN}✓${NC} eva запускается"
else
    echo -e "${YELLOW}!${NC} eva --version вернул ошибку — проверь ключи в $EVA_HOME/.env"
fi

echo ""
echo -e "${GREEN}Готово.${NC} Дальше:"
echo "  1. Заполни ключи в $EVA_HOME/.env  (минимум: TELEGRAM_BOT_TOKEN + ключ модели)"
echo "  2. Поправь $EVA_HOME/PERSONA.md и $EVA_HOME/config.yaml под себя"
echo "  3. Запусти гейтвей:  eva gateway run"
echo ""
echo "  Остановить/посмотреть логи:"
echo "    eva gateway status      # состояние"
echo "    journalctl -u eva-gateway.service -f   # логи (если настроен systemd-юнит)"
echo ""
