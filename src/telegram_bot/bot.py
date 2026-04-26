"""
Telegram Bot — /asset 指令
執行方式：python -m src.telegram_bot.bot
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
import traceback

from dotenv import load_dotenv
from telegram import Update
from telegram.error import NetworkError, RetryAfter, TimedOut
from telegram.ext import Application, CommandHandler, ContextTypes

load_dotenv()

_log = logging.getLogger(__name__)

# chat ID 白名單，空集合 = 不限制
_ALLOWED_IDS: set[int] = set()

# 每個 chat_id 的查詢鎖，防止並行執行產生舊報告
_locks: dict[int, asyncio.Lock] = {}
_REPORT_TIMEOUT = 240  # 秒

# Telegram API 呼叫重試設定
_SEND_RETRIES = 3
_SEND_RETRY_BASE_DELAY = 2.0  # 秒，指數退避基底


def _get_lock(chat_id: int) -> asyncio.Lock:
    if chat_id not in _locks:
        _locks[chat_id] = asyncio.Lock()
    return _locks[chat_id]


async def _call_with_retry(coro_factory):
    """
    對 Telegram API 呼叫進行最多 _SEND_RETRIES 次重試。
    coro_factory: callable → coroutine，每次重試需重新建立 coroutine。
    遇到 RetryAfter 依伺服器要求等待；遇到 NetworkError / TimedOut 做指數退避。
    """
    for attempt in range(_SEND_RETRIES):
        try:
            return await coro_factory()
        except RetryAfter as e:
            wait = e.retry_after + 1
            _log.warning("Telegram 要求等待 %ds 後重試 (第%d次)", wait, attempt + 1)
            await asyncio.sleep(wait)
        except (NetworkError, TimedOut) as e:
            if attempt >= _SEND_RETRIES - 1:
                raise
            delay = _SEND_RETRY_BASE_DELAY * (2 ** attempt)
            _log.warning("Telegram 網路錯誤，%.1fs 後重試 (第%d次): %s", delay, attempt + 1, e)
            await asyncio.sleep(delay)
    # 最後一次不捕捉，讓例外往上傳
    return await coro_factory()


async def _error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """全域錯誤處理器：記錄例外但不讓 bot 程序崩潰。"""
    _log.error(
        "未處理的例外\nupdate=%s\n%s",
        update,
        "".join(traceback.format_exception(type(context.error), context.error, context.error.__traceback__ if context.error else None)),
    )


def _parse_allowed_ids() -> set[int]:
    raw = os.getenv("TELEGRAM_ALLOWED_CHAT_IDS", "").strip()
    if not raw:
        return set()
    ids: set[int] = set()
    for s in raw.split(","):
        s = s.strip()
        if s:
            try:
                ids.add(int(s))
            except ValueError:
                _log.warning("無效的 TELEGRAM_ALLOWED_CHAT_IDS 值: %s", s)
    return ids


def _is_authorized(chat_id: int) -> bool:
    return not _ALLOWED_IDS or chat_id in _ALLOWED_IDS


# ---------------------------------------------------------------------------
# 同步工作（在 thread executor 中執行，避免阻塞 event loop）
# ---------------------------------------------------------------------------

def _run_report() -> tuple[bytes, bytes, str]:
    """
    執行完整資料收集 + 產生摘要 PNG + 產生明細 HTML。
    返回 (png_bytes, html_bytes, timestamp_str)
    """
    from main import collect_snapshot
    from src.report.html_builder import build_html, build_summary_html
    from src.utils.valuation import get_twd_rate
    from playwright.sync_api import sync_playwright

    twd_rate = get_twd_rate()
    snapshot = collect_snapshot(None, None, twd_rate)
    ts: str = snapshot["timestamp"]

    # 摘要 PNG
    html_summary = build_summary_html(snapshot)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 520, "height": 800})
        page.set_content(html_summary, wait_until="networkidle")
        page.wait_for_timeout(800)
        w = page.evaluate("document.documentElement.scrollWidth")
        h = page.evaluate("Math.ceil(document.body.getBoundingClientRect().bottom)")
        png_bytes: bytes = page.screenshot(
            clip={"x": 0, "y": 0, "width": w, "height": h}
        )
        browser.close()

    # 明細 HTML
    html_bytes = build_html(snapshot).encode("utf-8")

    return png_bytes, html_bytes, ts


# ---------------------------------------------------------------------------
# 指令處理
# ---------------------------------------------------------------------------

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    assert update.message
    await update.message.reply_text("⚆_⚆")


async def cmd_asset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    assert update.effective_chat and update.message

    chat_id = update.effective_chat.id
    if not _is_authorized(chat_id):
        await update.message.reply_text("⛔ 未授權")
        return

    lock = _get_lock(chat_id)
    if lock.locked():
        await update.message.reply_text("⏳ 已在查詢中，請稍候...")
        return

    status_msg = await update.message.reply_text("查詢中請稍後...")

    async with lock:
        try:
            png_bytes, html_bytes, ts = await asyncio.wait_for(
                asyncio.to_thread(_run_report),
                timeout=_REPORT_TIMEOUT,
            )
            ts_safe = ts.replace(":", "-").replace(" ", "_")

            await _call_with_retry(
                lambda: context.bot.send_photo(
                    chat_id=chat_id,
                    photo=png_bytes,
                    caption=f"📊 資產摘要  {ts}",
                )
            )
            await _call_with_retry(
                lambda: context.bot.send_document(
                    chat_id=chat_id,
                    document=io.BytesIO(html_bytes),
                    filename=f"portfolio_{ts_safe}.html",
                    caption="📄 詳細報告",
                )
            )
            await status_msg.delete()

        except asyncio.TimeoutError:
            _log.warning("asset 查詢逾時 (%ds)", _REPORT_TIMEOUT)
            await status_msg.edit_text("❌ 查詢逾時，請稍後再試")
        except Exception as exc:
            _log.error("asset 指令失敗", exc_info=True)
            await status_msg.edit_text(f"❌ 查詢失敗：{exc}")


# ---------------------------------------------------------------------------
# 進入點
# ---------------------------------------------------------------------------

def main() -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("請在 .env 設定 TELEGRAM_BOT_TOKEN")

    global _ALLOWED_IDS
    _ALLOWED_IDS = _parse_allowed_ids()
    if _ALLOWED_IDS:
        _log.info("已啟用白名單，允許的 chat ID: %s", _ALLOWED_IDS)
    else:
        _log.warning("未設定 TELEGRAM_ALLOWED_CHAT_IDS，所有人皆可使用")

    app = (
        Application.builder()
        .token(token)
        .connect_timeout(30)
        .read_timeout(60)
        .write_timeout(60)
        .build()
    )
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("asset", cmd_asset))
    app.add_error_handler(_error_handler)

    _log.info("Telegram bot 啟動，等待 /asset 指令...")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=False)


if __name__ == "__main__":
    main()
