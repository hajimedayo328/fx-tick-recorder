"""tick レコーダーの設定."""

from __future__ import annotations

import os
from pathlib import Path


# ========== 対象シンボル（31個） ==========

SYMBOLS: list[str] = [
    # FX Major (7)
    "EURUSD", "USDJPY", "GBPUSD", "AUDUSD",
    "USDCHF", "USDCAD", "NZDUSD",
    # FX Cross (3)
    "EURJPY", "GBPJPY", "EURGBP",
    # FX EM (3)
    "USDTRY", "USDHUF", "EURTRY",
    # Metal (2)
    "XAUUSD", "XAGUSD",
    # Crypto (2)
    "BTCUSD", "ETHUSD",
    # Energy (2)
    "USOUSD", "UKOUSD",
    # Index US (4)
    "SP500.r", "NAS100.r", "DJ30.r", "US2000.r",
    # Index EU (3)
    "GER40.r", "UK100.r", "FRA40.r",
    # Index JP (1)
    "Nikkei225",
    # Index CN (1)
    "CHINA50.r",
    # Special (2)
    "USDX.r", "VIX.r",
    # === 2026/4/24 Added ===
    # US Stocks Mag7 subset (5): NVDA, GOOGL, AMZN are not on Vantage
    "AAPL", "MSFT", "GOOG", "META", "TSLA",
    # Rates (3): US10y, German Bund 10y, UK 10y
    "USNote10Y", "EUB10Y", "LongGilt",
    # Commodity (2): Copper, Natural Gas
    "COPPER-Cr", "NG-Cr",
]

assert len(SYMBOLS) > 0, "SYMBOLS is empty"
N_SYMBOLS: int = len(SYMBOLS)


# ========== ファイル保存先 ==========

DATA_ROOT: Path = Path(os.environ.get("TICK_DATA_ROOT", r"C:\TickData"))
LOG_DIR: Path = DATA_ROOT / "_logs"
HEARTBEAT_FILE: Path = LOG_DIR / "heartbeat.txt"
LOG_FILE: Path = LOG_DIR / "recorder.log"


# ========== 動作パラメータ ==========

# メインループの間隔（秒）: 各シンボルの新tickを取りに行く頻度
POLL_INTERVAL_SECONDS: float = 1.0

# Parquet に書き出す間隔（秒）
FLUSH_INTERVAL_SECONDS: int = 300  # 5分

# 1ポーリングで取るtickの最大時間範囲（秒）
# 通常は直前のpoll時刻から現在までだが、起動直後や欠損時にバッファとして使う
MAX_CATCHUP_SECONDS: int = 3600  # 1時間

# MT5切断時の再接続リトライ間隔（秒）
RECONNECT_WAIT_SECONDS: int = 10

# ハートビート更新間隔（秒）
HEARTBEAT_INTERVAL_SECONDS: int = 60

# Parquet 圧縮方式
PARQUET_COMPRESSION: str = "zstd"  # zstd / snappy / gzip


# ========== ユーティリティ ==========

def get_parquet_path(symbol: str, date_str: str) -> Path:
    """YYYY-MM-DD 形式の日付文字列から Parquet のパスを返す.

    例: get_parquet_path("EURUSD", "2026-04-24")
        -> C:\\TickData\\EURUSD\\2026\\04\\24.parquet
    """
    year, month, day = date_str.split("-")
    # シンボル名の '.' は Windows のフォルダ名で問題ないが、念のためそのまま使う
    return DATA_ROOT / symbol / year / month / f"{day}.parquet"


def ensure_dirs() -> None:
    """必要なディレクトリを事前に作成."""
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    for sym in SYMBOLS:
        (DATA_ROOT / sym).mkdir(parents=True, exist_ok=True)
