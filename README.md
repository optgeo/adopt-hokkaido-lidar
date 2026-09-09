# adopt-hokkaido-lidar

北海道の航空レーザ測量オープンデータ(ORIGINAL LAZ)を発見し、1ファイルずつ
COPC(Cloud Optimized Point Cloud)へ変換し、来歴(provenance)・ライセンス・
帰属表示が確認できたものだけをSource Cooperativeへ公開するパイプライン。

**現状: Phase 0(調査)完了、Phase 1(実データ投入)着手前。まだ1件も
COPC変換・公開はしていない。**

## これは何をするものか

1. ArcGIS Hub(北海道オープンデータ5000図郭)とgeospatial.jp(G空間情報センター、
   CKAN)を発見経路として、「ORIGINAL LAZ」ZIPパッケージを見つける
2. ZIPの中のLAZファイルを1つずつ(絶対にマージせず)PDALでCOPCへ変換する
3. 変換結果を検証し、来歴・ライセンス・帰属表示が揃っているものだけを
   Source Cooperativeの`smartmaps/adopt-hokkaido-lidar`へ公開する
   (揃っていないものは自動削除せず、人間のレビュー待ちとして保持する)
4. 公開済みCOPCのフットプリント(位置情報のみ、他の属性は持たない)を
   PMTiles化し、GitHub Pages上のMapLibre地図で閲覧できるようにする
   (クリックで初めてEptium等の外部ビューアを開く、自動読込はしない)

## なぜ「1ファイル=1変換、絶対にマージしない」のか

来歴を個々の原本ファイルまで追跡可能にするため。マージすると、どの成果物が
どの元ファイル・どのライセンス条件に由来するかが曖昧になる。

## 現在わかっていること・わかっていないこと

一次調査の詳細と根拠は`docs-src/discovery-report.md`を参照。特に重要な発見:

- 「ORIGINAL LAZ」が実際に含まれるかどうかは案件ごとに異なり、**保証されない**
  (自動判定が必須)
- 北海道庁側の帰属表示(部局名・ライセンス)も案件ごとに異なる
- `mapterhorn-japan-bridge`は自称"interim"の地形ソースであり、本家Mapterhornへの
  差し替えが前提

## 開発

```bash
just setup   # uv sync --extra dev
just test    # pytest
```

`justfile`はロジックを持たない薄いラッパー。CLIは`just`なしでも
`uv run python -m adopt_hokkaido_lidar <verb>`で直接実行できる。

`just clean`はdry-runのみ(何も削除しない)。`just clean-apply`は
ビルドキャッシュ等の使い捨てファイルのみ削除し、SQLite状態・マニフェスト・
チェックサム・来歴レコード・検証レポート・公開カタログは絶対に削除しない
(`docs-src/provenance-policy.md`参照)。

## Where to look

- 調査結果 → [docs-src/discovery-report.md](docs-src/discovery-report.md)
- 実装計画 → [PLAN.md](PLAN.md)
- 帰属表示の方針 → [docs-src/attribution.md](docs-src/attribution.md)
- 公開可否の判定基準 → [docs-src/provenance-policy.md](docs-src/provenance-policy.md)
- 背景地図・地形ソース → [docs-src/basemap.md](docs-src/basemap.md)
- 外部システムへの配慮 → [docs-src/source-system-etiquette.md](docs-src/source-system-etiquette.md)

## License

コード・文書は[CC0 1.0](LICENSE)。原本LiDARデータ・変換済みCOPC・背景地図・
地形データは、それぞれの提供元のライセンス・出典表示に従う
(`docs-src/attribution.md`参照)。
