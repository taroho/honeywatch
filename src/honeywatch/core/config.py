"""アプリケーション設定モジュール.

環境変数から設定を読み込み、pydantic-settings で型安全に管理する。
.env ファイルからの読み込みにも対応。
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    """PostgreSQL データベース接続設定."""

    model_config = SettingsConfigDict(env_prefix="DB_")

    host: str = "localhost"
    port: int = 5432
    user: str = "honeywatch"
    password: str = "honeywatch"
    name: str = "honeywatch"

    @property
    def async_url(self) -> str:
        """SQLAlchemy 用の非同期接続 URL を生成する."""
        return f"postgresql+asyncpg://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"


class RedisSettings(BaseSettings):
    """Redis 接続設定."""

    model_config = SettingsConfigDict(env_prefix="REDIS_")

    host: str = "localhost"
    port: int = 6379
    db: int = 0

    @property
    def url(self) -> str:
        """Redis 接続 URL を生成する."""
        return f"redis://{self.host}:{self.port}/{self.db}"


class HoneypotSettings(BaseSettings):
    """Honeypot サーバー設定."""

    model_config = SettingsConfigDict(env_prefix="HONEYPOT_")

    # SSH Honeypot
    ssh_host: str = "0.0.0.0"  # noqa: S104 — Honeypot は意図的に外部公開する
    # コンテナ内でリッスンするポート（非 root のため 1024 以上にする）
    ssh_port: int = 2222
    # 外部に公開されているポート（イベントの destination_port に記録する値）
    # None の場合は ssh_port を使う。ホスト 22 → コンテナ 2222 の場合は 22 を指定する。
    ssh_public_port: int | None = None
    ssh_max_auth_attempts: int = 10
    ssh_timeout: int = 30
    ssh_host_key_dir: str = "data/ssh_host_keys"

    # HTTP Honeypot
    http_host: str = "0.0.0.0"  # noqa: S104 — Honeypot は意図的に外部公開する
    http_port: int = 8080
    # 外部公開ポート（記録用）。None なら http_port を使う。
    http_public_port: int | None = None

    @property
    def ssh_reported_port(self) -> int:
        """イベントに記録する SSH の宛先ポート（公開ポート優先）."""
        return self.ssh_public_port if self.ssh_public_port is not None else self.ssh_port

    @property
    def http_reported_port(self) -> int:
        """イベントに記録する HTTP の宛先ポート（公開ポート優先）."""
        return self.http_public_port if self.http_public_port is not None else self.http_port


class APISettings(BaseSettings):
    """FastAPI サーバー設定."""

    model_config = SettingsConfigDict(env_prefix="API_")

    host: str = "127.0.0.1"
    port: int = 8000
    # Basic Auth 認証情報
    auth_user: str = "admin"
    auth_password: str = "changeme"


class Settings(BaseSettings):
    """アプリケーション全体の設定を統合するルート設定クラス."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 環境名（development / production）
    environment: str = "development"
    # ログレベル
    log_level: str = "INFO"

    # サブ設定
    db: DatabaseSettings = DatabaseSettings()
    redis: RedisSettings = RedisSettings()
    honeypot: HoneypotSettings = HoneypotSettings()
    api: APISettings = APISettings()


def get_settings() -> Settings:
    """アプリケーション設定のインスタンスを取得する."""
    return Settings()
