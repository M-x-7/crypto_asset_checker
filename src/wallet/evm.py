import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from dotenv import load_dotenv
from web3 import Web3

load_dotenv()

_chains_cache: dict | None = None
_chains_lock = threading.Lock()
_MAX_WORKERS = 8  # cap to avoid hammering public RPCs


def _load_chains() -> dict:
    global _chains_cache
    with _chains_lock:
        if _chains_cache is None:
            from src.utils.config import get_chains
            data = get_chains()
            _required = {"name", "symbol", "rpc"}
            for chain_id, cfg in data.items():
                missing = _required - set(cfg or {})
                if missing:
                    raise ValueError(f"endpoints.yaml 中 [{chain_id}] 缺少必要欄位: {missing}")
            _chains_cache = data
    return _chains_cache


def _get_rpc(chain_cfg: dict) -> str:
    env_key = chain_cfg.get("env_rpc", "")
    override = os.getenv(env_key, "").strip()
    return override if override else chain_cfg["rpc"]


def _connect(chain_cfg: dict) -> Web3:
    rpc = _get_rpc(chain_cfg)
    return Web3(Web3.HTTPProvider(rpc))


def validate_address(address: str) -> str:
    """Validate and return checksum address. Raises ValueError if invalid."""
    try:
        return Web3.to_checksum_address(address)
    except Exception:
        raise ValueError(f"無效的 EVM 地址: {address}")


def get_native_balance(address: str, chain_id: str) -> dict:
    """Query native token balance for an address on a specific chain."""
    chains = _load_chains()
    if chain_id not in chains:
        raise ValueError(f"不支援的鏈: {chain_id}（可用: {', '.join(chains)}）")

    chain_cfg = chains[chain_id]
    checksum_addr = validate_address(address)
    w3 = _connect(chain_cfg)
    raw_balance = w3.eth.get_balance(checksum_addr)

    return {
        "chain_id": chain_id,
        "chain": chain_cfg["name"],
        "symbol": chain_cfg["symbol"],
        "balance": float(w3.from_wei(raw_balance, "ether")),
    }


def _query_chain(chain_id: str, chain_cfg: dict, checksum_addr: str) -> dict:
    try:
        w3 = _connect(chain_cfg)
        raw = w3.eth.get_balance(checksum_addr)
        return {
            "chain_id": chain_id,
            "chain": chain_cfg["name"],
            "symbol": chain_cfg["symbol"],
            "balance": float(w3.from_wei(raw, "ether")),
        }
    except Exception as e:
        return {
            "chain_id": chain_id,
            "chain": chain_cfg["name"],
            "symbol": chain_cfg["symbol"],
            "balance": None,
            "error": str(e),
        }


def get_all_native_balances(address: str) -> list[dict]:
    """Query native token balance across all configured chains in parallel."""
    chains = _load_chains()
    checksum_addr = validate_address(address)

    ordered: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=min(len(chains), _MAX_WORKERS)) as executor:
        futures = {
            executor.submit(_query_chain, cid, cfg, checksum_addr): cid
            for cid, cfg in chains.items()
        }
        for future in as_completed(futures):
            cid = futures[future]
            ordered[cid] = future.result()

    return [ordered[cid] for cid in chains]


def list_chains() -> list[str]:
    return list(_load_chains().keys())
