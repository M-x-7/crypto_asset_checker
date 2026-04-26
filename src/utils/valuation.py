import time
import warnings

import requests

from src.utils.config import get_service

_STABLECOINS = {"USDT", "USDC", "BUSD", "DAI", "TUSD", "USDP", "FDUSD"}
_HTTP_TIMEOUT = 10
_RETRIES = 3
_RETRY_BACKOFF = 1.5


def _get_with_retry(url: str, **kwargs) -> requests.Response:
    last_exc: Exception = RuntimeError("未知錯誤")
    for attempt in range(_RETRIES):
        try:
            resp = requests.get(url, timeout=_HTTP_TIMEOUT, **kwargs)
            resp.raise_for_status()
            return resp
        except Exception as e:
            last_exc = e
            if attempt < _RETRIES - 1:
                time.sleep(_RETRY_BACKOFF ** attempt)
    raise last_exc


def get_usd_prices(symbols: list[str], exchange) -> dict[str, float]:
    """Return USD price for each symbol using exchange tickers. Stablecoins = 1.0."""
    prices: dict[str, float] = {s: 1.0 for s in symbols if s in _STABLECOINS}
    for symbol in symbols:
        if symbol in prices:
            continue
        for quote in ("USDT", "USDC"):
            try:
                ticker = exchange.fetch_ticker(f"{symbol}/{quote}")
                if ticker.get("last"):
                    prices[symbol] = float(ticker["last"])
                    break
            except Exception:
                continue
    return prices


def get_twd_rate() -> float:
    """Return current USD/TWD exchange rate from open.er-api.com."""
    try:
        resp = _get_with_retry(get_service("fx_rate_url"))
        return float(resp.json()["rates"]["TWD"])
    except Exception:
        warnings.warn("TWD 匯率取得失敗，使用備用值 32.0", stacklevel=2)
        return 32.0
