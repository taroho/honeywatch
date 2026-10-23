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
    BODY_PREVIEW_LIMIT,
    MAX_BODY_SIZE,
    CredentialSubmission,
    HTTPHoneypot,
    _body_preview_from_bytes,
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


# ==================================================================
# 修正 spec: 7.02-fix-body-preview-limit
# body_preview 保持上限の引き上げ（1024 → 8192）
# ------------------------------------------------------------------
# 対象コード: src/honeywatch/honeypot/http.py の以下。
# - BODY_PREVIEW_LIMIT: モジュール定数（保持する先頭バイト数）
# - _body_preview_from_bytes(body): 生ボディ先頭断片の文字列化（純粋関数）
#
# 保持上限の変更はこの共通ヘルパ 1 箇所に集約されるため、ヘルパ単体の検証で
# 全リクエスト経路（_handle_request / _handle_login）の挙動を担保できる。
# ==================================================================


# ------------------------------------------------------------------
# Property 1: BODY_PREVIEW_LIMIT は 8192 である
# ------------------------------------------------------------------
# Feature: 7.02-fix-body-preview-limit, Property 1。
# Validates: Requirements 1.1
def test_body_preview_limit_is_8192() -> None:
    """保持上限定数が 8192（8 KB）である.

    Validates: Requirements 1.1
    """
    assert BODY_PREVIEW_LIMIT == 8192


# ------------------------------------------------------------------
# Property 2: 8192 バイト超は先頭 8192 バイトに切り詰める
# ------------------------------------------------------------------
# Feature: 7.02-fix-body-preview-limit, Property 2。上限超過のバイト列について、
# _body_preview_from_bytes は b[:8192] の replace デコードと一致する（切り詰めが
# 発生する）。hypothesis が巨大な最小例を扱わずに済むよう、生成するのは「上限を
# 超える長さ（extra）」と「末尾を埋める 1 バイト（filler）」のみとし、
# `b"a" * 8192 + filler * extra` で上限超過ボディを構築する。先頭 8192 バイトは
# ASCII 'a' 固定で安定した期待値を保ちつつ、切り詰め挙動を検証する。
# Validates: Requirements 1.2
@settings(max_examples=100)
@given(
    extra=st.integers(min_value=1, max_value=8192),
    filler=st.binary(min_size=1, max_size=1),
)
def test_body_preview_truncates_over_limit(extra: int, filler: bytes) -> None:
    """上限超過のボディは先頭 BODY_PREVIEW_LIMIT バイトに切り詰めて文字列化する.

    Validates: Requirements 1.2
    """
    body = b"a" * BODY_PREVIEW_LIMIT + filler * extra
    assert len(body) > BODY_PREVIEW_LIMIT  # 前提: 上限超過

    result = _body_preview_from_bytes(body)

    # 切り詰め後は先頭 8192 バイト（ここでは ASCII 'a' * 8192）のみ
    assert result == body[:BODY_PREVIEW_LIMIT].decode("utf-8", errors="replace")


# ------------------------------------------------------------------
# Property 3: 1〜8192 バイトの非空ボディは全体を保持する
# ------------------------------------------------------------------
# Feature: 7.02-fix-body-preview-limit, Property 3。長さ 1〜8192 の非空バイト列
# について、_body_preview_from_bytes は切り詰めを行わず全体の replace デコードと
# 一致する。
# Validates: Requirements 1.3
@settings(max_examples=100)
@given(body=st.binary(min_size=1, max_size=8192))
def test_body_preview_keeps_whole_body_within_limit(body: bytes) -> None:
    """上限以下の非空ボディは全体を保持する（切り詰めなし）.

    Validates: Requirements 1.3
    """
    result = _body_preview_from_bytes(body)

    assert result == body.decode("utf-8", errors="replace")


# ------------------------------------------------------------------
# 境界 example テスト（オフバイワン防止）
# ------------------------------------------------------------------
# Feature: 7.02-fix-body-preview-limit, 境界（8192 ちょうど・8193）。
# ASCII バイトのみで構成し、バイト長と文字数が 1:1 対応する前提で境界を確認する。
# Validates: Requirements 1.2, 1.3
def test_body_preview_boundary_exactly_limit_keeps_all() -> None:
    """ちょうど 8192 バイトのボディは全体（8192 文字）を保持する.

    Validates: Requirements 1.3
    """
    body = b"a" * BODY_PREVIEW_LIMIT  # 8192 バイト（全て ASCII）

    result = _body_preview_from_bytes(body)

    assert result is not None
    assert len(result) == BODY_PREVIEW_LIMIT
    assert result == body.decode("utf-8")


def test_body_preview_boundary_over_limit_truncates_one() -> None:
    """8193 バイトのボディは先頭 8192 バイトで切れる（末尾 1 バイトが落ちる）.

    Validates: Requirements 1.2
    """
    body = b"a" * (BODY_PREVIEW_LIMIT + 1)  # 8193 バイト（全て ASCII）

    result = _body_preview_from_bytes(body)

    assert result is not None
    assert len(result) == BODY_PREVIEW_LIMIT
    assert result == body[:BODY_PREVIEW_LIMIT].decode("utf-8")


# ------------------------------------------------------------------
# Property 4: 空ボディは None を返す（不変の非回帰）
# ------------------------------------------------------------------
# Feature: 7.02-fix-body-preview-limit, Property 4。
# Validates: Requirements 1.4
def test_body_preview_empty_body_is_none() -> None:
    """空ボディは None を返す（上限引き上げ後も不変）.

    Validates: Requirements 1.4
    """
    assert _body_preview_from_bytes(b"") is None


# ------------------------------------------------------------------
# Property 5: 読み取り上限（MAX_BODY_SIZE）は不変
# ------------------------------------------------------------------
# Feature: 7.02-fix-body-preview-limit, Property 5。本修正は「保存する断片の
# 長さ」（BODY_PREVIEW_LIMIT）のみを引き上げ、「読み取り上限」（MAX_BODY_SIZE）
# は変更しない。1 MB 超 POST の 413・イベント非発行経路は _read_body_limited が
# 担い、本修正は同経路に一切触れていないため、読み取り上限が据え置かれている
# ことを定数レベルで非回帰確認する。
# Validates: Requirements 3.1, 3.2
def test_max_body_size_unchanged() -> None:
    """読み取り上限 MAX_BODY_SIZE が 1 MB のまま変更されていない.

    Validates: Requirements 3.1, 3.2
    """
    assert MAX_BODY_SIZE == 1_048_576


def test_body_preview_limit_below_max_body_size() -> None:
    """保存上限は読み取り上限より十分小さい（断片保存の方針を維持）.

    保持する断片長（BODY_PREVIEW_LIMIT）が読み取り上限（MAX_BODY_SIZE）を
    超えないことを保証し、「生ボディ全体を溜め込まない」方針を担保する。

    Validates: Requirements 3.1
    """
    assert BODY_PREVIEW_LIMIT < MAX_BODY_SIZE
