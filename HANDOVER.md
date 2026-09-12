# HANDOVER

## Status as of 2026-09-12 13:50頃(JST) — バッチは意図的に停止中(グレースフル停止済み)

このセッションはここでcompact/clearされ、専用エージェントに引き継ぐ。
**バッチ処理プロセスは既に安全にkillされ、`.work/`も掃除済み。壊れて
止まっているのではなく、意図的に一時停止した状態。** 再開は下記
「再開手順」からそのまま行える。

- リポジトリ: https://github.com/optgeo/adopt-hokkaido-lidar
- 地図サイト: https://optgeo.github.io/adopt-hokkaido-lidar/
- Source Cooperative: https://source.coop/smartmaps/adopt-hokkaido-lidar
- ローカル作業ディレクトリ: `/Users/hfu/adopt-hokkaido-lidar/`
  (Pythonパッケージ本体は`src/adopt_hokkaido_lidar/`、Webサイトは`web/`
  ——ビルド出力`docs/`がGitHub Pages配信元)

## まず確認すべきこと(再開前に必ず)

```bash
cd /Users/hfu/adopt-hokkaido-lidar
sqlite3 .work/state.sqlite3 "SELECT count(*) FROM published_asset;"
sqlite3 .work/state.sqlite3 "SELECT status, count(*) FROM logical_asset GROUP BY status;"
ps aux | grep process-jkure-batch   # 何も出ないはず(停止済み)
ls -la .work/                        # batch_full.log と state.sqlite3 のみのはず
```

停止時点の実測値(2026-09-12 13:50頃):
- `published_asset`: **2032件**
- `logical_asset`ステータス内訳: `published` 2032 / `validated` 230 /
  `discovered` 14 (`suspended_provenance_review`は0件——ゲート弾かれは今のところ発生していない)
- 直近まで処理していたバッチ起動時点で「未公開パッケージ」119件が対象に
  なっており、そのうち19件処理したところで停止(ログ末尾: `[19/119] ... published`)
- Jクレ全273件中、何らかのlogical_assetが存在する(=着手済み)source_packageは
  **183件**(distinct count、SQLで再確認可)

## ⚠️ 最重要: `state.sqlite3`は絶対に消さない・上書きしない

`.work/state.sqlite3`はgitignore対象で**ローカルにしか存在しない**。これが
2032件の公開実績・provenance判断・attribution記録すべての唯一の記録。
バックアップが無いので、削除・置き換え・別環境への「まっさらな再init」は
絶対にしないこと。触る前に一度どこかにコピーを取っておくと安全。

## `.work/`を掃除済み(このセッションで実施)

グレースフル停止の一環として、以下を削除した(すべて再生成可能な
中間生成物、または`state.sqlite3`に重複記録済みのもの):

- `*.validation_report.json` 2262個(SQLiteに同内容が記録済み)
- 未公開のまま残っていた`*.copc.laz` 231個(≒15GB分——ダウンロード・
  変換は完了していたが、アップロード前だったもの)
- リーフトーバー`*.raw.*`中間ファイル 1個
- カタログビルド生成物一式(`catalog_index.geojson`/`.pmtiles`、
  `catalog_manifest.jsonl`、および旧世代の`index.geojson`/`.pmtiles`/
  `manifest.jsonl`)

結果、`.work/`は約15GB→約20MBに縮小(`batch_full.log`+`state.sqlite3`のみ)。

**影響**: 上記231件の「変換済みだが未公開だった」COPCファイルはローカルに
もう存在しない。次回バッチ再開時、これらのsource_memberは
`already_published`チェックで「未公開」と判定されるため、**ZIPの
再ダウンロード→再変換からやり直しになる**(データ破損ではなく、単に
やり直しの手間が発生するだけ。詳細は`ingest.py`の`already_published`
判定ロジック参照)。

## 再開手順

1. **source-coop認証を確認**(下記「認証関連の既知の問題」参照):
   ```bash
   source-coop creds  # Expiration フィールドを確認、切れていれば source-coop login
   aws s3 ls s3://smartmaps/adopt-hokkaido-lidar/ --profile source-coop --endpoint-url https://data.source.coop
   ```
2. **起動コマンド**(これまでと完全に同一、コピペで再開可):
   ```bash
   cd /Users/hfu/adopt-hokkaido-lidar
   nohup uv run python -m adopt_hokkaido_lidar process-jkure-batch \
     --vertical-datum "JGD2011 (vertical) height, EPSG:6695 (推定。根拠: 2023年度測量でJGD2011が公式標準/実測値がGSI正標高とほぼ一致。公式仕様書は未発見、LAZヘッダー自体はJGD2000を記載——誤表記の可能性が高いと判断)" \
     --organization "道有林課" \
     --license "CC-BY" \
     --db-path .work/state.sqlite3 \
     --work-dir .work \
     >> .work/batch_full.log 2>&1 &
   disown
   ```
3. 進捗監視は`Monitor`ツールで`batch_full.log`をtail(エラー/完了/クラッシュ
   シグネチャでフィルタ)、または`state.sqlite3`の`published_asset`件数を
   定期ポーリング。**`ScheduleWakeup`は使わない**——バックグラウンドプロセスの
   完了通知は自動で届く(このセッションで一度誤用し、自己修正した経緯あり)。
4. 10件公開ごとに進捗報告、報告には必ずJST時刻を付ける(ユーザーの明示的な
   要望)。

## 認証関連の既知の問題と対処

1. **`source-coop login`のセッション有効期限は実測で最大12時間程度**:
   `--duration 12h`・`--duration 24h`のどちらを指定しても、`source-coop creds`の
   `Expiration`フィールドで確認すると実際は約12時間しか付与されない
   (Source Cooperative側のIAMロールの実効上限と推測、24hを指定しても
   延びない)。長時間バッチを回す前提なら、この12h制約を織り込んでおくこと。
2. **11時間以上の連続稼働で断続的に`credential_process`が失敗する**:
   「`Cached credentials have expired`」「`No cached credentials found`」が、
   手動で`source-coop creds`を確認すると成功しているのに、バッチ側では
   繰り返し失敗することがあった。macOSキーチェーンへのアクセスが長時間
   起動プロセス下で劣化する挙動が疑わしい(確証はない状況証拠ベース)。
   **有効だった対処**: `source-coop login`のやり直しではなく、**バッチ
   プロセス自体をkill&再起動**すると復旧する。再ログインだけでは直らない
   ことが複数回確認されている。
3. リトライ戦略: ArcGIS側の一時的403、Source Cooperative側の一時的520/接続
   エラーは自動リトライ済み(`http_client.py`/`sc_client.py`)。ただし
   ユーザーの判断("3を試してみようか")で最大リトライ回数は5→1に下げてある
   ——リトライ蓄積によるペース低下を避け、失敗した項目は次回バッチ再実行時に
   自然に拾われる設計。

## 直近で解決した問題(再発防止のため記録——同じ穴に落ちないこと)

1. **DEM地形の誇張バグ**: `exaggeration`値の問題ではなく、
   `mapterhorn-japan-bridge`のraster-demソースに`encoding: 'terrarium'`が
   未指定だったことが原因(MapLibre既定はmapbox形式で、誤デコードすると
   標高が実際の約5,400倍になる)。`web/src/main.ts`で修正済み・本番反映済み。
2. **1 ZIP内に複数LAZファイルが入るケース**: 「1 source_package =
   1 logical_asset」という当初設計を、実際に16件のLAZを含むZIPが
   見つかったことで「1 source_package = 複数logical_asset」に修正済み
   (`ingest.py`の`ingest_arcgis_source_package()`が全メンバーをループする
   設計、discovery-report.md §8)。あわせて`find_unpublished_jkure_packages()`
   の再開判定ロジックも「ANYが公開済みなら完了」から「ALLが公開済みで
   なければ未完了」に修正済み(修正前は16件中1件公開されただけで残り15件が
   永久にスキップされるバグがあった)。
3. **h25oribegawasabou案件のLAZ誤認**: 先頭1KBだけを見て「LAZらしい」と
   判断したのが誤りで、実際は31個の`_org.txt`(プレーンテキストXYZ CSV)
   だった。以後、候補判定は必ず`zip_inspect.py`によるフルcentral directory
   解析で確認してから信頼する運用に統一済み。

## アーキテクチャの要点(詳細はPLAN.md・docs-src/discovery-report.md参照)

- 発見: ArcGIS org横断タグ検索(`tags:"LAZ" AND tags:"ORIGINAL"`)+
  geospatial.jp CKAN(`package_show`)の2経路併用
- 変換: PDAL、`readers.las`→`writers.copc`、CRS埋め込みは信頼するが
  JGD2000/2011の食い違いは人間確認事項として記録
- 公開ゲート: license/crs/vertical_datum/attribution(source_data/
  processing/hosting)が揃わないと`suspended_provenance_review`になり
  自動公開されない(`publish.py: check_publish_gate()`)
- SCキー構造: `data/<source_system>/<source_package_id>/<raw_stem>/v<N>/...`
- カタログ: `catalog/index.pmtiles`(`asset_id`のみ)+`catalog/manifest.jsonl`
  (`asset_id`→`object_url`)。地図サイトはこの2つをSCから直接fetchする
  (`docs/`にはカタログの実体を置かない)。`build-catalog`は1公開ごとに
  バッチ内から自動で呼ばれる設計(`batch.py: run_batch`)——地図サイトは
  常にほぼ最新のはず

## 未着手・既知の非効率(次の一手)

- Jクレ残り(273件中、着手済み183件・完全公開は要件次第で数え方が変わる
  ——正確な残数は上の確認コマンドで都度出し直すこと)
- CKAN系43件(text_csv変換パス、`ingest.py`では`NotImplementedError`のまま)
- ArcGIS Hub系の残り26件(LAZ無し確認済み・対象外)・HPなし1件(未調査)
- **既知の非効率(未修正、対応は未着手のまま停止)**: `already_published`判定が
  「公開済みか」だけを見ており「変換済みだが未公開」を区別しない。そのため
  公開失敗の連鎖(例: 認証切れ)が起きた直後にバッチを再開すると、
  ダウンロード・変換済みだったファイルまで無駄に再ダウンロード・再変換される。
  今回の`.work/`掃除でも同じ理由で231件分の変換済みファイルを失っている。
  改善するなら「ローカルにCOPCが存在し中身がvalidateされていれば再変換せず
  publishだけやり直す」ような中間状態の判定を追加する必要がある。

## Where to look

- 調査の全記録・訂正履歴 → [docs-src/discovery-report.md](docs-src/discovery-report.md)
- 実装計画・達成事項のログ → [PLAN.md](PLAN.md)
- 帰属表示の方針 → [docs-src/attribution.md](docs-src/attribution.md)
- 公開可否の判定基準 → [docs-src/provenance-policy.md](docs-src/provenance-policy.md)
