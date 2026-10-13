"""HTTP ログインフォーム認証情報収集の純粋ロジックに関するテスト.

対象 spec: 7-feat-http-login-form-collection

本ファイルは design.md「Testing Strategy」のテスト配置に従い、認証情報の
抽出・切り詰め（純粋ロジック）に対応する以下を検証する。

- Property 4: 切り詰めは長さ上限を保ちつつ先頭を保存する（タスク 4.2）
- Property 2: form 抽出の round-trip（切り詰め範囲内で入力を復元）（タスク 4.3）
- Property 3: 欠落・空フィールドは空文字になる（タスク 4.4）
- form 解析失敗の edge テスト（タスク 4.5）

対象コードは ``src/honeywatch/honeypot/http.py`` の以下。

- ``_truncate(value, limit)``: モジュール関数（コードポイント単位の切り詰め）
- ``CredentialSubmission``: 抽出結果の dataclass（email / password / parsed）
- ``HTTPHoneypot._extract_credentials(raw_body)``: form ボディからの抽出

``_extract_credentials`` はインスタンスメソッドのため、既存 SSH テスト
（``test_ssh_connection_event.py``）に倣い、実 DB / Redis / 設定に依存しない
よう ``EventQueue`` をモックして ``HTTPHoneypot`` を生成する。``__init__`` は
``get_settings()`` で host / port を読むのみで外部接続は行わないため、これで
純粋ロジック（抽出・切り詰め）の検証に十分である。
"""

import json
from unittest.mock import MagicMock
from urllib.parse import urlencode

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from honeywatch.collector.handler import EventQueue
from honeywatch.core.config import get_max_credential_length
from honeywatch.honeypot.http import (
    CredentialSubmission,
    HTTPHoneypot,
    _truncate,
)

# ------------------------------------------------------------------
# テスト用ヘルパー
# ------------------------------------------------------------------


def _make_honeypot() -> HTTPHoneypot:
    """抽出ロジック検証用に HTTPHoneypot インスタンスを生成する.

    既存 SSH テストの方針（実 DB / Redis に依存させない）に倣い、EventQueue を
    MagicMock で差し替える。``_extract_credentials`` は event_queue を参照しない
    純粋ロジックのため、モックで十分である。

    Returns:
        抽出ロジック検証用の HTTPHoneypot インスタンス。
    """
    event_queue = MagicMock(spec=EventQueue)
    return HTTPHoneypot(event_queue)


def _encode_form(fields: dict[str, str]) -> bytes:
    """フィールド辞書を application/x-www-form-urlencoded のバイト列へ変換する.

    Args:
        fields: form フィールド名 → 値のマッピング。

    Returns:
        urlencode 後の UTF-8 バイト列。
    """
    return urlencode(fields).encode("utf-8")


# ------------------------------------------------------------------
# Property 4: 切り詰めは長さ上限を保ちつつ先頭を保存する（タスク 4.2）
# ------------------------------------------------------------------
# Feature: 7-feat-http-login-form-collection, Property 4: 切り詰めは長さ上限を
# 保ちつつ先頭を保存する。任意文字列 s と有効上限 n (1<=n<=4096) について、
# _truncate(s, n) は長さ n 以下かつ s[:n] に一致する。
# Validates: Requirements 2.4, 5.5
@settings(max_examples=100)
@given(value=st.text(), limit=st.integers(min_value=1, max_value=4096))
def test_truncate_preserves_prefix_within_limit(value: str, limit: int) -> None:
    """_truncate の結果が長さ上限以下かつ元文字列の先頭 limit 文字に一致する.

    Validates: Requirements 2.4, 5.5
    """
    result = _truncate(value, limit)

    # 長さは上限 limit 以下（コードポイント単位）
    assert len(result) <= limit
    # 先頭 limit 文字（元文字列のプレフィックス）が保存される
    assert result == value[:limit]


# ------------------------------------------------------------------
# Property 2: form 抽出の round-trip（タスク 4.3）
# ------------------------------------------------------------------
# Feature: 7-feat-http-login-form-collection, Property 2: form 抽出の round-trip
# （切り詰め範囲内で入力を復元）。長さ <= limit の email / password を
# urlencode して _extract_credentials に渡すと、抽出値は元値に一致する。
# Validates: Requirements 2.1
#
# 切り詰めが round-trip を乱さないよう、生成文字列の長さを現在の
# Max_Credential_Length 以下に制限する。urlencode は '&' / '=' 等を
# パーセントエンコードするため、特殊文字を含む値も安全に往復できる。
_MAX_LEN = get_max_credential_length()


@settings(max_examples=100)
@given(
    email=st.text(max_size=_MAX_LEN),
    password=st.text(max_size=_MAX_LEN),
)
def test_extract_credentials_round_trip(email: str, password: str) -> None:
    """切り詰め範囲内の email / password を urlencode→抽出すると元値に一致する.

    Validates: Requirements 2.1
    """
    honeypot = _make_honeypot()
    body = _encode_form({"email": email, "password": password})

    result = honeypot._extract_credentials(body)

    assert result.parsed is True
    assert result.email == email
    assert result.password == password


# ------------------------------------------------------------------
# Property 3: 欠落・空フィールドは空文字になる（タスク 4.4）
# ------------------------------------------------------------------
# Feature: 7-feat-http-login-form-collection, Property 3: 欠落・空フィールドは
# 空文字になる。email（または password）フィールドが存在しない、もしくは値が
# 空であるとき、CredentialSubmission の該当フィールドは空文字列（長さ 0）になる。
# Validates: Requirements 2.2, 2.3
#
# ジェネレータ: 各フィールドについて「欠落 / 空 / 非空値」の 3 状態を生成し、
# 少なくとも片方が欠落または空になるケースを対象とする（assume で制御）。
# 非空値は切り詰めが結果を乱さないよう長さ <= limit に制限する。


@st.composite
def _field_states(draw: st.DrawFn) -> tuple[str | None, str | None]:
    """email / password の状態を生成する.

    各要素は以下のいずれか。
    - None: フィールド欠落（form に含めない）
    - "": 空値（form に含めるが値は空）
    - 非空文字列: 通常値（長さ <= Max_Credential_Length）

    Returns:
        (email_state, password_state) のタプル。
    """
    choice = st.one_of(
        st.none(),
        st.just(""),
        st.text(min_size=1, max_size=_MAX_LEN),
    )
    return draw(choice), draw(choice)


@settings(max_examples=100)
@given(states=_field_states())
def test_missing_or_empty_fields_become_empty_string(
    states: tuple[str | None, str | None],
) -> None:
    """欠落・空の email / password が空文字列として抽出される.

    Validates: Requirements 2.2, 2.3
    """
    email_state, password_state = states
    # 少なくとも一方が欠落または空であるケースのみを対象とする
    assume(not email_state or not password_state)

    fields: dict[str, str] = {}
    if email_state is not None:
        fields["email"] = email_state
    if password_state is not None:
        fields["password"] = password_state

    honeypot = _make_honeypot()
    result = honeypot._extract_credentials(_encode_form(fields))

    # 欠落（None）または空（""）はいずれも空文字列になる
    if not email_state:
        assert result.email == ""
    if not password_state:
        assert result.password == ""


# ------------------------------------------------------------------
# form 解析失敗の edge テスト（タスク 4.5）
# ------------------------------------------------------------------
# 非 form ボディ（ランダムバイト・JSON・空）で email == "" / password == "" /
# parsed == False となり、例外を送出しないことを確認する。
# Validates: Requirements 2.5


def test_extract_credentials_random_bytes_is_not_parsed() -> None:
    """UTF-8 デコード不能なランダムバイトは解析失敗として空文字になる.

    Validates: Requirements 2.5
    """
    honeypot = _make_honeypot()
    # UTF-8 として不正なバイト列（0xFF は単独では不正な先頭バイト）
    raw_body = b"\xff\xfe\xfa\x80\x81\x82"

    result = honeypot._extract_credentials(raw_body)

    assert isinstance(result, CredentialSubmission)
    assert result.email == ""
    assert result.password == ""
    assert result.parsed is False


def test_extract_credentials_json_body_has_empty_fields() -> None:
    """JSON ボディには email / password フィールドが無く空文字になる.

    JSON は UTF-8 デコード可能なため parsed=True だが、form の email /
    password キーは存在しないため両値は空文字列になる（処理は継続する）。

    Validates: Requirements 2.5
    """
    honeypot = _make_honeypot()
    raw_body = json.dumps({"email": "a@example.com", "password": "secret"}).encode("utf-8")

    result = honeypot._extract_credentials(raw_body)

    assert isinstance(result, CredentialSubmission)
    # JSON 文字列には form の email= / password= キーが現れないため空文字
    assert result.email == ""
    assert result.password == ""


def test_extract_credentials_empty_body_has_empty_fields() -> None:
    """空ボディは email / password とも空文字になり例外を送出しない.

    Validates: Requirements 2.5
    """
    honeypot = _make_honeypot()

    result = honeypot._extract_credentials(b"")

    assert isinstance(result, CredentialSubmission)
    assert result.email == ""
    assert result.password == ""
    # 空文字は UTF-8 デコード可能なため parsed=True（解析自体は成功）
    assert result.parsed is True
