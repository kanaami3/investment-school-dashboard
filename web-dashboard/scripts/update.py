#!/usr/bin/env python3
"""投資塾 マーケット・ダッシュボード ─ データ更新スクリプト v2

実行内容:
1. 主要指数(日米)の取得
2. ユニバース約400銘柄の価格・出来高・財務取得
3. テクニカル(RSI, SMA, ボラ)とスコア(Magic Formula, F-Score, Z-Score, JT Momentum)を計算
4. セクター集計とブレダス指標を算出
5. data/*.json として静的サイト向けにシリアライズ
6. data/stocks/<TICKER>.json で個別銘柄ページの詳細データを保存

呼び出し: python scripts/update.py
依存: yfinance, pandas, requests
"""
from __future__ import annotations

import json
import math
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd
import yfinance as yf

sys.path.insert(0, str(Path(__file__).resolve().parent))
import scoring  # noqa: E402
import universe  # noqa: E402

JST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
STOCKS_DIR = DATA / "stocks"
DATA.mkdir(exist_ok=True)
STOCKS_DIR.mkdir(exist_ok=True)

INDICES = {
    "nikkei": ("^N225", "日経平均"),
    "topix": ("^TPX", "TOPIX"),
    "sp500": ("^GSPC", "S&P 500"),
    "nasdaq": ("^IXIC", "NASDAQ"),
    "dow": ("^DJI", "Dow Jones"),
    "russell": ("^RUT", "Russell 2000"),
    "usdjpy": ("JPY=X", "USD/JPY"),
}


def now_jst() -> str:
    return datetime.now(JST).strftime("%Y-%m-%d %H:%M")


def safe(x) -> Optional[float]:
    return scoring.safe(x)


# ---------------------------------------------------------------
# 1. 指数取得
# ---------------------------------------------------------------
def fetch_index(ticker: str, name: str) -> dict:
    try:
        h = yf.Ticker(ticker).history(period="1mo", auto_adjust=False)
    except Exception as e:
        print(f"[idx] {ticker}: {e}", file=sys.stderr)
        return {"ticker": ticker, "name": name, "close": None, "change": None, "pct": None, "history": []}
    if h.empty:
        return {"ticker": ticker, "name": name, "close": None, "change": None, "pct": None, "history": []}
    last = h.iloc[-1]
    prev = h.iloc[-2] if len(h) >= 2 else last
    close = safe(last["Close"])
    pclose = safe(prev["Close"])
    change = (close - pclose) if (close is not None and pclose is not None) else None
    pct = (change / pclose * 100) if (change is not None and pclose) else None
    history = [
        {"d": d.strftime("%Y-%m-%d"), "c": safe(r["Close"])}
        for d, r in h.tail(22).iterrows()
    ]
    return {"ticker": ticker, "name": name, "close": close, "change": change, "pct": pct, "history": history}


# ---------------------------------------------------------------
# 2. 個別銘柄
# ---------------------------------------------------------------
@dataclass
class StockRow:
    ticker: str
    name: str
    market: str               # "JP" or "US"
    sector: Optional[str]
    industry: Optional[str]
    close: Optional[float]
    currency: Optional[str]
    market_cap: Optional[float]
    # リターン
    ret_1d: Optional[float]
    ret_1w: Optional[float]
    ret_1m: Optional[float]
    ret_3m: Optional[float]
    ret_6m: Optional[float]
    ret_1y: Optional[float]
    # テクニカル
    rsi14: Optional[float]
    sma50: Optional[float]
    sma200: Optional[float]
    above_sma50: Optional[bool]
    golden_cross: Optional[bool]
    high52w: Optional[float]
    pct_off_high52w: Optional[float]   # 52週高値からの乖離 %
    vol_ratio: Optional[float]         # 直近 / 20日平均
    vol_60d: Optional[float]           # 年率ボラ %
    # ファンダ
    per: Optional[float]
    forward_pe: Optional[float]
    pbr: Optional[float]
    ps: Optional[float]                # PSR
    div_yield: Optional[float]         # %
    payout_ratio: Optional[float]
    roe: Optional[float]
    roa: Optional[float]
    op_margin: Optional[float]
    debt_to_equity: Optional[float]
    current_ratio: Optional[float]
    # スコア
    f_score: Optional[int]
    z_score: Optional[float]
    momentum_jt: Optional[float]       # JT 12-1
    magic_roc: Optional[float]
    magic_ey: Optional[float]
    magic_rank: Optional[int]


def fetch_one(ticker: str, market: str) -> Optional[StockRow]:
    try:
        t = yf.Ticker(ticker)
        h = t.history(period="14mo", auto_adjust=False)
        if h.empty or len(h) < 5:
            return None
        info = t.info or {}
    except Exception as e:
        print(f"[stk] {ticker}: {e}", file=sys.stderr)
        return None

    close_s = h["Close"]
    vol_s = h["Volume"]
    last = float(close_s.iloc[-1])

    def pct_back(n: int) -> Optional[float]:
        if len(close_s) <= n or close_s.iloc[-n - 1] == 0 or pd.isna(close_s.iloc[-n - 1]):
            return None
        return float((last / close_s.iloc[-n - 1] - 1) * 100)

    high52 = safe(close_s.tail(252).max()) if len(close_s) >= 60 else None
    off_high = ((last / high52 - 1) * 100) if (high52 and high52 > 0) else None

    vol_ratio = None
    if len(vol_s) >= 21:
        avg20 = vol_s.tail(21).iloc[:-1].mean()
        if avg20:
            vol_ratio = float(vol_s.iloc[-1] / avg20)

    sma50 = scoring.sma(close_s, 50)
    sma200 = scoring.sma(close_s, 200)
    rsi14 = scoring.rsi(close_s, 14)
    vol_60d = scoring.annualized_vol(close_s, 60)
    jt = scoring.jt_momentum(close_s)

    # ファンダの正規化
    dy = info.get("dividendYield")
    if dy and dy < 1:
        dy *= 100
    roe = info.get("returnOnEquity")
    if roe and abs(roe) < 5:
        roe *= 100
    roa = info.get("returnOnAssets")
    if roa and abs(roa) < 5:
        roa *= 100
    op_margin = info.get("operatingMargins")
    if op_margin and abs(op_margin) < 5:
        op_margin *= 100
    payout = info.get("payoutRatio")
    if payout and abs(payout) < 5:
        payout *= 100

    f5 = scoring.f_score_simple(info)
    z = scoring.z_score_simple(info)
    roc, ey = scoring.magic_formula_inputs(info)

    sector = info.get("sector") or universe.SECTOR_MAP.get(ticker)
    if market == "JP" and sector and sector.isascii():
        # 英語セクターを和訳（簡易）
        sector = {
            "Technology": "情報技術", "Financial Services": "金融",
            "Industrials": "産業", "Consumer Cyclical": "一般消費財",
            "Consumer Defensive": "生活必需品", "Healthcare": "ヘルスケア",
            "Communication Services": "通信サービス", "Energy": "エネルギー",
            "Utilities": "公益", "Real Estate": "不動産", "Basic Materials": "素材",
        }.get(sector, sector)

    return StockRow(
        ticker=ticker,
        name=info.get("shortName") or info.get("longName") or ticker,
        market=market,
        sector=sector,
        industry=info.get("industry"),
        close=last,
        currency=info.get("currency"),
        market_cap=safe(info.get("marketCap")),
        ret_1d=pct_back(1), ret_1w=pct_back(5), ret_1m=pct_back(21),
        ret_3m=pct_back(63), ret_6m=pct_back(126), ret_1y=pct_back(252),
        rsi14=rsi14,
        sma50=sma50, sma200=sma200,
        above_sma50=(last > sma50) if (sma50 is not None) else None,
        golden_cross=(sma50 > sma200) if (sma50 and sma200) else None,
        high52w=high52,
        pct_off_high52w=safe(off_high),
        vol_ratio=safe(vol_ratio),
        vol_60d=vol_60d,
        per=safe(info.get("trailingPE")),
        forward_pe=safe(info.get("forwardPE")),
        pbr=safe(info.get("priceToBook")),
        ps=safe(info.get("priceToSalesTrailing12Months")),
        div_yield=safe(dy),
        payout_ratio=safe(payout),
        roe=safe(roe), roa=safe(roa),
        op_margin=safe(op_margin),
        debt_to_equity=safe(info.get("debtToEquity")),
        current_ratio=safe(info.get("currentRatio")),
        f_score=f5,
        z_score=z,
        momentum_jt=jt,
        magic_roc=safe(roc), magic_ey=safe(ey),
        magic_rank=None,  # 後段で全銘柄ランキング後に埋める
    )


def fetch_stock_history(ticker: str) -> dict:
    """個別銘柄ページ用の1年分価格履歴。"""
    try:
        h = yf.Ticker(ticker).history(period="1y", auto_adjust=False)
    except Exception:
        return {"ticker": ticker, "history": []}
    if h.empty:
        return {"ticker": ticker, "history": []}
    return {
        "ticker": ticker,
        "history": [
            {"d": d.strftime("%Y-%m-%d"), "c": safe(r["Close"]), "v": safe(r["Volume"])}
            for d, r in h.iterrows()
        ],
    }


# ---------------------------------------------------------------
# 3. パイプライン本体
# ---------------------------------------------------------------
def fetch_universe_parallel() -> list[StockRow]:
    jobs = [(t, "JP") for t in universe.JP_TICKERS_FULL]
    jobs += [(t, "US") for t in universe.US_TICKERS]
    rows: list[StockRow] = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(fetch_one, t, m): (t, m) for t, m in jobs}
        for fut in as_completed(futures):
            r = fut.result()
            if r:
                rows.append(r)
    return rows


def compute_breadth(rows: list[StockRow]) -> dict:
    out = {"JP": {}, "US": {}}
    for mkt in ("JP", "US"):
        sub = [r for r in rows if r.market == mkt]
        n = len(sub)
        if n == 0:
            out[mkt] = {"count": 0}
            continue
        adv = sum(1 for r in sub if r.ret_1d is not None and r.ret_1d > 0)
        dec = sum(1 for r in sub if r.ret_1d is not None and r.ret_1d < 0)
        new_high = sum(1 for r in sub if r.pct_off_high52w is not None and r.pct_off_high52w > -2)
        above_50 = sum(1 for r in sub if r.above_sma50 is True)
        gc = sum(1 for r in sub if r.golden_cross is True)
        out[mkt] = {
            "count": n,
            "advancers": adv,
            "decliners": dec,
            "ad_ratio": (adv / dec) if dec else None,
            "new_highs_pct": (new_high / n * 100),
            "above_sma50_pct": (above_50 / n * 100),
            "golden_cross_pct": (gc / n * 100),
        }
    return out


def compute_sectors(rows: list[StockRow]) -> dict:
    """セクター別の(平均1d, 平均1w, 平均1m, 銘柄数, 中央値PER, 中央値ROE)。ヒートマップ用。"""
    by_market = {"JP": {}, "US": {}}
    for r in rows:
        if not r.sector:
            continue
        d = by_market.setdefault(r.market, {}).setdefault(r.sector, {
            "tickers": [], "rets_1d": [], "rets_1w": [], "rets_1m": [], "per": [], "roe": [],
        })
        d["tickers"].append(r.ticker)
        for k, v in [("rets_1d", r.ret_1d), ("rets_1w", r.ret_1w), ("rets_1m", r.ret_1m),
                     ("per", r.per), ("roe", r.roe)]:
            if v is not None:
                d[k].append(v)
    # 集計
    out = {}
    for mkt, sectors in by_market.items():
        out[mkt] = []
        for sec, d in sectors.items():
            if len(d["tickers"]) < 2:
                continue
            def avg(xs): return sum(xs) / len(xs) if xs else None
            def med(xs): return float(pd.Series(xs).median()) if xs else None
            out[mkt].append({
                "sector": sec,
                "count": len(d["tickers"]),
                "avg_1d": avg(d["rets_1d"]),
                "avg_1w": avg(d["rets_1w"]),
                "avg_1m": avg(d["rets_1m"]),
                "median_per": med(d["per"]),
                "median_roe": med(d["roe"]),
                "tickers": d["tickers"][:30],
            })
        out[mkt].sort(key=lambda x: -(x["avg_1w"] or -1e9))
    return out


def assign_magic_ranks(rows: list[StockRow]) -> None:
    for mkt in ("JP", "US"):
        sub = [r for r in rows if r.market == mkt]
        # roc/ey 両方ある銘柄のみ対象
        cand = [{"ticker": r.ticker, "roc": r.magic_roc, "ey": r.magic_ey} for r in sub]
        ranks = scoring.magic_formula_rank(cand)
        for r in sub:
            r.magic_rank = ranks.get(r.ticker)


def write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1, default=str), encoding="utf-8")


def main() -> int:
    t0 = time.time()
    print(f"==> [{now_jst()}] starting update")

    print("==> indices")
    indices = {k: fetch_index(*v) for k, v in INDICES.items()}

    print(f"==> universe ({len(universe.JP_TICKERS_FULL)} JP + {len(universe.US_TICKERS)} US)")
    rows = fetch_universe_parallel()
    print(f"  fetched: {len(rows)}")

    assign_magic_ranks(rows)

    breadth = compute_breadth(rows)
    sectors = compute_sectors(rows)

    snapshot = {
        "generated_at": now_jst(),
        "indices": indices,
        "breadth": breadth,
        "universe_size": len(rows),
    }
    write_json(DATA / "snapshot.json", snapshot)
    write_json(DATA / "breadth.json", breadth)
    write_json(DATA / "sectors.json", sectors)

    # 銘柄DB
    write_json(DATA / "stocks.json", {
        "generated_at": now_jst(),
        "rows": [asdict(r) for r in rows],
    })

    # 個別銘柄ページ用に上位300の履歴を保存（時価総額順、APIコール削減）
    rows_with_cap = [r for r in rows if r.market_cap]
    rows_with_cap.sort(key=lambda r: -(r.market_cap or 0))
    targets = rows_with_cap[:300]
    print(f"==> per-stock history for top {len(targets)} by market cap")
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(fetch_stock_history, r.ticker): r for r in targets}
        for fut in as_completed(futs):
            r = futs[fut]
            data = fut.result()
            data["meta"] = asdict(r)
            (STOCKS_DIR / f"{r.ticker}.json").write_text(
                json.dumps(data, ensure_ascii=False, default=str), encoding="utf-8"
            )

    print(f"==> done in {time.time() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
