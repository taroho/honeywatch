"""攻撃イベント Pydantic モデル定義.

Honeypot が生成するイベントの共通フォーマットと、
プロトコル固有のデータモデルを定義する。
"""

import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


class SSHEventData(BaseModel):
    """SSH Honeypot 固有のイベントデータ.

    SSH 認証試行時に記録する情報。
    パスワードは平文で保存する（攻撃パターン分析・辞書攻撃傾向の可視化に使用）。
    """

    username: str = Field(description="試行されたユーザー名")
    password: str = Field(description="試行されたパスワード（平文）")
    client_version: str = Field(default="", description="SSH クライアントバージョン文字列")
    connection_duration: float = Field(default=0.0, description="接続時間（秒）")
    auth_success: bool = Field(default=False, description="認証成功フラグ（常に False）")


class HTTPEventData(BaseModel):
    """HTTP Honeypot 固有のイベントデータ.

    HTTP リクエスト受信時に記録する情報。
    リクエストボディは先頭 1024 バイトのみ保持する。
    """

    method: str = Field(description="HTTP メソッド（GET, POST 等）")
    path: str = Field(description="リクエストパス")
    headers: dict[str, str] = Field(default_factory=dict, description="リクエストヘッダー")
    user_agent: str = Field(default="", description="User-Agent ヘッダー値")
    body_preview: str | None = Field(default=None, description="リクエストボディ先頭 1024 バイト")
    status_code: int = Field(default=200, description="返却したレスポンスのステータスコード")


class AttackEvent(BaseModel):
    """Honeypot が生成する攻撃イベントの共通フォーマット.

    すべてのプロトコルの Honeypot がこの形式でイベントを発行する。
    raw_data にはプロトコル固有の情報を辞書形式で格納する。
    """

    id: uuid.UUID = Field(default_factory=uuid.uuid4, description="イベント UUID")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="イベント発生タイムスタンプ（UTC）",
    )
    source_ip: str = Field(description="送信元 IP アドレス")
    source_port: int = Field(description="送信元ポート番号")
    destination_port: int = Field(description="宛先ポート番号（Honeypot リッスンポート）")
    protocol: Literal["ssh", "http"] = Field(description="プロトコル種別")
    event_type: str = Field(description="イベントタイプ（ssh_login_attempt, http_request 等）")
    raw_data: dict[str, object] = Field(
        default_factory=dict,
        description="プロトコル固有データ（JSON シリアライズ可能）",
    )

    def to_json_str(self) -> str:
        """JSON 文字列にシリアライズする（Redis Stream 投入用）."""
        return self.model_dump_json()

    @classmethod
    def from_json_str(cls, json_str: str) -> "AttackEvent":
        """JSON 文字列からデシリアライズする（Redis Stream 読み取り用）."""
        return cls.model_validate_json(json_str)
