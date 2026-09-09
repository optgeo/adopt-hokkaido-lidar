# Discovery Report

Phase 0 (source-system investigation) の記録。2026-09-09時点の一次調査結果。
以降のパイプライン設計は、ここに書かれた「確認済みの事実」にのみ基づく。
未確認の事項は「未確認」として明示し、憶測で埋めない。

## 1. 発見経路の全体構造

対象のArcGIS Item(`3029dee26c854f7da3566e77f5ec4c19`、Web Map、
タイトル「北海道オープンデータ5000図郭」、owner `opendatahok`)は、直接ダウンロード
リンク集ではなく、**索引**として機能している。

```
ArcGIS Web Map (3029dee26c854f7da3566e77f5ec4c19)
├── operationalLayers[0]: GeoJSON「オープンデータ範囲」
│     itemId 2af5a367e5584160a8fe6a73e9f90cab
│     → 72件のfeature。各featureが1つの発注案件(事業)に対応
│     → 各featureの `HP` プロパティが実データの入口
│
└── operationalLayers[1..3]: 5000図郭メッシュ(11系/12系/13系、FeatureServer)
      → 図郭単位の検索補助レイヤ。`URL`フィールドはHubのUI検索ページへのリンクで、
        機械的な直接ダウンロード手段ではない(§4参照)
```

## 2. 「オープンデータ範囲」72件の内訳(確認済み)

72件の`HP`リンクの遷移先を機械的に分類した結果:

| 分類 | 件数 | 遷移先 |
|---|---|---|
| geospatial.jp (CKAN) | 43 | `https://www.geospatial.jp/ckan/dataset/<slug>` |
| ArcGIS Hub タグ検索 | 28 | `https://opendata-rakuno-gis.hub.arcgis.com/search?tags=...` |
| 空文字列(HPなし) | 1 | (「2022-A-0068 上流川 砂防工事地形調査」、リンク自体が無い) |

**この2系統(CKAN系 / ArcGIS Hubタグ検索系)は、公開されているデータの種類が
異なる可能性が高い(§3参照)。パイプラインの対象範囲を決める前に、系統ごとに
個別の投入判定が必要。**

ArcGIS Hubタグ検索系の28件はすべて事業名に「令和5年」または「R05」を含み、
「土砂・洪水氾濫対策航空レーザ測量」系の事業に限られている(2023年度に実施された
一連の災害対策測量とみられる)。

## 3. 重要な発見: 「ORIGINAL LAZ」の有無は案件ごとに異なり、自動判定が必要

起動プロンプトは「ORIGINAL LAZ ZIPパッケージ」を発見対象として明確に定義しているが、
実際に確認したところ、**この存在は保証されておらず、案件ごとに個別確認が必要**
であることが分かった。

### 3.1 CKAN系(43件)でも一律ではない

3件をサンプル調査した結果:

| CKANパッケージ | 組織 | ORIGINAL LAZ ZIP | 提供されているもの |
|---|---|---|---|
| `h25oribegawasabou` | 総合政策部 | **あり**(`original.zip`、ORIGINAL/ディレクトリ、510MB) | オリジナルデータ+派生データ一式 |
| `r01biseikawasabou` | 総合政策部 | **なし** | 2mCSV/2mDTM/2mDEMラスタ/地表面データ/航空写真/水域シェープのみ |
| `hokkaido-h30atumachiku` | 水産林務部 | **なし**。しかもこのデータセットは1mメッシュのみで、0.5mメッシュは別ポータル(`harp.lg.jp`、北海道庁の別サイト)からDVD配布と明記 | 1mCSV/1mDTM(0.5m相当)/1mDEMラスタ/水域シェープ/航空写真 |

→ 「原本(LAZ)を含むかどうか」は、CKANの`resources[]`配列を実際に読んで、
`format=ZIP`かつ名称・ファイル名が「オリジナルデータ」/`original.zip`相当のものが
存在するかを都度判定するしかない。**存在しない案件は、パイプラインの対象から
除外し、その旨を記録する(黙って無視しない)**——これはsource_member/logical_asset
の生成ロジックに直接影響する設計上の要件になる。

### 3.2 ArcGIS Hubタグ検索系(28件)は、LAZどころか点群自体が見当たらない

サンプル1件(`R05帯広洪水対策その４`、7アイテム)を確認した結果、公開されている
アイテム種別は次の7つのみだった:

```
エリアGeojson (Feature Service)
航空写真Jpeg (Image Collection)
1mDTM (CSV Collection)
標高DEMラスタ (Image Collection)
地表面(グランド)データ (CSV Collection)
1mCSV_ZIP (CSV Collection)
水域_シェープファイル (Shapefile)
```

点群(LAZ/COPC相当)を示唆するアイテムは1件も無かった。この系統(28件)は、
**現時点では「ORIGINAL LAZ」の存在が未確認**であり、パイプラインの一次対象からは
除外し、別途調査が必要な保留グループとして扱う——存在しないと断定するのではなく、
「今回のサンプルでは見つからなかった」という限定された事実として記録する。

### 3.3 ライセンスは3件中3件ともCC-BY(暫定的に一貫、ただし帰属先組織は案件ごとに異なる)

サンプルした3件のCKANパッケージはいずれも`license_id: "CC-BY"`だったが、
`organization`(北海道庁の担当部局)は「総合政策部」「水産林務部」など**案件ごとに
異なる**。これはCC-BYの「表示すべき相手」が案件単位で変わりうることを意味し、
attributionレコードは`logical_asset`単位(あるいは`source_item`単位)で個別に
保持する必要がある——「北海道庁」という一括表記に単純化してはならない。

ArcGIS側の`licenseInfo`フィールドも、確認した1件では
「クリエイティブ・コモンズ表示 CC-BY」と一致していた。

**43件全体・28件全体にわたる網羅的なライセンス確認はまだ行っていない。
パイプラインが実際に個々のlogical_assetを`published_asset`へ昇格させる前に、
その案件固有のCKAN package(またはArcGIS Item)のライセンス・組織情報を
毎回取得し、キャッシュ済みの一般論に頼らないこと。**

## 4. 5000図郭メッシュグリッド(11系/12系/13系)の位置づけ(未解決、優先度低)

`URL`フィールド(例: `https://opendata-rakuno-gis.hub.arcgis.com/search?q=11TB09`)は、
Hub UIの検索ページへのリンクであり、機械的なREST APIでの直接解決方法は
確立できなかった。

- Hubの新しい検索API(`<hub>/api/search/v1?q=...`)は、単純な`q`パラメータでは
  Hubサイト自身の自己記述文書を返すのみで、絞り込まれたアイテム一覧を返さなかった
- 図郭番号をそのままクラシックな`sharing/rest/search?q=<図郭番号>&orgid=...`に
  投げると`total: 0`

一方、`tags:"<タグ>"`形式のクラシック検索(`sharing/rest/search?q=tags:"..."`)は
正しく機能することを確認した(§3.2の調査で使用)。これは72件のGeoJSON側の
`HP`フィールドが既にタグ文字列を含んでいる場合(ArcGIS Hub系の28件)にのみ有効で、
図郭番号からの逆引きには使えない。

**この図郭グリッドは、5000分の1地形図の図郭単位でエリアを人間が目視で探すための
補助レイヤと考えられ、パイプラインの主要な発見経路(§1・§2)には必須ではない。**
11系だけで1,533件の図郭ポリゴンがあり、12系・13系の件数は未確認。優先度は低いと
判断し、これ以上の解決は保留する。

## 5. 総括: パイプラインの一次スコープ

以上より、Phase 1(実データ投入)の一次対象は次のように限定する:

1. 72件の「オープンデータ範囲」featureのうち、`HP`がgeospatial.jp CKANを
   指す43件を`source_item`候補とする
2. 各`source_item`について、CKAN `package_show`を実際に取得し、
   `resources[]`の中に「オリジナルデータ」相当のZIPが実在するかを個別判定する
   (`source_package`として記録するのは、この判定を通過したものだけ)
3. ArcGIS Hubタグ検索系の28件、および`HP`が空の1件は、現時点では
   `provenance_link`はあるが`source_package`が見つからない状態として記録し、
   将来の追加調査対象として保留する(自動削除・黙殺はしない)
4. 全43件・全72件を横断した網羅的なライセンス・組織確認は未実施。
   `published_asset`への昇格は、各logical_assetごとに個別確認したライセンス・
   帰属情報がある場合に限る

## 6. 外部システムへのアクセス実績(本調査で実施した分)

REST APIのみを使用(スクレイピングなし)。すべて低頻度・単発の確認リクエスト。

- ArcGIS `sharing/rest`: item metadata、Web Map JSON、search(tags)——合計10回未満
- ArcGIS FeatureServer: スキーマ取得1回、サンプルレコード取得1回、件数取得1回(11系のみ)
- geospatial.jp CKAN `package_show`: 3回(サンプルパッケージ)
- `original.zip`の実体: **フルダウンロードはしていない**。HEAD 1回(302確認)+
  レンジGET(`Range: bytes=0-1023`)1回のみ。ダウンロードした実バイト数は1024バイト
- stars.optgeo.org: `bvmap-dark`スタイルJSON1回、`mapterhorn-japan-bridge`
  TileJSON1回

User-Agentの明示的な設定はこの調査フェーズではまだ実装していない
(§source-system-etiquette.md参照、Phase 1実装時に対応する)。
