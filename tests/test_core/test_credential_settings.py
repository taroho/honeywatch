"""CredentialSettings / get_max_credential_length のテスト.

HTTP ログインフォームで収集する email / password の最大文字数
（Max_Credential_Length）のクランプ挙動を検証する。

- Property テスト（Hypothesis）: 任意整数のクランプ（design.md Property 10）
- example テスト: 環境変数未設定時のデフォルト、非整数文字列による
  フォールバック（get_settings の ValidationError 捕捉）

Redis / DB に依存しない純粋ロジック・設定レイヤーのテスト。
"""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from honeywatch.core import config
from honeywatch.core.config import (
    CredentialSettings,
    get_max_credential_length,
)

# =====================================================================
# プロパティテスト（Hypothesis）
# =====================================================================


# Feature: 7-feat-http-login-form-collection,
# Property 10: Max_Credential_Length は有効範囲にクランプされる
# 任意の整数 n について、n が 1〜4096 の範囲内であれば n を、
# 範囲外であれば既定値 256 を返す。
@given(n=st.integers())
@settings(max_examples=100)
def test_property_max_credential_length_clamped(n: int) -> None:
    """任意整数 n について n∈[1,4096] なら n、さもなくば 256 を返す.

    max_credential_length_raw に任意の整数を設定し、property
    max_credential_length が有効範囲へクランプされることを検証する。

    **Validates: Requirements 5.2, 5.3, 5.4**
    """
    settings_obj = CredentialSettings(max_credential_length_raw=n)
    result = settings_obj.max_credential_length

    expected = n if 1 <= n <= 4096 else 256
    assert result == expected
    # 返り値は常に有効範囲内に収まる
    assert 1 <= result <= 4096


# =====================================================================
# example テスト
# =====================================================================


def test_get_max_credential_length_default_without_env() -> None:
    """環境変数未設定時は既定値 256 を返す.

    CredentialSettings のデフォルト（max_credential_length_raw=256）が
    そのまま有効値として返ることを確認する（要件 5.2）。

    _Requirements: 5.2_
    """
    assert get_max_credential_length() == 256


def test_get_max_credential_length_falls_back_on_non_integer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """非整数文字列設定時は ValidationError を捕捉し 256 にフォールバックする.

    環境変数 ``CREDENTIAL_MAX_CREDENTIAL_LENGTH`` に非整数文字列（例: "abc"）
    が指定されると pydantic の ValidationError が発生する。get_settings() が
    その検証失敗を送出する状況を再現し、get_max_credential_length() が例外を
    送出せず既定値 256 を返すことを確認する（要件 5.4）。

    get_settings() は credential サブ設定をインポート時のデフォルトインスタンス
    で保持するため環境変数を実行時に再読込しない。そのため、非整数文字列による
    ValidationError が発生する状況を get_settings の差し替えで忠実に再現する。

    _Requirements: 5.4_
    """

    def _raise_validation_error() -> config.Settings:
        # 非整数文字列を渡したときに実際に送出される ValidationError を再現する。
        CredentialSettings(max_credential_length_raw="abc")
        # 到達しない（上行で ValidationError が送出される）。
        raise AssertionError("ValidationError が送出されるはず")

    monkeypatch.setattr(config, "get_settings", _raise_validation_error)

    # get_settings() 内で ValidationError が送出されても、例外を捕捉して 256 を返す。
    assert get_max_credential_length() == 256


def test_credential_settings_raises_validation_error_on_non_integer() -> None:
    """参考: 非整数文字列は CredentialSettings 構築時に ValidationError となる.

    get_max_credential_length のフォールバック対象となる失敗条件
    （非整数文字列が ValidationError を引き起こす）が実在することを確認する。
    """
    with pytest.raises(ValidationError):
        CredentialSettings(max_credential_length_raw="abc")
