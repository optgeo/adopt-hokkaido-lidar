# Provenance Policy

## 公開の可否を決める判定

`published_asset`として実際に公開してよいのは、次のすべてを満たす場合のみ:

1. `source_item`/`source_package`が、CKAN(またはArcGIS Item)の一次情報から
   直接取得したライセンス情報を持つ(推測・キャッシュされた一般論ではない)
2. その`source_package`に「ORIGINAL LAZ」相当のリソースが実在することを、
   実際にAPIレスポンスを読んで確認済みである
   (discovery-report.md §3の通り、これは保証されないため必須の判定ステップ)
3. `derived_asset_version`(COPC変換結果)がPDALによる妥当性検証
   (COPC構造検証、点数・bbox・CRS等の整合性チェック)を通過している
4. attribution(source_data/basemap/elevation/processing/hosting)がすべて
   記録済みである

## 判定に失敗した場合

**自動削除しない。** 上記のいずれかを満たさない場合、そのlogical_assetは
`suspended_provenance_review`相当のステータスに置き、人間のレビュー待ちとする。
理由(どの条件を満たさなかったか)を必ず記録する。

該当例(discovery-report.mdより):
- ArcGIS Hubタグ検索系の28案件は、条件2を満たすかどうか自体が未確認
  (点群アイテムが見当たらない)ため、この段階では`suspended_provenance_review`
  相当として保留する
- CKAN系でも`original.zip`が存在しない案件(例: `r01biseikawasabou`、
  `hokkaido-h30atumachiku`)は、条件2を満たさないため同様に保留する

## 不変性(immutability)

一度公開した`published_asset`のオブジェクトURLは上書きしない。同じlogical_asset
の新しいバージョンを公開する場合も、新しいバージョン識別子を含む新規URLを発行する。
「latest」に相当する固定名オブジェクトを繰り返し上書きする運用はしない
(起動プロンプト第35節で明示的に禁止されている)。

## 監査可能性

SQLite状態・マニフェスト・チェックサム・provenanceレコード・検証レポート・
公開カタログは、`just clean-apply`を含むいかなるクリーン操作でも削除しない
(元データとの対応関係を将来にわたって追跡可能にするため)。
