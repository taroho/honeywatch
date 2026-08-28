"""攻撃イベントリポジトリ.

AttackEventModel に対する CRUD 操作を提供する。
API 層やワーカーから利用される。
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from honeywatch.db.models import AttackEventModel


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
        since: datetime,
        until: datetime,
    ) -> dict[str, int]:
        """指定期間の攻撃サマリーを取得する.

        Args:
            since: 集計開始日時
            until: 集計終了日時

        Returns:
            サマリー辞書（total, unique_ips, ssh_attempts, http_attacks）
        """
        base_filter = (
            AttackEventModel.timestamp >= since,
            AttackEventModel.timestamp <= until,
        )

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
        since: datetime,
        until: datetime,
        limit: int = 10,
    ) -> list[dict[str, object]]:
        """攻撃数の多い送信元 IP ランキングを取得する.

        Args:
            since: 集計開始日時
            until: 集計終了日時
            limit: 取得件数

        Returns:
            IP ごとの集計結果リスト
        """
        result = await self._session.execute(
            select(
                AttackEventModel.source_ip,
                func.count(AttackEventModel.id).label("event_count"),
                func.min(AttackEventModel.timestamp).label("first_seen"),
                func.max(AttackEventModel.timestamp).label("last_seen"),
            )
            .where(
                AttackEventModel.timestamp >= since,
                AttackEventModel.timestamp <= until,
            )
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
        since: datetime,
        until: datetime,
        interval_minutes: int = 60,
    ) -> list[dict[str, object]]:
        """時間帯別のイベント数を取得する（タイムライン用）.

        Args:
            since: 集計開始日時
            until: 集計終了日時
            interval_minutes: 集計間隔（分）

        Returns:
            時間帯ごとの集計結果リスト
        """
        # PostgreSQL の date_trunc + interval でバケット集計
        # interval_minutes に応じて適切な trunc 単位を選択
        if interval_minutes <= 5:
            trunc_expr = func.date_trunc("minute", AttackEventModel.timestamp)
        elif interval_minutes <= 15:
            trunc_expr = func.date_trunc("quarter_hour", AttackEventModel.timestamp)
        else:
            trunc_expr = func.date_trunc("hour", AttackEventModel.timestamp)

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
            .where(
                AttackEventModel.timestamp >= since,
                AttackEventModel.timestamp <= until,
            )
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
