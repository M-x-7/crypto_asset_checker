"""
Build a self-contained HTML report from portfolio snapshot data.
"""

from __future__ import annotations

import datetime
import html as _html

def _esc(s: object) -> str:
    return _html.escape(str(s))


def _fmt_usd(v: float | None) -> str:
    if v is None:
        return "—"
    return f"USD${v:,.2f}"


def _fmt_twd(v: float | None, rate: float) -> str:
    if v is None:
        return "—"
    return f"NT${v * rate:,.0f}"


def _fmt_num(v: float | None, decimals: int = 8) -> str:
    if v is None:
        return "—"
    return f"{v:.{decimals}f}"



# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------

def _exchange_section(exchanges: dict[str, dict], prices: dict[str, float], twd_rate: float) -> str:
    """Each exchange rendered as its own sub-card with its own table."""
    cards = ""
    for exchange_id, balances in exchanges.items():
        if "_error" in balances:
            cards += f'<div class="ex-card"><p class="err">{_esc(exchange_id.upper())} 錯誤: {_esc(balances["_error"])}</p></div>'
            continue
        total_usd = 0.0
        main_rows = ""
        small_rows = ""
        small_count = 0
        for asset, amount in sorted(balances.items()):
            if not amount or amount <= 0:
                continue
            usd = amount * prices.get(asset, 0)
            total_usd += usd
            usd_str = _fmt_usd(usd) if usd else "—"
            twd_str = _fmt_twd(usd, twd_rate) if usd else "—"
            row = f"""
              <tr>
                <td class="asset-name">{_esc(asset)}</td>
                <td class="num">{_fmt_num(amount)}</td>
                <td class="num">{usd_str}</td>
                <td class="num">{twd_str}</td>
              </tr>"""
            if usd >= 1.0:
                main_rows += row
            else:
                small_rows += row
                small_count += 1
        if not main_rows and not small_rows:
            continue
        total_row = f"""
              <tr class="total-row">
                <td class="total-label">總計</td>
                <td></td>
                <td class="num pos">{_fmt_usd(total_usd)}</td>
                <td class="num pos">{_fmt_twd(total_usd, twd_rate)}</td>
              </tr>"""
        small_html = ""
        if small_rows:
            small_html = f"""
          <details class="small-assets">
            <summary>小額 / 無估值（{small_count} 種）</summary>
            <div class="table-wrap"><table class="data-table">
              <thead><tr><th>資產</th><th>數量</th><th>≈ USD</th><th>≈ TWD</th></tr></thead>
              <tbody>{small_rows}</tbody>
            </table></div>
          </details>"""
        cards += f"""
        <div class="ex-card">
          <div class="ex-card-header">
            <span class="exchange-badge">{_esc(exchange_id.upper())}</span>
            <span class="ex-total">{_fmt_usd(total_usd)} / {_fmt_twd(total_usd, twd_rate)}</span>
          </div>
          <div class="table-wrap">
            <table class="data-table">
              <thead><tr><th>資產</th><th>數量</th><th>≈ USD</th><th>≈ TWD</th></tr></thead>
              <tbody>{main_rows}{total_row}</tbody>
            </table>
          </div>
          {small_html}
        </div>"""
    return cards


def _chain_table(chain_results: list[dict]) -> str:
    rows = ""
    for r in chain_results:
        if r.get("error"):
            rows += f'<tr><td class="ct-chain">{_esc(r["chain"])}</td><td class="ct-symbol">{_esc(r["symbol"])}</td><td class="ct-amount err" colspan="2">{_esc(r["error"])}</td></tr>'
        else:
            usd = r.get("usd", 0)
            rows += f"""<tr>
              <td class="ct-chain">{_esc(r["chain"])}</td>
              <td class="ct-symbol">{_esc(r["symbol"])}</td>
              <td class="ct-amount">{_fmt_num(r.get("balance"))}</td>
              <td class="ct-usd">{_fmt_usd(usd) if usd else "—"}</td>
            </tr>"""
    return f"""<div class="table-wrap"><table class="ct">
      <thead><tr>
        <th class="ct-chain">鏈</th>
        <th class="ct-symbol">資產</th>
        <th class="ct-amount">數量</th>
        <th class="ct-usd">≈ USD</th>
      </tr></thead>
      <tbody>{rows}</tbody>
    </table></div>"""


def _defi_table(protocols: list[dict], total_usd: float) -> str:
    rows = ""
    for p in protocols:
        first = True
        for item in p.get("items", []):
            visible = [t for t in item["tokens"] if t["amount"] > 0][:4]
            token_str = "<br>".join(f"{_esc(t['symbol'])} {t['amount']:.4f}" for t in visible) or "—"
            proto_cell = f'<td class="dt-protocol">{_esc(p["protocol"])}</td>' if first else '<td class="dt-protocol"></td>'
            rows += f"""<tr>
              {proto_cell}
              <td class="dt-type">{_esc(item["name"])}</td>
              <td class="dt-tokens">{token_str}</td>
              <td class="dt-usd">{_fmt_usd(item["usd_value"])}</td>
            </tr>"""
            first = False
    return f"""<div class="defi-block">
      <div class="defi-header">
        <span class="defi-label">DeFi 持倉</span>
        <span class="defi-total">{_fmt_usd(total_usd)}</span>
      </div>
      <div class="table-wrap"><table class="dt">
        <thead><tr>
          <th class="dt-protocol">協議</th>
          <th class="dt-type">類型</th>
          <th class="dt-tokens">資產</th>
          <th class="dt-usd">≈ USD</th>
        </tr></thead>
        <tbody>{rows}</tbody>
      </table></div>
    </div>"""


def _evm_section(wallet_data: list[dict], twd_rate: float, full_addr: bool = False) -> str:
    html = ""
    for w in wallet_data:
        addr = w["address"]
        display_addr = addr if full_addr else f"{addr[:6]}...{addr[-4:]}"
        chain_results = w.get("chain_results", [])
        defi = w.get("defi_protocols", [])
        evm_usd = sum(r.get("usd", 0) for r in chain_results if r.get("usd"))
        defi_usd = sum(p["net_usd_value"] for p in defi)
        total = evm_usd + defi_usd

        chain_html = _chain_table(chain_results)
        defi_html = _defi_table(defi, defi_usd) if defi else ""

        html += f"""
        <div class="wallet-card">
          <div class="wallet-header">
            <span class="wallet-addr">{display_addr}</span>
            <span class="wallet-total">{_fmt_usd(total)} / {_fmt_twd(total, twd_rate)}</span>
          </div>
          {chain_html}
          {defi_html}
        </div>"""
    return html


def _btc_section(btc_results: list[dict], btc_price: float, twd_rate: float, full_addr: bool = False) -> str:
    html = ""
    for r in btc_results:
        addr = r["address"]
        display_addr = addr if full_addr else f"{addr[:8]}...{addr[-6:]}"
        if r.get("error"):
            html += f'<div class="wallet-card"><div class="wallet-header"><span class="wallet-addr">{_esc(display_addr)}</span></div><p class="err">{_esc(r["error"])}</p></div>'
        else:
            balance = r.get("balance") or 0.0
            usd = balance * btc_price
            html += f"""
            <div class="wallet-card">
              <div class="wallet-header">
                <span class="wallet-addr">{display_addr}</span>
                <span class="wallet-total">{_fmt_usd(usd)} / {_fmt_twd(usd, twd_rate)}</span>
              </div>
              {_chain_table([dict(chain="Bitcoin", symbol="BTC", balance=balance, usd=usd)])}

            </div>"""
    return html


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------

def build_html(snapshot: dict) -> str:
    """
    snapshot keys:
      timestamp, twd_rate,
      exchanges: {id: balances}, prices: {symbol: usd},
      evm_wallets: [{address, chain_results, defi_protocols}],
      btc_wallets: [{address, balance, error}],
      btc_price: float,
      grand_total_usd: float
    """
    twd_rate: float = snapshot.get("twd_rate", 32.0)
    prices: dict = snapshot.get("prices", {})
    grand_total: float = snapshot.get("grand_total_usd", 0.0)
    ts: str = snapshot.get("timestamp", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    evm_html = _evm_section(snapshot.get("evm_wallets", []), twd_rate, full_addr=True)

    btc_results = snapshot.get("btc_wallets", [])
    btc_price = snapshot.get("btc_price", 0.0)
    btc_cards = _btc_section(btc_results, btc_price, twd_rate, full_addr=True)
    btc_section = ""
    if btc_cards:
        btc_section = f'<section class="card"><h2>BTC 冷錢包</h2>{btc_cards}</section>'

    exchange_section = ""
    exchange_cards = _exchange_section(snapshot.get("exchanges", {}), prices, twd_rate)
    if exchange_cards:
        exchange_section = f'<section class="card"><h2>交易所帳戶</h2>{exchange_cards}</section>'

    evm_section = ""
    if evm_html:
        evm_section = f'<section class="card"><h2>EVM 冷錢包</h2>{evm_html}</section>'

    return f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

  body {{
    font-family: 'Inter', system-ui, sans-serif;
    background: #0b0e17;
    color: #e2e8f0;
    padding: 12px;
    font-size: 14px;
  }}
  @media (min-width: 640px) {{
    body {{ padding: 32px 48px; }}
  }}

  /* ── Header ── */
  .header {{
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    flex-wrap: wrap;
    gap: 12px;
    margin-bottom: 20px;
    padding-bottom: 16px;
    border-bottom: 1px solid #1e2535;
  }}
  .header-left h1 {{
    font-size: 20px;
    font-weight: 700;
    background: linear-gradient(135deg, #60a5fa, #a78bfa);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    margin-bottom: 4px;
  }}
  @media (min-width: 480px) {{
    .header-left h1 {{ font-size: 22px; }}
  }}
  .header-left .ts {{ font-size: 12px; color: #64748b; }}
  .grand-total {{ text-align: right; flex-shrink: 0; }}
  .grand-total .label {{ font-size: 11px; color: #64748b; margin-bottom: 2px; }}
  .grand-total .usd {{
    font-size: 24px; font-weight: 700;
    background: linear-gradient(135deg, #34d399, #60a5fa);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    line-height: 1.2;
  }}
  @media (min-width: 480px) {{
    .grand-total .usd {{ font-size: 28px; }}
  }}
  .grand-total .twd {{ font-size: 13px; color: #94a3b8; margin-top: 2px; }}

  /* ── Section cards ── */
  .card {{
    background: #111827;
    border: 1px solid #1e2535;
    border-radius: 12px;
    padding: 14px 12px;
    margin-bottom: 14px;
  }}
  @media (min-width: 640px) {{
    .card {{ padding: 20px 24px; }}
  }}
  .card h2 {{
    font-size: 12px;
    font-weight: 600;
    color: #64748b;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-bottom: 14px;
  }}

  /* ── Scrollable table wrapper ── */
  .table-wrap {{
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
    margin: 0 -4px;
    padding: 0 4px;
  }}

  /* ── Exchange table ── */
  .data-table {{
    width: 100%;
    min-width: 320px;
    border-collapse: collapse;
    font-size: 13px;
  }}
  .data-table thead tr {{ border-bottom: 1px solid #1e2535; }}
  .data-table th {{
    color: #4b5563;
    font-weight: 500;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    padding: 6px 10px;
    text-align: left;
    white-space: nowrap;
  }}
  .data-table th:not(:first-child) {{ text-align: right; }}
  .data-table td {{ padding: 9px 10px; border-bottom: 1px solid #0f1520; }}
  .data-table tbody tr:last-child td {{ border-bottom: none; }}

  /* ── Chain table (.ct) ── */
  .ct {{
    width: 100%;
    min-width: 300px;
    border-collapse: collapse;
    font-size: 13px;
  }}
  .ct thead tr {{ border-bottom: 1px solid #1e2535; }}
  .ct th {{
    color: #4b5563; font-size: 11px; font-weight: 500;
    text-transform: uppercase; letter-spacing: 0.05em;
    padding: 6px 10px; text-align: left; white-space: nowrap;
  }}
  .ct td {{ padding: 9px 10px; }}
  .ct tbody tr {{ border-bottom: 1px solid #0f1520; }}
  .ct tbody tr:last-child {{ border-bottom: none; }}
  .ct-chain  {{ color: #7c8ba1; font-size: 12px; white-space: nowrap; }}
  .ct-symbol {{ font-weight: 600; color: #e2e8f0; white-space: nowrap; }}
  .ct-amount {{ font-variant-numeric: tabular-nums; color: #cbd5e1; font-size: 12px; white-space: nowrap; }}
  .ct-usd    {{ font-variant-numeric: tabular-nums; color: #cbd5e1; font-size: 12px;
                text-align: right; white-space: nowrap; }}
  .ct th.ct-usd {{ text-align: right; }}

  /* ── DeFi block & table (.dt) ── */
  .defi-block {{ margin-top: 14px; padding-top: 12px; border-top: 1px solid #1a2333; }}
  .defi-header {{
    display: flex; justify-content: space-between; align-items: center;
    flex-wrap: wrap; gap: 6px;
    margin-bottom: 8px; padding: 0 4px;
  }}
  .defi-label {{ font-size: 11px; font-weight: 700; color: #a78bfa;
                 text-transform: uppercase; letter-spacing: 0.05em; }}
  .defi-total {{ font-size: 13px; font-weight: 600; color: #34d399; }}
  .dt {{
    width: 100%;
    min-width: 360px;
    border-collapse: collapse;
    font-size: 13px;
  }}
  .dt thead tr {{ border-bottom: 1px solid #1e2535; }}
  .dt th {{
    color: #4b5563; font-size: 11px; font-weight: 500;
    text-transform: uppercase; letter-spacing: 0.05em;
    padding: 6px 10px; text-align: left; white-space: nowrap;
  }}
  .dt td {{ padding: 8px 10px; }}
  .dt tbody tr {{ border-bottom: 1px solid #0f1520; }}
  .dt tbody tr:last-child {{ border-bottom: none; }}
  .dt-protocol {{ font-weight: 600; color: #e2e8f0; white-space: nowrap; }}
  .dt-type     {{ color: #7c8ba1; font-size: 12px; white-space: nowrap; }}
  .dt-tokens   {{ color: #94a3b8; font-size: 11px; line-height: 1.7; }}
  .dt-usd      {{ font-variant-numeric: tabular-nums; color: #cbd5e1; font-size: 12px;
                  text-align: right; white-space: nowrap; }}
  .dt th.dt-usd {{ text-align: right; }}

  /* ── Shared cell styles ── */
  .num {{ text-align: right; font-variant-numeric: tabular-nums; font-size: 12px; color: #cbd5e1; }}
  .asset-name {{ font-weight: 500; color: #e2e8f0; }}
  .err {{ color: #f87171; font-size: 12px; }}
  .pos {{ color: #34d399; }}
  .neg {{ color: #f87171; }}

  /* ── Exchange sub-cards ── */
  .exchange-badge {{
    display: inline-block;
    background: #1e2d45; color: #60a5fa;
    font-size: 11px; font-weight: 600;
    padding: 3px 10px; border-radius: 4px;
    letter-spacing: 0.05em;
  }}
  .ex-card {{
    background: #0f1520;
    border: 1px solid #1a2333;
    border-radius: 8px;
    margin-bottom: 10px;
    overflow: hidden;
  }}
  .ex-card:last-child {{ margin-bottom: 0; }}
  .ex-card-header {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 6px;
    padding: 10px 14px;
    background: #0d1525;
    border-bottom: 1px solid #1a2333;
  }}
  .ex-total {{ font-size: 13px; font-weight: 600; color: #34d399; }}
  .ex-card .table-wrap {{ padding: 0; margin: 0; }}
  .ex-card .data-table td {{ padding: 9px 14px; }}
  .ex-card .data-table th {{ padding: 6px 14px; }}
  .total-row td {{ border-top: 1px solid #1e2535 !important; }}
  .total-row .total-label {{ font-weight: 600; color: #94a3b8; font-size: 12px; }}
  .total-row .num {{ color: #34d399; }}

  /* ── Wallet cards ── */
  .wallet-card {{
    background: #0f1520;
    border: 1px solid #1a2333;
    border-radius: 8px;
    padding: 12px 14px;
    margin-bottom: 12px;
  }}
  .wallet-header {{
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    flex-wrap: wrap;
    gap: 6px;
    margin-bottom: 10px;
  }}
  .wallet-addr {{
    font-family: monospace;
    font-size: 11px;
    color: #60a5fa;
    background: #1e2d45;
    padding: 4px 8px;
    border-radius: 4px;
    word-break: break-all;
    max-width: 100%;
    line-height: 1.5;
  }}
  @media (min-width: 480px) {{
    .wallet-addr {{ font-size: 12px; }}
  }}
  .wallet-total {{ font-size: 13px; font-weight: 600; color: #34d399; white-space: nowrap; }}

  /* ── Collapsible small assets ── */
  .small-assets {{
    border-top: 1px solid #1a2333;
  }}
  .small-assets > summary {{
    cursor: pointer;
    list-style: none;
    padding: 9px 14px;
    font-size: 12px;
    color: #4b5563;
    user-select: none;
    outline: none;
  }}
  .small-assets > summary::-webkit-details-marker {{ display: none; }}
  .small-assets > summary::before {{ content: '▶  '; font-size: 9px; color: #374151; }}
  .small-assets[open] > summary::before {{ content: '▼  '; }}
  .small-assets > summary:hover {{ color: #6b7280; }}
  .small-assets .table-wrap {{ border-top: 1px solid #1a2333; }}

  /* ── Footer ── */
  .footer {{
    margin-top: 20px;
    padding-top: 14px;
    border-top: 1px solid #1e2535;
    font-size: 11px;
    color: #374151;
    text-align: center;
  }}
</style>
</head>
<body>
  <header class="header">
    <div class="header-left">
      <h1>資產總覽</h1>
      <div class="ts">{ts}</div>
    </div>
    <div class="grand-total">
      <div class="label">總資產</div>
      <div class="usd">{_fmt_usd(grand_total)}</div>
      <div class="twd">{_fmt_twd(grand_total, twd_rate)}</div>
    </div>
  </header>

  {exchange_section}
  {evm_section}
  {btc_section}

  <div class="footer">由 crypto資產查詢 生成 · {ts}</div>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Summary builder (simplified: totals only, large font)
# ---------------------------------------------------------------------------

def build_summary_html(snapshot: dict) -> str:
    twd_rate: float = snapshot.get("twd_rate", 32.0)
    prices: dict = snapshot.get("prices", {})
    grand_total: float = snapshot.get("grand_total_usd", 0.0)
    ts: str = snapshot.get("timestamp", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    # Build summary rows
    rows_html = ""

    # Exchanges
    for exchange_id, balances in snapshot.get("exchanges", {}).items():
        if "_error" in balances:
            continue
        total = sum(
            amount * prices.get(asset, 0)
            for asset, amount in balances.items()
            if amount and amount > 0
        )
        rows_html += f"""
        <div class="row">
          <div class="row-left">
            <span class="badge">{exchange_id.upper()}</span>
            <span class="row-label">交易所</span>
          </div>
          <div class="row-right">
            <span class="row-usd">{_fmt_usd(total)}</span>
            <span class="row-twd">{_fmt_twd(total, twd_rate)}</span>
          </div>
        </div>"""

    # EVM wallets
    for w in snapshot.get("evm_wallets", []):
        addr = w["address"]
        short = f"{addr[:6]}...{addr[-4:]}"
        evm_usd = sum(r.get("usd", 0) for r in w.get("chain_results", []))
        defi_usd = sum(p["net_usd_value"] for p in w.get("defi_protocols", []))
        total = evm_usd + defi_usd
        rows_html += f"""
        <div class="row">
          <div class="row-left">
            <span class="badge addr-badge">{short}</span>
            <span class="row-label">EVM 錢包</span>
          </div>
          <div class="row-right">
            <span class="row-usd">{_fmt_usd(total)}</span>
            <span class="row-twd">{_fmt_twd(total, twd_rate)}</span>
          </div>
        </div>"""

    # BTC
    btc_price = snapshot.get("btc_price", 0.0)
    for r in snapshot.get("btc_wallets", []):
        if r.get("error"):
            continue
        balance = r.get("balance") or 0.0
        usd = balance * btc_price
        if not usd:
            continue
        addr = r["address"]
        short_addr = f"{addr[:6]}...{addr[-6:]}"
        rows_html += f"""
        <div class="row">
          <div class="row-left">
            <span class="badge btc-badge">{short_addr}</span>
            <span class="row-label">BTC 冷錢包</span>
          </div>
          <div class="row-right">
            <span class="row-usd">{_fmt_usd(usd)}</span>
            <span class="row-twd">{_fmt_twd(usd, twd_rate)}</span>
          </div>
        </div>"""

    return f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: 'Inter', system-ui, sans-serif;
    background: #0b0e17;
    color: #e2e8f0;
    padding: 32px 40px 0px;
    width: 520px;
  }}

  /* Timestamp */
  .ts {{ font-size: 18px; font-weight: 600; color: #94a3b8; margin-bottom: 28px; letter-spacing: 0.02em; }}

  /* Rows */
  .rows {{ display: flex; flex-direction: column; gap: 10px; margin-bottom: 28px; }}
  .row {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    background: #111827;
    border: 1px solid #1e2535;
    border-radius: 10px;
    padding: 16px 20px;
  }}
  .row-left {{ display: flex; align-items: center; gap: 12px; }}
  .row-label {{ font-size: 13px; color: #6b7280; }}
  .row-right {{ text-align: right; }}
  .row-usd {{ font-size: 20px; font-weight: 700; color: #e2e8f0; display: block; }}
  .row-twd {{ font-size: 13px; color: #6b7280; display: block; margin-top: 2px; }}

  /* Badges */
  .badge {{
    display: inline-block;
    font-size: 12px;
    font-weight: 700;
    padding: 3px 10px;
    border-radius: 6px;
    letter-spacing: 0.04em;
    background: #1e2d45;
    color: #60a5fa;
  }}
  .addr-badge {{ background: #1e2535; color: #94a3b8; font-family: monospace; letter-spacing: 0; }}
  .btc-badge {{ background: #2a1f0a; color: #f59e0b; }}

  /* Divider */
  .divider {{ border: none; border-top: 1px solid #1e2535; margin: 4px 0 14px; }}

  /* Grand total */
  .grand {{
    background: linear-gradient(135deg, #0f2235, #14122a);
    border: 1px solid #2a3a55;
    border-radius: 14px;
    padding: 24px 28px;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }}
  .grand-label {{ font-size: 15px; color: #94a3b8; font-weight: 500; }}
  .grand-right {{ text-align: right; }}
  .grand-usd {{
    font-size: 36px;
    font-weight: 800;
    background: linear-gradient(135deg, #34d399, #60a5fa);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
  }}
  .grand-twd {{ font-size: 16px; color: #6b7280; margin-top: 4px; }}

  /* Footer */
  .footer {{ margin-top: 4px; padding-bottom: 4px; font-size: 11px; color: #374151; text-align: center; }}
</style>
</head>
<body>
  <div class="ts">{ts}</div>

  <div class="rows">
    {rows_html}
  </div>

  <hr class="divider">

  <div class="grand">
    <div class="grand-label">總資產</div>
    <div class="grand-right">
      <div class="grand-usd">{_fmt_usd(grand_total)}</div>
      <div class="grand-twd">{_fmt_twd(grand_total, twd_rate)}</div>
    </div>
  </div>

  <div class="footer">crypto資產查詢 · {ts}</div>
</body>
</html>"""
