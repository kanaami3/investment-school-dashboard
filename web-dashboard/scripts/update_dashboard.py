#!/usr/bin/env python3
"""
Investment School Daily Market Dashboard Generator
==================================================

GitHub Actions から毎営業日朝 7:30 JST に呼び出され、
Yahoo Finance (yfinance) からデータを取得して
リポジトリ直下の index.html を再生成する。

ロジック概要:
- 主要指数とFXの当日値・5日推移
- ウォッチリスト銘柄 (日米) の RSI / MA / 出来高 / リターン → モメンタム判定
- ファンダメンタル (PER / PBR / 配当利回り / ROE) → 4軸の割安スクリーニング
- S&P500主要構成銘柄から週間上昇率トップ5を抽出
"""
from __future__ import annotations

import json
import math
import os
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import yfinance as yf
from jinja2 import Template

# ------------------------------------------------------------
# 定数 / ウォッチリスト
# ------------------------------------------------------------
JST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

INDICES = {
    "nikkei": ("^N225", "日経平均"),
    "topix": ("^TPX", "TOPIX"),
    "sp500": ("^GSPC", "S&P 500"),
    "nasdaq": ("^IXIC", "NASDAQ"),
    "dow": ("^DJI", "Dow Jones"),
    "usdjpy": ("JPY=X", "USD/JPY"),
}

# 日本株モメンタム候補（出来高が大きく、テクニカルが効きやすい大型）
JP_MOMENTUM = [
    "9432.T", "8035.T", "6857.T", "6920.T",  # NTT, 東京エレクトロン, アドバンテスト, レーザーテック
    "7203.T", "9984.T", "8001.T", "6758.T",  # トヨタ, ソフトバンクG, 伊藤忠, ソニーG
    "6098.T", "4063.T",                       # リクルート, 信越化学
]

# 米国株モメンタム候補
US_MOMENTUM = [
    "ORCL", "AAPL", "CRM", "NVDA", "MU",
    "META", "GOOGL", "AVGO", "AMD", "TSLA",
    "MRK", "LLY",
]

# 割安スクリーニング候補（教育目的の固定リスト）
JP_VALUE_UNIVERSE = [
    "9104.T", "9107.T", "7267.T", "6963.T",   # 商船三井, 川崎汽船, ホンダ, ローム
    "9501.T", "9503.T", "9508.T",              # 東電HD, 関西電力, 九州電力
    "8316.T", "8306.T", "8411.T",              # 三井住友FG, MUFG, みずほFG
    "4452.T", "8593.T", "8001.T", "8058.T",    # 花王, 三菱HCキャピタル, 伊藤忠, 三菱商事
    "9433.T", "7974.T", "6954.T", "8031.T",    # KDDI, 任天堂, ファナック, 三井物産
]

US_VALUE_UNIVERSE = [
    "GM", "F", "MU", "LULU",                   # 自動車・半導体・小売
    "JNJ", "PG", "KO", "MRK", "ABBV", "PEP",   # 連続増配の代表
    "BAC", "C", "MET", "CVS",                  # 金融・ヘルスケア
    "GOOGL", "META", "BRK-B",                  # 現金リッチ
]

# S&P 500 週間上昇率を確認するユニバース（流動性大型）
SP500_TOP_UNIVERSE = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "AVGO",
    "ORCL", "CRM", "ADBE", "AMD", "INTC", "MU", "QCOM", "TXN",
    "JPM", "BAC", "WFC", "GS", "MS", "C",
    "JNJ", "LLY", "PFE", "MRK", "ABBV", "UNH", "TMO", "DHR",
    "XOM", "CVX", "COP", "WMT", "COST", "HD", "MCD", "NKE",
    "BA", "CAT", "DE", "GE", "HON", "LMT", "RTX",
    "DIS", "NFLX", "PYPL", "SHOP", "UBER",
]


# ------------------------------------------------------------
# データ取得ヘルパー
# ------------------------------------------------------------
@dataclass
class IndexSnapshot:
    code: str
    name: str
    close: float | None
    change: float | None
    pct: float | None
    history: list[dict]


@dataclass
class StockMetrics:
    ticker: str
    name: str
    close: float | None
    week_pct: float | None
    rsi14: float | None
    sma50: float | None
    sma200: float | None
    above_sma50: bool | None
    golden_cross: bool | None
    vol_ratio: float | None        # 直近出来高 / 20日平均
    per: float | None
    pbr: float | None
    div_yield: float | None        # %
    roe: float | None              # %
    market_cap: float | None       # USD or JPY

    def asdict(self) -> dict:
        return asdict(self)


def safe_float(x) -> float | None:
    try:
        if x is None:
            return None
        f = float(x)
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def fetch_index(ticker: str, name: str) -> IndexSnapshot:
    try:
        hist = yf.Ticker(ticker).history(period="10d", auto_adjust=False)
    except Exception as e:
        print(f"[warn] index fetch failed {ticker}: {e}", file=sys.stderr)
        return IndexSnapshot(ticker, name, None, None, None, [])
    if hist.empty:
        return IndexSnapshot(ticker, name, None, None, None, [])
    last = hist.iloc[-1]
    prev = hist.iloc[-2] if len(hist) >= 2 else last
    history = [
        {"date": d.strftime("%-m/%-d"), "close": safe_float(r["Close"])}
        for d, r in hist.tail(5).iterrows()
    ]
    close = safe_float(last["Close"])
    pclose = safe_float(prev["Close"])
    change = (close - pclose) if (close is not None and pclose is not None) else None
    pct = (change / pclose * 100) if (change is not None and pclose) else None
    return IndexSnapshot(ticker, name, close, change, pct, history)


def compute_rsi(series: pd.Series, period: int = 14) -> float | None:
    if len(series) < period + 1:
        return None
    delta = series.diff().dropna()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = -delta.clip(upper=0).rolling(period).mean()
    rs = gain / loss.replace(0, pd.NA)
    rsi = 100 - (100 / (1 + rs))
    val = rsi.iloc[-1]
    return safe_float(val)


def fetch_stock(ticker: str) -> StockMetrics | None:
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="1y", auto_adjust=False)
        if hist.empty:
            return None
        info = t.info or {}
    except Exception as e:
        print(f"[warn] stock fetch failed {ticker}: {e}", file=sys.stderr)
        return None

    close_series = hist["Close"]
    vol_series = hist["Volume"]
    close = safe_float(close_series.iloc[-1])
    week_pct = None
    if len(close_series) >= 6:
        c5 = close_series.iloc[-6]
        if c5:
            week_pct = float((close_series.iloc[-1] / c5 - 1) * 100)

    sma50 = safe_float(close_series.rolling(50).mean().iloc[-1]) if len(close_series) >= 50 else None
    sma200 = safe_float(close_series.rolling(200).mean().iloc[-1]) if len(close_series) >= 200 else None
    above_sma50 = (close > sma50) if (close and sma50) else None
    gc = (sma50 > sma200) if (sma50 and sma200) else None

    vol_ratio = None
    if len(vol_series) >= 21:
        avg20 = vol_series.tail(21).iloc[:-1].mean()
        if avg20:
            vol_ratio = float(vol_series.iloc[-1] / avg20)

    rsi14 = compute_rsi(close_series, 14)

    dy = info.get("dividendYield")
    if dy is not None and dy < 1:  # yfinanceは0.045の様な小数
        dy = dy * 100
    roe = info.get("returnOnEquity")
    if roe is not None and abs(roe) < 5:
        roe = roe * 100

    name = info.get("shortName") or info.get("longName") or ticker
    return StockMetrics(
        ticker=ticker,
        name=name,
        close=close,
        week_pct=week_pct,
        rsi14=rsi14,
        sma50=sma50,
        sma200=sma200,
        above_sma50=above_sma50,
        golden_cross=gc,
        vol_ratio=vol_ratio,
        per=safe_float(info.get("trailingPE")),
        pbr=safe_float(info.get("priceToBook")),
        div_yield=safe_float(dy),
        roe=safe_float(roe),
        market_cap=safe_float(info.get("marketCap")),
    )


def fetch_universe(tickers: list[str]) -> list[StockMetrics]:
    out: list[StockMetrics] = []
    for tk in tickers:
        m = fetch_stock(tk)
        if m:
            out.append(m)
    return out


# ------------------------------------------------------------
# スクリーニング
# ------------------------------------------------------------
def rank_momentum(stocks: list[StockMetrics], n: int = 5) -> list[StockMetrics]:
    """RSIが過熱しすぎず(45-72)、SMA50超え、出来高拡大している順に並べる。"""
    def score(s: StockMetrics) -> float:
        if s.rsi14 is None or s.week_pct is None:
            return -1e9
        if not (40 <= s.rsi14 <= 75):
            return -1e9
        sma_bonus = 5 if s.above_sma50 else 0
        gc_bonus = 5 if s.golden_cross else 0
        vol_bonus = (s.vol_ratio or 1) * 2
        return (s.week_pct or 0) + sma_bonus + gc_bonus + vol_bonus
    return sorted(stocks, key=score, reverse=True)[:n]


def rank_value_per_pbr(stocks: list[StockMetrics], n: int = 5) -> list[StockMetrics]:
    f = [s for s in stocks if s.per and 0 < s.per < 15 and s.pbr and s.pbr < 1.2]
    return sorted(f, key=lambda s: (s.per * s.pbr))[:n]


def rank_dividend(stocks: list[StockMetrics], n: int = 5) -> list[StockMetrics]:
    f = [s for s in stocks if s.div_yield and s.div_yield >= 2.5]
    return sorted(f, key=lambda s: -s.div_yield)[:n]


def rank_quality_value(stocks: list[StockMetrics], n: int = 5) -> list[StockMetrics]:
    f = [s for s in stocks if s.roe and s.roe >= 10 and s.pbr and s.pbr < 2.0]
    return sorted(f, key=lambda s: -(s.roe / max(s.pbr, 0.1)))[:n]


def rank_weekly_gainers(stocks: list[StockMetrics], n: int = 5) -> list[StockMetrics]:
    return sorted([s for s in stocks if s.week_pct is not None], key=lambda s: -s.week_pct)[:n]


# ------------------------------------------------------------
# レンダリング
# ------------------------------------------------------------
HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>投資塾 マーケット・ダッシュボード</title>
<style>
:root { color-scheme: light; }
body { margin:0; background:#fbfaf7; color:#1f2937; font-family:-apple-system,BlinkMacSystemFont,"Helvetica Neue","Hiragino Kaku Gothic ProN","Yu Gothic",sans-serif; line-height:1.55; }
.wrap { max-width:1100px; margin:0 auto; padding:18px 22px 60px; }
h1 { font-size:24px; font-weight:600; margin:4px 0 2px; }
h2 { font-size:17px; font-weight:600; margin:30px 0 10px; padding-bottom:6px; border-bottom:1px solid #e7e5dc; }
h3 { font-size:14px; font-weight:600; margin:18px 0 8px; color:#374151; }
.meta { color:#6b7280; font-size:12px; margin-bottom:14px; }
.grid-3 { display:grid; grid-template-columns:repeat(auto-fit,minmax(240px,1fr)); gap:12px; }
.grid-2 { display:grid; grid-template-columns:repeat(auto-fit,minmax(420px,1fr)); gap:16px; }
.card { background:#fff; border:1px solid #e7e5dc; border-radius:10px; padding:14px 16px; }
.stat-label { font-size:11px; color:#6b7280; letter-spacing:.04em; text-transform:uppercase; }
.stat-value { font-size:22px; font-weight:600; margin-top:4px; }
.up { color:#117a3d; font-weight:500; }
.down { color:#b3261e; font-weight:500; }
.flat { color:#6b7280; font-weight:500; }
table { width:100%; border-collapse:collapse; font-size:13px; }
th,td { text-align:left; padding:8px 10px; border-bottom:1px solid #eee9dc; }
th { font-weight:500; color:#6b7280; font-size:11px; text-transform:uppercase; letter-spacing:.04em; background:#faf8f1; }
td.num { text-align:right; font-variant-numeric:tabular-nums; }
.pill { display:inline-block; padding:2px 8px; border-radius:999px; font-size:11px; font-weight:500; }
.pill-jp { background:#fde7e7; color:#962020; }
.pill-us { background:#dde8f7; color:#1d3a73; }
.pill-mom { background:#fff0d5; color:#7a4a09; }
.pill-val { background:#e2efde; color:#2c5e1a; }
.note { font-size:12px; color:#6b7280; margin-top:8px; }
.footer { color:#9ca3af; font-size:11px; margin-top:36px; text-align:center; }
.chart-wrap { position:relative; width:100%; height:240px; margin-top:8px; }
@media (max-width:720px) { .grid-2 { grid-template-columns:1fr; } }
</style>
</head>
<body>
<div class="wrap">
  <h1>投資塾 マーケット・ダッシュボード</h1>
  <div class="meta">最終更新: {{ now }} (JST) ／ データソース: Yahoo Finance</div>

  <h2>1. 市場サマリ（日本・米国）</h2>
  <div class="grid-3">
    {% for key, idx in indices.items() %}
    <div class="card">
      <div class="stat-label">
        <span class="pill {{ 'pill-jp' if key in ['nikkei','topix','usdjpy'] else 'pill-us' }}">
          {{ 'JP' if key in ['nikkei','topix','usdjpy'] else 'US' }}
        </span> {{ idx.name }}
      </div>
      <div class="stat-value">{{ fmt_num(idx.close) }}</div>
      <div class="{{ 'up' if (idx.pct or 0) > 0 else ('down' if (idx.pct or 0) < 0 else 'flat') }}">
        {{ fmt_signed(idx.change) }} ({{ fmt_signed_pct(idx.pct) }})
      </div>
    </div>
    {% endfor %}
  </div>

  <h3>主要指数 5日推移</h3>
  <div class="card"><div class="chart-wrap">
    <canvas id="indexChart" role="img" aria-label="日経平均・S&P500・NASDAQの直近5営業日推移"></canvas>
  </div></div>

  <h2>2. S&P 500 ウォッチリスト 週間上昇率ランキング</h2>
  <div class="card">
    <table>
      <thead><tr><th>#</th><th>Ticker</th><th>銘柄</th><th class="num">週間騰落率</th><th class="num">RSI(14)</th><th class="num">出来高比</th></tr></thead>
      <tbody>
      {% for s in sp500_top %}
        <tr>
          <td>{{ loop.index }}</td>
          <td><b>{{ s.ticker }}</b></td>
          <td>{{ s.name }}</td>
          <td class="num up">{{ fmt_signed_pct(s.week_pct) }}</td>
          <td class="num">{{ fmt_num(s.rsi14, 1) }}</td>
          <td class="num">{{ fmt_num(s.vol_ratio, 2) }}x</td>
        </tr>
      {% endfor %}
      </tbody>
    </table>
    <div class="note">対象: 主要S&P500構成銘柄 約{{ sp500_n }}銘柄。週間騰落率は直近5営業日。</div>
  </div>

  <h2>3. モメンタム銘柄</h2>
  <div class="grid-2">
    <div class="card">
      <h3><span class="pill pill-jp">JP</span> 日本株モメンタム <span class="pill pill-mom">RSI / MA / Vol</span></h3>
      <table>
        <thead><tr><th>コード</th><th>銘柄</th><th class="num">週間</th><th class="num">RSI</th><th class="num">出来高比</th><th>シグナル</th></tr></thead>
        <tbody>
        {% for s in jp_momentum %}
          <tr>
            <td>{{ s.ticker.replace('.T','') }}</td>
            <td>{{ s.name }}</td>
            <td class="num {{ 'up' if (s.week_pct or 0) >0 else 'down' }}">{{ fmt_signed_pct(s.week_pct) }}</td>
            <td class="num">{{ fmt_num(s.rsi14,1) }}</td>
            <td class="num">{{ fmt_num(s.vol_ratio,2) }}x</td>
            <td>{{ momentum_label(s) }}</td>
          </tr>
        {% endfor %}
        </tbody>
      </table>
    </div>
    <div class="card">
      <h3><span class="pill pill-us">US</span> 米国株モメンタム <span class="pill pill-mom">RSI / MA / Vol</span></h3>
      <table>
        <thead><tr><th>Ticker</th><th>銘柄</th><th class="num">週間</th><th class="num">RSI</th><th class="num">出来高比</th><th>シグナル</th></tr></thead>
        <tbody>
        {% for s in us_momentum %}
          <tr>
            <td><b>{{ s.ticker }}</b></td>
            <td>{{ s.name }}</td>
            <td class="num {{ 'up' if (s.week_pct or 0) >0 else 'down' }}">{{ fmt_signed_pct(s.week_pct) }}</td>
            <td class="num">{{ fmt_num(s.rsi14,1) }}</td>
            <td class="num">{{ fmt_num(s.vol_ratio,2) }}x</td>
            <td>{{ momentum_label(s) }}</td>
          </tr>
        {% endfor %}
        </tbody>
      </table>
    </div>
  </div>

  <h2>4. 割安銘柄スクリーニング（4軸）</h2>
  <h3><span class="pill pill-jp">JP</span> 日本株</h3>
  <div class="grid-2">
    {{ render_value_card("A. 低PER × 低PBR", jp_value_per_pbr, "per_pbr") }}
    {{ render_value_card("B. 高配当", jp_div, "div") }}
    {{ render_value_card("C. ROE高 × PBR低", jp_quality, "quality") }}
    {{ render_value_card("D. ネットキャッシュ・現金リッチ", jp_cash_rich, "cash") }}
  </div>
  <h3><span class="pill pill-us">US</span> 米国株</h3>
  <div class="grid-2">
    {{ render_value_card("A. 低PER × 低PBR", us_value_per_pbr, "per_pbr") }}
    {{ render_value_card("B. 高配当", us_div, "div") }}
    {{ render_value_card("C. ROE高 × PBR低", us_quality, "quality") }}
    {{ render_value_card("D. ネットキャッシュ・現金リッチ", us_cash_rich, "cash") }}
  </div>

  <div class="footer">
    本ダッシュボードは公開データ (Yahoo Finance) に基づく教育目的の集計です。投資判断はご自身の責任で行ってください。<br>
    毎営業日朝 7:30 (JST) に GitHub Actions が自動更新します。
  </div>
</div>

<script src="https://cdn.jsdelivr.net/npm/chart.js@4.5.0/dist/chart.umd.js"></script>
<script>
const idxData = {{ chart_json|safe }};
new Chart(document.getElementById('indexChart'), {
  type:'line',
  data:{
    labels: idxData.labels,
    datasets: idxData.datasets.map((d,i)=>({
      label:d.label, data:d.data,
      borderColor:['#b3261e','#1d3a73','#117a3d','#7a4a09'][i%4],
      backgroundColor:'rgba(0,0,0,0.04)', tension:0.3, borderWidth:2
    }))
  },
  options:{responsive:true, maintainAspectRatio:false, plugins:{legend:{position:'bottom',labels:{boxWidth:10,font:{size:11}}}}}
});
</script>
</body>
</html>
"""


VALUE_CARD_TEMPLATE = r"""
<div class="card">
  <div class="stat-label">{{ title }}</div>
  <table>
    <thead><tr><th>銘柄</th><th class="num">PER</th><th class="num">PBR</th>{% if mode=='div' %}<th class="num">利回り</th>{% elif mode=='quality' %}<th class="num">ROE</th>{% else %}<th class="num">時価総額</th>{% endif %}</tr></thead>
    <tbody>
    {% for s in stocks %}
      <tr>
        <td><b>{{ s.ticker.replace('.T','') }}</b> {{ s.name|truncate(18,true,'…') }}</td>
        <td class="num">{{ fmt_num(s.per,1) }}</td>
        <td class="num">{{ fmt_num(s.pbr,2) }}</td>
        {% if mode=='div' %}<td class="num">{{ fmt_num(s.div_yield,1) }}%</td>
        {% elif mode=='quality' %}<td class="num">{{ fmt_num(s.roe,1) }}%</td>
        {% else %}<td class="num">{{ fmt_mcap(s.market_cap) }}</td>{% endif %}
      </tr>
    {% else %}
      <tr><td colspan="4" class="note">該当銘柄なし（条件未充足）</td></tr>
    {% endfor %}
    </tbody>
  </table>
</div>
"""


def fmt_num(x, digits=2):
    if x is None or (isinstance(x, float) and not math.isfinite(x)):
        return "—"
    if abs(x) >= 1000:
        return f"{x:,.0f}"
    return f"{x:,.{digits}f}"


def fmt_signed(x):
    if x is None:
        return "—"
    return f"{'+' if x>=0 else ''}{x:,.2f}"


def fmt_signed_pct(x):
    if x is None:
        return "—"
    return f"{'+' if x>=0 else ''}{x:.2f}%"


def fmt_mcap(x):
    if x is None:
        return "—"
    if x >= 1e12:
        return f"{x/1e12:,.1f}T"
    if x >= 1e9:
        return f"{x/1e9:,.1f}B"
    if x >= 1e6:
        return f"{x/1e6:,.0f}M"
    return fmt_num(x, 0)


def momentum_label(s: StockMetrics) -> str:
    parts = []
    if s.golden_cross:
        parts.append("GC")
    if s.above_sma50:
        parts.append(">50MA")
    if s.vol_ratio and s.vol_ratio > 1.3:
        parts.append("Vol↑")
    if s.rsi14 and s.rsi14 > 70:
        parts.append("過熱注意")
    return " / ".join(parts) or "—"


def render(payload: dict) -> str:
    # value-card の部分テンプレも一緒にレンダリング
    value_card_t = Template(VALUE_CARD_TEMPLATE)
    def render_value_card(title, stocks, mode):
        return value_card_t.render(title=title, stocks=stocks, mode=mode,
                                    fmt_num=fmt_num, fmt_mcap=fmt_mcap)
    t = Template(HTML_TEMPLATE)
    return t.render(
        **payload,
        fmt_num=fmt_num,
        fmt_signed=fmt_signed,
        fmt_signed_pct=fmt_signed_pct,
        momentum_label=momentum_label,
        render_value_card=render_value_card,
    )


# ------------------------------------------------------------
# Entry
# ------------------------------------------------------------
def main() -> int:
    print("==> Fetching indices …")
    indices = {k: fetch_index(*v) for k, v in INDICES.items()}

    print("==> Fetching JP momentum universe …")
    jp_stocks = fetch_universe(JP_MOMENTUM)
    print("==> Fetching JP value universe …")
    jp_value = fetch_universe(JP_VALUE_UNIVERSE)
    print("==> Fetching US momentum universe …")
    us_stocks = fetch_universe(US_MOMENTUM)
    print("==> Fetching US value universe …")
    us_value = fetch_universe(US_VALUE_UNIVERSE)
    print("==> Fetching S&P500 watchlist …")
    sp500_stocks = fetch_universe(SP500_TOP_UNIVERSE)

    # 5日推移チャート用データ（日経・S&P・NASDAQをスケール調整）
    n = indices.get("nikkei")
    s = indices.get("sp500")
    q = indices.get("nasdaq")
    labels = (n.history if n and n.history else s.history if s else [])
    label_dates = [h["date"] for h in labels] if labels else []

    def scale(idx, factor):
        if not idx or not idx.history:
            return [None]*len(label_dates)
        return [(h["close"]*factor) if h["close"] else None for h in idx.history[:len(label_dates)]]

    chart = {
        "labels": label_dates,
        "datasets": [
            {"label": "日経平均", "data": scale(n, 1)},
            {"label": "S&P500 (×8)", "data": scale(s, 8)},
            {"label": "NASDAQ (×2.4)", "data": scale(q, 2.4)},
        ],
    }

    payload = {
        "now": datetime.now(JST).strftime("%Y-%m-%d %H:%M"),
        "indices": indices,
        "sp500_top": rank_weekly_gainers(sp500_stocks, 5),
        "sp500_n": len(sp500_stocks),
        "jp_momentum": rank_momentum(jp_stocks, 5),
        "us_momentum": rank_momentum(us_stocks, 5),
        "jp_value_per_pbr": rank_value_per_pbr(jp_value, 5),
        "jp_div": rank_dividend(jp_value, 5),
        "jp_quality": rank_quality_value(jp_value, 5),
        "jp_cash_rich": sorted([s for s in jp_value if s.market_cap], key=lambda s: -s.market_cap)[:5],
        "us_value_per_pbr": rank_value_per_pbr(us_value, 5),
        "us_div": rank_dividend(us_value, 5),
        "us_quality": rank_quality_value(us_value, 5),
        "us_cash_rich": sorted([s for s in us_value if s.market_cap], key=lambda s: -s.market_cap)[:5],
        "chart_json": json.dumps(chart, ensure_ascii=False),
    }

    html = render(payload)
    out = ROOT / "index.html"
    out.write_text(html, encoding="utf-8")
    print(f"==> wrote {out} ({len(html):,} bytes)")

    # スナップショットJSONも保存（時系列管理・デバッグ用）
    def s_to_dict(s):
        return s.asdict() if isinstance(s, StockMetrics) else (asdict(s) if hasattr(s,'__dataclass_fields__') else s)
    snapshot = {
        "generated_at": payload["now"],
        "indices": {k: asdict(v) for k, v in indices.items()},
        "sp500_top": [s_to_dict(s) for s in payload["sp500_top"]],
        "jp_momentum": [s_to_dict(s) for s in payload["jp_momentum"]],
        "us_momentum": [s_to_dict(s) for s in payload["us_momentum"]],
    }
    (DATA_DIR / "snapshot.json").write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"==> wrote {DATA_DIR / 'snapshot.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
