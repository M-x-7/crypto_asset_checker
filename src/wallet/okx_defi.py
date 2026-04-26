import base64
import datetime
import hashlib
import hmac
import os
from urllib.parse import urlencode

import requests
from dotenv import load_dotenv

load_dotenv()

_BASE = "https://www.okx.com"
_HTTP_TIMEOUT = 10
_MIN_USD_VALUE = 0.01


def _sign_headers(method: str, path: str, query_string: str = "") -> dict:
    api_key = os.getenv("OKX_API_KEY", "")
    secret = os.getenv("OKX_SECRET", "")
    passphrase = os.getenv("OKX_PASSPHRASE", "")
    project_id = os.getenv("OKX_PROJECT_ID", "")

    ts = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    full_path = path + ("?" + query_string if query_string else "")
    sig = base64.b64encode(
        hmac.new(secret.encode(), (ts + method.upper() + full_path).encode(), hashlib.sha256).digest()
    ).decode()

    return {
        "OK-ACCESS-KEY": api_key,
        "OK-ACCESS-SIGN": sig,
        "OK-ACCESS-TIMESTAMP": ts,
        "OK-ACCESS-PASSPHRASE": passphrase,
        "OK-ACCESS-PROJECT": project_id,
        "accept": "application/json",
    }


def is_configured() -> bool:
    return bool(os.getenv("OKX_PROJECT_ID", "").strip())


def get_defi_positions(address: str) -> list[dict]:
    """Return DeFi positions for an address via OKX Web3 API."""
    path = "/api/v5/wallet/investment/defi-position"
    params = {"address": address.lower()}
    query_string = urlencode(sorted(params.items()))
    headers = _sign_headers("GET", path, query_string)

    resp = requests.get(
        _BASE + path,
        params=params,
        headers=headers,
        timeout=_HTTP_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()

    if data.get("code") != "0":
        raise RuntimeError(f"OKX Web3 API 錯誤: {data.get('msg')}")

    protocols = []
    for p in data.get("data", []):
        net_usd = float(p.get("usdValue", 0) or 0)
        if net_usd < _MIN_USD_VALUE:
            continue
        items = []
        for item in p.get("positionList", []):
            item_usd = float(item.get("usdValue", 0) or 0)
            tokens = []
            for t in item.get("tokenList", []):
                amount = float(t.get("amount", 0) or 0)
                price = float(t.get("tokenPrice", 0) or 0)
                tokens.append({
                    "symbol": t.get("symbol", "?"),
                    "amount": amount,
                    "usd": amount * price,
                })
            items.append({
                "name": item.get("positionType", ""),
                "usd_value": item_usd,
                "tokens": tokens,
            })
        protocols.append({
            "protocol": p.get("projectName", ""),
            "chain": p.get("chainName", ""),
            "net_usd_value": net_usd,
            "items": items,
        })
    return sorted(protocols, key=lambda x: x["net_usd_value"], reverse=True)
