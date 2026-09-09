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
| `h25oribegawasabou` | 総合政策部 | **原本はある(510MB)が、中身はLAZではない**(§3.1a参照) | 図郭単位のXYZ点群CSV一式 |
| `r01biseikawasabou` | 総合政策部 | **なし** | 2mCSV/2mDTM/2mDEMラスタ/地表面データ/航空写真/水域シェープのみ |
| `hokkaido-h30atumachiku` | 水産林務部 | **なし**。しかもこのデータセットは1mメッシュのみで、0.5mメッシュは別ポータル(`harp.lg.jp`、北海道庁の別サイト)からDVD配布と明記 | 1mCSV/1mDTM(0.5m相当)/1mDEMラスタ/水域シェープ/航空写真 |

→ 「原本を含むかどうか」は、CKANの`resources[]`配列を実際に読んで、
`format=ZIP`かつ名称・ファイル名が「オリジナルデータ」/`original.zip`相当のものが
存在するかを都度判定するしかない。**存在しない案件は、パイプラインの対象から
除外し、その旨を記録する(黙って無視しない)**——これはsource_member/logical_asset
の生成ロジックに直接影響する設計上の要件になる。

#### 3.1a 訂正: h25oribegawasabouの「オリジナルデータ」はLAZではなくXYZ点群CSVだった

Phase 0の初期調査では、`original.zip`の先頭1KBだけをレンジGETで確認し、
`ORIGINAL/`というディレクトリ名が見えたことから「ORIGINAL LAZを含む」と
誤って報告していた。その後、ZIPの中央ディレクトリ(末尾のレンジGETのみで
取得可能、フルダウンロード不要)を実際に全件パースしたところ、**31エントリ
すべてが`.laz`ではなく`_org.txt`という拡張子**であることが分かった。

さらに1エントリの内容を実際にデコードして確認したところ、次のような
プレーンテキストのXYZ点群CSVだった(平面直角座標系13系/EPSG2455の座標値と
一致):

```
1,-68413.45,-100500.66,89.41,1
2,-68412.95,-100500.57,89.35,1
...
```

(列は推定: 通し番号, X, Y, Z, 分類コード)

**教訓: CKANのリソース名(「オリジナルデータ」)やファイル名(`original.zip`)
だけでは、中身が本当にLAZ/LASかどうか判定できない。** ZIPの中央ディレクトリを
実際に開いて拡張子を見るまで断定してはならない——これを受けて
`src/adopt_hokkaido_lidar/zip_inspect.py`を実装し、「候補の検出(ckan.py、
リソース名ベース)」と「実際の中身の確認(zip_inspect.py、中央ディレクトリ
パース+拡張子分類)」を明確に2段階に分けた。

XYZ点群CSVも、PDALの`readers.text`ステージで読み込みCOPCへ変換すること自体は
可能——「LAZではない」からといって即座に対象外にする必要は無いが、
`derived_asset_version.source_format`にどちらの形式から変換したかを必ず
記録する設計にした(§スキーマ変更参照)。

### 3.2 ArcGIS Hub系(28件)を全27件+1件で個別検証: 大半は確認済みで対象外、1件だけ大量のORIGINAL LAZがある

初期調査ではサンプル1件(`R05帯広洪水対策その４`)のみで「LAZが見当たらない」と
した。その後、28件のうち27件について、各featureのHPリンクに埋め込まれた
正確なタグ文字列を使い、`orgid:vtIFKqGmW1wohBxY AND tags:"<タグ>" AND
tags:"LAZ" AND tags:"ORIGINAL"`で個別に直接検索した。

**結果: 27件中26件が完全にゼロヒット。** 公開されているのは
エリアGeojson・航空写真Jpeg・DTM/DEM・地表面データ・水域シェープのみで、
いずれも令和5年度(R05)の「土砂・洪水氾濫対策航空レーザ測量」系の案件だった。
これは1件のサンプルによる推測ではなく、ほぼ全数(27/28)の直接検証による、
確度の高い結論として記録する。**この26件はORIGINAL LAZが存在しないことを
確認済みとして、パイプラインの対象から明確に除外する**(「未解決」ではなく
「確認済みで対象外」)。

**唯一の例外: 「Jクレジット」案件(道有林課、森林分野のカーボンクレジット測量、
タグ`上川北部・網走西部Jクレ`)だけは、273件もの図郭単位ORIGINAL LAZが
ArcGISに存在する。** 他の27件が治水部局(建設管理部)の案件であるのに対し、
これだけ所管(道有林課=森林分野)も性質も異なる案件だった、という違いが
公開状況の差につながっている可能性がある(断定はしない)。

さらに、ArcGIS全体を`orgid:vtIFKqGmW1wohBxY AND tags:"LAZ" AND
tags:"ORIGINAL"`で横断検索すると、**41プロジェクト・1,304件**の
図郭単位ORIGINAL LAZアイテムが見つかった。うち少なくとも1件
(`13nc02_ORIGINAL_LAZ【2013居辺川砂防】`)は、CKAN系の`h25oribegawasabou`
(§3.1a訂正参照)と同一案件に対応することを確認——**同じ案件のデータが
CKANとArcGISの両方に(異なる形式で)存在することがある**、という新しい事実。
1件、レンジGETで実際にダウンロード経路まで検証済み
(`ORIGINAL_LAZ/12HE811.laz`という本物のLAZエントリ、CC-BY、サイズ
1,614,040,761バイト)。

ただしArcGIS側アイテムの`accessInformation`(帰属情報を書く場所)は`null`
——部局名はここには無い。**部局名(帰属)は72件のGeoJSON自体の
`担当部署`/`計画機関名称`フィールドに全72件分揃っている**(例:
「道有林課」)ため、CKANを経由しなくても解決できることが分かった
(§3.3参照)。

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

## 5. 総括: パイプラインの一次スコープと処理優先順位

**Phase 1最初に処理する対象は「Jクレジット」案件(道有林課、273件の図郭単位
ORIGINAL LAZ、ArcGIS発見、CC-BY確認済み)と決定した。** 理由:
実際にダウンロード経路(レンジGET)・LAZフォーマット・ライセンスまで
確認済みの、最も準備が整った案件であるため。

その他の一次スコープ:

1. 72件の「オープンデータ範囲」featureのうち、`HP`がgeospatial.jp CKANを
   指す43件を`source_item`候補とする。ただし§3.1aの通り、CKAN側の
   「オリジナルデータ」は中身がLAZとは限らない(XYZ点群CSVの場合もある)ため、
   `zip_inspect.py`による中央ディレクトリの実地確認を経てから
   `source_package`として確定する
2. **ArcGIS Hubタグ検索系28件のうち26件(R05治水系)は、ORIGINAL LAZが
   存在しないことを確認済み。パイプライン対象から除外し、その理由
   (「27件中26件を直接検証、ゼロヒット」)とともに記録する**(未解決ではなく
   確認済みの除外)
3. Jクレジット案件(道有林課)は、ArcGIS `tags:"上川北部・網走西部Jクレ"
   AND tags:"LAZ" AND tags:"ORIGINAL"`を発見クエリとして採用する
4. `HP`が空の1件(2022-A-0068 上流川砂防工事)は個別要調査のまま(優先度低)
5. 全43件・全72件を横断した網羅的なライセンス・組織確認は未実施。
   `published_asset`への昇格は、各logical_assetごとに個別確認したライセンス・
   帰属情報がある場合に限る

### スキーマ変更(2026-09-09、承認済み)

上記の発見(CKAN/ArcGISの2つの発見系統・LAZでないケースの存在)を受けて、
`src/adopt_hokkaido_lidar/db.py`を改訂した:

- `source_item`/`source_package`に`source_system`(`ckan`|`arcgis`)を追加
  ——2つの発見系統のIDを混在させない
- `source_item`に`responsible_department`(担当部署)を追加
  ——CKANを経由しない帰属表示の主経路として使う(§3.2後半参照)
- `laz_member_path`を`raw_member_path`に改名——中身がLAZとは限らないため
- `source_member.raw_format`/`derived_asset_version.source_format`
  (`las`|`text_csv`)を追加——PDALの`readers.las`/`readers.text`どちらを
  使ったかを記録する
- `identifiers.stable_asset_id()`は`(source_system, source_package_id,
  raw_member_path)`の3引数を取るよう変更(CKAN package名とArcGIS item id
  は無関係なID空間のため、混同を防ぐ)

### Source Cooperativeディレクトリ構造(実例で確定、PLAN.md参照)

`source_system`を第一階層に置く形に確定した。実例:

```
smartmaps/adopt-hokkaido-lidar/data/
  arcgis/fccdb80933434b3ab45bb7b725207e6b/12he811/v1/12he811.copc.laz   (確認済み実例、Jクレ案件)
  ckan/h25oribegawasabou/13nc012/v1/13nc012.copc.laz                    (元がXYZ点群CSVの実例)
```

## 6. 外部システムへのアクセス実績(本調査で実施した分)

REST APIのみを使用(スクレイピングなし)。すべて低頻度・単発の確認リクエスト。

- ArcGIS `sharing/rest`: item metadata、Web Map JSON、search(tags、orgid横断含む)——数十回程度、いずれも軽量なJSON応答のみ
- ArcGIS FeatureServer: スキーマ取得1回、サンプルレコード取得1回、件数取得1回(11系のみ)
- geospatial.jp CKAN `package_show`: 3回(サンプルパッケージ)
- ZIPの実体確認: **フルダウンロードは一度もしていない**。すべてHEAD/レンジGETのみ
  - `original.zip`(h25oribegawasabou、510MB): 先頭1KB + 中央ディレクトリ領域(末尾256KB)
    + 1エントリの内容確認用に約2KB、の3回のレンジGET
  - ArcGIS `12HE88_ORIGINAL_LAZ...zip`(1.6GB、Jクレ案件): HEAD 1回 + 先頭256バイトの
    レンジGET 1回
  - 実際にダウンロードした合計バイト数: 1MB未満
- Source Cooperative: 読み取り確認(ls)数回 + 書き込みテスト1回(78バイトの
  テストオブジェクトをPUT→確認→DELETE、hfuさんの許可を得て実施、現在は残っていない)
- stars.optgeo.org: `bvmap-dark`スタイルJSON1回、`mapterhorn-japan-bridge`
  TileJSON1回

User-Agentの明示的な設定はこの調査フェーズではまだ実装していない
(§source-system-etiquette.md参照、Phase 1実装時に対応する)。

## 7. 再入可能性(reentrancy)についての現状

2026-09-09、hfuさんから設計思想の確認があった。現状の正確な立ち位置:

- **土台は再入可能・冪等な設計を意図している**: `identifiers.stable_asset_id()`
  は決定的(同じ入力→同じID)、`db.connect()`はスキーマ初期化が冪等
  (`CREATE TABLE IF NOT EXISTS`)、`published_asset.object_url`はUNIQUE制約+
  上書き禁止方針、`derived_asset_version`はバージョン追記型
- **しかし実行可能なコードとしての再入可能性はまだ無い**: 実際に
  「ダウンロード→変換→検証→アップロード→ローカル削除」を行う`ingest`/
  `publish`コマンド自体が未実装(現状`init-db`のみ)。中断後の再実行時に
  「どこまで済んでいるかを見て続きから再開する」判定ロジックは、これから
  実装するPhase 1の課題として残っている
