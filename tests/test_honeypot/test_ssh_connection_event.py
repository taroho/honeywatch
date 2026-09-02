"""SSH 認証前接続の記録漏れ（Bug Condition）に関する探索テスト.

このテストは bugfix ワークフローの「探索フェーズ（修正前）」のためのものである。

方針（bugfix.md / design.md より）:
- バグ条件: SSH 接続でパスワード認証試行が 0 回のまま切断されたケース
  （`protocol == "ssh"` かつ切断時 `self._attempts == 0`）。
- 期待挙動（Property 1 / Requirement 2.1, 2.2, 2.3）:
  修正後 (F') は当該接続について `event_type="ssh_connection"` の `AttackEvent` を
  ちょうど 1 件発行する。

⚠️ 重要:
    このテストは「修正後に満たされるべき期待挙動」をエンコードしている。
    修正前コード（UNFIXED）では `connection_lost` が `logger.debug` のみで
    `emit_event` を呼ばないため、このテストは **必ず FAIL する**。
    FAIL することがバグの存在を裏付ける（この段階では FAIL が正しい結果）。

テスト方式:
    hypothesis は導入せず、`@pytest.mark.parametrize` で複数ケースを列挙する
    （tasks.md タスク 0 のユーザー確認済み方針）。
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from honeywatch.collector.events import AttackEvent
from honeywatch.honeypot.ssh import SSHHoneypotServer

# ------------------------------------------------------------------
# テスト用定数
# ------------------------------------------------------------------
# バグ条件の識別に使う認証試行回数（0 = 認証試行なし）
NO_AUTH_ATTEMPTS = 0
# 期待される ssh_connection イベントの発行件数
EXPECTED_SSH_CONNECTION_COUNT = 1
# honeypot.port（記録用宛先ポート）として使うダミー値
DUMMY_REPORTED_PORT = 22


def _make_mock_honeypot() -> MagicMock:
    """emit_event をモック化した SSHHoneypot 相当のダミーを生成する.

    SSHHoneypotServer は親 honeypot の `emit_event`（async）と `port` を参照する。
    ここでは実 DB / Redis / 設定に依存しないよう、両者をモックで差し替える。

    Returns:
        emit_event が AsyncMock、port が DUMMY_REPORTED_PORT のモック
    """
    honeypot = MagicMock()
    # emit_event は async メソッドなので AsyncMock で発行内容を捕捉する
    honeypot.emit_event = AsyncMock()
    # destination_port として記録される値（= ssh_reported_port 相当）
    honeypot.port = DUMMY_REPORTED_PORT
    return honeypot


def _make_dummy_conn(source_ip: str, source_port: int, client_version: str) -> MagicMock:
    """peername / client_version を返すダミーの asyncssh コネクションを生成する.

    Args:
        source_ip: 接続元 IP アドレス
        source_port: 接続元ポート番号
        client_version: SSH クライアントバージョン（空文字も許容）

    Returns:
        get_extra_info("peername") / ("client_version") に応答するモック
    """
    conn = MagicMock()

    def _get_extra_info(key: str, default: object = None) -> object:
        if key == "peername":
            return (source_ip, source_port)
        if key == "client_version":
            return client_version
        return default

    conn.get_extra_info.side_effect = _get_extra_info
    return conn


def _extract_emitted_events(honeypot: MagicMock) -> list[AttackEvent]:
    """emit_event モックに渡された AttackEvent の一覧を取り出す.

    Args:
        honeypot: _make_mock_honeypot() で生成したモック

    Returns:
        emit_event に渡された AttackEvent のリスト
    """
    return [call.args[0] for call in honeypot.emit_event.await_args_list]


async def _drain_pending_tasks() -> None:
    """connection_lost が asyncio.create_task でスケジュールした発行タスクを消化する.

    修正後コードは同期メソッド connection_lost 内から
    `asyncio.create_task(emit_event(...))` で発行をスケジュールする設計のため、
    テスト側でイベントループに制御を戻してタスクを完了させる必要がある。
    修正前コードでは create_task が発生しないため、ここで待っても何も起きない。
    """
    # 現在のループにスケジュール済みのタスクへ制御を渡す
    await asyncio.sleep(0)
    # 念のためもう一巡し、生成された発行タスク（emit_event）の完了を待つ
    pending = [
        t for t in asyncio.all_tasks() if t is not asyncio.current_task() and not t.done()
    ]
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)


# ------------------------------------------------------------------
# Property 1: Bug Condition — 認証試行なし接続の記録（修正前は FAIL）
# ------------------------------------------------------------------
# 各ケースは「バグ条件（validate_password 未呼び出し = self._attempts == 0）」を
# 満たす切断シーケンスを表現する。
#   - Banner Grab Test          : 正常切断（exc=None）
#   - Connection With Exception : 例外切断（exc=Exception(...)）
#   - client_version 空文字      : 接続段階で version 未取得（Requirement 2.3）
@pytest.mark.parametrize(
    ("case_id", "source_ip", "source_port", "client_version", "lost_exc"),
    [
        # Banner Grab Test: バージョン取得後に正常切断
        ("banner_grab", "203.0.113.10", 54321, "SSH-2.0-OpenSSH_9.6", None),
        # Connection With Exception Test: self._attempts == 0 かつ例外切断
        ("exception_close", "198.51.100.20", 40000, "SSH-2.0-libssh_0.10", Exception("reset")),
        # client_version 空文字ケース（接続段階で未取得でも発行を妨げない, Req 2.3）
        ("empty_client_version", "192.0.2.30", 33333, "", None),
    ],
)
async def test_connection_without_auth_emits_ssh_connection(
    case_id: str,
    source_ip: str,
    source_port: int,
    client_version: str,
    lost_exc: Exception | None,
) -> None:
    """認証試行なし接続の切断時に ssh_connection が 1 件発行されることを検証する.

    修正前コード（UNFIXED）では connection_lost が emit_event を呼ばないため、
    ssh_connection は 0 件となり、このテストは FAIL する（= バグの証拠）。

    Validates: Requirements 2.1, 2.2, 2.3
    """
    honeypot = _make_mock_honeypot()
    server = SSHHoneypotServer(honeypot)

    conn = _make_dummy_conn(source_ip, source_port, client_version)

    # 接続確立 → 認証試行なし → 切断（validate_password は呼ばない）
    server.connection_made(conn)
    # バグ条件の前提: 認証試行が 0 回であること
    assert server._attempts == NO_AUTH_ATTEMPTS, (
        f"[{case_id}] 前提崩壊: connection_made 直後は認証試行 0 のはず"
    )
    server.connection_lost(lost_exc)

    # 同期 connection_lost からスケジュールされた発行タスクを消化する
    await _drain_pending_tasks()

    events = _extract_emitted_events(honeypot)
    ssh_conn_events = [e for e in events if e.event_type == "ssh_connection"]

    # --- 期待挙動（実装後に満たされるべき Expected Behavior）---
    assert len(ssh_conn_events) == EXPECTED_SSH_CONNECTION_COUNT, (
        f"[{case_id}] ssh_connection がちょうど 1 件発行されるべき "
        f"（修正前は emit_event が呼ばれず 0 件 = バグ）。実際: {len(ssh_conn_events)} 件"
    )

    event = ssh_conn_events[0]
    assert event.source_ip == source_ip, f"[{case_id}] source_ip が接続元 IP と一致するべき"
    assert event.protocol == "ssh", f"[{case_id}] protocol は 'ssh' であるべき"
    assert event.destination_port == honeypot.port, (
        f"[{case_id}] destination_port は honeypot.port と一致するべき"
    )

    # raw_data の検証（design: Property 1 / 案B の dict 構築）
    assert event.raw_data["auth_attempts"] == NO_AUTH_ATTEMPTS, (
        f"[{case_id}] raw_data.auth_attempts は 0 であるべき"
    )
    duration = event.raw_data["connection_duration"]
    assert isinstance(duration, (int, float)) and duration >= 0, (
        f"[{case_id}] raw_data.connection_duration は 0 以上であるべき"
    )
    # client_version は空文字でも含まれること（Requirement 2.3）
    assert "client_version" in event.raw_data, (
        f"[{case_id}] raw_data に client_version が含まれるべき（空文字も許容）"
    )
    assert event.raw_data["client_version"] == client_version, (
        f"[{case_id}] raw_data.client_version は取得値と一致するべき"
    )
