from rich.console import Console
from rich.table import Table
from rich import box

console = Console()

_MAX_TOKENS_PER_ROW = 4


def render_exchange_balances(
    all_balances: dict[str, dict],
    prices: dict[str, float] | None = None,
    twd_rate: float | None = None,
) -> None:
    if not all_balances:
        console.print("[yellow]未配置任何交易所 API 金鑰[/yellow]")
        return

    for exchange_id, balances in all_balances.items():
        title = f"交易所帳戶餘額  [{exchange_id.upper()}]"

        if "_error" in balances:
            console.print(f"[red][{exchange_id}] 錯誤: {balances['_error']}[/red]")
            continue

        if not balances:
            console.print(f"[dim][{exchange_id}] 餘額為空[/dim]")
            continue

        show_valuation = bool(prices and twd_rate)

        table = Table(title=title, box=box.ROUNDED, show_lines=False)
        table.add_column("資產", style="cyan", min_width=8)
        table.add_column("數量", justify="right", min_width=18)
        if show_valuation:
            table.add_column("≈ USD", justify="right", min_width=14)
            table.add_column("≈ TWD", justify="right", min_width=14)

        total_usd = 0.0
        rows = []
        for asset, amount in sorted(balances.items()):
            usd_val = amount * prices.get(asset, 0) if prices else None
            if usd_val:
                total_usd += usd_val
            rows.append((asset, amount, usd_val))

        for asset, amount, usd_val in rows:
            if show_valuation:
                usd_str = f"${usd_val:,.2f}" if usd_val else "—"
                twd_str = f"NT${usd_val * twd_rate:,.0f}" if usd_val and twd_rate else "—"
                table.add_row(asset, f"{amount:.8f}", usd_str, twd_str)
            else:
                table.add_row(asset, f"{amount:.8f}")

        if show_valuation and total_usd > 0:
            table.add_section()
            table.add_row(
                "[bold]總計[/bold]",
                "",
                f"[bold green]${total_usd:,.2f}[/bold green]",
                f"[bold green]NT${total_usd * twd_rate:,.0f}[/bold green]",
            )

        console.print(table)


def render_wallet_balances(
    address: str,
    chain_results: list[dict],
    prices: dict[str, float] | None = None,
    twd_rate: float | None = None,
) -> None:
    short_addr = f"{address[:6]}...{address[-4:]}"
    title = f"EVM 冷錢包  {short_addr}"
    show_val = bool(prices and twd_rate)

    table = Table(title=title, box=box.ROUNDED, show_lines=False)
    table.add_column("鏈", style="cyan", min_width=12)
    table.add_column("資產", style="white", min_width=8)
    table.add_column("數量", justify="right", min_width=18)
    if show_val:
        table.add_column("≈ USD", justify="right", min_width=14)
        table.add_column("≈ TWD", justify="right", min_width=14)

    total_usd = 0.0
    for r in chain_results:
        if r.get("error"):
            row = [r["chain"], r["symbol"], f"[red]錯誤: {r['error']}[/red]"]
            if show_val:
                row += ["—", "—"]
            table.add_row(*row)
        else:
            balance = r["balance"] or 0.0
            balance_str = f"{balance:.8f}"
            if show_val:
                usd = balance * prices.get(r["symbol"], 0)
                total_usd += usd
                usd_str = f"${usd:,.2f}" if usd else "—"
                twd_str = f"NT${usd * twd_rate:,.0f}" if usd and twd_rate else "—"
                table.add_row(r["chain"], r["symbol"], balance_str, usd_str, twd_str)
            else:
                table.add_row(r["chain"], r["symbol"], balance_str)

    if show_val and total_usd > 0:
        table.add_section()
        table.add_row(
            "[bold]總計[/bold]", "", "",
            f"[bold green]${total_usd:,.2f}[/bold green]",
            f"[bold green]NT${total_usd * twd_rate:,.0f}[/bold green]",
        )

    console.print(table)


def render_defi_positions(address: str, protocols: list[dict], twd_rate: float | None = None) -> None:
    if not protocols:
        console.print("[dim]無 DeFi 持倉[/dim]")
        return

    short_addr = f"{address[:6]}...{address[-4:]}"
    total_usd = sum(p["net_usd_value"] for p in protocols)

    table = Table(title=f"DeFi 持倉  {short_addr}", box=box.ROUNDED, show_lines=False)
    table.add_column("協議", style="cyan", min_width=16)
    table.add_column("類型", style="white", min_width=12)
    table.add_column("資產", style="white", min_width=18)
    table.add_column("≈ USD", justify="right", min_width=14)
    if twd_rate:
        table.add_column("≈ TWD", justify="right", min_width=14)

    for p in protocols:
        first = True
        for item in p["items"]:
            visible = [t for t in item["tokens"] if t["amount"] > 0]
            parts = [f"{t['symbol']} {t['amount']:.4f}" for t in visible[:_MAX_TOKENS_PER_ROW]]
            if len(visible) > _MAX_TOKENS_PER_ROW:
                parts.append(f"+{len(visible) - _MAX_TOKENS_PER_ROW} 更多")
            token_str = "  ".join(parts) or "—"

            usd_str = f"${item['usd_value']:,.2f}"
            twd_str = f"NT${item['usd_value'] * twd_rate:,.0f}" if twd_rate else None
            row = [p["protocol"] if first else "", item["name"], token_str, usd_str]
            if twd_rate:
                row.append(twd_str)
            table.add_row(*row)
            first = False

    table.add_section()
    total_row = ["[bold]總計[/bold]", "", "", f"[bold green]${total_usd:,.2f}[/bold green]"]
    if twd_rate:
        total_row.append(f"[bold green]NT${total_usd * twd_rate:,.0f}[/bold green]")
    table.add_row(*total_row)
    console.print(table)


def render_btc_balances(
    results: list[dict],
    prices: dict[str, float] | None = None,
    twd_rate: float | None = None,
) -> None:
    show_val = bool(prices and twd_rate)
    table = Table(title="BTC 冷錢包", box=box.ROUNDED, show_lines=False)
    table.add_column("地址", style="cyan", min_width=16)
    table.add_column("資產", style="white", min_width=6)
    table.add_column("數量", justify="right", min_width=18)
    if show_val:
        table.add_column("≈ USD", justify="right", min_width=14)
        table.add_column("≈ TWD", justify="right", min_width=14)

    total_usd = 0.0
    for r in results:
        addr = r["address"]
        short = f"{addr[:8]}...{addr[-6:]}"
        if r.get("error"):
            row = [short, "BTC", f"[red]錯誤: {r['error']}[/red]"]
            if show_val:
                row += ["—", "—"]
            table.add_row(*row)
        else:
            balance = r["balance"] or 0.0
            if show_val:
                usd = balance * prices.get("BTC", 0)
                total_usd += usd
                usd_str = f"${usd:,.2f}" if usd else "—"
                twd_str = f"NT${usd * twd_rate:,.0f}" if usd and twd_rate else "—"
                table.add_row(short, "BTC", f"{balance:.8f}", usd_str, twd_str)
            else:
                table.add_row(short, "BTC", f"{balance:.8f}")

    if show_val and total_usd > 0:
        table.add_section()
        table.add_row(
            "[bold]總計[/bold]", "", "",
            f"[bold green]${total_usd:,.2f}[/bold green]",
            f"[bold green]NT${total_usd * twd_rate:,.0f}[/bold green]",
        )

    console.print(table)
