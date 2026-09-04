"""攻撃イベントリポジトリ.

AttackEventModel に対する CRUD 操作を提供する。
API 層やワーカーから利用される。
"""

from datetime import datetime
from typing import TypedDict
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from honeywatch.db.models import AttackEventModel

# get_timeline の集計粒度を月単位（date_trunc('month')）に切り替える番兵値（分）。
# interval_minutes がこの値以上のとき暦月バケットで集計する。30 日相当（30*24*60）。
# 通常の interval（5m/15m/1h → 5/15/60）では到達せず、1y/all のルートのみが渡す。
_MONTH_SENTINEL = 43200


class IPAggregate(TypedDict):
    """IP 別集計データ（プロファイル構築・Risk ランキング用）."""

    source_ip: str
    first_seen: datetime | None
    last_seen: datetime | None
    total_events: int
    attack_types: list[str]
    severities: list[str]


class AttackEventRepository:
    """攻撃イベントのデータベース操作を抽象化するリポジトリクラス."""

    def __init__(self, session: AsyncSession) -> None:
        """リポジトリを初期化する.

        Args:
            session: SQLAlchemy 非同期セッション
        """
        self._session = session

    async def create(self, event: AttackEventModel) -> AttackEventModel:
        """攻撃イベントを新規作成する.

        Args:
            event: 保存する攻撃イベントモデルインスタンス

        Returns:
            保存されたモデルインスタンス（ID, created_at が設定済み）
        """
        self._session.add(event)
        await self._session.commit()
        await self._session.refresh(event)
        return event

    async def create_bulk(self, events: list[AttackEventModel]) -> list[AttackEventModel]:
        """複数の攻撃イベントを一括作成する.

        Args:
            events: 保存する攻撃イベントモデルのリスト

        Returns:
            保存されたモデルインスタンスのリスト
        """
        self._session.add_all(events)
        await self._session.commit()
        return events

    async def get_by_id(self, event_id: UUID) -> AttackEventModel | None:
        """ID で攻撃イベントを取得する.

        Args:
            event_id: イベント UUID

        Returns:
            見つかったイベント。存在しない場合は None。
        """
        result = await self._session.execute(
            select(AttackEventModel).where(AttackEventModel.id == event_id)
        )
        return result.scalar_one_or_none()

    async def list_events(
        self,
        *,
        protocol: str | None = None,
        source_ip: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        page: int = 1,
        per_page: int = 50,
    ) -> tuple[list[AttackEventModel], int]:
        """攻撃イベント一覧を取得する（フィルタ・ページネーション対応）.

        Args:
            protocol: プロトコルフィルタ（ssh, http など）
            source_ip: 送信元 IP フィルタ
            since: 開始日時フィルタ
            until: 終了日時フィルタ
            page: ページ番号（1始まり）
            per_page: 1ページあたりの件数

        Returns:
            (イベントリスト, 総件数) のタプル
        """
        query = select(AttackEventModel)
        count_query = select(func.count(AttackEventModel.id))

        # フィルタ適用
        if protocol is not None:
            query = query.where(AttackEventModel.protocol == protocol)
            count_query = count_query.where(AttackEventModel.protocol == protocol)
        if source_ip is not None:
            query = query.where(AttackEventModel.source_ip == source_ip)
            count_query = count_query.where(AttackEventModel.source_ip == source_ip)
        if since is not None:
            query = query.where(AttackEventModel.timestamp >= since)
            count_query = count_query.where(AttackEventModel.timestamp >= since)
        if until is not None:
            query = query.where(AttackEventModel.timestamp <= until)
            count_query = count_query.where(AttackEventModel.timestamp <= until)

        # 総件数取得
        total_result = await self._session.execute(count_query)
        total = total_result.scalar_one()

        # ページネーション + ソート（新しい順）
        offset = (page - 1) * per_page
        query = query.order_by(AttackEventModel.timestamp.desc()).offset(offset).limit(per_page)

        result = await self._session.execute(query)
        events = list(result.scalars().all())

        return events, total

    async def get_summary(
        self,
        since: datetime | None,
        until: datetime,
    ) -> dict[str, int]:
        """指定期間の攻撃サマリーを取得する.

        Args:
            since: 集計開始日時（下限）。None の場合は下限フィルタを付けず、
                until 以前の全 Attack_Event を集計対象とする（all 期間）。
            until: 集計終了日時（上限）。常に適用される。

        Returns:
            サマリー辞書（total, unique_ips, ssh_attempts, http_attacks）
        """
        # until は常に適用し、since は None でなければ下限フィルタを追加する。
        # 非 None の since を渡す既存呼び出しは従来どおり両端フィルタとなる（後方互換）。
        base_filter = [AttackEventModel.timestamp <= until]
        if since is not None:
            base_filter.append(AttackEventModel.timestamp >= since)

        # 合計件数
        total_result = await self._session.execute(
            select(func.count(AttackEventModel.id)).where(*base_filter)
        )
        total = total_result.scalar_one()

        # ユニーク IP 数
        unique_ips_result = await self._session.execute(
            select(func.count(func.distinct(AttackEventModel.source_ip))).where(*base_filter)
        )
        unique_ips = unique_ips_result.scalar_one()

        # SSH 試行数
        ssh_result = await self._session.execute(
            select(func.count(AttackEventModel.id)).where(
                *base_filter,
                AttackEventModel.protocol == "ssh",
            )
        )
        ssh_attempts = ssh_result.scalar_one()

        # HTTP 攻撃数
        http_result = await self._session.execute(
            select(func.count(AttackEventModel.id)).where(
                *base_filter,
                AttackEventModel.protocol == "http",
            )
        )
        http_attacks = http_result.scalar_one()

        return {
            "total": total,
            "unique_ips": unique_ips,
            "ssh_attempts": ssh_attempts,
            "http_attacks": http_attacks,
        }

    async def get_top_ips(
        self,
        since: datetime | None,
        until: datetime,
        limit: int = 10,
    ) -> list[dict[str, object]]:
        """攻撃数の多い送信元 IP ランキングを取得する.

        Args:
            since: 集計開始日時（下限）。None の場合は下限フィルタを付けず、
                until 以前の全 Attack_Event を集計対象とする（all 期間）。
            until: 集計終了日時（上限）。常に適用される。
            limit: 取得件数

        Returns:
            IP ごとの集計結果リスト
        """
        # until は常に適用し、since は None でなければ下限フィルタを追加する（後方互換）。
        filters = [AttackEventModel.timestamp <= until]
        if since is not None:
            filters.append(AttackEventModel.timestamp >= since)

        result = await self._session.execute(
            select(
                AttackEventModel.source_ip,
                func.count(AttackEventModel.id).label("event_count"),
                func.min(AttackEventModel.timestamp).label("first_seen"),
                func.max(AttackEventModel.timestamp).label("last_seen"),
            )
            .where(*filters)
            .group_by(AttackEventModel.source_ip)
            .order_by(func.count(AttackEventModel.id).desc())
            .limit(limit)
        )

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

    async def get_timeline(
        self,
        since: datetime | None,
        until: datetime,
        interval_minutes: int = 60,
    ) -> list[dict[str, object]]:
        """時間帯別のイベント数を取得する（タイムライン用）.

        Args:
            since: 集計開始日時（下限）。None の場合は下限フィルタを付けず、
                until 以前の全 Attack_Event を集計対象とする（all 期間）。
            until: 集計終了日時（上限）。常に適用される。
            interval_minutes: 集計間隔（分）

        Returns:
            時間帯ごとの集計結果リスト
        """
        # PostgreSQL の date_trunc + interval でバケット集計
        # interval_minutes に応じて適切な trunc 単位を選択する。
        # 番兵値（>= _MONTH_SENTINEL）のときは暦月単位（1y/all 用）を最上位で判定する。
        if interval_minutes >= _MONTH_SENTINEL:
            trunc_expr = func.date_trunc("month", AttackEventModel.timestamp)
        elif interval_minutes <= 5:
            trunc_expr = func.date_trunc("minute", AttackEventModel.timestamp)
        elif interval_minutes <= 15:
            trunc_expr = func.date_trunc("quarter_hour", AttackEventModel.timestamp)
        else:
            trunc_expr = func.date_trunc("hour", AttackEventModel.timestamp)

        # until は常に適用し、since は None でなければ下限フィルタを追加する（後方互換）。
        filters = [AttackEventModel.timestamp <= until]
        if since is not None:
            filters.append(AttackEventModel.timestamp >= since)

        result = await self._session.execute(
            select(
                trunc_expr.label("bucket"),
                func.count(AttackEventModel.id).label("total"),
                func.count(AttackEventModel.id)
                .filter(AttackEventModel.protocol == "ssh")
                .label("ssh"),
                func.count(AttackEventModel.id)
                .filter(AttackEventModel.protocol == "http")
                .label("http"),
            )
            .where(*filters)
            .group_by("bucket")
            .order_by("bucket")
        )

        rows = result.all()
        return [
            {
                "timestamp": row.bucket,
                "total": row.total,
                "ssh": row.ssh,
                "http": row.http,
            }
            for row in rows
        ]

    async def get_ip_counts(
        self,
        since: datetime | None,
        until: datetime | None,
    ) -> list[tuple[str, int]]:
        """期間内の source_ip 別イベント件数を返す（国別集計の入力）.

        国別集計（CountryAggregator）の入力となる「IP と件数」の一覧を取得する。
        地理変換は行わず、DB では source_ip 単位の件数集計のみを担う
        （スキーマ変更なし方針のため、地理情報は DB に保持しない）。

        期間フィルタは AttackEventModel.timestamp に対して両端を含む
        （since が None でなければ ``>= since``、until が None でなければ ``<= until``）。
        since / until がいずれも None の場合は全期間を対象とする。

        Args:
            since: 集計開始日時（両端を含む）。None の場合は下限なし。
            until: 集計終了日時（両端を含む）。None の場合は上限なし。

        Returns:
            (source_ip, count) のタプルのリスト。件数の降順で返す
            （呼び出し側でソートするため順序は問わないが、安定のため降順とする）。
        """
        query = select(
            AttackEventModel.source_ip,
            func.count(AttackEventModel.id).label("event_count"),
        )

        # 期間フィルタ（両端を含む）。両方 None の場合はフィルタなし＝全期間。
        if since is not None:
            query = query.where(AttackEventModel.timestamp >= since)
        if until is not None:
            query = query.where(AttackEventModel.timestamp <= until)

        query = query.group_by(AttackEventModel.source_ip).order_by(
            func.count(AttackEventModel.id).desc()
        )

        result = await self._session.execute(query)
        rows = result.all()
        return [(row.source_ip, row.event_count) for row in rows]

    # === Phase 2: 分析用集計メソッド ===

    async def count_by_attack_type(
        self,
        since: datetime | None,
        until: datetime,
    ) -> list[dict[str, object]]:
        """攻撃タイプ別のイベント件数を取得する.

        Args:
            since: 集計開始日時（下限）。None の場合は下限フィルタを付けず、
                until 以前の全 Attack_Event を集計対象とする（all 期間）。
            until: 集計終了日時（上限）。常に適用される。

        Returns:
            攻撃タイプごとの件数リスト
        """
        # until と attack_type の非 NULL 条件は常に適用し、
        # since は None でなければ下限フィルタを追加する（後方互換）。
        filters = [
            AttackEventModel.timestamp <= until,
            AttackEventModel.attack_type.is_not(None),
        ]
        if since is not None:
            filters.append(AttackEventModel.timestamp >= since)

        result = await self._session.execute(
            select(
                AttackEventModel.attack_type,
                func.count(AttackEventModel.id).label("cnt"),
            )
            .where(*filters)
            .group_by(AttackEventModel.attack_type)
            .order_by(func.count(AttackEventModel.id).desc())
        )
        rows = result.all()
        return [
            {"attack_type": row.attack_type, "count": row.cnt} for row in rows
        ]

    async def count_by_severity(
        self,
        since: datetime | None,
        until: datetime,
    ) -> dict[str, int]:
        """Severity 別のイベント件数を取得する.

        Args:
            since: 集計開始日時（下限）。None の場合は下限フィルタを付けず、
                until 以前の全 Attack_Event を集計対象とする（all 期間）。
            until: 集計終了日時（上限）。常に適用される。

        Returns:
            Severity をキー、件数を値とする辞書
        """
        # until と severity の非 NULL 条件は常に適用し、
        # since は None でなければ下限フィルタを追加する（後方互換）。
        filters = [
            AttackEventModel.timestamp <= until,
            AttackEventModel.severity.is_not(None),
        ]
        if since is not None:
            filters.append(AttackEventModel.timestamp >= since)

        result = await self._session.execute(
            select(
                AttackEventModel.severity,
                func.count(AttackEventModel.id).label("cnt"),
            )
            .where(*filters)
            .group_by(AttackEventModel.severity)
        )
        rows = result.all()
        return {row.severity: row.cnt for row in rows}

    async def get_ip_aggregate(
        self,
        source_ip: str,
    ) -> IPAggregate | None:
        """指定 IP の集計データを取得する（プロファイル構築用）.

        Args:
            source_ip: 送信元 IP

        Returns:
            集計データ（初回・最終観測、総数、攻撃タイプ・Severity 一覧）。
            該当イベントがなければ None。
        """
        # 基本統計（初回・最終・総数）
        stats_result = await self._session.execute(
            select(
                func.min(AttackEventModel.timestamp).label("first_seen"),
                func.max(AttackEventModel.timestamp).label("last_seen"),
                func.count(AttackEventModel.id).label("total"),
            ).where(AttackEventModel.source_ip == source_ip)
        )
        stats = stats_result.one_or_none()
        if stats is None or stats.total == 0:
            return None

        # 観測された攻撃タイプ・Severity 一覧
        types_result = await self._session.execute(
            select(func.distinct(AttackEventModel.attack_type)).where(
                AttackEventModel.source_ip == source_ip,
                AttackEventModel.attack_type.is_not(None),
            )
        )
        attack_types = [row[0] for row in types_result.all()]

        sev_result = await self._session.execute(
            select(AttackEventModel.severity).where(
                AttackEventModel.source_ip == source_ip,
                AttackEventModel.severity.is_not(None),
            )
        )
        severities = [row[0] for row in sev_result.all()]

        return IPAggregate(
            source_ip=source_ip,
            first_seen=stats.first_seen,
            last_seen=stats.last_seen,
            total_events=stats.total,
            attack_types=attack_types,
            severities=severities,
        )

    async def get_ip_aggregates_for_ranking(
        self,
        since: datetime | None,
        until: datetime,
        limit: int = 100,
    ) -> list[IPAggregate]:
        """Risk ランキング算出用に、IP 別の集計データを取得する.

        イベント数の多い順に候補を絞り込み、各 IP の攻撃タイプ・Severity を返す。
        Risk Score の算出は呼び出し側（RiskScorer）で行う。

        Args:
            since: 集計開始日時（下限）。None の場合は下限フィルタを付けず、
                until 以前の全 Attack_Event を集計対象とする（all 期間）。
            until: 集計終了日時（上限）。常に適用される。
            limit: 対象とする上位 IP 数

        Returns:
            IP 別集計データのリスト
        """
        # until は常に適用し、since は None でなければ下限フィルタを追加する（後方互換）。
        # 下限フィルタは先頭の絞り込みクエリ（イベント数上位 IP の選定）にのみ適用する。
        filters = [AttackEventModel.timestamp <= until]
        if since is not None:
            filters.append(AttackEventModel.timestamp >= since)

        # まずイベント数上位の IP を絞り込む
        top_ips_result = await self._session.execute(
            select(
                AttackEventModel.source_ip,
                func.count(AttackEventModel.id).label("total"),
                func.min(AttackEventModel.timestamp).label("first_seen"),
                func.max(AttackEventModel.timestamp).label("last_seen"),
            )
            .where(*filters)
            .group_by(AttackEventModel.source_ip)
            .order_by(func.count(AttackEventModel.id).desc())
            .limit(limit)
        )
        top_ips = top_ips_result.all()

        aggregates: list[IPAggregate] = []
        for ip_row in top_ips:
            # 各 IP の攻撃タイプ・Severity を取得
            types_result = await self._session.execute(
                select(AttackEventModel.attack_type).where(
                    AttackEventModel.source_ip == ip_row.source_ip,
                    AttackEventModel.attack_type.is_not(None),
                )
            )
            attack_types = [row[0] for row in types_result.all()]

            sev_result = await self._session.execute(
                select(AttackEventModel.severity).where(
                    AttackEventModel.source_ip == ip_row.source_ip,
                    AttackEventModel.severity.is_not(None),
                )
            )
            severities = [row[0] for row in sev_result.all()]

            aggregates.append(
                IPAggregate(
                    source_ip=ip_row.source_ip,
                    first_seen=ip_row.first_seen,
                    last_seen=ip_row.last_seen,
                    total_events=ip_row.total,
                    attack_types=attack_types,
                    severities=severities,
                )
            )

        return aggregates
