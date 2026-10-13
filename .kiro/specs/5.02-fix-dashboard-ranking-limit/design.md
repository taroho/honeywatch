# Design Document

## Overview

本設計は spec \`5.02-fix-dashboard-ranking-limit\` の requirements.md（R1〜R2）を実現するための技術設計である。親フェーズ \`5-feat-dashboard-unified-period\`（および Top Source IP の取得元である \`4-feat-geoip-ip-location\`）で実装済みの Dashboard について、以下 2 つのランキング表示の**表示件数の上限を 20 件から 10 件に変更**する。

- **Top Source IPs**（\`TopIPsTable\`）: 送信元 IP ランキングの表示を上位 10 件までにする。
- **国別攻撃件数ランキング**（\`CountryRankingTable\`）: 国別ランキングの表示を上位 10 件までにする。

本修正は**フロントエンドの表示層のみ**の変更であり、バックエンド API・データ取得件数・集計ロジックには一切手を入れない。

### 何を変えるか（要点）

1. **Top Source IPs：テーブル表示のみ 10 件に絞る**
   - データ取得は現状どおり \`useGeoTopIPs(20, period)\` を維持する（\`DashboardPage.tsx\`、取得件数 20 は不変）。
   - \`TopIPsTable\` は受け取った配列を先頭 10 件にスライスして表示する。
   - この取得結果は攻撃元マップ（\`GeoMap\`）と共用しているが、**地図のマーカーは 20 件のまま維持**する（テーブル側のスライスのみで地図には影響させない）。

2. **国別攻撃件数ランキング：表示上限定数を 10 に変更**
   - \`CountryRankingTable.tsx\` の表示上限定数 \`MAX_COUNTRIES\` を \`20\` → \`10\` に変更する。
   - バックエンドの国別集計（最大 1000 件）や取得ロジックは不変。

### 最小差分・後方互換方針

- **バックエンド変更なし・API 変更なし・新規依存なし。** 変更はフロントエンドの表示層に限定する。
- **データ取得件数は不変**（Top IPs は 20 件取得のまま）。地図（\`GeoMap\`）のマーカー表示件数（20 件）に影響を与えない。
- 空データ時の表示（「No data available」「集計対象データがありません」）や、Loading 表示、既存のスタイル・レイアウトは不変。
- \`period\` 連動や自動ポーリング（30 秒間隔）などの既存挙動は不変。

---

## Architecture

変更は Dashboard のフロントエンド表示コンポーネント 2 つに限定される。データフロー（取得件数・集計）は不変で、最終的な**描画時のスライス上限のみ**が 20 → 10 に変わる。

\`\`\`
DashboardPage
  ├─ useGeoTopIPs(20, period) ─┬─→ TopIPsTable   … 受領 20 件を先頭 10 件にスライス表示（変更）
  │                            └─→ GeoMap        … 20 件のままマーカー表示（不変）
  └─ useCountrySummary(start,end) → CountryRankingTable … MAX_COUNTRIES 10 件で表示（変更）
\`\`\`

## Components and Interfaces

### 1. TopIPsTable（\`frontend/src/components/TopIPsTable.tsx\`）

- 表示上限を表す定数（例: \`MAX_TOP_IPS = 10\`）を追加する。
- \`data\` をそのまま \`map\` するのではなく、\`data.slice(0, MAX_TOP_IPS)\` の結果を描画する。
- 空判定（\`No data available\`）はスライス後の配列に対して行う（元データが空なら従来どおり空表示）。
- Props インターフェース（\`TopIPsTableProps\`）は不変。\`DashboardPage\` からの呼び出しも不変。

### 2. CountryRankingTable（\`frontend/src/components/CountryRankingTable.tsx\`）

- 既存の表示上限定数 \`MAX_COUNTRIES\` を \`20\` → \`10\` に変更する。
- 併せて、上限に言及する docstring/コメント（「上位最大 20 か国」等）を 10 件に更新する。
- スライス処理 \`data.slice(0, MAX_COUNTRIES)\` 自体のロジックは不変。

### 3. DashboardPage（\`frontend/src/pages/DashboardPage.tsx\`）

- **変更しない。** \`useGeoTopIPs(20, period)\` の取得件数 20 は据え置き、\`GeoMap\` へ渡す \`entries\`（20 件）も不変。

## Testing Strategy

- 既存のフロントエンドテスト（もしあれば）が壊れないことを確認する。
- 手動確認: Dashboard を表示し、Top Source IPs テーブルが最大 10 行、国別ランキングが最大 10 行になっていること、攻撃元マップのマーカーは従来どおり（最大 20）であることを目視で確認する。
- データが 10 件未満の場合は全件表示されること、0 件の場合は空表示になることを確認する。