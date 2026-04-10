アイスホッケー練習出欠アプリ（ブラウザ版 / クラウド公開向け）

この版は各家庭からスマホのブラウザで使う前提です。
アプリのインストールは不要です。

主な特長
- 管理者用ページと登録者6名用ページを分離
- 登録者は自分の出欠だけ変更可能
- PINはサーバー側でハッシュ化して保存
- ログイン失敗回数の簡易制限あり
- セッションCookie対応
- SQLite保存でデータ保持
- Render などの外部ホスティングに載せやすい構成

同梱ファイル
- server.py : 本体サーバー
- config.json : PINハッシュを持つ設定ファイル
- attendance.db : 初回起動後に自動作成されるDB
- render.yaml : Render向け設定ファイル
- generate_config.py : PIN変更後にconfig.jsonを再生成する補助スクリプト

ローカル確認
1. python server.py
2. http://127.0.0.1:8000 を開く

公開運用（推奨）
1. GitHubにこのフォルダをアップロード
2. Renderで New Web Service を作成
3. リポジトリを接続
4. Start Command を python server.py に設定
5. Persistent Disk を /var/data に付与
6. APP_DB_PATH=/var/data/attendance.db を設定
7. SECURE_COOKIES=1 を設定
8. デプロイ完了後のURLを配布

PIN変更
- generate_config.py 内の PINS を変更
- python generate_config.py config.json を実行
- 再デプロイ
