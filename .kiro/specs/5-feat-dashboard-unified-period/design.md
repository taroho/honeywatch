# Design Document

## Overview

本設計は spec `5-feat-dashboard-unified-period` の requirements.md（R1〜R10）を実現するための技術設計である。HoneyWatch の Dashboard に **単一の統一期間セレクタ（Unified_Period_Selector）** を配置し、Recent Events と Events 一覧（Excluded_Items）を除く全項目（Linked_Items）を、その 1 つのセレクタに連動させて同一期間で集計・表示する。期間の選択肢は `1h` / `6h` / `24h` / `7d` / `1y`（直近365日）/ `all`（全期間＝下限なし）の 6 種、初期選択は `24h` とする。

親フェーズ `4-feat-geoip-ip-location` および修正 spec `4.01-fix-geoip-map-period-filter` で検討済みの「地図の期間対応（limit=20・`1y`/`all` 追加・`get_top_ips` の since None 許容化）」は、**本 spec に統合する**。4.01 は未実装のまま破棄される前提であり、地図（Geo_Map）は独立タブではなく統一セレクタに従う。

### 何を変えるか（要点）

1. **フロント：統一期間セレクタへの一本化**
   - `DashboardPage` に単一の `period` state（初期 `"24h"`）と選択肢 `UNIFIED_PERIOD_OPTIONS`（`1h`/`6h`/`24h`/`7d`/`1y`/`all`）を持たせる。
   - 既存の Detection Analysis 専用セレクタ（`PERIOD_OPTIONS`、初期 `7d`）を **廃止** し、統一セレクタへ統合する。
   - Linked_Items の各 hook に `period` を渡して連動させる。地図・Top IP テーブルは `useGeoTopIPs(20, period)` を共用する。
   - Recent Events（`useRecentEvents`）と Events 一覧は据え置き（非連動）。

2. **バックエンド：period の共通化と `1y`/`all` 拡張**
   - `analysis.py` の `_PERIOD_MAP` / `_period_to_range`、`dashboard.py` の重複ロジック、`geo.py` の `_PERIOD_MAP` を、**単一の共通ヘルパー `resolve_period_range(period)`** に集約する（`period → (since: datetime | None, until: datetime)`）。`all` は `since=None`、`1y` は `now - timedelta(days=365)` を返す。
   - period 対応の全エンドポイント（Summary / Timeline / Attack_Types / Severity / Risk_Ranking / Top_IPs）の Query pattern を `^(1h|6h|24h|7d|1y|all)$` に統一する。
   - `all` に対応するため、リポジトリの集計メソッド（`get_summary` / `get_timeline` / `get_top_ips` / `count_by_attack_type` / `count_by_severity` / `get_ip_aggregates_for_ranking`）の `since` を `datetime | None` 許容化する（`get_ip_counts` は既に対応済み）。`since=None` のとき下限フィルタを外す。
   - Summary_Endpoint に period パラメータを新設（既定 `24h`）。従来の「本日固定」を廃止する。
   - Timeline の `1y`/`all` は区間数過大を防ぐため、interval を時間単位以上（`interval_minutes >= 60`）にクランプする。

3. **Country_Summary（国別）：フロント変換で最小差分**
   - `country-summary` は現状 `start`/`end`（ISO 8601）方式で、既に全期間対応済み。**バックエンドは変更せず、フロントで `period → (start, end)` に変換して既存 API を呼ぶ**（`all` は start/end 未指定）。

### 最小差分・後方互換方針

- **DB スキーマ変更なし・新規 npm 依存なし。** 地理情報は親 spec と同じく非永続（都度解決）。
- `since` の型を `datetime | None` に緩めても、既存の非 None 呼び出しの挙動は不変（下限フィルタは `since` 指定時のみ適用）。
- period 未指定時は全エンドポイントで既定 `24h`。`1h`/`6h`/`24h`/`7d` の集計対象期間は従来と同一。
- limit の既定・受理範囲（1〜100）は維持する。

---

## Architecture

### レイヤー構成（変更範囲）

既存のレイヤー構成（Honeypot → Collector → Detection → Database → API → Dashboard）のうち、**Database 層（リポジトリ）・API 層・Dashboard 層** にのみ手を入れる。Honeypot / Collector / Detection には影響しない。

```
Dashboard (React)
  DashboardPage
    period state（初期 "24h"） / UNIFIED_PERIOD_OPTIONS（1h/6h/24h/7d/1y/all）
      ├─ useDashboardSummary(period)      → GET /dashboard/summary?period=
      ├─ useTimeline(period, interval)     → GET /dashboard/timeline?period=&interval=
      ├─ useGeoTopIPs(20, period)          → GET /geo/top-ips?limit=20&period=   （地図 + Top IP テーブル共用）
      ├─ useAttackTypes(period)            → GET /analysis/attack-types?period=
      ├─ useSeveritySummary(period)        → GET /analysis/severity-summary?period=
      ├─ useRiskRanking(limit, period)     → GET /analysis/risk-ranking?limit=&period=
      └─ useCountrySummary(start, end)     → GET /geo/country-summary?start=&end=  （period→start/end 変換）
    ── Excluded_Items（非連動）: useRecentEvents(10) / Events 一覧ページ
       ▼
API_Server (FastAPI)
  api/period.py（新規・共通ヘルパー）
    resolve_period_range(period) -> (since: datetime | None, until: datetime)
       ├─ "all"           → (None, now)
       ├─ "1y"            → (now - 365d, now)
       └─ 1h/6h/24h/7d    → (now - timedelta, now)
       ▼
  routes/dashboard.py  ── summary(period) / timeline(period, interval)
  routes/analysis.py   ── attack-types / severity-summary / risk-ranking(period)
  routes/geo.py        ── top-ips(limit, period)   ※ country-summary は period 非対応のまま（start/end）
       │  period 検証（pattern: ^(1h|6h|24h|7d|1y|all)$ → 不正は 422）
       ▼
Database 層
  repositories/attack.py
    get_summary / get_timeline / get_top_ips / count_by_attack_type /
    count_by_severity / get_ip_aggregates_for_ranking
       └─ since: datetime | None（None のとき下限フィルタなし＝全期間）
    get_ip_counts（既に None 許容・変更不要）
```

### 共通 period 変換ヘルパーの置き場所（設計判断）

現状、period → 期間の変換は **3 か所** に重複している。

| 場所 | 現状の実装 |
|---|---|
| `dashboard.py` | timeline / top-ips 内にインラインの `period_map`（`str → timedelta`）を各々定義 |
| `analysis.py` | モジュールレベルの `_PERIOD_MAP` と `_period_to_range()`（`(datetime, datetime)` を返す） |
| `geo.py` | モジュールレベルの `_PERIOD_MAP` と `now - _PERIOD_MAP[period]` のインライン算出 |

これらは同一ロジックの重複であり、`1y`/`all` の追加でさらに分岐が増える。そこで **API 層に共通モジュール `src/honeywatch/api/period.py` を新設** し、`resolve_period_range` を 1 つ用意して全ルートがこれを使う。

- **置き場所：`honeywatch/api/period.py`（API 層内）。**
  `core/config.py` は環境設定の一元管理用であり、期間変換は API のクエリ解釈に属するため API 層に置くのが責務として自然である。過剰な抽象化を避け、モジュール 1 つ・関数 1 つに留める。
- **戻り値：`tuple[datetime | None, datetime]`。**
  `since` は `all` のとき `None`（下限なし）、それ以外は `now - timedelta`。`until` は常に `now`（要求受信時刻）。`now` はヘルパー内部で `datetime.now(UTC)` を取得する（呼び出しごとに要求受信時刻を用いる）。
- **`_PERIOD_MAP` の扱い：** `1h`/`6h`/`24h`/`7d`/`1y` は `timedelta` で表現し、`all` はマップに含めず `since=None` の分岐で扱う（`all` は timedelta で表せないため）。これは 4.01 design と同一の判断である。

```python
# src/honeywatch/api/period.py（新規）
from datetime import UTC, datetime, timedelta

# 受理する period の正規表現（全ルートで共有する）
PERIOD_PATTERN = "^(1h|6h|24h|7d|1y|all)$"

# period → timedelta のマップ（"all" は下限なしのため含めない）
_PERIOD_MAP: dict[str, timedelta] = {
    "1h": timedelta(hours=1),
    "6h": timedelta(hours=6),
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "1y": timedelta(days=365),  # 直近365日（Requirement 3.1）
}


def resolve_period_range(period: str) -> tuple[datetime | None, datetime]:
    """period 文字列を (since, until) に変換する.

    - "all": since=None（下限なし＝全期間）, until=now
    - それ以外: since = now - _PERIOD_MAP[period], until = now

    Args:
        period: 受理済みの period 文字列（Query の pattern で事前検証される）。

    Returns:
        (since, until)。since は "all" のとき None。until は要求受信時刻（now）。
    """
    now = datetime.now(UTC)
    if period == "all":
        return None, now
    return now - _PERIOD_MAP[period], now
```

### データフロー（期間選択時）

1. 利用者が Unified_Period_Selector で period を選択 → `DashboardPage` の `period` state が更新される。
2. `period` を依存に持つ各 hook（`useDashboardSummary(period)` など）が再取得を実行する。`useGeoTopIPs(20, period)` は地図・Top IP テーブルの両方に供給する。国別は `period` から算出した `start`/`end` を `useCountrySummary` へ渡す。
3. 各エンドポイントが `resolve_period_range(period)` で `(since, until)` を決定し、リポジトリ集計メソッドを呼ぶ。`since is None`（`all`）のときは下限フィルタを付けない。
4. Timeline は `1y`/`all` のとき `interval_minutes` を 60 以上にクランプしてから `get_timeline` を呼ぶ。
5. Country_Summary は既存の `start`/`end` 方式（`all` は未指定＝全期間）で集計する。

---

## Components and Interfaces

### Backend

#### 新規: `src/honeywatch/api/period.py`

上記 Architecture の `resolve_period_range` と `PERIOD_PATTERN` を定義する。全 period 対応ルートがこれを import して使用する。

#### `src/honeywatch/api/routes/dashboard.py`

**`summary`：period パラメータを新設し、本日固定を廃止する（Requirement 4）**

```python
from honeywatch.api.period import PERIOD_PATTERN, resolve_period_range

@router.get("/summary")
async def get_dashboard_summary(
    _user: AuthUser,
    db: DbSession,
    period: str = Query(default="24h", pattern=PERIOD_PATTERN),
) -> dict[str, object]:
    since, until = resolve_period_range(period)
    repo = AttackEventRepository(db)
    summary = await repo.get_summary(since=since, until=until)
    return {
        "attacks_today": summary["total"],
        "unique_ips_today": summary["unique_ips"],
        "ssh_attempts_today": summary["ssh_attempts"],
        "http_attacks_today": summary["http_attacks"],
        # period_start は since が None のとき null を返す（all は下限なし）
        "period_start": since.isoformat() if since is not None else None,
        "period_end": until.isoformat(),
    }
```

- レスポンスのキー名（`attacks_today` など）は **変更しない**（フロント型・既存表示の後方互換）。カード表題の「本日」依存の解消は、後述のフロント側で文言を期間非依存に変更して行う（Requirement 4.4）。`period_start` は `all` のとき `null` を返す（下限なしを表現）。

**`timeline`：`1y`/`all` を追加し、粒度クランプを行う（Requirement 5）**

```python
_INTERVAL_MAP: dict[str, int] = {"5m": 5, "15m": 15, "1h": 60}

@router.get("/timeline")
async def get_dashboard_timeline(
    _user: AuthUser,
    db: DbSession,
    period: str = Query(default="24h", pattern=PERIOD_PATTERN),
    interval: str = Query(default="1h", pattern="^(5m|15m|1h)$"),
) -> dict[str, object]:
    since, until = resolve_period_range(period)
    interval_minutes = _INTERVAL_MAP[interval]
    # 1y / all は区間数過大を防ぐため最小粒度を 1 時間にクランプ（Requirement 5.5）
    if period in ("1y", "all"):
        interval_minutes = max(interval_minutes, 60)
    repo = AttackEventRepository(db)
    timeline = await repo.get_timeline(
        since=since, until=until, interval_minutes=interval_minutes
    )
    return {"timeline": timeline}
```

- `interval` パラメータ（`5m`/`15m`/`1h`）は引き続き受理する（Requirement 5.4）。`1y`/`all` で `5m`/`15m` が指定されても実効粒度は 1h にクランプされる。
- 粒度の丸め方針：`get_timeline` は `interval_minutes` に応じて `date_trunc('minute'|'quarter_hour'|'hour')` を選択する既存実装であり、`interval_minutes >= 60` のとき `date_trunc('hour', ...)` となる。過度に凝らず「`1y`/`all` は最低でも 1h バケット」を保証する。日単位への丸め（`date_trunc('day')`）はさらなる区間削減が必要になった場合の将来拡張とし、本 spec では 1h クランプに留める（区間数：`1y` で最大 365×24=8760、`all` は全期間だが 1h バケットで十分実用範囲）。

> 備考：`dashboard.py` の `/dashboard/top-ips`（Top IP テーブル向け別実装）は、フロントが `useGeoTopIPs`（`/geo/top-ips`）を使う構成であり Linked_Items としては `/geo/top-ips` を用いる。`/dashboard/top-ips` エンドポイント自体は本 spec の連動対象ではないが、`resolve_period_range` 共通化に合わせて period 拡張しておくと重複が減る（任意）。**最小差分方針として、フロントで実際に使う `/geo/top-ips` を優先し、`/dashboard/top-ips` は `resolve_period_range` への置き換え + pattern 統一のみ行う（挙動不変、`get_top_ips` の since None 許容化に追従）。**

#### `src/honeywatch/api/routes/analysis.py`

`_PERIOD_MAP` / `_period_to_range` を削除し、共通の `resolve_period_range` に置き換える。`attack-types` / `severity-summary` / `risk-ranking` の Query pattern を `PERIOD_PATTERN` に統一する。

```python
from honeywatch.api.period import PERIOD_PATTERN, resolve_period_range

@router.get("/attack-types")
async def get_attack_types(
    _user: AuthUser, db: DbSession,
    period: str = Query(default="24h", pattern=PERIOD_PATTERN),
) -> dict[str, object]:
    since, until = resolve_period_range(period)
    repo = AttackEventRepository(db)
    counts = await repo.count_by_attack_type(since=since, until=until)
    return {"attack_types": counts}
```

`severity-summary` / `risk-ranking` も同様に `resolve_period_range` を使う。`risk-ranking` の `limit`（`ge=1, le=100`）と `get_ip_aggregates_for_ranking(limit=max(limit*3, 30))` のロジックは維持する。

#### `src/honeywatch/api/routes/geo.py`

- `_PERIOD_MAP` を削除し、`top-ips` を `resolve_period_range` に置き換える。Query pattern を `PERIOD_PATTERN` に統一する。

```python
from honeywatch.api.period import PERIOD_PATTERN, resolve_period_range

@router.get("/top-ips")
async def get_geo_top_ips(
    _user: AuthUser, db: DbSession, resolver: GeoIPResolverDep,
    limit: int = Query(default=10, ge=1, le=100),
    period: str = Query(default="24h", pattern=PERIOD_PATTERN),
) -> dict[str, object]:
    since, until = resolve_period_range(period)
    repo = AttackEventRepository(db)
    ips = await repo.get_top_ips(since=since, until=until, limit=limit)
    # 以降の geo 付与ロジック（resolver.resolve → _geo_to_dict）は既存のまま
    ...
```

- **`country-summary` は変更しない。** period ではなく `start`/`end`（ISO 8601）方式を維持し、フロント側で `period → (start, end)` に変換する（下記フロント + 下記「Country_Summary の扱い」参照）。

#### `src/honeywatch/db/repositories/attack.py`

`all`（下限なし）に対応するため、以下のメソッドの `since` を `datetime | None` 許容化し、`since is None` のとき `timestamp >= since` の下限フィルタを付けないようにする。`until` は現状どおり必須（全ルートが `now` を渡す）。**`get_ip_counts` は既に対応済みで変更不要。**

| メソッド | 変更内容 | 後方互換の根拠 |
|---|---|---|
| `get_summary(since, until)` | `since: datetime | None` 化。`base_filter` を「`until` 常時 + `since` は None でなければ追加」に分割 | 非 None 呼び出しは従来どおり両端フィルタ |
| `get_timeline(since, until, interval_minutes)` | `since: datetime | None` 化。`where` の下限を条件分岐 | 同上 |
| `get_top_ips(since, until, limit)` | `since: datetime | None` 化（4.01 と同一パターン） | 同上 |
| `count_by_attack_type(since, until)` | `since: datetime | None` 化 | 同上 |
| `count_by_severity(since, until)` | `since: datetime | None` 化 | 同上 |
| `get_ip_aggregates_for_ranking(since, until, limit)` | `since: datetime | None` 化（先頭の絞り込みクエリの下限を条件分岐） | 同上 |

例（`get_summary` の `base_filter` 分割）:

```python
async def get_summary(
    self, since: datetime | None, until: datetime,
) -> dict[str, int]:
    filters = [AttackEventModel.timestamp <= until]
    if since is not None:
        filters.append(AttackEventModel.timestamp >= since)
    # 以降、各 count クエリで .where(*filters, ...) を用いる（従来の base_filter を置換）
    ...
```

> `since=None` を渡す呼び出しは `all` 選択時のみ発生する。既存の非 None 呼び出し（`1h`〜`1y`）はフィルタ内容が従来と一致するため、集計結果は不変（後方互換）。

### Frontend

#### `frontend/src/pages/DashboardPage.tsx`：統一セレクタへ一本化

- 選択肢定数を `PERIOD_OPTIONS`（4 択）から `UNIFIED_PERIOD_OPTIONS`（6 択）へ差し替える。
- `period` state の初期値を `"7d"` から `"24h"` に変更する（Requirement 1.3）。
- **Detection Analysis 専用セレクタを廃止** し、ページ上部（サマリーカードの直上）に単一の統一セレクタを配置する（Requirement 1.1）。UI は既存の Detection Analysis タブと同一スタイル（選択中 `bg-hw-accent`、未選択 `bg-hw-card`）とする（Requirement 1.4/1.5）。
- 各 hook に `period` を連動させる。国別は `period` から `start`/`end` を算出して渡す。

```tsx
// 統一期間セレクタの選択肢（Requirement 1.2）
const UNIFIED_PERIOD_OPTIONS = ["1h", "6h", "24h", "7d", "1y", "all"] as const;

// period → (start, end) 変換（Country_Summary 用。resolve_period_range と同じ期間定義）
function periodToRange(period: string): { start?: string; end?: string } {
  if (period === "all") return {}; // 下限なし＝全期間（start/end 未指定）
  const now = new Date();
  const end = now.toISOString();
  const ms: Record<string, number> = {
    "1h": 3600e3, "6h": 6 * 3600e3, "24h": 24 * 3600e3,
    "7d": 7 * 24 * 3600e3, "1y": 365 * 24 * 3600e3,
  };
  return { start: new Date(now.getTime() - ms[period]).toISOString(), end };
}

// コンポーネント内
const [period, setPeriod] = useState<string>("24h"); // 初期 24h（Requirement 1.3）

const { data: summary, loading: summaryLoading } = useDashboardSummary(period);
const { data: timeline, loading: timelineLoading } = useTimeline(period);
const { data: topIPs, loading: topIPsLoading } = useGeoTopIPs(20, period); // 地図 + Top IP テーブル（limit=20）
const { data: attackTypes, loading: attackTypesLoading } = useAttackTypes(period);
const { data: severity, loading: severityLoading } = useSeveritySummary(period);
const { data: riskRanking, loading: riskLoading } = useRiskRanking(10, period);

const { start, end } = periodToRange(period);
const { data: countrySummary, loading: countryLoading } = useCountrySummary(start, end);

// Excluded_Items（非連動・据え置き）
const { data: events, loading: eventsLoading } = useRecentEvents(10);
```

統一セレクタ UI（ページ上部に配置）:

```tsx
<div className="flex items-center justify-between mb-4">
  <h1 className="text-lg font-bold text-gray-100">Dashboard</h1>
  <div className="flex gap-1">
    {UNIFIED_PERIOD_OPTIONS.map((opt) => (
      <button
        key={opt}
        onClick={() => setPeriod(opt)}
        className={`px-3 py-1 rounded text-xs font-medium transition-colors ${
          period === opt ? "bg-hw-accent text-white" : "bg-hw-card text-gray-400 hover:text-gray-200"
        }`}
      >
        {opt}
      </button>
    ))}
  </div>
</div>
```

Detection Analysis セクションの見出しは残してよいが、**その隣にあった期間セレクタ（`PERIOD_OPTIONS.map(...)`）は削除する**（統一セレクタに統合済み）。

#### hooks のシグネチャ変更

現状の hook シグネチャと必要な変更を洗い出す。**period 引数はいずれも既定値付きで追加し、後方互換を保つ**（既存の引数なし呼び出しがあっても既定 `24h` で従来相当）。

| hook | 現状シグネチャ | 変更 |
|---|---|---|
| `useDashboardSummary` | `()`（period 引数なし・依存配列 `[]`） | **`(period: string = "24h")` を追加**。依存配列を `[period]` に。`fetchDashboardSummary` に period を渡す |
| `useTimeline` | `(period="24h", interval="1h")` | 変更不要（既に period 引数あり） |
| `useGeoTopIPs` | `(limit=10, period="24h")` | 変更不要（呼び出し側で `(20, period)`） |
| `useAttackTypes` | `(period="24h")` | 変更不要 |
| `useSeveritySummary` | `(period="24h")` | 変更不要 |
| `useRiskRanking` | `(limit=10, period="24h")` | 変更不要 |
| `useCountrySummary` | `(start?, end?)` | 変更不要（呼び出し側で period→start/end 変換して渡す） |

唯一シグネチャ変更が必要なのは **`useDashboardSummary`**（period 引数なし）。あわせて `client.ts` の `fetchDashboardSummary` に period 引数を追加する。

#### `frontend/src/api/client.ts`：`fetchDashboardSummary` に period 追加

```ts
export async function fetchDashboardSummary(
  period: string = "24h"
): Promise<DashboardSummary> {
  const params = new URLSearchParams({ period });
  const response = await fetchWithAuth(`${API_BASE}/dashboard/summary?${params}`);
  return response.json();
}
```

- 他の fetch 関数（`fetchTimeline` / `fetchGeoTopIPs` / `fetchAttackTypes` / `fetchSeveritySummary` / `fetchRiskRanking` / `fetchCountrySummary`）は既に period または start/end を受けるため変更不要。`1y`/`all` も文字列としてそのまま送出される。
- `login()` 内の `dashboard/summary` 呼び出し（period なし）はバックエンド既定 `24h` で受理されるため変更不要。

#### `GeoMap.tsx` / `TopIPsTable.tsx` / `CountryRankingTable.tsx`：変更不要

`GeoMap` は entries を受けて緯度経度ありのマーカーを描画する既存挙動（Requirement 6.5）を維持する。データ供給（limit=20・期間）は `useGeoTopIPs(20, period)` 側で制御するため、コンポーネント本体は変更しない。Top IP テーブル・国別テーブルも表示ロジックは変更不要。

### Country_Summary の扱い（設計判断：フロント変換を採用）

`all` を含む統一期間に国別ランキングを連動させる方法として 2 案を比較した。

- **案 A（採用）：フロントで `period → (start, end)` に変換し、既存 `country-summary`（start/end 方式）を呼ぶ。**
- 案 B：`country-summary` に period パラメータを追加し、バックエンドで変換する。

**案 A を採用する理由：**

1. **最小差分。** `country-summary` は既に `start`/`end` の両端指定・全期間対応（両方未指定）を実装済み（親 spec の Requirement 5.5/5.6 で担保）。バックエンドを一切変更せず、フロントの 1 関数（`periodToRange`）追加のみで統一連動を実現できる。
2. **`all` が自然。** `all` は start/end を渡さない＝既存の全期間集計にそのまま乗る。
3. **後方互換。** `country-summary` の API・テストを変更しないため非回帰リスクが最小。

期間定義の一貫性（フロントの `periodToRange` とバックエンドの `resolve_period_range` が同じ意味の範囲を指す）は、`1y=365日`・`all=下限なし`・他は同一 timedelta と定義を揃えることで担保する。フロント・バックエンドで `now` を各々取得する差（ミリ秒〜秒オーダー）は集計結果に実害がない。

---

## Data Models

本 spec は永続データモデル（`attack_events` テーブル）を変更しない（Requirement 10.3）。地理情報は非永続のまま（Requirement 10.2）。

### API の period パラメータ（共通）

- 型：文字列。受理値は `1h` / `6h` / `24h` / `7d` / `1y` / `all` の 6 種（`PERIOD_PATTERN`）。
- 集計対象期間：
  - `1h`/`6h`/`24h`/`7d`：`now - timedelta`（従来と同一、Requirement 3.3）。
  - `1y`：`now - timedelta(days=365)`（Requirement 3.1）。
  - `all`：下限なし（`since=None`、Requirement 3.2）。

### レスポンス形

- 各エンドポイントの JSON 構造・キー名は変更しない。`summary` は period 反映で値が変わるのみ（`period_start` は `all` のとき `null`）。フロントの型（`DashboardSummary` 等）は変更不要。

### リポジトリメソッドの `since` 型

- `get_summary` / `get_timeline` / `get_top_ips` / `count_by_attack_type` / `count_by_severity` / `get_ip_aggregates_for_ranking` の `since` を `datetime` → `datetime | None` に緩和する。戻り値の形は不変。

### フロントの期間型・定数

- `UNIFIED_PERIOD_OPTIONS`（6 択）を `as const` タプルで定義する。hook / fetch の `period` 引数は `string` のままとし、新たな共用体型は導入しない（最小差分方針）。

---

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system-essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

本 spec の中心的なロジックは、共通ヘルパー `resolve_period_range` による `period → (since, until)` の変換と、それを全ルートが共有すること、および不正 period の拒否である。これらは入力（period）で挙動が意味を持って変わる純粋ロジックであり PBT が適切である。UI のセレクタ表示・連動描画・地図マーカー描画は例示テスト／ビルド検証で扱う（Testing Strategy 参照）。親 spec の geo 付与・降順・limit 上限・未解決 null・国別集計・`start>end`→400 のプロパティとは重複しない範囲で、period 変換に絞って定義する。

### Property 1: period → (since, until) 変換の一貫性

*For any* 要求受信時刻 now と任意の受理 period（`1h`/`6h`/`24h`/`7d`/`1y`/`all`）について、`resolve_period_range(period)` は次を満たす：`period == "all"` のとき `since is None` かつ `until == now`、`period == "1y"` のとき `until - since == timedelta(days=365)`、それ以外（`1h`/`6h`/`24h`/`7d`）のとき `until - since == _PERIOD_MAP[period]` であり、いずれの場合も `until` は now（要求受信時刻）に一致する。

**Validates: Requirements 3.1, 3.2, 3.3, 5.2, 5.3, 7.4, 7.5**

### Property 2: 全 period 対応エンドポイントは同一の period 変換を共有する

*For any* 受理 period について、period を受け付ける各エンドポイント（Summary_Endpoint / Timeline_Endpoint / Attack_Types_Endpoint / Severity_Endpoint / Risk_Ranking_Endpoint / Top_IPs_Endpoint）は、同一 period に対して `resolve_period_range(period)` が返すのと同じ `(since, until)` をリポジトリ集計メソッドへ渡す（`all` のときは `since=None` を渡す）。

**Validates: Requirements 2.2, 4.2, 5.1, 6.1, 7.1, 7.2, 7.3**

### Property 3: 不正な period はエラー応答となり集計を返さない

*For any* `1h`/`6h`/`24h`/`7d`/`1y`/`all` のいずれにも一致しない period 文字列について、period を受け付ける各エンドポイントはエラー応答（HTTP 422）を返し、正常な集計レスポンス本体（`ips` / `timeline` / `attack_types` 等）を返さない。

**Validates: Requirements 9.1**

### Property 4: 1y / all のタイムラインは時間単位以上の粒度に丸められる

*For any* 要求 interval（`5m`/`15m`/`1h`）について、Timeline_Endpoint に `period` が `1y` または `all` で指定されたとき、`get_timeline` に渡される `interval_minutes` は 60 以上である（区間数過大を防ぐための時間単位クランプ）。

**Validates: Requirements 5.5**

---

## Error Handling

- **不正な period（Requirement 9.1）：** 各 period 対応ルートは `Query(pattern=PERIOD_PATTERN)`（`^(1h|6h|24h|7d|1y|all)$`）で制約する。FastAPI はパターン不一致に対し **HTTP 422 Unprocessable Entity** を自動で返す。バリデーション段階で拒否されるため DB 集計は実行されない。requirements.md の「period が不正である旨を示すエラー応答を返し集計結果を返さない」を 422 で満たす。
- **limit の範囲外（Requirement 9.3）：** `Query(ge=1, le=100)` により範囲外は 422。既定 10・範囲 1〜100 を維持する（Top_IPs / Risk_Ranking）。
- **period 未指定（Requirement 9.2）：** `Query(default="24h")` により既定 `24h` で集計する。
- **timeline の巨大区間対策（Requirement 5.5）：** `period in ("1y","all")` のとき `interval_minutes = max(interval_minutes, 60)` にクランプし、区間数の過大化を防ぐ。
- **geo 未解決（Requirement 6.5、10.2）：** 親 spec のフェイルセーフ設計を維持する。Resolver 利用不可・未解決でも 500 にせず geo 各フィールドを null で返す（`_geo_to_dict` / `resolver.resolve` の既存挙動）。緯度経度なしのエントリはフロントの `GeoMap` がマーカーから除外する。
- **country-summary の期間（Requirement 8）：** 既存の `start`/`end` パース（不正 ISO 8601 / `start>end` は 400）を維持する。`all` は start/end 未指定で全期間。
- **`since=None`（all）時の集計：** リポジトリは下限フィルタを付けず `timestamp <= until` のみで集計する。空集合でもエラーにはせず、通常の空結果を返す。

---

## Testing Strategy

pytest を用いる。バックエンドの DB 依存は既存 `tests/test_api/test_geo.py` の方針（`app.dependency_overrides` で `verify_credentials`/`get_db` を無効化、`AttackEventRepository` を `patch` してモックの `AsyncMock` に差し替え）に合わせる。フロントは本環境で npm が使えないため、**ユーザー環境でのビルド検証（`cd frontend && npm run build`）と目視確認** に委ねる。

### Dual Testing Approach

- **Property tests（Hypothesis、各最小 100 iterations / `@settings(max_examples=100, ...)`）：** period 変換の純粋ロジックと不変条件を網羅する。新規 PBT ライブラリは導入せず、既存の Hypothesis を用いる。
- **Unit / example tests：** 具体的な period 値・エラー条件・境界・後方互換を確認する。

各 property test には次のタグをコメントで付与する：
**Feature: 5-feat-dashboard-unified-period, Property {番号}: {プロパティ本文}**

### Backend — property tests

- **Property 1（変換一貫性）：** `resolve_period_range` の単体プロパティテスト（`tests/test_api/test_period.py` 新規）。受理 period を `st.sampled_from([...])` で生成し、`all→since=None`、`1y→差 365日`、他→差が `_PERIOD_MAP[period]` に一致、`until` が呼び出し直前後の now とほぼ一致（許容誤差数秒）することを検証する。
- **Property 2（全ルート共有）：** 各エンドポイントを TestClient で叩き、モックした repo メソッドの `call_args` の `since`/`until` が、そのリクエスト時点の `resolve_period_range(period)` と整合する（`all→since=None`、他→`until-since ≈ _PERIOD_MAP[period]`）ことを、受理 period 集合を生成して検証する。対象：summary/timeline/attack-types/severity-summary/risk-ranking/geo top-ips。
- **Property 3（不正 period→422）：** `1h/6h/24h/7d/1y/all` に一致しないランダム文字列（例：`st.text()` から受理集合を除外）を生成し、各ルートが 422 を返し正常レスポンス本体を含まないことを検証する。
- **Property 4（timeline 粒度クランプ）：** `period in ("1y","all")` かつ interval を `5m/15m/1h` から生成し、`get_timeline` の `call_args` の `interval_minutes >= 60` を検証する。

### Backend — unit / example tests

- **summary の period 反映（Requirement 4）：** `?period=1h` と `?period=7d` で `get_summary` に渡る `since`/`until` が異なること、period 未指定で `24h` 相当になること、`?period=all` で `since=None`・`period_start` が `null` になることを例示。
- **各エンドポイントの `1y`/`all`：** 200 を返し、`all` で `since=None` が repo に渡ることを例示（summary/timeline/attack-types/severity/risk-ranking/top-ips）。
- **不正 period：** `?period=xyz` / `?period=30d` で 422（例示）。
- **timeline interval 維持（Requirement 5.4）：** `?period=24h&interval=5m` で `interval_minutes=5` が渡ることを例示（クランプ対象外）。
- **repo の `since=None` 許容化：** `get_summary` / `get_timeline` / `get_top_ips` / `count_by_attack_type` / `count_by_severity` / `get_ip_aggregates_for_ranking` を対象に、`since=None` のとき下限フィルタなし（全期間集計）、非 None のとき従来どおり両端フィルタとなることを検証する。DB 実行が難しい環境では、クエリ構築の分岐（`since is not None` の有無で `where` 句が変わること）を対象とする最小テストに留める（既存のモック中心方針に合わせる）。

### Backend — 非回帰（影響範囲外）

- 既存の `1h`/`6h`/`24h`/`7d` の集計対象期間が不変であること（後方互換）。
- `/geo/country-summary`・`/geo/ips/{ip}` の既存テストがパスすること（本 spec で未変更）。
- `/events`（Events 一覧）・Recent Events が period に非依存で従来どおり動くこと（Requirement 2.3, 10.1）。
- `login()` の `dashboard/summary`（period なし）呼び出しが引き続き 200/401 判定できること。

### Frontend（ユーザー環境で検証）

- 変更は `DashboardPage.tsx`（統一セレクタ・`period` state 初期 `24h`・各 hook への period 連動・`periodToRange`・Detection Analysis 専用セレクタ削除）、`useDashboardSummary`（period 引数追加）、`client.ts`（`fetchDashboardSummary` に period 追加）に限定される。型はすべて `string` period・既存 API 型と整合するため型エラーは発生しない想定。
- 検証項目（目視・ビルド）：初期表示で `24h` 選択（Requirement 1.3）、6 択の表示（1.2）、選択中タブの区別表示（1.4/1.5）、期間切替で Linked_Items 全てが更新される（2.1）、Recent Events / Events 一覧が非連動（2.3）、地図・Top IP テーブルが limit=20 で選択期間に連動（6.4/6.6）、国別ランキングが選択期間に連動し `all` で全期間（8.1〜8.3）、サマリーカード表題が期間非依存の文言（4.4）。
- UI レンダリング・地図描画は PBT 非適用（親 spec 同様）。ビルド検証と目視確認で担保する。

---

## Requirements Traceability

| Requirement | 設計要素 |
|---|---|
| 1.1 統一セレクタ 1 つを上部表示 | `DashboardPage`: ページ上部の単一タブ group |
| 1.2 6 択（1h/6h/24h/7d/1y/all） | `UNIFIED_PERIOD_OPTIONS` |
| 1.3 初期 24h | `useState<string>("24h")` |
| 1.4 選択中の区別表示 | 選択中 `bg-hw-accent` / 未選択 `bg-hw-card` |
| 1.5 Detection Analysis と同一タブ方式 | 既存セレクタと同一構造・スタイル |
| 2.1 期間切替で Linked_Items 更新 | 各 hook に単一 `period` を連動 |
| 2.2 常に同一 period で集計 | 単一 state ＋ 全ルートが `resolve_period_range` 共有（Property 2） |
| 2.3 Excluded_Items 非連動 | `useRecentEvents` / Events 一覧を period 非依存で据え置き |
| 3.1 1y=直近365日 | `_PERIOD_MAP["1y"]=timedelta(days=365)`（Property 1） |
| 3.2 all=下限なし全期間 | `resolve_period_range("all")→(None, now)`（Property 1） |
| 3.3 1h/6h/24h/7d は従来同一 | `_PERIOD_MAP` 既存値維持（Property 1） |
| 4.1 summary が period 受理 | `Query(default="24h", pattern=PERIOD_PATTERN)` |
| 4.2 summary が指定 period で集計 | `resolve_period_range` → `get_summary(since, until)`（Property 2） |
| 4.3 summary 未指定で 24h | `Query(default="24h")` |
| 4.4 カード表題を期間非依存に | フロントで表題文言を変更（レスポンスキーは不変） |
| 5.1 timeline が 1y/all 受理 | `PERIOD_PATTERN` に統一（Property 2） |
| 5.2 timeline 1y=直近365日 | `resolve_period_range`（Property 1/2） |
| 5.3 timeline all=全期間 | `since=None` → `get_timeline`（Property 2） |
| 5.4 interval 5m/15m/1h 維持 | interval Query 維持（クランプ対象外時は不変） |
| 5.5 1y/all は時間単位以上の粒度 | `interval_minutes = max(interval_minutes, 60)`（Property 4） |
| 6.1 top-ips が 1y/all 受理 | `PERIOD_PATTERN` に統一（Property 2） |
| 6.2 top-ips 1y=直近365日 | `resolve_period_range`（Property 1/2） |
| 6.3 top-ips all=全期間 | `since=None` → `get_top_ips`（Property 2） |
| 6.4 地図は limit=20 で要求 | `useGeoTopIPs(20, period)` |
| 6.5 緯度経度ありのみマーカー | `GeoMap`（親 spec 既存挙動・変更不要） |
| 6.6 Top IP テーブルが選択期間で表示 | `useGeoTopIPs(20, period)` を地図と共用 |
| 7.1/7.2/7.3 attack-types/severity/risk が 1y/all 受理 | `PERIOD_PATTERN` に統一（Property 2） |
| 7.4 これらが 1y=直近365日 | `resolve_period_range`（Property 1/2） |
| 7.5 これらが all=全期間 | `since=None` → 各 repo メソッド（Property 2） |
| 8.1 国別が選択期間で表示 | フロント `periodToRange(period)` → `useCountrySummary(start, end)` |
| 8.2 国別 all=全期間 | `periodToRange("all")→{}`（start/end 未指定＝既存全期間） |
| 8.3 国別 1h〜1y は当該期間 | `periodToRange`（`resolve_period_range` と同一定義） |
| 9.1 不正 period はエラー・集計なし | `Query(pattern=PERIOD_PATTERN)` → 422（Property 3） |
| 9.2 未指定で 24h | `Query(default="24h")` |
| 9.3 limit 既定・範囲 1〜100 維持 | `Query(default=10, ge=1, le=100)` 維持 |
| 10.1 Excluded_Items を従来維持 | Recent Events / Events を変更しない |
| 10.2 地理情報を非永続で都度解決 | 親 spec の resolver 方式を維持 |
| 10.3 attack_events テーブル不変 | マイグレーション非追加・スキーマ変更なし |
