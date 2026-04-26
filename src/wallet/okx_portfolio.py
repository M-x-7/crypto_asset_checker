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
# Compiled regexes (cached at module level)
_RE_PROTOCOL = re.compile(r"^(.+?)\s*·\s*(\$[\d,.<]+)$")
_RE_TOKEN_ROW = re.compile(r"^([\d.]+)\s+([A-Za-z][A-Za-z0-9.]{1,15})$")
_RE_USD = re.compile(r"^\$[\d,.<]+$")


def scrape_defi_positions_batch(addresses: list[str]) -> dict[str, list[dict]]:
    """
    Scrape DeFi positions for multiple addresses in a single browser session.
    Returns {address: [protocol, ...]}
    """
    results: dict[str, list[dict]] = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            for address in addresses:
                results[address] = _scrape_one(browser, address)
        finally:
            browser.close()
    return results


def scrape_defi_positions(address: str) -> list[dict]:
    """Scrape DeFi positions for a single address."""
    results = scrape_defi_positions_batch([address])
    return results.get(address, [])


def _scrape_one(browser: Browser, address: str) -> list[dict]:
    url = get_service("okx_portfolio_url").format(address)
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    try:
        page.goto(url, wait_until="networkidle", timeout=_GOTO_TIMEOUT)
        try:
            page.wait_for_selector("[class*=assetAmount]", timeout=_SELECTOR_TIMEOUT)
        except PWTimeout:
            _log.warning("OKX portfolio 頁面載入逾時: %s", address[:10])
            return []

        page.locator('.dashboard-tabs-pane:has-text("資產組合")').click()
        page.wait_for_timeout(2000)

        page.locator('.dashboard-tabs-pane-segmented:has-text("DeFi")').click()
        page.wait_for_timeout(_DEFI_WAIT_MS)

        try:
            page.wait_for_selector(".dashboard-table-row", timeout=8000)
        except PWTimeout:
            _log.debug("DeFi table row selector 逾時，繼續嘗試解析")

        page.evaluate("window.scrollTo(0, 300)")
        page.wait_for_timeout(500)

        return _extract_protocols(page)
    finally:
        page.close()


def _parse_usd(text: str) -> float:
    """Extract float from strings like '$4,781.87' or '<$0.01'."""
    text = text.replace("<", "").replace("$", "").replace(",", "").strip()
    try:
        return float(text)
    except ValueError:
        return 0.0


def _extract_protocols(page) -> list[dict]:
    body = page.inner_text("body")
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
