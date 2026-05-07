import logging
import re
from playwright.sync_api import Browser, sync_playwright, TimeoutError as PWTimeout

from src.utils.config import get_service

_log = logging.getLogger(__name__)

_GOTO_TIMEOUT = 30000
_SELECTOR_TIMEOUT = 10000
_DEFI_WAIT_MS = 3000
_SECTION_LABELS = {"機槍池", "流動池", "質押", "借貸", "收益農場", "保險庫", "存款", "鎖倉", "借出", "借入"}
_TABLE_HEADERS = {"投資品", "資產", "可領取收益", "總價值"}
_MIN_USD_VALUE = 0.01
# Known chain display names on OKX Portfolio page
_CHAIN_DISPLAY = {
    "Ethereum", "BNB Chain", "Polygon", "Arbitrum One", "Optimism",
    "Avalanche C-Chain", "Base", "Fantom", "Cronos", "Solana",
    "zkSync Era", "Linea", "Scroll", "Mantle",
}
# Compiled regexes (cached at module level)
_RE_PROTOCOL = re.compile(r"^(.+?)\s*·\s*(\$[\d,.<]+)$")
_RE_TOKEN_ROW = re.compile(r"^([\d.]+)\s+([A-Za-z][A-Za-z0-9.]{1,15})$")
_RE_USD = re.compile(r"^\$[\d,.<]+$")
_RE_AMOUNT = re.compile(r"^[\d,]+\.?\d*$")
_RE_SYMBOL = re.compile(r"^[A-Za-z][A-Za-z0-9.]{1,19}$")


_BLOCK_TYPES = {"image", "media", "font", "other"}
_BROWSER_ARGS = [
    "--disable-extensions",
    "--disable-default-apps",
    "--disable-background-networking",
    "--disable-sync",
    "--disable-translate",
    "--disable-plugins",
    "--no-first-run",
    "--disable-gpu",
    "--disable-software-rasterizer",
    "--disable-dev-shm-usage",
    "--renderer-process-limit=1",
    "--js-flags=--max-old-space-size=256",
]


def scrape_defi_positions_batch(addresses: list[str]) -> dict[str, dict]:
    """
    Scrape DeFi positions + token balances for multiple addresses in one browser session.
    Returns {address: {"protocols": [...], "tokens": [...]}}
    """
    results: dict[str, dict] = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=_BROWSER_ARGS)
        try:
            for address in addresses:
                results[address] = _scrape_one(browser, address)
        finally:
            browser.close()
    return results


def _scrape_one(browser: Browser, address: str) -> dict:
    """Returns {"protocols": [...], "tokens": [...]}"""
    url = get_service("okx_portfolio_url").format(address)
    page = browser.new_page(viewport={"width": 1280, "height": 720})
    page.route("**/*", lambda route: (
        route.abort() if route.request.resource_type in _BLOCK_TYPES else route.continue_()
    ))
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=_GOTO_TIMEOUT)

        # 等待頁面主要內容渲染（assetAmount 或任何已知穩定 selector）
        try:
            page.wait_for_selector("[class*=assetAmount], [class*=totalAsset], [class*=portfolioTotal]",
                                   timeout=_SELECTOR_TIMEOUT)
        except PWTimeout:
            _log.warning("OKX portfolio 頁面載入逾時: %s", address[:10])
            return {"protocols": [], "tokens": []}

        # 切到「資產組合」tab（頁面通常預設就在此，失敗也繼續）
        try:
            tab = page.get_by_role("tab", name="資產組合")
            tab.wait_for(timeout=5000)
            tab.click()
            page.wait_for_timeout(1500)
        except Exception:
            pass

        # 幣種 sub-tab
        tokens: list[dict] = []
        try:
            token_tab = page.get_by_role("tab", name="幣種")
            token_tab.wait_for(timeout=8000)
            token_tab.click()
            page.wait_for_timeout(1500)
            tokens = _extract_tokens(page.inner_text("body"))
        except Exception as e:
            _log.warning("幣種頁解析失敗: %s", e)

        # Switch to DeFi tab
        try:
            defi_tab = page.get_by_role("tab", name="DeFi")
            defi_tab.wait_for(timeout=8000)
            defi_tab.click()
        except Exception as e:
            _log.warning("DeFi tab 點擊失敗: %s", e)
            return {"protocols": [], "tokens": tokens}

        page.wait_for_timeout(_DEFI_WAIT_MS)
        page.evaluate("window.scrollTo(0, 300)")
        page.wait_for_timeout(500)

        protocols = _extract_protocols(page.inner_text("body"))
        return {"protocols": protocols, "tokens": tokens}
    finally:
        page.close()


def _parse_usd(text: str) -> float:
    """Extract float from strings like '$4,781.87' or '<$0.01'."""
    text = text.replace("<", "").replace("$", "").replace(",", "").strip()
    try:
        return float(text)
    except ValueError:
        return 0.0


def _extract_tokens(body: str) -> list[dict]:
    """
    Parse wallet token balances from the OKX Portfolio token tab.
    Expected text pattern per token: chain_name → symbol → amount → $usd
    """
    lines = [l.strip() for l in body.split("\n") if l.strip()]

    tokens: list[dict] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line not in _CHAIN_DISPLAY:
            i += 1
            continue
        chain = line
        # Look ahead for: symbol, amount, usd  (within 4 lines)
        for offset in range(1, 5):
            if i + offset + 2 >= len(lines):
                break
            sym_line = lines[i + offset]
            amt_line = lines[i + offset + 1]
            usd_line = lines[i + offset + 2]
            if (
                _RE_SYMBOL.match(sym_line)
                and _RE_AMOUNT.match(amt_line.replace(",", ""))
                and _RE_USD.match(usd_line)
            ):
                usd = _parse_usd(usd_line)
                if usd >= _MIN_USD_VALUE:
                    tokens.append({
                        "chain": chain,
                        "symbol": sym_line,
                        "name": sym_line,
                        "balance": float(amt_line.replace(",", "")),
                        "usd_value": usd,
                    })
                i += offset + 3
                break
        else:
            i += 1

    return sorted(tokens, key=lambda x: x["usd_value"], reverse=True)


def _extract_protocols(body: str) -> list[dict]:
    lines = [l.strip() for l in body.split("\n") if l.strip()]

    detail_start = next(
        (i for i, l in enumerate(lines) if _RE_PROTOCOL.match(l) and "DeFi" not in l),
        None,
    )
    if detail_start is None:
        return []

    protocols = []
    current_protocol = None
    current_items: list[dict] = []
    current_section = "持倉"
    current_tokens: list[dict] = []

    def flush_section():
        if current_tokens and current_protocol is not None:
            usd_total = sum(t["usd"] for t in current_tokens)
            current_items.append({
                "name": current_section,
                "usd_value": usd_total,
                "tokens": current_tokens[:],
            })
        current_tokens.clear()

    i = detail_start
    while i < len(lines):
        line = lines[i]

        m = _RE_PROTOCOL.match(line)
        if m and "DeFi" not in line:
            flush_section()
            if current_protocol is not None:
                protocols.append({
                    "protocol": current_protocol["name"],
                    "net_usd_value": current_protocol["usd"],
                    "items": current_items[:],
                })
            current_protocol = {"name": m.group(1).strip(), "usd": _parse_usd(m.group(2))}
            current_items = []
            current_section = "持倉"
            current_tokens = []
            i += 1
            continue

        if line in _SECTION_LABELS:
            flush_section()
            current_section = line
            i += 1
            continue

        if line in _TABLE_HEADERS:
            i += 1
            continue

        token_m = _RE_TOKEN_ROW.match(line)
        if token_m and current_protocol is not None:
            amount = float(token_m.group(1))
            symbol = token_m.group(2)
            usd = 0.0
            if i + 1 < len(lines) and _RE_USD.match(lines[i + 1]):
                usd = _parse_usd(lines[i + 1])
                i += 2
                skip = 0
                while skip < 2 and i < len(lines) and (lines[i] == "--" or _RE_USD.match(lines[i])):
                    i += 1
                    skip += 1
            else:
                i += 1
            current_tokens.append({"symbol": symbol, "amount": amount, "usd": usd})
            continue

        i += 1

    flush_section()
    if current_protocol is not None:
        protocols.append({
            "protocol": current_protocol["name"],
            "net_usd_value": current_protocol["usd"],
            "items": current_items[:],
        })

    return sorted(protocols, key=lambda x: x["net_usd_value"], reverse=True)
