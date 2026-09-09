# PLAN

現時点(Phase 0完了直後)の実装計画。詳細な調査根拠は`docs-src/discovery-report.md`
ほか`docs-src/*.md`を参照。ここでは「次に何を作るか」に絞る。

## スコープの確定・処理優先順位(discovery-report.mdより、2026-09-09更新)

**最初に処理するのは「Jクレジット」案件**(道有林課、ArcGIS発見、273件の
図郭単位ORIGINAL LAZ、CC-BY確認済み、ダウンロード経路も検証済み)。
理由: 現時点で最も検証が進んでおり、確実に成功させられる対象だから。

その他のスコープ(discovery-report.md §5参照):

- CKAN系43件: `resources[]`にZIPがあっても、中身が実際にLAZ/LASかは
  `zip_inspect.py`で中央ディレクトリを開くまで断定できない
  (h25oribegawasabouは実はXYZ点群CSVだった、という訂正済みの実例あり)
- ArcGIS Hub系28件中26件: ORIGINAL LAZが存在しないことを確認済み。対象外
- HPなし1件: 個別要調査のまま(優先度低)

## Source Cooperativeのディレクトリ/オブジェクトキー構造(実例で確定)

発見系統(CKAN / ArcGIS)ごとにIDの意味が根本的に異なる
(CKAN package slug vs ArcGIS item id)ため、`source_system`を第一階層に
置く形に確定した:

```
smartmaps/adopt-hokkaido-lidar/
  data/
    arcgis/
      fccdb80933434b3ab45bb7b725207e6b/    # ArcGIS item id(Jクレ案件、実例)
        12he811/                           # 図郭番号(拡張子抜き)。1 raw file = 1 logical_asset
          v1/
            12he811.copc.laz               # 変換結果(不変)
            checksum.sha256
            validation_report.json         # source_format: "las" をここに記録
          v2/                              # 再変換が必要になった場合のみ追加。v1は残す
    ckan/
      h25oribegawasabou/                   # CKAN package slug(実例)
        13nc012/
          v1/
            13nc012.copc.laz
            checksum.sha256
            validation_report.json         # source_format: "text_csv" をここに記録
  catalog/
    index.geojson                  # 全logical_assetの footprint 集約(spatial index生成の入力)
    manifest.jsonl                 # published_asset の一覧(1行1レコード)
```

- バージョンディレクトリ(`v1`, `v2`, ...)を切ることで、「同じ論理アセットの
  再変換」と「新しい版の公開」を、既存URLを壊さずに両立できる
- Source Cooperativeへの読み書きアクセスは確認済み(下記「解決済み」参照)。
  上記は実例で裏付けたキー構造の確定案。実際の書き込みは
  Jクレ案件の最初の1件で試してから、残りに展開する

## 実装するモジュール(Phase 1、初期スキャフォールドの範囲)

`src/adopt_hokkaido_lidar/`:

- `arcgis.py` — Web Map JSON・coverage GeoJSONのパース、HPリンクの分類
  (ckan / arcgis-hub-search / なし)
- `ckan.py` — CKAN `package_show`レスポンスのパース、ORIGINAL LAZ候補の検出
  (stage 1、CKANメタデータのみに基づく「候補」——確定は`zip_inspect.py`で行う)
- `zip_inspect.py` — ZIPの中央ディレクトリをレンジGETで取得・パースし、
  実際のメンバー拡張子(`.laz`/`.las` vs `.txt`/`.csv`)を判定する(stage 2、実地確認)
- `identifiers.py` — 安定したasset_id生成
  (`source_system` + `source_package_id` + `raw_member_path`から決定的に生成)
- `eptium.py` — Eptium起動URLの生成(URLエンコード、クエリパラメータ`copc`)
- `zip_safety.py` — Zip Slip・パストラバーサル・シンボリックリンク・
  ZIP爆弾に対するガード(ZIP展開前の検証ロジック)
- `db.py` — SQLiteスキーマ(9エンティティ)のDDLとマイグレーション。
  `source_system`/`responsible_department`/`raw_member_path`/`raw_format`/
  `source_format`を含む(2026-09-09改訂版)

CLIは`python -m adopt_hokkaido_lidar <verb>`として直接実行可能にし、
`justfile`はそれを呼ぶだけの薄いラッパーとする(ロジックはjustfileに書かない)。

## 次に実装するコマンド: ディスク容量ガード付きの逐次ingest/publish(承認済み、未実装)

2026-09-09、hfuさんから以下の方針で承認を得た。まだコードは無い(次の実装対象):

- 1件(または少数、同時ダウンロード数≤2)ずつ「ダウンロード→変換→検証
  (チェックサム一致)→アップロード→アップロード確認→ローカル削除」の順で処理する
- **各アイテムの処理開始前に空き容量を確認し、閾値(暫定20GB)を下回っていたら
  新規ダウンロードを開始せず一時停止する**——この машине(単一内蔵ディスク、
  空き83GB、外部ボリューム無し、確認済み)では、コーパス全体をローカルに
  保持することは前提にできないため、規律をコードで強制する
- 削除は「アップロード先で検証してから」のみ(確認前に消さない)
- SQLite状態・マニフェスト・チェックサム・検証レポートは、対応するCOPC
  そのものをローカル削除した後も残す(provenance-policy.md参照)
- 中断後の再実行時に「どこまで済んでいるか」を見て続きから再開する設計
  (真の意味での再入可能性)は、このコマンドの実装で初めて実現する
  ——現状の`identifiers`/`db`スキーマはその土台(決定的asset_id・追記型
  バージョニング)を用意しただけで、実行可能な再開ロジックはまだ無い

## 達成: 最初の1件を実際に公開し、地図上でクリック可能にした(2026-09-09)

`12JE14_ORIGINAL_LAZ`(item `fb8559df347e43e68f9634dbc17d9f6f`、約4.2MB、
448,887点)について、発見から地図表示まで全工程を実データで完了した:

1. `confirm-provenance` — 鉛直基準を記録
   (「JGD2011 (vertical) height, EPSG:6695、推定。根拠: 2023年度測量で
   JGD2011が公式標準/地面点の実測値がGSI正標高とほぼ一致(誤差0.07m、
   楕円体高なら30-40m乖離するはず)。公式仕様書(CKAN・ArcGIS・harp.lg.jp・
   道有林課ページを確認したが未発見)。LAZヘッダー自体はJGD2000を記載——
   誤表記の可能性が高いと判断」——hfuさんに承認済み)。
   帰属情報(source_data=道有林課/CC-BY、processing、hosting)を登録
2. `publish` — ゲート通過、実際にSource Cooperativeへアップロード成功
   (`https://data.source.coop/smartmaps/adopt-hokkaido-lidar/data/arcgis/
   fb8559df347e43e68f9634dbc17d9f6f/12je1411/v1/12je1411.copc.laz`、
   HTTP 200・CORS開放・Range対応を直接curlで確認済み)。
   ローカルCOPCは検証後に削除、SQLiteには`published`状態で記録
3. カタログ(`catalog/index.pmtiles`——`footprints`レイヤ、`asset_id`のみ、
   `catalog/manifest.jsonl`)を生成しSCへアップロード(**現状は手動、
   専用CLIコマンドは未実装——後述の次の一手参照**)
4. 本番サイト(https://optgeo.github.io/adopt-hokkaido-lidar/)を実際に
   操作し、名寄市近郊のフットプリントをクリック→ポップアップ→
   「Eptiumで開く」ボタンのURLが正しく実COPC URLを指していることを確認

**これで「ArcGIS Hub → CKAN/ArcGIS発見 → ORIGINAL LAZ → COPC → SC公開 →
地図でクリック可能」という一連の流れが、1件について実証された。**

### 次の一手(未実装)

- カタログ生成(footprint収集・PMTiles再構築・manifest追記)を
  専用CLIコマンド(`build-catalog`等)にする——現状は手動でtippecanoeを
  叩いている
- CKAN系(43件)の`ckan.py`→`zip_inspect.py`による実地判定パイプラインは
  まだCLIに配線されていない(`text_csv`変換もingest.pyでは
  `NotImplementedError`のまま)
- Jクレ案件の残り272件への展開(1件ずつ、閾値ガード付きで)
- ArcGIS Hub系(28件)の残り26件・HPなし1件は引き続き対象外/要調査のまま

## 明示的にまだやっていないこと

- 全72件・全272件(Jクレ残り)の一括ダウンロード・一括公開
- CKAN系43件への展開
- GitHub Pagesの本番公開は完了しているが、実データはまだ1件のみ
- provenance・ライセンス未確認のデータの公開(ゲートで引き続き強制)

## 解決済み: Source Cooperative読み書きアクセス

2026-09-09、hfuさんが以下を実施し、フルに確認できた:

1. `source-coop login`実行(OIDCブラウザログイン、ユーザー本人が実施)
2. Source Cooperative Web UI上で`smartmaps/adopt-hokkaido-lidar`
   プロダクトを作成(us-west-2、プラットフォーム管理接続)
   → https://source.coop/smartmaps/adopt-hokkaido-lidar
3. 読み取り確認: `aws s3 ls s3://smartmaps/adopt-hokkaido-lidar/
   --profile source-coop --endpoint-url https://data.source.coop` で
   プレフィックスが存在しアクセス可能なことを確認(当時は空、正常)
4. 書き込み確認: 78バイトのテストオブジェクト
   (`_write-probe/probe.txt`)をPUT→存在確認→DELETE→削除確認まで
   実施し、フルの読み書き権限を確認。テストオブジェクトは残っていない

`~/.aws/config`の`credential_process = source-coop creds`パターン
(静的キーをファイルに保存しない)は引き続き有効で、リポジトリや
ログには一切認証情報を書き込んでいない。

## Source Cooperative Product Title / Description(提案、hfuさんへ提示済み)

- Title案: "Hokkaido Aerial LiDAR (COPC)"
- Description: 出典・帰属は案件ごとに個別確認する旨、原本ZIP/LAZは
  再配布せずCOPC派生物のみを公開する旨を明記(全案件一括のライセンス表記は
  避ける)。詳細はSource Cooperative側のプロダクトページを参照

## 実装完了: ingest/publishコマンド、実データで動作確認済み(2026-09-09)

`src/adopt_hokkaido_lidar/`に以下を追加:

- `disk_guard.py` — 空き容量チェック(閾値20GB、`ingest_member`が新規
  ダウンロード前に必ず通す)
- `http_client.py` — User-Agent付きの丁寧なHTTPクライアント
  (`adopt-hokkaido-lidar/0.1 (+https://github.com/optgeo/adopt-hokkaido-lidar)`、
  hfuさんの選択によりメールアドレスは含めない)。429/Retry-Afterの
  指数バックオフ対応
- `arcgis_search.py` — ArcGIS org横断タグ検索(discovery-report.md §3.2で
  確認した`tags:"LAZ" AND tags:"ORIGINAL"`パターン)のネットワーク層
- `pdal_pipeline.py` — PDALパイプラインJSON構築(純粋関数、テスト済み)+
  subprocess実行(argvリスト、`shell=True`不使用)。`pdal info --metadata`
  経由でのCRS抽出も含む
- `zip_inspect.py`に`member_byte_range()`を追加——ZIP全体をダウンロードせず、
  1メンバーだけをレンジGETで取り出す(h25oribegawasabouのような多エントリZIPで
  帯域を節約する設計、実データで検証済み)
- `sc_client.py` — Source Cooperativeへのaws s3 cp/rm/head-objectラッパー
- `ingest.py` — 1メンバー分の「レンジDL→展開→PDAL変換→checksum→CRS抽出→
  validation_report生成」を実行。JGD2000のような疑わしい埋め込みCRSは
  自動補正せず、`validation_report.notes`に警告として記録するのみ
- `publish.py` — 公開ゲート(license/crs/vertical_datum/attribution一式が
  揃っているかを確認)。**不合格の場合はアップロードせず、
  `logical_asset.status`を`suspended_provenance_review`にして理由を記録する
  ——このゲートは実際に発火させて確認済み(下記)**

### 実データでのエンドツーエンド確認(2026-09-09)

Jクレ案件の中から最小のアイテム(`12JE14_ORIGINAL_LAZ`、約4.2MB)を選び、
`discover-jkure` → `ingest` → `publish`を実際に実行した:

1. `discover-jkure`: 273件のArcGISアイテムを実際に検索・記録(手作業調査時と
   同じ件数と一致)
2. `ingest fb8559df347e43e68f9634dbc17d9f6f`: ZIP全体ではなく該当メンバー
   (`ORIGINAL_LAZ/12JE1411.laz`)のみをレンジGETし、448,887点のCOPCへの
   変換に成功。CRSはこの案件でも同じくJGD2000(EPSG:2454)——単発ではなく
   このプロジェクト全体の傾向である可能性が高いことが分かった
3. `publish`: **想定通りゲートで拒否された**
   (`vertical_datum`未確認、`attribution[source_data/processing/hosting]`
   未登録)。ローカルのCOPCファイルは削除されず、
   `logical_asset.status='suspended_provenance_review'`として記録された

**この案件はまだ地図に公開できていない。** 鉛直基準の確認と帰属情報の
登録が次の実質的なブロッカー。
