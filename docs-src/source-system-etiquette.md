# Source System Etiquette

対象システムへの負荷を最小化し、REST APIを優先し、丁寧にアクセスする。

## 原則

- REST APIを最優先する。ArcGIS(`sharing/rest`、FeatureServer)、
  geospatial.jp CKAN(`ckan/api/3/action/*`)とも、公式REST APIのみで
  Phase 0調査を完結できることを確認済み。Playwright/Seleniumのような
  ブラウザ自動化は今のところ不要で、第一選択にしない
- メタデータ取得・ダウンロードの同時実行数は2以下に制限する
- HTTP 429やRetry-Afterヘッダーを尊重し、指数バックオフで再試行する
- レスポンスをキャッシュし、可能な箇所ではETag/Last-Modifiedによる
  条件付きリクエストを使う
- User-Agentには、プロジェクト名・バージョン・リポジトリURL・連絡先を明示する
  (例: `adopt-hokkaido-lidar/0.1 (+https://github.com/optgeo/adopt-hokkaido-lidar; contact: <未設定>)`)。
  **連絡先が未設定の間は、本格アクセス(全件クロールや大量ダウンロード)の前に
  警告する**——現時点では調査目的の少数リクエストのみに留めている
- 全件ダウンロードの前に、必ず小規模テスト(1件のみ)を行う

## 本調査(Phase 0)での実施状況

- User-Agentの明示的な設定は未実装(curlのデフォルトを使用した)。
  Phase 1でHTTPクライアントを実装する際に対応する
- `original.zip`(487MB)は、フルダウンロードせずレンジGET
  (`Range: bytes=0-1023`)で先頭1KBのみ取得し、ZIPマジックバイトと
  ディレクトリエントリ名を確認する方法で検証した。この方法は今後の
  「全件ダウンロード前の小規模テスト」としても再利用できる
- レンジGETが機能したことから、geospatial.jpのCKANストレージ(S3/CloudFront)は
  HTTP Rangeリクエストに対応していることを確認済み。これは将来のresumable
  downloadの実装に使える

## 未確認・今後の課題

- 実際の同時実行数制限・バックオフの実装はまだ無い(調査フェーズでは
  単発リクエストのみだったため必要が無かった)
- geospatial.jp・ArcGIS双方のrate limit / 利用規約上の明示的な制限は
  未確認(公開情報として明記されているか、Phase 1着手前に確認する)
