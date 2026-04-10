アイスホッケー練習出欠アプリ v4

追加した機能
- 練習日 / 練習時間の編集
- 登録者の追加

最短起動手順
1. Python 3 を用意
2. このフォルダで以下を実行
   pip install -r requirements.txt
   python server.py
3. ブラウザで http://127.0.0.1:8000 を開く

Render へ更新するとき
1. 既存のGitHubリポジトリを開く
2. このフォルダの中身で上書きアップロード
3. Commit changes
4. Render は自動再デプロイ

ポイント
- attendance.db は本番データです
- 本番更新前に attendance.db のバックアップを取ると安心です
- config.json は初期メンバーと管理者PINの種だけを持ちます
- 追加した登録者は DB に保存されます
