import logging
import os

import ccxt
from dotenv import load_dotenv

load_dotenv()

_log = logging.getLogger(__name__)

CCXT_CONFIGS = {
    "binance": {
        "class": ccxt.binance,
        "params": {
            "apiKey": os.getenv("BINANCE_API_KEY"),
            "secret": os.getenv("BINANCE_SECRET"),
        },
    },
    "okx": {
        "class": ccxt.okx,
        "params": {
            "apiKey": os.getenv("OKX_API_KEY"),
            "secret": os.getenv("OKX_SECRET"),
            "password": os.getenv("OKX_PASSPHRASE"),
        },
    },
}

WATCH_PAIRS = ["BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT"]


def _build_ccxt(exchange_id: str) -> ccxt.Exchange | None:
    cfg = CCXT_CONFIGS.get(exchange_id)
    if not cfg:
        return None
    return cfg["class"]({"enableRateLimit": True, **cfg["params"]})


def _ccxt_configured(exchange_id: str) -> bool:
    return bool(CCXT_CONFIGS.get(exchange_id, {}).get("params", {}).get("apiKey"))


def _fetch_binance_combined_balances() -> dict[str, float]:
    """
    Query Binance spot + Simple Earn (flexible + locked) and merge totals.
    LD* tokens in spot are earn vouchers — filtered out to avoid double-counting.
    """
    exchange = _build_ccxt("binance")
    combined: dict[str, float] = {}

    try:
        raw = exchange.fetch_balance({"type": "spot"})
        for asset, total in raw["total"].items():
            if total and total > 0 and not asset.startswith("LD"):
                combined[asset] = combined.get(asset, 0.0) + total
    except Exception as e:
        _log.warning("Binance spot 餘額查詢失敗: %s", e)

    try:
        resp = exchange.sapiGetSimpleEarnFlexiblePosition({"size": 100})
        for item in resp.get("rows", []):
            asset = item.get("asset", "")
            amt = float(item.get("totalAmount", 0))
            if asset and amt > 0:
                combined[asset] = combined.get(asset, 0.0) + amt
    except Exception as e:
        _log.warning("Binance Flexible Earn 查詢失敗: %s", e)

    try:
        resp = exchange.sapiGetSimpleEarnLockedPosition({"size": 100})
        for item in resp.get("rows", []):
            asset = item.get("asset", "")
            amt = float(item.get("amount", 0))
            if asset and amt > 0:
                combined[asset] = combined.get(asset, 0.0) + amt
    except Exception as e:
        _log.warning("Binance Locked Earn 查詢失敗: %s", e)

    return combined


def _fetch_okx_combined_balances() -> dict[str, float]:
    """Query OKX funding + unified trading + savings earn accounts and merge totals."""
    exchange = _build_ccxt("okx")
    combined: dict[str, float] = {}

    for account_type in ("funding", "trading"):
        try:
            raw = exchange.fetch_balance({"type": account_type})
            for asset, total in raw["total"].items():
                if total and total > 0:
                    combined[asset] = combined.get(asset, 0.0) + total
        except Exception as e:
            _log.warning("OKX %s 帳戶查詢失敗: %s", account_type, e)

    try:
        resp = exchange.privateGetFinanceSavingsBalance()
        for item in resp.get("data", []):
            asset = item.get("ccy", "")
            amt = float(item.get("amt", 0))
            if asset and amt > 0:
                combined[asset] = combined.get(asset, 0.0) + amt
    except Exception as e:
        _log.warning("OKX Savings 帳戶查詢失敗: %s", e)

    return combined


def get_balances(exchange_id: str) -> dict:
    """Return non-zero balances for the given exchange."""
    if not _ccxt_configured(exchange_id):
        return {}

    if exchange_id == "binance":
        try:
            return _fetch_binance_combined_balances()
        except Exception as e:
            raise RuntimeError(f"[binance] 餘額查詢失敗: {e}") from e

    if exchange_id == "okx":
        try:
            return _fetch_okx_combined_balances()
        except Exception as e:
            raise RuntimeError(f"[okx] 餘額查詢失敗: {e}") from e

    exchange = _build_ccxt(exchange_id)
    try:
        raw = exchange.fetch_balance()
        return {
            asset: total
            for asset, total in raw["total"].items()
            if total and total > 0
        }
    except Exception as e:
        raise RuntimeError(f"[{exchange_id}] 餘額查詢失敗: {e}") from e


def get_exchange_instance(exchange_id: str) -> ccxt.Exchange | None:
    """Return a ccxt exchange instance for use in valuation lookups."""
    if not _ccxt_configured(exchange_id):
        return None
    return _build_ccxt(exchange_id)


def get_all_balances() -> dict[str, dict]:
    """Return balances keyed by exchange_id. Unconfigured exchanges are omitted."""
    result = {}
    for exchange_id in CCXT_CONFIGS:
        if not _ccxt_configured(exchange_id):
            continue
        try:
            result[exchange_id] = get_balances(exchange_id)
        except RuntimeError as e:
            result[exchange_id] = {"_error": str(e)}
    return result
