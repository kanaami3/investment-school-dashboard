"""定量スコア計算ライブラリ。

実装するスコア:
- Greenblatt Magic Formula  : ROC + 益回りのランク合計
- Piotroski F-Score (9項目) : 財務健全性
- Altman Z-Score             : 倒産リスク（製造業向け原典版）
- Jegadeesh-Titman Momentum  : 12-1 リターン (12ヶ月-1ヶ月のスキップ)
"""
from __future__ import annotations
import math
from typing import Iterable, Optional

import pandas as pd


def safe(x) -> Optional[float]:
    try:
        if x is None:
            return None
        f = float(x)
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------
# 1. Greenblatt Magic Formula
#    要素:
#      - ROC (Return on Capital) ≒ EBIT / (NetWorkingCapital + NetFixedAssets)
#         yfinance だと EBIT 直接は取りづらいので 営業利益率×投下資本回転率で近似
#      - Earnings Yield = EBIT / Enterprise Value
#         代わりに 1 / forwardPE をプロキシ
#    各メトリクスでランキングし、合計順位の小さい順が「Magic Formula 順」。
# ---------------------------------------------------------------
def magic_formula_inputs(info: dict) -> tuple[Optional[float], Optional[float]]:
    """info dict から (ROC, EarningsYield) を概算で返す。"""
    roa = safe(info.get("returnOnAssets"))
    eq = safe(info.get("returnOnEquity"))
    op_margin = safe(info.get("operatingMargins"))
    # ROCを ROA を主、無ければ営業利益率で代用
    roc = roa if roa is not None else op_margin
    # earnings yield: trailingPE が小さいほど高い
    pe = safe(info.get("trailingPE")) or safe(info.get("forwardPE"))
    ey = (1.0 / pe) if pe and pe > 0 else None
    return roc, ey


def magic_formula_rank(stocks: list[dict]) -> dict[str, int]:
    """各銘柄の MagicFormula 合計順位を返す（小さい順が良い）。"""
    rocs = sorted(
        [s for s in stocks if s.get("roc") is not None],
        key=lambda s: -s["roc"],
    )
    eys = sorted(
        [s for s in stocks if s.get("ey") is not None],
        key=lambda s: -s["ey"],
    )
    rank_roc = {s["ticker"]: i + 1 for i, s in enumerate(rocs)}
    rank_ey = {s["ticker"]: i + 1 for i, s in enumerate(eys)}
    out = {}
    for s in stocks:
        r1 = rank_roc.get(s["ticker"])
        r2 = rank_ey.get(s["ticker"])
        if r1 and r2:
            out[s["ticker"]] = r1 + r2
    return out


# ---------------------------------------------------------------
# 2. Piotroski F-Score (9項目, 0〜9点)
# 収益性 (4): ROA>0, OperatingCF>0, ROA増加, Accruals (CF>NI)
# レバレッジ (3): 長期負債減少, 流動比率向上, 株式希薄化なし
# 効率 (2): 粗利率向上, 資産回転率向上
#
# yfinanceは過去2期の財務を取れないことがあるため、取れた範囲でスコアし、
# 不明項目は0扱いとする（実装上の妥協、教育目的としては十分）。
# ---------------------------------------------------------------
def f_score(
    roa: Optional[float],
    cfo_to_assets: Optional[float],
    roa_change: Optional[float],
    accruals_ok: Optional[bool],
    leverage_change: Optional[float],
    cur_ratio_change: Optional[float],
    no_dilution: Optional[bool],
    gross_margin_change: Optional[float],
    asset_turn_change: Optional[float],
) -> int:
    score = 0
    if roa is not None and roa > 0:
        score += 1
    if cfo_to_assets is not None and cfo_to_assets > 0:
        score += 1
    if roa_change is not None and roa_change > 0:
        score += 1
    if accruals_ok:
        score += 1
    if leverage_change is not None and leverage_change < 0:  # 負債が減少
        score += 1
    if cur_ratio_change is not None and cur_ratio_change > 0:
        score += 1
    if no_dilution:
        score += 1
    if gross_margin_change is not None and gross_margin_change > 0:
        score += 1
    if asset_turn_change is not None and asset_turn_change > 0:
        score += 1
    return score


def f_score_simple(info: dict) -> Optional[int]:
    """yfinanceのinfoだけで近似Fスコアを出す簡易版（最大5点）。"""
    parts = []
    roa = safe(info.get("returnOnAssets"))
    if roa is not None:
        parts.append(1 if roa > 0 else 0)
    op_margin = safe(info.get("operatingMargins"))
    if op_margin is not None:
        parts.append(1 if op_margin > 0 else 0)
    cur = safe(info.get("currentRatio"))
    if cur is not None:
        parts.append(1 if cur > 1.0 else 0)
    de = safe(info.get("debtToEquity"))
    if de is not None:
        parts.append(1 if de < 100 else 0)  # 1.0倍未満
    gm = safe(info.get("grossMargins"))
    if gm is not None:
        parts.append(1 if gm > 0.2 else 0)
    if not parts:
        return None
    return sum(parts) + (5 - len(parts)) // 2  # 不明分は中央値で補正


# ---------------------------------------------------------------
# 3. Altman Z-Score (Original 1968)
# Z = 1.2*A + 1.4*B + 3.3*C + 0.6*D + 1.0*E
#  A = WorkingCapital / TotalAssets
#  B = RetainedEarnings / TotalAssets
#  C = EBIT / TotalAssets
#  D = MarketCap / TotalLiabilities
#  E = Sales / TotalAssets
# Z>2.99: Safe / 1.81<Z<2.99: Grey / Z<1.81: Distress
#
# yfinance.info から取れない要素は近似に置き換える簡易版。
# ---------------------------------------------------------------
def z_score_simple(info: dict) -> Optional[float]:
    op_margin = safe(info.get("operatingMargins"))
    asset_turn = None
    rev = safe(info.get("totalRevenue"))
    ta = safe(info.get("totalAssets"))
    if rev and ta:
        asset_turn = rev / ta
    de = safe(info.get("debtToEquity"))
    mc = safe(info.get("marketCap"))
    td = safe(info.get("totalDebt"))
    cur = safe(info.get("currentRatio"))

    A = (cur - 1) * 0.3 if cur is not None else 0  # WC/TA 近似
    B = 0.1 if (op_margin and op_margin > 0.1) else 0  # RE/TA 近似
    C = op_margin * 0.8 if op_margin else 0  # EBIT/TA 近似
    D = (mc / td) if (mc and td and td > 0) else 0
    E = asset_turn if asset_turn else 0

    z = 1.2 * A + 1.4 * B + 3.3 * C + 0.6 * (D or 0) + 1.0 * E
    if all(x is None for x in [op_margin, asset_turn, mc, td, cur]):
        return None
    return safe(z)


# ---------------------------------------------------------------
# 4. Jegadeesh-Titman 12-1 Momentum
#    過去12ヶ月リターンから直近1ヶ月を除いたリターン。
# ---------------------------------------------------------------
def jt_momentum(close_series: pd.Series) -> Optional[float]:
    if close_series is None or len(close_series) < 252:
        return None
    end = close_series.iloc[-21]   # 1ヶ月前(≒21営業日)
    start = close_series.iloc[-252]  # 12ヶ月前
    if not start or pd.isna(start) or pd.isna(end):
        return None
    return float((end / start - 1) * 100)


# ---------------------------------------------------------------
# 5. RSI / SMA / Volatility
# ---------------------------------------------------------------
def rsi(close: pd.Series, period: int = 14) -> Optional[float]:
    if len(close) < period + 1:
        return None
    delta = close.diff().dropna()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = -delta.clip(upper=0).rolling(period).mean()
    rs = gain / loss.replace(0, pd.NA)
    val = (100 - 100 / (1 + rs)).iloc[-1]
    return safe(val)


def sma(close: pd.Series, n: int) -> Optional[float]:
    if len(close) < n:
        return None
    return safe(close.rolling(n).mean().iloc[-1])


def annualized_vol(close: pd.Series, lookback: int = 60) -> Optional[float]:
    if len(close) < lookback + 1:
        return None
    rets = close.pct_change().dropna().tail(lookback)
    if rets.empty:
        return None
    return safe(rets.std() * (252 ** 0.5) * 100)
