# 🔥 HYPE SCAN
**YouTube ライブアーカイブ 盛り上がり分析ツール**

動画のチャットコメントを取得し、盛り上がりをグラフ・ランキング・ライブチャットリプレイで可視化します。

---

## ファイル構成

```
hypescan/
  ├── index.html        # フロントエンド
  ├── server.py         # Flask バックエンド
  ├── requirements.txt  # Python 依存パッケージ
  ├── render.yaml       # Render.com 用設定
  └── README.md         # このファイル
```

---

## ローカルで動かす

```bash
# 1. 依存パッケージをインストール
pip install -r requirements.txt

# 2. yt-dlp をインストール（まだの場合）
pip install yt-dlp

# 3. サーバーを起動
python server.py

# 4. ブラウザで開く
# http://localhost:5000
```

---

## 回数制限

デフォルトで **1IPあたり1日3回** に制限しています。
環境変数で変更できます：

```bash
# 回数制限を変更する場合
RATE_LIMIT=5 python server.py    # 1日5回に変更

# 制限を無効にする場合（ローカル開発時）
RATE_LIMIT=9999 python server.py
```

---

## デプロイ先の選択肢

### ① Render.com（おすすめ・無料枠あり）

| 項目 | 内容 |
|------|------|
| 料金 | 無料（月750時間、15分無操作でスリープ） |
| 有料 | $7/月（スリープなし） |
| 難易度 | ★☆☆ 簡単 |

**手順：**
1. [render.com](https://render.com) でアカウント作成
2. GitHubにこのフォルダをリポジトリとして push
3. `New +` → `Web Service` → リポジトリを選択
4. `render.yaml` が自動検出される → `Deploy`
5. 数分後に `https://hype-scan.onrender.com` のようなURLが発行される

---

### ② Railway（無料枠あり・高速）

| 項目 | 内容 |
|------|------|
| 料金 | 月$5クレジット無料（超過後は従量課金） |
| 難易度 | ★☆☆ 簡単 |

**手順：**
1. [railway.app](https://railway.app) でアカウント作成
2. `New Project` → `Deploy from GitHub repo`
3. 環境変数に `RATE_LIMIT=3` を設定
4. Deploy

---

### ③ VPS（ConoHa / さくらのVPS）

| 項目 | 内容 |
|------|------|
| 料金 | 月660円〜 |
| 難易度 | ★★★ 上級 |
| メリット | スリープなし・自由度高い |

**手順（ConoHa例）：**
```bash
# サーバーにSSH接続後
sudo apt update && sudo apt install -y python3-pip nginx

# ファイルをアップロード後
pip3 install -r requirements.txt

# Gunicorn で起動（本番用）
pip3 install gunicorn
gunicorn -w 2 -b 0.0.0.0:5000 server:app
```

---

## 広告収益化（Google AdSense）

1. [Google AdSense](https://adsense.google.com) に申請
2. 審査通過後（数週間）、発行されたコードを `index.html` の `<head>` 内に追加：

```html
<head>
  <!-- AdSense コード（審査通過後に発行されます） -->
  <script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-XXXXXXXXXXXXXXXX" crossorigin="anonymous"></script>
  ...
</head>
```

---

## 注意事項

- yt-dlp を使用してYouTubeのデータを取得しています
- サーバー費用は利用者数に比例して増加する可能性があります
- 回数制限はサーバーのメモリ上に保持されるため、再起動するとリセットされます
