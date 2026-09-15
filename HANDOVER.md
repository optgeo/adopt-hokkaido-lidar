# HANDOVER

## Status as of 2026-09-16 07:15頃(JST) — Jクレ273件、完全公開達成

このセッションはここで一区切り。**Jクレ273 source_package全件が
`published`のみ(validated/discovered/suspended_provenance_reviewいずれも0件)
に到達した。** バッチ処理プロセスは完走・終了済み。次はJクレ以外
(CKAN・ArcGIS Hub残り)へ着手するフェーズ。

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
```

到達時点の実測値(2026-09-16 07:15頃):
- `published_asset`: **3539件**
- `logical_asset`ステータス内訳: `published` 3539件のみ
  (`validated`/`discovered`/`suspended_provenance_review`すべて0件)
- Jクレ全273 source_package、**全メンバー公開完了**

## ✅ 解決済み: 「同一403が繰り返される」問題の正体(2026-09-16に判明)

2026-09-12〜13にかけて3パッケージが繰り返し`ingest: HTTPError 403`で
失敗していた件(旧版のこのファイルで「要人間確認」としていたもの)は、
**アイテム固有のアクセス制限ではなかった**。実際に該当ArcGISアイテム
(`41804cddcecc4a0193e60fc0d302b4c2`)を人間が直接確認したところ:

- アイテムメタデータは`"access":"public"`、ブロックの形跡なし
- コードと全く同じリクエスト(Range `bytes=0-0`・同一User-Agent、
  redirectを手動でたどる)を実行したところ、`302→302→206`と正常応答
- 共通点: 3件とも**約1.6〜1.8GB級の大容量ZIP**だった

**推定原因**: ArcGISのdata URLはS3署名付きURL(有効期限10分、
`X-Amz-Expires=600`)にリダイレクトする。このマシンは複数のClaude Code
フリートセッションが並行稼働し帯域を奪い合うため、大容量ファイルの
ダウンロードが署名の10分枠内に収まらず期限切れになり、403として
表面化していた可能性が高い(`http_client.py`は403を1回だけリトライする
設計だが、帯域競合による遅延には不十分だった)。**対処は単純再実行**
(3回目で3件とも成功)。今後も大容量アイテムで同様の403が出たら、まず
ネットワーク帯域が空いているタイミングでの再実行を試すこと——アイテム
個別のアクセス制限を疑うのは、それでも複数回失敗する場合のみでよい。

## ⚠️ 最重要: `state.sqlite3`は絶対に消さない・上書きしない

`.work/state.sqlite3`はgitignore対象で**ローカルにしか存在しない**。これが
2032件の公開実績・provenance判断・attribution記録すべての唯一の記録。
バックアップが無いので、削除・置き換え・別環境への「まっさらな再init」は
絶対にしないこと。触る前に一度どこかにコピーを取っておくと安全。

## `.work/`は今回未掃除(次に触るセッションで掃除してよい)

2026-09-16時点で`.work/`は約35MB(`*.validation_report.json`が約47個
残っている——公開は完了しているのでSQLiteに同内容が記録済み、いつでも
削除して問題ない)。過去2回(2026-09-12・09-13)と同じ方針で、次に
このプロジェクトに触るセッションが`*.validation_report.json`・
`*.copc.laz`・`catalog_index.*`/`catalog_manifest.jsonl`を削除して
`batch_full.log`+`state.sqlite3`のみに戻してよい(コマンド例は過去の
git log参照)。

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

## ロードアベレージ監視(2026-09-13セッションで新規導入)

このマシンでは多数のClaude Codeフリートセッションが並行稼働しており、
バッチのCPU負荷は小さくても**マシン全体のロードアベレージ**が跳ねることが
頻繁にある(観測範囲: 1分値で最大30台、原因はこのバッチ以外の並行プロセス
であることが多い——`identityservicesd`等のmacOSデーモンが一時的に暴走する
ケースも観測)。この対策として:

- `CronCreate`で15分間隔の監視ジョブを登録し、`uptime`の1/5/15分いずれかが
  **25超**なら`kill -STOP`でバッチを一時停止、**20未満**に戻ったら
  `kill -CONT`で再開(20と25の間はヒステリシス、頻繁な停止/再開の
  バタつきを防ぐため)。
- カウントベース(`published_asset`件数)のポーリングは行わず、時間ベースの
  この監視に一本化する方針(ユーザーの明示的な指示、2026-09-13)。
- バッチ完了・クラッシュを検知したら`CronDelete`でこの監視ジョブ自体を
  停止すること(放置すると7日後に自動失効するが、早めに掃除するのが望ましい)。
- 再開時は同じ発想でこの監視ジョブを再設定すること。プロンプト文面は
  このセッションのやり取りに実例あり(cron idは使い捨てなので都度新規作成)。

**⚠️ `Monitor`ツールを使う際の落とし穴(2026-09-16に発生・自己解決)**: `command`
パラメータ内で`<`や`&`を含むシェル構文(`wc -l < file`、`cmd &`によるバック
グラウンド化等)を書く際、開始行番号の算出にバグがあると`tail -n +N -f`が
意図しない位置から出力し、**古いログ内容を「新規イベント」として誤通知する**
ことがある(state.sqlite3自体は無事だったが、一時的にバッチを誤ってSIGSTOPで
止める誤判断につながった)。対策: 行番号算出(`$(wc -l < file)+1`)より、
`tail -n 0 -f file`(呼び出し時点のファイル末尾から追従、算出不要)の方が
事故りにくい。何か疑わしいイベントが来たら、まず`ls -la`でファイルの
mtimeが本当に更新されているか確認してから対応すること。

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

- **Jクレ273件は完全公開完了(2026-09-16)。次はここから**:
- CKAN系43件(text_csv変換パス、`ingest.py`では`NotImplementedError`のまま)
  ——次に着手する自然な候補
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
