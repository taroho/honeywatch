"""GeoIP_Resolver のプロパティテスト（Hypothesis）とユニットテスト.

design.md「Correctness Properties」の Property 1〜4 を Hypothesis で検証し、
ログ出力・状態遷移・エッジケース（キャッシュ挙動含む）を例示テストで検証する。

ログ検証は structlog の ``capture_logs`` を用いる。本プロジェクトのロガーは
``core/logging.py`` の ``get_logger``（structlog）であり、``capture_logs`` は
structlog の処理チェーンを差し替えて発行ログをリスト形式で捕捉する。
"""

import ipaddress
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import geoip2.database
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from structlog.testing import capture_logs

from honeywatch.analysis.geoip import GeoIPResolver, GeoLocation
from honeywatch.core.config import GeoIPSettings

from .conftest import KNOWN_ENTRIES

# =====================================================================
# ヘルパー
# =====================================================================


def _is_parsable_ip(value: str) -> bool:
    """IPv4/IPv6 として解析可能かを返す（Property 4 の入力フィルタ用）."""
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return False
    return True


def _make_geoip_settings(database_path: str) -> GeoIPSettings:
    """テスト用の GeoIPSettings を生成する（環境変数の影響を避けて明示指定）."""
    return GeoIPSettings(
        database_path=database_path,
        cache_size=100,
        enabled=True,
    )


# =====================================================================
# プロパティテスト（Hypothesis）
# =====================================================================


# Feature: 4-feat-geoip-ip-location, Property 1: ロード済み Resolver はパブリック IP を
# 値域・形式を満たす Geo_Location に解決する
@given(ip=st.sampled_from(list(KNOWN_ENTRIES)))
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_property_loaded_resolver_resolves_public_ip(
    loaded_resolver: GeoIPResolver, ip: str
) -> None:
    """ロード済み Resolver は登録済みパブリック IP を値域・形式を満たす GeoLocation に解決する.

    Validates: Requirements 1.3, 2.1
    """
    location = loaded_resolver.resolve(ip)

    assert isinstance(location, GeoLocation)
    assert location.is_resolved
    # country_code は ISO 3166-1 alpha-2（2文字の英字）
    assert location.country_code is not None
    assert len(location.country_code) == 2
    assert location.country_code.isalpha()
    # 緯度は [-90, 90]
    assert location.latitude is not None
    assert -90.0 <= location.latitude <= 90.0
    # 経度は [-180, 180]
    assert location.longitude is not None
    assert -180.0 <= location.longitude <= 180.0


# Feature: 4-feat-geoip-ip-location, Property 2: 未ロード状態ではすべての IP が未解決になる
@given(
    ip=st.one_of(
        st.text(),
        st.ip_addresses(v=4).map(str),
        st.ip_addresses(v=6).map(str),
        st.none(),
    )
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_property_unloaded_resolver_always_unresolved(
    unloaded_resolver: GeoIPResolver, ip: str | None
) -> None:
    """未ロード状態の Resolver は任意の IP 文字列に対し常に全 None の未解決を返す.

    Validates: Requirements 1.6, 2.6
    """
    location = unloaded_resolver.resolve(ip)

    assert location == GeoLocation.unresolved()
    assert not location.is_resolved


# Feature: 4-feat-geoip-ip-location, Property 3: プライベート・予約 IP は DB を参照せず未解決になる
@given(
    ip=st.one_of(
        # RFC 1918 プライベート範囲
        st.ip_addresses(v=4, network="10.0.0.0/8").map(str),
        st.ip_addresses(v=4, network="172.16.0.0/12").map(str),
        st.ip_addresses(v=4, network="192.168.0.0/16").map(str),
        # ループバック
        st.ip_addresses(v=4, network="127.0.0.0/8").map(str),
        # リンクローカル
        st.ip_addresses(v=4, network="169.254.0.0/16").map(str),
    )
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_property_private_ip_unresolved_without_db(
    loaded_resolver: GeoIPResolver, mock_reader: MagicMock, ip: str
) -> None:
    """プライベート/ループバック/リンクローカル IP は DB 非参照で未解決になる.

    Validates: Requirements 1.7, 2.3
    """
    # 前提: 実際にプライベート/予約系であること
    parsed = ipaddress.ip_address(ip)
    assert (
        parsed.is_private or parsed.is_loopback or parsed.is_link_local or parsed.is_reserved
    )

    location = loaded_resolver.resolve(ip)

    assert location == GeoLocation.unresolved()
    # DB（Reader.city）が一切参照されていないこと
    assert mock_reader.city.call_count == 0


# Feature: 4-feat-geoip-ip-location, Property 4: 不正な IP 文字列は未解決になる
@given(text=st.text().filter(lambda s: not _is_parsable_ip(s)))
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_property_invalid_ip_string_unresolved(
    loaded_resolver: GeoIPResolver, text: str
) -> None:
    """IPv4/IPv6 として解析不能な任意文字列（空文字含む）は未解決になる.

    Validates: Requirements 2.4
    """
    location = loaded_resolver.resolve(text)
    assert location == GeoLocation.unresolved()


# =====================================================================
# ユニットテスト（例示）: ロード処理・状態遷移・ログ
# =====================================================================


def test_load_success_sets_loaded_and_logs_info(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """正常ロードで is_loaded=True かつ info ログ1件を出力する（Requirement 1.2）."""
    # 実ファイル存在チェックを通すためダミーの .mmdb を作成する
    db_path = tmp_path / "GeoLite2-City.mmdb"
    db_path.write_bytes(b"dummy")

    # geoip2.database.Reader をモックし、正常に構築できるようにする
    monkeypatch.setattr(geoip2.database, "Reader", lambda path: MagicMock())

    settings_obj = _make_geoip_settings(str(db_path))

    with capture_logs() as logs:
        resolver = GeoIPResolver.load(settings_obj)

    assert resolver.is_loaded is True
    info_logs = [e for e in logs if e.get("log_level") == "info"]
    assert len(info_logs) == 1


def test_load_missing_path_sets_unloaded_and_logs_error() -> None:
    """パス不在で is_loaded=False かつ error ログ1件を出力する（Requirement 1.4）."""
    settings_obj = _make_geoip_settings("/nonexistent/GeoLite2-City.mmdb")

    with capture_logs() as logs:
        resolver = GeoIPResolver.load(settings_obj)

    assert resolver.is_loaded is False
    error_logs = [e for e in logs if e.get("log_level") == "error"]
    assert len(error_logs) == 1


def test_load_corrupted_file_sets_unloaded_and_logs_error(tmp_path: Path) -> None:
    """破損/不正ファイルで is_loaded=False かつ error ログ1件を出力する（Requirement 1.5）."""
    # 不正なバイト列を持つ .mmdb を作成する（geoip2 のオープンに失敗する）
    db_path = tmp_path / "corrupted.mmdb"
    db_path.write_bytes(b"\x00\x01\x02not a valid mmdb\xff\xfe")

    settings_obj = _make_geoip_settings(str(db_path))

    with capture_logs() as logs:
        resolver = GeoIPResolver.load(settings_obj)

    assert resolver.is_loaded is False
    error_logs = [e for e in logs if e.get("log_level") == "error"]
    assert len(error_logs) == 1


# =====================================================================
# ユニットテスト（例示）: resolve のログ・エッジケース・キャッシュ
# =====================================================================


def test_resolve_when_unloaded_logs_warning(unloaded_resolver: GeoIPResolver) -> None:
    """未ロード時 resolve で warning ログ1件を出力し未解決を返す（Requirement 2.6）."""
    with capture_logs() as logs:
        location = unloaded_resolver.resolve("8.8.8.8")

    assert location == GeoLocation.unresolved()
    warning_logs = [e for e in logs if e.get("log_level") == "warning"]
    assert len(warning_logs) == 1


def test_resolve_disabled_returns_unresolved_without_warning(
    disabled_resolver: GeoIPResolver,
) -> None:
    """enabled=False では警告なしで未解決を返す（Requirement 1.6 と整合）."""
    with capture_logs() as logs:
        location = disabled_resolver.resolve("8.8.8.8")

    assert location == GeoLocation.unresolved()
    # enabled=False の場合は「DB 利用不可」警告を出さない
    warning_logs = [e for e in logs if e.get("log_level") == "warning"]
    assert len(warning_logs) == 0


def test_resolve_invalid_string_logs_warning(loaded_resolver: GeoIPResolver) -> None:
    """解析不能な文字列で warning ログ1件を出力し未解決を返す（Requirement 2.4）."""
    with capture_logs() as logs:
        location = loaded_resolver.resolve("not-an-ip")

    assert location == GeoLocation.unresolved()
    warning_logs = [e for e in logs if e.get("log_level") == "warning"]
    assert len(warning_logs) == 1


def test_resolve_partial_fields_preserved(
    loaded_resolver: GeoIPResolver, mock_reader: MagicMock
) -> None:
    """一部フィールド欠損でも取得できたフィールドは保持し、欠損は None（Requirement 2.5）."""

    # city.name=None, subdivisions が空（most_specific.name=None）のレスポンスを返す
    def _partial_city(ip: str) -> SimpleNamespace:
        return SimpleNamespace(
            country=SimpleNamespace(iso_code="FR", name="France"),
            subdivisions=SimpleNamespace(most_specific=SimpleNamespace(name=None)),
            city=SimpleNamespace(name=None),
            location=SimpleNamespace(latitude=48.8566, longitude=2.3522),
        )

    mock_reader.city.side_effect = _partial_city

    # 実在のパブリック IP を用いる（ドキュメント用予約範囲は DB 参照前に弾かれるため）
    location = loaded_resolver.resolve("9.9.9.9")

    # 取得できたフィールドは保持
    assert location.country_code == "FR"
    assert location.country_name == "France"
    assert location.latitude == 48.8566
    assert location.longitude == 2.3522
    # 欠損フィールドは None
    assert location.region is None
    assert location.city is None


def test_resolve_unregistered_public_ip_unresolved(loaded_resolver: GeoIPResolver) -> None:
    """未登録パブリック IP（AddressNotFoundError）で未解決を返す（Requirement 1.8, 2.2）."""
    # 既知エントリに含まれない実在のパブリック IP（モックが AddressNotFoundError を送出する）
    location = loaded_resolver.resolve("2.2.2.2")
    assert location == GeoLocation.unresolved()


def test_resolve_caches_result_lru_hit(
    loaded_resolver: GeoIPResolver, mock_reader: MagicMock
) -> None:
    """同一 IP を2回 resolve するとモック Reader.city は1回しか呼ばれない（LRU ヒット）."""
    first = loaded_resolver.resolve("8.8.8.8")
    second = loaded_resolver.resolve("8.8.8.8")

    assert first == second
    assert first.is_resolved
    # 2回目はキャッシュヒットのため DB 参照は1回のみ
    assert mock_reader.city.call_count == 1


# =====================================================================
# プロパティテスト（Hypothesis）: 国別集計ロジック（Property 6, 7）
# =====================================================================


def _make_dict_resolver(ip_to_country: dict[str, str | None]) -> MagicMock:
    """resolve をラップした軽量スタブ Resolver を生成する.

    ``ip_to_country`` に含まれる IP は対応する国コードの解決済み ``GeoLocation`` を
    返し、含まれない IP または国コードが None の IP は未解決を返す。DB や .mmdb には
    依存しない（CountryAggregator の集計ロジックのみを検証するため）。

    Args:
        ip_to_country: IP → 国コード（None は未解決）のマッピング

    Returns:
        ``resolve(ip)`` を持つ ``MagicMock``
    """

    def _resolve(ip: str) -> GeoLocation:
        country_code = ip_to_country.get(ip)
        if country_code is None:
            return GeoLocation.unresolved()
        return GeoLocation(
            country_code=country_code,
            country_name=None,
            region=None,
            city=None,
            latitude=None,
            longitude=None,
        )

    resolver = MagicMock()
    resolver.resolve.side_effect = _resolve
    return resolver


# 集計入力の生成戦略: 一意な IP をキーに、国コード（または None=未解決）と件数を持つ。
# distinct な IP 数を max_countries（既定1000）以下に抑えるため、IP のバリエーションを
# 制限する（切り詰めの影響を受けずに件数総和を検証できるようにする）。
_country_codes = st.sampled_from(["US", "JP", "CN", "AU", "FR", "DE", "GB", "BR"])
_ip_key = st.integers(min_value=0, max_value=50).map(lambda n: f"203.0.{n // 256}.{n % 256}")


@st.composite
def _ip_count_maps(draw: st.DrawFn) -> tuple[list[tuple[str, int]], dict[str, str | None]]:
    """(IP, 件数) 一覧と、対応する IP→国コード（None=未解決）マップを生成する.

    同一 IP が複数回現れうる一覧を作り、各一意 IP には国コードまたは None（未解決）を
    割り当てる。distinct な国コード数は _country_codes の範囲 + UNKNOWN に収まるため、
    max_countries=1000 では切り詰めが発生しない。
    """
    # 一意 IP → 国コード（None は未解決を意味する）
    mapping: dict[str, str | None] = draw(
        st.dictionaries(
            keys=_ip_key,
            values=st.one_of(_country_codes, st.none()),
            min_size=0,
            max_size=20,
        )
    )
    # 一覧は mapping のキーから重複ありで組み立てる（同一 IP 複数回を許容）
    keys = list(mapping.keys())
    if keys:
        ip_counts = draw(
            st.lists(
                st.tuples(st.sampled_from(keys), st.integers(min_value=0, max_value=1000)),
                min_size=0,
                max_size=40,
            )
        )
    else:
        ip_counts = []
    return ip_counts, mapping


# Feature: 4-feat-geoip-ip-location, Property 6: 国別集計は件数を保存し、未解決 IP を
# 「不明」区分に合算する
@given(data=_ip_count_maps())
@settings(max_examples=100)
def test_property_aggregate_preserves_count_and_unknown(
    data: tuple[list[tuple[str, int]], dict[str, str | None]],
) -> None:
    """集計結果の件数総和は入力総和に等しく、未解決 IP は UNKNOWN に合算される.

    Validates: Requirements 5.1, 5.9
    """
    ip_counts, mapping = data
    resolver = _make_dict_resolver(mapping)

    from honeywatch.analysis.geoip import UNKNOWN_COUNTRY, CountryAggregator

    # distinct な国コード + UNKNOWN は max_countries(1000) 以下なので切り詰められない
    result = CountryAggregator.aggregate(ip_counts, resolver, max_countries=1000)

    # 件数総和の保存
    assert sum(cc.count for cc in result) == sum(count for _, count in ip_counts)

    # 期待する国コード単位の合算を独立に算出して照合する
    expected: dict[str, int] = {}
    for ip, count in ip_counts:
        country = mapping.get(ip)
        key = country if country is not None else UNKNOWN_COUNTRY
        expected[key] = expected.get(key, 0) + count
    # 件数 0 の区分も aggregate は保持する（入力に現れた区分はすべて出力される）
    actual = {cc.country_code: cc.count for cc in result}
    assert actual == expected

    # 未解決 IP（mapping が None）由来の件数は UNKNOWN 区分に入ること
    unknown_expected = sum(
        count for ip, count in ip_counts if mapping.get(ip) is None
    )
    if unknown_expected > 0:
        assert actual.get(UNKNOWN_COUNTRY) == unknown_expected


# 多数の国コードを含む入力を生成する戦略（Property 7 用）。
# 国コードは2文字の大文字英字。IP は国コードをそのままキーにできるよう擬似 IP を割り当てる。
_many_country_codes = st.text(
    alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ", min_size=2, max_size=2
)


@st.composite
def _many_country_ip_counts(
    draw: st.DrawFn,
) -> tuple[list[tuple[str, int]], dict[str, str | None]]:
    """多数の国コードを含む (IP, 件数) 一覧と IP→国コードマップを生成する."""
    countries: list[str] = draw(
        st.lists(_many_country_codes, min_size=1, max_size=60, unique=True)
    )
    ip_counts: list[tuple[str, int]] = []
    mapping: dict[str, str | None] = {}
    for i, country in enumerate(countries):
        ip = f"198.51.{i // 256}.{i % 256}"
        mapping[ip] = country
        # 各国コードに 1 件以上の件数を割り当てる
        count = draw(st.integers(min_value=1, max_value=500))
        ip_counts.append((ip, count))
    return ip_counts, mapping


# Feature: 4-feat-geoip-ip-location, Property 7: 国別集計はソート順と件数上限の
# 不変条件を満たす
@given(
    data=_many_country_ip_counts(),
    max_countries=st.integers(min_value=1, max_value=100),
)
@settings(max_examples=100)
def test_property_aggregate_sort_order_and_limit(
    data: tuple[list[tuple[str, int]], dict[str, str | None]],
    max_countries: int,
) -> None:
    """集計結果は件数降順・同数は国コード昇順・要素数 <= max_countries を満たす.

    Validates: Requirements 3.4, 5.2, 5.3
    """
    ip_counts, mapping = data
    resolver = _make_dict_resolver(mapping)

    from honeywatch.analysis.geoip import CountryAggregator

    result = CountryAggregator.aggregate(ip_counts, resolver, max_countries=max_countries)

    # 件数上限
    assert len(result) <= max_countries

    # 件数降順、同数は国コード昇順
    for prev, curr in zip(result, result[1:], strict=False):
        assert prev.count >= curr.count
        if prev.count == curr.count:
            assert prev.country_code <= curr.country_code
