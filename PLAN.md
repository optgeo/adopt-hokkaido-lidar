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

## 明示的に今回はやらないこと

- 全72件・全43件の一括ダウンロード
- Source Cooperativeへの実データアップロード(アクセス自体は確認済み。
  下記「解決済み」参照。あくまで本番データの投入はまだ行わないという意味)
- GitHub Pagesの本番公開
- provenance・ライセンス未確認のデータの公開

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
