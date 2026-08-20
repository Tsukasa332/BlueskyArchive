# BlueskyArchive 設計書

## 1. 目的

1つのBlueskyアカウントについて、本人の投稿とリポストを継続取得し、PostgreSQLを正本として検索・閲覧できる個人用アーカイブを構築する。

公開版では機能と権限を次の境界に制限する。

- 画像検索Viewerと公開ブロック一覧を含めない。
- 他人の画像・動画・動画字幕をローカルへ保存しない。
- 本人mediaも`SAVE_OWN_MEDIA=true`の場合だけ保存する。
- 本人media保存時も、直接添付だけを対象とし、引用先mediaを混入させない。
- raw JSONを保持し、将来のprotocol変更に備える。

## 2. 実行時構成

| サービス | 責務 | 接続先 |
|---|---|---|
| `nginx` | HTTP入口、Frontend・API・本人mediaの振り分け、Rate Limit、security header | Frontend、Backend、`media/` |
| `frontend` | React/Viteで生成した閲覧画面 | ブラウザから`/api`経由でBackend |
| `backend` | timeline、検索、calendar、分析、手動同期要求 | PostgreSQL |
| `fetcher` | repository取得、record解釈、DB更新、任意の本人media保存 | Bluesky API、PostgreSQL、`media/` |
| `postgres` | アーカイブ、検索索引、同期状態、実行履歴 | database network |
| `db-migrate` | Alembic migration | PostgreSQL |
| `db-grants` | Backend・Fetcher用ロールの権限適用と自己検証 | PostgreSQL |

起動順序は`postgres` → `db-migrate` → `db-grants` → `backend` / `fetcher`である。`frontend-network`と`database-network`を分け、両方へ接続するのはBackendだけとする。

## 3. 同期と永続化

1. FetcherがApp Passwordでログインし、取得対象本人のDIDを確定する。
2. 本人repositoryのpostとrepost recordを新しい順に取得する。
3. post view、Actor、facet、label、embedを解釈する。
4. 投稿とリポストを別tableへupsertする。
5. `SAVE_OWN_MEDIA=true`かつpostの`author_did`がログインDIDと一致する場合だけ、直接添付mediaを保存する。
6. リポスト元viewは本文表示用metadataとして保存するが、media本体は保存しない。
7. cursor、同期結果、全照合時刻を更新する。

media判定はFetcherの`SyncService._save_media_for_post`へ集約する。引用embedの内部へ再帰せず、`shared/archive/bluesky_embed.py`が返す直接添付だけを対象にする。リポスト元mediaを保存する処理は公開版には置かない。

`SAVE_OWN_MEDIA=false`は新しいmedia保存を停止する設定であり、既存ファイルやDB rowを削除する設定ではない。既存環境の移行では別途data auditが必要である。

## 4. 表示

FrontendはURL queryを画面状態として扱い、Backendからtimeline、検索結果、calendar、navigation、analyticsを取得する。Backendはページング前に安定した並び順を適用し、Frontendは日付単位で表示する。

media API schemaは本人のローカルmediaだけを参照する。リポスト元にmedia metadataが存在してもローカルmedia assetがない場合は、保存済みmediaとして返さない。

## 5. ソースコードの責務

### Frontend

- `frontend/src/main.tsx`: route、filter、page state
- `frontend/src/TimelineCard.tsx`: 投稿・リポストcard
- `frontend/src/api.ts`: API clientと型
- `frontend/src/settings.ts`: browser local settings

### Backend

- `backend/app/api/posts.py`: timeline・検索API
- `backend/app/api/navigation.py`: Friends・Hashtags集計
- `backend/app/api/analytics.py`: 活動分析
- `backend/app/api/presenters.py`: DB modelから公開schemaへの変換
- `backend/app/core/config.py`: Backend設定

### Fetcher

- `fetcher/app/bluesky_client.py`: Bluesky XRPC clientと再認証
- `fetcher/app/sync.py`: 同期、本人media判定、reconcile
- `fetcher/app/repository.py`: DB更新
- `fetcher/app/media_downloader.py`: 容量制限付きfile保存
- `fetcher/app/config.py`: Fetcher設定

### Shared

- `shared/archive/bluesky_embed.py`: embed、Hashtag、label、直接添付mediaの正規化
- `shared/archive/db/models.py`: BackendとFetcherが共有するDB model

## 6. セキュリティ境界

- `.env`を各サービスへ一括注入せず、必要な環境変数だけを明示する。
- BackendとFetcherは別DBロールを使用し、どちらにもDDL権限を与えない。
- Backendは原則read-onlyとし、手動同期要求に必要な`sync_states`列だけ更新できる。
- Fetcherだけが`media/`へ書き込む。
- application serviceはUID/GID 3006の非rootで実行する。
- applicationとnginxはread-only root filesystem、capability全削除、`no-new-privileges`を使用する。
- nginx access logにはquery stringとRefererを含めない。
- HTTP UI自体に認証機能はない。直接Internetへ公開しない。

## 7. 依存関係とテスト

BackendとFetcherはルートの非package型`pyproject.toml`と`uv.lock`を共有する。runtime dependency groupは`backend`と`fetcher`、開発用は`dev`とする。本番imageはbuilder stageで必要なgroupだけをlocked syncし、runtime stageへ`.venv`だけをコピーする。

BackendとFetcherはどちらもtop-level package名が`app`なので、別々のpytest processで実行する。

~~~powershell
$env:PYTHONPATH='shared;backend'
uv run --locked pytest backend/tests -q

$env:PYTHONPATH='shared;fetcher'
uv run --locked pytest fetcher/tests -q
~~~

media policyのtestでは少なくとも次を固定する。

- 既定値では本人mediaもdownloadしない。
- 有効時は本人の直接添付を保存する。
- 有効時でも別DIDのmediaをdownloadしない。
- リポスト元viewが完全でもmediaをdownloadしない。

## 8. 配備後の確認

| 対象 | 合格条件 |
|---|---|
| Git | 意図したcommit、clean worktree |
| Compose | `docker compose config`成功 |
| 一回実行service | `db-migrate`と`db-grants`がexit code 0 |
| 常駐service | `postgres`と`backend`がhealthy、`fetcher`・`frontend`・`nginx`がrunning |
| HTTP | `/`、`/api/health`、`/api/calendar`、`/api/timeline?limit=1`が成功 |
| media無効 | 同期後も`media/images`、`media/videos`、`media/captions`に実fileが増えない |
| media有効 | 本人の直接添付だけが保存され、リポスト元mediaが増えない |

通常更新で`docker compose down -v`を実行してはならない。これはPostgreSQL volumeを削除する。

## 9. 開発方法とライセンス境界

プロジェクトの方針と要件はmaintainerのHAYASHI Tsukasaが指示し、リポジトリに含まれるソースコード、テスト、ドキュメントの作成と変更はOpenAI Codexが行う。AI生成物を人間だけが作成したものとして表示しない。

リポジトリ独自のソースコードとドキュメントは、適用可能な権利の範囲でMIT Licenseにより提供する。著作権表示は`Copyright (c) 2026 HAYASHI Tsukasa`とし、OpenAIおよびOpenAI Codexを著作権者またはmaintainerとして表示しない。

次の対象はリポジトリのMIT Licenseに含めない。

- Python・Node.js依存ライブラリとそのtransitive dependency
- Docker base imageと配布物
- Bluesky API、AT Protocol実装、外部service
- 取得した投稿、Actor情報、raw JSON、画像、動画、字幕

これらは各権利者のlicense、利用規約、その他の適用条件に従う。第三者のlicense表示を削除したり、MIT Licenseで上書きしたりしない。
