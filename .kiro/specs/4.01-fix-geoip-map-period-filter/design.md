# Design Document

## Overview

本設計は、修正 spec `4.01-fix-geoip-map-period-filter` の requirements.md を実現するための技術設計である。親フェーズ `4-feat-geoip-ip-location` で実装済みの Geo_Map（攻撃元マップ）に対して、以下の 3 点を **最小差分** で拡張する。

### 何を変えるか

1. **Geo_Map への期間切り替えタブの追加**（Requirement 1）
   Dashboard の Geo_Map 上部に期間タブ（`24h` / `7d` / `1y` / `all`、初期選択 `24h`）を追加する。UI は親 spec で実装済みの Detection Analysis の期間セレクタ（`PERIOD_OPTIONS` によるボタン group、選択中は `bg-hw-accent`）と同一のタブ切り替え方式に揃える。

2. **表示件数の上限を 20 件へ引き上げ**（Requirement 2）
   Geo_Map へ供給する Top IP を、現状の `limit=10` から `limit=20` に変更する。緯度経度を持つ IP のみをマーカー表示する挙動（親要件 4.8）は維持する。

3. **`/geo/top-ips`（Top_IPs_Endpoint）の period 拡張**（Requirement 3・4）
   period パラメータに `1y`（直近365日）と `all`（全期間＝下限なし）を追加する。`24h` / `7d`（および既存の `1h` / `6h`）は現状の集計対象期間を維持する。不正な period は拒否する。

### 最小変更方針

- **DB スキーマ変更なし・新規 npm 依存なし。** 地理情報は親 spec と同じく非永続（リクエスト都度 GeoIP_Resolver で解決）のまま。
- バックエンドは `geo.py`（ルート）と `attack.py`（リポジトリ）のみに閉じた変更とする。`all` に対応するための `get_top_ips` の since 任意化は、既に全期間対応済みの `get_ip_counts(since: datetime | None, until: datetime | None)` と **同一パターン**に揃える。
- フロントは `DashboardPage.tsx` に「Geo_Map 用の period state」と「タブ UI」を追加し、`useGeoTopIPs(20, mapPeriod)` を渡すだけに留める。`useGeoTopIPs` / `fetchGeoTopIPs` / `GeoMap` は変更不要（後述の検証で確認）。

### 後方互換方針

- `/geo/top-ips` の既定値は変更しない（period 既定 `24h`、limit 既定 `10`、範囲 `1`〜`100`）。
- `24h` / `7d`（および `1h` / `6h`）の集計対象期間は親 spec と同一。
- 国別ランキング（Country_Summary）および Top IP テーブル向けエンドポイントの仕様は本修正で変更しない（Requirement 4.4）。
- `get_top_ips` の since 任意化は、既存呼び出し（本エンドポイントは常に非 None の since を渡す）に対して挙動を変えないため後方互換である。

---

## Architecture

### レイヤー構成（変更範囲）

本修正は親 spec のレイヤー構成（Honeypot → Collector → Detection → Database → API → Dashboard）のうち、**Database 層（リポジトリ）・API 層・Dashboard 層**にのみ手を入れる。Honeypot / Collector / Detection には影響しない。

```
Dashboard (React)
  DashboardPage  ── mapPeriod state（"24h" 初期） / Period_Tab（24h/7d/1y/all）
       │  useGeoTopIPs(20, mapPeriod)
       ▼
  api/client.ts  ── fetchGeoTopIPs(20, mapPeriod)  →  GET /api/v1/geo/top-ips?limit=20&period=<mapPeriod>
       ▼
API_Server (FastAPI)
  routes/geo.py  ── get_geo_top_ips(limit, period)
       │  period 検証（pattern: ^(1h|6h|24h|7d|1y|all)$）
       │  period=="all" → since=None
       │  それ以外       → since = now - _PERIOD_MAP[period]（1y = 365日）
       ▼
Database 層
  repositories/attack.py ── get_top_ips(since: datetime | None, until, limit)
       │  since is None → 下限フィルタなし（全期間）
       ▼
  Geo 付与： resolver.resolve(source_ip) → _geo_to_dict()
       ▼
  { "ips": [ { source_ip, event_count, first_seen, last_seen, geo } ... ] }
       ▼
GeoMap ── 緯度経度を持つエントリのみ Map_Marker として描画（変更不要）
```

### データフロー（期間選択時）

1. 利用者が Period_Tab で期間を選択 → `DashboardPage` の `mapPeriod` state が更新される。
2. `useGeoTopIPs(20, mapPeriod)` の依存配列 `[limit, period]` が変化し、`fetchGeoTopIPs(20, mapPeriod)` を再実行する。
3. `GET /geo/top-ips?limit=20&period=<mapPeriod>` が呼ばれる。
4. `get_geo_top_ips` が period を検証し、`since` を決定する。
   - `all` の場合：`since = None`（下限なし）。
   - それ以外：`since = now - _PERIOD_MAP[period]`（`1y` は `timedelta(days=365)`）。
5. `AttackEventRepository.get_top_ips(since=since, until=now, limit=20)` を呼ぶ。
   - `since is None` のときは `timestamp >= since` の絞り込みを付けず全期間を対象とする。
6. 各エントリに `_geo_to_dict(resolver.resolve(source_ip))` で geo を付与して返す。
7. `GeoMap` が受け取った entries から緯度経度を持つものだけをマーカー描画する。

### all のときの since=None フロー（設計判断）

`all`（全期間）を表現する方法として 2 案を比較した。

- **案 A（採用）: `get_top_ips` の since を `datetime | None` にし、None のとき下限フィルタを付けない。**
- 案 B: geo.py 側で「十分過去の since」（例：`datetime.min`）を渡す。

**案 A を採用する理由：**

1. **既存パターンとの一貫性。** `get_ip_counts(since: datetime | None, until: datetime | None)` が既に None 許容で全期間に対応している。同一の書き方に揃えることで、リポジトリの期間フィルタの扱いが統一され、可読性・保守性が高い。
2. **正確性。** 案 B の「十分過去」は恣意的で、タイムゾーンや将来のデータ範囲によっては意味が曖昧になる。「下限フィルタを付けない」は「全期間」の意味を過不足なく表現する。
3. **`all` は `timedelta` で表現できない。** `_PERIOD_MAP` は `str → timedelta` のマップであり、`all`（下限なし）は timedelta では表せない。したがって `all` は `_PERIOD_MAP` に入れず、`since=None` の分岐で扱うのが素直である。

---

## Components and Interfaces

### Backend: `src/honeywatch/api/routes/geo.py`

#### `_PERIOD_MAP` の拡張

`1y`（直近365日）を追加する。`all` は timedelta で表現できないため **追加しない**（`since=None` 分岐で扱う）。

```python
_PERIOD_MAP: dict[str, timedelta] = {
    "1h": timedelta(hours=1),
    "6h": timedelta(hours=6),
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "1y": timedelta(days=365),  # 追加: 直近365日（Requirement 3.1）
}
```

#### `get_geo_top_ips` の period バリデーション拡張と since 分岐

period の受理パターンを `^(1h|6h|24h|7d)$` から `^(1h|6h|24h|7d|1y|all)$` に拡張する。`all` のときは `since=None`、それ以外は `since = now - _PERIOD_MAP[period]` を渡す。既定値（period=`24h`、limit=`10`、range `1-100`）は変更しない。

```python
@router.get("/top-ips")
async def get_geo_top_ips(
    _user: AuthUser,
    db: DbSession,
    resolver: GeoIPResolverDep,
    limit: int = Query(default=10, ge=1, le=100),
    period: str = Query(default="24h", pattern="^(1h|6h|24h|7d|1y|all)$"),
) -> dict[str, object]:
    now = datetime.now(UTC)
    # all は下限なし（全期間）。それ以外は now から遡って since を算出する。
    since = None if period == "all" else now - _PERIOD_MAP[period]

    repo = AttackEventRepository(db)
    ips = await repo.get_top_ips(since=since, until=now, limit=limit)
    # 以降の geo 付与ロジックは既存のまま（変更なし）
    ...
```

`since` の型が `datetime | None` になるため、`get_top_ips` の引数型もこれに合わせる（下記）。それ以外の geo 付与ロジック（`resolver.resolve` → `_geo_to_dict`、`first_seen`/`last_seen` の isoformat 変換）は変更しない。

### Database 層: `src/honeywatch/db/repositories/attack.py`

#### `get_top_ips` の since を None 許容化

`since` を `datetime | None` にし、`None` のとき `timestamp >= since` の下限フィルタを付けない。`until` は現状どおり必須のまま（本エンドポイントは常に `now` を渡す）で変更しない。`get_ip_counts` の実装パターンに揃える。

```python
async def get_top_ips(
    self,
    since: datetime | None,
    until: datetime,
    limit: int = 10,
) -> list[dict[str, object]]:
    query = (
        select(
            AttackEventModel.source_ip,
            func.count(AttackEventModel.id).label("event_count"),
            func.min(AttackEventModel.timestamp).label("first_seen"),
            func.max(AttackEventModel.timestamp).label("last_seen"),
        )
        .where(AttackEventModel.timestamp <= until)
    )
    # since が None の場合は下限フィルタを付けない（全期間 = period "all"）
    if since is not None:
        query = query.where(AttackEventModel.timestamp >= since)

    query = (
        query.group_by(AttackEventModel.source_ip)
        .order_by(func.count(AttackEventModel.id).desc())
        .limit(limit)
    )
    result = await self._session.execute(query)
    rows = result.all()
    return [
        {
            "source_ip": row.source_ip,
            "event_count": row.event_count,
            "first_seen": row.first_seen,
            "last_seen": row.last_seen,
        }
        for row in rows
    ]
```

**後方互換：** `get_top_ips` の呼び出し元は現状 2 か所ある。

- `routes/geo.py` の `get_geo_top_ips`（本エンドポイント）
- `routes/dashboard.py` の `/dashboard/top-ips`（**Top IP テーブル向けエンドポイント**）

両者とも `since=now - _PERIOD_MAP[period]` の **非 None** の `since` を渡す。`since` を `datetime | None` に緩めても、`since` が指定されている限り下限フィルタは従来どおり適用されるため、両呼び出し元の挙動は不変である。特に `/dashboard/top-ips` は Requirement 4.4（Top IP テーブル向けエンドポイントの集計仕様を変更しない）の対象であり、`dashboard.py` のコードは本修正で変更しない。`since` の型を緩めるだけでは既存の集計結果に影響しないことが後方互換の根拠となる。

### Frontend: `frontend/src/pages/DashboardPage.tsx`

#### Geo_Map 用の period state とタブ UI を追加

Detection Analysis の期間セレクタとは独立した Geo_Map 専用の state を追加する（両者の期間は独立に切り替えられる）。初期値は `24h`（Requirement 1.2）。

```tsx
// Geo_Map の期間タブ選択肢（Requirement 1.1）
const MAP_PERIOD_OPTIONS = ["24h", "7d", "1y", "all"] as const;

// コンポーネント内
const [mapPeriod, setMapPeriod] = useState<string>("24h"); // 初期 24h（Requirement 1.2）

// Top IPs（geo 付き）を Geo_Map 用に limit=20・選択期間で取得（Requirement 2.1）
const { data: topIPs, loading: topIPsLoading } = useGeoTopIPs(20, mapPeriod);
```

Geo_Map の表示ブロックに、Detection Analysis と同じスタイルのタブ group を付与する（選択中は `bg-hw-accent`、Requirement 1.4/1.5）。

```tsx
{/* 攻撃元マップ（Geo_Map）: 期間タブ + マップ */}
<div className="mb-6">
  <div className="flex items-center justify-between mb-3">
    <h2 className="text-lg font-bold text-gray-100">攻撃元マップ</h2>
    <div className="flex gap-1">
      {MAP_PERIOD_OPTIONS.map((opt) => (
        <button
          key={opt}
          onClick={() => setMapPeriod(opt)}
          className={`px-3 py-1 rounded text-xs font-medium transition-colors ${
            mapPeriod === opt
              ? "bg-hw-accent text-white"
              : "bg-hw-card text-gray-400 hover:text-gray-200"
          }`}
        >
          {opt}
        </button>
      ))}
    </div>
  </div>
  <GeoMap enabled={true} entries={topIPs} />
</div>
```

> 備考：現状 `GeoMap` 内にも `<h2>攻撃元マップ</h2>` の見出しがある。タブ UI を Geo_Map の外側（DashboardPage）に置く場合、見出しの重複を避けるため、実装時に「タブ行のラベル」と「GeoMap 内の見出し」のどちらを残すかを整理する。本設計では上記のように DashboardPage 側にラベル付きタブ行を置き、GeoMap 内の見出しは残置（重複表示を避けたい場合はタブ行のラベルを省くだけで済む）とし、`GeoMap.tsx` 自体のロジックは変更しない方針とする。

#### `useGeoTopIPs` は変更不要

`useGeoTopIPs(limit=10, period="24h")` は既に `limit`・`period` を引数に取り、依存配列 `[limit, period]` で再取得する。呼び出し側で `useGeoTopIPs(20, mapPeriod)` と渡すだけでよく、hook 本体は変更しない（既定値も据え置き）。

#### `fetchGeoTopIPs` は変更不要（確認事項）

`fetchGeoTopIPs(limit, period)` は `period` を `URLSearchParams` にそのまま付与している。`1y` / `all` も文字列としてそのまま送出されるため、クライアント側の変更は不要。バックエンドの pattern 拡張で新 period が受理される。

#### `GeoMap.tsx` は変更不要

`GeoMap` は entries を受け取り、緯度経度を持つものだけをマーカー描画し、0 件時は「表示できる位置情報がありません」を表示する（Requirement 2.3/2.4/2.5 を既に満たす）。件数上限・期間はデータ供給側（DashboardPage / useGeoTopIPs / API）で制御するため、`GeoMap` 自体の変更は不要。

---

## Data Models

本修正は永続データモデル（`attack_events` テーブル）を変更しない。

### API の period パラメータ

- 型：文字列。受理値は `1h` / `6h` / `24h` / `7d` / `1y` / `all` の 6 種（Requirement 3.5）。
- 集計対象期間：
  - `1h`/`6h`/`24h`/`7d`：`now - timedelta`（親 spec と同一）。
  - `1y`：`now - timedelta(days=365)`（Requirement 3.1）。
  - `all`：下限なし（`since=None`、Requirement 3.2）。

### フロントの期間型

Geo_Map のタブ選択肢は 4 種（`24h` / `7d` / `1y` / `all`）。既存 `PERIOD_OPTIONS` と同様に `as const` タプル（`MAP_PERIOD_OPTIONS`）で定義する。`useGeoTopIPs` / `fetchGeoTopIPs` の `period` 引数は `string` のままで足りる（新たな共用体型の導入は最小変更方針により行わない）。API レスポンス型（`GeoTopIPsResponse` / `GeoTopIPEntry` / `GeoLocation`）は親 spec のものを変更なしで再利用する。

### `get_top_ips` の戻り値

戻り値の形（`source_ip` / `event_count` / `first_seen` / `last_seen` のリスト）は変更しない。変更するのは `since` の受理型（`datetime` → `datetime | None`）と下限フィルタの条件分岐のみ。

---

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system-essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

本修正は「純粋なロジック（period → since の算出、下限フィルタの有無）」と「集計結果の不変条件（件数上限・降順・geo 付与）」を含み、入力（period・limit・IP 集合）によって挙動が意味を持って変わるため、これらは PBT が適切である。一方、UI のタブ表示・地図描画は親 spec 同様に例示テスト／ビルド検証で扱う（下記 Testing Strategy 参照）。

以下のプロパティは、親 spec のプロパティ（geo 付与・降順・limit 上限・未解決 null・緯度経度なし除外）と重複しない、本修正で新たに導入する挙動に絞って定義する。

### Property 1: period=all は下限フィルタを付けない（全期間集計）

*For any* limit（1〜100）と任意の Attack_Event 集合について、`get_geo_top_ips` に `period="all"` を指定したとき、`AttackEventRepository.get_top_ips` は `since=None`（下限フィルタなし）で呼び出され、集計対象は当該 until 以前の全 Attack_Event となる。

**Validates: Requirements 3.2**

### Property 2: period=1y は直近365日を集計対象とする

*For any* 要求受信時刻 now について、`get_geo_top_ips` に `period="1y"` を指定したとき、`get_top_ips` に渡される `since` は `now - 365日` に等しく、`until` は `now` に等しい。

**Validates: Requirements 3.1**

### Property 3: 受理される全 period は正しい since を導く

*For any* 受理値 period（`1h`/`6h`/`24h`/`7d`/`1y`/`all`）について、`all` のときは `since=None`、それ以外のときは `since = now - _PERIOD_MAP[period]` が `get_top_ips` へ渡される（`24h`/`7d`/`1h`/`6h` は親 spec と同一の since を維持する）。

**Validates: Requirements 3.3, 4.3**

### Property 4: 不正 period はエラー応答（集計を行わない）

*For any* `1h`/`6h`/`24h`/`7d`/`1y`/`all` のいずれにも一致しない period 文字列について、`/geo/top-ips` はエラー応答（HTTP 422）を返し、正常な集計レスポンス（`ips`）を返さない。

**Validates: Requirements 3.5**

### Property 5: since を指定した get_top_ips は下限を含めて絞り込む（後方互換）

*For any* 非 None の `since` と `until`（`since <= until`）および任意の Attack_Event 集合について、`get_top_ips(since, until, limit)` の結果に含まれる各 IP の集計は `since <= timestamp <= until` の範囲の Attack_Event のみを対象とする（`since=None` 化が既存の非 None 呼び出しの挙動を変えないこと）。

**Validates: Requirements 4.3**

---

## Error Handling

- **不正な period（Requirement 3.5）：** period は `Query(pattern="^(1h|6h|24h|7d|1y|all)$")` で制約する。FastAPI はパターン不一致のクエリパラメータに対し **HTTP 422 Unprocessable Entity** を自動で返す。requirements.md は「period が不正である旨を示すエラー応答を返す」ことを求めており、422（バリデーションエラー詳細を含む）でこれを満たす。バリデーション段階で拒否されるため、DB 集計・geo 解決は実行されない。
  - 補足：親 spec の他エンドポイント（`/geo/ips/{ip}` の不正 IP、`/geo/country-summary` の不正日時）は明示的に 400 を投げているが、これらは「本文の値検証」であるのに対し、period は「Query パラメータの pattern 制約」であり、FastAPI 標準の 422 で扱う方が実装が単純かつ後方互換（既存 pattern も 422 を返していた）である。
- **limit の範囲外（Requirement 3.4/4.2）：** `Query(ge=1, le=100)` により範囲外は 422。既定 10・範囲 1〜100 を維持する。
- **geo 未解決（Requirement 3.6）：** 親 spec のフェイルセーフ設計を維持する。Resolver 利用不可・未解決でも 500 にせず、geo 各フィールドを null として返す（既存の `_geo_to_dict` / `resolver.resolve` の挙動をそのまま利用）。
- **緯度経度なしのエントリ（Requirement 2.4）：** フロント側で `GeoMap` が緯度経度 null のエントリをマーカーから除外する（既存挙動）。
- **マーカー 0 件（Requirement 2.5）：** `GeoMap` が「表示できる位置情報がありません」を表示する（既存挙動）。

---

## Testing Strategy

親 spec のテスト構成（`tests/test_api/test_geo.py`）に合わせる。DB 依存は `patch("honeywatch.api.routes.geo.AttackEventRepository")` でモックし、`get_top_ips` を `AsyncMock` に差し替える。Resolver も `MagicMock` の `resolve.side_effect` で構成する（既存 `_make_resolver` を踏襲）。

### Dual Testing Approach

- **Property tests（`hypothesis`、最小 100 iterations）：** 本修正の純粋ロジックと不変条件を網羅する。
- **Unit / example tests：** 具体的な period 値・エラー条件・境界を確認する。

各 property test には次のタグをコメントで付与する：
**Feature: 4.01-fix-geoip-map-period-filter, Property {番号}: {プロパティ本文}**

### Backend — property tests

Python 用 PBT ライブラリは **Hypothesis**（親 spec の test_geo.py で既に使用）を用い、新規実装はしない。各テストは最小 100 iterations（`@settings(max_examples=100, ...)`）で実行する。

- **Property 1（period=all → since=None）：** limit と行データを生成し、`period="all"` で `/geo/top-ips` を叩き、モックした `get_top_ips` が `since=None` で呼ばれたことを `call_args` で検証する。
- **Property 2（period=1y → since = now-365日）：** `period="1y"` で呼び、`get_top_ips` の `since`/`until` を検証する。now はエンドポイント内で取得するため、`since` と `until` の差が概ね 365 日（許容誤差数秒）であることを確認する（`datetime.now` の揺れを吸収）。
- **Property 3（受理 period → 正しい since）：** 受理値の集合から period を生成し、`all` のみ `since=None`、それ以外は `until - since ≈ _PERIOD_MAP[period]` を検証する。
- **Property 4（不正 period → 422）：** `1h/6h/24h/7d/1y/all` に一致しないランダム文字列を生成し、応答が 422 で `ips` を含まないことを検証する。
- **Property 5（since 指定時の範囲絞り込み・後方互換）：** これは `AttackEventRepository.get_top_ips` のリポジトリ単体テスト（DB を用いる統合寄りテスト、または in-memory/セッションモック）で扱う。既存の DB 依存テスト方針（モック中心）に合わせ、`since` を渡した場合に下限フィルタが SQL に含まれることを、生成した since/until の組で確認する。DB 実行が難しい環境では、クエリ構築分岐（`since is not None` の有無）を対象にした最小テストに留める。

### Backend — unit / example tests

- `period="all"` で 200・`ips` を返し、`get_top_ips` が `since=None` で呼ばれる（例示）。
- `period="1y"` で 200 を返す（例示）。
- `period` 未指定時は既定 `24h`・limit 既定 `10` で親 spec と同一挙動（後方互換、Requirement 4.1/4.2/4.3）。
- 不正 period（例：`"xyz"`、`"30d"`）で 422（例示）。
- `get_top_ips` の `since=None` 呼び出し（全期間）で、下限フィルタなしの集計になること（リポジトリ単体、Requirement 3.2）。

### Backend — 影響範囲外の非回帰

- `/geo/country-summary`・`/geo/ips/{ip}` の既存テストが引き続きパスすること（Requirement 4.4）。
- **`/dashboard/top-ips`（Top IP テーブル向けエンドポイント）の既存テストが引き続きパスすること（Requirement 4.4）。** `get_top_ips` の `since` 型緩和が `dashboard.py` の呼び出し（非 None since）に影響しないことを、既存テストの非回帰で担保する。`get_top_ips` の呼び出し元が `geo.py` と `dashboard.py` の 2 か所であることは確認済み。

### Frontend

この環境では npm が使えないため、フロントの検証は **ユーザー環境でのビルド確認（`cd frontend && npm run build`）** に委ねる。変更は `DashboardPage.tsx` の state・タブ UI・`useGeoTopIPs(20, mapPeriod)` 呼び出しに限定され、型（`string` period）・既存 API 型と整合するため、型エラーは発生しない想定。UI のタブ表示・地図描画（Requirement 1.1〜1.5、2.2〜2.5）は親 spec 同様に PBT の対象外とし、ビルド検証と目視確認で担保する。

---

## Requirements Traceability

| Requirement | 設計要素 |
|---|---|
| 1.1 期間タブ 4 択（24h/7d/1y/all） | `DashboardPage`: `MAP_PERIOD_OPTIONS` によるタブ group |
| 1.2 初期選択 24h | `DashboardPage`: `useState<string>("24h")` |
| 1.3 選択で表示更新 | `setMapPeriod` → `useGeoTopIPs(20, mapPeriod)` 再取得 |
| 1.4 選択中タブの区別表示 | 選択中 `bg-hw-accent`、未選択 `bg-hw-card`（Detection Analysis と同一） |
| 1.5 Detection Analysis と同一のタブ方式 | 既存 `PERIOD_OPTIONS` セレクタと同一構造・スタイル |
| 2.1 limit=20 で要求 | `useGeoTopIPs(20, mapPeriod)` → `fetchGeoTopIPs(20, ...)` |
| 2.2 降順・最大 20 件を表示対象 | `get_top_ips`（降順・limit）＋ `limit=20` |
| 2.3/2.4 緯度経度ありのみマーカー | `GeoMap`（既存挙動、変更不要） |
| 2.5 0 件時の案内表示 | `GeoMap`（既存挙動、変更不要） |
| 3.1 period=1y（直近365日） | `_PERIOD_MAP["1y"] = timedelta(days=365)` |
| 3.2 period=all（全期間・下限なし） | `since=None` 分岐 ＋ `get_top_ips` の None 許容化 |
| 3.3 24h/7d は親 spec と同一 | `_PERIOD_MAP` の既存値を維持 |
| 3.4 limit 1〜100 | `Query(ge=1, le=100)`（維持） |
| 3.5 不正 period はエラー | `Query(pattern="^(1h|6h|24h|7d|1y|all)$")` → 422 |
| 3.6 未解決 geo は null | `_geo_to_dict` / フェイルセーフ Resolver（維持） |
| 4.1 period 既定 24h | `Query(default="24h")`（維持） |
| 4.2 limit 既定 10・範囲 1〜100 | `Query(default=10, ge=1, le=100)`（維持） |
| 4.3 period 未指定で親 spec と同一 | 既定 `24h` かつ非 None since（後方互換） |
| 4.4 Country_Summary / Top IP テーブルは不変 | `get_ip_counts`・`/geo/country-summary`・`dashboard.py` の `/dashboard/top-ips` は変更しない（`get_top_ips` の since 型緩和は非 None 呼び出しに無影響） |
