# Attribution Policy

## 原則

帰属表示はスコープごとに分離して保持・表示する。「READMEに1箇所書けば足りる」
という設計は禁止(起動プロンプト第35節)。最低限、以下のスコープを区別する:

| スコープ | 内容 | 現時点の値(例) |
|---|---|---|
| `source_data` | 原本LiDARデータの著作権者・ライセンス | 案件ごとに個別確認が必要。**一括で「北海道庁」と書かない**(§discovery-report.md §3.3) |
| `basemap` | 背景地図 | 「国土地理院最適化ベクトルタイル」(bvmap-dark) |
| `elevation` | 地形・陰影起伏 | 「国土地理院 (GSI Japan). Processed with Mapterhorn (japan-bridge, interim).」 |
| `processing` | LAZ→COPC変換等の処理主体 | 本プロジェクト(`optgeo/adopt-hokkaido-lidar`) |
| `hosting` | 変換済みCOPCの配布主体 | Source Cooperative(`smartmaps/adopt-hokkaido-lidar`) |
| `external_viewer` | Eptium等の外部ビューア | Eptium(https://eptium.com/、本プロジェクトとは無関係の第三者サービス) |

## `source_data`について、絶対に守ること

- ArcGIS Itemの`owner`(例: `opendatahok`)を、データの著作権者や提供組織と
  **絶対に混同しない**。今回のケースでは`opendatahok`はポータル運営者
  (酪農学園大学、Rakuno Gakuen University)であり、実際のデータ提供組織は
  CKAN側の`organization`(北海道庁の各部局)である
  (discovery-report.md §1「ポータル運営者と発見済み」の節を参照)
- CKANの`organization.title`は案件によって異なる(確認済み例:
  「総合政策部」「水産林務部」)。`published_asset`ごとに、その案件固有の
  organization名を保持する。決して「北海道」「北海道庁」のような上位概念に
  丸めない
- ライセンスは案件ごとに`license_id`を実際に取得して記録する
  (これまでのサンプルはすべてCC-BYだったが、網羅確認は未実施——
  discovery-report.md §3.3参照)
- CC-BYの再配布条件(改変・派生データへの追加ライセンス付与の可否等)は、
  CKAN organizationの説明文に案件横断で書かれている場合がある(例:
  「hokkaidopref-ss」組織の説明文に、画像データはODbLでなくCC-BYを適用する旨の
  記載を確認済み)。この種の説明文はorganizationごとに異なりうるため、
  organizationが変われば再確認する

## データモデル上の扱い

`attribution`エンティティ(起動プロンプトで定義された9エンティティの1つ)は、
上記スコープを`scope`フィールドで区別して複数レコード持つ設計とする。
1つの`logical_asset`は複数の`attribution`レコード(source_data 1件 +
basemap 1件 + elevation 1件 + ...)を持ちうる。
