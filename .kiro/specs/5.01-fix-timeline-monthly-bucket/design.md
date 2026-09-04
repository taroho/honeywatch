# Design Document

## Overview

本設計は spec `5.01-fix-timeline-monthly-bucket` の requirements.md（R1〜R5）を実現するための技術設計である。親フェーズ `5-feat-dashboard-unified-period` で実装済みの Attack Timeline について、Period_Option が `1y` / `all` のとき集計粒度を **月単位（Monthly_Bucket）** に変更し、フロントの横軸ラベルを月単位のときだけ年月（`YYYY/MM`）表記にする。

現状、`dashboard.py` の timeline ルートは `1y`/`all` のとき `interval_minutes` を 60 以上にクランプするだけで、集計は最大でも 1 時間バケット（`date_trunc('hour', ...)`）に留まる。このため `1y` で最大 8760 点となり、長期傾向の俯瞰に不向きである。本 spec では `1y`/`all` を暦月バケット（`date_trunc('month', ...)`）に切り替え、点数を月数分（`1y` で最大 13、`all` は運用期間の月数）に抑える。

### 何を変えるか（要点）

1. **バックエンド：`get_timeline` に月粒度分岐を追加**
   - `get_timeline` の `interval_minutes` による粒度選択に「月」を追加する。既存の 3 段階（`minute`/`quarter_hour`/`hour`）は不変。
   - 月粒度は分では自然に表現できない（暦月の日数が可変）ため、**番兵値**で判定する。`interval_minutes >= _MONTH_SENTINEL`（`43200` = 30 日相当）のとき `date_trunc('month', ...)` を用いる。
2. **バックエンド：timeline ルートで `1y`/`all` のとき月粒度を指定**
   - 現状の「`interval_minutes = max(interval_minutes, 60)`（1h クランプ）」を、`1y`/`all` のとき `interval_minutes = _MONTH_SENTINEL` に置き換える。`1h`〜`7d` は従来どおり interval 値を反映。
3. **フロント：横軸ラベルを月単位のとき年月表記に**
   - `AttackTimeline` に現在の `period`（または月表示フラグ）を渡し、`1y`/`all` のとき横軸ラベルを `YYYY/MM` で整形する。それ以外は従来の時刻表示（時:分）を維持する。

### 最小差分・後方互換方針

- **DB スキーマ変更なし・新規依存なし。** `date_trunc('month', ...)` は PostgreSQL 標準機能。
- `resolve_period_range` は変更しない（集計範囲 since/until の定義は不変、R3）。
- `get_timeline` の非 `1y`/`all` 呼び出し（`interval_minutes < _MONTH_SENTINEL`）は既存の分岐にそのまま乗るため挙動不変（R5.4）。
- Timeline_Endpoint のレスポンス構造（`timeline` 配列・`timestamp`/`total`/`ssh`/`http`）は不変（R5.3）。
- `interval` パラメータの受理値（`5m`/`15m`/`1h`）・pattern は不変。`1y`/`all` では実効的に無視され月粒度になる（R1.3）。

---

## Architecture

### レイヤー構成（変更範囲）

Database 層（`repositories/attack.py`）・API 層（`routes/dashboard.py`）・Dashboard 層（`AttackTimeline.tsx` / `DashboardPage.tsx`）にのみ手を入れる。集計範囲の解決（`api/period.py`）は変更しない。

```
Dashboard (React)
  DashboardPage
    period state（1h/6h/24h/7d/1y/all）
      └─ AttackTimeline に period を渡す（新規）
           └─ period ∈ {1y, all} のとき横軸ラベルを YYYY/MM に整形
      └─ useTimeline(period) → GET /dashboard/timeline?period=&interval=
       ▼
API_Server (FastAPI)
  routes/dashboard.py  ── timeline(period, interval)
       └─ period ∈ {1y, all}: interval_minutes = _MONTH_SENTINEL（変更）
       └─ それ以外: interval_map[interval] を反映（不変）
       ▼
Database 層
  repositories/attack.py
    get_timeline(since, until, interval_minutes)
       └─ interval_minutes >= _MONTH_SENTINEL → date_trunc('month', ...)（新規分岐）
       └─ <= 5 / <= 15 / それ以外 → minute / quarter_hour / hour（不変）
```

### 月粒度の判定方式（設計判断：番兵値 vs 追加引数）

月粒度を `get_timeline` に伝える方法として 2 案を比較した。

- **案 A（採用）：`interval_minutes` の番兵値で月粒度を表す。**
  `_MONTH_SENTINEL = 43200`（= 30 日 × 24 時間 × 60 分）を定義し、`interval_minutes >= _MONTH_SENTINEL` のとき `date_trunc('month', ...)` を選ぶ。`get_timeline` のシグネチャ（`interval_minutes: int`）を変えない。
- 案 B：`get_timeline` に `granularity: str`（`"hour"`/`"month"` 等）の引数を追加する。

**案 A を採用する理由：**

1. **最小差分・後方互換。** `get_timeline` のシグネチャと既存呼び出し（テスト含む）を変えずに済む。既存の粒度選択は `interval_minutes` の大小で分岐する設計であり、その延長で「十分大きい値＝月」と解釈するのは既存パターンに沿う。
2. **意味の一貫性。** 分単位の閾値比較（`<= 5` / `<= 15` / それ以上）に「`>= 43200`（30 日超）なら月」を最上位分岐として足すだけで、粒度が単調に粗くなる並びを保てる。
3. **呼び出し側の明快さ。** ルート側は `1y`/`all` のとき `_MONTH_SENTINEL` を渡すのみ。番兵値の意味はモジュール定数のコメントで明示する。

> トレードオフ：番兵値は「マジックナンバー」的だが、モジュール定数として命名・コメントすることで可読性を担保する。将来「週」「日」など粒度を増やす場合は案 B（明示引数）への移行を検討する余地があるが、本 spec のスコープ（月のみ追加）では案 A が最小差分で妥当。

---

## Components and Interfaces

### Backend

#### `src/honeywatch/db/repositories/attack.py`

`get_timeline` の粒度選択に月分岐を追加する。番兵値 `_MONTH_SENTINEL` をモジュールレベル定数として定義する。

```python
# モジュールレベル定数（attack.py 冒頭付近）
# interval_minutes がこの値以上のとき、暦月単位（date_trunc('month')）で集計する番兵値。
# 30 日相当（30*24*60）。1h/6h/24h/7d では到達せず、1y/all のルートのみが渡す。
_MONTH_SENTINEL = 43200


async def get_timeline(
    self,
    since: datetime | None,
    until: datetime,
    interval_minutes: int = 60,
) -> list[dict[str, object]]:
    # interval_minutes に応じて trunc 単位を選択する。
    # 月粒度は番兵値（>= _MONTH_SENTINEL）で判定する（1y/all 用）。
    if interval_minutes >= _MONTH_SENTINEL:
        trunc_expr = func.date_trunc("month", AttackEventModel.timestamp)
    elif interval_minutes <= 5:
        trunc_expr = func.date_trunc("minute", AttackEventModel.timestamp)
    elif interval_minutes <= 15:
        trunc_expr = func.date_trunc("quarter_hour", AttackEventModel.timestamp)
    else:
        trunc_expr = func.date_trunc("hour", AttackEventModel.timestamp)

    # 以降（filters 構築 / select / group_by / order_by / 整形）は既存のまま変更しない。
    ...
```

- 既存の `<= 5` / `<= 15` / `else(hour)` 分岐は不変（R2.1, R5.4）。月分岐を**最上位**に置き、番兵値以上のときだけ月にする。
- `filters`（`until` 常時 + `since` は None でなければ下限追加）・`select`・整形ロジックは変更しない。レスポンス要素の `timestamp` はバケットの月初 00:00（`date_trunc('month')` の結果、R1.4）。

#### `src/honeywatch/api/routes/dashboard.py`

timeline ルートの `1y`/`all` 分岐を、1h クランプから月粒度指定に変更する。

```python
from honeywatch.db.repositories.attack import _MONTH_SENTINEL
# （または dashboard.py 内に同名定数を定義せず、repo 定数を import して 1 箇所管理）

@router.get("/timeline")
async def get_dashboard_timeline(
    _user: AuthUser,
    db: DbSession,
    period: str = Query(default="24h", pattern=PERIOD_PATTERN),
    interval: str = Query(default="1h", pattern="^(5m|15m|1h)$"),
) -> dict[str, object]:
    since, until = resolve_period_range(period)

    interval_map: dict[str, int] = {"5m": 5, "15m": 15, "1h": 60}
    interval_minutes = interval_map[interval]

    # 1y / all は暦月単位で集計する（区間数を月数に抑える）。
    # interval 指定によらず月粒度を用いる（Requirement 1.3）。
    if period in ("1y", "all"):
        interval_minutes = _MONTH_SENTINEL

    repo = AttackEventRepository(db)
    timeline = await repo.get_timeline(
        since=since, until=until, interval_minutes=interval_minutes
    )
    return {"timeline": timeline}
```

- 定数の一元管理：`_MONTH_SENTINEL` は `attack.py` に定義し、`dashboard.py` から import する（重複定義を避ける）。import 名の公開性（アンダースコア始まり）を避けたい場合は `attack.py` で `MONTH_SENTINEL_MINUTES` として公開名にする案もあるが、本 spec では既存の内部利用に留まるため `_MONTH_SENTINEL` を repo モジュールから import する最小構成とする。
- `1h`/`6h`/`24h`/`7d` は `interval_map[interval]` をそのまま使う（R2.1, R2.2）。従来の 1h クランプ（`max(..., 60)`）は月粒度指定に置き換わるため不要になる。

### Frontend

#### `frontend/src/components/AttackTimeline.tsx`：横軸ラベルの月表示対応

`AttackTimeline` は現在 period を知らず、常に `toLocaleTimeString` で時:分表示している。月粒度のときに `YYYY/MM` を表示するため、`period` を prop で受け取り、`1y`/`all` のとき年月整形に切り替える。

```tsx
interface AttackTimelineProps {
  data: TimelinePoint[];
  loading: boolean;
  period: string; // 追加: 横軸ラベルの粒度判定に用いる
}

export function AttackTimeline({ data, loading, period }: AttackTimelineProps) {
  ...
  // 1y / all は月単位バケットのため年月（YYYY/MM）で表示する（Requirement 4.1）。
  // それ以外は従来どおり時刻（時:分）で表示する（Requirement 4.2）。
  const isMonthly = period === "1y" || period === "all";
  const formatted = data.map((point) => {
    const d = new Date(point.timestamp);
    const label = isMonthly
      ? `${d.getFullYear()}/${String(d.getMonth() + 1).padStart(2, "0")}`
      : d.toLocaleTimeString("ja-JP", { hour: "2-digit", minute: "2-digit" });
    return { ...point, time: label };
  });
  // 以降の LineChart / XAxis(dataKey="time") / 各 Line は変更しない（R4.3）。
  ...
}
```

- Total / SSH / HTTP の各 Line、Tooltip、Legend は変更しない（R4.3）。
- `dataKey="time"` の値を月単位のとき `YYYY/MM` にするだけで、Recharts 側の変更は不要。
- 日付整形はローカルタイム（`getFullYear`/`getMonth`）を用いる。既存の時刻表示も `toLocaleTimeString("ja-JP")` でローカル基準のため、表示基準を揃える。

#### `frontend/src/pages/DashboardPage.tsx`：period を AttackTimeline に渡す

```tsx
<AttackTimeline
  data={timeline}
  loading={timelineLoading || summaryLoading}
  period={period}  // 追加
/>
```

- `useTimeline(period)` は変更不要（既に period を送出。`interval` 未指定で既定 `1h` を送るが、`1y`/`all` ではバックが月粒度に上書きするため実効影響なし）。

#### `client.ts` / `useTimeline.ts`：変更不要

`fetchTimeline` / `useTimeline` は period・interval をそのまま送出するのみで、月粒度化はバック側で判定するため変更不要。

---

## Data Models

本 spec は永続データモデル（`attack_events` テーブル）を変更しない（R5.2）。

### get_timeline の粒度選択（内部仕様）

| interval_minutes | trunc 単位 | 用途 |
|---|---|---|
| `>= _MONTH_SENTINEL`（43200） | `month` | `1y` / `all`（本 spec で追加） |
| `<= 5` | `minute` | `interval=5m`（不変） |
| `<= 15` | `quarter_hour` | `interval=15m`（不変） |
| その他（`hour`） | `hour` | `interval=1h`（不変） |

### レスポンス形

- Timeline_Endpoint のレスポンス構造・キー名は不変（`timeline` 配列、各要素 `timestamp`/`total`/`ssh`/`http`、R5.3）。
- 月粒度のとき `timestamp` はその月の初日 00:00（`date_trunc('month')` の結果、R1.4）。フロントの `TimelinePoint` 型は変更不要。

### フロントの props 型

- `AttackTimelineProps` に `period: string` を追加する。新たな共用体型は導入しない（最小差分）。

---

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system.*

本 spec の中心ロジックは、timeline ルートが `1y`/`all` のとき `get_timeline` に月粒度（番兵値）を渡すこと、および `1h`〜`7d` では従来どおり interval 値を渡すことである。これらは period・interval で挙動が意味を持って変わる純粋ロジックであり PBT が適切である。横軸ラベルの月表示はフロント範囲のため例示・ビルド検証で扱う。

### Property 1: 1y / all は月粒度（番兵値）で集計される

*For any* interval（`5m`/`15m`/`1h`）について、Timeline_Endpoint に period が `1y` または `all` で指定されたとき、`get_timeline` に渡される `interval_minutes` は `_MONTH_SENTINEL` 以上である（すなわち月粒度 `date_trunc('month')` が選択される）。

**Validates: Requirements 1.1, 1.2, 1.3**

### Property 2: 1h/6h/24h/7d は interval に応じた粒度で集計される（後方互換）

*For any* period ∈ {`1h`,`6h`,`24h`,`7d`} と interval ∈ {`5m`,`15m`,`1h`} の組について、`get_timeline` に渡される `interval_minutes` は `interval_map[interval]`（5 / 15 / 60）に一致し、`_MONTH_SENTINEL` 未満である（月粒度に丸められない）。

**Validates: Requirements 2.1, 2.2, 5.4**

### Property 3: get_timeline の粒度選択の単調性

*For any* `interval_minutes` 値について、`get_timeline` は `>= _MONTH_SENTINEL` のとき `month`、`<= 5` のとき `minute`、`<= 15` のとき `quarter_hour`、それ以外のとき `hour` を選択する（粒度は値の増加に対して単調に粗くなり、月が最も粗い）。

**Validates: Requirements 1.1, 1.2, 2.1, 5.4**

---

## Error Handling

- **不正な period / interval：** 既存の `Query(pattern=...)` 制約（period は `PERIOD_PATTERN`、interval は `^(5m|15m|1h)$`）を維持する。不一致は FastAPI が HTTP 422 を返す。本 spec で pattern は変更しない。
- **`since=None`（all）時の集計：** 親 spec と同じく下限フィルタなしで `timestamp <= until` のみ適用する（`get_timeline` の既存挙動）。空集合でもエラーにせず空の `timeline` を返す。
- **月粒度で該当データが無い月：** `group_by` の結果に存在しない月はレスポンスに含まれない（既存の bucket 集計と同じ挙動＝ゼロ埋めはしない）。フロントは受け取った点のみ描画する。本 spec でゼロ埋めは導入しない（最小差分）。
- **フロントの日付整形：** `timestamp` が不正な値になることは想定しない（バックが `date_trunc` 結果を ISO で返す）。`new Date(...)` が Invalid Date でも既存の時刻表示と同様に描画は継続する（例外を投げない）。

---

## Testing Strategy

pytest を用いる。バックエンドの DB 依存は親 spec と同じく `app.dependency_overrides` で `verify_credentials`/`get_db` を無効化し、`AttackEventRepository` を `patch` してモック（`AsyncMock`）に差し替える方針とする。フロントは本環境で npm が使えないため、ユーザー環境でのビルド検証（`cd frontend && npm run build`）と目視確認に委ねる。

### Dual Testing Approach

- **Property tests（Hypothesis、`@settings(max_examples=100)`）：** period × interval の組に対する粒度選択の不変条件を網羅する。新規 PBT ライブラリは導入せず既存の Hypothesis を用いる。
- **Unit / example tests：** 具体的な period・interval 値と、`get_timeline` に渡る `interval_minutes` の値を確認する。

各 property test には次のタグをコメントで付与する：
**Feature: 5.01-fix-timeline-monthly-bucket, Property {番号}: {プロパティ本文}**

### Backend — property tests（`tests/test_api/test_dashboard.py` に追記）

- **Property 1（1y/all は月粒度）：** period を `st.sampled_from(["1y","all"])`、interval を `st.sampled_from(["5m","15m","1h"])` で生成し、TestClient で timeline を叩き、モック `get_timeline` の `call_args.kwargs["interval_minutes"]` が `_MONTH_SENTINEL` 以上であることを検証する。
- **Property 2（短期は interval 反映）：** period を `st.sampled_from(["1h","6h","24h","7d"])`、interval を生成し、`interval_minutes == {5m:5,15m:15,1h:60}[interval]` かつ `< _MONTH_SENTINEL` を検証する。

### Backend — unit / example tests

- `?period=1y`（interval 既定）で `get_timeline` の `interval_minutes` が `_MONTH_SENTINEL`。
- `?period=all&interval=5m` でも `interval_minutes` が `_MONTH_SENTINEL`（interval に依存しない、R1.3）。
- `?period=24h&interval=5m` で `interval_minutes == 5`（従来維持、R2.2）。
- `?period=7d`（interval 既定 1h）で `interval_minutes == 60`。
- （任意・repo 単体）`_MONTH_SENTINEL` を渡したとき、`get_timeline` の粒度選択が `date_trunc('month')` になること。DB 実行が難しい環境では、粒度選択分岐（trunc 単位の決定）を対象とする最小テストに留めるか、Property 3 のロジック検証で代替する。

### Backend — 非回帰（影響範囲外）

- 親 spec で追加した timeline テスト（`1y`/`all` が 200 を返す、`all` で `since=None` が渡る等）が引き続きパスすること。従来「1h クランプ」を前提にしたアサーション（`interval_minutes >= 60`）があれば、月粒度（`>= _MONTH_SENTINEL >= 60`）でも成立するため両立するが、`interval_minutes == 60` を厳密に期待する箇所があれば本 spec の変更に合わせて更新する。
- Summary / Top_IPs / Attack_Types / Severity / Risk_Ranking / Country_Summary の既存テストが不変であること（R5.1）。

### Frontend（ユーザー環境で検証）

- 変更は `AttackTimeline.tsx`（`period` prop 追加・月単位ラベル整形）と `DashboardPage.tsx`（`period` を渡す）に限定される。型は `string` period で既存と整合するため型エラーは発生しない想定。
- 検証項目（目視・ビルド）：`1y`/`all` 選択時に横軸が `YYYY/MM` 表記になる（R4.1）、`1h`〜`7d` 選択時は従来の時刻表示のまま（R4.2）、Total/SSH/HTTP の線・凡例・Tooltip が従来どおり（R4.3）、点数が月数分に減っている（`1y` で最大 13 点程度）。

---

## Requirements Traceability

| Requirement | 設計要素 |
|---|---|
| 1.1 1y は月単位集計 | `dashboard.py`: `period=="1y"` → `_MONTH_SENTINEL` → `get_timeline` の `date_trunc('month')`（Property 1/3） |
| 1.2 all は月単位集計 | 同上（`period=="all"`）（Property 1/3） |
| 1.3 interval によらず月粒度 | ルートで `1y`/`all` のとき interval を無視し `_MONTH_SENTINEL` 指定（Property 1） |
| 1.4 バケット代表時刻は月初 | `date_trunc('month', timestamp)` の結果を `timestamp` に返す |
| 2.1 1h〜7d は従来粒度 | ルートで `interval_map[interval]` を反映、`get_timeline` 既存分岐（Property 2/3） |
| 2.2 1h〜7d は interval 反映 | `interval_map` 反映（Property 2） |
| 3.1 1y は直近365日 | `resolve_period_range` 不変 |
| 3.2 all は下限なし | `resolve_period_range` 不変（`since=None`） |
| 3.3 変換ロジック不変 | `api/period.py` 未変更 |
| 4.1 月単位は YYYY/MM 表示 | `AttackTimeline`: `isMonthly` のとき `YYYY/MM` 整形 |
| 4.2 それ以外は時刻表示 | `AttackTimeline`: 従来 `toLocaleTimeString` |
| 4.3 内訳表示は不変 | Line/Legend/Tooltip 変更なし |
| 5.1 他エンドポイント不変 | timeline ルート・repo 粒度分岐のみ変更 |
| 5.2 テーブル不変 | マイグレーション非追加 |
| 5.3 レスポンス構造不変 | `timeline`/`timestamp`/`total`/`ssh`/`http` 維持 |
| 5.4 非 1y/all 呼び出し不変 | 月分岐は番兵値以上のみ、既存分岐は不変（Property 2/3） |
