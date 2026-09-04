"""test_analysis 配下の共通フィクスチャ.

GeoIP_Resolver のテスト用に、``geoip2.database.Reader`` をモックした Resolver を提供する。

方針（design.md「Testing Strategy」に準拠）:
    実際の GeoLite2 .mmdb は配布・コミットしないため、テストでは Resolver を ``load``
    経由ではなく直接構築し、``resolver._reader`` にモックの Reader を差し込む。
    プライベート判定などの IP 種別ロジックは実際の ``ipaddress`` を通すため、モックは
    lookup 部分（Reader.city）だけに留める。

    モック Reader の ``.city(ip)`` は:
        - 登録済み IP に対して geoip2 の city レスポンス風オブジェクト
          （``country.iso_code`` / ``country.name`` / ``subdivisions.most_specific.name``
          / ``city.name`` / ``location.latitude`` / ``location.longitude``）を返す
        - 未登録 IP に対して ``geoip2.errors.AddressNotFoundError`` を送出する
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import geoip2.errors
import pytest

from honeywatch.analysis.geoip import GeoIPResolver

# テスト用の既知エントリ（パブリック IP → 地理情報）。
# geoip2 の city レスポンス構造に合わせた値を返すためのデータ。
KNOWN_ENTRIES: dict[str, dict[str, object]] = {
    "8.8.8.8": {
        "country_code": "US",
        "country_name": "United States",
        "region": "California",
        "city": "Mountain View",
        "latitude": 37.386,
        "longitude": -122.0838,
    },
    # 注: RFC 5737 のドキュメント用範囲（203.0.113.0/24 等）は Python の ipaddress で
    # 予約済み扱いとなり Resolver が DB 参照前に未解決を返すため、実在のパブリック IP を用いる。
    "9.9.9.9": {
        "country_code": "JP",
        "country_name": "Japan",
        "region": "Tokyo",
        "city": "Tokyo",
        "latitude": 35.6895,
        "longitude": 139.6917,
    },
    "1.1.1.1": {
        "country_code": "AU",
        "country_name": "Australia",
        "region": "Queensland",
        "city": "Brisbane",
        "latitude": -27.4679,
        "longitude": 153.0281,
    },
}


def _build_city_response(entry: dict[str, object]) -> SimpleNamespace:
    """既知エントリ辞書を geoip2 の city レスポンス風オブジェクトに変換する.

    Args:
        entry: 国コード・国名・地域・都市・緯度経度を持つ辞書

    Returns:
        ``response.country.iso_code`` 等の属性アクセスに対応する擬似レスポンス
    """
    return SimpleNamespace(
        country=SimpleNamespace(
            iso_code=entry["country_code"],
            name=entry["country_name"],
        ),
        subdivisions=SimpleNamespace(
            most_specific=SimpleNamespace(name=entry["region"]),
        ),
        city=SimpleNamespace(name=entry["city"]),
        location=SimpleNamespace(
            latitude=entry["latitude"],
            longitude=entry["longitude"],
        ),
    )


def _make_mock_reader(entries: dict[str, dict[str, object]]) -> MagicMock:
    """既知エントリを返し、未登録 IP には AddressNotFoundError を送出するモック Reader を生成する.

    Args:
        entries: IP → 地理情報辞書のマッピング

    Returns:
        ``.city(ip)`` を持つ ``MagicMock``（呼び出し回数の検証にも使える）
    """

    def _city(ip: str) -> SimpleNamespace:
        entry = entries.get(ip)
        if entry is None:
            # geoip2 の未登録時挙動を再現する
            raise geoip2.errors.AddressNotFoundError(f"{ip} not found")
        return _build_city_response(entry)

    reader = MagicMock()
    reader.city.side_effect = _city
    return reader


@pytest.fixture
def known_entries() -> dict[str, dict[str, object]]:
    """テスト用の既知エントリ（パブリック IP → 地理情報）を提供する."""
    return KNOWN_ENTRIES


@pytest.fixture
def mock_reader() -> MagicMock:
    """既知エントリを解決するモックの geoip2 Reader を提供する.

    ``city.call_count`` 等でリーダー参照回数の検証にも利用できる。
    """
    return _make_mock_reader(KNOWN_ENTRIES)


@pytest.fixture
def loaded_resolver(mock_reader: MagicMock) -> GeoIPResolver:
    """ロード済み（is_loaded=True 相当）の Resolver を提供する.

    実際の .mmdb をロードせず、モック Reader を ``_reader`` に差し込むことで
    「ロード済み」状態を再現する。既知エントリを解決できる。
    """
    resolver = GeoIPResolver(
        database_path="/mock/GeoLite2-City.mmdb",
        cache_size=100,
        enabled=True,
    )
    resolver._reader = mock_reader
    return resolver


@pytest.fixture
def unloaded_resolver() -> GeoIPResolver:
    """未ロード状態（_reader=None）の Resolver を提供する.

    存在しないパスを指定して直接構築するため、``_reader`` は None のまま。
    enabled=True なので resolve 時に「DB 利用不可」の warning を出す挙動になる。
    """
    return GeoIPResolver(
        database_path="/nonexistent/GeoLite2-City.mmdb",
        cache_size=100,
        enabled=True,
    )


@pytest.fixture
def disabled_resolver(mock_reader: MagicMock) -> GeoIPResolver:
    """機能無効（enabled=False）の Resolver を提供する.

    Reader を差し込んでいても enabled=False のため常に未解決を返す挙動を検証できる。
    """
    resolver = GeoIPResolver(
        database_path="/mock/GeoLite2-City.mmdb",
        cache_size=100,
        enabled=False,
    )
    resolver._reader = mock_reader
    return resolver
