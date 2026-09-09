# PLAN

現時点(Phase 0完了直後)の実装計画。詳細な調査根拠は`docs-src/discovery-report.md`
ほか`docs-src/*.md`を参照。ここでは「次に何を作るか」に絞る。

## スコープの確定(discovery-report.mdより)

一次対象は、72件中「HPがgeospatial.jp CKANを指し、かつCKAN
`resources[]`に実際にORIGINAL LAZ ZIPが存在すると個別確認できた」案件のみ。
現時点でこの条件を満たすと確認できているのは1件(`h25oribegawasabou`)。
残り42件のCKAN系候補は未確認、28件のArcGIS Hub系候補は保留。

**Phase 1の最初の実装対象は「43件のCKAN系候補を機械的に全件チェックし、
ORIGINAL LAZの有無を判定してSQLiteに記録する」ことであり、まだ1件も
COPC変換・公開はしない。**

## Source Cooperativeのディレクトリ/オブジェクトキー構造(提案)

72件が「1つの発注案件 = 1つのCKANパッケージ = 複数のLAZファイルを含みうる
original.zip」という構造であることを踏まえ、次の階層を提案する
(immutable URL / logical-asset-vs-versionモデルに準拠):

```
smartmaps/adopt-hokkaido-lidar/
  data/
    <ckan_package_name>/           # 例: h25oribegawasabou (CKAN側のslugをそのまま使う、安定・一意)
      <laz_stem>/                  # ZIP内の元ファイル名(拡張子抜き)。1 LAZ = 1 logical_asset
        v1/
          <laz_stem>.copc.laz      # 変換結果(不変)
          checksum.sha256
          validation_report.json
        v2/                        # 再変換が必要になった場合のみ追加。v1は残す
          ...
  catalog/
    index.geojson                  # 全logical_assetの footprint 集約(spatial index生成の入力)
    manifest.jsonl                 # published_asset の一覧(1行1レコード)
```

- `<ckan_package_name>`をキーに使う理由: CKANのpackage nameは既に一意・安定
  (URLの一部として使われており、CKAN側で変更されない前提のslug)。
  ArcGIS Hub系(28件)を将来対応する場合は、別のprefix
  (例: `data-arcgis/<item_id>/...`)を切って混在させない
- バージョンディレクトリ(`v1`, `v2`, ...)を切ることで、「同じ論理アセットの
  再変換」と「新しい版の公開」を、既存URLを壊さずに両立できる
- **この提案は未実施・未合意の設計案。実際にSource Cooperativeへ何かを
  書き込む前に、認証復旧後(下記「ブロッキング事項」参照)に再度確認する**

## 実装するモジュール(Phase 1、初期スキャフォールドの範囲)

`src/adopt_hokkaido_lidar/`:

- `arcgis.py` — Web Map JSON・coverage GeoJSONのパース、HPリンクの分類
  (ckan / arcgis-hub-search / なし)
- `ckan.py` — CKAN `package_show`レスポンスのパース、ORIGINAL LAZ候補の検出
  (確信が持てない場合は「候補」として返し、断定しない)
- `identifiers.py` — 安定したasset_id生成(package_name + laz_stemから決定的に生成)
- `eptium.py` — Eptium起動URLの生成(URLエンコード、クエリパラメータ`copc`)
- `zip_safety.py` — Zip Slip・パストラバーサル・シンボリックリンク・
  ZIP爆弾に対するガード(ZIP展開前の検証ロジック)
- `db.py` — SQLiteスキーマ(9エンティティ)のDDLとマイグレーション

CLIは`python -m adopt_hokkaido_lidar <verb>`として直接実行可能にし、
`justfile`はそれを呼ぶだけの薄いラッパーとする(ロジックはjustfileに書かない)。

## 明示的に今回はやらないこと

- 全72件・全43件の一括ダウンロード
- Source Cooperativeへの実書き込み(認証が期限切れのため、そもそも現状不可能。
  下記参照)
- GitHub Pagesの本番公開
- provenance・ライセンス未確認のデータの公開

## ブロッキング事項

**Source Cooperativeへの読み書きアクセスが、認証切れのため今回は確認できていない。**

- 公式CLI(`source-coop`)がインストール済みで、`~/.aws/config`に
  `credential_process = source-coop creds`という安全なパターン
  (静的キーをファイルに保存しない、AWS推奨の方式)で設定済みであることは確認した
- しかし`aws s3 ls`を試したところ「Cached credentials have expired.
  Run 'source-coop login' to refresh.」と返された
- `source-coop login`はOIDC経由のブラウザログインを要するインタラクティブな
  操作であり、非対話的なこのセッションからは実行できない
  (CAPTCHA同様、ユーザー本人の操作が必要な認証フロー)

**→ hfuさんに`source-coop login`の実行をお願いしたい。** 完了後、
`aws s3 ls s3://smartmaps/adopt-hokkaido-lidar/ --profile source-coop
--endpoint-url https://data.source.coop`で読み取りアクセスを確認する
(これも書き込みは伴わない安全な確認コマンド)。
