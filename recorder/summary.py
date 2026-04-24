"""週次サマリー生成スクリプト.

直近N日間のtick蓄積状況をシンボル別・日別に集計し、
Markdownレポートを `_logs/weekly_summary_YYYY-WNN.md` に書き出す。

使い方:
  python -m recorder.summary              # 直近7日
  python -m recorder.summary --days 7
  python -m recorder.summary --days 30    # 月次サマリ代わり

タスクスケジューラで毎週月曜早朝に実行する想定（scripts/install_summary_task.ps1）。
"""

from __future__ import annotations

import argparse
import io
import logging
import sys
from datetime import datetime, timedelta, timezone, date
from pathlib import Path
from collections import defaultdict

import pandas as pd


# cp932 だと em-dash や特殊記号で print が落ちるため UTF-8 でラップ
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from .config import DATA_ROOT, LOG_DIR, SYMBOLS


logger = logging.getLogger(__name__)


def _parse_parquet_date(pq: Path) -> date | None:
    """パス `.../{YYYY}/{MM}/{DD}.parquet` から日付を取り出す."""
    try:
        parts = pq.parts
        yyyy = int(parts[-3])
        mm = int(parts[-2])
        dd = int(parts[-1].replace(".parquet", ""))
        return date(yyyy, mm, dd)
    except Exception:
        return None


def collect_per_symbol_stats(
    start_date: date, end_date: date
) -> dict[str, dict]:
    """各シンボルの該当期間 tick集計."""
    per_symbol: dict[str, dict] = {}

    for sym in SYMBOLS:
        sym_dir = DATA_ROOT / sym
        stat = {
            "total_ticks": 0,
            "file_size": 0,
            "file_count": 0,
            "days": defaultdict(int),
            "first_ts": None,
            "last_ts": None,
        }

        if sym_dir.exists():
            for pq in sym_dir.rglob("*.parquet"):
                d = _parse_parquet_date(pq)
                if d is None or d < start_date or d > end_date:
                    continue
                try:
                    df = pd.read_parquet(pq)
                    n = len(df)
                    if n == 0:
                        continue
                    stat["total_ticks"] += n
                    stat["days"][d.isoformat()] += n
                    stat["file_size"] += pq.stat().st_size
                    stat["file_count"] += 1
                    if "time_msc" in df.columns:
                        t_min = df["time_msc"].min()
                        t_max = df["time_msc"].max()
                        if stat["first_ts"] is None or t_min < stat["first_ts"]:
                            stat["first_ts"] = int(t_min)
                        if stat["last_ts"] is None or t_max > stat["last_ts"]:
                            stat["last_ts"] = int(t_max)
                except Exception as e:
                    logger.warning(f"Failed to read {pq}: {e}")

        per_symbol[sym] = stat
    return per_symbol


def detect_anomalies(
    stats: dict[str, dict], days_covered: int
) -> list[str]:
    """異常検知ルール."""
    anomalies = []

    # 1. tick 0 のシンボル
    zero_syms = [k for k, v in stats.items() if v["total_ticks"] == 0]
    if zero_syms:
        anomalies.append(
            f"- **tick 0 のシンボル（{len(zero_syms)}個）**: {', '.join(zero_syms)}"
        )

    # 2. ファイル数が期待より極端に少ない（期間中の半分未満）
    expected_files_min = max(1, days_covered // 2)
    low_files = [
        k for k, v in stats.items()
        if 0 < v["total_ticks"] and v["file_count"] < expected_files_min
    ]
    if low_files:
        anomalies.append(
            f"- **ファイル数が少ないシンボル（<{expected_files_min}）**: {', '.join(low_files)}"
        )

    # 3. 日別で極端にtickが少ない日（ファイル内 tick 100 未満）
    # 実装簡略化：とりあえず省略（将来追加）

    return anomalies


def generate_markdown(
    stats: dict[str, dict],
    start_date: date,
    end_date: date,
    week_label: str,
) -> str:
    lines: list[str] = []
    lines.append(f"# Tick Recorder Weekly Summary - {week_label}")
    lines.append("")
    lines.append(f"- 期間: `{start_date.isoformat()}` 〜 `{end_date.isoformat()}`")
    lines.append(f"- 生成時刻 (UTC): `{datetime.now(timezone.utc).isoformat(timespec='seconds')}`")
    lines.append(f"- 対象シンボル数: {len(SYMBOLS)}")
    lines.append("")

    # Overall
    total_ticks = sum(s["total_ticks"] for s in stats.values())
    total_size = sum(s["file_size"] for s in stats.values())
    total_files = sum(s["file_count"] for s in stats.values())
    zero_syms = [k for k, v in stats.items() if v["total_ticks"] == 0]

    lines.append("## Overall")
    lines.append("")
    lines.append(f"- 総tick数: **{total_ticks:,}**")
    lines.append(f"- 総ファイル数: {total_files}")
    lines.append(f"- 総データサイズ: {total_size / 1024 / 1024:.1f} MB")
    days_covered = (end_date - start_date).days + 1
    lines.append(f"- 日数: {days_covered}日")
    if days_covered > 0:
        lines.append(f"- 1日平均: {total_ticks / days_covered:,.0f} tick/日")
    lines.append(f"- tick取得ゼロのシンボル: **{len(zero_syms)}** / {len(SYMBOLS)}")
    lines.append("")

    # Per symbol ranking
    lines.append("## シンボル別tick数（多い順）")
    lines.append("")
    lines.append("| # | Symbol | Ticks | Files | Size (MB) | 日平均 |")
    lines.append("|---|--------|------:|------:|----------:|------:|")
    ranked = sorted(stats.items(), key=lambda x: -x[1]["total_ticks"])
    for i, (sym, s) in enumerate(ranked, 1):
        daily_avg = s["total_ticks"] / max(1, s["file_count"]) if s["file_count"] > 0 else 0
        lines.append(
            f"| {i} | {sym} | {s['total_ticks']:,} | {s['file_count']} | "
            f"{s['file_size'] / 1024 / 1024:.2f} | {daily_avg:,.0f} |"
        )
    lines.append("")

    # Daily breakdown
    lines.append("## 日別合計（全シンボル合計）")
    lines.append("")
    daily: dict[str, int] = defaultdict(int)
    for s in stats.values():
        for d, n in s["days"].items():
            daily[d] += n
    lines.append("| 日付 | Ticks |")
    lines.append("|------|------:|")
    for d in sorted(daily.keys()):
        lines.append(f"| {d} | {daily[d]:,} |")
    lines.append("")

    # Anomaly detection
    lines.append("## 異常検知")
    lines.append("")
    anomalies = detect_anomalies(stats, days_covered)
    if not anomalies:
        lines.append("- 異常は検出されませんでした ✅")
    else:
        lines.extend(anomalies)
    lines.append("")

    # Disk info
    lines.append("## ストレージ情報")
    lines.append("")
    try:
        import shutil
        total, used, free = shutil.disk_usage(DATA_ROOT)
        lines.append(f"- Cドライブ総容量: {total / 1024**3:.1f} GB")
        lines.append(f"- 使用量: {used / 1024**3:.1f} GB")
        lines.append(f"- 空き: {free / 1024**3:.1f} GB")
        lines.append(f"- TickDataフォルダ: {_dir_size(DATA_ROOT) / 1024**3:.2f} GB")
    except Exception as e:
        lines.append(f"- 取得失敗: {e}")
    lines.append("")

    return "\n".join(lines)


def _dir_size(path: Path) -> int:
    total = 0
    for f in path.rglob("*"):
        if f.is_file():
            try:
                total += f.stat().st_size
            except Exception:
                pass
    return total


def main():
    parser = argparse.ArgumentParser(description="Tick recorder weekly summary generator.")
    parser.add_argument("--days", type=int, default=7, help="Last N days (default: 7)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

    end_date = datetime.now(timezone.utc).date()
    start_date = end_date - timedelta(days=args.days - 1)

    y, w, _ = start_date.isocalendar()
    week_label = f"{y}-W{w:02d}"

    logger.info(f"Collecting stats {start_date} - {end_date} ({args.days} days)")
    stats = collect_per_symbol_stats(start_date, end_date)
    report = generate_markdown(stats, start_date, end_date, week_label)

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    out_path = LOG_DIR / f"weekly_summary_{week_label}.md"
    out_path.write_text(report, encoding="utf-8")
    logger.info(f"Written: {out_path}")

    # コンソールにも出力
    print()
    print(report)


if __name__ == "__main__":
    main()
