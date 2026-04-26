import re
import time
import requests

from src.utils.config import get_service
_HTTP_TIMEOUT = 10
_RETRIES = 3
_RETRY_BACKOFF = 1.5

# Supports: P2PKH (1...), P2SH (3...), Bech32 (bc1...)
_BTC_ADDRESS_RE = re.compile(r"^(1[a-zA-Z0-9]{25,34}|3[a-zA-Z0-9]{25,34}|bc1[a-zA-Z0-9]{6,87})$")


def validate_btc_address(address: str) -> str:
    """Validate BTC address format. Raises ValueError if invalid."""
    if not _BTC_ADDRESS_RE.match(address):
        raise ValueError(f"無效的 BTC 地址格式: {address}")
    return address


def get_btc_balance(address: str) -> dict:
    """Query BTC balance via Blockstream API (no key required), with retry."""
    validate_btc_address(address)
    last_exc: Exception = RuntimeError("未知錯誤")
    for attempt in range(_RETRIES):
        try:
            resp = requests.get(get_service("btc_explorer_url").format(address), timeout=_HTTP_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            stats = data.get("chain_stats", {})
            satoshis = stats.get("funded_txo_sum", 0) - stats.get("spent_txo_sum", 0)
            return {
                "address": address,
                "chain": "Bitcoin",
                "symbol": "BTC",
                "balance": satoshis / 1e8,
            }
        except Exception as e:
            last_exc = e
            if attempt < _RETRIES - 1:
                time.sleep(_RETRY_BACKOFF ** attempt)
    raise last_exc


def get_all_btc_balances(addresses: list[str]) -> list[dict]:
    results = []
    for addr in addresses:
        try:
            results.append(get_btc_balance(addr.strip()))
        except Exception as e:
            results.append({
                "address": addr.strip(),
                "chain": "Bitcoin",
                "symbol": "BTC",
                "balance": None,
                "error": str(e),
            })
    return results
