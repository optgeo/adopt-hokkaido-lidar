# HANDOVER

## Status as of 2026-09-10 早朝(JST)

Phase 0(調査)〜Phase 1前半(Jクレ案件のバッチ公開)まで進行中。
バックグラウンドでバッチ処理が実行中——**この文書を読んだら、まず現在の
進捗を確認すること**:

```bash
sqlite3 /Users/hfu/adopt-hokkaido-lidar/.work/state.sqlite3 "SELECT count(*) FROM published_asset;"
ps aux | grep process-jkure-batch
tail -30 /Users/hfu/adopt-hokkaido-lidar/.work/batch_full.log
```

- リポジトリ: https://github.com/optgeo/adopt-hokkaido-lidar
- 地図サイト: https://optgeo.github.io/adopt-hokkaido-lidar/
- Source Cooperative: https://source.coop/smartmaps/adopt-hokkaido-lidar
- ローカル作業ディレクトリ: `/Users/hfu/adopt-hokkaido-lidar/`
  (Pythonパッケージ本体は`src/adopt_hokkaido_lidar/`、Webサイトは`web/`
  ——ビルド出力`docs/`がGitHub Pages配信元)

## 今バックグラウンドで動いていること

`process-jkure-batch`コマンドが、Jクレ案件(道有林課、2023年度、
森林由来カーボンクレジット測量)の273件のsource_packageを1件ずつ処理中。
起動コマンド(再開する場合はこれと同じ):

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

進捗は`published_asset`テーブルの件数で確認する(2026-09-10 06:50頃時点で
44件)。273件中、1件あたりのLAZファイル数は1件〜16件以上とばらつきがあり
(discovery-report.md §8参照)、総logical_asset数は273より大幅に多くなる
見込み。

## 直近で解決した問題

1. **DEM地形の誇張バグ(2026-09-09深夜)**: 「地形が誇張されすぎている」と
   指摘を受け調査した結果、`exaggeration`値の問題ではなく、
   **`mapterhorn-japan-bridge`のraster-demソースに`encoding: 'terrarium'`が
   未指定だった**ことが原因と判明。MapLibreの既定(mapbox形式)で誤ってデコード
   すると標高が実際の約5,400倍(147m→832,816m)になっていた。実タイルを
   デコードして検証済み。修正・本番反映済み(コミット`2c7911d`)
2. **1 ZIP内に複数LAZファイルが入るケース**: 当初「1 source_package = 1
   logical_asset」という設計だったが、実際には16件のLAZファイルを含む
   ZIPが見つかった。設計を「1 source_package = 複数logical_asset」に修正
   (discovery-report.md §8、コミット`4759ff4`)
3. **Source Cooperative認証の期限切れが繰り返し発生**: `source-coop login`の
   セッションが1時間弱で切れる。バッチ処理中に切れると、残り全アイテムの
   アップロードが失敗し続ける(ダウンロード・変換は成功するが公開できない)。
   **対策**: 次回ログイン時に`source-coop login --duration 12h`のように
   長めのセッション時間を指定することを推奨(未検証、ロール側の上限次第)。
   `source-coop creds`はキャッシュを読むだけで延命効果は無い

## 認証が切れて止まっている場合の再開手順

1. hfuさんに`source-coop login`(できれば`--duration`オプション付き)を
   実行してもらう
2. `aws s3 ls s3://smartmaps/adopt-hokkaido-lidar/ --profile source-coop --endpoint-url https://data.source.coop`で疎通確認
3. 上記の起動コマンドを再実行(`find_unpublished_jkure_packages`が
   未公開分だけを自動的に拾うため、公開済み分は再ダウンロードされない
   ——ただし「1つのZIPの一部だけ公開済み」の場合、そのZIP自体は
   再ダウンロード・再展開される。個別メンバーの再変換はスキップされる
   `already_published`チェックあり、詳細は`ingest.py`参照)

## アーキテクチャの要点(詳細はPLAN.md・docs-src/discovery-report.md参照)

- 発見: ArcGIS org横断タグ検索(`tags:"LAZ" AND tags:"ORIGINAL"`)
- 変換: PDAL、`readers.las`→`writers.copc`、CRS埋め込みは信頼するが
  JGD2000/2011の食い違いは人間確認事項として記録
- 公開ゲート: license/crs/vertical_datum/attribution(source_data/
  processing/hosting)が揃わないと`suspended_provenance_review`になり
  自動公開されない
- SCキー構造: `data/<source_system>/<source_package_id>/<raw_stem>/v<N>/...`
- カタログ: `catalog/index.pmtiles`(`asset_id`のみ)+`catalog/manifest.jsonl`
  (`asset_id`→`object_url`)。地図サイトはこの2つをSCから直接fetchする
  (`docs/`にはカタログの実体を置かない)

## 未着手・次の一手

- Jクレ272件(残り)の完了を待つ
- CKAN系43件(text_csv変換パス、`ingest.py`では`NotImplementedError`のまま)
- ArcGIS Hub系の残り26件・HPなし1件(discovery-report.md §3.2、対象外/要調査)
- カタログ生成は`build-catalog`コマンドで自動化済みだが、バッチの中で
  1公開ごとに呼ばれる設計(`batch.py`の`run_batch`参照)——都度SCへ
  アップロードされるため、地図サイトは常にほぼ最新の状態のはず

## Where to look

- 調査の全記録・訂正履歴 → [docs-src/discovery-report.md](docs-src/discovery-report.md)
- 実装計画・達成事項のログ → [PLAN.md](PLAN.md)
- 帰属表示の方針 → [docs-src/attribution.md](docs-src/attribution.md)
- 公開可否の判定基準 → [docs-src/provenance-policy.md](docs-src/provenance-policy.md)
