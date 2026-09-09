# Basemap / Terrain

## bvmap-dark(確認済み)

- URL: `https://stars.optgeo.org/style/bvmap-dark`
- 2026-09-09に本プロジェクトで直接fetchして確認(HTTP 200、150936 bytes)
- style名: "GSI optimized vector tile basemap (bvmap), background/roads/labels only,
  no terrain/hillshade"
- source: `bvmap` → `https://stars.optgeo.org/bvmap`
- attribution: 「国土地理院最適化ベクトルタイル」
- `nuye`プロジェクト(`dwg7/nuye`)で同一URLを既に実運用しており、CORS・実表示とも
  問題ないことは別プロジェクトで確認済み。本プロジェクトでも同じ前提で使う

## mapterhorn-japan-bridge(暫定、確認済み)

- TileJSON URL: `https://stars.optgeo.org/mapterhorn-japan-bridge`
- 2026-09-09に本プロジェクトで直接fetchして確認(HTTP 200)
- tiles: `https://stars.optgeo.org/mapterhorn-japan-bridge/{z}/{x}/{y}`
- attribution(TileJSON内に埋め込み済み):
  「国土地理院 (GSI Japan). Processed with Mapterhorn (japan-bridge, interim).」
  → **ソース自身が"interim"と明記している。** 起動プロンプトの要求通り、この
  ソースは恒久的なものと見なさず、設定ファイル1箇所で本家Mapterhornへ差し替え
  可能な形にする(下記「差し替え設計」参照)
- minzoom/maxzoom: 0/16、bounds: 全球(-180,-85.05,180,85.05) ——ただし実際に
  データがあるのは日本周辺のみと推測される(bounds自体は全球のデフォルト値の
  可能性が高く、実際のデータ範囲は個別のズーム・タイルで確認が必要。未確認)
- `dwg7/nuye`で2026-09-08に404障害を実際に経験し、同日中に復旧を確認済み
  (アップロード中の一時的な状態だった)——**恒久稼働を保証するホストではない**
  という認識を裏付ける実例

## 本家(upstream) Mapterhorn(Web検索で確認、未実地検証)

- プロジェクト公式サイト: https://mapterhorn.com/ 、データアクセス:
  https://mapterhorn.com/data-access/
- 2026年4月時点の更新情報で、日本全国が1m/5m/10m解像度でカバレッジに追加された
  ことをWeb検索で確認([oliverwipfli.ch 2026-04-14の更新記事]
  (https://oliverwipfli.ch/mapterhorn-update-2026-04-14/)、
  [Mapterhornプロジェクト公式](https://mapterhorn.com/)による)
- **未確認**: 本家が配布する実際のPMTiles/タイルURL、北海道の実カバレッジ範囲、
  ライセンス条件、レート制限。これらはPhase 1で実際に差し替えを検討する際に
  個別に確認する。現時点では「差し替え候補が存在する」という事実の確認に留める

## 差し替え設計(方針、実装はPhase 1)

地形ソースのURL・attributionは、コード中にハードコードせず、
`config/terrain-source.json`のような設定ファイル1箇所に集約する
(例: `{"tiles_url": "...", "attribution": "...", "label": "japan-bridge (interim)"}`)。
本家へ切り替える際はこのファイルの値を差し替えるだけで済むようにし、
Webアプリ側のコードは変更しない。
