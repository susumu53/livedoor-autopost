# Livedoor Blog Auto Post System

Livedoorブログへの自動投稿システムです。DMM/FANZAの売れ筋ランキングや、AIによる美人度解析ランキングを定期的に投稿します。

## 特徴
- **自動スケジュール**: GitHub Actionsを使用して1時間ごとに自動投稿。
- **ハイブリッドコンテンツ**: FANZAの売れ筋ランキングと、AI解析に基づいた美人度ランキングを交互に投稿。
- **NGワードフィルタ**: Livedoorブログの規約に合わせたフィルタリング機能を搭載。
- **レスポンシブデザイン**: 投稿される記事はモダンでプレミアムなHTML/CSSデザインを採用。

## セットアップ

1. **環境変数の設定**:
   `.env.example` を `.env` にコピーし、必要なAPIキー等を設定してください。
   GitHubで実行する場合は、Repository Secretsに以下の値を設定してください：
   - `DMM_API_ID`
   - `DMM_AFFILIATE_ID`
   - `LIVEDOOR_ID`
   - `LIVEDOOR_BLOG_ID`
   - `LIVEDOOR_API_KEY`
   - `AMAZON_ACCESS_KEY` (任意)
   - `AMAZON_SECRET_KEY` (任意)
   - `AMAZON_PARTNER_TAG` (任意)

2. **依存関係のインストール**:
   ```bash
   pip install -r requirements.txt
   ```

3. **実行**:
   ```bash
   python main.py
   ```

## ディレクトリ構造
- `main.py`: メインの投稿ロジック。
- `livedoor_client.py`: Livedoor Blog AtomPub APIクライアント。
- `dmm_client.py`: DMM/FANZA APIクライアント。
- `database.py`: 解析データ保存用SQLiteデータベース管理。
- `generate_article.py`: 記事生成・分析マネージャー。
- `beauty_engine.py`: AI画像解析エンジン（MediaPipe/OpenCV）。

## メンテナンス
- `beauty_index_fanza.db`: 解析済みデータのキャッシュ。
- `last_actresses.json`: 次回の解析対象となる女優リスト。
