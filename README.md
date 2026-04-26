# crypto 資產查詢

加密資產總覽工具，支援中心化交易所（Binance、OKX）、EVM 多鏈冷錢包、BTC 冷錢包、DeFi 持倉，並可透過 Telegram Bot 隨時查詢。

---

## 功能

- **交易所餘額**：Binance、OKX，含 Spot、Earn 子帳戶，USD / TWD 估值
- **EVM 冷錢包**：Ethereum、BNB Chain、Polygon 原生幣餘額
- **BTC 冷錢包**：支援 P2PKH（`1...`）、P2SH（`3...`）、Bech32（`bc1...`）
- **DeFi 持倉**：透過 OKX Web3 Portfolio 爬蟲取得持倉明細
- **HTML 報告**：深色主題、手機友善，可匯出摘要 PNG + 完整明細 HTML
- **Telegram Bot**：一鍵查詢，自動回傳 PNG 摘要與 HTML 明細

---

## 需求

- Python 3.11 以上
- Windows：直接執行 `setup.bat`
- Linux / macOS：執行 `setup.sh`

---

## 安裝

```bash
# Windows
setup.bat

# Linux / macOS
bash setup.sh
```

腳本會自動：
1. 建立 `.venv` 虛擬環境
2. 安裝所有相依套件
3. 下載 Playwright Chromium（用於 DeFi 持倉爬蟲與 PNG 截圖）

---

## 設定

複製範本並填入金鑰：

```bash
cp .env.example .env
```

`.env` 各欄位說明：

| 欄位 | 說明 |
|------|------|
| `BINANCE_API_KEY` / `BINANCE_SECRET` | Binance API 金鑰（僅需 Read 權限） |
| `OKX_API_KEY` / `OKX_SECRET` / `OKX_PASSPHRASE` | OKX API 金鑰（僅需 Read 權限） |
| `EVM_WALLET` | EVM 錢包地址，多個以逗號分隔 |
| `BTC_WALLET` | BTC 錢包地址，多個以逗號分隔 |
| `ETH_RPC_URL` / `BSC_RPC_URL` / `POLYGON_RPC_URL` | 自訂 RPC 節點（選填，不填使用免費公共節點） |
| `TELEGRAM_BOT_TOKEN` | Telegram Bot Token（從 @BotFather 取得） |
| `TELEGRAM_ALLOWED_CHAT_IDS` | 限制可使用 Bot 的 Chat ID，留空表示不限制 |

> API 金鑰只需要查詢（Read）權限，**不需要**下單或提幣權限。

---

## 使用

### CLI 查詢

```bash
# 啟動虛擬環境
.venv\Scripts\Activate.ps1        # Windows
source .venv/bin/activate          # Linux / macOS

# 顯示所有交易所餘額與 .env 設定的冷錢包
python main.py

# 同上，並額外輸出摘要 PNG 與明細 HTML 到 output/
python main.py --image

# 臨時查詢指定 EVM 地址（所有鏈）
python main.py --wallet 0xABC...

# 只查詢特定鏈
python main.py --wallet 0xABC... --chain ethereum

# 查看可用鏈名稱
python main.py --help
```

### Telegram Bot

```bash
.venv\Scripts\python -m src.telegram_bot.bot
```

Bot 指令：

| 指令 | 說明 |
|------|------|
| `/asset` | 查詢全部資產，回傳摘要 PNG + 明細 HTML |

---

## 切換第三方服務節點

所有外部 API 節點集中在 `config/endpoints.yaml`，不需修改程式碼即可切換供應商：

```yaml
services:
  fx_rate_url: "https://open.er-api.com/v6/latest/USD"   # 可換其他匯率 API
  btc_explorer_url: "https://blockstream.info/api/address/{}"  # 可換 mempool.space
  okx_portfolio_url: "https://web3.okx.com/zh-hant/portfolio/{}/analysis"
```

EVM RPC 節點預設使用 [publicnode.com](https://publicnode.com) 免費節點，生產環境建議改用 Infura 或 Alchemy（在 `.env` 填入對應的 `*_RPC_URL`）。

---

## 新增 EVM 鏈

在 `config/endpoints.yaml` 的 `chains:` 區塊新增一條：

```yaml
arbitrum:
  name: Arbitrum One
  symbol: ETH
  rpc: https://arbitrum-one.publicnode.com
  env_rpc: ARB_RPC_URL
```

存檔後立即生效，不需修改任何 Python 程式碼。

---

## 專案結構

```
├── main.py                  # CLI 入口
├── config/
│   └── endpoints.yaml       # 第三方服務節點（統一管理）
├── src/
│   ├── exchanges/
│   │   └── client.py        # Binance、OKX 餘額查詢（ccxt）
│   ├── wallet/
│   │   ├── evm.py           # EVM 多鏈原生幣查詢（web3.py）
│   │   ├── btc.py           # BTC 餘額查詢（Blockstream API）
│   │   ├── okx_portfolio.py # DeFi 持倉爬蟲（Playwright）
│   │   └── okx_defi.py      # OKX DeFi REST API（需 OKX API 金鑰）
│   ├── report/
│   │   └── html_builder.py  # HTML / PNG 報告產生
│   ├── display/
│   │   └── renderer.py      # Rich 終端機表格
│   ├── telegram_bot/
│   │   └── bot.py           # Telegram Bot
│   └── utils/
│       ├── config.py        # endpoints.yaml 載入器
│       └── valuation.py     # 匯率與 USD 估值
├── setup.bat                # Windows 一鍵建環境
├── setup.sh                 # Linux / macOS 一鍵建環境
└── .env.example             # 環境變數範本
```

---

## 授權

MIT License
