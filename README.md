# fx-tick-recorder

Vantage MT5 から 31 シンボルの tick を常時記録するレコーダー。

卒論素材として**動的相関ネットワーク・連結性指標・ジャンプ伝播**などの研究用データを蓄積する。
バックテスト用の秒〜ミリ秒解像度データは、ブローカー側で保存されないため、**自分で蓄積するしかない**。

## 対象シンボル（31）

| カテゴリ | 数 | 内訳 |
|----------|----|------|
| FX Major | 7 | EURUSD, USDJPY, GBPUSD, AUDUSD, USDCHF, USDCAD, NZDUSD |
| FX Cross | 3 | EURJPY, GBPJPY, EURGBP |
| FX EM | 3 | USDTRY, USDHUF, EURTRY |
| Metal | 2 | XAUUSD, XAGUSD |
| Crypto | 2 | BTCUSD, ETHUSD |
| Energy | 2 | USOUSD (WTI), UKOUSD (Brent) |
| Index US | 4 | SP500.r, NAS100.r, DJ30.r, US2000.r |
| Index EU | 3 | GER40.r, UK100.r, FRA40.r |
| Index JP | 1 | Nikkei225 |
| Index CN | 1 | CHINA50.r |
| Special | 2 | USDX.r (USD Index), VIX.r (Volatility Index) |

## データ形式

Parquet（zstd圧縮）。シンボル × 日別に 1 ファイル。

```
C:\TickData\
  EURUSD\2026\04\24.parquet
  XAUUSD\2026\04\24.parquet
  ...
  _logs\
    recorder.log
    heartbeat.txt
```

1 tick のスキーマ:
| 列 | 型 | 説明 |
|----|----|------|
| time_msc | int64 | ミリ秒 UNIX タイムスタンプ |
| bid | float64 | 買値 |
| ask | float64 | 売値 |
| last | float64 | 最終取引価格 |
| volume_real | float64 | 出来高 |
| flags | uint32 | tick フラグ（bid更新/ask更新/last更新 など） |

## 使い方

### 前提

- Windows（MT5 が動く環境）
- Python 3.10+
- MetaTrader 5 がインストールされ、ログイン済み
- pandas, pyarrow, MetaTrader5 パッケージ

### セットアップ

```bash
pip install -r requirements.txt
```

### 実行

```bash
# 全 31 シンボルを常時記録
python -m recorder.main

# テスト実行（10 イテレーションで終了）
python -m recorder.main --test --iterations 10

# 特定シンボルだけ
python -m recorder.main --symbols EURUSD,XAUUSD
```

### 保存先変更

環境変数 `TICK_DATA_ROOT` で上書き可能（デフォルト `C:\TickData`）。

```bash
set TICK_DATA_ROOT=D:\TickData
python -m recorder.main
```

## 動作概要

```
[MT5 Terminal]
      |  copy_ticks_range (1秒おき)
      v
[MT5Client]  新tickのみ抽出
      |
      v
[TickStorage]  メモリバッファ
      |  5分ごと
      v
[Parquet]  既存ファイル + 新tick → 上書き
```

- **ポーリング間隔**: 1秒
- **Parquet flush**: 5分ごと
- **ハートビート**: 1分ごと `_logs/heartbeat.txt` に状態記録
- **MT5切断時**: 10秒待機後に自動再接続
- **Ctrl+C**: 残バッファを flush してから安全終了

## データ量試算

- 1 シンボル平均: 約 6.5 MB/日
- 31 シンボル合計: **約 200 MB/日**
- **年間約 73 GB**（Parquet zstd 圧縮込み）

## 関連

- 研究用途: 動的相関ネットワーク、Diebold-Yilmaz 連結性、Hawkes 自己励起
- 運用 VPS: ABLENET Windows Server 2022
