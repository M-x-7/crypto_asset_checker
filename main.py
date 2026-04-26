"""
量化交易系統 — 第一層：餘額查詢
用法：
  python main.py                    顯示交易所餘額 + .env 設定的冷錢包
  python main.py --image            額外輸出 HTML 報告和 PNG 圖片到 output/
  python main.py --wallet 0xABC...  臨時查詢單一 EVM 地址（所有鏈）
  python main.py --wallet 0xABC... --chain ethereum

.env 設定：
  EVM_WALLET=0xABC...,0xDEF...   多個 EVM 地址逗號分隔
  BTC_WALLET=bc1q...,1A2B...     多個 BTC 地址逗號分隔
  OKX_PROJECT_ID=...             OKX Web3 DeFi 查詢
  DEBANK_KEY=...                 DeBank DeFi 查詢（備用）
"""

import argparse
import datetime
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table
from rich import box

from src.display.renderer import (
    render_btc_balances,
    render_defi_positions,
    render_exchange_balances,
    render_token_balances,
    render_wallet_balances,
)
from src.exchanges.client import get_all_balances, get_exchange_instance
from src.utils.valuation import get_usd_prices, get_twd_rate
from src.wallet.btc import get_all_btc_balances
from src.wallet.okx_defi import get_defi_positions as okx_get_defi, is_configured as okx_defi_configured
from src.wallet.okx_portfolio import scrape_defi_positions_batch
from src.wallet.evm import get_all_native_balances, get_native_balance, list_chains, validate_address
from src.report.html_builder import build_html, build_summary_html
from playwright.sync_api import sync_playwright as _pw

_OUTPUT_DIR = Path(__file__).parent / "output"

load_dotenv()

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

console = Console()


def _get_valuation(symbols: list[str]) -> tuple[dict[str, float], float]:
    exchange = get_exchange_instance("binance") or get_exchange_instance("okx")
    prices = get_usd_prices(symbols, exchange) if exchange else {}
    twd_rate = get_twd_rate()
    return prices, twd_rate


def _parse_addresses(env_key: str) -> list[str]:
    raw = os.getenv(env_key, "").strip()
    if not raw:
        return []
    return [a.strip().strip('"').strip("'") for a in raw.split(",") if a.strip().strip('"').strip("'")]


# ---------------------------------------------------------------------------
# Data collection (returns structured snapshot dict for both terminal + image)
# ---------------------------------------------------------------------------

def collect_snapshot(
    wallet_override: str | None,
    chain: str | None,
    twd_rate: float,
) -> dict:
    """Collect all portfolio data into a single snapshot dict."""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    snapshot: dict = {
        "timestamp": now,
        "twd_rate": twd_rate,
        "exchanges": {},
        "prices": {},
        "evm_wallets": [],
        "btc_wallets": [],
        "btc_price": 0.0,
        "grand_total_usd": 0.0,
    }

    # --- Exchanges ---
    if not wallet_override:
        with console.status("[cyan]查詢交易所餘額...[/cyan]"):
            all_balances = get_all_balances()
            all_assets = {
                asset
                for balances in all_balances.values()
                if "_error" not in balances
                for asset in balances
            }
            prices: dict[str, float] = {}
            if all_assets:
                exchange = get_exchange_instance("binance") or get_exchange_instance("okx")
                if exchange:
                    prices = get_usd_prices(list(all_assets), exchange)

        snapshot["exchanges"] = all_balances
        snapshot["prices"] = prices
        snapshot["grand_total_usd"] += sum(
            amount * prices.get(asset, 0)
            for balances in all_balances.values()
            if "_error" not in balances
            for asset, amount in balances.items()
            if amount and amount > 0
        )

    # --- EVM wallets ---
    evm_addrs = [wallet_override] if wallet_override else _parse_addresses("EVM_WALLET")
    if evm_addrs:
        with console.status("[cyan]取得 EVM 估值匯率...[/cyan]"):
            evm_prices, _ = _get_valuation(["ETH", "BNB", "MATIC"])

        checksums: list[str] = []
        for addr in evm_addrs:
            try:
                checksums.append(validate_address(addr.strip()))
            except ValueError as e:
                console.print(f"[red]{e}[/red]")

        if checksums:
            scraped: dict[str, dict] = {}
            with console.status("[cyan]查詢代幣與 DeFi 持倉（啟動瀏覽器）...[/cyan]"):
                try:
                    scraped = scrape_defi_positions_batch(checksums)
                    for checksum in checksums:
                        if not scraped.get(checksum, {}).get("protocols"):
                            if okx_defi_configured():
                                scraped.setdefault(checksum, {})["protocols"] = okx_get_defi(checksum)
                except Exception as e:
                    console.print(f"[red]OKX Portfolio 查詢失敗: {e}[/red]")

            for checksum in checksums:
                if chain:
                    with console.status(f"[cyan]查詢 {checksum[:8]}... 在 {chain}...[/cyan]"):
                        chain_results = [get_native_balance(checksum, chain)]
                else:
                    with console.status(f"[cyan]查詢 {checksum[:8]}... 所有鏈...[/cyan]"):
                        chain_results = get_all_native_balances(checksum)

                # Attach USD to each chain result
                for r in chain_results:
                    if r.get("balance") and evm_prices.get(r["symbol"]):
                        r["usd"] = r["balance"] * evm_prices[r["symbol"]]

                wallet_data = scraped.get(checksum, {})
                protocols = wallet_data.get("protocols", [])
                tokens: list[dict] = wallet_data.get("tokens", [])

                wallet_usd = sum(r.get("usd", 0) for r in chain_results)
                defi_usd = sum(p["net_usd_value"] for p in protocols)
                token_usd = sum(t["usd_value"] for t in tokens)
                snapshot["grand_total_usd"] += wallet_usd + defi_usd + token_usd
                snapshot["evm_wallets"].append({
                    "address": checksum,
                    "chain_results": chain_results,
                    "defi_protocols": protocols,
                    "evm_prices": evm_prices,
                    "tokens": tokens,
                })

    # --- BTC wallets ---
    btc_addrs = [] if wallet_override else _parse_addresses("BTC_WALLET")
    if btc_addrs:
        with console.status("[cyan]查詢 BTC 錢包...[/cyan]"):
            btc_results = get_all_btc_balances(btc_addrs)
            btc_prices, _ = _get_valuation(["BTC"])
        btc_price = btc_prices.get("BTC", 0.0)
        btc_total = sum((r.get("balance") or 0) * btc_price for r in btc_results if not r.get("error"))
        snapshot["btc_wallets"] = btc_results
        snapshot["btc_price"] = btc_price
        snapshot["grand_total_usd"] += btc_total

    return snapshot


# ---------------------------------------------------------------------------
# Terminal rendering
# ---------------------------------------------------------------------------

def render_snapshot_terminal(snapshot: dict) -> None:
    twd_rate = snapshot["twd_rate"]
    prices = snapshot["prices"]

    # Exchanges
    if snapshot["exchanges"]:
        console.print()
        render_exchange_balances(snapshot["exchanges"], prices or None, twd_rate)

    # EVM wallets
    for w in snapshot["evm_wallets"]:
        evm_prices = w.get("evm_prices", {})
        console.print()
        render_wallet_balances(w["address"], w["chain_results"], evm_prices, twd_rate)
        if w.get("tokens"):
            console.print()
            render_token_balances(w["address"], w["tokens"], twd_rate)
        console.print()
        render_defi_positions(w["address"], w["defi_protocols"], twd_rate)

    # BTC wallets
    if snapshot["btc_wallets"]:
        btc_prices = {"BTC": snapshot["btc_price"]}
        console.print()
        render_btc_balances(snapshot["btc_wallets"], btc_prices, twd_rate)

    # Grand total
    total = snapshot["grand_total_usd"]
    console.print()
    table = Table(box=box.HEAVY, show_header=False, padding=(0, 1))
    table.add_column(style="bold white", min_width=12)
    table.add_column(justify="right", min_width=18)
    table.add_column(justify="right", min_width=18)
    table.add_row(
        "總資產",
        f"[bold green]$ {total:>14,.2f}[/bold green]",
        f"[bold yellow]NT$ {total * twd_rate:>12,.0f}[/bold yellow]",
    )
    console.print(table)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="量化交易系統第一層：餘額查詢",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--wallet", metavar="ADDRESS", help="臨時查詢單一 EVM 地址")
    parser.add_argument("--chain", metavar="CHAIN",
                        help=f"指定鏈（可用: {', '.join(list_chains())}）")
    parser.add_argument("--image", action="store_true",
                        help="輸出摘要 + 完整明細圖片到 output/")
    args = parser.parse_args()

    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    console.print(f"[dim]查詢時間：{now}[/dim]\n")

    with console.status("[cyan]取得匯率...[/cyan]"):
        twd_rate = get_twd_rate()

    snapshot = collect_snapshot(args.wallet, args.chain, twd_rate)
    render_snapshot_terminal(snapshot)

    if args.image:
        console.print()
        with console.status("[cyan]產生摘要圖片...[/cyan]"):
            html = build_summary_html(snapshot)
            _OUTPUT_DIR.mkdir(exist_ok=True)
            ts2 = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            png_path = _OUTPUT_DIR / f"{ts2}_summary.png"
            with _pw() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page(viewport={"width": 520, "height": 800})
                page.set_content(html, wait_until="networkidle")
                page.wait_for_timeout(800)
                w = page.evaluate("document.documentElement.scrollWidth")
                h = page.evaluate("Math.ceil(document.body.getBoundingClientRect().bottom)")
                page.screenshot(path=str(png_path), clip={"x": 0, "y": 0, "width": w, "height": h})
                browser.close()
        console.print(f"[green]✓ 摘要 PNG:[/green]  {png_path}")
        with console.status("[cyan]產生明細 HTML...[/cyan]"):
            html = build_html(snapshot)
            _OUTPUT_DIR.mkdir(exist_ok=True)
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            detail_html_path = _OUTPUT_DIR / f"{ts}_detail.html"
            detail_html_path.write_text(html, encoding="utf-8")
        console.print(f"[green]✓ 明細 HTML:[/green] {detail_html_path}")


if __name__ == "__main__":
    main()
