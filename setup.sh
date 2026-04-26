#!/usr/bin/env bash
set -euo pipefail

echo "============================================"
echo " crypto 資產查詢  setup"
echo "============================================"
echo

# ── 如果 .venv 已存在，詢問是否重建 ────────────────
if [ -d ".venv" ]; then
    read -rp "虛擬環境已存在，是否重建？[y/N] " REBUILD
    if [[ "${REBUILD,,}" == "y" ]]; then
        echo "移除舊的 .venv..."
        rm -rf .venv
    fi
fi

if [ ! -d ".venv" ]; then
    echo "[1/4] 建立虛擬環境..."
    python3 -m venv .venv
else
    echo "[1/4] 沿用現有虛擬環境。"
fi

echo "[2/4] 更新 pip..."
.venv/bin/python -m pip install --upgrade pip -q

echo "[3/4] 安裝相依套件..."
.venv/bin/pip install . -q
rm -rf *.egg-info build

echo "[4/4] 安裝 Playwright 瀏覽器（Chromium）..."
.venv/bin/playwright install chromium

echo
echo "============================================"
echo " 安裝完成！"
echo "============================================"
echo
echo "接下來："
echo "  1. 複製 .env.example 為 .env 並填入 API 金鑰"
echo "  2. 執行查詢：  .venv/bin/python main.py"
echo "  3. 啟動機器人：.venv/bin/python -m src.telegram_bot.bot"
echo
echo "常用參數："
echo "  python main.py                          顯示所有餘額"
echo "  python main.py --image                  同上，輸出 PNG + HTML 到 output/"
echo "  python main.py --wallet 0xABC...        查詢指定 EVM 地址"
echo "  python main.py --wallet 0xABC... --chain ethereum"
echo "  python main.py --help                   顯示可用鏈名稱"
echo
