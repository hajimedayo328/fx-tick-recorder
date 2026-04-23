"""MT5 接続のラッパー.

既に起動している MetaTrader 5 ターミナルにアタッチする前提。
再接続ロジック・シンボル有効化・tick取得を提供。
"""

from __future__ import annotations

import time
import logging
from datetime import datetime, timedelta
from typing import Any

import MetaTrader5 as mt5

from .config import RECONNECT_WAIT_SECONDS, MAX_CATCHUP_SECONDS


logger = logging.getLogger(__name__)


class MT5Client:
    """MT5 へのアタッチと tick 取得."""

    def __init__(self, symbols: list[str]):
        self.symbols = symbols
        self._last_tick_time_msc: dict[str, int] = {}
        self._connected = False

    # ========== 接続管理 ==========

    def connect(self) -> bool:
        """既存の MT5 ターミナルにアタッチする."""
        if not mt5.initialize():
            err = mt5.last_error()
            logger.error(f"MT5 initialize failed: {err}")
            self._connected = False
            return False

        self._connected = True
        info = mt5.terminal_info()
        ai = mt5.account_info()
        logger.info(
            f"MT5 connected: broker={info.company if info else 'N/A'}, "
            f"account={ai.login if ai else 'N/A'}, server={ai.server if ai else 'N/A'}"
        )
        return True

    def ensure_symbols(self) -> tuple[list[str], list[str]]:
        """全シンボルを Market Watch に追加して取得可能にする.

        戻り値: (成功したシンボル, 失敗したシンボル)
        """
        ok, missing = [], []
        for s in self.symbols:
            info = mt5.symbol_info(s)
            if info is None:
                missing.append(s)
                continue
            # Market Watch に無ければ追加
            if not info.visible:
                if not mt5.symbol_select(s, True):
                    missing.append(s)
                    continue
            ok.append(s)

        if missing:
            logger.warning(f"Missing symbols: {missing}")
        logger.info(f"Active symbols: {len(ok)}/{len(self.symbols)}")
        return ok, missing

    def reconnect(self) -> bool:
        """切断検知後に再接続を試みる."""
        logger.warning("MT5 reconnecting...")
        mt5.shutdown()
        self._connected = False
        time.sleep(RECONNECT_WAIT_SECONDS)
        return self.connect()

    def shutdown(self) -> None:
        if self._connected:
            mt5.shutdown()
            self._connected = False

    # ========== tick 取得 ==========

    def fetch_new_ticks(self, symbol: str) -> list[dict[str, Any]]:
        """対象シンボルの最新tickを、前回取得以降の分だけ返す.

        戻り値の各要素は dict: {time_msc, bid, ask, last, volume_real, flags}
        """
        now = datetime.now()

        # 初回は直近30秒から取り始める
        last_msc = self._last_tick_time_msc.get(symbol)
        if last_msc is None:
            from_time = now - timedelta(seconds=30)
        else:
            # msec -> datetime
            from_time = datetime.fromtimestamp(last_msc / 1000.0)
            # 極端な catchup を避ける
            if (now - from_time).total_seconds() > MAX_CATCHUP_SECONDS:
                from_time = now - timedelta(seconds=MAX_CATCHUP_SECONDS)

        ticks = mt5.copy_ticks_range(symbol, from_time, now, mt5.COPY_TICKS_ALL)
        if ticks is None:
            err = mt5.last_error()
            logger.warning(f"{symbol}: copy_ticks_range failed: {err}")
            return []

        if len(ticks) == 0:
            return []

        # time_msc で前回以降のものだけに絞る（重複防止）
        new_ticks = []
        for t in ticks:
            tmsc = int(t["time_msc"])
            if last_msc is not None and tmsc <= last_msc:
                continue
            new_ticks.append({
                "time_msc": tmsc,
                "bid": float(t["bid"]),
                "ask": float(t["ask"]),
                "last": float(t["last"]),
                "volume_real": float(t["volume_real"]),
                "flags": int(t["flags"]),
            })

        if new_ticks:
            self._last_tick_time_msc[symbol] = new_ticks[-1]["time_msc"]

        return new_ticks

    @property
    def is_connected(self) -> bool:
        return self._connected
