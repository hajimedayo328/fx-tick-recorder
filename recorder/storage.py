"""tick データの Parquet 保存.

Parquet は追記書き込みができないため、以下の戦略:
  - 日次ファイル（シンボル × 日付ごと）に全 tick を保存
  - メモリ上のバッファに蓄積
  - 定期的にバッファ分を既存ファイルと結合して上書き保存
  - 日付を跨いだら新ファイルに切り替え
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from .config import get_parquet_path, PARQUET_COMPRESSION


logger = logging.getLogger(__name__)


# Parquet のスキーマ（全シンボル共通）
TICK_SCHEMA = pa.schema([
    ("time_msc", pa.int64()),
    ("bid", pa.float64()),
    ("ask", pa.float64()),
    ("last", pa.float64()),
    ("volume_real", pa.float64()),
    ("flags", pa.uint32()),
])


class TickStorage:
    """シンボルごとに日次 Parquet を書き込む."""

    def __init__(self):
        # バッファ: {symbol: [tick_dict, ...]}
        self._buffer: dict[str, list[dict[str, Any]]] = {}
        # 書き込み統計: {symbol: 累計tick数}
        self._total_written: dict[str, int] = {}

    def append_ticks(self, symbol: str, ticks: list[dict[str, Any]]) -> None:
        """バッファにtickを追加."""
        if not ticks:
            return
        if symbol not in self._buffer:
            self._buffer[symbol] = []
        self._buffer[symbol].extend(ticks)

    def buffer_size(self, symbol: str | None = None) -> int:
        if symbol is not None:
            return len(self._buffer.get(symbol, []))
        return sum(len(v) for v in self._buffer.values())

    def flush_all(self) -> dict[str, int]:
        """全シンボルのバッファをParquetに書き出し. 書き出した件数を返す."""
        today = datetime.now(timezone.utc).date().isoformat()  # UTC基準で日付管理
        written = {}
        for symbol, buf in list(self._buffer.items()):
            if not buf:
                continue
            try:
                n = self._flush_symbol(symbol, today, buf)
                written[symbol] = n
                self._buffer[symbol] = []  # 書き出し後クリア
                self._total_written[symbol] = self._total_written.get(symbol, 0) + n
            except Exception as e:
                logger.error(f"{symbol}: flush failed: {e}", exc_info=True)
                # バッファはクリアしない（次回再試行）
        return written

    def _flush_symbol(self, symbol: str, date_str: str, ticks: list[dict]) -> int:
        """1シンボル分のバッファをParquet化.

        既存ファイルがあれば追記（= 読み込んで結合して上書き）。
        """
        path = get_parquet_path(symbol, date_str)
        path.parent.mkdir(parents=True, exist_ok=True)

        new_df = pd.DataFrame(ticks)

        # 既存ファイルがあれば読み込んで結合
        if path.exists():
            try:
                existing = pd.read_parquet(path)
                combined = pd.concat([existing, new_df], ignore_index=True)
                # time_msc で重複除去（保険）
                combined = combined.drop_duplicates(subset=["time_msc"], keep="last")
                combined = combined.sort_values("time_msc").reset_index(drop=True)
            except Exception as e:
                logger.error(f"{symbol}: existing parquet read failed, overwriting: {e}")
                combined = new_df
        else:
            combined = new_df.sort_values("time_msc").reset_index(drop=True)

        # 書き出し
        table = pa.Table.from_pandas(combined, schema=TICK_SCHEMA, preserve_index=False)
        pq.write_table(table, path, compression=PARQUET_COMPRESSION)

        return len(ticks)

    def get_stats(self) -> dict[str, int]:
        """累計書き込みtick数."""
        return dict(self._total_written)
