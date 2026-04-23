"""ヘルスチェック・ログ出力."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from .config import HEARTBEAT_FILE, LOG_FILE, LOG_DIR


def setup_logging(level: int = logging.INFO) -> None:
    """ロガー初期化. ファイル + コンソール両方へ出力."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    logging.basicConfig(
        level=level,
        format=fmt,
        handlers=[
            logging.FileHandler(LOG_FILE, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


def write_heartbeat(stats: dict[str, int], buffer_size: int, last_flush_at: str) -> None:
    """ハートビートファイルに現在の状態を記録."""
    HEARTBEAT_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "total_written_by_symbol": stats,
        "total_written_sum": sum(stats.values()),
        "buffer_size_sum": buffer_size,
        "last_flush_at": last_flush_at,
    }
    HEARTBEAT_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
