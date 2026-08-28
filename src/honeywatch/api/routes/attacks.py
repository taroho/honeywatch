"""攻撃イベント API エンドポイント.

イベント一覧のページネーション・フィルタ付き取得を提供する。
認証必須。
"""

from datetime import datetime

from fastapi import APIRouter, Query

from honeywatch.api.deps import AuthUser, DbSession
from honeywatch.db.repositories.attack import AttackEventRepository

router = APIRouter(prefix="/events", tags=["events"])


@router.get("")
async def list_events(
    _user: AuthUser,
    db: DbSession,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=100),
    protocol: str | None = Query(default=None, pattern="^(ssh|http)$"),
    source_ip: str | None = Query(default=None),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
) -> dict[str, object]:
    """攻撃イベント一覧を返す（ページネーション・フィルタ対応）.

    Args:
        page: ページ番号（1始まり）
        per_page: 1ページあたりの件数（最大100）
        protocol: プロトコルフィルタ（ssh, http）
        source_ip: 送信元 IP フィルタ
        since: 開始日時フィルタ
        until: 終了日時フィルタ

    Returns:
        イベント一覧とページネーション情報
    """
    repo = AttackEventRepository(db)
    events, total = await repo.list_events(
        protocol=protocol,
        source_ip=source_ip,
        since=since,
        until=until,
        page=page,
        per_page=per_page,
    )

    # モデルを辞書に変換
    events_data = [
        {
            "id": str(event.id),
            "timestamp": event.timestamp.isoformat(),
            "source_ip": event.source_ip,
            "source_port": event.source_port,
            "destination_port": event.destination_port,
            "protocol": event.protocol,
            "event_type": event.event_type,
            "raw_data": event.raw_data,
        }
        for event in events
    ]

    total_pages = (total + per_page - 1) // per_page

    return {
        "events": events_data,
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": total_pages,
        },
    }
