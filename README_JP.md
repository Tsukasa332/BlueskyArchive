# BlueskyArchive

[English](README.md) | 日本語

## Maintainerからの声明

> この声明の内容だけはmaintainer本人が直接提示したものです。表記の整理と英訳はCodexが行っています。maintainerは設計と指示のみを行い、コーディング、テスト、ドキュメント作成はすべてCodexが行っています。Debian GNU/Linux 12 (bookworm) + Docker Engine 29.7.2で動作確認しています。Windows 11 + Docker Desktopでも動作すると見込んでいますが、未検証です。機能追加の要望は受け付けません。必要な変更は各自でforkして行ってください。

自分のBluesky投稿とリポストをPostgreSQLへ保存し、Twilog風の画面で検索・閲覧する個人用アーカイブです。

Web画面は英語を既定とし、ヘッダーの言語ボタンまたは設定画面から英語・日本語を切り替えられます。選択した言語は現在のブラウザだけに保存します。

この公開版には、Bluesky全体を対象にした画像Viewerと公開ブロック一覧機能は含まれません。画像・動画・動画字幕のローカル保存は既定で無効です。有効にした場合も、取得対象アカウント本人が投稿へ直接添付したmediaだけを保存し、リポスト元や引用先など他人のmediaは保存しません。

## 開発方法の開示

プロジェクトの方針と要件はmaintainerのHAYASHI Tsukasaが指示し、このリポジトリに含まれるソースコード、テスト、ドキュメントの作成と変更はOpenAI Codexが行っています。AI生成物を人間だけが作成したものとして表示しません。

OpenAIおよびOpenAI Codexは、このリポジトリの著作権者またはmaintainerとして表示しません。権利表示と利用条件は、リポジトリ直下の[`LICENSE`](LICENSE)に従います。

## 主な機能

- 自分の投稿、返信、引用、リポストを定期取得
- 日・月・全文・返信先・Hashtagによる検索と絞り込み
- 新着順、日ごとの時刻順、古い順のtimeline表示
- `images`、`gallery`、`video`、`external`、`record`、`recordWithMedia`の解釈
- Recent、Archives、Friends、Hashtagsのサイドバー
- 投稿種別と曜日・時間帯別の分析
- 削除済み投稿・リポストの照合
- 任意の本人media保存と、ファイル・総容量・空き容量による上限
- 英語・日本語の画面切り替えとbrowser-localな言語設定

## media保存ポリシー

`.env`の`SAVE_OWN_MEDIA`で制御します。

| 値 | 動作 |
|---|---|
| `false` | 画像・動画・動画字幕をローカルへ保存しない。既定値 |
| `true` | ログインした取得対象アカウント本人の直接添付mediaと動画字幕だけを保存する |

次のデータは`SAVE_OWN_MEDIA=true`でも保存しません。

- リポスト元の画像・動画・字幕
- 引用先投稿の画像・動画・字幕
- 他人が作成した投稿のmedia

投稿・リポストの本文、Actor情報、embed metadata、AT Protocolのraw JSONはmediaファイルとは別にPostgreSQLへ保存します。リポスト元のraw viewにはBluesky CDNのURLなどが含まれる場合がありますが、画像・動画本体はダウンロードしません。

設定を`true`から`false`へ変更しても、すでに保存済みのファイルやDB上のmedia情報は自動削除しません。既存環境を公開版へ移行するときは、以前保存した他人のmediaが残らないよう別途確認してください。新規環境では空のDBと`media/`から開始するのが安全です。

## 構成

- `nginx`: HTTP入口。Frontend、Backend API、本人mediaを振り分ける
- `frontend`: React 19、TypeScript、Viteによる閲覧画面
- `backend`: FastAPI REST API。PostgreSQLの検索・集計を担当する
- `fetcher`: Bluesky APIから投稿・リポスト・Actorを取得する。設定時のみ本人mediaも保存する
- `postgres`: アーカイブ、検索索引、同期状態、実行履歴を保存する
- `db-migrate`: Alembic migrationを実行する一回実行サービス
- `db-grants`: Backend・Fetcher用DBロールの権限を適用・検証する一回実行サービス

`frontend-network`と`database-network`を分け、両方へ接続するのはBackendだけです。Backend、Fetcher、両nginxはread-only root filesystem、capability全削除、`no-new-privileges`で実行します。BackendとFetcherはUID/GID 3006の非rootユーザーです。

詳細は[`docs/architecture.ja.md`](docs/architecture.ja.md)を参照してください。

## 必要なもの

- Docker EngineとDocker Compose v2
- Blueskyの取得対象アカウント
- Bluesky App Password
- 開発時のみPython 3.12、uv、Node.js、pnpm 11.7.0

## 初回配置

~~~bash
git clone <repository-url> BlueskyArchive
cd BlueskyArchive
cp .env.example .env
chmod 600 .env
~~~

`.env`で少なくとも次を変更します。

- `BLSKY_IDENTIFIER`
- `BLSKY_APP_PASSWORD`
- `POSTGRES_PASSWORD`
- `BACKEND_DB_PASSWORD`
- `FETCHER_DB_PASSWORD`

3種類のDBパスワードには、それぞれ異なる十分に長いランダム値を使用してください。mediaを保存する場合だけ`SAVE_OWN_MEDIA=true`へ変更します。

Fetcherが`media/`へ書き込めるよう、Linuxホストでは所有者を合わせます。

~~~bash
sudo chown -R 3006:3006 media
docker compose up -d --build
docker compose ps -a
docker compose logs --tail=100 db-migrate db-grants backend fetcher frontend nginx
~~~

動作確認例:

~~~bash
curl -fsS http://127.0.0.1:8080/ -o /dev/null
curl -fsS http://127.0.0.1:8080/api/health
curl -fsS http://127.0.0.1:8080/api/calendar -o /dev/null
curl -fsS 'http://127.0.0.1:8080/api/timeline?limit=1' -o /dev/null
~~~

## 環境変数

| 変数 | 既定値・用途 |
|---|---|
| `POSTGRES_DB` | `bluesky_archive`。PostgreSQLデータベース名 |
| `POSTGRES_USER` | `bluesky`。migration用管理ロール |
| `POSTGRES_PASSWORD` | 管理ロールのパスワード。必ず変更 |
| `BACKEND_DB_USER` | `bluesky_backend`。Backend用ロール |
| `BACKEND_DB_PASSWORD` | Backend用ロールのパスワード。必ず変更 |
| `FETCHER_DB_USER` | `bluesky_fetcher`。Fetcher用ロール |
| `FETCHER_DB_PASSWORD` | Fetcher用ロールのパスワード。必ず変更 |
| `BLSKY_IDENTIFIER` | 取得対象Blueskyアカウント |
| `BLSKY_APP_PASSWORD` | Fetcherが使用するBluesky App Password |
| `SAVE_OWN_MEDIA` | `false`。`true`の場合だけ本人の直接添付mediaを保存 |
| `APP_TIMEZONE` | `Asia/Tokyo`。日付境界とカレンダー集計に使用 |
| `MEDIA_MIN_FREE_BYTES` | `5368709120`。保存後に確保する空き容量5 GiB |
| `MEDIA_MAX_FILE_BYTES` | `157286400`。1ファイル上限150 MiB |
| `MEDIA_MAX_TOTAL_BYTES` | `53687091200`。media全体上限50 GiB |
| `MEDIA_TOTAL_SCAN_INTERVAL_SECONDS` | `300`。media全体容量の再集計間隔 |
| `FETCH_INTERVAL_SECONDS` | `900`。通常同期間隔 |
| `FETCH_PAGE_LIMIT` | `100`。Bluesky APIの1ページ取得件数 |
| `FULL_RECONCILE_INTERVAL_SECONDS` | `86400`。CIDと削除状態を全照合する間隔 |
| `ERROR_BACKOFF_SECONDS` | `60`。同期失敗後の再試行待機時間 |
| `HTTP_PORT` | `8080`。ホストで公開するHTTPポート |

`MEDIA_ROOT`はコンテナ内の`/app/media`に固定しています。1ファイル上限、総容量、空き容量のいずれかに抵触したmediaは保存せず、同期を失敗させます。

## セキュリティ上の注意

- `.env`にはBluesky App PasswordとDBパスワードが入るため、Gitへ追加しないでください。
- Composeは既定で`0.0.0.0:8080`へ公開します。認証機能はありません。インターネットへ直接公開せず、Firewall、VPN、認証付きリバースプロキシなどで閲覧者を制限してください。
- 投稿本文、raw JSON、DB dump、本人mediaも個人情報です。公開GitHubリポジトリへ追加しないでください。
- FastAPIの`/docs`、`/redoc`、`/openapi.json`は無効です。
- `docker compose down -v`はPostgreSQL volumeを削除します。通常更新では実行しないでください。

## 開発

BackendとFetcherはルートの非package型uvプロジェクトと`uv.lock`を共有します。両方のtop-level package名が`app`なので、同じpytest processで一括収集しません。

~~~powershell
uv sync --locked

$env:PYTHONPATH='shared;backend'
uv run --locked pytest backend/tests -q

$env:PYTHONPATH='shared;fetcher'
uv run --locked pytest fetcher/tests -q

Set-Location frontend
pnpm install --frozen-lockfile
pnpm run build
~~~

変更後は`git diff --check`と`docker compose config`も確認してください。依存解決には`uv.lock`と`frontend/pnpm-lock.yaml`だけを使用し、`requirements.txt`や`package-lock.json`を追加しないでください。

## API

- `GET /api/posts`
- `GET /api/reposts`
- `GET /api/timeline`
- `GET /api/timeline/search?tag=TAG`
- `GET /api/timeline/replies?reply_to=DID`
- `GET /api/navigation?limit=20`
- `GET /api/analytics?period=all|year|month|week`
- `GET /api/posts/{id}`
- `GET /api/calendar`
- `GET /api/search`
- `GET /api/health`
- `GET /api/sync`
- `POST /api/sync`

## リポスト元の修復

保存済みリポストの元投稿viewだけを再取得する場合は、リポストURIまたは元投稿URIを指定します。公開版では元投稿の画像・動画を保存しません。

~~~bash
docker compose exec fetcher python -m app.repair_reposts \
  at://did:plc:example/app.bsky.feed.post/example
~~~

## バックアップ

完全な復元には次が必要です。

- PostgreSQL volumeまたはDB dump
- `SAVE_OWN_MEDIA=true`で運用する場合は`media/`
- `.env`
- 使用していたGit commit

バックアップにも投稿内容、認証情報、本人mediaが含まれます。Git管理や公開対象に含めないでください。

## Gitへ追加しないもの

- `.env`、`.venv/`、`.pnpm-store/`、`node_modules/`
- Python cache、pytest cache、`frontend/dist/`
- `media/`内の実ファイル
- PostgreSQLデータ、dump、backup、`outputs/`
- パスワード、App Password、SSH秘密鍵

`media/images/.gitkeep`、`media/videos/.gitkeep`、`media/captions/.gitkeep`だけは空ディレクトリ維持のため追跡します。

## License

このリポジトリ独自のソースコードとドキュメントは、適用可能な権利の範囲でMIT Licenseにより提供します。

Copyright (c) 2026 HAYASHI Tsukasa

依存ライブラリ、コンテナイメージ、外部サービス、Blueskyから取得した投稿・Actor情報・raw JSON・mediaにはMIT Licenseを適用しません。それぞれの権利者と利用条件に従ってください。全文は[`LICENSE`](LICENSE)を参照してください。
