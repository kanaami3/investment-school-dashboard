# 投資塾 マーケット・ダッシュボード（Web公開版 v2）

GitHub Pages + GitHub Actions で運用する、日米マーケットの自動更新ダッシュボードです。
毎営業日朝 7:30 JST に Yahoo Finance から日米約400銘柄のデータを取得し、
- 主要指数サマリ
- セクターヒートマップ
- 市場ブレダス指標（A/D、52週高値近接率、>50MA比率、GC比率）
- 全銘柄スクリーナー（PER/PBR/配当/ROE/RSI/F-Score/Z-Score 等で絞込・並替・CSV出力）
- 個別銘柄ページ（チャート＋シグナル＋財務＋スコア）

を生成し、Pages に静的配信します。

## ディレクトリ構成

```
web-dashboard/
├── index.html                  # ダッシュボード
├── screen.html                 # スクリーナー（Grid.js）
├── stock.html                  # 個別銘柄（Chart.js）
├── assets/
│   ├── style.css               # 共通スタイル
│   └── app.js                  # 共通JSヘルパー
├── data/                       # ← Actionsが毎朝生成
│   ├── snapshot.json
│   ├── stocks.json
│   ├── sectors.json
│   ├── breadth.json
│   └── stocks/<TICKER>.json    # 個別銘柄ページ用
├── scripts/
│   ├── update.py               # データパイプライン本体
│   ├── universe.py             # ウォッチユニバース定義
│   └── scoring.py              # スコア計算ライブラリ
├── requirements.txt
└── .github/workflows/update.yml
```

## 実装している定量スコア

| スコア | 内容 | 用途 |
|---|---|---|
| **Greenblatt Magic Formula** | ROC（資本収益率）と Earnings Yield のランク合計 | クオリティ × バリューの代表的指標 |
| **Piotroski F-Score（簡易版5点）** | ROA、営業利益率、流動比率、D/E、粗利率 の5項目 | 財務健全性。3点以上で良好の目安 |
| **Altman Z-Score（簡易版）** | WC/TA, RE/TA, EBIT/TA, MV/TL, S/TA を info 値で近似 | 倒産リスク。>2.99 安全 / <1.81 警戒 |
| **Jegadeesh-Titman 12-1 Momentum** | 12ヶ月リターン − 直近1ヶ月リターン | 学術的に頑健なモメンタム指標 |
| **RSI(14) / SMA50 / SMA200 / GC** | 標準テクニカル | 短中期トレンド判定 |
| **52週高値乖離率** | 直近終値 ÷ 1年高値 − 1 | ブレイクアウト判定 |

## セットアップ手順（5〜10分）

「Claude in Chrome を使ったナビ」で進める場合は、別途チャットで「ナビして」と言ってもらえれば
ブラウザ上で一緒に手を動かしながら進めます。手動でやる場合は以下:

### 1. GitHub に Private リポジトリ作成
名前は推測されにくいものに（例: `mt-dashboard-priv-xyz123`）。

### 2. このフォルダをコミット & push
```bash
cd web-dashboard
git init && git add . && git commit -m "init"
git remote add origin git@github.com:<user>/<repo>.git
git branch -M main && git push -u origin main
```

### 3. GitHub Pages を有効化
Settings → Pages → Build and deployment
- Source = Deploy from a branch
- Branch = main / (root)

### 4. Actions に書き込み権限を付与
Settings → Actions → General → Workflow permissions = **Read and write permissions**

### 5. 初回テスト実行
Actions タブ → Update Market Dashboard → Run workflow

5〜15分で `data/` 配下のJSONが生成され、ページにデータが反映されます。
以降は cron (`30 22 * * 0-4` UTC = 7:30 JST 月-金) で自動実行。

## カスタマイズ

### ウォッチ銘柄を変える
`scripts/universe.py` の `JP_TICKERS` / `US_TICKERS` を編集。
- 日本株: 4桁証券コード（`.T` は自動付与）
- 米国株: ティッカーそのまま

### スコア定義を変える
`scripts/scoring.py` を編集。F-Score の項目追加、Z-Score の係数調整など。

### スクリーナーのプリセットを増やす
`screen.html` の `applyPreset()` 関数に case を追加。

### 配信時刻を変える
`.github/workflows/update.yml` の `cron` を編集（UTC指定、JSTは+9時間）。

## トラブルシューティング

| 症状 | 対処 |
|---|---|
| Actions が `git push` で 403 | Settings → Actions → Workflow permissions を Read and write に |
| `yfinance` のレート制限で空データ多発 | 数分待って再実行。または `max_workers` を 4 に下げる |
| 1回の Actions 実行が長すぎる | universe.py で銘柄数を減らす（150銘柄程度なら 5-7分） |
| 日本株が `—` 表示 | `.T` が付いているか確認 |
| Pages が 404 | Settings → Pages の Branch 設定確認、push 後 1-2分待つ |

## アクセス制限を強化したい場合
GitHub Pages 単体では URL を知っている人なら誰でも閲覧可能（noindexで検索除外のみ）。
さらに絞るなら **Cloudflare Access**（無料50ユーザーまで・メール認証ゲート）を被せる構成が最も手軽です。

## ライセンス
教育目的の社内利用想定。Yahoo Finance のデータ利用規約に従ってください。
