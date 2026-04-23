"""tick レコーダーのエントリーポイント.

常駐プロセス。以下を繰り返す:
  1. 全シンボルから新しい tick を取得
  2. ストレージのバッファに積む
  3. 一定間隔で Parquet へ flush
  4. 定期的にハートビート書き込み
  5. MT5 切断時は自動再接続

Ctrl+C で安全に終了（残バッファを flush してから終了）。
"""

from __future__ import annotations

import time
import signal
import logging
import argparse
from datetime import datetime, timezone

from .config import (
    SYMBOLS, POLL_INTERVAL_SECONDS, FLUSH_INTERVAL_SECONDS,
    HEARTBEAT_INTERVAL_SECONDS, ensure_dirs,
)
from .mt5_client import MT5Client
from .storage import TickStorage
from .monitor import setup_logging, write_heartbeat


logger = logging.getLogger(__name__)

# シャットダウンフラグ（シグナルハンドラから操作）
_shutdown_requested = False


def _signal_handler(signum, frame):
    global _shutdown_requested
    logger.warning(f"Signal {signum} received, shutting down gracefully...")
    _shutdown_requested = True


def run(symbols: list[str], test_mode: bool = False, max_iterations: int | None = None) -> None:
    """メインループ."""
    ensure_dirs()
    logger.info(f"=== tick recorder starting ===")
    logger.info(f"Target symbols: {len(symbols)}")
    logger.info(f"Poll interval: {POLL_INTERVAL_SECONDS}s, Flush interval: {FLUSH_INTERVAL_SECONDS}s")
    if test_mode:
        logger.info(f"TEST MODE: max_iterations={max_iterations}")

    client = MT5Client(symbols)
    storage = TickStorage()

    if not client.connect():
        logger.error("Failed to connect MT5, exit")
        return

    active_symbols, missing = client.ensure_symbols()
    if not active_symbols:
        logger.error("No active symbols, exit")
        client.shutdown()
        return

    last_flush = time.time()
    last_heartbeat = time.time()
    iteration = 0
    last_flush_at_str = "never"

    try:
        while not _shutdown_requested:
            iteration += 1
            loop_start = time.time()

            # 1. 各シンボルから新tick取得
            if not client.is_connected:
                if not client.reconnect():
                    time.sleep(POLL_INTERVAL_SECONDS)
                    continue
                active_symbols, _ = client.ensure_symbols()

            total_fetched = 0
            for sym in active_symbols:
                try:
                    ticks = client.fetch_new_ticks(sym)
                    if ticks:
                        storage.append_ticks(sym, ticks)
                        total_fetched += len(ticks)
                except Exception as e:
                    logger.error(f"{sym}: fetch failed: {e}")

            # 2. Flush判定
            now = time.time()
            if now - last_flush >= FLUSH_INTERVAL_SECONDS:
                written = storage.flush_all()
                if written:
                    wsum = sum(written.values())
                    logger.info(f"Flushed {wsum} ticks across {len(written)} symbols")
                last_flush = now
                last_flush_at_str = datetime.now(timezone.utc).isoformat()

            # 3. Heartbeat
            if now - last_heartbeat >= HEARTBEAT_INTERVAL_SECONDS:
                write_heartbeat(
                    stats=storage.get_stats(),
                    buffer_size=storage.buffer_size(),
                    last_flush_at=last_flush_at_str,
                )
                last_heartbeat = now
                logger.info(
                    f"iter={iteration} fetched_this_iter={total_fetched} "
                    f"buffer={storage.buffer_size()} total_written={sum(storage.get_stats().values())}"
                )

            # 4. Poll間隔調整（処理時間差し引き）
            elapsed = time.time() - loop_start
            sleep_time = max(0.0, POLL_INTERVAL_SECONDS - elapsed)
            time.sleep(sleep_time)

            if test_mode and max_iterations is not None and iteration >= max_iterations:
                logger.info(f"Test mode: reached max_iterations={max_iterations}, exit")
                break

    finally:
        # 残バッファを flush
        logger.info("Final flush before exit...")
        try:
            written = storage.flush_all()
            logger.info(f"Final flush: {sum(written.values())} ticks")
        except Exception as e:
            logger.error(f"Final flush failed: {e}")

        client.shutdown()
        logger.info("=== tick recorder stopped ===")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--symbols",
        type=str,
        default=None,
        help="Comma-separated symbol list. If omitted, uses all from config.",
    )
    parser.add_argument("--test", action="store_true", help="Run in test mode")
    parser.add_argument("--iterations", type=int, default=None, help="Max iterations (test mode)")
    args = parser.parse_args()

    setup_logging()

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    symbols = SYMBOLS if args.symbols is None else [s.strip() for s in args.symbols.split(",")]

    run(symbols=symbols, test_mode=args.test, max_iterations=args.iterations)


if __name__ == "__main__":
    main()
