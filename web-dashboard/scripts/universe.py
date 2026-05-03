"""ウォッチユニバース定義 — 投資塾の教育目的で日米計約400銘柄。

JP: TOPIX Core 30 を中心に、教育的に押さえておきたい大型・中型を選抜。
US: S&P 100 を中心に、テック・ヘルスケア・消費財・金融・エネルギーなど主要銘柄を選抜。
"""

# ---- 日本株 (Tokyo Stock Exchange) ----
# Yahoo Finance ティッカーは "<コード>.T"
JP_TICKERS = [
    # TOPIX Core 30
    "7203", "6758", "9432", "9433", "9434", "8306", "8316", "8411",
    "6594", "6861", "8035", "9984", "6098", "4063", "6367", "6273",
    "4519", "4502", "4568", "8001", "8031", "8053", "8058", "8766",
    "9020", "9022", "7267", "7741", "6981", "4901",
    # Large 70 (主要)
    "1605", "1928", "2502", "2914", "3382", "3402", "4005", "4061",
    "4188", "4324", "4452", "4503", "4523", "4543", "4661", "4689",
    "4704", "4751", "4755", "4901", "5108", "5201", "5301", "5401",
    "5713", "5802", "6178", "6201", "6301", "6326", "6479", "6501",
    "6502", "6503", "6506", "6645", "6701", "6702", "6723", "6724",
    "6752", "6754", "6762", "6857", "6902", "6920", "6952", "6971",
    "7011", "7201", "7202", "7269", "7270", "7272", "7733", "7751",
    "7832", "7912", "7974", "8002", "8015", "8252", "8267", "8331",
    "8354", "8473", "8591", "8593", "8604", "8630", "8697", "8725",
    "8729", "8750", "8801", "8802", "8830", "9007", "9201", "9202",
    "9301", "9404", "9501", "9502", "9503", "9531", "9532", "9613",
    "9735", "9766", "9983",
    # Mid (教育的)
    "3092", "3659", "3769", "4307", "4385", "4716", "4768", "6178",
    "6273", "6383", "6588", "6770", "6857", "7164", "7203", "7282",
    "7581", "7649", "7733", "7751", "8136", "8439", "9201", "9531",
]

# ユニーク化＋ソート
JP_TICKERS = sorted(set(JP_TICKERS))
JP_TICKERS_FULL = [f"{c}.T" for c in JP_TICKERS]

# ---- 米国株 ----
US_TICKERS = [
    # メガキャップ・テック
    "AAPL", "MSFT", "GOOGL", "GOOG", "AMZN", "META", "NVDA", "TSLA",
    "AVGO", "ORCL", "CRM", "ADBE", "AMD", "INTC", "QCOM", "TXN",
    "CSCO", "IBM", "NOW", "INTU", "SHOP", "PYPL", "NFLX", "DIS",
    "UBER", "ABNB", "PLTR", "SNOW", "DDOG", "MDB", "CRWD", "ZS",
    "PANW", "ANET", "CDNS", "SNPS", "MU", "AMAT", "LRCX", "KLAC",
    "ASML", "TSM",
    # 金融
    "JPM", "BAC", "WFC", "C", "GS", "MS", "BLK", "SCHW", "AXP", "USB",
    "PNC", "TFC", "COF", "BK", "MET", "PRU", "AIG", "TRV", "ALL",
    "BRK-B", "V", "MA", "PYPL",
    # ヘルスケア
    "JNJ", "LLY", "PFE", "MRK", "ABBV", "UNH", "TMO", "DHR", "ABT",
    "AMGN", "GILD", "BMY", "MDT", "ISRG", "REGN", "VRTX", "BIIB",
    "CVS", "CI", "HUM", "ELV", "MCK", "BSX", "EW", "SYK", "ZTS",
    # 消費財・リテール
    "WMT", "COST", "HD", "MCD", "NKE", "TGT", "LOW", "SBUX", "BKNG",
    "TJX", "ROST", "DG", "DLTR", "KR", "WBA", "AAP", "AZO", "ORLY",
    "PG", "KO", "PEP", "KMB", "CL", "MO", "PM", "STZ", "MDLZ",
    "GIS", "HSY", "CHD", "CLX",
    # 産業
    "BA", "CAT", "DE", "GE", "HON", "LMT", "RTX", "NOC", "GD",
    "UNP", "CSX", "NSC", "FDX", "UPS", "ETN", "EMR", "ITW", "PH",
    "ROK", "JCI", "DOV", "PCAR",
    # エネルギー
    "XOM", "CVX", "COP", "EOG", "SLB", "OXY", "PSX", "VLO", "MPC",
    "PXD", "HES", "WMB", "OKE", "KMI",
    # コミュニケーション
    "T", "VZ", "TMUS", "CMCSA", "CHTR", "DISH",
    # 公益・REIT
    "NEE", "DUK", "SO", "AEP", "D", "EXC", "SRE", "XEL", "ED",
    "AMT", "PLD", "CCI", "EQIX", "PSA", "WELL", "DLR", "O", "SPG",
    # 素材
    "LIN", "APD", "FCX", "NEM", "DOW", "DD", "ECL", "SHW", "NUE",
    "STLD", "MLM", "VMC",
    # 自動車・EV関連
    "F", "GM", "RIVN", "LCID",
    # 外食・旅行
    "CMG", "YUM", "DRI", "MAR", "HLT", "RCL", "CCL", "NCLH",
    # その他成長
    "LULU", "DECK", "RH", "WSM", "CRH", "VRSK", "MCO", "SPGI",
    "FICO", "MSCI", "RJF", "FI",
    # ETF (補助・ベンチマーク用)
    "SPY", "QQQ", "IWM", "DIA",
]

US_TICKERS = sorted(set(US_TICKERS))


def all_tickers_full():
    """yfinance に渡すフルティッカー一覧を返す。"""
    return JP_TICKERS_FULL + US_TICKERS


# 簡易セクター分類（yfinance.info["sector"]がうまく取れない時の保険）
SECTOR_MAP = {
    # JP
    "7203.T": "自動車", "7267.T": "自動車", "7269.T": "自動車", "7270.T": "自動車",
    "6758.T": "電機", "6981.T": "電子部品", "8035.T": "半導体製造装置",
    "6857.T": "半導体検査", "6920.T": "半導体検査",
    "9432.T": "通信", "9433.T": "通信", "9434.T": "通信",
    "8306.T": "銀行", "8316.T": "銀行", "8411.T": "銀行",
    "8001.T": "総合商社", "8031.T": "総合商社", "8058.T": "総合商社", "8053.T": "総合商社",
    "9501.T": "電力", "9502.T": "電力", "9503.T": "電力",
    "4452.T": "化学", "4063.T": "素材", "4502.T": "医薬品", "4519.T": "医薬品",
    # US (一部のみ。未指定はyfinance.info["sector"]を信頼)
    "AAPL": "Technology", "MSFT": "Technology", "GOOGL": "Communication",
    "META": "Communication", "AMZN": "Consumer Discretionary",
    "NVDA": "Technology", "TSLA": "Consumer Discretionary",
}
