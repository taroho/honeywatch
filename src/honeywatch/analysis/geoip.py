"""GeoIP による IP → 地理情報の変換.

攻撃イベントの送信元 IP を MaxMind GeoLite2（.mmdb）で地理情報（Geo_Location）に
変換する。地理情報は永続化せず、リクエストのたびにオンザフライで解決する方針のため、
本モジュールはプロセス内 LRU キャッシュを備えた ``GeoIPResolver`` を提供する。

フェイルセーフ設計:
    .mmdb の不在・破損・未解決・不正 IP のいずれの場合も例外で処理を止めず、
    未解決（全フィールド None）の ``GeoLocation`` を返す。攻撃監視という主機能を
    GeoIP の障害で停止させないための方針である。
"""

import ipaddress
import os
from collections import OrderedDict
from dataclasses import dataclass

import geoip2.database
import geoip2.errors

from honeywatch.core.config import GeoIPSettings
from honeywatch.core.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class GeoLocation:
    """IP に対応する地理情報（未解決フィールドは None）.

    未解決（未登録 IP、プライベート IP、DB 未ロード、不正 IP）の場合は全フィールドが
    None になる。一部フィールドのみ欠損する場合は、取得できたフィールドは値を保持し、
    欠損フィールドのみ None とする。DB には保存しない。

    Attributes:
        country_code: ISO 3166-1 alpha-2 形式の国コード（例: "JP"）
        country_name: 国名
        region: 地域名（subdivision）
        city: 都市名
        latitude: 緯度（-90 〜 90）
        longitude: 経度（-180 〜 180）
    """

    country_code: str | None
    country_name: str | None
    region: str | None
    city: str | None
    latitude: float | None
    longitude: float | None

    @classmethod
    def unresolved(cls) -> "GeoLocation":
        """全フィールド None の未解決インスタンスを返す.

        Returns:
            すべてのフィールドが None の ``GeoLocation``
        """
        return cls(None, None, None, None, None, None)

    @property
    def is_resolved(self) -> bool:
        """地理情報が解決済みか（国コードを持つか）を返す.

        Returns:
            ``country_code`` が None でなければ True
        """
        return self.country_code is not None


class GeoIPResolver:
    """IP アドレスを ``GeoLocation`` に変換する中核コンポーネント.

    アプリ起動時に ``.mmdb`` を1回ロードし、シングルトンとして再利用することを想定する。
    同一 IP の繰り返し解決を高速化するため、プロセス内 LRU キャッシュを内部に持つ。

    スレッド安全性は保証しない（単純さを優先）。ロードに失敗した場合は未ロード状態で
    初期化され、以降 ``resolve`` は常に未解決を返す。
    """

    def __init__(self, database_path: str, cache_size: int, enabled: bool) -> None:
        """Resolver を初期化する（.mmdb のロードは行わない）.

        通常は ``load`` クラスメソッド経由で構築する。``__init__`` は状態フィールドの
        初期化のみを行い、リーダーは未設定（未ロード状態）のままとする。

        Args:
            database_path: GeoLite2-City.mmdb ファイルのパス
            cache_size: LRU キャッシュのエントリ上限
            enabled: 機能の有効/無効（無効時は常に未解決を返す）
        """
        self._database_path = database_path
        self._cache_size = cache_size
        self._enabled = enabled
        # ロード済みの geoip2 リーダー（未ロード時は None）
        self._reader: geoip2.database.Reader | None = None
        # プロセス内 LRU キャッシュ（挿入順を保持し、上限超過時に最古を追い出す）
        self._cache: OrderedDict[str, GeoLocation] = OrderedDict()

    @classmethod
    def load(cls, settings: GeoIPSettings) -> "GeoIPResolver":
        """設定に従い .mmdb をロードして Resolver を構築する（フェイルセーフ）.

        - パスにファイルが存在しない場合: 未ロード状態で初期化し error ログを1件出力する。
        - ファイルは存在するが破損・不正形式でリーダー生成に失敗した場合:
          未ロード状態で初期化し error ログを1件出力する。
        - 正常ロード時: 読み込み済み状態へ遷移し info ログを1件出力する。

        いずれの失敗でも例外は送出せず、Resolver インスタンスを返す。

        Args:
            settings: GeoIP 設定

        Returns:
            構築された ``GeoIPResolver``（ロード成否は ``is_loaded`` で判定する）
        """
        resolver = cls(
            database_path=settings.database_path,
            cache_size=settings.cache_size,
            enabled=settings.enabled,
        )

        # パス不在: 未ロード状態のまま error ログを出力
        if not os.path.isfile(settings.database_path):
            logger.error(
                "geoip database file not found",
                path=settings.database_path,
            )
            return resolver

        try:
            # geoip2.database.Reader は内部で maxminddb を用いてメモリ効率よく読み込む
            resolver._reader = geoip2.database.Reader(settings.database_path)
        except Exception as exc:
            # ファイル破損・不正形式など: 未ロード状態のまま error ログを出力
            logger.error(
                "failed to load geoip database",
                path=settings.database_path,
                error=str(exc),
            )
            return resolver

        logger.info("geoip database loaded", path=settings.database_path)
        return resolver

    @property
    def is_loaded(self) -> bool:
        """DB 読み込み済み状態かを返す.

        Returns:
            リーダーがロード済みなら True
        """
        return self._reader is not None

    def resolve(self, ip: str | None) -> GeoLocation:
        """IP を ``GeoLocation`` に変換する（未解決時は未解決インスタンスを返す）.

        処理フローは design.md に準拠する:
            1. 無効化（enabled=False）または未ロード → 未解決を返す。
               未ロード時は warning ログを1件出力する。
            2. None / 空文字 / IP として解析不能 → warning ログを1件出力して未解決を返す。
            3. プライベート / ループバック / リンクローカル / 予約 / 未指定アドレス
               → DB を参照せず未解決を返す（ログ不要）。
            4. パブリック IP → LRU キャッシュを参照し、ヒットすれば返す。
            5. ミス → .mmdb を参照。未登録なら未解決、取得できた項目のみ埋めた
               ``GeoLocation`` を生成する。
            6. 結果（未解決含む）をキャッシュに格納して返す。

        Args:
            ip: 解決対象の IP アドレス文字列（None も許容）

        Returns:
            解決された ``GeoLocation``（未解決時は全フィールド None）
        """
        # 1. 無効化または未ロード（Requirement 1.6, 2.6）
        if not self._enabled or self._reader is None:
            if self._enabled and self._reader is None:
                # 有効だがロードされていない場合のみ、DB 利用不可を警告する
                logger.warning("geoip database is not available")
            return GeoLocation.unresolved()

        # 2. None / 空文字 / 解析不能な文字列（Requirement 2.4）
        if ip is None or ip == "":
            logger.warning("invalid ip address for geoip resolve", ip=ip)
            return GeoLocation.unresolved()

        try:
            parsed = ipaddress.ip_address(ip)
        except ValueError:
            logger.warning("invalid ip address for geoip resolve", ip=ip)
            return GeoLocation.unresolved()

        # 3. プライベート・予約系アドレス（Requirement 1.7, 2.3）
        if (
            parsed.is_private
            or parsed.is_loopback
            or parsed.is_link_local
            or parsed.is_reserved
            or parsed.is_unspecified
            or parsed.is_multicast
        ):
            return GeoLocation.unresolved()

        # 4. LRU キャッシュ参照
        cached = self._cache.get(ip)
        if cached is not None:
            # 参照されたエントリを最新に移動する（LRU）
            self._cache.move_to_end(ip)
            return cached

        # 5. .mmdb 参照
        location = self._lookup(ip)

        # 6. 結果（未解決含む）をキャッシュに格納する
        self._cache_put(ip, location)
        return location

    def _lookup(self, ip: str) -> GeoLocation:
        """ロード済みリーダーで IP を検索し ``GeoLocation`` を組み立てる.

        未登録 IP（``AddressNotFoundError``）は未解決を返す（Requirement 1.8, 2.2）。
        取得できたフィールドのみ値を保持し、欠損フィールドは None とする
        （Requirement 2.5）。

        Args:
            ip: パブリック IP アドレス文字列

        Returns:
            検索結果の ``GeoLocation``（未登録時は未解決）
        """
        assert self._reader is not None  # noqa: S101 — resolve 側でロード済みを保証

        try:
            response = self._reader.city(ip)
        except geoip2.errors.AddressNotFoundError:
            return GeoLocation.unresolved()

        # 国コード（ISO 3166-1 alpha-2）と国名
        country_code = response.country.iso_code
        country_name = response.country.name
        # 地域名（最も詳細な subdivision の名称）
        region = response.subdivisions.most_specific.name
        # 都市名
        city = response.city.name
        # 緯度・経度（float、欠損時は None）
        latitude = response.location.latitude
        longitude = response.location.longitude

        return GeoLocation(
            country_code=country_code,
            country_name=country_name,
            region=region,
            city=city,
            latitude=float(latitude) if latitude is not None else None,
            longitude=float(longitude) if longitude is not None else None,
        )

    def _cache_put(self, ip: str, location: GeoLocation) -> None:
        """LRU キャッシュへエントリを格納する（上限超過時は最古を追い出す）.

        Args:
            ip: キャッシュキーとなる IP アドレス
            location: 格納する解決結果
        """
        # cache_size が 0 以下の場合はキャッシュを使わない
        if self._cache_size <= 0:
            return

        self._cache[ip] = location
        self._cache.move_to_end(ip)
        # 上限を超えた分を最古（先頭）から追い出す
        while len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)

    def close(self) -> None:
        """.mmdb リーダーをクローズする（シャットダウン時に呼び出す）.

        既に未ロードの場合は何もしない。
        """
        if self._reader is not None:
            self._reader.close()
            self._reader = None


# 「不明」区分を表す固定キー（未解決 IP の集計先）
UNKNOWN_COUNTRY = "UNKNOWN"


@dataclass(frozen=True)
class CountryCount:
    """国コード単位の攻撃件数集計結果.

    国別集計の1区分を表す不変データ構造。未解決の IP は ``country_code`` が
    ``UNKNOWN_COUNTRY``（"UNKNOWN"）の区分に合算される。

    Attributes:
        country_code: ISO 3166-1 alpha-2 形式の国コード（例: "JP"）、
            または未解決区分を表す "UNKNOWN"
        count: その国コードに集計された Attack_Event 件数
    """

    country_code: str
    count: int


class CountryAggregator:
    """(IP, 件数) の一覧を国コード単位に再集計するロジック.

    DB からは「IP と件数」だけを取得し、地理変換と国コード単位の再集計をアプリ層で
    行う。これにより ``attack_events`` テーブルのスキーマを一切変更しない
    （オンザフライ解決方針）。
    """

    @staticmethod
    def aggregate(
        ip_counts: list[tuple[str, int]],
        resolver: GeoIPResolver,
        *,
        max_countries: int = 1000,
    ) -> list[CountryCount]:
        """(IP, 件数) の一覧を国コード単位に集計する.

        処理内容:
            - 各 IP を ``resolver.resolve`` で解決し、解決できた場合は
              ``GeoLocation.country_code`` 単位で件数を合算する。
            - 未解決（``is_resolved`` が False、または ``country_code`` が None）の
              IP は ``UNKNOWN_COUNTRY`` 区分に合算する（Requirement 5.9）。
            - 件数の降順、件数が同一の場合は国コードの昇順でソートする
              （Requirement 5.2）。"UNKNOWN" も通常の文字列として昇順比較に含める。
            - 上位 ``max_countries`` 件に切り詰め、それを超える区分は返さない
              （Requirement 5.3）。
            - 入力が空の場合は空リストを返す（Requirement 5.8）。

        Args:
            ip_counts: (IP アドレス, 件数) のタプル一覧
            resolver: IP を地理情報に解決する ``GeoIPResolver``
            max_countries: 返す国コード区分の上限件数（既定 1000）

        Returns:
            件数降順・同数は国コード昇順でソートされた ``CountryCount`` の一覧
            （最大 ``max_countries`` 件）
        """
        # 国コード（または UNKNOWN）ごとに件数を合算する
        totals: dict[str, int] = {}
        for ip, count in ip_counts:
            location = resolver.resolve(ip)
            # 未解決（country_code が None）は UNKNOWN 区分に合算する
            if location.is_resolved and location.country_code is not None:
                key = location.country_code
            else:
                key = UNKNOWN_COUNTRY
            totals[key] = totals.get(key, 0) + count

        # 件数降順、同数は国コード昇順でソートする
        sorted_counts = sorted(
            (CountryCount(country_code=code, count=total) for code, total in totals.items()),
            key=lambda cc: (-cc.count, cc.country_code),
        )

        # 上位 max_countries 件に切り詰める
        return sorted_counts[:max_countries]
